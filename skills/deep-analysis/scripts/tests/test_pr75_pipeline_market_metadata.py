"""Regression for PR #75 · pipeline raw cache 保留 market/code/full.

背景 (contributor constansino)：
pipeline 路径写 raw_data.json 时只写 ticker + dimensions，丢了顶层
market/code/full。下游 self_review / stock_features 用 raw.get("market", "A")
→ NOK / AAPL / 港股等非 A 股标的被误判为 A 股 → 误触雪球/东财/A股龙虎榜/cninfo
兜底路径，产生大量假缺口。

修复：lib/pipeline/run.py 组装 raw_data_compatible 时写入 market/code/full
（market 优先 0_basic.market · 否则 parse_ticker 兜底），与 legacy 路径对齐。

测试覆盖：
1. parse_ticker 市场约定 (NOK/AAPL→U · HK→H · A股→A) · PR 依赖此约定
2. 行为测试：mock 重函数 · run_pipeline 写入的 raw 含正确 market/code/full
3. 0_basic.market 优先级高于 parse_ticker 兜底
4. 结构守护：run.py 源码确实写 market/code/full（防回归被还原）
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


# ─── #1 · parse_ticker 市场约定 (PR 依赖) ────────────────

def test_parse_ticker_market_convention():
    from lib.market_router import parse_ticker
    assert parse_ticker("NOK").market == "U"
    assert parse_ticker("AAPL").market == "U"
    assert parse_ticker("00700.HK").market == "H"
    assert parse_ticker("600519.SH").market == "A"
    assert parse_ticker("300470.SZ").market == "A"


# ─── #2 · 行为测试 · run_pipeline 保留 market ────────────

def _patch_pipeline(monkeypatch, collect_ret):
    """把 run_pipeline 的重函数都 mock 成 no-op · 只捕获写 cache 的 raw."""
    from lib.pipeline import run as run_mod
    captured = {}
    monkeypatch.setattr(run_mod, "_preflight_guards", lambda t: None)
    monkeypatch.setattr(run_mod, "_load_cache", lambda t: {})
    monkeypatch.setattr(run_mod, "pipeline_collect", lambda *a, **k: collect_ret)
    monkeypatch.setattr(run_mod, "_write_cache", lambda ticker, raw: captured.update(raw))
    monkeypatch.setattr(run_mod, "score_from_cache", lambda t: None)
    monkeypatch.setattr(run_mod, "synthesize_and_render", lambda t: "/fake/report.html")
    return run_mod, captured


def test_pipeline_preserves_market_us_ticker(monkeypatch):
    """NOK (ADR) · 0_basic 无 market → 回退 parse_ticker → market=U (不被当 A 股)."""
    run_mod, captured = _patch_pipeline(monkeypatch, {"0_basic": {}})
    run_mod.run_pipeline("NOK", resume=False)
    assert captured["market"] == "U", "NOK 必须是 U · 否则会走 A 股兜底路径"
    assert captured["code"] == "NOK"
    assert captured["full"] == "NOK"
    # dimensions 仍保留
    assert "dimensions" in captured


def test_pipeline_preserves_market_hk_ticker(monkeypatch):
    run_mod, captured = _patch_pipeline(monkeypatch, {"0_basic": {}})
    run_mod.run_pipeline("00700.HK", resume=False)
    assert captured["market"] == "H"
    assert captured["full"] == "00700.HK"


def test_pipeline_a_share_still_a(monkeypatch):
    """A 股不受影响 · 仍是 A."""
    run_mod, captured = _patch_pipeline(monkeypatch, {"0_basic": {}})
    run_mod.run_pipeline("600519.SH", resume=False)
    assert captured["market"] == "A"


# ─── #3 · 0_basic.market 优先级 ──────────────────────────

def test_basic_market_takes_priority_over_parse_ticker(monkeypatch):
    """若 0_basic 已带 market (真实数据) · 优先用它 · 不被 parse_ticker 覆盖."""
    # ticker 字面像 A 股代码 · 但 basic 明确说是 U → 应信 basic
    run_mod, captured = _patch_pipeline(monkeypatch, {"0_basic": {"market": "U"}})
    run_mod.run_pipeline("300470.SZ", resume=False)
    assert captured["market"] == "U", "0_basic.market 应优先于 parse_ticker"


def test_invalid_basic_market_falls_back(monkeypatch):
    """0_basic.market 是非法值 (不在 A/H/U) · 回退 parse_ticker."""
    run_mod, captured = _patch_pipeline(monkeypatch, {"0_basic": {"market": "XYZ"}})
    run_mod.run_pipeline("600519.SH", resume=False)
    assert captured["market"] == "A"


# ─── #4 · 结构守护 (防 PR 被还原) ────────────────────────

def test_run_py_writes_market_code_full():
    src = (SCRIPTS / "lib" / "pipeline" / "run.py").read_text(encoding="utf-8")
    assert '"market":' in src, "run.py 必须写顶层 market (PR #75)"
    assert '"code":' in src
    assert '"full":' in src
    # default=str 防 datetime 序列化崩溃
    assert "default=str" in src or "default=_default" in src
