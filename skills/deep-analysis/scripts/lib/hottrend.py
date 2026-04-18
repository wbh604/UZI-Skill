"""热榜聚合 · 6 平台（v2.12 · 抄自 run-bigpig/jcp/internal/services/hottrend）

覆盖：微博 / 知乎 / B 站 / 百度 / 抖音 / 头条

用途：
- `fetch_sentiment.py` 17_sentiment 维度：把股票名/公司名在热榜命中作为散户情绪信号
- `fetch_trap_signals.py` 18_trap 维度：小红书/抖音/快手类情绪热点补盲

设计：
- 每平台独立 fetcher + 独立 try/except → 单平台挂不影响其他
- 5 分钟文件缓存（jcp 同款 TTL）
- 所有请求 UZI_HTTP_TIMEOUT 秒超时（默认 20）
- 返回统一 HotItem 数据模型

反爬：抄 jcp 的 User-Agent 策略（每平台用不同 UA）。被反爬时降级返空，不抛
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Callable

import requests

# ─── 配置 ────────────────────────────────────────────────────────────

HTTP_TIMEOUT = int(os.environ.get("UZI_HTTP_TIMEOUT", "20"))
CACHE_TTL_SEC = 300  # 5 分钟（jcp 同款）

# 每平台独立 User-Agent（jcp 同款）
UA_PC = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
UA_MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
UA_MOBILE = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"

# 支持的平台清单（顺序 = 展示优先级）
SUPPORTED_PLATFORMS = [
    ("weibo",    "微博热搜"),
    ("zhihu",    "知乎热榜"),
    ("baidu",    "百度热搜"),
    ("douyin",   "抖音热点"),
    ("toutiao",  "头条热榜"),
    ("bilibili", "B 站热搜"),
]


# ─── 数据模型 ────────────────────────────────────────────────────────

@dataclass
class HotItem:
    rank: int
    title: str
    url: str = ""
    hot_score: int = 0
    platform: str = ""
    extra: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HotTrendResult:
    platform: str
    platform_cn: str
    items: list = field(default_factory=list)
    updated_at: float = 0.0
    from_cache: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "platform_cn": self.platform_cn,
            "items": [i.to_dict() if isinstance(i, HotItem) else i for i in self.items],
            "updated_at": self.updated_at,
            "from_cache": self.from_cache,
            "error": self.error,
        }


# ─── 文件缓存 ────────────────────────────────────────────────────────

def _cache_dir() -> Path:
    root = Path(__file__).resolve().parent.parent / ".cache" / "_global" / "hottrend"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cache_get(platform: str) -> list | None:
    f = _cache_dir() / f"{platform}.json"
    if not f.exists():
        return None
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
        if time.time() - raw.get("ts", 0) > CACHE_TTL_SEC:
            return None
        return raw.get("items")
    except Exception:
        return None


def _cache_set(platform: str, items: list) -> None:
    try:
        f = _cache_dir() / f"{platform}.json"
        f.write_text(
            json.dumps({"ts": time.time(), "items": items}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


# ─── HTTP helper ─────────────────────────────────────────────────────

def _http_json(url: str, ua: str = UA_PC, extra_headers: dict | None = None) -> dict | None:
    headers = {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
    }
    if extra_headers:
        headers.update(extra_headers)
    try:
        r = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


# ─── 平台 fetchers ───────────────────────────────────────────────────

def fetch_weibo() -> list[HotItem]:
    """微博热搜 · https://weibo.com/ajax/side/hotSearch"""
    data = _http_json("https://weibo.com/ajax/side/hotSearch", ua=UA_MAC)
    if not data:
        return []
    items = (data.get("data") or {}).get("realtime") or []
    out: list[HotItem] = []
    for i, it in enumerate(items[:50], start=1):
        word = it.get("word", "")
        if not word:
            continue
        out.append(HotItem(
            rank=i, title=word,
            url=f"https://s.weibo.com/weibo?q={word}",
            hot_score=int(it.get("num", 0) or 0),
            platform="weibo",
            extra=it.get("category", "") or "",
        ))
    return out


