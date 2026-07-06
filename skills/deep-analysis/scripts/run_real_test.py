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
#
# v3.3.4 · issue #61 · macOS Python 3.12/3.13 + mini_racer 0.x 即使串行化仍可能
# 在 V8 isolate pool 双重初始化时 SIGTRAP（"address_pool_manager.cc Check failed"）·
# 用户可设 `UZI_DISABLE_MINI_RACER=1` env var 完全跳过这 3 个 fetcher · graceful 降级
# (industry_pe / fund_flow / a_pe_and_pb 字段会缺 · 但报告其余 19 维仍正常生成)
import threading as _threading
_MINI_RACER_FETCHERS = {"fetch_industry", "fetch_capital_flow", "fetch_valuation"}
_MINI_RACER_LOCK = _threading.Lock()


_MINI_RACER_SENTINEL = Path.home() / ".uzi-skill" / "_minirackercrash.sentinel"


def _mini_racer_disabled() -> bool:
    """v3.3.4 · 多重判断是否禁用 mini_racer.

    1. 显式 env var `UZI_DISABLE_MINI_RACER=1` → disable
    2. `UZI_FORCE_MINI_RACER=1` → force enable (overrides sentinel)
    3. sentinel 文件存在（上次 crash 留下）→ auto-disable + 提示
    """
    if os.environ.get("UZI_DISABLE_MINI_RACER") == "1":
        return True
    if os.environ.get("UZI_FORCE_MINI_RACER") == "1":
        return False
    if _MINI_RACER_SENTINEL.exists():
        # auto-recovery：上次 mini_racer 崩过 · 本次自动 skip
        # 用户想重试可 `rm ~/.uzi-skill/_minirackercrash.sentinel` 或 UZI_FORCE_MINI_RACER=1
        if not getattr(_mini_racer_disabled, "_warned", False):
            print(
                f"   ⚠️  检测到上次 mini_racer 崩溃记录 · 自动跳过 industry/capital_flow/valuation 中的 cninfo/lg 调用",
                file=sys.stderr,
            )
            print(
                f"   ℹ️  想重试 · `rm {_MINI_RACER_SENTINEL}` 或 `UZI_FORCE_MINI_RACER=1`",
                file=sys.stderr,
            )
            _mini_racer_disabled._warned = True  # 避免重复打印
        return True
    return False


def _arm_mini_racer_sentinel(module_name: str) -> None:
    """v3.3.4 · 调 mini_racer fetcher 前写 sentinel · 若崩则下次启动检测到."""
    try:
        _MINI_RACER_SENTINEL.parent.mkdir(parents=True, exist_ok=True)
        _MINI_RACER_SENTINEL.write_text(
            f"{time.time()}|{module_name}\n", encoding="utf-8"
        )
    except Exception:
        pass


def _disarm_mini_racer_sentinel() -> None:
    """v3.3.4 · 调 mini_racer fetcher 成功后删 sentinel."""
    try:
        if _MINI_RACER_SENTINEL.exists():
            _MINI_RACER_SENTINEL.unlink()
    except Exception:
        pass


