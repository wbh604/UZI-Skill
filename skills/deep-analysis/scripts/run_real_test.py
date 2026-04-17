"""End-to-end live pipeline on a real ticker.

Runs all 22 fetchers (with graceful failure), computes dimensions + panel
+ synthesis rule-based, then calls assemble_report + inline_assets.

Usage: python run_real_test.py 002273.SZ
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import traceback
from pathlib import Path

# Force UTF-8 output on Windows GBK consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from lib.cache import write_task_output  # noqa: E402
from lib.investor_db import INVESTORS  # noqa: E402
from lib.investor_personas import get_comment as _persona_comment  # noqa: E402
from lib.market_router import parse_ticker  # noqa: E402
from lib.stock_features import extract_features  # noqa: E402
from lib.investor_evaluator import evaluate as _evaluate_investor  # noqa: E402
from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: E402

# Fetcher registry: (module_name, dim_key, fetcher_args_fn)
# fetcher_args_fn(ticker, raw_so_far) → args tuple for main()
FETCHER_MAP = [
    ("fetch_basic",           "0_basic",        lambda t, r: (t,)),
    ("fetch_financials",      "1_financials",   lambda t, r: (t,)),
    ("fetch_kline",           "2_kline",        lambda t, r: (t,)),
    ("fetch_peers",           "4_peers",        lambda t, r: (t,)),
    ("fetch_chain",           "5_chain",        lambda t, r: (t,)),
    ("fetch_research",        "6_research",     lambda t, r: (t,)),
    ("fetch_industry",        "7_industry",     lambda t, r: (r.get("0_basic", {}).get("data", {}).get("industry", "") or "综合",)),
    ("fetch_materials",       "8_materials",    lambda t, r: (t,)),
    ("fetch_futures",         "9_futures",      lambda t, r: (r.get("0_basic", {}).get("data", {}).get("industry", "") or "综合",)),
    ("fetch_valuation",       "10_valuation",   lambda t, r: (t,)),
    ("fetch_governance",      "11_governance",  lambda t, r: (t,)),
    ("fetch_capital_flow",    "12_capital_flow",lambda t, r: (t,)),
    ("fetch_policy",          "13_policy",      lambda t, r: (r.get("0_basic", {}).get("data", {}).get("industry", "") or "综合",)),
    ("fetch_moat",            "14_moat",        lambda t, r: (t,)),
    ("fetch_events",          "15_events",      lambda t, r: (t,)),
    ("fetch_lhb",             "16_lhb",         lambda t, r: (t,)),
    ("fetch_sentiment",       "17_sentiment",   lambda t, r: (t,)),
    ("fetch_trap_signals",    "18_trap",        lambda t, r: (t,)),
    ("fetch_contests",        "19_contests",    lambda t, r: (t,)),
    ("fetch_macro",           "3_macro",        lambda t, r: (r.get("0_basic", {}).get("data", {}).get("industry", "") or "综合",)),
]


# v2.6 · mini_racer (V8 isolate) 不是 thread-safe，多线程同时初始化会触发
# `Check failed: !pool->IsInitialized()` 致命错误。已知用 mini_racer 的 akshare 函数：
#   - fetch_industry → ak.stock_industry_pe_ratio (cninfo)
#   - fetch_capital_flow → ak.stock_individual_fund_flow (em fund flow)
#   - fetch_valuation → ak.stock_a_pe_and_pb (lg)
# 给这些 fetcher 加共享锁，强制串行化，其他 fetcher 仍并行。
import threading as _threading
_MINI_RACER_FETCHERS = {"fetch_industry", "fetch_capital_flow", "fetch_valuation"}
_MINI_RACER_LOCK = _threading.Lock()


def run_fetcher(module_name: str, args: tuple) -> dict:
    try:
        mod = __import__(module_name)
        if module_name in _MINI_RACER_FETCHERS:
            with _MINI_RACER_LOCK:
                result = mod.main(*args)
        else:
            result = mod.main(*args)
        return result if isinstance(result, dict) else {"data": result}
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return {"data": {}, "source": module_name, "fallback": True, "error": f"{type(e).__name__}: {e}"}


def collect_raw_data(ticker: str, max_workers: int = 6, resume: bool = True) -> dict:
    """Parallel fetcher execution via ThreadPoolExecutor.

    Strategy: run fetch_basic first (others depend on industry etc), then
    spawn all remaining fetchers in parallel. Bonus fetchers (fund_holders,
    similar_stocks) run in a second wave since they depend on base cache.

    v2.6 · resume mode: if `.cache/{ticker}/raw_data.json` already exists,
    skip dims that already have valid data. Realtime dims (price snapshots)
    are always re-fetched. Use `resume=False` (or env UZI_NO_RESUME=1) to
    force full re-fetch.
    """
    # v2.6 · 允许通过 env 关闭 resume（run.py --no-resume 设置）
    if os.environ.get("UZI_NO_RESUME") == "1":
        resume = False
    from datetime import datetime as _dt
    raw = {"ticker": ticker, "market": "A", "fetched_at": _dt.now().isoformat(timespec="seconds")}
    dims: dict = {}
    t0 = time.time()

    # v2.6 · resume: 加载已有 raw_data.json 中的 dim 缓存
    cached_dims: dict = {}
    if resume:
        from lib.cache import read_task_output as _read_cache
        # 尝试用原始 ticker 和可能的 resolved ticker 都查
        prev = _read_cache(ticker, "raw_data")
        if prev and isinstance(prev.get("dimensions"), dict):
            cached_dims = prev["dimensions"]
            valid_count = sum(
                1 for d in cached_dims.values()
                if isinstance(d, dict)
                and d.get("data")
                and not d.get("_timeout")
                and not d.get("error")
            )
            if valid_count > 0:
                print(f"  [resume] 检测到已有缓存 · {valid_count}/{len(cached_dims)} 维有效，跳过这些 fetcher")
                print(f"           （用 --no-resume 强制重抓）")

    # 哪些 dim 总是重抓（实时数据）
    REALTIME_DIMS = {"0_basic"}  # basic 含 price/change_pct 必须 fresh
    # （2_kline 是 daily snapshot，可以 resume；其他 dim 全部 daily/quarterly TTL）

    def _is_dim_cached_valid(dim_key: str) -> bool:
        if not resume:
            return False
        if dim_key in REALTIME_DIMS:
            return False
        d = cached_dims.get(dim_key)
        if not isinstance(d, dict):
            return False
        return bool(d.get("data")) and not d.get("_timeout") and not d.get("error")

    # ── Wave 1: fetch_basic (串行, 后续 fetcher 依赖它拿 industry) ──
    print("  [wave 1] fetch_basic ...", end="", flush=True)
    wave1_start = time.time()
    dims["0_basic"] = run_fetcher("fetch_basic", (ticker,))
    print(f" ✓ ({time.time() - wave1_start:.1f}s)")

    # v2.2 · 关键修复: fetch_basic 内部会把中文名解析为代码，读回来给后续 fetcher
    resolved_ticker = (dims.get("0_basic", {}).get("data") or {}).get("ticker")
    if not resolved_ticker:
        # 也可能在 result 顶层
        resolved_ticker = dims.get("0_basic", {}).get("ticker")
    if resolved_ticker and resolved_ticker != ticker:
        print(f"  [resolve] {ticker} → {resolved_ticker}")
        ticker = resolved_ticker
        raw["ticker"] = ticker  # 更新 raw 的 ticker 字段
        raw["market"] = dims["0_basic"].get("data", {}).get("market", "A")

    # ── Wave 2: all other 19 fetchers in parallel ──
    # v2.6 · 加 per-fetcher timeout + overall timeout 防止 hang 卡死整条流水线
    # v2.6 · resume: 已缓存有效的 dim 直接复用，不重新调 fetcher
    wave2_start = time.time()
    all_others = [(m, d, a) for m, d, a in FETCHER_MAP if d != "0_basic"]
    # 分流
    others = []
    skipped_cached = []
    for m, d, a in all_others:
        if _is_dim_cached_valid(d):
            dims[d] = cached_dims[d]
            skipped_cached.append(d)
        else:
            others.append((m, d, a))
    if skipped_cached:
        print(f"  [resume] 跳过 {len(skipped_cached)} 个已缓存维度: {', '.join(skipped_cached[:5])}{'...' if len(skipped_cached) > 5 else ''}")
    print(f"  [wave 2] {len(others)}/{len(all_others)} fetchers parallel (max_workers={max_workers}, per-fetcher 90s)...")

    # 长尾 fetcher 给更长 timeout（拉研报 / 拉公告 通常较慢）
    PER_FETCHER_TIMEOUT_OVERRIDES = {
        "6_research": 180,    # akshare research_report 拉 30+ 篇
        "1_financials": 150,  # 多张财报合并
        "10_valuation": 150,  # 历史估值分位计算
        "15_events": 120,     # 公告 + web search
    }
    DEFAULT_PER_FETCHER_TIMEOUT = 90

    def _run_one(item):
        mod_name, dim_key, args_fn = item
        t = time.time()
        args = args_fn(ticker, dims)
        result = run_fetcher(mod_name, args)
        return dim_key, mod_name, result, time.time() - t

    from concurrent.futures import TimeoutError as _FutureTimeout
    # v2.6 · 增量持久化：每完成 N 个 fetcher 写一次 raw_data.json，crash/Ctrl+C 后 --resume 可续
    from lib.cache import write_task_output as _write_cache
    INCREMENTAL_SAVE_EVERY = 3
    completed_count = 0
    def _persist_progress():
        raw["dimensions"] = dims
        try:
            _write_cache(ticker, "raw_data", raw)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run_one, it): it for it in others}
        # 整体 5 分钟硬上限；as_completed 内部按 future 自己 result(timeout=)
        try:
            for fut in as_completed(futures, timeout=300):
                item = futures[fut]
                _, dim_key_pending, _ = item
                fetcher_timeout = PER_FETCHER_TIMEOUT_OVERRIDES.get(dim_key_pending, DEFAULT_PER_FETCHER_TIMEOUT)
                try:
                    dim_key, mod_name, result, elapsed = fut.result(timeout=fetcher_timeout)
                    dims[dim_key] = result
                    err = result.get("error") if isinstance(result, dict) else None
                    has_data = bool(result.get("data")) if isinstance(result, dict) else False
                    status = "✗" if err else ("✓" if has_data else "·")
                    tail = f" {err[:60]}" if err else ""
                    print(f"    {status} {dim_key:18} ({elapsed:5.1f}s){tail}")
                    completed_count += 1
                    if completed_count % INCREMENTAL_SAVE_EVERY == 0:
                        _persist_progress()
                except _FutureTimeout:
                    # 单 fetcher 超时 — 标记为超时维度，不影响其他 fetcher
                    dims[dim_key_pending] = {
                        "data": {},
                        "_timeout": True,
                        "fallback": True,
                        "error": f"fetcher timeout > {fetcher_timeout}s",
                        "source": "timeout"
                    }
                    print(f"    ⏱  {dim_key_pending:18} (>{fetcher_timeout}s · TIMEOUT · agent 可补抓)")
                except Exception as e:
                    dims[dim_key_pending] = {
                        "data": {},
                        "fallback": True,
                        "error": f"{type(e).__name__}: {str(e)[:120]}",
                        "source": "crash"
                    }
                    print(f"    ✗ {dim_key_pending:18} crash: {type(e).__name__}: {str(e)[:60]}")
        except _FutureTimeout:
            # 整体 5 分钟超时 — 记录还没完成的 fetcher
            unfinished = [futures[f] for f in futures if not f.done()]
            for item in unfinished:
                _, dim_key_pending, _ = item
                if dim_key_pending not in dims:
                    dims[dim_key_pending] = {
                        "data": {},
                        "_timeout": True,
                        "fallback": True,
                        "error": "wave2 overall timeout > 300s",
                        "source": "timeout"
                    }
            print(f"    ⏱  wave2 整体超时 · 未完成 {len(unfinished)} 个 fetcher 已标记")
    wave2_elapsed = time.time() - wave2_start
    print(f"  [wave 2] done in {wave2_elapsed:.1f}s")

    # ── Wave 3: bonus fetchers (parallel) ──
    print("  [wave 3] bonus fetchers parallel ...")
    wave3_start = time.time()

    def _fund_holders():
        try:
            import fetch_fund_holders
            # BUG#R2 fix: v2.4 已把 fetcher limit 改为 None（不截断），但 wave3 调用
            # 还是写死 limit=6 → 报告里只显示 6 个基金。这次同步移除调用层的截断。
            # 茅台 649 家、浙江东方 80 家全收录；render_fund_managers 已支持紧凑行展开。
            fh = fetch_fund_holders.main(ticker, limit=None)
            return ("fund_managers", (fh.get("data") or {}).get("fund_managers", []), None)
        except Exception as e:
            return ("fund_managers", [], str(e))

    def _similar_stocks():
        try:
            import fetch_similar_stocks
            ss = fetch_similar_stocks.main(ticker, top_n=4)
            return ("similar_stocks", (ss.get("data") or {}).get("similar_stocks", []), None)
        except Exception as e:
            return ("similar_stocks", [], str(e))

    # v2.6 · wave3 同样加 60s timeout per fetcher（fund_holders 默认抓全量，可能慢）
    from concurrent.futures import TimeoutError as _FutureTimeout
    with ThreadPoolExecutor(max_workers=2) as pool:
        wave3_futures = {pool.submit(_fund_holders): "fund_managers", pool.submit(_similar_stocks): "similar_stocks"}
        try:
            for fut in as_completed(wave3_futures, timeout=180):
                key_pending = wave3_futures[fut]
                try:
                    key, val, err = fut.result(timeout=120)
                    raw[key] = val
                    status = "✗" if err else "✓"
                    print(f"    {status} {key}: {len(val) if isinstance(val, list) else 'n/a'}")
                except _FutureTimeout:
                    raw[key_pending] = []
                    print(f"    ⏱  {key_pending} (>120s · TIMEOUT)")
                except Exception as e:
                    raw[key_pending] = []
                    print(f"    ✗ {key_pending} crash: {type(e).__name__}: {str(e)[:60]}")
        except _FutureTimeout:
            for f, k in wave3_futures.items():
                if not f.done() and k not in raw:
                    raw[k] = []
            print(f"    ⏱  wave3 overall timeout")
    wave3_elapsed = time.time() - wave3_start
    print(f"  [wave 3] done in {wave3_elapsed:.1f}s")

    raw["dimensions"] = dims
    total_elapsed = time.time() - t0
    print(f"\n  Task 1 total: {total_elapsed:.1f}s (wave1 {time.time() - wave1_start:.1f}s + wave2 {wave2_elapsed:.1f}s + wave3 {wave3_elapsed:.1f}s)")
    return raw


# ─────────── DIMENSIONS SCORING (rule-based) ───────────

def _f(v, default=0.0):
    try:
        return float(str(v).replace("%", "").replace(",", "").replace("+", ""))
    except (ValueError, TypeError):
        return default


def score_dimensions(raw: dict) -> dict:
    dims = raw.get("dimensions", {})
    out = {}

    def _get(key: str) -> dict:
        return (dims.get(key) or {}).get("data") or {}

    # 1 · 财报
    fin = _get("1_financials")
    roe = _f(fin.get("roe"))
    last_roe = (fin.get("roe_history") or [0])[-1] if fin.get("roe_history") else roe
    net_margin = _f(fin.get("net_margin"))
    health = fin.get("financial_health") or {}
    debt = _f(health.get("debt_ratio"))
    rev_hist = fin.get("revenue_history") or []
    growth = ((rev_hist[-1] - rev_hist[-2]) / rev_hist[-2] * 100) if len(rev_hist) >= 2 and rev_hist[-2] else 0
    score_1 = 5
    if last_roe >= 15: score_1 += 2
    elif last_roe >= 10: score_1 += 1
    elif last_roe < 5: score_1 -= 2
    if net_margin >= 15: score_1 += 1
    if growth >= 20: score_1 += 1
    if debt >= 60: score_1 -= 1
    score_1 = max(1, min(10, score_1))
    reasons_pass_1 = []
    reasons_fail_1 = []
    if last_roe >= 15: reasons_pass_1.append(f"ROE 最新 {last_roe:.1f}%")
    elif last_roe < 8: reasons_fail_1.append(f"ROE 最新 {last_roe:.1f}% 偏低")
    if growth >= 20: reasons_pass_1.append(f"营收增速 {growth:.1f}%")
    elif growth < 5: reasons_fail_1.append(f"营收增速 {growth:.1f}% 停滞")
    if debt < 40: reasons_pass_1.append(f"资产负债率 {debt:.0f}% 健康")
    elif debt > 60: reasons_fail_1.append(f"资产负债率 {debt:.0f}% 偏高")
    out["1_financials"] = {"score": score_1, "weight": 5,
                            "label": f"ROE {last_roe:.1f}% · 营收增速 {growth:+.1f}% · 负债率 {debt:.0f}%",
                            "reasons_pass": reasons_pass_1, "reasons_fail": reasons_fail_1}

    # 2 · K 线
    kline = _get("2_kline")
    stage = str(kline.get("stage", ""))
    ma_align = str(kline.get("ma_align", ""))
    stats = kline.get("kline_stats") or {}
    score_2 = 5
    if "Stage 2" in stage: score_2 += 2
    elif "Stage 1" in stage: score_2 += 1
    elif "Stage 3" in stage or "Stage 4" in stage: score_2 -= 2
    if "多头" in ma_align: score_2 += 1
    dd_str = stats.get("max_drawdown", "0%")
    dd = _f(dd_str)
    if dd <= -30: score_2 -= 1
    score_2 = max(1, min(10, score_2))
    label_2 = f"{stage} · 均线{ma_align}"
    if stats.get("ytd_return"): label_2 += f" · YTD {stats['ytd_return']}"
    out["2_kline"] = {"score": score_2, "weight": 4, "label": label_2,
                      "reasons_pass": [f"{stage}"] if "Stage 2" in stage else [],
                      "reasons_fail": [f"最大回撤 {dd:.1f}%"] if dd <= -25 else []}

    # 3 · 宏观 (qualitative — give middle)
    out["3_macro"] = {"score": 6, "weight": 3, "label": "宏观环境中性（需 web search 补充）"}

    # 4 · 同行
    peers = _get("4_peers")
    peer_table = peers.get("peer_table") or []
    score_4 = 5
    if peer_table and len(peer_table) > 1:
        score_4 = 7  # we have data
        try:
            self_row = next((p for p in peer_table if p.get("is_self")), None)
            if self_row:
                self_pe = _f(self_row.get("pe"))
                avg_pe = sum(_f(p.get("pe")) for p in peer_table if not p.get("is_self")) / max(1, len([p for p in peer_table if not p.get("is_self")]))
                if self_pe > 0 and avg_pe > 0:
                    if self_pe < avg_pe * 0.9: score_4 += 1
                    elif self_pe > avg_pe * 1.2: score_4 -= 1
        except Exception:
            pass
    out["4_peers"] = {"score": score_4, "weight": 4,
                      "label": f"同业 {len(peer_table) - 1} 家对比" if peer_table else "无同行数据",
                      "reasons_pass": [], "reasons_fail": []}

    # 5 · 上下游
    chain = _get("5_chain")
    breakdown = chain.get("main_business_breakdown") or []
    score_5 = 6 if breakdown else 5
    out["5_chain"] = {"score": score_5, "weight": 4,
                      "label": f"主营 {len(breakdown)} 类业务已识别" if breakdown else "产业链数据不完整",
                      "reasons_pass": [], "reasons_fail": []}

    # 6 · 研报
    research = _get("6_research")
    coverage = research.get("report_count", 0)
    ratings = research.get("rating_distribution") or {}
    buy_count = sum(v for k, v in ratings.items() if "买入" in str(k) or "增持" in str(k))
    score_6 = 5 + min(3, coverage // 5)
    if buy_count >= 10: score_6 += 1
    score_6 = min(10, score_6)
    out["6_research"] = {"score": score_6, "weight": 3,
                         "label": f"{coverage} 份研报 · 买入/增持 {buy_count} 份" if coverage else "研报数据稀少",
                         "reasons_pass": [f"覆盖券商 {coverage} 家"] if coverage >= 10 else [],
                         "reasons_fail": [] if coverage else ["缺乏覆盖"]}

    # 7 · 行业景气 (stub heavy qualitative)
    out["7_industry"] = {"score": 7, "weight": 4, "label": "行业处于成长期（需 web search 确认）"}

    # 8 · 原材料
    out["8_materials"] = {"score": 6, "weight": 3, "label": "原材料成本数据需 web search"}

    # 9 · 期货关联
    out["9_futures"] = {"score": 5, "weight": 2, "label": "无强关联期货品种"}

    # 10 · 估值
    val = _get("10_valuation")
    pe_q_str = str(val.get("pe_quantile", ""))
    import re
    m = re.search(r'(\d+)', pe_q_str)
    pe_q = int(m.group(1)) if m else 50
    score_10 = 5
    if pe_q < 30: score_10 = 9
    elif pe_q < 50: score_10 = 7
    elif pe_q < 70: score_10 = 5
    elif pe_q < 85: score_10 = 3
    else: score_10 = 2
    out["10_valuation"] = {"score": score_10, "weight": 5,
                            "label": f"PE {val.get('pe', '—')} · 5 年 {pe_q} 分位 · 行业均值 {val.get('industry_pe', '—')}",
                            "reasons_pass": ["PE 在 5 年中位数以下"] if pe_q < 50 else [],
                            "reasons_fail": ["PE 已在 5 年高位区"] if pe_q >= 75 else []}

    # 11 · 治理
    gov = _get("11_governance")
    pledge = gov.get("pledge") or []
    has_insider = bool(gov.get("insider_trades_1y"))
    score_11 = 6
    if not pledge or (isinstance(pledge, list) and len(pledge) == 0): score_11 += 1
    if has_insider: score_11 += 1
    out["11_governance"] = {"score": min(10, score_11), "weight": 4,
                             "label": f"质押记录 {len(pledge) if isinstance(pledge, list) else '—'} · 内部交易 {'有' if has_insider else '无'}"}

    # 12 · 资金面 (v2.2: 主力资金替代北向，北向已关停)
    cap = _get("12_capital_flow")
    main_flow = cap.get("main_fund_flow_20d") or []
    main_5d_net = 0
    if main_flow:
        for rec in main_flow[:5]:
            v = rec.get("主力净流入-净额", 0) if isinstance(rec, dict) else 0
            try:
                main_5d_net += float(v)
            except (ValueError, TypeError):
                pass
    main_5d_label = f"{main_5d_net / 1e8:+.1f}亿" if main_5d_net else "—"
    unlock = cap.get("unlock_schedule") or []
    score_12 = 5
    if main_5d_net > 0: score_12 += 2
    elif main_5d_net < 0: score_12 -= 1
    if len(unlock) == 0: score_12 += 1
    score_12 = max(1, min(10, score_12))
    out["12_capital_flow"] = {"score": score_12, "weight": 4,
                               "label": f"主力 5日 {main_5d_label} · 12 个月解禁 {len(unlock)} 次",
                               "reasons_pass": [f"主力资金 5 日净流入 {main_5d_label}"] if main_5d_net > 0 else [],
                               "reasons_fail": [f"主力资金 5 日净流出 {main_5d_label}"] if main_5d_net < 0 else []}

    # 13 · 政策
    out["13_policy"] = {"score": 6, "weight": 3, "label": "政策环境中性"}

    # 14 · 护城河
    out["14_moat"] = {"score": 6, "weight": 3, "label": "护城河需定性评估"}

    # 15 · 事件
    events = _get("15_events")
    news = events.get("news") or []
    notices = events.get("recent_notices") or []
    score_15 = 5 + min(3, len(news) // 10)
    out["15_events"] = {"score": score_15, "weight": 4,
                        "label": f"近期新闻 {len(news)} 条 · 公告 {len(notices)} 份"}

    # 16 · 龙虎榜
    lhb = _get("16_lhb")
    lhb_count = lhb.get("lhb_count_30d", 0)
    matched = lhb.get("matched_youzi") or []
    score_16 = 5 + min(3, lhb_count // 2)
    if matched: score_16 += 1
    score_16 = min(10, score_16)
    out["16_lhb"] = {"score": score_16, "weight": 4,
                     "label": f"近 30 天上榜 {lhb_count} 次 · 识别游资 {len(matched)} 位",
                     "reasons_pass": [f"{'/'.join(matched[:3])} 席位出现"] if matched else []}

    # 17 · 舆情
    hot = _get("17_sentiment")
    hot_rank = (hot.get("hot_rank") or {}).get("rank_history") or []
    score_17 = 6 + min(2, len(hot_rank) // 10)
    out["17_sentiment"] = {"score": score_17, "weight": 3,
                            "label": f"雪球热度上榜 {len(hot_rank)} 次"}

    # 18 · 杀猪盘 (stub → safe by default, 9 分)
    out["18_trap"] = {"score": 9, "weight": 5, "label": "🟢 未发现推广痕迹（需 web search 8 信号确认）"}

    # 19 · 实盘赛
    contests = _get("19_contests")
    summary = contests.get("summary") or {}
    xq_total = summary.get("xueqiu_cubes_total", 0)
    hi = summary.get("high_return_cubes", 0)
    score_19 = 5 + min(3, xq_total // 5) + min(2, hi)
    score_19 = min(10, score_19)
    out["19_contests"] = {"score": score_19, "weight": 4,
                           "label": f"雪球 {xq_total} 个组合持有 · {hi} 个收益 >50%",
                           "reasons_pass": [f"{xq_total} 个雪球组合持有"] if xq_total else []}

    # Overall fundamental score
    total_weighted = sum(v["score"] * v["weight"] for v in out.values())
    total_weight = sum(v["weight"] for v in out.values())
    fundamental = (total_weighted / total_weight * 10) if total_weight else 0

    return {"ticker": raw["ticker"], "fundamental_score": round(fundamental, 1), "dimensions": out}


# ─────────── PANEL GENERATION (rule-based) ───────────

GROUP_VERDICTS = {
    "bullish":  ["强烈买入", "买入", "关注"],
    "bearish":  ["观望", "回避", "等待"],
    "neutral":  ["观望", "不适合", "不达标"],
}

COMMENT_TEMPLATES = {
    "A": {
        "bullish": [
            "ROE 和现金流都看得过去，长期持有没问题。",
            "商业模式清晰，10 年后还能赚钱的那种。",
            "安全边际尚可，不急着全仓。",
        ],
        "bearish": [
            "估值已透支未来几年的增长，等回调。",
            "护城河在侵蚀，这种价格不该买。",
            "现金流质量存疑，再观察两个季度。",
        ],
        "neutral": ["看不太懂，先放观察池。", "不在能力圈内。"],
    },
    "B": {
        "bullish": ["PEG 合理且成长性可见，可以进攻。", "CANSLIM 多数条件达标。"],
        "bearish": ["估值已脱离 PEG 合理区间。", "机构持股过高，不符合 CANSLIM S 项。"],
        "neutral": ["增长故事需要更多验证。"],
    },
    "C": {
        "bullish": ["宏观环境对这只票的反身性有利。", "流动性拐点已到，可以下注。"],
        "bearish": ["反身性正反馈进入晚期，小心。"],
        "neutral": ["宏观判断暂时不明。"],
    },
    "D": {
        "bullish": ["Stage 2 + 量能配合，技术面允许进场。", "VCP 形态已成，止损位清晰。"],
        "bearish": ["距 52 周高点太近，不是入场点。"],
        "neutral": ["等待明确突破。"],
    },
    "E": {
        "bullish": ["生意对、人对、价格还凑合。", "ROE 持续性强，可以重仓。"],
        "bearish": ["价格对不起生意质量。"],
        "neutral": ["看不懂就不要碰。"],
    },
    "F": {
        "bullish": ["板块有格局，趋势向上可以跟。", "二板定龙头，题材在线。", "情绪合力在，短线机会。"],
        "bearish": ["市值不在我的射程里。", "题材已过热，这不是我的菜。"],
        "neutral": ["不在风格里，不适合。"],
    },
    "G": {
        "bullish": ["多因子评分 top 20%，值得下注。", "凯利公式给出正仓位。"],
        "bearish": ["统计上已进入均值回归区。"],
        "neutral": ["因子中性，模型无信号。"],
    },
}


def generate_panel(dims_scored: dict, raw: dict) -> dict:
    """Rule-engine-based panel — each investor's verdict cites specific
    criteria from investor_criteria.py that were hit or missed.
    """
    # Build the flat feature dict once for all 51 investors
    features = extract_features(raw, raw.get("dimensions", {}))

    basic_ctx = (raw.get("dimensions", {}).get("0_basic") or {}).get("data") or {}
    kline_ctx = (raw.get("dimensions", {}).get("2_kline") or {}).get("data") or {}
    fin_ctx = (raw.get("dimensions", {}).get("1_financials") or {}).get("data") or {}

    investors_out = []
    vote_dist = {"strongly_buy": 0, "buy": 0, "watch": 0, "wait": 0, "avoid": 0, "n_a": 0, "skip": 0}
    sig_dist = {"bullish": 0, "neutral": 0, "bearish": 0, "skip": 0}

    def _score_to_verdict(score: float, signal: str) -> str:
        if signal == "bullish" and score >= 80:
            return "强烈买入"
        if signal == "bullish":
            return "买入"
        if signal == "bearish" and score <= 20:
            return "回避"
        if signal == "bearish":
            return "观望"
        # neutral
        return "关注" if score >= 50 else "观望"

    for inv in INVESTORS:
        inv_id = inv["id"]
        verdict_obj = _evaluate_investor(inv_id, features)

        sig = verdict_obj["signal"]
        score = int(max(0, verdict_obj["score"]))
        confidence = int(verdict_obj["confidence"])

        # Handle "skip" — investor won't look at this market
        if sig == "skip":
            verdict = "不适合"
            score = 0
            confidence = 0
            skip_reason = verdict_obj.get("skip_reason", "不在能力圈")
            headline = f"不适合 — {skip_reason}"
            comment = f"不在能力圈范围内，不做评价。\n{headline}"
            reasoning = verdict_obj.get("rationale", "")
        else:
            verdict = _score_to_verdict(score, sig)

            # Persona voice layer
            ctx = {
                "name": basic_ctx.get("name", "这只票"),
                "industry": basic_ctx.get("industry", "该行业"),
                "price": basic_ctx.get("price", "—"),
                "pe": basic_ctx.get("pe_ttm", "—"),
                "roe": str((fin_ctx.get("roe_history") or ["—"])[-1]),
                "stage": kline_ctx.get("stage", "—"),
                "growth": fin_ctx.get("revenue_growth", "—"),
            }
            persona_line = _persona_comment(inv_id, sig, ctx)

            headline = verdict_obj["headline"]
            comment = f"{persona_line}\n{headline}"
            reasoning = verdict_obj["rationale"]

        v_key = {"强烈买入": "strongly_buy", "买入": "buy", "关注": "watch",
                 "观望": "wait", "回避": "avoid", "不适合": "skip"}.get(verdict, "n_a")
        vote_dist[v_key] = vote_dist.get(v_key, 0) + 1
        sig_dist[sig] = sig_dist.get(sig, 0) + 1

        investors_out.append({
            "investor_id": inv_id,
            "name": inv["name"],
            "group": inv["group"],
            "avatar": f"avatars/{inv_id}.svg",
            "signal": sig,
            "confidence": confidence,
            "score": score,
            "verdict": verdict,
            "reasoning": reasoning,
            "comment": comment,
            "headline": headline,
            "pass": [{"name": r["name"], "msg": r["msg"], "weight": r["weight"]}
                     for r in verdict_obj["pass_rules"][:4]],
            "fail": [{"name": r["name"], "msg": r["msg"], "weight": r["weight"]}
                     for r in verdict_obj["fail_rules"][:4]],
            "weight_pass": verdict_obj["weight_pass"],
            "weight_total": verdict_obj["weight_total"],
            "ideal_price": None,
            "period": "中长线" if inv["group"] in ("A", "B", "E") else "短线",
        })

    active_count = len(investors_out) - sig_dist.get("skip", 0)
    consensus = sig_dist["bullish"] / max(active_count, 1) * 100
    return {
        "ticker": raw["ticker"],
        "panel_consensus": round(consensus, 1),
        "vote_distribution": vote_dist,
        "signal_distribution": sig_dist,
        "investors": investors_out,
    }


# ─────────────────────────────────────────────────────────────
# v2.6.1 · 自动综合各维度 raw_data 字段为可读 commentary
# 替代旧版 "[脚本占位]" 废话；让直跑模式（无 agent）也能产出有信息量的报告
# Agent 介入时仍可覆盖（agent_analysis.dim_commentary 优先级最高）
# ─────────────────────────────────────────────────────────────
def _auto_summarize_dim(dim_key: str, label: str, dim: dict, score: float) -> str:
    """Build a one-paragraph commentary from raw_data fields. NEVER returns
    "[占位]" type strings — either real content or empty."""
    if not isinstance(dim, dict):
        return ""
    data = dim.get("data") or {}
    if not data:
        return f"{label}：未拉取到数据（fetcher 失败或返回空）。"

    def _v(*keys, default="—"):
        for k in keys:
            v = data.get(k)
            if v not in (None, "", "—", "-", [], {}):
                return v
        return default

    def _join_list(lst, max_n=3, sep="；"):
        if not isinstance(lst, list) or not lst:
            return None
        out = []
        for x in lst[:max_n]:
            if isinstance(x, dict):
                t = x.get("title") or x.get("name") or x.get("date") or str(x)
                out.append(str(t)[:50])
            else:
                out.append(str(x)[:50])
        return sep.join(out)

    # ─── Per-dim auto summarizer ───
    if dim_key == "0_basic":
        return f"{label}：{_v('name')}（{_v('code')}），{_v('industry')} 行业。市值 {_v('market_cap')}，PE {_v('pe_ttm')}，PB {_v('pb')}。"

    if dim_key == "1_financials":
        roe = _v("roe_latest", "roe")
        rev_g = _v("revenue_growth_yoy", "revenue_yoy")
        np_g = _v("net_profit_yoy")
        margin = _v("net_margin", "gross_margin")
        return f"{label}：ROE {roe}，营收同比 {rev_g}，净利同比 {np_g}，净利率 {margin}。综合得分 {score}/10。"

    if dim_key == "2_kline":
        stage = _v("stage", "wyckoff_stage")
        ma = _v("ma_align", "trend")
        macd = _v("macd")
        return f"{label}：{stage} · 均线 {ma} · MACD {macd}。"

    if dim_key == "3_macro":
        return (f"{label}：利率周期 {_v('rate_cycle')}；汇率 {_v('fx_trend')}；"
                f"地缘 {_v('geo_risk')}；大宗商品 {_v('commodity', 'commodity_trend')}。"
                f"得分 {score}/10。")

    if dim_key == "4_peers":
        rank = _v("rank")
        peer_table = data.get("peer_table") or []
        ind = _v("industry")
        peers_str = _join_list([p.get("name") for p in peer_table if isinstance(p, dict) and not p.get("is_self")][:5], max_n=5, sep="、")
        return f"{label}：{ind} 行业，{rank}{('，主要同行：' + peers_str) if peers_str else ''}。得分 {score}/10。"

    if dim_key == "5_chain":
        return f"{label}：上游 {_v('upstream')}；下游 {_v('downstream')}；客户集中度 {_v('client_concentration')}。"

    if dim_key == "6_research":
        rep_count = _v("report_count", "n_reports")
        target = _v("avg_target_price", "target_price")
        rating = _v("consensus_rating", "rating")
        return f"{label}：近期券商研报 {rep_count} 篇，一致评级 {rating}，目标价均值 {target}。"

    if dim_key == "7_industry":
        ind_pe = _v("industry_pe_weighted") or (data.get("cninfo_metrics") or {}).get("industry_pe_weighted")
        ind_count = _v("total_companies") or (data.get("cninfo_metrics") or {}).get("company_count")
        growth = _v("growth")
        return f"{label}：所属 {_v('industry')} · 行业 PE 加权 {ind_pe} · 上市公司数 {ind_count} · 增速 {growth}。"

    if dim_key == "8_materials":
        core = _v("core_material")
        trend = _v("price_trend")
        cost = _v("cost_share")
        return f"{label}：核心原料 {core}；近期价格走势 {trend}；占成本比例 {cost}。"

    if dim_key == "9_futures":
        contract = _v("linked_contract")
        ftrend = _v("contract_trend")
        return f"{label}：关联合约 {contract}；近期走势 {ftrend}；{_v('note', default='')}。"

    if dim_key == "10_valuation":
        pe_q = _v("pe_quantile_5y", "pe_quantile")
        pb_q = _v("pb_quantile_5y", "pb_quantile")
        return f"{label}：PE 5 年分位 {pe_q}，PB 5 年分位 {pb_q}。得分 {score}/10。"

    if dim_key == "11_governance":
        ctrl = _v("actual_controller")
        recent = _v("recent_changes", "recent_holdings_change")
        return f"{label}：实控人 {ctrl}；近期变动 {recent}。"

    if dim_key == "12_capital_flow":
        north = _v("north_holding_pct", "north_change_5d", default=None)
        margin = _v("margin_balance", default=None)
        if north or margin:
            return f"{label}：北向持股 {north or '—'}；融资余额 {margin or '—'}。"
        return f"{label}：{_v('_note', default='资金面数据有限')}。"

    if dim_key == "13_policy":
        snippets = data.get("snippets") or {}
        non_empty = {k: v for k, v in snippets.items() if v}
        if non_empty:
            preview = "；".join(f"{k}: {len(v) if isinstance(v, list) else 1} 条" for k, v in non_empty.items())
            return f"{label}：{_v('industry', default='本行业')} {_v('year', default='')} 年政策检索：{preview}。"
        return f"{label}：{_v('industry', default='本行业')} 政策搜索未命中具体内容（建议 web_search 补抓）。"

    if dim_key == "14_moat":
        scores = data.get("scores") or {}
        total = sum(scores.values()) if scores else None
        if total is not None:
            return f"{label}：四力评分 无形资产 {scores.get('intangible')}/10、转换成本 {scores.get('switching')}/10、网络效应 {scores.get('network')}/10、规模 {scores.get('scale')}/10 · 综合 {total}/40。"
        return f"{label}：评估数据有限，得分 {score}/10。"

    if dim_key == "15_events":
        timeline = data.get("event_timeline") or []
        recent_news = data.get("recent_news") or []
        if timeline:
            head = "；".join([str(t)[:60] for t in timeline[:3]])
            return f"{label}：近期事件 {len(timeline)} 条，含：{head}。"
        if recent_news:
            head = "；".join([(n.get("title") or "")[:60] for n in recent_news[:3]])
            return f"{label}：近期新闻 {len(recent_news)} 条，含：{head}。"
        return f"{label}：暂无显著事件（fetcher 返回空）。"

    if dim_key == "16_lhb":
        n = _v("recent_lhb_count", "n_lhb_30d", default=None)
        seats = data.get("recent_seats") or data.get("top_seats") or []
        if n or seats:
            seat_str = "、".join([s.get("name", "") for s in seats[:3] if isinstance(s, dict)]) if seats else ""
            return f"{label}：近 30 天上榜 {n or '—'} 次{('，主要席位：' + seat_str) if seat_str else ''}。"
        return f"{label}：近期未上龙虎榜或非 A 股。"

    if dim_key == "17_sentiment":
        hot = _v("hot_rank", "hot_score")
        senti = _v("sentiment_label", "sentiment")
        return f"{label}：热度 {hot}；情绪 {senti}。"

    if dim_key == "18_trap":
        # v2.7.1: 字段名其实是 signals_hit_count（不是 hit_signals_count），修；显示 8 信号扫描结果
        level = _v("trap_level", "level")
        n_signals = data.get("signals_hit_count", data.get("hit_signals_count", 0))
        scanned = data.get("signals_hit", "?/8")
        rec = _v("recommendation")
        detail = data.get("signals_hit_detail") or []
        if detail:
            kws = [s.get("name", "") for s in detail[:3]]
            return f"{label}：{level} · 8 信号扫描命中 {scanned}（{('、'.join(kws))}）· 建议：{rec}"
        return f"{label}：{level} · 8 信号扫描命中 {scanned}（已扫 ddgs 24 条搜索结果）· 建议：{rec}"

    if dim_key == "19_contests":
        # v2.7.1: 字段名是 summary.xueqiu_cubes_total，不是 contests_count；要看 login_required
        summary = data.get("summary") or {}
        n_cubes = summary.get("xueqiu_cubes_total", 0)
        n_high = summary.get("high_return_cubes", 0)
        login_req = summary.get("xueqiu_login_required", False)
        src = summary.get("xueqiu_source", "http")
        if login_req and n_cubes == 0:
            return (f"{label}：⚠️ XueQiu cubes 接口需登录（2026 起新政），未启用 → 0 cube。"
                    f"启用方式：export UZI_XQ_LOGIN=1 + python -m lib.xueqiu_browser login")
        if n_cubes:
            return f"{label}：雪球 {n_cubes} 个组合持有本股（高收益 >50% 的有 {n_high} 个）· 来源 {src}"
        return f"{label}：雪球 0 个组合持有本股（可能小盘 / 冷门 / 接口未返）"

    # Default: just enumerate top fields
    items = []
    for k, v in list(data.items())[:5]:
        if v not in (None, "", "—", "-", [], {}) and not str(k).startswith("_"):
            items.append(f"{k}={str(v)[:30]}")
    return f"{label}：{'、'.join(items) if items else '无数据'}。" if items else ""


def _autofill_qualitative_via_mx(raw: dict, ticker: str) -> None:
    """v2.6.1 · 自动补齐 6 个定性维度的空字段（in-place 修改 raw['dimensions']）.

    优先级：MX 妙想 API → ddgs WebSearch → 显式标记 autofill_failed。
    适用场景：直跑模式（无 agent 介入），fetcher 拿到空数据时不能让报告也空。
    """
    try:
        from lib.mx_api import MXClient
    except ImportError:
        MXClient = None
    try:
        from lib.web_search import search as _ws_search
    except ImportError:
        _ws_search = None

    client = MXClient() if MXClient else None
    mx_ok = client is not None and client.available
    if not mx_ok and not _ws_search:
        print("   ⚠️ MX_APIKEY 未设置且 ddgs 不可用，跳过自动兜底")
        return

    dims = raw.get("dimensions", {})
    basic = (dims.get("0_basic") or {}).get("data") or {}
    name = basic.get("name") or ticker
    industry = basic.get("industry") or "综合"
    code_raw = ticker.split(".")[0] if "." in ticker else ticker

    def _is_default_or_empty(v) -> bool:
        """True if value is missing OR a generic-default placeholder."""
        if v in (None, "", "—", "-", [], {}, "n/a", "N/A"):
            return True
        s = str(v)
        # 这些都是 fetcher 的默认 fallback 字符串，没真实信息量
        if any(kw in s for kw in ["中性（", "中性(", "未拉取", "未命中", "无直接关联"]):
            return True
        return False

    # 6 个定性维度的"空判定" + MX query 模板（v2.6.1 加严：默认值也算空）
    targets = [
        ("3_macro",     lambda d: all(_is_default_or_empty(d.get(k)) for k in ("rate_cycle","fx_trend","geo_risk","commodity")),
                        lambda: f"{industry} 2026 宏观环境 利率周期 汇率 大宗商品 行业影响"),
        ("7_industry",  lambda d: _is_default_or_empty(d.get("growth")) and not (d.get("cninfo_metrics") or {}).get("industry_pe_weighted"),
                        lambda: f"{industry} 2026 行业增速 TAM 市场规模 渗透率"),
        ("8_materials", lambda d: _is_default_or_empty(d.get("core_material")),
                        lambda: f"{name} {code_raw} 主营业务 主要原材料 成本构成"),
        ("9_futures",   lambda d: _is_default_or_empty(d.get("linked_contract")) or "无直接" in str(d.get("linked_contract","")),
                        lambda: f"{industry} 行业 上下游 期货品种 套保 大宗"),
        ("13_policy",   lambda d: not any((d.get("snippets") or {}).get(k) for k in ("policy_dir","subsidy","monitoring","anti_trust")),
                        lambda: f"{industry} 2026 国家政策 监管动态 补贴 税收 影响"),
        ("15_events",   lambda d: not d.get("event_timeline") and not d.get("recent_news") and not d.get("recent_notices"),
                        lambda: f"{name} {code_raw} 最新公告 重大事件 业绩 合同"),
    ]
    fixed_count = 0
    skipped_full = 0
    failed_count = 0
    for dim_key, is_empty_fn, query_fn in targets:
        dim = dims.get(dim_key) or {}
        data = dim.get("data") or {}
        try:
            if not is_empty_fn(data):
                skipped_full += 1
                continue  # 该维度已有真实数据
        except Exception:
            skipped_full += 1
            continue

        query = query_fn()
        text = ""
        source_used = None

        # 优先 MX
        if mx_ok:
            try:
                r = client.query(query)
                text = _extract_mx_text(r)
                if text:
                    source_used = "mx_api"
            except Exception:
                pass

        # 回退 ddgs WebSearch
        if not text and _ws_search:
            try:
                results = _ws_search(query, max_results=3) or []
                snippets = []
                for r in results[:3]:
                    if isinstance(r, dict):
                        title = (r.get("title") or "").strip()
                        body = (r.get("body") or "").strip()
                        if title or body:
                            snippets.append(f"{title} — {body[:80]}".strip(" —"))
                text = "；".join(snippets)[:300]
                if text:
                    source_used = "ddgs"
            except Exception:
                pass

        if text:
            data.setdefault("_autofill", {})
            data["_autofill"]["query"] = query
            data["_autofill"]["snippet"] = text
            data["_autofill"]["source"] = source_used
            # 把内容塞到对应字段，方便 _auto_summarize_dim 摘要
            if dim_key == "3_macro":
                data["rate_cycle"] = (text[:80] + "…") if len(text) > 80 else text
            elif dim_key == "7_industry":
                data["growth"] = (text[:80] + "…") if len(text) > 80 else text
            elif dim_key == "8_materials":
                data["core_material"] = (text[:60] + "…") if len(text) > 60 else text
            elif dim_key == "9_futures":
                data["contract_trend"] = (text[:60] + "…") if len(text) > 60 else text
            elif dim_key == "13_policy":
                snippets = data.setdefault("snippets", {})
                snippets.setdefault("policy_dir", []).append({"title": text[:120], "url": "", "source": source_used})
            elif dim_key == "15_events":
                data["event_timeline"] = [text[:120]]
            dims[dim_key] = {"ticker": ticker, "data": data,
                             "source": (dim.get("source", "") + f"+autofill:{source_used}").lstrip("+"),
                             "fallback": True}
            fixed_count += 1
            print(f"   ✓ {dim_key:14s} via {source_used}: {text[:60]}{'…' if len(text)>60 else ''}")
        else:
            data["_autofill_failed"] = {"query": query, "reason": "MX/ddgs 都没有返回内容"}
            dims[dim_key] = {"ticker": ticker, "data": data,
                             "source": (dim.get("source", "") + "+autofill_failed").lstrip("+"),
                             "fallback": True}
            failed_count += 1
            print(f"   ⚠️ {dim_key:14s} 兜底失败 · agent 应主动 web search 补抓")

    print(f"   合计 · 充足 {skipped_full} · 兜底成功 {fixed_count} · 失败 {failed_count}（共 6 维）")


def _extract_mx_text(result: dict) -> str:
    """Pull most readable text from MX query response.
    First tries dataTableDTOList[].title + entityName; else returns empty."""
    if not isinstance(result, dict) or result.get("error"):
        return ""
    data = result.get("data") or {}
    inner = data.get("data") or {}
    sr = inner.get("searchDataResultDTO") or {}
    dto_list = sr.get("dataTableDTOList") or []
    if not dto_list:
        # Try inner.entityName as last resort
        return str(inner.get("entityName") or "")[:200]
    parts = []
    for dto in dto_list[:2]:
        if not isinstance(dto, dict):
            continue
        title = dto.get("title") or dto.get("entityName") or ""
        if title:
            parts.append(str(title)[:120])
    return "；".join(parts)[:300] if parts else ""


def generate_synthesis(raw: dict, dims_scored: dict, panel: dict, agent_analysis: dict | None = None) -> dict:
    """Generate synthesis — merges agent_analysis.json if provided.

    agent_analysis keys (all optional, agent writes what it has):
      - dim_commentary: {dim_key: "agent's qualitative note"}
      - panel_insights: "agent's panel-level narrative"
      - great_divide_override: {punchline, bull_say_rounds, bear_say_rounds}
      - narrative_override: {core_conclusion, risks, buy_zones}
      - agent_reviewed: True  (marks that agent has intervened)
    """
    from compute_friendly import compute_scenarios, compute_exit_triggers
    ag = agent_analysis or {}

    basic = (raw.get("dimensions", {}).get("0_basic") or {}).get("data") or {}
    name = basic.get("name") or raw.get("ticker")
    price = basic.get("price") or 0

    # v2.7 · 按股票风格动态加权（解决 "几乎一片回避" 的系统性偏差）
    # detect_style 识别：白马/高成长/周期/小盘投机/分红防御/困境反转/量化因子/中性
    # apply_style_weights：评委组级×个体 override 加权 + 22 维 fundamental dim mult
    # neutral 半权计入 consensus（修正旧公式 0% 权重的问题）
    style_label = "balanced"
    style_diag = {}
    fund_score = dims_scored.get("fundamental_score", 60)
    consensus = panel.get("panel_consensus", 50)
    fund_score_old = fund_score
    consensus_old = consensus
    try:
        from lib.stock_style import detect_style, apply_style_weights, STYLE_LABELS, STYLE_EXPLANATIONS
        # Build feature dict for style detection
        bd = basic
        try:
            mcap_yi = float(bd.get("market_cap_raw") or 0) / 1e8 if bd.get("market_cap_raw") else 0
        except (ValueError, TypeError):
            mcap_yi = 0
        # 简化的局部数字转换（避开 generate_synthesis 内 _f 作用域冲突）
        def _ff(v, dflt=0.0):
            try:
                if v is None or v == "":
                    return dflt
                return float(str(v).replace(",", "").replace("%", "").replace("亿", "").replace("+", "").strip())
            except (ValueError, TypeError):
                return dflt
        d_fin = (dims_scored.get("dimensions", {}).get("1_financials") or {})
        feat_for_style = {
            "code": raw.get("ticker", ""),
            "market": raw.get("market", "A"),
            "industry": bd.get("industry", "") or "",
            "market_cap_yi": mcap_yi,
            "pe": _ff(bd.get("pe_ttm")),
            "pe_ttm": _ff(bd.get("pe_ttm")),
            "pb": _ff(bd.get("pb")),
            "roe_5y_avg": _ff(d_fin.get("roe_5y_avg")),
            "roe_5y_min": _ff(d_fin.get("roe_5y_min")),
            "revenue_growth_3y_cagr": _ff(d_fin.get("revenue_growth_3y_cagr")),
            "dividend_yield": _ff(bd.get("dividend_yield_ttm")),
        }
        style_label = detect_style(feat_for_style, raw)
        adj = apply_style_weights(panel.get("investors", []), dims_scored, style_label)
        fund_score = adj["fundamental_score"]
        consensus = adj["panel_consensus"]
        style_diag = adj["diagnostics"]
        print(f"\n  🎯 v2.7 风格识别: {style_label} ({STYLE_LABELS.get(style_label,'?')}) — fund {fund_score_old:.1f}→{fund_score:.1f} · consensus {consensus_old:.1f}→{consensus:.1f}")
    except Exception as _se:
        print(f"  ⚠️ v2.7 风格加权失败（沿用原始公式）: {type(_se).__name__}: {str(_se)[:120]}")

    overall = fund_score * 0.6 + consensus * 0.4

    if overall >= 85: verdict_label = "值得重仓"
    elif overall >= 70: verdict_label = "可以蹲一蹲"
    elif overall >= 55: verdict_label = "观望优先"
    elif overall >= 40: verdict_label = "谨慎"
    else: verdict_label = "回避"

    # Pick bull and bear for great divide
    # CRITICAL: must pick from ACTUALLY bullish/bearish investors, never misattribute
    investors = panel.get("investors", [])

    # v2.6 · 防御性 panel 排序 (fix bug #5: "最看空 27 vs 下面 0 不一致")
    # 非 Claude LLM 可能写出 signal=bullish 但 score=5 这种自相矛盾输出。
    # 旧逻辑按 signal 先分组再选 → 实际可见的最低分(neutral/skip 里 0 分的)反而没被选为 bear。
    # 新逻辑：先排除 skip 和明显异常（score=0 通常是空数据），然后按 score 排序，
    #        bull = 最高分 · bear = 最低分。signal 仅作辅助检查。
    eligible = [
        i for i in investors
        if i.get("signal") != "skip"
        and i.get("score", 0) > 0  # 0 分通常是 fail_msg 幻觉，剔除
    ]
    if not eligible:
        eligible = [i for i in investors if i.get("signal") != "skip"] or investors

    inv_by_score = sorted(eligible, key=lambda x: -x.get("score", 0))
    bull = inv_by_score[0] if inv_by_score else (investors[0] if investors else {})
    bear = inv_by_score[-1] if inv_by_score else (investors[-1] if investors else {})

    # Safety: bull and bear must be different investors
    if bull.get("investor_id") == bear.get("investor_id") and len(inv_by_score) > 1:
        bear = inv_by_score[-2]

    # v2.6 · Sanity warnings: signal vs score 矛盾时打印（不阻断流程）
    def _check_signal_score(inv: dict, role: str) -> None:
        sig = inv.get("signal", "")
        sc = inv.get("score", 50)
        if role == "bull" and sig == "bearish":
            print(f"   ⚠️ Top bull '{inv.get('name')}' signal=bearish but score={sc} → 数据可能错乱")
        if role == "bear" and sig == "bullish":
            print(f"   ⚠️ Bottom bear '{inv.get('name')}' signal=bullish but score={sc} → 数据可能错乱")
    _check_signal_score(bull, "bull")
    _check_signal_score(bear, "bear")

    # Build debate rounds — use actual headline + reasoning from evaluator
    bull_headline = bull.get("headline", bull.get("comment", ""))
    bear_headline = bear.get("headline", bear.get("comment", ""))
    bull_reasoning = bull.get("reasoning", "")
    bear_reasoning = bear.get("reasoning", "")

    bull_pass_rules = bull.get("pass", [])
    bull_fail_rules = bull.get("fail", [])
    bear_pass_rules = bear.get("pass", [])
    bear_fail_rules = bear.get("fail", [])

    # Build debate rounds — agent can override with great_divide_override
    gd_override = ag.get("great_divide_override") or {}
    agent_bull_rounds = gd_override.get("bull_say_rounds") or []
    agent_bear_rounds = gd_override.get("bear_say_rounds") or []

    rounds = [
        {
            "round": 1,
            "bull_say": agent_bull_rounds[0] if len(agent_bull_rounds) > 0 else bull_headline,
            "bear_say": agent_bear_rounds[0] if len(agent_bear_rounds) > 0 else bear_headline,
        },
        {
            "round": 2,
            "bull_say": agent_bull_rounds[1] if len(agent_bull_rounds) > 1 else (" · ".join(r.get("msg", r.get("name", "")) for r in bull_pass_rules[:3]) or "数据支持我的判断。"),
            "bear_say": agent_bear_rounds[1] if len(agent_bear_rounds) > 1 else (" · ".join(r.get("msg", r.get("name", "")) for r in bear_fail_rules[:3]) or "风险点太多。"),
        },
        {
            "round": 3,
            "bull_say": agent_bull_rounds[2] if len(agent_bull_rounds) > 2 else f"综合看，{bull.get('score', 0)} 分，我的立场不变。",
            "bear_say": agent_bear_rounds[2] if len(agent_bear_rounds) > 2 else f"综合看，{bear.get('score', 0)} 分，风险大于收益。",
        },
    ]

    kline = (raw.get("dimensions", {}).get("2_kline") or {}).get("data") or {}
    val = (raw.get("dimensions", {}).get("10_valuation") or {}).get("data") or {}

    # v2.0 · Pull institutional modeling summaries
    d20 = (raw.get("dimensions", {}).get("20_valuation_models") or {}).get("data") or {}
    d21 = (raw.get("dimensions", {}).get("21_research_workflow") or {}).get("data") or {}
    d22 = (raw.get("dimensions", {}).get("22_deep_methods") or {}).get("data") or {}
    dcf_summary = d20.get("summary") or {}
    init_cov = d21.get("initiating_coverage") or {}
    ic_memo = d22.get("ic_memo") or {}
    competitive = d22.get("competitive_analysis") or {}

    # Build punchline with conflict — prefer real conflicts over platitudes
    dcf_sm = dcf_summary.get("dcf_safety_margin_pct", 0) or 0
    lbo_irr = dcf_summary.get("lbo_irr_pct", 0) or 0
    tp = (init_cov.get("headline") or {}).get("target_price") or 0
    upside = (init_cov.get("headline") or {}).get("upside_pct", 0) or 0
    rating = (init_cov.get("headline") or {}).get("rating", "")

    # Punchline: prefer agent override, fallback to script generation
    agent_punchline = gd_override.get("punchline") or ""
    if agent_punchline:
        punchline = agent_punchline
    elif dcf_sm and lbo_irr and abs(dcf_sm) > 10 and lbo_irr > 15:
        if dcf_sm < 0 and lbo_irr > 20:
            punchline = f"DCF 说高估 {abs(dcf_sm):.0f}%，但 LBO 测试显示 PE 买方仍能赚 {lbo_irr:.0f}% IRR — 冲突很有意思。"
        elif dcf_sm > 15 and lbo_irr > 20:
            punchline = f"DCF 认为低估 {dcf_sm:.0f}%，LBO IRR {lbo_irr:.0f}% 也确认 — 双重信号看多。"
        else:
            punchline = f"机构建模定调 {rating}，目标价 ¥{tp}（{upside:+.0f}%），LBO 视角 IRR {lbo_irr:.0f}%。"
    elif tp > 0 and abs(upside) > 5:
        punchline = f"首次覆盖 {rating}，目标价 ¥{tp}，空间 {upside:+.0f}%。"
    else:
        punchline = f"{name} · ROE 历史与当前估值存在结构性分歧，等待方向明朗。"

    # Risks: prefer agent-written, fallback to script generation from low-scoring dims
    narrative_override = ag.get("narrative_override") or {}
    agent_risks = narrative_override.get("risks") or []
    risks = list(agent_risks) if agent_risks else []
    if not risks:
        for key, dim in dims_scored["dimensions"].items():
            if dim["score"] <= 4:
                reasons = dim.get("reasons_fail", [])
                if reasons:
                    risks.extend(reasons[:1])
                else:
                    # Use dim name as fallback
                    dim_name = dim.get("name") or dim.get("label") or key
                    risks.append(f"{dim_name} 评分偏低 ({dim['score']}/10)")

    # If still empty, generate dynamic risks from actual data instead of hardcoded ones
    if not risks:
        pe_val = features.get("pe", 0) if "features" in dir() else 0
        debt_val = features.get("debt_ratio", 0) if "features" in dir() else 0
        # Use features from extract_features if available
        try:
            _f = extract_features(raw, raw.get("dimensions", {}))
            pe_val = _f.get("pe", 0)
            debt_val = _f.get("debt_ratio", 0)
            roe_min = _f.get("roe_5y_min", 0)
            industry = _f.get("industry", "所属行业")
        except Exception:
            pe_val, debt_val, roe_min, industry = 0, 0, 0, "所属行业"

        if pe_val > 30:
            risks.append(f"当前 PE {pe_val:.0f}x，估值偏高")
        if debt_val > 50:
            risks.append(f"资产负债率 {debt_val:.0f}%，财务杠杆偏高")
        if roe_min < 5:
            risks.append(f"ROE 最低 {roe_min:.1f}%，盈利稳定性不足")
        risks.append(f"{industry}行业竞争加剧风险")
        risks.append("宏观经济或政策环境变化")

    risks = risks[:5]

    # Friendly layer
    scenarios = compute_scenarios(raw, dims_scored)
    exit_triggers = compute_exit_triggers(raw, dims_scored, {})
    similar_stocks = raw.get("similar_stocks", [])

    # Dashboard — core_conclusion: agent override > script
    ytd_return = (kline.get("kline_stats") or {}).get("ytd_return", "—")
    agent_core_conclusion = narrative_override.get("core_conclusion") or ""
    core_conclusion = agent_core_conclusion or f"{name} · {int(overall)} 分 · {verdict_label}。51 位大佬里 {panel['signal_distribution']['bullish']} 人看多，YTD {ytd_return}。{punchline}"

    # v2.2 · dim_commentary: prefer agent-written, fallback to AUTO-SUMMARY (v2.6.1)
    # 关键修复：原 fallback 只生成 "[脚本占位]" 字符串，导致直跑模式下报告里
    # 5/6 定性维度是 missing/占位文字。新版直接把 raw_data 字段综合成实际中文。
    agent_dim_commentary = ag.get("dim_commentary") or {}
    dim_commentary_final: dict[str, str] = {}
    dim_labels = {
        "0_basic": "基础信息",
        "1_financials": "财报",
        "2_kline": "K线技术面",
        "3_macro": "宏观环境",
        "4_peers": "同行对比",
        "5_chain": "产业链",
        "6_research": "券商研报",
        "7_industry": "行业景气",
        "8_materials": "原材料",
        "9_futures": "期货关联",
        "10_valuation": "估值分位",
        "11_governance": "治理/减持",
        "12_capital_flow": "资金面",
        "13_policy": "政策与监管",
        "14_moat": "护城河",
        "15_events": "事件驱动",
        "16_lhb": "龙虎榜",
        "17_sentiment": "舆情",
        "18_trap": "杀猪盘",
        "19_contests": "实盘比赛",
    }
    for dim_key, label in dim_labels.items():
        # Agent-written commentary takes priority
        if dim_key in agent_dim_commentary and agent_dim_commentary[dim_key]:
            dim_commentary_final[dim_key] = agent_dim_commentary[dim_key]
        else:
            dim = (raw.get("dimensions", {}).get(dim_key) or {})
            score_info = dims_scored.get("dimensions", {}).get(dim_key) or {}
            score = score_info.get("score", 0)
            auto = _auto_summarize_dim(dim_key, label, dim, score)
            if auto:
                dim_commentary_final[dim_key] = auto

    return {
        "ticker": raw["ticker"],
        "name": name,
        "overall_score": round(overall, 1),
        "verdict_label": verdict_label,
        "fundamental_score": round(fund_score, 1),
        "panel_consensus": round(consensus, 1),
        "dim_commentary": dim_commentary_final,  # agent-written > stub
        "institutional_modeling": {
            "dcf_intrinsic": dcf_summary.get("dcf_intrinsic"),
            "dcf_safety_margin_pct": dcf_summary.get("dcf_safety_margin_pct"),
            "dcf_verdict": dcf_summary.get("dcf_verdict"),
            "lbo_irr_pct": dcf_summary.get("lbo_irr_pct"),
            "lbo_verdict": dcf_summary.get("lbo_verdict"),
            "comps_verdict": dcf_summary.get("comps_verdict"),
            "initiating_rating": (init_cov.get("headline") or {}).get("rating"),
            "target_price": (init_cov.get("headline") or {}).get("target_price"),
            "upside_pct": (init_cov.get("headline") or {}).get("upside_pct"),
            "ic_recommendation": (ic_memo.get("sections", {}).get("I_exec_summary", {}) or {}).get("headline"),
            "bcg_position": (competitive.get("bcg_position") or {}).get("category"),
            "industry_attractiveness": competitive.get("industry_attractiveness_pct"),
        },
        # v2.7 · 风格识别 + 加权诊断（让 HTML 报告显示 + agent 可在 agent_analysis.json 覆盖 style）
        "detected_style": style_label,
        "style_label_cn": (lambda: __import__("lib.stock_style", fromlist=["STYLE_LABELS"]).STYLE_LABELS.get(style_label, "?"))() if style_label else "?",
        "style_explanation": (lambda: __import__("lib.stock_style", fromlist=["STYLE_EXPLANATIONS"]).STYLE_EXPLANATIONS.get(style_label, ""))() if style_label else "",
        "style_diagnostics": style_diag,
        "agent_reviewed": bool(ag.get("agent_reviewed")),
        "panel_insights": ag.get("panel_insights") or "",
        "claude_narrative_stub": {
            "_note": "以下字段已由 agent 覆盖" if ag.get("agent_reviewed") else "以下字段是脚本生成的占位，Task 4 中 Claude 必须根据原始数据重写",
            "needs_rewrite": [] if ag.get("agent_reviewed") else [
                "great_divide.punchline", "dashboard.core_conclusion",
                "debate.rounds[*].bull_say", "debate.rounds[*].bear_say",
                "buy_zones.*.rationale", "risks[*]"],
        },
        "debate": {
            "bull": {"investor_id": bull["investor_id"], "name": bull["name"], "group": bull["group"]},
            "bear": {"investor_id": bear["investor_id"], "name": bear["name"], "group": bear["group"]},
            "rounds": rounds,
            "punchline": punchline,
        },
        "great_divide": {
            "bull_avatar": bull["investor_id"],
            "bear_avatar": bear["investor_id"],
            "bull_score": bull["score"],
            "bear_score": bear["score"],
            "bull_signal": bull["signal"],
            "bear_signal": bear["signal"],
            "punchline": punchline,
        },
        "risks": risks,
        "buy_zones": narrative_override.get("buy_zones") or {
            "value": {"price": round(price * 0.85, 2) if price else "—", "rationale": "历史 PE 25 分位"},
            "growth": {"price": round(price * 0.92, 2) if price else "—", "rationale": "PEG 合理区"},
            "technical": {"price": round(price * 0.95, 2) if price else "—", "rationale": "MA60 支撑位"},
            "youzi": {"price": price or "—", "rationale": "当前情绪未破"},
        },
        "friendly": {
            "scenarios": scenarios,
            "exit_triggers": exit_triggers,
            "similar_stocks": similar_stocks,
        },
        "fund_managers": raw.get("fund_managers", []),
        "dashboard": {
            "core_conclusion": core_conclusion,
            "data_perspective": {
                "trend": f"{kline.get('stage', '—')}",
                "price": f"¥{price}" if price else "—",
                "volume": "—",
                "chips": kline.get("ma_align", "—"),
            },
            "intelligence": {
                "news": "近期新闻 + 公告已采集",
                "risks": risks[:3],
                "catalysts": [
                    e.get("event", "季报")[:30]
                    for e in ((d21.get("catalyst_calendar") or {}).get("events") or [])
                    if e.get("impact") in ("high", "medium")
                ][:3] or ["季报窗口", "行业事件"],
            },
            "battle_plan": {
                "entry": f"¥{round(price * 0.92, 2) if price else '—'}",
                "position": "50% 起步",
                "stop": f"¥{round(price * 0.85, 2) if price else '—'}",
                "target": f"¥{round(price * 1.25, 2) if price else '—'}",
            },
        },
    }


def stage1(ticker: str) -> dict:
    """Stage 1: 数据采集 + 建模 + 规则引擎骨架分。

    返回 {ticker, raw, dims, panel, features} 供 Claude agent 审查。
    Claude 应该在 stage1 之后介入，用 sub-agent 逐组分析 51 评委，
    覆盖 panel.json 中的 headline/reasoning/score，然后调 stage2 生成报告。
    """
    # v2.3 · 中文名解析 — 支持纠错提示。若输入无法明确解析，早退并返回候选，不继续跑 22 fetcher。
    from lib.market_router import is_chinese_name
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
                # Early-exit with structured suggestions. Write a marker so run.py / agent can react.
                import json as _json
                from pathlib import Path as _Path
                safe_dir = _Path(".cache") / ticker
                safe_dir.mkdir(parents=True, exist_ok=True)
                err_payload = {
                    "status": "name_not_resolved",
                    "user_input": ticker,
                    "candidates": r["candidates"],
                    "message": f"未能确认 '{ticker}' 对应的股票。最接近的候选: "
                               + ", ".join(f"{c['name']}({c['code']})" for c in r["candidates"][:3]),
                }
                (safe_dir / "_resolve_error.json").write_text(
                    _json.dumps(err_payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(f"\n🔴 无法确认股票: {ticker!r}")
                print(f"   你是不是想输入：")
                for c in r["candidates"][:5]:
                    print(f"     · {c['name']} ({c['code']})   [编辑距离 {c['distance']}]")
                print(f"   请用 --force-name <代码> 指定，或用准确名称/代码重跑。")
                return err_payload
            else:
                ti = parse_ticker(ticker)  # last resort, will likely fail fetcher
        except Exception:
            ti = parse_ticker(ticker)
    else:
        ti = parse_ticker(ticker)
    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"🎯 TARGET: {ti.full}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    print("📊 Task 1 · 数据采集")
    raw = collect_raw_data(ti.full)
    write_task_output(ti.full, "raw_data", raw)

    # Data integrity check
    from lib.data_integrity import (
        validate as _validate_raw,
        format_report as _fmt_integrity,
        generate_recovery_tasks as _gen_tasks,
    )
    _integrity = _validate_raw(raw)
    print("\n" + _fmt_integrity(_integrity))
    raw["_integrity"] = _integrity

    # v2.3 · 生成可被 agent 消费的恢复任务清单（不 abort，让 agent 接管补数据）
    _tasks = _gen_tasks(raw, _integrity)
    if _tasks:
        import json as _json
        from pathlib import Path as _Path
        gaps_path = _Path(".cache") / ti.full / "_data_gaps.json"
        gaps_path.parent.mkdir(parents=True, exist_ok=True)
        gaps_path.write_text(
            _json.dumps({
                "ticker": ti.full,
                "coverage_pct": _integrity.get("coverage_pct", 0),
                "critical_missing": _integrity.get("critical_missing", False),
                "tasks": _tasks,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        crit_n = sum(1 for t in _tasks if t["severity"] == "critical")
        print(f"\n{'▓' * 50}")
        print(f"⚠️  检测到 {len(_tasks)} 个数据缺口 ({crit_n} critical)")
        print(f"   恢复任务清单: .cache/{ti.full}/_data_gaps.json")
        print(f"   Agent 必须尝试用以下手段补齐（按优先级）:")
        print(f"     1. Chrome/Playwright MCP 访问 xueqiu/eastmoney")
        print(f"     2. MX API (若 MX_APIKEY 已设置)")
        print(f"     3. WebSearch 精确到代码")
        print(f"     4. 已有数据逻辑推导")
        print(f"   仍拿不到的字段 → 在 agent_analysis.json 显式标 data_gap_acknowledged")
        print(f"   HTML 报告会对这些字段显示 ⚠️ 橙色徽章而非假数据")
        print(f"{'▓' * 50}")

    # v2.6.1 · 自动兜底补齐 6 个定性维度的空字段（不等 agent）
    # 论坛反馈：直跑模式下"宏观/政策/原材料"这些经常空，agent 没介入就出空报告
    # 优先 MX API，失败 fallback ddgs；都失败时显式标 _autofill_failed
    print("\n🤖 v2.6.1 · 自动兜底补齐定性维度空字段（MX → ddgs）...")
    try:
        _autofill_qualitative_via_mx(raw, ti.full)
        write_task_output(ti.full, "raw_data", raw)  # 持久化补齐后的数据
    except Exception as _af_e:
        print(f"   ⚠️ 自动兜底异常: {type(_af_e).__name__}: {str(_af_e)[:120]}")

    print("\n🏛  Task 1.5 · 机构级财务建模 (Dims 20-22)")
    from compute_deep_methods import compute_dim_20, compute_dim_21, compute_dim_22
    _features_pre = extract_features(raw, raw.get("dimensions", {}))
    raw["dimensions"]["20_valuation_models"] = compute_dim_20(_features_pre, raw)
    _d20 = raw["dimensions"]["20_valuation_models"]["data"]
    raw["dimensions"]["21_research_workflow"] = compute_dim_21(_features_pre, raw, _d20)
    _d21 = raw["dimensions"]["21_research_workflow"]["data"]
    raw["dimensions"]["22_deep_methods"] = compute_dim_22(_features_pre, raw, _d20, _d21)
    write_task_output(ti.full, "raw_data", raw)
    _s20 = _d20["summary"]
    _s21 = _d21["summary"]
    _s22 = raw["dimensions"]["22_deep_methods"]["data"]["summary"]
    print(f"  DCF: ¥{_s20.get('dcf_intrinsic')} · 安全边际 {_s20.get('dcf_safety_margin_pct')}% · {_s20.get('dcf_verdict')}")
    print(f"  LBO: IRR {_s20.get('lbo_irr_pct')}% · {_s20.get('lbo_verdict')}")
    print(f"  首次覆盖: {_s21.get('rec_rating')} · TP ¥{_s21.get('target_price')} ({_s21.get('upside_pct'):+}%)")
    print(f"  IC Memo: {_s22.get('ic_recommendation')}")
    print(f"  BCG: {_s22.get('bcg_position')} · 行业吸引力 {_s22.get('industry_attractiveness')}%")

    print("\n📏 Task 2 · 22 维打分")
    dims = score_dimensions(raw)
    write_task_output(ti.full, "dimensions", dims)
    print(f"  基本面得分: {dims['fundamental_score']}/100")

    print("\n🎭 Task 3 · 51 评委规则引擎（骨架分）")
    panel = generate_panel(dims, raw)
    write_task_output(ti.full, "panel", panel)
    sd = panel["signal_distribution"]
    skip_n = sd.get("skip", 0)
    active_n = len(panel["investors"]) - skip_n
    print(f"  参与 {active_n} · 跳过 {skip_n} · 看多 {sd['bullish']} · 中性 {sd['neutral']} · 看空 {sd['bearish']}")

    features = extract_features(raw, raw.get("dimensions", {}))

    print(f"\n{'━' * 50}")
    print(f"📋 Stage 1 完成 · 骨架分已生成")
    print(f"   数据: .cache/{ti.full}/raw_data.json")
    print(f"   评分: .cache/{ti.full}/dimensions.json")
    print(f"   评委: .cache/{ti.full}/panel.json")
    print(f"")
    print(f"   ⏸️  此时 Claude agent 应介入：")
    print(f"      1. 读取 panel.json 中 51 人的骨架分")
    print(f"      2. Spawn 4 个 sub-agent 分组 role-play 投资者")
    print(f"      3. 用 agent 判断覆盖 panel.json 中的 headline/reasoning/score")
    print(f"      4. 写 agent_analysis.json 到 .cache/{ti.full}/")
    print(f"         包含: dim_commentary, panel_insights, great_divide_override, narrative_override")
    print(f"         设置 agent_reviewed: true")
    print(f"      5. 然后调用 stage2('{ti.full}') 生成最终报告")
    print(f"{'━' * 50}")

    return {
        "ticker": ti.full,
        "raw": raw,
        "dims": dims,
        "panel": panel,
        "features": features,
    }


def stage2(ticker: str) -> str:
    """Stage 2: 综合研判 + 报告组装。

    在 Claude agent 审查/覆盖 panel.json + 写入 agent_analysis.json 之后调用。
    读取 .cache 中的最新数据生成报告。
    agent_analysis.json 的字段会合并进 synthesis，优先级高于脚本生成。
    返回报告路径。
    """
    from lib.cache import read_task_output
    ti = parse_ticker(ticker)

    raw = read_task_output(ti.full, "raw_data")
    dims = read_task_output(ti.full, "dimensions")
    panel = read_task_output(ti.full, "panel")

    if not (raw and dims and panel):
        raise RuntimeError(f"Stage 2 缺少数据，请先跑 stage1('{ticker}')")

    # v2.2 · Read agent_analysis.json — the agent's written-back analysis
    agent_analysis = read_task_output(ti.full, "agent_analysis")

    # v2.6 · 校验 agent_analysis schema（特别针对非 Claude 模型的输出）
    if agent_analysis:
        try:
            from lib.agent_analysis_validator import validate as _validate_aa, format_issues as _fmt_aa
            issues = _validate_aa(agent_analysis)
            errs = [i for i in issues if i.severity == "error"]
            if issues:
                print("\n" + _fmt_aa(issues))
                # 写错误清单 JSON 给 agent 复盘
                from pathlib import Path as _Path
                err_path = _Path(".cache") / ti.full / "_agent_analysis_errors.json"
                err_path.parent.mkdir(parents=True, exist_ok=True)
                err_path.write_text(
                    __import__("json").dumps(
                        [{"severity": i.severity, "field": i.field, "message": i.message, "suggestion": i.suggestion} for i in issues],
                        ensure_ascii=False, indent=2
                    ),
                    encoding="utf-8"
                )
                if errs:
                    print(f"   → 详细 issue 写入 {err_path}")
                    print(f"   → {len(errs)} 条结构性错误，agent 应修正后重跑 stage2")
        except Exception as _ve:
            print(f"   ⚠️ schema 校验跳过: {_ve}")

    if agent_analysis and agent_analysis.get("agent_reviewed"):
        print(f"\n🧠 Agent 分析已加载 · agent_analysis.json")
        ag_dc = agent_analysis.get("dim_commentary") or {}
        ag_written = sum(1 for v in ag_dc.values() if v and "[脚本占位]" not in str(v))
        print(f"   dim_commentary: {ag_written} 个维度有 agent 定性评语")
        print(f"   panel_insights: {'✓' if agent_analysis.get('panel_insights') else '✗'}")
        print(f"   narrative_override: {'✓' if agent_analysis.get('narrative_override') else '✗'}")
        print(f"   great_divide_override: {'✓' if agent_analysis.get('great_divide_override') else '✗'}")

        # v2.4 · HARD-GATE-QUALITATIVE 校验（仅警示，不 abort）
        qd = agent_analysis.get("qualitative_deep_dive") or {}
        required_dims = ("3_macro", "7_industry", "8_materials", "9_futures", "13_policy", "15_events")
        missing_qd = [d for d in required_dims if d not in qd or not qd[d].get("evidence")]
        total_evidence = sum(len((qd.get(d) or {}).get("evidence") or []) for d in required_dims)
        total_assoc = sum(len((qd.get(d) or {}).get("associations") or []) for d in required_dims)
        if missing_qd:
            print(f"   ⚠️  qualitative_deep_dive: 缺失 {len(missing_qd)}/6 维 ({','.join(missing_qd)})")
            print(f"      → 参考 references/task2.5-qualitative-deep-dive.md")
            print(f"      → 应 spawn 3 个并行 sub-agent (Macro-Policy / Industry-Events / Cost-Transmission)")
        else:
            print(f"   qualitative_deep_dive: ✓ 6 维全覆盖 · evidence {total_evidence} 条 · associations {total_assoc} 条")
            if total_assoc < 3:
                print(f"   ⚠️  跨域因果链仅 {total_assoc} 条，task2.5 要求 ≥ 3 条")
    else:
        print(f"\n⚠️  未检测到 agent_analysis.json · 将使用脚本骨架生成 synthesis")
        print(f"   提示: Claude agent 应在 stage1 之后写入 .cache/{ti.full}/agent_analysis.json")
        print(f"   然后再调用 stage2() · 这样报告质量会显著提升")
        agent_analysis = None

    print(f"\n⚖ Task 4 · 综合研判")
    syn = generate_synthesis(raw, dims, panel, agent_analysis=agent_analysis)

    # v2.3 · 合并 _data_gaps.json 进 synthesis，让报告组装环节能渲染橙色徽章/banner。
    # agent 若在 agent_analysis.json 里显式 ack 了某个 gap，标 resolved=false + note；
    # 其他未处理的 gap 原样传递给 HTML。
    from pathlib import Path as _Path
    import json as _json
    gaps_path = _Path(".cache") / ti.full / "_data_gaps.json"
    if gaps_path.exists():
        try:
            gaps_doc = _json.loads(gaps_path.read_text(encoding="utf-8"))
            tasks = gaps_doc.get("tasks", [])
            # Merge agent's ack if present
            acks = (agent_analysis or {}).get("data_gap_acknowledged", {}) if agent_analysis else {}
            for t in tasks:
                key = f"{t['dim']}.{t['field']}"
                if key in acks or t["dim"] in acks:
                    t["status"] = "acknowledged"
                    t["agent_note"] = acks.get(key, acks.get(t["dim"], ""))
            syn["data_gaps"] = {
                "coverage_pct": gaps_doc.get("coverage_pct", 0),
                "total_gaps": len(tasks),
                "unresolved": sum(1 for t in tasks if t["status"] == "pending"),
                "tasks": tasks,
            }
            print(f"  data_gaps: {syn['data_gaps']['total_gaps']} 项 · 已 ack {syn['data_gaps']['total_gaps'] - syn['data_gaps']['unresolved']}")
        except Exception as _e:
            print(f"  ⚠️ 读取 _data_gaps.json 失败: {_e}")

    write_task_output(ti.full, "synthesis", syn)
    print(f"  综合评分: {syn['overall_score']}/100 · {syn['verdict_label']}")
    print(f"  agent_reviewed: {syn.get('agent_reviewed', False)}")

    print(f"\n📄 Task 5 · 报告组装")
    from assemble_report import assemble
    out = assemble(ti.full)
    print(f"  → {out}")

    from inline_assets import main as inline_main
    standalone = inline_main(ti.full)

    try:
        from render_share_card import main as render_sc
        render_sc(ti.full)
        print(f"  ✓ 朋友圈分享卡 PNG")
    except Exception as e:
        print(f"  ⚠️ 分享卡跳过: {e}")
    try:
        from render_war_report import main as render_wr
        render_wr(ti.full)
        print(f"  ✓ 战报横图 PNG")
    except Exception as e:
        print(f"  ⚠️ 战报跳过: {e}")

    standalone_path = Path(standalone).resolve()
    assert standalone_path.exists() and standalone_path.stat().st_size > 10000, \
        f"Standalone file missing or too small: {standalone_path}"

    print(f"\n✅ Stage 2 完成!")
    print(f"   报告: {standalone_path}")
    print(f"   大小: {standalone_path.stat().st_size // 1024} KB")

    if os.environ.get("UZI_NO_AUTO_OPEN") != "1":
        try:
            import webbrowser
            webbrowser.open(standalone_path.as_uri())
            print(f"   🌐 已在浏览器中打开")
        except Exception:
            print(f"   💡 手动打开: {standalone_path}")

    return str(standalone_path)


def main(ticker: str = "002273.SZ"):
    """完整流程: stage1 + stage2 一把跑完（无 agent 介入 = 快速模式）。

    当 Claude agent 使用时，应该分开调用:
        result = stage1(ticker)   # 数据+骨架分
        # ... agent 审查 panel.json, 写 agent_analysis.json ...
        stage2(ticker)            # 生成报告 (自动合并 agent_analysis)
    """
    result = stage1(ticker)
    # v2.3 · stage1 可能因中文名无法解析而早退，此时不能继续 stage2
    if isinstance(result, dict) and result.get("status") == "name_not_resolved":
        print("\n⚠️  因股票名无法解析，跳过 stage2（不会生成空报告）")
        return
    report_path = stage2(ticker)
    print(f"\n🎯 完整流程结束 · 报告: {report_path}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"
    main(arg)
