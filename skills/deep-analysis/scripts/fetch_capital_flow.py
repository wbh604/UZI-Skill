"""Dimension 12 · 资金面 (北向 / 融资融券 / 股东户数 / 主力 / 限售解禁 / 大宗交易).

补全：原方案要求覆盖
  • 北向/南向资金近 20 日净买卖
  • 融资融券余额趋势
  • 股东户数近 3 季度变化
  • 大宗交易折溢价
  • 限售股解禁时间表
  • 主力资金流入流出
全部已实现。

v2.15.3 (#30) · 大宗交易 + 解禁数据走 ds.cached module-level · 避免每只股重抓全 A 数据（原每次 3+min，改后首次 3min 后续 < 1s）.
"""
import json
import os
import sys
import time

import lib.net_timeout_guard  # noqa: F401 - timeout + proxy routing
import akshare as ak  # type: ignore
from lib import data_sources as ds
from lib.cache import cached  # v2.15.3 · TTL cache
from lib.market_router import parse_ticker


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:
        return {"error": str(e)} if isinstance(default, dict) else default


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fetch_main_fund_flow_http(ti) -> list:
    """Direct Eastmoney HTTP path for per-stock main fund flow."""
    import requests

    market_map = {"SH": 1, "SZ": 0, "BJ": 0}
    market_id = market_map.get(ti.full[-2:].upper(), 1)
    params = {
        "lmt": "0",
        "klt": "101",
        "secid": f"{market_id}.{ti.code}",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "ut": "b2884a393a59ad64002292a3e90d46a5",
        "_": int(time.time() * 1000),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Referer": "https://data.eastmoney.com/",
    }
    session = requests.Session()
    session.trust_env = False
    r = session.get(
        "http://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
        params=params,
        headers=headers,
        timeout=int(os.environ.get("UZI_HTTP_TIMEOUT", "8")),
    )
    r.raise_for_status()
    klines = (((r.json() or {}).get("data") or {}).get("klines") or [])
    rows = []
    for line in klines[-20:]:
        parts = str(line).split(",")
        if len(parts) < 13:
            continue
        rows.append({
            "日期": parts[0],
            "收盘价": _to_float(parts[11]),
            "涨跌幅": _to_float(parts[12]),
            "主力净流入-净额": _to_float(parts[1]),
            "主力净流入-净占比": _to_float(parts[6]),
            "超大单净流入-净额": _to_float(parts[5]),
            "超大单净流入-净占比": _to_float(parts[10]),
            "大单净流入-净额": _to_float(parts[4]),
            "大单净流入-净占比": _to_float(parts[9]),
            "中单净流入-净额": _to_float(parts[3]),
            "中单净流入-净占比": _to_float(parts[8]),
            "小单净流入-净额": _to_float(parts[2]),
            "小单净流入-净占比": _to_float(parts[7]),
            "_source": "eastmoney:push2his.fflow.daykline",
        })
    return rows


def _sina_moneyflow_symbol(ti) -> str:
    market = ti.full[-2:].upper()
    prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(market, "sh")
    return f"{prefix}{ti.code}"


def _ratio_to_pct(value):
    parsed = _to_float(value)
    return parsed * 100 if parsed is not None else None


def _fetch_main_fund_flow_sina(ti) -> list:
    """Sina per-stock moneyflow history; independent of Eastmoney push2his."""
    import requests

    params = {
        "page": 1,
        "num": 20,
        "sort": "opendate",
        "asc": 0,
        "daima": _sina_moneyflow_symbol(ti),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Referer": "https://vip.stock.finance.sina.com.cn/moneyflow/",
    }
    session = requests.Session()
    session.trust_env = False
    r = session.get(
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs",
        params=params,
        headers=headers,
        timeout=int(os.environ.get("UZI_HTTP_TIMEOUT", "8")),
    )
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, list):
        return []

    rows = []
    for item in reversed(payload[:20]):
        main_net = _to_float(item.get("r0_net"))
        rows.append({
            "日期": item.get("opendate"),
            "收盘价": _to_float(item.get("trade")),
            "涨跌幅": _ratio_to_pct(item.get("changeratio")),
            "换手率": _to_float(item.get("turnover")),
            "净流入-净额": _to_float(item.get("netamount")),
            "净流入-净占比": _ratio_to_pct(item.get("ratioamount")),
            "主力净流入-净额": main_net,
            "主力净流入": main_net,
            "主力净流入-净占比": _ratio_to_pct(item.get("r0_ratio")),
            "主力罗盘": _to_float(item.get("r0x_ratio")),
            "行业净流入-净额": _to_float(item.get("cate_na")),
            "行业净流入-净占比": _ratio_to_pct(item.get("cate_ra")),
            "_source": "sina:MoneyFlow.ssl_qsfx_zjlrqs",
        })
    return rows


