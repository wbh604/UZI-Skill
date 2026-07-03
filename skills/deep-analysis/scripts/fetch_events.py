"""Dimension 15 - event catalysts from announcements and lightweight news."""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timedelta

import lib.net_timeout_guard  # noqa: F401 - install requests default timeouts
import akshare as ak  # type: ignore
from lib.fast_basic import fetch_basic_fast
from lib.market_router import parse_ticker
from lib.web_search import search as web_search, search_trusted

DASH = "—"


def _cninfo_direct_api(code: str, page_size: int = 30, timeout: int = 15) -> list[dict]:
    """Direct cninfo query, first page only, to avoid akshare full-pagination stalls."""
    import requests

    code_prefix = code[:3]
    if code_prefix in ("000", "001", "002") or code.startswith("3"):
        column = "szse"
        stock_code = code
    elif code_prefix in ("600", "601", "603", "605", "688", "689"):
        column = "sse"
        stock_code = code
    else:
        column = "bse"
        stock_code = code

    url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Origin": "http://www.cninfo.com.cn",
        "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
    }
    payload = {
        "pageNum": 1,
        "pageSize": page_size,
        "column": column,
        "tabName": "fulltext",
        "plate": "",
        "stock": stock_code,
        "searchkey": "",
        "secid": "",
        "category": "",
        "trade": "",
        "seDate": "",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    try:
        r = requests.post(url, data=payload, headers=headers, timeout=timeout)
        if r.status_code != 200:
            return []
        data = r.json()
    except (requests.RequestException, ValueError):
        return []

    rows = []
    for a in (data.get("announcements") or [])[:page_size]:
        ts = a.get("announcementTime") or 0
        try:
            date_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else ""
        except (TypeError, ValueError, OSError):
            date_str = ""
        ann_url = a.get("adjunctUrl") or ""
        if ann_url and not ann_url.startswith("http"):
            ann_url = f"http://static.cninfo.com.cn/{ann_url.lstrip('/')}"
        rows.append({
            "date": date_str,
            "title": str(a.get("announcementTitle", "")),
            "url": ann_url,
            "type": "cninfo 公告",
        })
    return rows


def _cninfo_disclosures(code: str, days_back: int = 180) -> list[dict]:
    """Cninfo disclosures. Slow akshare fallback is opt-in via UZI_AK_CNINFO_FALLBACK=1."""
    rows = _cninfo_direct_api(code, page_size=30, timeout=15)
    if rows:
        return rows

    if os.environ.get("UZI_AK_CNINFO_FALLBACK") != "1":
        return []

    today = datetime.now()
    start = (today - timedelta(days=days_back)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    try:
        df = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=code,
            market="沪深京",
            category="",
            start_date=start,
            end_date=end,
        )
        if df is None or df.empty:
            return []
        rows = []
        for _, r in df.head(30).iterrows():
            rows.append({
                "date": str(r.get("公告时间", ""))[:10],
                "title": str(r.get("公告标题", "")),
                "url": str(r.get("公告链接", "")),
                "type": "cninfo 公告",
            })
        return rows
    except Exception as e:
        return [{"error": f"cninfo fail: {e}"}]


def _eastmoney_disclosures(code: str, limit: int = 20) -> list[dict]:
    """Lightweight Eastmoney announcement fallback keyed by stock code."""
    try:
        from lib.news_providers import fetch_em_stock_ann

        items = fetch_em_stock_ann(stock_code=code, limit=limit)
    except Exception:
        return []

    rows = []
    for item in items[:limit]:
        d = item.to_dict() if hasattr(item, "to_dict") else dict(item)
        title = str(d.get("title", "")).strip()
        if not title:
            continue
        rows.append({
            "date": str(d.get("publish_time", ""))[:10],
            "title": title,
            "url": str(d.get("url", "")),
            "type": "eastmoney 公告",
        })
    return rows


def _try_news(code: str) -> list[dict]:
    """Best-effort akshare stock_news_em. Disabled by default in main; keep callable."""
    try:
        df = ak.stock_news_em(symbol=code)
        if df is None or df.empty:
            return []
        rows = []
        for _, r in df.head(30).iterrows():
            title = str(r.get("新闻标题", ""))
            if _is_noise_news(title):
                continue
            rows.append({
                "date": str(r.get("发布时间", ""))[:16],
                "title": title,
                "type": "新闻",
                "source": str(r.get("文章来源", "")),
            })
            if len(rows) >= 12:
                break
        return rows
    except Exception:
        return []


_NOISE_KWS = [
    "主力资金净流", "资金流向日报", "融资余额", "北向资金", "两融", "龙虎榜汇总",
    "板块涨幅", "行业今日", "大盘分析", "涨停", "跌停", "涨幅榜",
]


def _is_noise_news(title: str) -> bool:
    if not title:
        return True
    return any(kw in title for kw in _NOISE_KWS)


def _web_search_events(name: str, max_results: int = 6) -> list[dict]:
    """Optional web-search fallback for company-specific events."""
    queries = [
        f"{name} 上市公司 最新动态 合同 订单 产品",
        f"{name} 业绩 研发 突破 合作",
    ]
    results = []
    seen = set()
    for q in queries:
        res_trusted = search_trusted(q, dim_key="15_events", max_results=max_results)
        res_generic = web_search(q, max_results=max_results) if len(res_trusted) < 3 else []
        for r in list(res_trusted) + list(res_generic):
            if "error" in r:
                continue
            title = r.get("title", "")[:80]
            if title and title not in seen and not _is_noise_news(title):
                seen.add(title)
                results.append({
                    "date": DASH,
                    "title": title,
                    "type": "web_search",
                    "source": r.get("url", ""),
                })
    return results[:8]


def _append_news_providers(news: list[dict], code: str, company_name: str) -> None:
    try:
        from lib.news_providers import get_news_multi_source

        multi = get_news_multi_source(stock_code=code, stock_name=company_name, limit_per_source=10)
        for src, items in (multi.get("sources") or {}).items():
            for it in items:
                if not isinstance(it, dict) or it.get("error"):
                    continue
                title = it.get("title", "")[:80]
                if not title or _is_noise_news(title):
                    continue
                news.append({
                    "date": (it.get("publish_time") or "")[:16] or DASH,
                    "title": title,
                    "type": f"news_providers:{src}",
                    "source": it.get("url", ""),
                })
    except Exception:
        pass


def _dedupe_sort(disclosures: list[dict], news: list[dict]) -> list[dict]:
    merged = {}
    for item in disclosures + news:
        if "error" in item:
            continue
        key = item.get("title", "")[:80]
        if key and key not in merged:
            merged[key] = item
    return sorted(merged.values(), key=lambda x: x.get("date", ""), reverse=True)


def main(ticker: str) -> dict:
    ti = parse_ticker(ticker)
    if ti.market == "H":
        try:
            from lib.hk_data_sources import fetch_hk_announcements_cached
            basic = fetch_basic_fast(ti)
            company_name = basic.get("name") or basic.get("full_name") or ti.code
            anns = fetch_hk_announcements_cached(ti.code.zfill(5), limit=20)
            ws_events = (
                _web_search_events(company_name)
                if len(anns) < 5 and os.environ.get("UZI_EVENTS_WEB_SEARCH") == "1"
                else []
            )
            timeline = [f"{a.get('date', DASH)} · {a.get('title', '')[:80]}" for a in anns + ws_events]
            return {
                "ticker": ti.full,
                "data": {
                    "event_timeline": timeline[:30],
                    "recent_news": [
                        {"date": a.get("date", ""), "title": a.get("title", ""),
                         "url": a.get("url", ""), "source": a.get("source", "hkexnews")}
                        for a in anns
                    ],
                    "recent_notices": [],
                    "catalysts": [],
                    "warnings": [],
                    "_note": "HK 公告来自 hkexnews；web_search 为 UZI_EVENTS_WEB_SEARCH=1 opt-in。",
                },
                "source": "hkexnews + web_search(opt-in)",
                "fallback": False,
            }
        except Exception as e:
            return {
                "ticker": ti.full,
                "data": {"_err": f"{type(e).__name__}: {str(e)[:120]}"},
                "source": "hkexnews",
                "fallback": True,
            }
    if ti.market != "A":
        return {"ticker": ti.full, "data": {}, "source": "n/a", "fallback": True}

    try:
        basic = fetch_basic_fast(ti)
        company_name = basic.get("name") or ti.code
    except Exception:
        company_name = ti.code

    disclosures = _cninfo_disclosures(ti.code)
    if not disclosures:
        disclosures = _eastmoney_disclosures(ti.code)

    news = _try_news(ti.code) if os.environ.get("UZI_EVENTS_AK_NEWS") == "1" else []
    _append_news_providers(news, ti.code, company_name)

    if len(news) < 3 and os.environ.get("UZI_EVENTS_WEB_SEARCH") == "1":
        news = news + _web_search_events(company_name)

    sorted_events = _dedupe_sort(disclosures, news)

    timeline = []
    for ev in sorted_events[:10]:
        date = ev.get("date", "")[:10] or DASH
        title = ev.get("title", "")[:70]
        timeline.append(f"{date} · {title}")

    catalyst_kws = ["合同", "中标", "业绩", "研发", "获批", "专利", "投资", "合作", "股权", "分红", "回购"]
    catalysts = []
    for item in disclosures[:20]:
        title = item.get("title", "")
        if any(kw in title for kw in catalyst_kws):
            catalysts.append({
                "date": item.get("date", ""),
                "event": title[:80],
                "impact": "medium",
            })

    warning_kws = ["风险", "立案", "违规", "退市", "ST", "商誉减值", "资产减值", "业绩下滑"]
    warning_items = []
    for item in disclosures[:20]:
        title = item.get("title", "")
        if any(kw in title for kw in warning_kws):
            warning_items.append(title[:80])

    return {
        "ticker": ti.full,
        "data": {
            "event_timeline": timeline,
            "recent_news": news[:10],
            "recent_notices": disclosures[:20],
            "disclosures_count": len(disclosures),
            "news_count": len(news),
            "recent_news_label": f"{len(news)} 条新闻" if news else DASH,
            "catalyst": catalysts[:5],
            "warnings": warning_items if warning_items else [],
        },
        "source": "cninfo + eastmoney_ann + news_providers(jin10/em/ths) + ak_news(opt-in) + web_search(opt-in)",
        "fallback": False,
    }


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"
    try:
        print(json.dumps(main(arg), ensure_ascii=False, indent=2, default=str))
    except Exception:
        traceback.print_exc()
