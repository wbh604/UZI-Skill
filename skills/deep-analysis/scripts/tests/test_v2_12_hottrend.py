"""Tests for v2.12.0 hottrend aggregation (抄自 jcp `internal/services/hottrend`).

All tests mock requests.get — zero network dependency. Validates:
1. Per-platform parser correctly extracts HotItem from mocked JSON
2. Cache write/read roundtrip
3. Single platform failure does not break others
4. get_hot_mentions correctly matches stock names
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from lib import hottrend  # noqa: E402
from lib.hottrend import (  # noqa: E402
    HotItem, HotTrendResult, SUPPORTED_PLATFORMS,
    fetch_weibo, fetch_zhihu, fetch_baidu, fetch_douyin, fetch_toutiao, fetch_bilibili,
    get_hot_trend, get_hot_mentions,
)


# ─── fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """每个测试独立 cache 目录，避免干扰."""
    monkeypatch.setattr(hottrend, "_cache_dir", lambda: tmp_path)
    return tmp_path


def _mock_response(json_data):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = json_data
    return resp


# ─── 平台 parser 测试 ───────────────────────────────────────────────

def test_weibo_parser_extracts_items(isolated_cache):
    mock_json = {
        "data": {
            "realtime": [
                {"word": "贵州茅台暴涨", "num": 123456, "category": "财经"},
                {"word": "腾讯裁员", "num": 98765, "category": "科技"},
            ]
        }
    }
    with patch("requests.get", return_value=_mock_response(mock_json)):
        items = fetch_weibo()
    assert len(items) == 2
    assert items[0].title == "贵州茅台暴涨"
    assert items[0].rank == 1
    assert items[0].hot_score == 123456
    assert items[0].platform == "weibo"
    assert "weibo.com" in items[0].url


def test_zhihu_parser_extracts_items(isolated_cache):
    mock_json = {
        "data": [
            {
                "target": {
                    "title": "茅台股价为什么跌",
                    "link": {"url": "https://zhihu.com/q/1"},
                    "metrics_area": {"text": "1000 万热度"},
                }
            }
        ]
    }
    with patch("requests.get", return_value=_mock_response(mock_json)):
        items = fetch_zhihu()
    assert len(items) == 1
    assert items[0].title == "茅台股价为什么跌"
    assert items[0].url == "https://zhihu.com/q/1"
    assert items[0].extra == "1000 万热度"


def test_baidu_parser_extracts_items(isolated_cache):
    mock_json = {
        "data": {
            "cards": [
                {
                    "content": [
                        {"word": "比亚迪涨停", "hotScore": 5000, "url": "https://b.co/1"},
                        {"word": "宁德时代", "hotScore": 4500, "url": "https://b.co/2"},
                    ]
                }
            ]
        }
    }
    with patch("requests.get", return_value=_mock_response(mock_json)):
        items = fetch_baidu()
    assert len(items) == 2
    assert items[0].title == "比亚迪涨停"
    assert items[0].hot_score == 5000


def test_bilibili_parser_extracts_items(isolated_cache):
    mock_json = {
        "list": [
            {"keyword": "A股大涨", "heat_score": 888},
            {"keyword": "巴菲特", "heat_score": 666},
        ]
    }
    with patch("requests.get", return_value=_mock_response(mock_json)):
        items = fetch_bilibili()
    assert len(items) == 2
    assert items[0].title == "A股大涨"
    assert "bilibili.com" in items[0].url


def test_toutiao_parser_extracts_items(isolated_cache):
    mock_json = {
        "data": [
            {"Title": "央行降息", "ClusterIdStr": "abc123", "HotValue": 99999, "LabelDesc": "热"},
            {"title": "外资加仓"},
        ]
    }
    with patch("requests.get", return_value=_mock_response(mock_json)):
        items = fetch_toutiao()
    assert len(items) == 2
    assert items[0].title == "央行降息"
    assert "abc123" in items[0].url


def test_douyin_parser_extracts_items(isolated_cache):
    mock_json = {
        "data": {
            "word_list": [
                {"word": "股市暴涨", "hot_value": 12345},
            ]
        }
    }
    with patch("requests.get", return_value=_mock_response(mock_json)):
        items = fetch_douyin()
    assert len(items) == 1
    assert items[0].title == "股市暴涨"


def test_parser_handles_empty_response(isolated_cache):
    """所有 parser 对空 dict 都不应抛异常."""
    with patch("requests.get", return_value=_mock_response({})):
        assert fetch_weibo() == []
        assert fetch_zhihu() == []
        assert fetch_baidu() == []
        assert fetch_bilibili() == []
        assert fetch_toutiao() == []
        assert fetch_douyin() == []


def test_parser_handles_network_error(isolated_cache):
    """_http_json 返 None 时 parser 返空 []，不抛."""
    with patch("requests.get", side_effect=Exception("network down")):
        assert fetch_weibo() == []
        assert fetch_zhihu() == []


# ─── cache 测试 ─────────────────────────────────────────────────────

def test_cache_roundtrip(isolated_cache):
    items = [HotItem(rank=1, title="茅台", platform="weibo").to_dict()]
    hottrend._cache_set("weibo", items)
    got = hottrend._cache_get("weibo")
    assert got is not None
    assert got[0]["title"] == "茅台"


def test_cache_expires_after_ttl(isolated_cache, monkeypatch):
    items = [HotItem(rank=1, title="old", platform="weibo").to_dict()]
    cache_file = isolated_cache / "weibo.json"
    cache_file.write_text(
        json.dumps({"ts": time.time() - 999, "items": items}),  # 过期
        encoding="utf-8",
    )
    monkeypatch.setattr(hottrend, "CACHE_TTL_SEC", 300)
    assert hottrend._cache_get("weibo") is None


def test_get_hot_trend_uses_cache(isolated_cache):
    # 先手工写缓存
    items = [HotItem(rank=1, title="cached", platform="weibo").to_dict()]
    hottrend._cache_set("weibo", items)
    # 拿数据：应走 cache 不发网络请求
    with patch("requests.get") as mock_get:
        result = get_hot_trend("weibo")
        assert mock_get.call_count == 0
    assert result.from_cache is True
    assert result.items[0].title == "cached"


def test_get_hot_trend_unknown_platform_returns_error(isolated_cache):
    r = get_hot_trend("unknown_platform")
    assert r.error != ""
    assert r.items == []


# ─── get_hot_mentions 核心场景 ─────────────────────────────────────

def test_get_hot_mentions_matches_by_name(isolated_cache):
    """股票名在热榜标题里出现 → 命中."""
    # 预置 3 平台缓存 · 其中 2 平台有命中
    hottrend._cache_set("weibo", [
        HotItem(rank=1, title="贵州茅台股价跌停", platform="weibo").to_dict(),
        HotItem(rank=2, title="其他新闻", platform="weibo").to_dict(),
    ])
    hottrend._cache_set("zhihu", [
        HotItem(rank=1, title="腾讯财报超预期", platform="zhihu").to_dict(),
    ])
    hottrend._cache_set("baidu", [
        HotItem(rank=1, title="茅台业绩", platform="baidu").to_dict(),  # 前 2 字命中
    ])
    # 其他 3 平台 empty cache
    for p in ("douyin", "toutiao", "bilibili"):
        hottrend._cache_set(p, [])

    # 预测：weibo 命中 1（全名）· zhihu 命中 0 · baidu 命中 1（简称"茅台"）
    r = get_hot_mentions("贵州茅台")
    assert r["stock_name"] == "贵州茅台"
    assert "茅台" in r["keywords_used"]  # 前 2 字会被加
    assert r["total_hits"] >= 2, f"expected >=2 hits, got {r}"
    assert r["by_platform_count"]["weibo"] == 1
    assert r["by_platform_count"]["zhihu"] == 0
    assert r["by_platform_count"]["baidu"] == 1


def test_get_hot_mentions_handles_platform_failure(isolated_cache):
    """某平台 API 挂了时，其他平台仍能正常返回."""
    # weibo cache OK
    hottrend._cache_set("weibo", [
        HotItem(rank=1, title="茅台上涨", platform="weibo").to_dict(),
    ])
    # zhihu 无 cache + 网络失败
    def _fake_get(url, **_kw):
        if "weibo" in url:
            # 不应走到这里（weibo 有 cache）
            return _mock_response({"data": {"realtime": []}})
        raise Exception("503 Service Unavailable")

    with patch("requests.get", side_effect=_fake_get):
        r = get_hot_mentions("贵州茅台")

    # weibo 应该命中（走 cache）· 其他平台 error 但不抛
    assert r["total_hits"] >= 1
    assert r["by_platform_count"]["weibo"] == 1
    # platforms_ok 数量 ≥ 1（至少 weibo OK）
    assert r["platforms_ok"] >= 1


def test_get_hot_mentions_skips_short_keywords(isolated_cache):
    """单字关键词太短会噪音太多 → hottrend 过滤掉 < 2 字的."""
    r = get_hot_mentions("A")  # 1 字符
    assert r["keywords_used"] == []
    assert r["total_hits"] == 0


def test_supported_platforms_has_six():
    """接口保证：6 平台清单不变."""
    assert len(SUPPORTED_PLATFORMS) == 6
    ids = {p[0] for p in SUPPORTED_PLATFORMS}
    assert ids == {"weibo", "zhihu", "baidu", "douyin", "toutiao", "bilibili"}


def test_hot_item_to_dict_roundtrip():
    it = HotItem(rank=3, title="test", url="https://x.com", hot_score=100,
                 platform="weibo", extra="热")
    d = it.to_dict()
    assert d["rank"] == 3
    assert d["title"] == "test"
    assert d["platform"] == "weibo"
