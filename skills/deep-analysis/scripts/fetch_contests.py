"""Dimension 19 · 实盘比赛持仓 (真实抓取版).

数据源:
1. 雪球 cubes_search.json    — 公开 API，最稳定，能拿到所有持有该股的雪球组合 + 收益率
2. 雪球 stock-related cubes   — 同一只股票的相关组合
3. 淘股吧 实盘大赛排行         — 爬 HTML（可能被反爬，失败降级）
4. 同花顺模拟炒股             — 爬 moni.10jqka.com.cn（公开榜单）
5. 大盘手网期货实盘大赛       — 仅当股票有关联期货品种时使用
6. Claude web search 兜底     — 上述全部失败时

输出结构:
{
  "xueqiu_cubes":     [{name, owner, total_gain, monthly_gain, position_pct, url}, ...],
  "tgb_players":      [{nickname, rank, return_pct, holding_pct, evidence_url}, ...],
  "ths_simu":         [{nickname, rank, return_pct, ...}],
  "qh_contest":       [{nickname, ...}],
  "summary": {
    "s_tier_holders": int,    # 顶级选手持有
    "a_tier_holders": int,
    "b_tier_holders": int,
    "high_return_cubes": int,  # 收益率 > 50% 的组合数
  }
}
"""
import json
import re
import sys
import time
import urllib.parse
from typing import Any

import requests  # type: ignore

from lib.cache import cached
from lib.market_router import parse_ticker

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


# ─────────────────────────────────────────────────────────────
# 1. 雪球 cubes (most reliable)
# ─────────────────────────────────────────────────────────────
def _xq_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": "https://xueqiu.com/"})
    try:
        s.get("https://xueqiu.com/", timeout=10)
    except Exception:
        pass
    return s


def _xq_symbol(ti) -> str:
    """Convert ticker to xueqiu symbol format: SH600519 / SZ002273 / HK00700 / AAPL"""
    if ti.market == "A":
        suffix = ti.full[-2:]
        return f"{suffix}{ti.code}"
    if ti.market == "H":
        return f"HK{ti.code.zfill(5)}"
    return ti.code  # US


def fetch_xueqiu_cubes(ti, limit: int = 50) -> tuple[list[dict], dict]:
    """Returns (cubes, meta) where meta has {http_status, source, login_required}.

    v2.7.1: 2026 起 cubes_search.json 强制登录（HTTP 400 + error_code 400016）。
    流程：
    1. 先试 HTTP 直访（无登录） — 仍存活的旧版本可能能用
    2. 失败 → 检查 UZI_XQ_LOGIN 是否启用
    3. 启用 → 调 lib.xueqiu_browser 用 Playwright + 持久化 cookie 抓
    4. 未启用 → 返回 [{"_login_required": True, ...}] 标记，不报 error
    """
    sess = _xq_session()
    symbol = _xq_symbol(ti)
    url = f"https://xueqiu.com/cubes/cubes_search.json?code={symbol}&category=2&count={limit}&page=1"
    meta = {"http_status": None, "source": "http", "login_required": False}
    try:
        r = sess.get(url, timeout=15)
        meta["http_status"] = r.status_code
        if r.status_code == 200:
            data = r.json()
            cubes = data.get("list") or data.get("cubes") or []
            out = _normalize_cubes(cubes)
            if out:
                return out, meta
        # Treat 400/401/403/error_code 400016 as login-required
        if r.status_code in (400, 401, 403) or '"error_code":"400016"' in r.text:
            meta["login_required"] = True
    except Exception as e:
        meta["http_error"] = f"{type(e).__name__}: {str(e)[:120]}"

    # Fallback to Playwright (opt-in only)
    try:
        from lib.xueqiu_browser import is_login_enabled, fetch_cubes_via_browser, _has_valid_cookies
        if is_login_enabled() and _has_valid_cookies():
            cubes = fetch_cubes_via_browser(symbol, limit)
            if cubes:
                meta["source"] = "playwright_authenticated"
                return cubes, meta
        else:
            meta["login_required"] = True
            meta["hint"] = "set UZI_XQ_LOGIN=1 + run `python -m lib.xueqiu_browser login` (one-time)"
    except Exception as e:
        meta["browser_error"] = f"{type(e).__name__}: {str(e)[:120]}"

    return [], meta


def _normalize_cubes(cubes: list) -> list[dict]:
    """Normalize raw xueqiu cube dicts to our schema."""
    out = []
    for c in cubes:
        if not isinstance(c, dict):
            continue
        out.append({
            "name": c.get("name"),
            "owner": (c.get("owner") or {}).get("screen_name"),
            "symbol": c.get("symbol"),
            "daily_gain": c.get("daily_gain"),
            "monthly_gain": c.get("monthly_gain"),
            "total_gain": c.get("total_gain"),
            "annualized_gain_rate": c.get("annualized_gain_rate"),
            "url": f"https://xueqiu.com/P/{c.get('symbol')}" if c.get("symbol") else None,
            "stocks_count": c.get("stocks_count"),
            "view_rebalancing_count": c.get("view_rebalancing_count"),
        })
    return out