def run_fetcher(module_name: str, args: tuple) -> dict:
    # v3.3.4 · issue #61 · 多重保护 mini_racer 崩溃
    if module_name in _MINI_RACER_FETCHERS and _mini_racer_disabled():
        return {
            "data": {"_disabled": "mini_racer skipped (env / sentinel)"},
            "source": f"{module_name} (skipped)",
            "fallback": True,
            "error": "mini_racer disabled · crashes V8 on macOS Py 3.12/3.13",
        }
    try:
        mod = __import__(module_name)
        if module_name in _MINI_RACER_FETCHERS:
            with _MINI_RACER_LOCK:
                # v3.3.4 · 调用前埋 sentinel · 若进程崩 sentinel 留着 · 下次启动 auto-disable
                _arm_mini_racer_sentinel(module_name)
                result = mod.main(*args)
                _disarm_mini_racer_sentinel()
        else:
            result = mod.main(*args)
        return result if isinstance(result, dict) else {"data": result}
    except Exception as e:
        # 普通 Python 异常 · sentinel 不留（说明只是逻辑错 · 非 V8 crash）
        if module_name in _MINI_RACER_FETCHERS:
            _disarm_mini_racer_sentinel()
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

    # v2.10.6 · market 先用 parse_ticker 前置识别（HK/US 不再默认 "A"）
    # 原因：fetch_basic 有可能失败，但 parse_ticker("00700.HK") 纯字符串即可知道是 H 股
    from lib.market_router import parse_ticker as _parse, is_chinese_name as _is_cn
    _initial_market = "A"
    try:
        if not _is_cn(ticker):
            _initial_market = _parse(ticker).market
    except Exception:
        pass
    raw = {"ticker": ticker, "market": _initial_market, "fetched_at": _dt.now().isoformat(timespec="seconds")}
    dims: dict = {}
    t0 = time.time()

    # v2.6 · resume: 加载已有 raw_data.json 中的 dim 缓存
    # v2.10.6 · resume cache 双重查询：原始 ticker 和 parse_ticker 后的 full code 都试
    # 解决：用户用中文名/三位港股输入时，cache 是按 resolved 代码存的，不查就错过
    cached_dims: dict = {}
    if resume:
        from lib.cache import read_task_output as _read_cache
        # 1) 原始 ticker 直查
        prev = _read_cache(ticker, "raw_data")
        # 2) 如果没命中，用 parse_ticker 推测的 full code 再查（三位港股 "700" → "00700.HK"）
        if not prev and not _is_cn(ticker):
            try:
                _full = _parse(ticker).full
                if _full != ticker:
                    prev = _read_cache(_full, "raw_data")
                    if prev:
                        print(f"  [resume] cache 命中 · {ticker} → {_full}")
            except Exception:
                pass
        if prev and isinstance(prev.get("dimensions"), dict):
            cached_dims = prev["dimensions"]
            # 从 cache 也回填 market（它是 fetch_basic 真实抓回来的）
            _cached_market = prev.get("market")
            if _cached_market in ("A", "H", "U"):
                raw["market"] = _cached_market
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
    # v2.10.6 · market 无条件从 fetch_basic top-level 回填（不是 .data.market，fetch_basic
    # 把 market 放在顶层），解决 HK/US 直输时 raw.market 仍为 "A" 的污染问题
    _basic_market = dims.get("0_basic", {}).get("market")
    if _basic_market in ("A", "H", "U"):
        raw["market"] = _basic_market

    # ── Wave 2: all other 19 fetchers in parallel ──
    # v2.6 · 加 per-fetcher timeout + overall timeout 防止 hang 卡死整条流水线
    # v2.6 · resume: 已缓存有效的 dim 直接复用，不重新调 fetcher
    # v2.10.2 · 根据 analysis_profile 决定跑哪几维（lite 只跑核心 7 维）
    wave2_start = time.time()
    try:
        from lib.analysis_profile import get_profile as _get_profile
        _profile = _get_profile()
        enabled_dims = _profile.fetchers_enabled
    except Exception:
        enabled_dims = None
    all_others = [(m, d, a) for m, d, a in FETCHER_MAP if d != "0_basic"]
    # 按 profile 过滤（None 时不过滤，向后兼容）
    if enabled_dims is not None:
        before = len(all_others)
        all_others = [(m, d, a) for m, d, a in all_others if d in enabled_dims]
        skipped_profile = before - len(all_others)
        if skipped_profile > 0:
            print(f"  [profile] {_profile.depth} 模式跳过 {skipped_profile} 个维度")
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

    # v2.7.2 · 强制 flush：wave2 结束后立即把 dims（含 timeout 标记）落盘一次，
    # 防止 Ctrl+C / 后续 wave3 crash 时丢失 wave2 的完整状态（包括被标记超时的 fetcher）。
    _persist_progress()

    # ── Wave 3: bonus fetchers (parallel) ──
    print("  [wave 3] bonus fetchers parallel ...")
    wave3_start = time.time()

    def _fund_holders():
        try:
            import fetch_fund_holders
            # v2.10.1 · 清单 limit 保持 None（全量列出 649 家），慢在 fetch_fund_holders
            # 内部已改成"头部 top N 算完整 5Y 业绩，其余只列名字"双层策略。
            # UZI_FUND_STATS_TOP=N 控制几家算完整业绩（默认 20）。
            # 用户原问题："基金拉全不是直接检索就行了吗" — 对，清单一次 API 就够，
            # 过去慢是因为每家都跑 5Y NAV 计算，现在只头部跑，其他点 fund_url 看详情。
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

    # v2.7.2 · stage1 收尾再 flush 一次，确保 wave3 的 fund_managers / similar_stocks 也已落盘
    try:
        from lib.cache import write_task_output as _write_cache_final
        _write_cache_final(ticker, "raw_data", raw)
    except Exception:
        pass

    return raw


# ─────────── DIMENSIONS SCORING (rule-based) ───────────


# ═══════════════════════════════════════════════════════════════
# v3.1 · 1228 行纯函数已搬到 lib/pipeline/score_fns.py
# rrt 仍 re-export 保持向后兼容（stage1/stage2 + 外部调用不受影响）
# ═══════════════════════════════════════════════════════════════
from lib.pipeline.score_fns import (  # noqa: E402, F401
    _f,
    score_dimensions,
    generate_panel,
    _auto_summarize_dim,
    _autofill_qualitative_via_mx,
    _extract_mx_text,
    generate_synthesis,
    _is_junk_autofill,          # v2.12.1 junk filter（测试期望顶层属性）
    _AUTOFILL_JUNK_PATTERNS,    # v2.12.1
)


