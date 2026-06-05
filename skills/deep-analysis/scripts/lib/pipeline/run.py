"""pipeline.run · 编排入口 · collect → score → synthesize.

**v3.0.0 默认路径**：`run.py <ticker>` 默认走这里。`UZI_LEGACY=1` 才走 legacy.

用法：
    from lib.pipeline.run import run_pipeline
    report_path = run_pipeline("300470.SZ")
"""
from __future__ import annotations

import json
from pathlib import Path

from .collect import collect as pipeline_collect
from .score import score_from_cache
from .synthesize import synthesize_and_render


def run_pipeline(ticker: str, resume: bool = True) -> str:
    """完整管道入口（v3.0.0 主干）.

    1. pipeline.collect · 用 22 BaseFetcher adapter 并发抓数据（max_workers=6）
    2. 写 .cache/<ticker>/raw_data.json（与 legacy schema 兼容）
    3. pipeline.score_from_cache · 直接调 rrt 纯函数（score_dimensions / generate_panel /
       generate_synthesis）· 不再调 stage1（stage1 会重新 collect）
    4. pipeline.synthesize_and_render · 调 stage2（stage2 只读 cache 不 collect · OK）

    Phase 6c 升级：score 阶段解耦 legacy stage1 · 不再重复 collect · 省 5-10 min/股.
    """
    # v3.0.0 · pre-flight guards · 不兼容场景抛异常让 run.py fallback legacy（legacy 有完整解析）
    _preflight_guards(ticker)

    print(f"🚀 [pipeline.run] collect · {ticker}")
    raw_previous = _load_cache(ticker) if resume else {}
    raw_dict = pipeline_collect(ticker, raw_previous=raw_previous, max_workers=6)

    # 组装 legacy 兼容 raw_data.json（dimensions + 顶层溢出字段）
    # v3.7.2 hotfix: 必须保留顶层 market/code/full。否则 US/HK 标的在 self_review/stock_features
    # 里会因 raw.get("market", "A") 被误判为 A 股，导致雪球/东财/A股龙虎榜等兜底路径乱跑，
    # 最终出现 NOK 这类 ADR 被当 A 股检查的假缺口。
    from lib.market_router import parse_ticker as _parse_ticker
    _ti = _parse_ticker(ticker)
    _basic = raw_dict.get("0_basic") or {}
    _basic_market = _basic.get("market") if isinstance(_basic, dict) else None
    raw_data_compatible = {
        "ticker": ticker,
        "market": _basic_market if _basic_market in ("A", "H", "U") else _ti.market,
        "code": _ti.code,
        "full": _ti.full,
        "dimensions": {k: v for k, v in raw_dict.items()
                       if k not in ("fund_managers", "similar_stocks")},
    }
    for k in ("fund_managers", "similar_stocks"):
        if k in raw_dict:
            raw_data_compatible[k] = raw_dict[k]

    _write_cache(ticker, raw_data_compatible)
    print(f"✅ [pipeline.run] raw_data.json 已写 · 进入 scoring 段（v3.0 纯函数编排）")

    # pipeline.score_from_cache · 直接调 rrt.score_dimensions/generate_panel/generate_synthesis
    # 不再走 rrt.stage1（stage1 会重新 collect · 浪费时间）
    score_from_cache(ticker)
    return synthesize_and_render(ticker)


def _preflight_guards(ticker: str) -> None:
    """v3.0.0 · pipeline 不覆盖的场景 · 抛异常让 run.py 回退 legacy.

    抛 ValueError 触发 fallback（不 crash · run.py catch 后走 legacy stage1 能正常处理）.
    """
    from lib.market_router import is_chinese_name, parse_ticker, classify_security_type

    # 1. 中文名 · 由 legacy stage1 的 resolve_chinese_name_rich 处理
    if is_chinese_name(ticker):
        raise ValueError(
            f"pipeline: 中文名 {ticker!r} 需 legacy 解析 · fallback"
        )

    # 2. ETF / LOF / 可转债 · legacy stage1 有完整 guidance
    try:
        ti = parse_ticker(ticker)
        if ti.market == "A":
            sec_type = classify_security_type(ti.code)
            if sec_type in ("etf", "lof", "convertible_bond", "index"):
                raise ValueError(
                    f"pipeline: {sec_type} 证券类型需 legacy 处理 · fallback"
                )
    except ValueError:
        raise  # 重新抛 · 让 run.py fallback
    except Exception:
        pass  # 其他异常（parse 失败）· 让 pipeline 自己尝试 · 失败后再 fallback


def _load_cache(ticker: str) -> dict:
    """读已有 raw_data.json · 用于 resume."""
    from lib.market_router import parse_ticker
    ti = parse_ticker(ticker)
    import run_real_test as rrt
    cache_path = Path(rrt.__file__).parent / ".cache" / ti.full / "raw_data.json"
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_cache(ticker: str, raw: dict) -> None:
    """写 raw_data.json · 让 legacy stage1 的 resume 能复用."""
    from lib.market_router import parse_ticker
    ti = parse_ticker(ticker)
    import run_real_test as rrt
    cache_dir = Path(rrt.__file__).parent / ".cache" / ti.full
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "raw_data.json"
    try:
        cache_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        print(f"   ⚠️ 写 cache 失败: {e}")
