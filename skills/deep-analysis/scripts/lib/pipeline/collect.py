"""pipeline.collect · wave-based 数据采集编排器.

v3.0.0 Phase 7+ · 性能跟 legacy collect_raw_data 完全对齐.

设计：
- wave 1: 0_basic 先跑（后续 fetcher 依赖 industry）
- wave 2: 非依赖型 fetcher **并发 max_workers=6** + mini_racer 串行锁（跟 legacy 一致）
- wave 3: 依赖型 fetcher（3_macro / 7_industry / 9_futures / 13_policy）
- 所有结果返 dict[dim_key, DimResult]

**业务零区别保证**：
- 输出 raw_data.json 跟 legacy 格式完全一致（ticker/data/source/fallback 顶层字段）
- pipeline-extra 元信息放 `_pipeline` 命名空间 · 下游读不到就忽略
- 性能：并发 + 锁 · 跟 legacy 对齐（cold ~5min · warm ~15s）

feature flag：UZI_PIPELINE=1 时 stage1 走新管道 · 否则走老 collect_raw_data
"""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .fetchers.registry import FETCHER_REGISTRY, get_fetcher
from .schema import DimResult, Quality


# 依赖 0_basic.industry 的 dim · 必须在 wave 3
DEPENDENT_DIMS = {"3_macro", "7_industry", "9_futures", "13_policy"}

# v3.0.0 · mini_racer V8 isolate 非 thread-safe · 这些 legacy fetcher 用 mini_racer
# 必须串行跑 · 跟 legacy `_MINI_RACER_FETCHERS` 一致
_MINI_RACER_LEGACY_MODULES = {"fetch_industry", "fetch_capital_flow", "fetch_valuation"}
_MINI_RACER_LOCK = threading.Lock()


def is_pipeline_enabled() -> bool:
    """feature flag · 默认关 · 只在 UZI_PIPELINE=1 时启用新管道."""
    return os.environ.get("UZI_PIPELINE") == "1"


def collect(ticker: Any, raw_previous: dict | None = None, max_workers: int = 6) -> dict[str, dict]:
    """主入口 · 返老格式 dict · 兼容 run_real_test 下游消费.

    raw_previous · 用于 resume 模式 · 已有缓存的 dim 跳过.

    max_workers=6 默认 · 跟 legacy 一致 · mini_racer fetcher 用 _MINI_RACER_LOCK 串行.

    返回 dict 格式（100% 跟 legacy raw_data.json 兼容）：
    {
        "0_basic": {
            "data": {...},
            "source": "...",
            "fallback": bool,                  # ← legacy 格式
            "_pipeline": {quality, data_gaps, ...}  # ← v3 pipeline 额外
        },
        ...
        "fund_managers": [...]  # top_level 溢出字段（legacy 已有此惯例）
    }
    """
    t0 = time.time()
    out: dict[str, Any] = {}
    raw_previous = raw_previous or {}

    # Wave 1 · 0_basic 必须先跑
    basic_dim = raw_previous.get("dimensions", {}).get("0_basic")
    if basic_dim and _is_resume_valid(basic_dim):
        print("  [pipeline] 0_basic · resume cache")
        out["0_basic"] = basic_dim
    else:
        print("  [pipeline] wave 1 · 0_basic", end="", flush=True)
        t_w1 = time.time()
        basic_fetcher = get_fetcher("0_basic")
        result = basic_fetcher.fetch(ticker)
        out["0_basic"] = result.to_dict()
        # 写顶层溢出字段
        for k, v in result.top_level_fields.items():
            out[k] = v
        print(f" · {result.quality.value} ({time.time()-t_w1:.1f}s)")

    basic_data = out["0_basic"].get("data") or {}

    # Wave 2 · 非依赖型 fetcher 并发
    non_dep_dims = [d for d in FETCHER_REGISTRY.keys()
                    if d not in DEPENDENT_DIMS and d != "0_basic"]
    print(f"  [pipeline] wave 2 · {len(non_dep_dims)} fetcher (max_workers={max_workers})")

    def _run(dim_key: str) -> tuple[str, dict, dict]:
        # 检查 resume
        cached = raw_previous.get("dimensions", {}).get(dim_key)
        if cached and _is_resume_valid(cached):
            return dim_key, cached, {}
        fetcher = get_fetcher(dim_key)
        if not fetcher:
            return dim_key, DimResult.empty(dim_key).to_dict(), {}
        # v3.0.0 · mini_racer fetcher 必须串行（V8 isolate 非 thread-safe · 跟 legacy 一致）
        legacy_mod = getattr(fetcher, "_legacy_module", "")
        if legacy_mod in _MINI_RACER_LEGACY_MODULES:
            # v3.3.4 · issue #61 · UZI_DISABLE_MINI_RACER=1 时跳过危险 fetcher
            # valuation 可走 basic+MX 安全路径 · industry/capital_flow 仍 empty
            if os.environ.get("UZI_DISABLE_MINI_RACER") == "1":
                if dim_key == "10_valuation" or legacy_mod == "fetch_valuation":
                    try:
                        from fetch_valuation import main_safe
                        safe = main_safe(ticker)
                        data = (safe or {}).get("data") or {}
                        from .schema import DimResult, Quality
                        filled = any(
                            data.get(k) not in (None, "", "—")
                            for k in ("pe", "pb", "pe_quantile", "pb_quantile")
                        )
                        dr = DimResult(
                            dim_key=dim_key,
                            data=data,
                            quality=Quality.PARTIAL if filled else Quality.MISSING,
                            source=(safe or {}).get("source") or "main_safe",
                            error=(safe or {}).get("error"),
                        )
                        return dim_key, dr.to_dict(), dr.top_level_fields
                    except Exception as e:
                        return dim_key, DimResult.error_result(dim_key, f"main_safe: {e}").to_dict(), {}
                return dim_key, DimResult.empty(dim_key).to_dict(), {}
            with _MINI_RACER_LOCK:
                result = fetcher.fetch(ticker)
        else:
            result = fetcher.fetch(ticker)
        return dim_key, result.to_dict(), result.top_level_fields

    # 构造 raw dict 给 args_fn 用（部分 fetcher 需要从 0_basic 拿 industry）
    # 但 wave 2 的 non-dependent 不需要 raw · 此处简化
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run, d): d for d in non_dep_dims}
        for f in as_completed(futures):
            try:
                dim_key, result_dict, top_level = f.result(timeout=120)
                out[dim_key] = result_dict
                for k, v in top_level.items():
                    out[k] = v
                q = (result_dict.get("_pipeline") or {}).get("quality", "?")
                print(f"    ✓ {dim_key:20s} {q}")
            except Exception as e:
                d = futures[f]
                print(f"    ✗ {d:20s} {type(e).__name__}: {str(e)[:80]}")
                out[d] = DimResult.error_result(d, f"{type(e).__name__}: {e}").to_dict()

    # Wave 3 · 依赖 industry 的 fetcher · 串行（industry 是 shared context）
    print(f"  [pipeline] wave 3 · {len(DEPENDENT_DIMS)} dependent fetcher")
    # 构造 raw-shaped dict 给 args_fn
    raw_for_deps = {"0_basic": out["0_basic"]}
    # v3.9.4 · 9_futures 依赖 8_materials 的 materials_detail（识别原材料期货品种）· 一并传入
    if "8_materials" in out:
        raw_for_deps["8_materials"] = out["8_materials"]
    if "1_financials" in out:
        raw_for_deps["1_financials"] = out["1_financials"]
    for dim_key in sorted(DEPENDENT_DIMS):
        cached = raw_previous.get("dimensions", {}).get(dim_key)
        if cached and _is_resume_valid(cached):
            out[dim_key] = cached
            continue
        fetcher = get_fetcher(dim_key)
        if not fetcher:
            continue
        try:
            # 依赖 fetcher 的 _fetch_raw 收 raw 参数 · 但 BaseFetcher.fetch() 不传 raw
            # 临时方案：monkey-patch args_fn 变量闭包已经 bound 了 r · 但 raw 传不进去
            # 解决：给 BaseFetcher.fetch 加可选 context 参数
            result = _fetch_with_context(fetcher, ticker, raw_for_deps)
            out[dim_key] = result.to_dict()
            for k, v in result.top_level_fields.items():
                out[k] = v
            print(f"    ✓ {dim_key:20s} {result.quality.value}")
        except Exception as e:
            print(f"    ✗ {dim_key:20s} {type(e).__name__}: {str(e)[:80]}")
            out[dim_key] = DimResult.error_result(dim_key, f"{type(e).__name__}: {e}").to_dict()

    print(f"  [pipeline] collect 完成 · {time.time()-t0:.1f}s")
    return out


