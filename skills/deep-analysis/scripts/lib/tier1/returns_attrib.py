"""Tier-1 · 二级市场组合收益归因 (returns attribution).

改编自 anthropics/financial-services · private-equity/returns-analysis。
原文是 PE 基金 IRR/MOIC 归因桥；这里适配成**二级市场组合**的收益归因：
把组合总收益拆解为「各持仓贡献(权重×个股收益)」+「按行业/流派分组贡献」+
「Top 贡献 / Top 拖累」排序，并与基准做超额对比。

纯函数 · 无外部 IO · 吃 UZI `--portfolio` 的 holdings 结构
（参考 portfolio_runner.py：ticker / weight / note，外加可选 return_pct / industry）。

主入口:
    build_returns_attribution(holdings, benchmark_return=None) -> dict
"""
from __future__ import annotations

from typing import Any


def _num(v, default: float | None = 0.0) -> float | None:
    """容错转 float · 支持 '12.3%' / '1,234' / None。

    与 research_workflow._num 行为一致，但额外允许返回 None
    （用于区分"个股区间收益缺失"和"收益为 0"）。
    """
    if v is None:
        return default
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def build_returns_attribution(
    holdings: list[dict],
    benchmark_return: float | None = None,
) -> dict:
    """组合收益归因。

    Args:
        holdings: [{ticker, weight, return_pct, industry, name?, note?, school?}, ...]
            · weight       仓位（0-1 或 0-100，自动归一化；缺失则等权）
            · return_pct   个股区间收益率（百分比，如 12.5 表示 +12.5%）。
                           缺失 → 标注"需补价格区间"，该持仓贡献按 0 计且计入 missing。
            · industry     行业（用于行业归因；缺失归入"未分类"）
            · school       可选 · 流派/风格标签（用于流派归因，缺失则跳过该维度）
        benchmark_return: 基准区间收益率（百分比）。给定则算超额。

    Returns:
        dict · total_return / contribution_table / sector_attribution /
               top_contributors / top_detractors / benchmark / methodology_log
    """
    log: list[str] = []

    if not holdings:
        return {
            "method": "Returns Attribution (二级市场组合)",
            "error": "holdings 为空",
            "total_return": 0.0,
            "contribution_table": [],
            "sector_attribution": [],
            "school_attribution": [],
            "top_contributors": [],
            "top_detractors": [],
            "benchmark": None,
            "methodology_log": ["Step 0 · holdings 为空，无法归因"],
        }

    n = len(holdings)

    # ── Step 1 · 权重归一化（复刻 portfolio_runner._normalize_weights 语义）──
    raw_weights: list[float | None] = []
    for h in holdings:
        w = _num(h.get("weight"), default=None)
        if w is not None and w > 1.0:
            w = w / 100.0  # 50 当 50%
        raw_weights.append(w)

    weighted_idx = [i for i, w in enumerate(raw_weights) if w is not None]
    if not weighted_idx:
        # 全缺 → 等权
        norm_weights = [1.0 / n] * n
        log.append(f"Step 1 · 全部 {n} 只无权重 → 等权 {1.0/n:.3f}")
    else:
        total_w = sum(raw_weights[i] for i in weighted_idx)
        unweighted = [i for i, w in enumerate(raw_weights) if w is None]
        filled = list(raw_weights)
        if unweighted:
            remain = max(0.0, 1.0 - total_w)
            share = remain / len(unweighted) if remain > 0 else 0.0
            for i in unweighted:
                filled[i] = share
            total_w = sum(filled[i] or 0.0 for i in range(n))
        norm_weights = [
            (filled[i] or 0.0) / total_w if total_w > 0 else 0.0 for i in range(n)
        ]
        log.append(
            f"Step 1 · 权重归一化 · {len(weighted_idx)}/{n} 只带权重 · "
            f"{len(unweighted)} 只均分剩余"
        )

    # ── Step 2 · 逐持仓贡献 = 权重 × 个股收益 ──
    contribution_table: list[dict] = []
    missing: list[str] = []
    total_return = 0.0
    for i, h in enumerate(holdings):
        ticker = str(h.get("ticker", f"#{i+1}")).strip()
        name = h.get("name") or h.get("note") or ticker
        w = norm_weights[i]
        ret_raw = h.get("return_pct")
        ret = _num(ret_raw, default=None)
        if ret is None:
            ret_val = 0.0
            need_price = True
            missing.append(ticker)
        else:
            ret_val = ret
            need_price = False
        contrib = w * ret_val  # 单位：百分点
        total_return += contrib
        contribution_table.append({
            "ticker": ticker,
            "name": name,
            "industry": (h.get("industry") or "未分类"),
            "school": h.get("school"),
            "weight": round(w, 4),
            "return_pct": round(ret_val, 2) if not need_price else None,
            "contribution_pct": round(contrib, 3),
            "needs_price": need_price,
            "note": "需补价格区间" if need_price else (h.get("note") or ""),
        })

    total_return = round(total_return, 3)
    log.append(
        f"Step 2 · 逐持仓贡献 Σ(权重×收益) = {total_return:+.2f}pp"
        + (f" · {len(missing)} 只缺区间收益(按0计)" if missing else "")
    )

    # ── Step 3 · 行业归因 ──
    sector_attribution = _group_attribution(contribution_table, key="industry")
    log.append(
        f"Step 3 · 行业归因 · {len(sector_attribution)} 个行业 · "
        f"贡献分组加总 = {sum(s['contribution_pct'] for s in sector_attribution):+.2f}pp"
    )

    # ── Step 3b · 流派归因（仅当至少一只带 school）──
    has_school = any(c.get("school") for c in contribution_table)
    school_attribution = (
        _group_attribution(contribution_table, key="school") if has_school else []
    )
    if has_school:
        log.append(f"Step 3b · 流派归因 · {len(school_attribution)} 个流派")

    # ── Step 4 · Top 贡献 / Top 拖累（只取有收益数据的）──
    scored = [c for c in contribution_table if not c["needs_price"]]
    by_contrib = sorted(scored, key=lambda c: c["contribution_pct"], reverse=True)
    top_contributors = [c for c in by_contrib if c["contribution_pct"] > 0][:3]
    top_detractors = [c for c in reversed(by_contrib) if c["contribution_pct"] < 0][:3]
    log.append(
        f"Step 4 · Top {len(top_contributors)} 贡献 / Top {len(top_detractors)} 拖累"
    )

    # ── Step 5 · 基准超额 ──
    benchmark: dict | None = None
    if benchmark_return is not None:
        bench = _num(benchmark_return, default=0.0) or 0.0
        excess = round(total_return - bench, 3)
        benchmark = {
            "benchmark_return_pct": round(bench, 2),
            "excess_return_pct": excess,
            "outperform": excess > 0,
        }
        log.append(
            f"Step 5 · vs 基准 {bench:+.2f}% → 超额 {excess:+.2f}pp "
            f"({'跑赢' if excess > 0 else '跑输'})"
        )

    # ── 一句话点评 ──
    verdict = _one_liner(total_return, top_contributors, top_detractors, benchmark, missing)

    return {
        "method": "Returns Attribution (二级市场组合)",
        "source": "改编自 anthropics/financial-services · private-equity/returns-analysis",
        "n_holdings": n,
        "n_missing_return": len(missing),
        "missing_return_tickers": missing,
        "total_return": total_return,
        "contribution_table": contribution_table,
        "sector_attribution": sector_attribution,
        "school_attribution": school_attribution,
        "top_contributors": top_contributors,
        "top_detractors": top_detractors,
        "benchmark": benchmark,
        "verdict": verdict,
        "methodology_log": log,
    }


