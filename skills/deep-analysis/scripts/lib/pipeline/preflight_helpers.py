"""pipeline.preflight_helpers · stage1 顶部 preflight + ticker 解析 · v3.1 抽离.

### 抽离内容（从 run_real_test.py::stage1 line 431-596 搬）

- 网络 preflight（GFW / 代理探测）· 失败自动切 lite
- `_detect_lite_mode` + LITE MODE 环境变量设置
- 中文名解析（`resolve_chinese_name_rich`）· 失败返候选 early-exit
- ETF / LOF / 可转债识别 · 非个股 early-exit + ETF 持仓建议

### API

```python
result = prepare_target(ticker)
if not result["ok"]:
    return result["payload"]  # early-exit · stage1 直接 return
ti = result["ticker_info"]    # 继续正常流程
```

### 向后兼容

stage1 里的行为零变化 · 只是代码组织更清晰。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from lib.market_router import parse_ticker, is_chinese_name


def prepare_target(ticker: str, *, detect_lite_fn=None) -> dict[str, Any]:
    """stage1 开局的预处理 · 返回 {"ok": bool, "ticker_info" | "payload"}.

    Args:
      ticker: 用户输入（支持代码/中文名/带后缀）
      detect_lite_fn: 注入 rrt._detect_lite_mode（避免循环 import）

    Returns:
      成功: {"ok": True, "ticker_info": TickerInfo}
      早退: {"ok": False, "early_exit": "name_not_resolved"/"non_stock_security", "payload": dict}
    """
    # v2.10.2 · 全局 requests timeout 兜底（akshare 内部调用不会卡死）
    try:
        from lib import net_timeout_guard  # noqa: F401（import 副作用装 monkey-patch）
    except Exception as _e:
        print(f"  ⚠️ timeout guard load failed: {_e}")

    # v2.10.2 · 网络预检（代理/GFW 挂了立即提示，不让 20 fetcher 挨个超时 30 分钟）
    skip_preflight = os.environ.get("UZI_SKIP_PREFLIGHT") == "1"
    if not skip_preflight:
        try:
            from lib.network_preflight import run_preflight
            pre = run_preflight(verbose=True, timeout=3.0)
            # v2.13.5 · NetworkProfile 返 dataclass · 用 severity 判定
            # critical/degraded → 强制 lite（除非 UZI_LITE=0 显式覆盖）
            if pre.severity in ("critical", "degraded") and os.environ.get("UZI_LITE") != "0":
                os.environ["UZI_LITE"] = "1"
                print(f"   ⚡ 网络受限（{pre.severity}），自动切 lite 模式防止挂太久\n")
        except Exception as _e:
            print(f"  ⚠️ preflight failed (非致命): {_e}")

    # Lite mode detection
    if detect_lite_fn is not None:
        is_lite, lite_reason = detect_lite_fn()
        if is_lite:
            os.environ["UZI_LITE"] = "1"  # 下游 fetcher 能读
            os.environ.setdefault("UZI_DDG_BUDGET", "15")  # 全局 ddgs 预算上限
            print(f"\n⚡ LITE MODE: {lite_reason}")
            print(f"   · 跳过 fetch_macro/policy/moat 的 ddgs 查询（返回空让 agent 自己补）")
            print(f"   · fetch_industry 跳过动态景气度查询（省 3-9 次 ddgs）")
            print(f"   · wave3 fund_holders 默认 top 20（UZI_FUND_LIMIT=all 可覆盖）")
            print(f"   · 全局 ddgs 预算 15 次/ticker（超出自动 skip）")
            print(f"   · 完整跑请 UZI_LITE=0 && python run.py <ticker>\n")

    # v2.3 · 中文名解析 — 支持纠错提示。若输入无法明确解析，早退并返回候选
    ti = None
    if is_chinese_name(ticker):
        try:
            from lib import data_sources as _ds
            r = _ds.resolve_chinese_name_rich(ticker)
            if r["resolved"] is not None:
                if r["source"] != "exact":
                    print(f"  [resolve] {ticker} → {r['resolved'].full} (via {r['source']})")
                ti = r["resolved"]
            elif r["candidates"]:
                # Early-exit with structured suggestions
                safe_dir = Path(".cache") / ticker
                safe_dir.mkdir(parents=True, exist_ok=True)
                err_payload = {
                    "status": "name_not_resolved",
                    "user_input": ticker,
                    "candidates": r["candidates"],
                    "message": f"未能确认 '{ticker}' 对应的股票。最接近的候选: "
                               + ", ".join(f"{c['name']}({c['code']})" for c in r["candidates"][:3]),
                }
                (safe_dir / "_resolve_error.json").write_text(
                    json.dumps(err_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
                )
                print(f"\n🔴 无法确认股票: {ticker!r}")
                print(f"   你是不是想输入：")
                for c in r["candidates"][:5]:
                    print(f"     · {c['name']} ({c['code']})   [编辑距离 {c['distance']}]")
                print(f"   请用 --force-name <代码> 指定，或用准确名称/代码重跑。")
                return {"ok": False, "early_exit": "name_not_resolved", "payload": err_payload}
            else:
                ti = parse_ticker(ticker)  # last resort, will likely fail fetcher
        except Exception:
            ti = parse_ticker(ticker)
    else:
        ti = parse_ticker(ticker)

    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"🎯 TARGET: {ti.full}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    # v2.9.2 · ETF / LOF / 可转债识别
    guard = _check_non_stock_security(ti)
    if guard is not None:
        return {"ok": False, "early_exit": "non_stock_security", "payload": guard}

    return {"ok": True, "ticker_info": ti}


def _check_non_stock_security(ti) -> dict | None:
    """v2.9.2 · ETF/LOF/可转债拦截 · 返 err_payload 或 None.

    ETF 会额外拉前 10 大持仓供用户选成分股.
    """
    if ti.market != "A":
        return None
    try:
        from lib.market_router import classify_security_type
        sec_type = classify_security_type(ti.code)
    except Exception as e:
        print(f"  ⚠️ 非个股检测出错，继续走正常流程: {type(e).__name__}: {str(e)[:80]}")
        return None

    NON_STOCK_GUIDANCE = {
        "etf": ("ETF", "51 评委跑 ROE / 护城河 / 管理层 / 分红 这些个股财务指标，ETF 没这些字段",
                "建议：分析该 ETF 前 3-5 大持仓股（用 akshare.fund_portfolio_hold_em 查持仓），对每只成分股单独跑 /analyze-stock"),
        "lof": ("LOF 基金", "基金没有企业基本面字段", "基金评估用专门的 fund-analyze 工具"),
        # v3.4.3 · 开放式基金（OEIC）· 跟 ETF 一样循环分析持仓
        "mutual_fund": ("开放式基金", "基金没有企业基本面字段（个股评委不适用）",
                        "已自动改为分析该基金的前 10 大重仓股（akshare.fund_portfolio_hold_em）"),
        "convertible_bond": ("可转债", "可转债看转股价/溢价率/到期收益率，不是 ROE", "分析正股或用集思录的可转债工具"),
    }
    # 中证指数（Hxxxxx）有专用的指数估值/股息率采集路径，不应再被当成
    # ETF 或个股错误拦截；其它非个股标的仍按原有引导处理。
    if sec_type == "index":
        return None
    if sec_type not in NON_STOCK_GUIDANCE:
        return None

    label, why, what_to_do = NON_STOCK_GUIDANCE[sec_type]
    safe_dir = Path(".cache") / ti.full
    safe_dir.mkdir(parents=True, exist_ok=True)

    # v2.9.2 · ETF 特殊处理：拉前 10 大持仓供用户选择
    # v3.4.3 · LOF / mutual_fund 也走同样的持仓拉取（akshare.fund_portfolio_hold_em 对三类基金都 work）
    top_holdings: list[dict] = []
    if sec_type in ("etf", "lof", "mutual_fund"):
        try:
            import akshare as ak
            df = ak.fund_portfolio_hold_em(symbol=ti.code)
            if df is not None and not df.empty:
                # 找最新一期（通常按日期倒序）
                if "季度" in df.columns:
                    latest_period = df["季度"].iloc[0]
                    df_latest = df[df["季度"] == latest_period]
                else:
                    df_latest = df
                for i, (_, row) in enumerate(df_latest.head(10).iterrows(), start=1):
                    stock_code = str(row.get("股票代码", "") or row.get("code", "") or "").strip()
                    stock_name = str(row.get("股票名称", "") or row.get("name", "") or "").strip()
                    pct_raw = row.get("占净值比例") or row.get("比例") or row.get("weight") or ""
                    try:
                        pct = float(str(pct_raw).replace("%", "")) if pct_raw else 0
                    except (ValueError, TypeError):
                        pct = 0
                    if stock_code and stock_name:
                        try:
                            _ti_stock = parse_ticker(stock_code)
                            full_code = _ti_stock.full
                        except Exception:
                            full_code = stock_code
                        top_holdings.append({
                            "rank": i,
                            "code": full_code,
                            "name": stock_name,
                            "weight_pct": round(pct, 2) if pct else None,
                        })
        except Exception as _e:
            print(f"  ⚠️ 拉 ETF 持仓失败: {type(_e).__name__}: {str(_e)[:80]}")

    err_payload = {
        "status": "non_stock_security",
        "security_type": sec_type,
        "ticker": ti.full,
        "label": label,
        "why": why,
        "what_to_do": what_to_do,
        "top_holdings": top_holdings,  # ETF 才填
        "message": (
            f"{ti.full} 是 {label}，不是个股 — 本插件未设计支持这类标的。\n"
            f"原因: {why}\n"
            f"{what_to_do}"
        ),
        "user_prompt": (
            "请选择要分析的成分股（输入编号或代码），例如：`/analyze-stock 1` 或 `/analyze-stock 601899`"
            if top_holdings else ""
        ),
    }
    (safe_dir / "_resolve_error.json").write_text(
        json.dumps(err_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\n🔴 非个股标的: {ti.full} ({label})")
    print(f"   本插件是**个股**深度分析引擎，{why}")
    if sec_type == "etf" and top_holdings:
        print(f"\n   📊 不过我可以帮你识别 {ti.full} 的前 {len(top_holdings)} 大持仓，请选一只分析：\n")
        for h in top_holdings:
            pct_str = f"{h['weight_pct']:.2f}%" if h.get("weight_pct") else "—"
            print(f"     {h['rank']:2d}. {h['name']:12} ({h['code']:12}) · 占比 {pct_str}")
        print(f"\n   👉 请选择要分析的成分股（告诉我编号或代码）")
        print(f"      例：/analyze-stock {top_holdings[0]['code']}  或  /analyze-stock {top_holdings[0]['name']}")
    else:
        print(f"   {what_to_do}")
    return err_payload
