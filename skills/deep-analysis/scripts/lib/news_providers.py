"""财经新闻多源聚合 · v2.13.7

给 fetch_events / fetch_sentiment 提供 HTTP 直连新闻源 · 补 ddgs 盲区:
- jin10_flash: 金十数据 · 类财联社实时快讯 (JSON)
- em_kuaixun: 东财快讯 (JSON)
- em_stock_ann: 东财上市公司公告 (JSON · A 股)
- ths_news_today: 同花顺今日快讯 (HTML)

所有抓取：
- `UZI_HTTP_TIMEOUT` 秒超时（默认 20）
- 单源失败不影响其他源
- 10 min 文件缓存（新闻变化频率中等）
- 返回统一 NewsItem 结构
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

import requests

HTTP_TIMEOUT = int(os.environ.get("UZI_HTTP_TIMEOUT", "20"))
CACHE_TTL_SEC = 600  # 10 min

UA_PC = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"


@dataclass
class NewsItem:
    source: str
    title: str
    body: str = ""
    url: str = ""
    publish_time: str = ""
    raw_ts: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# ─── 缓存 ─────────────────────────────────────────────────────────

def _cache_dir() -> Path:
    root = Path(__file__).resolve().parent.parent / ".cache" / "_global" / "news"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cache_get(key: str) -> list | None:
    f = _cache_dir() / f"{key}.json"
    if not f.exists():
        return None
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
        if time.time() - raw.get("ts", 0) > CACHE_TTL_SEC:
            return None
        return raw.get("items")
    except Exception:
        return None


def _cache_set(key: str, items: list) -> None:
    try:
        f = _cache_dir() / f"{key}.json"
        f.write_text(
            json.dumps({"ts": time.time(), "items": items}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


# ─── HTTP helper ──────────────────────────────────────────────────

def _http_get(url: str, timeout: int = HTTP_TIMEOUT) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA_PC}, timeout=timeout)
        if r.status_code != 200:
            return None
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except Exception:
        return None


# ─── 各源 fetcher ────────────────────────────────────────────────

def fetch_jin10(limit: int = 30) -> list[NewsItem]:
    """金十数据实时快讯 · flash_newest.js 是 var newest = [...] JS 变量."""
    cached = _cache_get("jin10")
    if cached is not None:
        return [NewsItem(**x) for x in cached[:limit]]
    txt = _http_get("https://www.jin10.com/flash_newest.js", timeout=12)
    if not txt:
        return []
    # 抽 JSON 数组 · 跳 var newest = 前缀
    m = re.search(r"var newest\s*=\s*(\[.*?\]);", txt, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception:
        return []
    items: list[NewsItem] = []
    for row in data[:limit]:
        d = row.get("data", {}) if isinstance(row, dict) else {}
        title = d.get("title") or d.get("content", "")[:100] or ""
        body = d.get("content", "")
        # 去 HTML tag
        body = re.sub(r"<[^>]+>", "", body)[:300] if body else ""
        if not title and body:
            title = body[:80]
        if not title:
            continue
        items.append(NewsItem(
            source="jin10",
            title=title.strip()[:200],
            body=body.strip(),
            url="https://www.jin10.com/",
            publish_time=row.get("time", ""),
        ))
    _cache_set("jin10", [i.to_dict() for i in items])
    return items


def fetch_em_kuaixun(limit: int = 30) -> list[NewsItem]:
    """东财快讯 · var ajaxResult={LivesList: [...]} 格式."""
    cached = _cache_get("em_kuaixun")
    if cached is not None:
        return [NewsItem(**x) for x in cached[:limit]]
    url = (
        "https://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_50_1_.html"
    )
    txt = _http_get(url, timeout=12)
    if not txt:
        return []
    # 响应可能以 `};` 或裸 `}` 结尾 · 用 greedy 到文件末尾兜底
    m = re.search(r"var ajaxResult\s*=\s*(\{.*\})\s*;?\s*$", txt, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception:
        return []
    items: list[NewsItem] = []
    for row in (data.get("LivesList") or [])[:limit]:
        title = row.get("title") or row.get("digest", "")[:100] or ""
        body = row.get("digest", "")
        if not title:
            continue
        items.append(NewsItem(
            source="em_kuaixun",
            title=title.strip()[:200],
            body=body.strip()[:300],
            url=row.get("url_mobile") or row.get("url_w") or "",
            publish_time=row.get("showtime", ""),
        ))
    _cache_set("em_kuaixun", [i.to_dict() for i in items])
    return items


def fetch_em_stock_ann(stock_code: str = "", limit: int = 20) -> list[NewsItem]:
    """东财上市公司公告 JSON · A 股."""
    key = f"em_ann_{stock_code or 'all'}"
    cached = _cache_get(key)
    if cached is not None:
        return [NewsItem(**x) for x in cached[:limit]]
    url = (
        "https://np-anotice-stock.eastmoney.com/api/security/ann"
        f"?sr=-1&page_size={limit}&page_index=1&ann_type=A&client_source=web"
    )
    # 可扩展：按 stock_code 过滤 · 但 API 参数不稳定 · 先拉全量
    txt = _http_get(url, timeout=12)
    if not txt:
        return []
    try:
        data = json.loads(txt)
    except Exception:
        return []
    items: list[NewsItem] = []
    for row in (data.get("data", {}).get("list") or [])[:limit]:
        title = row.get("title", "") or ""
        if not title:
            continue
        if stock_code and not any(
            stock_code == c.get("stock_code", "") for c in row.get("codes", [])
        ):
            continue
        items.append(NewsItem(
            source="em_stock_ann",
            title=title.strip()[:200],
            body=row.get("art_code", ""),
            url="https://np-anotice-stock.eastmoney.com/",
            publish_time=row.get("notice_date", "") or row.get("display_time", ""),
        ))
    _cache_set(key, [i.to_dict() for i in items])
    return items


def fetch_ths_news_today(limit: int = 20) -> list[NewsItem]:
    """同花顺今日快讯 · HTML 解析 · 较重量级兜底."""
    cached = _cache_get("ths_today")
    if cached is not None:
        return [NewsItem(**x) for x in cached[:limit]]
    txt = _http_get("http://news.10jqka.com.cn/today_list/", timeout=12)
    if not txt:
        return []
    # 同花顺 HTML · 标题通常在 <a class="arc-title"> 或 <li>  内
    titles = re.findall(r'<a[^>]*class="[^"]*title[^"]*"[^>]*>([^<]{5,120})</a>', txt)
    if not titles:
        titles = re.findall(r'<li[^>]*>\s*<a[^>]*>([^<]{10,100})</a>', txt)
    items = []
    for t in titles[:limit]:
        title = t.strip()
        if len(title) < 10:
            continue
        items.append(NewsItem(
            source="ths_news_today",
            title=title[:200],
            url="http://news.10jqka.com.cn/today_list/",
        ))
    _cache_set("ths_today", [i.to_dict() for i in items])
    return items


# ─── 聚合 API ────────────────────────────────────────────────────

def get_news_multi_source(
    stock_code: str = "",
    stock_name: str = "",
    limit_per_source: int = 20,
) -> dict:
    """多源聚合 · 返 {"jin10": [...], "em_kuaixun": [...], ...}

    对 stock_name 做 keyword 过滤（标题或内容含 name）· 仅返相关项.
    若 stock_name 为空则返所有 · 给全局舆情用.
    """
    sources = [
        ("jin10", fetch_jin10),
        ("em_kuaixun", fetch_em_kuaixun),
        ("em_stock_ann", lambda n: fetch_em_stock_ann(stock_code, n)),
        ("ths_news_today", fetch_ths_news_today),
    ]
    result: dict[str, list[dict]] = {}
    total_hits = 0
    for name, fn in sources:
        try:
            items = fn(limit_per_source)
        except Exception as e:
            result[name] = [{"error": f"{type(e).__name__}: {str(e)[:80]}"}]
            continue
        # 名字过滤（若提供）
        if stock_name and len(stock_name) >= 2:
            # 派生简称
            keywords = [stock_name]
            if len(stock_name) >= 3:
                keywords.append(stock_name[-2:])
            items = [i for i in items
                     if any(k in i.title or k in i.body for k in keywords)]
        result[name] = [i.to_dict() for i in items]
        total_hits += len(items)
    return {
        "stock_name": stock_name,
        "stock_code": stock_code,
        "sources": result,
        "total_hits": total_hits,
        "sources_ok": sum(
            1 for v in result.values() if v and not (
                isinstance(v[0], dict) and "error" in v[0]
            )
        ),
    }


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    code = sys.argv[2] if len(sys.argv) > 2 else ""
    r = get_news_multi_source(stock_code=code, stock_name=name, limit_per_source=10)
    print(f"name: {r['stock_name']} · code: {r['stock_code']}")
    print(f"sources_ok: {r['sources_ok']}/4 · total_hits: {r['total_hits']}")
    for src, items in r["sources"].items():
        print(f"\n[{src}] {len(items)} items")
        for it in items[:3]:
            if isinstance(it, dict) and "error" in it:
                print(f"  ✗ {it['error']}")
            else:
                print(f"  · {it.get('title', '')[:70]}")
