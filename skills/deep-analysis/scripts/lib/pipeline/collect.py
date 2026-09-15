"""pipeline.collect · wave-based 数据采集编排器.

v3.0.0 Phase 7+ · 性能跟 legacy collect_raw_data 完全对齐.

设计：
- wave 1: 0_basic 先跑（后续 fetcher 依赖 industry）
- wave 2: 非依赖型 fetcher **并发 max_workers=6** + mini_racer 串行组
- wave 3: 依赖型 fetcher（3_macro / 7_industry / 9_futures / 13_policy）
- 所有结果返 dict[dim_key, DimResult]

**业务零区别保证**：
- 输出 raw_data.json 跟 legacy 格式完全一致（ticker/data/source/fallback 顶层字段）
- pipeline-extra 元信息放 `_pipeline` 命名空间 · 下游读不到就忽略
- 性能：可终止子进程并发 + 串行组 · 单 fetcher 和整波都有硬超时

feature flag：UZI_PIPELINE=1 时 stage1 走新管道 · 否则走老 collect_raw_data
"""
from __future__ import annotations

import os
import time
from typing import Any

from .fetchers.registry import FETCHER_REGISTRY, get_fetcher
from .process_runner import ProcessJob, ProcessOutcome, run_process_jobs
from .schema import DimResult


# 依赖 0_basic.industry 的 dim · 必须在 wave 3
DEPENDENT_DIMS = {"3_macro", "7_industry", "9_futures", "13_policy"}

# v3.0.0 · mini_racer V8 isolate 非 thread-safe · 这些 legacy fetcher 用 mini_racer
# 必须串行跑 · 跟 legacy `_MINI_RACER_FETCHERS` 一致
_MINI_RACER_LEGACY_MODULES = {"fetch_industry", "fetch_capital_flow", "fetch_valuation"}
def is_pipeline_enabled() -> bool:
    """feature flag · 默认关 · 只在 UZI_PIPELINE=1 时启用新管道."""
    return os.environ.get("UZI_PIPELINE") == "1"


def _dim_scope() -> tuple[frozenset[str] | None, frozenset[str]]:
    """返回 (本档位启用的 fetcher 维度, 档位管辖的全部维度)。

    读取 profile 失败 → (None, frozenset())，表示不做裁剪，保持 v3.0 原行为
    （宁可多跑，也不要因为 profile 异常而中断采集）。
    """
    try:
        from ..analysis_profile import ALL_FETCHER_DIMS, get_profile
        return frozenset(get_profile().fetchers_enabled), frozenset(ALL_FETCHER_DIMS)
    except Exception as e:
        print(f"  [pipeline] ⚠ 读取 analysis_profile 失败 · 不做档位裁剪: {e}")
        return None, frozenset()


def _mini_racer_disabled() -> bool:
    if os.environ.get("UZI_DISABLE_MINI_RACER") == "1":
        return True
    import run_real_test as rrt
    return rrt._mini_racer_disabled()


def _cache_ttl(fetcher) -> int:
    spec = getattr(fetcher, "spec", None)
    return int(getattr(spec, "cache_ttl_sec", 3600))


def _positive_env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
        return value if value > 0 else default
    except ValueError:
        return default


def _run_fetcher_job(dim_key: str, ticker: Any, raw_context: dict | None = None) -> tuple[str, dict, dict]:
    """Child-process entrypoint returning only pickle-safe data."""
    fetcher = get_fetcher(dim_key)
    if not fetcher:
        return dim_key, DimResult.empty(dim_key).to_dict(), {}

    legacy_mod = getattr(fetcher, "_legacy_module", "")
    is_mini_racer = legacy_mod in _MINI_RACER_LEGACY_MODULES
    if is_mini_racer and _mini_racer_disabled():
        if legacy_mod == "fetch_valuation":
            from fetch_valuation import main_safe
            from .validators import normalize_data, validate_result

            raw_result = main_safe(ticker)
            normalized = normalize_data(raw_result.get("data") or {})
            result = DimResult(
                dim_key=dim_key,
                data=normalized,
                source=raw_result.get("source") or "fetch_valuation (mini_racer-safe)",
                fetched_at=time.time(),
            )
            result = validate_result(result, fetcher.spec)
            return dim_key, result.to_dict(), {}
        result = DimResult.empty(dim_key, source=f"{legacy_mod} (skipped)")
        return dim_key, result.to_dict(), {}

    rrt = None
    if is_mini_racer:
        import run_real_test as rrt
        rrt._arm_mini_racer_sentinel(legacy_mod)
    try:
        result = (
            _fetch_with_context(fetcher, ticker, raw_context)
            if raw_context is not None
            else fetcher.fetch(ticker)
        )
    finally:
        if rrt is not None:
            rrt._disarm_mini_racer_sentinel()
    return dim_key, result.to_dict(), result.top_level_fields