def _group_attribution(rows: list[dict], key: str) -> list[dict]:
    """按 key（industry / school）聚合贡献，按贡献降序。"""
    buckets: dict[str, dict] = {}
    for c in rows:
        gk = c.get(key) or "未分类"
        b = buckets.setdefault(gk, {
            key: gk, "weight": 0.0, "contribution_pct": 0.0,
            "n": 0, "needs_price_n": 0,
        })
        b["weight"] += c["weight"]
        b["contribution_pct"] += c["contribution_pct"]
        b["n"] += 1
        if c["needs_price"]:
            b["needs_price_n"] += 1
    out = []
    for b in buckets.values():
        b["weight"] = round(b["weight"], 4)
        b["contribution_pct"] = round(b["contribution_pct"], 3)
        out.append(b)
    out.sort(key=lambda x: x["contribution_pct"], reverse=True)
    return out


def _one_liner(
    total: float,
    top_c: list[dict],
    top_d: list[dict],
    benchmark: dict | None,
    missing: list[str],
) -> str:
    """生成一句话点评。"""
    if total >= 0:
        head = f"组合区间总收益 {total:+.2f}%"
    else:
        head = f"组合区间总收益 {total:+.2f}%（下跌）"

    parts = [head]
    if top_c:
        parts.append(f"主升由 {top_c[0]['name']} 贡献 {top_c[0]['contribution_pct']:+.2f}pp")
    if top_d:
        parts.append(f"主要拖累 {top_d[0]['name']} {top_d[0]['contribution_pct']:+.2f}pp")
    if benchmark:
        parts.append(
            f"{'跑赢' if benchmark['outperform'] else '跑输'}基准 "
            f"{benchmark['excess_return_pct']:+.2f}pp"
        )
    if missing:
        parts.append(f"⚠️ {len(missing)} 只缺区间收益需补价格")
    return "，".join(parts) + "。"


if __name__ == "__main__":
    import json
    demo = [
        {"ticker": "600519.SH", "weight": 0.30, "return_pct": 12.0, "industry": "白酒", "name": "贵州茅台"},
        {"ticker": "000858.SZ", "weight": 0.15, "return_pct": -8.0, "industry": "白酒", "name": "五粮液"},
        {"ticker": "002594.SZ", "weight": 0.25, "return_pct": 30.0, "industry": "电动车", "name": "比亚迪"},
        {"ticker": "300750.SZ", "weight": 0.20, "return_pct": 5.0, "industry": "电动车", "name": "宁德时代"},
        {"ticker": "AAPL", "weight": 0.10, "industry": "科技", "name": "Apple"},  # 缺 return_pct
    ]
    r = build_returns_attribution(demo, benchmark_return=6.0)
    print(json.dumps(r, ensure_ascii=False, indent=2))