def fetch_zhihu() -> list[HotItem]:
    """知乎热榜 · https://www.zhihu.com/api/v3/feed/topstory/hot-list-web"""
    data = _http_json(
        "https://www.zhihu.com/api/v3/feed/topstory/hot-list-web?limit=50&desktop=true",
        ua=UA_PC,
    )
    if not data:
        return []
    out: list[HotItem] = []
    for i, it in enumerate((data.get("data") or [])[:50], start=1):
        tgt = it.get("target") or {}
        title = tgt.get("title_area", {}).get("text") or tgt.get("title") or ""
        link = (tgt.get("link") or {}).get("url", "")
        metrics = tgt.get("metrics_area", {}).get("text", "")
        if not title:
            continue
        out.append(HotItem(
            rank=i, title=title, url=link,
            platform="zhihu",
            extra=metrics,
        ))
    return out


def fetch_baidu() -> list[HotItem]:
    """百度热搜 · https://top.baidu.com/api/board?platform=wise&tab=realtime"""
    data = _http_json(
        "https://top.baidu.com/api/board?platform=wise&tab=realtime",
        ua=UA_MOBILE,
    )
    if not data:
        return []
    items = (data.get("data") or {}).get("cards", [])
    if items and isinstance(items, list):
        items = items[0].get("content", []) if items[0] else []
    out: list[HotItem] = []
    for i, it in enumerate(items[:50], start=1):
        word = it.get("word", "") or it.get("query", "")
        if not word:
            continue
        out.append(HotItem(
            rank=i, title=word,
            url=it.get("url", "") or f"https://www.baidu.com/s?wd={word}",
            hot_score=int(it.get("hotScore", 0) or 0),
            platform="baidu",
        ))
    return out


def fetch_douyin() -> list[HotItem]:
    """抖音热点 · https://www.douyin.com/aweme/v1/web/hot/search/list/"""
    # 抖音有签名反爬，直接命中概率较低；降级返空不抛
    data = _http_json(
        "https://www.douyin.com/aweme/v1/web/hot/search/list/",
        ua=UA_PC,
    )
    if not data:
        return []
    items = (data.get("data") or {}).get("word_list", [])
    out: list[HotItem] = []
    for i, it in enumerate(items[:50], start=1):
        word = it.get("word", "")
        if not word:
            continue
        out.append(HotItem(
            rank=i, title=word,
            url=f"https://www.douyin.com/search/{word}",
            hot_score=int(it.get("hot_value", 0) or 0),
            platform="douyin",
        ))
    return out


def fetch_toutiao() -> list[HotItem]:
    """头条热榜 · https://www.toutiao.com/hot-event/hot-board/"""
    data = _http_json(
        "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
        ua=UA_PC,
    )
    if not data:
        return []
    out: list[HotItem] = []
    for i, it in enumerate((data.get("data") or [])[:50], start=1):
        title = it.get("Title", "") or it.get("title", "")
        cid = it.get("ClusterIdStr") or it.get("ClusterId") or ""
        if not title:
            continue
        out.append(HotItem(
            rank=i, title=title,
            url=f"https://www.toutiao.com/trending/{cid}/" if cid else "",
            hot_score=int(it.get("HotValue", 0) or 0),
            platform="toutiao",
            extra=it.get("LabelDesc", "") or "",
        ))
    return out


def fetch_bilibili() -> list[HotItem]:
    """B 站热搜 · https://s.search.bilibili.com/main/hotword?limit=50"""
    data = _http_json(
        "https://s.search.bilibili.com/main/hotword?limit=50",
        ua=UA_PC,
    )
    if not data:
        return []
    out: list[HotItem] = []
    for i, it in enumerate((data.get("list") or [])[:50], start=1):
        keyword = it.get("keyword", "") or it.get("show_name", "")
        if not keyword:
            continue
        out.append(HotItem(
            rank=i, title=keyword,
            url=f"https://search.bilibili.com/all?keyword={keyword}",
            hot_score=int(it.get("heat_score", 0) or 0),
            platform="bilibili",
        ))
    return out


_FETCHERS: dict[str, Callable[[], list[HotItem]]] = {
    "weibo":    fetch_weibo,
    "zhihu":    fetch_zhihu,
    "baidu":    fetch_baidu,
    "douyin":   fetch_douyin,
    "toutiao":  fetch_toutiao,
    "bilibili": fetch_bilibili,
}


def _platform_cn(pid: str) -> str:
    for p, cn in SUPPORTED_PLATFORMS:
        if p == pid:
            return cn
    return pid


# ─── 公开 API ─────────────────────────────────────────────────────────