def _apply_outcome(out: dict[str, Any], outcome: ProcessOutcome) -> None:
    if outcome.error:
        source = "pipeline:timeout" if outcome.timed_out else "pipeline:worker"
        out[outcome.key] = DimResult.error_result(outcome.key, outcome.error, source=source).to_dict()
        marker = "timeout" if outcome.timed_out else "error"
        print(f"    {marker:7s} {outcome.key:20s} {outcome.error[:80]}")
        return
    dim_key, result_dict, top_level = outcome.value
    out[dim_key] = result_dict
    for key, value in top_level.items():
        out[key] = value
    quality = (result_dict.get("_pipeline") or {}).get("quality", "?")
    print(f"    ok      {dim_key:20s} {quality}")


def collect(ticker: Any, raw_previous: dict | None = None, max_workers: int = 6) -> dict[str, dict]:
    """主入口 · 返老格式 dict · 兼容 run_real_test 下游消费.

    raw_previous · 用于 resume 模式 · 已有缓存的 dim 跳过.

    max_workers=6 默认 · mini_racer fetcher 按 serial_group 串行.

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

    # v3.9.x · 按 analysis_profile 裁剪 fetcher 集合。
    # 此前 collect 完全没接 profile：--depth lite 声明只跑 7 维，这里却把注册表里
    # 22 个 fetcher 全跑了一遍，档位对采集阶段完全失效（实测 lite 仍跑 22 维）。
    enabled_dims, governed_dims = _dim_scope()

    def _in_scope(dim_key: str) -> bool:
        if enabled_dims is None or dim_key in enabled_dims:
            return True
        # 不在任何档位声明范围内 → 不归档位管辖（顶层字段提供者），照跑
        return dim_key not in governed_dims

    # Wave 1 · 0_basic 必须先跑
    basic_fetcher = get_fetcher("0_basic")
    basic_dim = raw_previous.get("dimensions", {}).get("0_basic")
    if basic_dim and _is_resume_valid(basic_dim, ttl_sec=_cache_ttl(basic_fetcher)):
        print("  [pipeline] 0_basic · resume cache")
        out["0_basic"] = basic_dim
    else:
        print("  [pipeline] wave 1 · 0_basic", end="", flush=True)
        t_w1 = time.time()
        fetcher_timeout = _positive_env_float("UZI_PIPELINE_FETCHER_TIMEOUT", 120.0)
        outcome = run_process_jobs(
            [ProcessJob("0_basic", _run_fetcher_job, ("0_basic", ticker), timeout_sec=fetcher_timeout)],
            max_workers=1,
            overall_timeout=fetcher_timeout,
        )[0]
        _apply_outcome(out, outcome)
        print(f"  [pipeline] wave 1 完成 ({time.time()-t_w1:.1f}s)")

    # Wave 2 · 非依赖型 fetcher 并发
    non_dep_dims = [d for d in FETCHER_REGISTRY.keys()
                    if d not in DEPENDENT_DIMS and d != "0_basic" and _in_scope(d)]
    print(f"  [pipeline] wave 2 · {len(non_dep_dims)} fetcher (max_workers={max_workers})")

    if enabled_dims is not None:
        skipped_dims = sorted(d for d in FETCHER_REGISTRY
                              if d != "0_basic" and not _in_scope(d))
        if skipped_dims:
            print(f"  [pipeline] 档位裁剪 · 跳过 {len(skipped_dims)} 维: "
                  f"{', '.join(skipped_dims)}")

    jobs: list[ProcessJob] = []
    fetcher_timeout = _positive_env_float("UZI_PIPELINE_FETCHER_TIMEOUT", 120.0)
    for dim_key in non_dep_dims:
        fetcher = get_fetcher(dim_key)
        if not fetcher:
            out[dim_key] = DimResult.empty(dim_key).to_dict()
            continue
        cached = raw_previous.get("dimensions", {}).get(dim_key)
        if cached and _is_resume_valid(cached, ttl_sec=_cache_ttl(fetcher)):
            out[dim_key] = cached
            continue
        legacy_mod = getattr(fetcher, "_legacy_module", "")
        jobs.append(ProcessJob(
            key=dim_key,
            target=_run_fetcher_job,
            args=(dim_key, ticker),
            timeout_sec=fetcher_timeout,
            serial_group="mini_racer" if legacy_mod in _MINI_RACER_LEGACY_MODULES else None,
        ))

    # 构造 raw dict 给 args_fn 用（部分 fetcher 需要从 0_basic 拿 industry）
    # 但 wave 2 的 non-dependent 不需要 raw · 此处简化
    wave_timeout = _positive_env_float("UZI_PIPELINE_WAVE_TIMEOUT", 300.0)
    for outcome in run_process_jobs(jobs, max_workers=max_workers, overall_timeout=wave_timeout):
        _apply_outcome(out, outcome)

    # Wave 3 · 依赖 industry 的 fetcher · 串行（industry 是 shared context）
    print(f"  [pipeline] wave 3 · {len(DEPENDENT_DIMS)} dependent fetcher")
    # 构造 raw-shaped dict 给 args_fn
    raw_for_deps = {"0_basic": out["0_basic"]}
    # v3.9.4 · 9_futures 依赖 8_materials 的 materials_detail（识别原材料期货品种）· 一并传入
    if "8_materials" in out:
        raw_for_deps["8_materials"] = out["8_materials"]
    if "1_financials" in out:
        raw_for_deps["1_financials"] = out["1_financials"]
    dependent_jobs: list[ProcessJob] = []
    for dim_key in sorted(DEPENDENT_DIMS):
        if not _in_scope(dim_key):
            continue
        fetcher = get_fetcher(dim_key)
        if not fetcher:
            continue
        cached = raw_previous.get("dimensions", {}).get(dim_key)
        if cached and _is_resume_valid(cached, ttl_sec=_cache_ttl(fetcher)):
            out[dim_key] = cached
            continue
        legacy_mod = getattr(fetcher, "_legacy_module", "")
        dependent_jobs.append(ProcessJob(
            key=dim_key,
            target=_run_fetcher_job,
            args=(dim_key, ticker, raw_for_deps),
            timeout_sec=fetcher_timeout,
            serial_group="mini_racer" if legacy_mod in _MINI_RACER_LEGACY_MODULES else None,
        ))
    for outcome in run_process_jobs(dependent_jobs, max_workers=1, overall_timeout=wave_timeout):
        _apply_outcome(out, outcome)

    print(f"  [pipeline] collect 完成 · {time.time()-t0:.1f}s")
    return out


def _is_resume_valid(dim_dict: dict, ttl_sec: int | None = None, now: float | None = None) -> bool:
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
    if not data:
        return False
    if ttl_sec is None:
        return True
    fetched_at = pp.get("fetched_at") or dim_dict.get("fetched_at")
    try:
        fetched_at = float(fetched_at)
    except (TypeError, ValueError):
        return False
    current_time = time.time() if now is None else now
    return 0 <= current_time - fetched_at <= ttl_sec


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
            actual_source = result.get("source") or f"legacy:{fetcher._legacy_module}"
            legacy_error = result.get("error")
        elif isinstance(result, dict):
            raw_data = result
            actual_source = f"legacy:{fetcher._legacy_module}"
            legacy_error = None
        else:
            raw_data = {}
            actual_source = f"legacy:{fetcher._legacy_module}"
            legacy_error = None
    except Exception as e:
        return DimResult.error_result(
            fetcher.spec.dim_key,
            error=f"{type(e).__name__}: {str(e)[:100]}",
            source=f"legacy:{fetcher._legacy_module}",
        )

    if legacy_error and not raw_data:
        return DimResult.error_result(
            fetcher.spec.dim_key,
            error=str(legacy_error),
            source=actual_source,
        )

    # 规约 + 校验（复用 BaseFetcher 逻辑）
    from .validators import normalize_data, validate_result
    normalized = normalize_data(raw_data, keep_zero_fields=fetcher.keep_zero_fields)
    top_level = fetcher.extract_top_level(normalized)
    dim_result = DimResult(
        dim_key=fetcher.spec.dim_key,
        data={k: v for k, v in normalized.items() if k not in top_level},
        source=actual_source,
        top_level_fields=top_level,
        latency_ms=int((_time.time() - t0) * 1000),
        fetched_at=_time.time(),
    )
    return validate_result(dim_result, fetcher.spec)