# ─────────────────────────────────────────────────────────────
# 2. 淘股吧 (stock thread search; player ranking is behind login)
# ─────────────────────────────────────────────────────────────
def fetch_tgb_mentions(ti) -> list[dict]:
    """Search 淘股吧 for threads mentioning this ticker — proxy for "实盘选手在讨论"."""
    code = ti.code
    url = f"https://www.taoguba.com.cn/Article/list/all?keyword={code}"
    headers = {"User-Agent": UA}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return []
        html = r.text
        rows = re.findall(
            r'<a[^>]+href="(/Article/\d+/\d+)"[^>]*>([^<]{4,80})</a>',
            html,
        )
        out = []
        for href, title in rows[:30]:
            out.append({
                "title": title.strip(),
                "url": f"https://www.taoguba.com.cn{href}",
            })
        return out
    except Exception as e:
        return [{"error": f"tgb fetch failed: {e}"}]


# ─────────────────────────────────────────────────────────────
# 3. 同花顺模拟炒股 (public leaderboards)
# ─────────────────────────────────────────────────────────────
def fetch_ths_simu(ti) -> list[dict]:
    """Try to find which 同花顺 simulator players hold this stock.
    The official endpoint is largely closed; we attempt a public search page.
    """
    code = ti.code
    url = f"https://moni.10jqka.com.cn/holder/?stock={code}"
    headers = {"User-Agent": UA, "Referer": "https://moni.10jqka.com.cn/"}
    try:
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code != 200 or "Just a moment" in r.text:
            return [{"note": "ths simu endpoint requires login or blocked"}]
        rows = re.findall(r'<a[^>]+class="user[^"]*"[^>]*>([^<]+)</a>.*?(\d+\.\d+)%', r.text)
        return [{"nickname": n, "return_pct": float(p)} for n, p in rows[:20]]
    except Exception as e:
        return [{"error": f"ths simu fetch failed: {e}"}]


# ─────────────────────────────────────────────────────────────
# 4. 大盘手网期货实盘大赛 (only if related futures exist)
# ─────────────────────────────────────────────────────────────
def fetch_dpswang(ti) -> list[dict]:
    """大盘手网公开榜单。仅作可达性探测，详细持仓不公开。"""
    url = "https://www.dpswang.com/match/list"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=12)
        if r.status_code != 200:
            return []
        return [{"note": "dpswang reachable, detailed holdings require player-page scrape"}]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────
# Aggregator
# ─────────────────────────────────────────────────────────────
def summarize(xq_cubes: list[dict], tgb: list[dict], ths: list[dict]) -> dict:
    high_return = 0
    s_tier = a_tier = b_tier = 0
    for c in xq_cubes:
        if "error" in c:
            continue
        try:
            tg = float(c.get("total_gain") or 0)
        except (TypeError, ValueError):
            tg = 0
        if tg > 50:
            high_return += 1
        if tg > 200:
            s_tier += 1
        elif tg > 100:
            a_tier += 1
        elif tg > 50:
            b_tier += 1
    return {
        "xueqiu_cubes_total": len([c for c in xq_cubes if "error" not in c]),
        "high_return_cubes": high_return,
        "s_tier_holders": s_tier,
        "a_tier_holders": a_tier,
        "b_tier_holders": b_tier,
        "tgb_mentions_count": len([t for t in tgb if "error" not in t]),
        "ths_evidence_count": len([t for t in ths if "error" not in t and "note" not in t]),
    }


def main(ticker: str) -> dict:
    ti = parse_ticker(ticker)

    # v2.7.1 · cached + new (cubes, meta) signature
    def _xq_call():
        cubes, meta = fetch_xueqiu_cubes(ti)
        return {"cubes": cubes, "meta": meta}

    xq_result = cached(ti.full, f"xq_cubes__{ti.code}", _xq_call, ttl=6 * 3600)
    xq = xq_result.get("cubes", []) if isinstance(xq_result, dict) else []
    xq_meta = xq_result.get("meta", {}) if isinstance(xq_result, dict) else {}

    time.sleep(0.5)
    tgb = cached(ti.full, f"tgb__{ti.code}", lambda: fetch_tgb_mentions(ti), ttl=12 * 3600)
    time.sleep(0.5)
    ths = cached(ti.full, f"ths_simu__{ti.code}", lambda: fetch_ths_simu(ti), ttl=12 * 3600)
    dps = fetch_dpswang(ti)

    summary = summarize(xq, tgb, ths)
    summary["xueqiu_login_required"] = bool(xq_meta.get("login_required"))
    summary["xueqiu_source"] = xq_meta.get("source", "http")

    note = "雪球 cubes API 是主数据源；其余 3 站点 ≥1 失败时 Claude 用 fallback_queries 补足"
    if xq_meta.get("login_required") and not xq:
        note = (
            "⚠️ XueQiu cubes 接口 2026 起需登录。当前未启用 Playwright 登录，0 cube 收录。"
            "如需启用：export UZI_XQ_LOGIN=1 然后 python -m lib.xueqiu_browser login 一次性登录。"
            "或 --skip-login-sources 接受跳过（其他维度不影响）。"
        )

    return {
        "ticker": ti.full,
        "data": {
            "xueqiu_cubes": xq,
            "xueqiu_meta": xq_meta,
            "tgb_mentions": tgb,
            "ths_simu": ths,
            "dpswang": dps,
            "summary": summary,
            "fallback_queries": [
                f"淘股吧 实盘 {ti.code} 持仓",
                f"挑战者杯 {ti.code}",
                f"雪球 实盘组合 {ti.code} 50%",
                f"全国期货实盘大赛 {ti.code}",
            ],
            "_note": note,
        },
        "source": "xueqiu + taoguba + 10jqka + dpswang",
        "fallback": bool(xq_meta.get("login_required") and not xq),
    }


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"
    print(json.dumps(main(arg), ensure_ascii=False, indent=2, default=str))