def get_hot_trend(platform: str) -> HotTrendResult:
    """获取单平台热榜（命中缓存秒回）."""
    if platform not in _FETCHERS:
        return HotTrendResult(platform=platform, platform_cn=platform, error="unsupported platform")

    # 缓存命中 → 直接返
    cached = _cache_get(platform)
    if cached is not None:
        items = [HotItem(**x) if isinstance(x, dict) else x for x in cached]
        return HotTrendResult(
            platform=platform, platform_cn=_platform_cn(platform),
            items=items, updated_at=time.time(), from_cache=True,
        )

    # 网络抓取
    try:
        items = _FETCHERS[platform]()
    except Exception as e:
        return HotTrendResult(
            platform=platform, platform_cn=_platform_cn(platform),
            error=f"{type(e).__name__}: {str(e)[:80]}",
        )

    if items:
        _cache_set(platform, [i.to_dict() for i in items])

    return HotTrendResult(
        platform=platform, platform_cn=_platform_cn(platform),
        items=items, updated_at=time.time(),
    )


def get_all_hot_trend() -> dict[str, HotTrendResult]:
    """串行拉 6 平台（5min cache 命中后几乎零耗时）."""
    return {p: get_hot_trend(p) for p, _ in SUPPORTED_PLATFORMS}


def get_hot_mentions(stock_name: str, extra_keywords: list | None = None) -> dict:
    """对给定股票名在 6 平台热榜中做命中检测 · 返回每平台命中条目清单.

    Args:
        stock_name: 股票中文名（如"贵州茅台"）
        extra_keywords: 额外关键词（如简称/子品牌），可选

    Returns:
    {
      "stock_name": "贵州茅台",
      "platforms_checked": 6,
      "platforms_ok": 5,
      "mentions": {
        "weibo": [{"rank": 3, "title": "茅台 1499", "url": "...", "hot_score": 12345}],
        "zhihu": [...],
        ...
      },
      "total_hits": 4,
      "by_platform_count": {"weibo": 1, "zhihu": 2, ...},
    }
    """
    keywords: list = [stock_name]
    # 自动派生简称：3 字以上股票名取前 2 字和后 2 字（覆盖"贵州茅台"→"贵州"/"茅台"）
    if stock_name and len(stock_name) >= 3:
        keywords.append(stock_name[:2])
    if stock_name and len(stock_name) >= 4:
        keywords.append(stock_name[-2:])
    if extra_keywords:
        keywords.extend(k for k in extra_keywords if k and k.strip())
    # 统一去首尾空格 · 去 None · 去空 · 去重保序
    seen: set = set()
    cleaned: list = []
    for k in keywords:
        if not k or not k.strip():
            continue
        ks = k.strip()
        if len(ks) < 2:  # 单字符噪音太大，过滤
            continue
        if ks in seen:
            continue
        seen.add(ks)
        cleaned.append(ks)
    keywords = cleaned

    mentions: dict[str, list] = {}
    by_count: dict[str, int] = {}
    ok_count = 0

    for platform, _ in SUPPORTED_PLATFORMS:
        result = get_hot_trend(platform)
        if result.error:
            mentions[platform] = []
            by_count[platform] = 0
            continue
        ok_count += 1
        hits: list = []
        for item in result.items:
            title = item.title if isinstance(item, HotItem) else item.get("title", "")
            for kw in keywords:
                if kw in title:
                    hits.append(item.to_dict() if isinstance(item, HotItem) else item)
                    break  # 一条只算一次命中
        mentions[platform] = hits
        by_count[platform] = len(hits)

    return {
        "stock_name": stock_name,
        "keywords_used": keywords,
        "platforms_checked": len(SUPPORTED_PLATFORMS),
        "platforms_ok": ok_count,
        "mentions": mentions,
        "total_hits": sum(by_count.values()),
        "by_platform_count": by_count,
    }


if __name__ == "__main__":
    # 手测：python3 -m lib.hottrend 贵州茅台
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "贵州茅台"
    r = get_hot_mentions(name)
    print(f"股票: {r['stock_name']}")
    print(f"平台 OK/总: {r['platforms_ok']}/{r['platforms_checked']}")
    print(f"总命中: {r['total_hits']}")
    for p, cnt in r["by_platform_count"].items():
        if cnt > 0:
            print(f"\n  [{_platform_cn(p)}]")
            for it in r["mentions"][p]:
                print(f"    #{it['rank']} {it['title']} — 热度 {it['hot_score']}")