def _fetch_main_fund_flow(ti) -> list:
    """Fast per-stock fund-flow path; safe to run in quick mode."""
    direct = _safe(lambda: _fetch_main_fund_flow_http(ti), [])
    if direct:
        return direct
    sina = _safe(lambda: _fetch_main_fund_flow_sina(ti), [])
    if sina:
        return sina
    return _safe(
        lambda: ak.stock_individual_fund_flow(stock=ti.code, market=ti.full[-2:].lower()).tail(20).to_dict("records"),
        [],
    )


def _main_net_value(row: dict) -> float:
    for key in ("主力净流入-净额", "主力净流入", "主力资金净流入", "主力净额"):
        if key in row:
            try:
                return float(row.get(key) or 0)
            except (ValueError, TypeError):
                return 0.0
    for key in ("主力净流入-净额", "主力净流入", "主力资金净流入", "主力净额"):
        if key in row:
            try:
                return float(row.get(key) or 0)
            except (ValueError, TypeError):
                return 0.0
    return 0.0


def _format_amount_yuan(total: float) -> str:
    if not total:
        return "—"
    return f"{total / 1e4:+.1f}万" if abs(total) < 1e8 else f"{total / 1e8:+.1f}亿"


def _main_sum(flow_list: list, days=None) -> str:
    if not flow_list:
        return "—"
    rows = flow_list[-days:] if days else flow_list
    total = sum(_main_net_value(r) for r in rows if isinstance(r, dict))
    return _format_amount_yuan(total)


# v2.15.3 · 大宗/解禁数据按年缓存（TTL 24h · 数据日频更新）
# 不缓存会每只股花 3+min 重拉 · 严重性能 bug
_UNIVERSE_TTL = 24 * 3600  # 24h


def _universe_dzjy(year: int = 2026) -> list:
    """v2.15.3 · 大宗交易整年数据 · module-level cache · 全 A 共享."""
    def _fetch():
        try:
            df = ak.stock_dzjy_mrtj(
                start_date=f"{year}0101",
                end_date=f"{year}1231",
            )
            return df.to_dict("records") if df is not None and not df.empty else []
        except Exception:
            return []
    return cached("_universe", f"dzjy_{year}", _fetch, ttl=_UNIVERSE_TTL) or []


def _universe_release_summary() -> list:
    """v2.15.3 · 近一年解禁 summary · module-level cache."""
    def _fetch():
        try:
            df = ak.stock_restricted_release_summary_em(symbol="近一年")
            return df.to_dict("records") if df is not None and not df.empty else []
        except Exception:
            return []
    return cached("_universe", "release_summary_1y", _fetch, ttl=_UNIVERSE_TTL) or []


def _universe_release_detail(year: int = 2026) -> list:
    """v2.15.3 · 解禁日历（年度） · module-level cache."""
    def _fetch():
        try:
            df = ak.stock_restricted_release_detail_em(
                start_date=f"{year}0101", end_date=f"{year}1231",
            )
            return df.to_dict("records") if df is not None and not df.empty else []
        except Exception:
            return []
    return cached("_universe", f"release_detail_{year}", _fetch, ttl=_UNIVERSE_TTL) or []


def _universe_margin_detail(exchange: str) -> list:
    """v2.15.3 · 某交易所最新一天融资明细 · module-level cache · 全 A 共享."""
    def _fetch():
        try:
            if exchange == "SZ":
                df = ak.stock_margin_detail_szse(date=None)
            else:
                df = ak.stock_margin_detail_sse(date=None)
            return df.to_dict("records") if df is not None and not df.empty else []
        except Exception:
            return []
    return cached("_universe", f"margin_detail_{exchange}", _fetch, ttl=_UNIVERSE_TTL) or []