def _is_resume_valid(dim_dict: dict) -> bool:
    """判断 dim cache 是否有效 · 兼容 legacy 和 v3 格式."""
    if not isinstance(dim_dict, dict):
        return False
    data = dim_dict.get("data") or {}
    # v3 格式：_pipeline.quality 不是 missing/error
    pp = dim_dict.get("_pipeline") or {}
    q = pp.get("quality") or dim_dict.get("quality", "")
    if q in ("missing", "error"):
        return False
    # legacy 格式：fallback=True 表示抓失败
    if dim_dict.get("fallback") is True:
        return False
    return bool(data)


def _fetch_with_context(fetcher, ticker, raw_context: dict) -> DimResult:
    """跑依赖型 fetcher · 把 raw_context 传给 _fetch_raw（通过 args_fn）."""
    # 临时方案：直接手动调 args_fn · bypass BaseFetcher.fetch 的 signature
    import importlib
    import time as _time
    t0 = _time.time()
    try:
        mod = importlib.import_module(fetcher._legacy_module)
        args = fetcher._args_fn(ticker, raw_context)
        result = mod.main(*args)
        if isinstance(result, dict) and "data" in result and isinstance(result["data"], dict):
            raw_data = result["data"]
        elif isinstance(result, dict):
            raw_data = result
        else:
            raw_data = {}
    except Exception as e:
        return DimResult.error_result(
            fetcher.spec.dim_key,
            error=f"{type(e).__name__}: {str(e)[:100]}",
            source=f"legacy:{fetcher._legacy_module}",
        )

    # 规约 + 校验（复用 BaseFetcher 逻辑）
    from .validators import normalize_data, validate_result
    normalized = normalize_data(raw_data, keep_zero_fields=fetcher.keep_zero_fields)
    top_level = fetcher.extract_top_level(normalized)
    dim_result = DimResult(
        dim_key=fetcher.spec.dim_key,
        data={k: v for k, v in normalized.items() if k not in top_level},
        source=f"legacy:{fetcher._legacy_module}",
        top_level_fields=top_level,
        latency_ms=int((_time.time() - t0) * 1000),
    )
    return validate_result(dim_result, fetcher.spec)
