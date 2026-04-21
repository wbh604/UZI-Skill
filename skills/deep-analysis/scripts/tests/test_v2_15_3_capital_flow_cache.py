"""Regression for v2.15.3 · fetch_capital_flow universe-level cache 修严重性能 bug.

背景：原 fetch_capital_flow 每股分析都重抓全 A 大宗/解禁/融资数据集（全年或近一年），
导致每股 3+ min · 多股批量分析几小时完不了.

修法：module-level universe cache · 24h TTL · 全股票共享.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def test_universe_cache_functions_exist():
    """v2.15.3 · 4 个 universe helper 必须存在."""
    import fetch_capital_flow as fcf
    assert callable(fcf._universe_dzjy)
    assert callable(fcf._universe_release_summary)
    assert callable(fcf._universe_release_detail)
    assert callable(fcf._universe_margin_detail)


def test_universe_cache_keys_use_universe_ticker():
    """universe cache 应用 '_universe' 作 ticker 共享 · 不是 per-stock."""
    src = (SCRIPTS / "fetch_capital_flow.py").read_text(encoding="utf-8")
    assert 'cached("_universe"' in src, "universe cache 必须用 '_universe' 作 ticker key · 实现跨股共享"
    assert '_UNIVERSE_TTL = 24 * 3600' in src or '_UNIVERSE_TTL=24*3600' in src.replace(" ", "")


def test_universe_cache_hit_is_fast(monkeypatch, tmp_path):
    """universe cache 命中时调用必须 < 0.1s · 不触发 akshare 真实请求."""
    import fetch_capital_flow as fcf
    from lib import cache as cache_mod

    # 第一次调：mock fetch_fn 让它记到 cache
    calls = {"dzjy": 0}
    import akshare as ak
    original_dzjy = ak.stock_dzjy_mrtj
    def fake_dzjy(start_date, end_date):
        calls["dzjy"] += 1
        import pandas as pd
        return pd.DataFrame([
            {"证券代码": "002217", "成交金额": 100, "日期": "2026-01-01"},
            {"证券代码": "600519", "成交金额": 500, "日期": "2026-01-02"},
        ])
    monkeypatch.setattr(ak, "stock_dzjy_mrtj", fake_dzjy)
    # 独立 cache 目录避免污染
    monkeypatch.setattr(cache_mod, "CACHE_ROOT", tmp_path / ".cache")

    # 第一次：触发 fetch
    t0 = time.time()
    r1 = fcf._universe_dzjy(2026)
    dt1 = time.time() - t0
    assert calls["dzjy"] == 1, "首次必须调 akshare"
    assert len(r1) == 2

    # 第二次：命中 cache · 必须秒回 · 不再调 akshare
    t0 = time.time()
    r2 = fcf._universe_dzjy(2026)
    dt2 = time.time() - t0
    assert calls["dzjy"] == 1, "二次不该再调 akshare · cache 命中"
    assert dt2 < 0.1, f"cache 命中应 < 0.1s · 实际 {dt2:.3f}s"
    assert r2 == r1


def test_block_trades_filter_uses_universe_not_refetch(monkeypatch):
    """main() 里 block_trades 必须从 universe cache filter · 不能每次调 stock_dzjy_mrtj."""
    src = (SCRIPTS / "fetch_capital_flow.py").read_text(encoding="utf-8")
    # 不允许 main 里直接调 ak.stock_dzjy_mrtj（除了 universe helper 里面）
    # main 函数的 block_trades 段应该用 _universe_dzjy
    assert "_universe_dzjy" in src, "main() 必须用 _universe_dzjy helper"
    # 老写法不应再出现在 main 里
    main_start = src.find("def main(")
    main_section = src[main_start:main_start + 5000]
    assert "stock_dzjy_mrtj" not in main_section, "main() 里不允许直调 stock_dzjy_mrtj · 必须走 _universe_dzjy"


def test_unlock_filter_uses_universe(monkeypatch):
    """unlock / unlock_future 也必须走 universe cache."""
    src = (SCRIPTS / "fetch_capital_flow.py").read_text(encoding="utf-8")
    main_start = src.find("def main(")
    main_section = src[main_start:main_start + 5000]
    assert "stock_restricted_release_summary_em" not in main_section, "main 里不允许直调 release_summary · 必须走 _universe"
    assert "stock_restricted_release_detail_em" not in main_section, "main 里不允许直调 release_detail · 必须走 _universe"


def test_margin_uses_universe(monkeypatch):
    """融资明细也必须走 universe cache."""
    src = (SCRIPTS / "fetch_capital_flow.py").read_text(encoding="utf-8")
    main_start = src.find("def main(")
    main_section = src[main_start:main_start + 5000]
    assert "_universe_margin_detail" in main_section, "main 必须用 _universe_margin_detail"
