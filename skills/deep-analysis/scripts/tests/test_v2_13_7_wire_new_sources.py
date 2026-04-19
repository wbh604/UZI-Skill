"""Regression tests for v2.13.7 · 把 v2.13.4 / v2.13.6 新登记源真正接入 fetcher.

v2.13.4 / v2.13.6 只把新源加到 registry，实际 fetcher 还没用 ·
v2.13.7 在 fetch_events/sentiment/policy + data_sources._kline_*_chain
里加载 news_providers / yahoo_v8_chart / cfachina_titles 调用。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


# ─── news_providers 模块存在性 ───────────────────────────────────

def test_news_providers_module_exports():
    from lib import news_providers as np
    assert callable(np.fetch_jin10)
    assert callable(np.fetch_em_kuaixun)
    assert callable(np.fetch_em_stock_ann)
    assert callable(np.fetch_ths_news_today)
    assert callable(np.get_news_multi_source)


def test_news_providers_news_item_dataclass():
    from lib.news_providers import NewsItem
    item = NewsItem(source="jin10", title="x")
    assert item.source == "jin10"
    assert item.to_dict()["title"] == "x"


def test_get_news_multi_source_shape():
    """空 stock_name 时返所有源 · 结构校验（不保证网络可达）."""
    from lib import news_providers as np
    with patch.object(np, "_http_get", return_value=None):
        r = np.get_news_multi_source(stock_code="", stock_name="", limit_per_source=5)
    assert "sources" in r
    assert set(r["sources"].keys()) == {"jin10", "em_kuaixun", "em_stock_ann", "ths_news_today"}
    assert "total_hits" in r
    assert "sources_ok" in r


def test_jin10_parses_var_newest_js():
    """jin10 返 var newest = [...] JS 格式 · 测试解析."""
    from lib import news_providers as np
    fake_js = 'var newest = [{"data": {"title": "测试快讯", "content": "内容"}, "time": "2026-04-19 10:00"}];'
    # 绕过缓存
    with patch.object(np, "_cache_get", return_value=None), \
         patch.object(np, "_http_get", return_value=fake_js), \
         patch.object(np, "_cache_set"):
        items = np.fetch_jin10(limit=5)
    assert len(items) == 1
    assert items[0].source == "jin10"
    assert items[0].title == "测试快讯"


def test_em_kuaixun_parses_ajax_result():
    """em_kuaixun 返 var ajaxResult={...} JSON · 测试无尾 ; 也能解析."""
    from lib import news_providers as np
    fake_js = 'var ajaxResult={"LivesList":[{"title":"东财快讯","digest":"摘要","url_mobile":"http://x","showtime":"2026-04-19"}]}'
    with patch.object(np, "_cache_get", return_value=None), \
         patch.object(np, "_http_get", return_value=fake_js), \
         patch.object(np, "_cache_set"):
        items = np.fetch_em_kuaixun(limit=5)
    assert len(items) == 1
    assert items[0].title == "东财快讯"


# ─── fetch_events 接入 news_providers ───────────────────────────

def test_fetch_events_uses_news_providers(monkeypatch):
    """A 股 fetch_events 应调 news_providers.get_news_multi_source."""
    import fetch_events
    called = {"n": 0}

    def fake_multi(**kw):
        called["n"] += 1
        return {"sources": {"jin10": [{"title": "测试利好合同", "publish_time": "2026-04-19", "url": ""}]}, "total_hits": 1, "sources_ok": 1}

    # mock cninfo / news / search
    monkeypatch.setattr(fetch_events, "_cninfo_disclosures", lambda c: [])
    monkeypatch.setattr(fetch_events, "_try_news", lambda c: [])
    monkeypatch.setattr(fetch_events, "_web_search_events", lambda n: [])
    # 需要 patch 导入进去的 lib 层函数
    import lib.news_providers as np
    monkeypatch.setattr(np, "get_news_multi_source", fake_multi)
    # mock basic
    import lib.data_sources as ds
    monkeypatch.setattr(ds, "fetch_basic", lambda ti: {"name": "测试股"})

    r = fetch_events.main("002273.SZ")
    assert called["n"] >= 1
    # 应至少有 news_providers 来源
    sources = r.get("source", "")
    assert "news_providers" in sources


# ─── fetch_sentiment 接入 news_providers ────────────────────────

def test_fetch_sentiment_integrates_news_multi(monkeypatch):
    import fetch_sentiment
    import lib.news_providers as np
    import lib.data_sources as ds

    monkeypatch.setattr(ds, "fetch_basic", lambda ti: {"name": "测试股"})
    monkeypatch.setattr(fetch_sentiment, "search", lambda *a, **k: [])
    # mock hottrend
    monkeypatch.setattr("lib.hottrend.get_hot_mentions", lambda n: {"stock_name": n, "total_hits": 0})
    fake_multi = {"sources": {"jin10": [{"title": "利好", "body": "看好突破"}]}, "total_hits": 1, "sources_ok": 1}
    monkeypatch.setattr(np, "get_news_multi_source", lambda **kw: fake_multi)

    r = fetch_sentiment.main("002273.SZ")
    data = r["data"]
    assert "news_multi_source" in data
    assert data.get("news_sources_ok") == 1
    assert "news_providers" in r.get("source", "")


# ─── yahoo v8 chart fallback ────────────────────────────────────

def test_yahoo_v8_chart_parses_response():
    from lib.data_sources import _yahoo_v8_chart
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "chart": {"result": [{
            "timestamp": [1704067200, 1704153600],
            "indicators": {"quote": [{
                "open": [100.0, 101.0],
                "close": [101.5, 102.0],
                "high": [102.0, 103.0],
                "low": [99.5, 100.5],
                "volume": [1000, 1100],
            }]},
        }]},
    }
    with patch("lib.data_sources.requests.get", return_value=fake_resp):
        rows = _yahoo_v8_chart("AAPL", range_="5d")
    assert len(rows) == 2
    assert rows[0]["收盘"] == 101.5
    assert rows[1]["开盘"] == 101.0


def test_yahoo_v8_chart_retries_on_429():
    from lib.data_sources import _yahoo_v8_chart
    r429 = MagicMock(status_code=429)
    r_ok = MagicMock(status_code=200)
    r_ok.json.return_value = {
        "chart": {"result": [{"timestamp": [1704067200], "indicators": {"quote": [{
            "open": [1.0], "close": [2.0], "high": [3.0], "low": [0.5], "volume": [10],
        }]}}]}
    }
    seq = [r429, r_ok]
    with patch("lib.data_sources.requests.get", side_effect=lambda *a, **k: seq.pop(0)):
        rows = _yahoo_v8_chart("AAPL", range_="1d")
    assert len(rows) == 1
    assert rows[0]["收盘"] == 2.0


def test_kline_us_chain_falls_through_to_yahoo_v8(monkeypatch):
    """yf + ak 全失败时，应调 _yahoo_v8_chart."""
    import lib.data_sources as ds
    called = {"v8": 0}

    def fake_v8(sym, range_="2y"):
        called["v8"] += 1
        return [{"日期": "2026-04-19", "收盘": 100}]

    monkeypatch.setattr(ds, "_yahoo_v8_chart", fake_v8)
    # force yf / ak to fail
    monkeypatch.setattr(ds, "yf", None)
    monkeypatch.setattr(ds, "ak", None)

    ti = MagicMock(code="AAPL")
    rows = ds._kline_us_chain(ti)
    assert called["v8"] == 1
    assert rows[0]["收盘"] == 100


# ─── cfachina 接入 fetch_policy ─────────────────────────────────

def test_fetch_policy_futures_industry_calls_cfachina(monkeypatch):
    """期货/商品 industry 时，fetch_policy 应触发 _fetch_cfachina_titles."""
    import fetch_policy
    called = {"cfa": 0}

    def fake_cfa(limit=10):
        called["cfa"] += 1
        return [{"title": "期货监管公告", "body": "", "url": "x"}]

    monkeypatch.setattr(fetch_policy, "_fetch_cfachina_titles", fake_cfa)
    monkeypatch.setattr(fetch_policy, "search_trusted", lambda *a, **k: [])

    r = fetch_policy.main(industry="期货衍生品")
    assert called["cfa"] == 1
    assert r["data"]["cfachina_titles_count"] == 1
    assert "cfachina" in r["source"]


def test_fetch_policy_non_futures_skips_cfachina(monkeypatch):
    """非期货 industry（如光学光电子）不调 cfachina."""
    import fetch_policy
    called = {"cfa": 0}

    def fake_cfa(limit=10):
        called["cfa"] += 1
        return []

    monkeypatch.setattr(fetch_policy, "_fetch_cfachina_titles", fake_cfa)
    monkeypatch.setattr(fetch_policy, "search_trusted", lambda *a, **k: [])

    fetch_policy.main(industry="光学光电子")
    assert called["cfa"] == 0