def _detect_lite_mode() -> tuple[bool, str]:
    """v2.10.1 · 三种方式决定是否进 lite mode:

    1. UZI_LITE=1 env（显式）
    2. UZI_LITE=auto 或未设置 → 自动检测首次安装（.cache/_global 为空）
    3. UZI_LITE=0 → 强制关闭

    Lite mode 影响:
      - fetch_macro / fetch_policy / fetch_moat 跳过 ddgs（返空让 agent 知道）
      - fetch_industry 跳过 _dynamic_industry_overview（省 3-9 次 ddgs）
      - wave3 fund_managers 不改（已有 UZI_FUND_LIMIT 控制）
      - HTML 报告正常生成，但会显示"⚡ LITE MODE 跑完后可去 LITE=0 补数据"

    返回 (is_lite: bool, reason: str)
    """
    import os
    from pathlib import Path
    val = os.environ.get("UZI_LITE", "auto").lower()
    if val in ("1", "true", "yes", "on"):
        return True, "UZI_LITE=1 显式启用"
    if val in ("0", "false", "no", "off"):
        return False, "UZI_LITE=0 显式关闭"
    # auto 模式：检测 _global api_cache 是否为空（首次安装判定）
    global_cache = Path(".cache/_global/api_cache")
    if not global_cache.exists():
        return True, "首次安装（.cache/_global 不存在）自动 lite"
    try:
        if len(list(global_cache.iterdir())) < 5:
            return True, "cache 非常冷（_global/api_cache 条目 < 5）自动 lite"
    except Exception:
        pass
    return False, "cache 已预热，full mode"


def stage1(ticker: str) -> dict:
    """Stage 1: 数据采集 + 建模 + 规则引擎骨架分。

    返回 {ticker, raw, dims, panel, features} 供 Claude agent 审查。
    Claude 应该在 stage1 之后介入，用 sub-agent 逐组分析 51 评委，
    覆盖 panel.json 中的 headline/reasoning/score，然后调 stage2 生成报告。
    """
    # v3.1 · stage1 前置段 (preflight + lite + name resolve + ETF guard) 已抽到 pipeline.preflight_helpers
    # 保持业务行为零差异 · 只是代码组织更清晰
    from lib.pipeline.preflight_helpers import prepare_target
    _pt = prepare_target(ticker, detect_lite_fn=_detect_lite_mode)
    if not _pt["ok"]:
        return _pt["payload"]  # name_not_resolved / non_stock_security early-exit
    ti = _pt["ticker_info"]

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

    # v2.13.0 · Playwright 最后一层兜底（按 profile 决策 · lite 自动跳过 · deep 默认启用 + y/n 装）
    # lite: 完全禁用 · medium: opt-in (UZI_PLAYWRIGHT_ENABLE=1) · deep: 默认启用（未装 y/n 确认装）
    try:
        from lib.playwright_fallback import autofill_via_playwright, is_playwright_enabled
        if is_playwright_enabled():
            print("\n🎭 v2.13.0 · Playwright 兜底（按 profile 策略）...")
            _pw_summary = autofill_via_playwright(raw, ti.full)
            if _pw_summary.get("succeeded", 0) > 0:
                write_task_output(ti.full, "raw_data", raw)
    except Exception as _pwe:
        print(f"   ⚠️ Playwright 兜底异常（跳过，不阻塞主流程）: {type(_pwe).__name__}: {str(_pwe)[:120]}")

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


def _validate_agent_analysis_or_fallback(agent_analysis: dict | None, ticker: str):
    """Validate agent_analysis and discard structurally invalid payloads."""
    if not agent_analysis:
        return None, []
    try:
        from lib.agent_analysis_validator import validate as _validate_aa, format_issues as _fmt_aa
        issues = _validate_aa(agent_analysis)
        errs = [i for i in issues if i.severity == "error"]
        if issues:
            print("\n" + _fmt_aa(issues))
            from pathlib import Path as _Path
            err_path = _Path(".cache") / ticker / "_agent_analysis_errors.json"
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
                print(f"   → {len(errs)} 条结构性错误，已回退到脚本骨架；agent 应修正后重跑 stage2")
                return None, issues
        return agent_analysis, issues
    except Exception as _ve:
        print(f"   ⚠️ schema 校验跳过: {_ve}")
        return agent_analysis, []


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
    # error 级结构问题不能继续 merge，否则 narrative_override/list 等坏结构会污染 synthesis。
    agent_analysis, _agent_analysis_issues = _validate_agent_analysis_or_fallback(agent_analysis, ti.full)

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
        return result
    # v2.10.4 · stage1 可能因非个股标的（ETF/指数/可转债）而早退，不能继续 stage2
    if isinstance(result, dict) and result.get("status") == "non_stock_security":
        print("\n⚠️  非个股标的，跳过 stage2（已输出成分股清单给 agent）")
        return result
    report_path = stage2(ticker)
    print(f"\n🎯 完整流程结束 · 报告: {report_path}")
    return report_path


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"
    main(arg)
