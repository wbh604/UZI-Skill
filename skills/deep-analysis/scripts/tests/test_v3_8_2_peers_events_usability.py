from __future__ import annotations

import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def test_fast_basic_timeout_uses_local_identity(monkeypatch):
    import lib.fast_basic as fb
    from lib.market_router import parse_ticker

    monkeypatch.setenv("UZI_BASIC_FETCH_TIMEOUT", "0.01")
    monkeypatch.setattr(fb.ds, "fetch_basic", lambda _ti: time.sleep(60))

    basic = fb.fetch_basic_fast(parse_ticker("600036.SH"))

    assert basic["name"] == "\u62db\u5546\u94f6\u884c"
    assert basic["industry"] == "\u94f6\u884c"
    assert basic["_basic_fast_fallback"].startswith("timeout")


def test_fetch_peers_uses_static_industry_fallback_when_push2_is_disabled(monkeypatch):
    import fetch_peers

    monkeypatch.delenv("UZI_PEERS_TRY_AK", raising=False)
    monkeypatch.setattr(fetch_peers.ds, "fetch_basic", lambda _ti: {
        "code": "600036.SH",
        "name": "\u62db\u5546\u94f6\u884c",
        "industry": "\u94f6\u884c",
        "pe_ttm": 5.9,
        "pb": 0.79,
    })
    monkeypatch.setattr(
        fetch_peers.ak,
        "stock_board_industry_cons_em",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("push2 should be opt-in")),
    )

    result = fetch_peers.main("600036.SH")
    data = result["data"]

    assert result["fallback"] is True
    assert "local_static_peers" in result["source"]
    assert len(data["peer_table"]) > 1
    assert data["peer_table"][0]["code"] == "600036.SH"
    assert data["peer_table"][0]["is_self"] is True
    assert any(row["code"] == "601398.SH" for row in data["peer_table"])


def test_eastmoney_disclosures_convert_news_items(monkeypatch):
    import fetch_events
    import lib.news_providers as np
    from lib.news_providers import NewsItem

    monkeypatch.setattr(np, "fetch_em_stock_ann", lambda stock_code, limit=20: [
        NewsItem(
            source="em_stock_ann",
            title="\u62db\u5546\u94f6\u884c\u5e74\u5ea6\u6743\u76ca\u5206\u6d3e\u5b9e\u65bd\u516c\u544a",
            url="https://example.test/ann",
            publish_time="2026-07-01 18:00:00",
        )
    ])

    rows = fetch_events._eastmoney_disclosures("600036")

    assert rows == [{
        "date": "2026-07-01",
        "title": "\u62db\u5546\u94f6\u884c\u5e74\u5ea6\u6743\u76ca\u5206\u6d3e\u5b9e\u65bd\u516c\u544a",
        "url": "https://example.test/ann",
        "type": "eastmoney \u516c\u544a",
    }]


def test_em_stock_ann_queries_stock_list(monkeypatch):
    import json
    import lib.news_providers as np

    seen = {}

    def fake_http_get(url, timeout=20):
        seen["url"] = url
        return json.dumps({
            "data": {"list": [{
                "title": "\u62db\u5546\u94f6\u884c\u516c\u544a",
                "notice_date": "2026-06-27 00:00:00",
                "art_code": "AN1",
                "codes": [{"stock_code": "600036"}],
            }]}
        })

    monkeypatch.setattr(np, "_cache_get", lambda _key: None)
    monkeypatch.setattr(np, "_cache_set", lambda *_a, **_k: None)
    monkeypatch.setattr(np, "_http_get", fake_http_get)

    items = np.fetch_em_stock_ann("600036", limit=5)

    assert "stock_list=600036" in seen["url"]
    assert len(items) == 1
    assert items[0].title == "\u62db\u5546\u94f6\u884c\u516c\u544a"


def test_news_multi_source_does_not_match_generic_company_suffix(monkeypatch):
    import lib.news_providers as np
    from lib.news_providers import NewsItem

    monkeypatch.setattr(np, "fetch_jin10", lambda limit=20: [])
    monkeypatch.setattr(np, "fetch_em_stock_ann", lambda stock_code="", limit=20: [])
    monkeypatch.setattr(np, "fetch_ths_news_today", lambda limit=20: [])
    monkeypatch.setattr(np, "fetch_em_kuaixun", lambda limit=20: [
        NewsItem(source="em_kuaixun", title="\u7f8e\u56fd\u94f6\u884c\uff1a\u7f8e\u56fd\u80a1\u5e02\u8d44\u91d1\u6d41\u51fa"),
        NewsItem(source="em_kuaixun", title="\u62db\u5546\u94f6\u884c\u53d1\u5e03\u6700\u65b0\u4e1a\u52a1\u52a8\u6001"),
    ])

    result = np.get_news_multi_source(stock_code="600036", stock_name="\u62db\u5546\u94f6\u884c", limit_per_source=5)
    titles = [row["title"] for row in result["sources"]["em_kuaixun"]]

    assert "\u62db\u5546\u94f6\u884c\u53d1\u5e03\u6700\u65b0\u4e1a\u52a1\u52a8\u6001" in titles
    assert not any(title.startswith("\u7f8e\u56fd\u94f6\u884c") for title in titles)


def test_fetch_events_skips_ddgs_by_default_and_uses_eastmoney_notices(monkeypatch):
    import fetch_events
    import lib.data_sources as ds
    import lib.news_providers as np

    monkeypatch.delenv("UZI_EVENTS_WEB_SEARCH", raising=False)
    monkeypatch.delenv("UZI_EVENTS_AK_NEWS", raising=False)
    monkeypatch.setattr(ds, "fetch_basic", lambda _ti: {"name": "\u62db\u5546\u94f6\u884c"})
    monkeypatch.setattr(fetch_events, "_cninfo_disclosures", lambda _code: [])
    monkeypatch.setattr(fetch_events, "_try_news", lambda _code: (_ for _ in ()).throw(
        AssertionError("ak stock_news_em should be opt-in")
    ))
    monkeypatch.setattr(fetch_events, "_eastmoney_disclosures", lambda _code: [{
        "date": "2026-07-01",
        "title": "\u62db\u5546\u94f6\u884c\u5e74\u5ea6\u6743\u76ca\u5206\u6d3e\u5b9e\u65bd\u516c\u544a",
        "type": "eastmoney \u516c\u544a",
        "url": "https://example.test/ann",
    }])
    monkeypatch.setattr(fetch_events, "_web_search_events", lambda _name: (_ for _ in ()).throw(
        AssertionError("ddgs web search should be opt-in")
    ))
    monkeypatch.setattr(np, "get_news_multi_source", lambda **_kw: {
        "sources": {},
        "total_hits": 0,
        "sources_ok": 0,
    })

    result = fetch_events.main("600036.SH")
    data = result["data"]

    assert data["disclosures_count"] == 1
    assert data["recent_notices"][0]["type"] == "eastmoney \u516c\u544a"
    assert data["event_timeline"]