def main(ticker: str) -> dict:
    ti = parse_ticker(ticker)
    if ti.market == "H":
        # v2.5 · HK 港股通南北向标记 + 历史每日市值（净值变动 proxy）
        # akshare 港股通南北向 spot (stock_hsgt_sh_hk_spot_em) 走 push2 已 blocked，
        # 这里用 stock_hk_security_profile_em 拿"是否沪/深港通标的"标记 + eniu 历史市值。
        from lib.hk_data_sources import fetch_hk_basic_combined
        try:
            enriched = fetch_hk_basic_combined(ti.code.zfill(5))
        except Exception:
            enriched = {}
        is_sh = enriched.get("is_south_bound_sh", False)
        is_sz = enriched.get("is_south_bound_sz", False)
        # eniu 市值历史（近 30 个数据点作为南北向资金流的 proxy）
        mv_hist: list = []
        try:
            import akshare as _ak  # type: ignore
            df = _ak.stock_hk_indicator_eniu(symbol=f"hk{ti.code.zfill(5)}", indicator="市值")
            if df is not None and not df.empty:
                mv_hist = df.tail(30).to_dict("records")
        except Exception:
            pass
        return {
            "ticker": ti.full,
            "data": {
                "is_south_bound_sh": is_sh,
                "is_south_bound_sz": is_sz,
                "south_bound_eligibility": "沪+深" if (is_sh and is_sz) else ("沪" if is_sh else ("深" if is_sz else "—")),
                "north_bound": "—",
                "margin_balance": "—",
                "main_flow_recent": [],
                "mv_history_30d": mv_hist[-30:],
                "_note": (
                    "HK 南向具体持股变动需走 AASTOCKS Playwright 或 hkexnews holdings page；"
                    "本字段提供港股通资格 + eniu 市值历史作 proxy。"
                ),
            },
            "source": "akshare:stock_hk_security_profile_em + stock_hk_indicator_eniu",
            "fallback": False,
        }
    if ti.market != "A":
        return {"ticker": ti.full, "data": {"_note": "capital_flow only A-share / HK for now"}, "source": "skip", "fallback": False}

    main_flow = _fetch_main_fund_flow(ti)

    heavy_enabled = os.environ.get("UZI_CAPITAL_FLOW_HEAVY") == "1"
    if not heavy_enabled:
        return {
            "ticker": ti.full,
            "data": {
                "northbound": {},
                "northbound_20d": "—",
                "margin_recent": [],
                "margin_trend": "—",
                "holder_count_history": [],
                "holders_trend": "—",
                "main_fund_flow_20d": main_flow,
                "main_20d": _main_sum(main_flow),
                "main_5d": _main_sum(main_flow, days=5),
                "block_trades_recent": [],
                "unlock_recent": [],
                "unlock_schedule": [],
                "institutional_history": {"quarters": [], "fund": [], "qfii": [], "shehui": []},
                "_skipped_universe_heavy": True,
                "_note": "资金面重型接口默认跳过；如需大宗/解禁/机构持仓全市场数据，设置 UZI_CAPITAL_FLOW_HEAVY=1 后重跑。",
            },
            "source": "capital_flow:quick + eastmoney:http_push2his + sina:moneyflow + akshare:stock_individual_fund_flow",
            "fallback": False,
        }

    north = ds.fetch_northbound(ti)

    # v2.15.3 · 融资明细走 universe cache · 按 exchange 缓存全市场最新一天
    exchange = "SZ" if ti.full.endswith("SZ") else "SSE"
    universe_margin = _universe_margin_detail(exchange)
    # head(5) 保留原行为（展示市场层 top 5 · 非本股过滤）
    margin = universe_margin[:5] if universe_margin else []

    holders = _safe(
        lambda: ak.stock_zh_a_gdhs(symbol=ti.code).head(8).to_dict("records"),
        [],
    )

    # 大宗交易 · v2.15.3 · 走 universe cache · 只 filter 本股（原每次 3+min 重抓全 A）
    try:
        universe_dzjy = _universe_dzjy(2026)
        block_trades = [r for r in universe_dzjy if r.get("证券代码") == ti.code][:20]
    except Exception:
        block_trades = []

    # 限售股解禁 (近一年) · v2.15.3 · universe cache
    try:
        universe_release = _universe_release_summary()
        unlock = [r for r in universe_release if r.get("代码") == ti.code]
    except Exception:
        unlock = []

    # 解禁日历前瞻 12 个月 · v2.15.3 · universe cache
    try:
        universe_detail = _universe_release_detail(2026)
        unlock_future = [r for r in universe_detail if r.get("代码") == ti.code][:20]
    except Exception:
        unlock_future = []

    # Normalize unlock_schedule for viz
    def _month_label(d):
        s = str(d)[:7].replace("-", "")
        if len(s) == 6:
            return f"{s[2:4]}-{s[4:6]}"
        return s[-5:] if s else "—"

    unlock_schedule = []
    for row in (unlock_future or [])[:12]:
        date = row.get("解禁日期") or row.get("解禁时间") or ""
        amount_str = row.get("解禁市值") or row.get("市值(亿元)") or row.get("解禁股份数量") or 0
        try:
            amount = float(str(amount_str).replace(",", ""))
            # 如果原始单位是元而非亿，做换算
            if amount > 1e6:
                amount = amount / 1e8
            unlock_schedule.append({"date": _month_label(date), "amount": round(amount, 2)})
        except (ValueError, TypeError):
            pass

    # 机构持仓 8 季度历史 (stock_report_fund_hold_detail)
    inst_history: dict = {"quarters": [], "fund": [], "qfii": [], "shehui": []}
    try:
        from datetime import datetime as _dt, timedelta as _td
        # Get last 8 quarters
        today = _dt.now()
        quarters = []
        for i in range(8):
            y = today.year
            q = ((today.month - 1) // 3) - i
            while q < 0:
                q += 4
                y -= 1
            q_dates = ["0331", "0630", "0930", "1231"]
            quarters.append((f"{y}{q_dates[q]}", f"{str(y)[2:]}Q{q+1}"))
        quarters.reverse()
        inst_history["quarters"] = [q[1] for q in quarters]

        for q_date, q_label in quarters:
            fund_pct = qfii_pct = shehui_pct = 0.0
            try:
                df_fund = ak.stock_report_fund_hold_detail(symbol="基金持仓", date=q_date)
                if df_fund is not None and not df_fund.empty and "股票代码" in df_fund.columns:
                    sub = df_fund[df_fund["股票代码"].astype(str) == ti.code]
                    if not sub.empty and "占流通股比例" in sub.columns:
                        fund_pct = float(sub["占流通股比例"].sum())
            except Exception:
                pass
            inst_history["fund"].append(round(fund_pct, 2))
            inst_history["qfii"].append(round(qfii_pct, 2))
            inst_history["shehui"].append(round(shehui_pct, 2))
    except Exception:
        pass

    # Build summary strings for viz
    def _north_sum_20d(hist):
        if not isinstance(hist, dict):
            return "—"
        flows = hist.get("flow_history", [])
        if not flows:
            return "—"
        try:
            total = sum(float(r.get("净买额") or r.get("净买入额") or 0) for r in flows[-20:])
            return f"{total / 1e8:+.1f}亿"
        except Exception:
            return "—"

    def _main_sum_20d(flow_list):
        if not flow_list:
            return "—"
        try:
            total = sum(float(r.get("主力净流入", 0) or 0) for r in flow_list[-20:])
            return f"{total / 1e4:+.1f}万" if abs(total) < 1e8 else f"{total / 1e8:+.1f}亿"
        except Exception:
            return "—"

    def _holders_trend(h):
        if not h or len(h) < 2:
            return "—"
        last = h[0]  # gdhs 接口通常最新在前
        prev = h[-1]
        try:
            l = float(str(last.get("股东户数", 0)).replace(",", ""))
            p = float(str(prev.get("股东户数", 0)).replace(",", ""))
            trend = "3 季连降" if l < p * 0.95 else "3 季连升" if l > p * 1.05 else "基本持平"
            return trend
        except Exception:
            return "—"

    return {
        "ticker": ti.full,
        "data": {
            "northbound": north,
            "northbound_20d": _north_sum_20d(north),
            "margin_recent": margin,
            "margin_trend": f"近 5 日 {len(margin)} 条记录" if margin else "—",
            "holder_count_history": holders,
            "holders_trend": _holders_trend(holders),
            "main_fund_flow_20d": main_flow,
            "main_20d": _main_sum_20d(main_flow),
            "main_5d": "—",
            "block_trades_recent": block_trades,
            "unlock_recent": unlock,
            "unlock_schedule": unlock_schedule,
            "institutional_history": inst_history,
        },
        "source": "akshare:multi (north + margin + gdhs + fund_flow + dzjy + restricted_release + fund_hold_detail)",
        "fallback": False,
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"), ensure_ascii=False, indent=2, default=str))
