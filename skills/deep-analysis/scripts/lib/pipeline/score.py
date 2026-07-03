"""pipeline.score · Scoring 阶段 · v3.0.0 Phase 6c · 真正接管主干.

### 相比 Phase 6a delegate 的区别

Phase 6a 做法：调 `rrt.stage1(ticker)` → stage1 内部 **重新 collect** 数据 + scoring · pipeline
只是薄包装 · 职责没转移.

Phase 6c 做法：pipeline 已经 collect 完 · 写了 raw_data.json · **只调 rrt 里的纯打分函数**
(score_dimensions / generate_panel / generate_synthesis / _autofill_qualitative_via_mx) ·
rrt.stage1 不再被 pipeline 调用 · pipeline 才是真正的主干.

依赖的 legacy 纯函数（无副作用 · 稳定 API）：
- `rrt.score_dimensions(raw) -> dims_scored`
- `rrt.generate_panel(dims_scored, raw) -> panel`
- `rrt.generate_synthesis(raw, dims_scored, panel, agent_analysis=None) -> synthesis`
- `rrt._autofill_qualitative_via_mx(raw, ticker)` (原地改 raw)

这些函数在 legacy 里也被 stage1 调用 · pipeline 调等价于 stage1 的 scoring 段 · 业务零差别.
"""
from __future__ import annotations

import json
from pathlib import Path


def score_from_cache(ticker: str) -> dict:
    """给定已有 .cache/<ticker>/raw_data.json · 执行 scoring · 落地 dimensions/panel/synthesis.

    流程（纯函数编排 · 不再调 stage1）：
      1. 读 raw_data.json
      2. _autofill_qualitative_via_mx · MX API 补齐定性维度（原地改 raw）
      3. autofill_via_playwright · v2.13 Playwright 兜底（原地改 raw）
      4. score_dimensions · 22 维打分
      5. generate_panel · 51 评委投票
      6. generate_synthesis · DCF/LBO/BCG/Porter
      7. 写 dimensions.json / panel.json / synthesis.json
    返回 {"dimensions": ..., "panel": ..., "synthesis": ...}
    """
    import run_real_test as rrt
    from lib.market_router import parse_ticker

    ti = parse_ticker(ticker)
    cache_dir = Path(rrt.__file__).parent / ".cache" / ti.full
    raw_path = cache_dir / "raw_data.json"
    if not raw_path.exists():
        raise FileNotFoundError(
            f"pipeline.score_from_cache: {raw_path} 不存在 · 必须先跑 pipeline.collect"
        )

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    try:
        from lib.local_data_repair import enrich_raw_data_from_local_cache
        enrich_raw_data_from_local_cache(raw)
    except Exception as e:
        print(f"   ⚠️ local_data_repair 跳过: {type(e).__name__}: {str(e)[:80]}")

    # v2.6.1 · MX API 兜底补齐定性维度（原地改 raw · 不 raise）
    try:
        rrt._autofill_qualitative_via_mx(raw, ti.full)
    except Exception as e:
        print(f"   ⚠️ autofill_via_mx 跳过: {type(e).__name__}: {str(e)[:80]}")

    # v2.13 · Playwright 兜底（按 profile 决策 · 默认 lite 不启用）
    try:
        from lib.playwright_fallback import autofill_via_playwright
        autofill_via_playwright(raw, ti.full)
    except Exception as e:
        print(f"   ⚠️ Playwright 兜底跳过: {type(e).__name__}: {str(e)[:80]}")

    # 重新写回 raw_data.json（autofill 已修改）
    raw_path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # 22 维 scoring
    dims_scored = rrt.score_dimensions(raw)
    (cache_dir / "dimensions.json").write_text(
        json.dumps(dims_scored, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # 51 评委 panel
    panel = rrt.generate_panel(dims_scored, raw)
    (cache_dir / "panel.json").write_text(
        json.dumps(panel, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # Synthesis（不 merge agent_analysis · stage2/synthesize_and_render 阶段做）
    synthesis = rrt.generate_synthesis(raw, dims_scored, panel, agent_analysis=None)
    (cache_dir / "synthesis.json").write_text(
        json.dumps(synthesis, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    return {
        "dimensions": dims_scored,
        "panel": panel,
        "synthesis": synthesis,
    }


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
