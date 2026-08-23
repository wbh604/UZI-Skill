"""Regression tests for the optional Xquik sentiment source."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def test_build_stock_query_uses_cashtag_for_us_stocks():
    from lib.xquik_sentiment import build_stock_query

    assert build_stock_query("AAPL", "Apple Inc.", "U") == '"Apple Inc." OR $AAPL'
    assert build_stock_query("600519", "贵州茅台", "A") == '"贵州茅台" OR "600519"'


def test_xquik_is_registered_for_sentiment():
    from lib.data_source_registry import by_id

    source = by_id("xquik_x_search")

    assert source is not None
    assert source.dims == ("17_sentiment",)
    assert source.tier == 1


def test_fetch_x_sentiment_stays_disabled_without_api_key(monkeypatch):
    from lib.xquik_sentiment import fetch_x_sentiment

    monkeypatch.delenv("X_TWITTER_SCRAPER_API_KEY", raising=False)

    def unexpected_client(**_kwargs):
        raise AssertionError("client should not be created")

    result = fetch_x_sentiment("$AAPL", client_factory=unexpected_client)

    assert result == {
        "status": "not_configured",
        "query": "$AAPL",
        "total_hits": 0,
        "snippets": [],
    }


def test_fetch_x_sentiment_normalizes_and_closes_client():
    from lib.xquik_sentiment import fetch_x_sentiment

    calls: dict = {}
    tweet = SimpleNamespace(
        id="123",
        text="Bullish demand signal",
        url=None,
        author=SimpleNamespace(username="analyst"),
    )

    class FakeTweets:
        def search(self, **kwargs):
            calls["search"] = kwargs
            return SimpleNamespace(tweets=[tweet])

    class FakeClient:
        def __init__(self):
            self.x = SimpleNamespace(tweets=FakeTweets())

        def close(self):
            calls["closed"] = True

    def client_factory(**kwargs):
        calls["client"] = kwargs
        return FakeClient()

    result = fetch_x_sentiment("$AAPL", api_key="test-key", limit=100, client_factory=client_factory)

    assert calls["client"] == {"api_key": "test-key", "max_retries": 1, "timeout": 12.0}
    assert calls["search"] == {"q": "$AAPL", "limit": 50, "query_type": "Latest"}
    assert calls["closed"] is True
    assert result["status"] == "ok"
    assert result["snippets"] == [{
        "title": "@analyst",
        "body": "Bullish demand signal",
        "url": "https://x.com/i/status/123",
    }]


def test_fetch_x_sentiment_reports_error_type_without_message():
    from lib.xquik_sentiment import fetch_x_sentiment

    def failing_client(**_kwargs):
        raise RuntimeError("sensitive-detail-should-not-escape")

    result = fetch_x_sentiment("$AAPL", api_key="test-key", client_factory=failing_client)

    assert result["status"] == "error"
    assert result["error_type"] == "RuntimeError"
    assert "sensitive-detail-should-not-escape" not in str(result)


def test_fetch_sentiment_includes_configured_x_evidence(monkeypatch):
    import fetch_sentiment
    import lib.hottrend as hottrend
    import lib.news_providers as news

    monkeypatch.setattr(fetch_sentiment.ds, "fetch_basic", lambda _ticker: {"name": "Apple Inc."})
    monkeypatch.setattr(fetch_sentiment, "search", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(hottrend, "get_hot_mentions", lambda _name: {"total_hits": 0})
    monkeypatch.setattr(news, "get_news_multi_source", lambda **_kwargs: {"total_hits": 0, "sources": {}})
    monkeypatch.setattr(fetch_sentiment, "fetch_x_sentiment", lambda query: {
        "status": "ok",
        "query": query,
        "total_hits": 1,
        "snippets": [{
            "title": "@analyst",
            "body": "Bullish outlook with upside",
            "url": "https://x.com/analyst/status/123",
        }],
    })

    result = fetch_sentiment.main("AAPL")
    data = result["data"]

    assert data["xquik_status"] == "ok"
    assert data["platform_hits"]["x"] == 1
    assert data["platform_snippets"]["x"][0]["body"] == "Bullish outlook with upside"
    assert data["sentiment_data_available"] is True
    assert data["sentiment_label"] == "乐观"
    assert "Xquik X search" in result["source"]
