"""Restore unknowns at the feature boundary before rules consume them.

Legacy calculations still use numeric defaults internally. This contract maps
their outputs back to source evidence and propagates missing dependencies.
Institutional models can explicitly opt into defaults via sanitize_features.
"""
from __future__ import annotations

import re

from lib.capital_flow_history import window_net


def apply_feature_evidence(f: dict, raw: dict) -> dict:
    from lib.stock_features import _f, _market_cap_to_yi

    dimensions = (raw or {}).get("dimensions") or {}

    def data(key):
        entry = dimensions.get(key) or {}
        if entry.get("status") in {"error", "failed", "timeout", "unavailable"}:
            return {}
        return entry.get("data") or {}

    basic, fin, kline = (data(k) for k in ("0_basic", "1_financials", "2_kline"))
    valuation, industry = data("10_valuation"), data("7_industry")
    capital, gov, events = (data(k) for k in ("12_capital_flow", "11_governance", "15_events"))
    health, indicators = fin.get("financial_health") or {}, kline.get("indicators") or {}

    def numbers(source, fields):
        for feature, field in fields.items():
            f[feature] = _f(source.get(field), None)

    def first(*values):
        return next((n for v in values if (n := _f(v, None)) is not None), None)

    numbers(basic, {k: k for k in ("price", "change_pct", "staff_num")})
    for feature, alt in (("market_cap_yi", "market_cap"), ("circulating_cap_yi", "circulating_cap")):
        value = first(basic.get(feature), basic.get(alt))
        f[feature] = _market_cap_to_yi(value) if value is not None else None
    numbers(health, {k: k for k in ("current_ratio", "debt_ratio", "fcf_margin", "roic")})
    numbers(health, {"total_debt_yi": "total_debt", "cash_yi": "cash", "equity_yi": "equity"})
    numbers(fin, {"gross_margin": "gross_margin"})
    numbers(fin.get("dupont") or {}, {
        "dupont_net_margin": "net_margin_pct", "dupont_asset_turnover": "asset_turnover",
        "dupont_equity_multiplier": "equity_multiplier", "dupont_roe": "roe_reconstructed_pct",
    })
    f["ocf_to_net_income_ratio"] = first(fin.get("ocf_to_net_income_ratio"), health.get("ocf_to_net_income_ratio"))
    for prefix, history, ttm, growth in (
        ("revenue", "revenue_history", "revenue_ttm", "revenue_growth_yoy"),
        ("net_profit", "net_profit_history", "net_profit_ttm", "net_profit_growth_yoy"),
    ):
        values = [_f(v, None) for v in fin.get(history) or []]
        latest = values[-1] if values else None
        f[prefix + "_latest_yi"] = first(fin.get(ttm), latest)
        yoy = _f(fin.get(growth), None)
        if yoy is None and len(values) >= 2 and latest is not None and values[-2] not in (None, 0):
            yoy = (latest - values[-2]) / abs(values[-2]) * 100
        f[prefix + "_growth_latest"] = yoy
        if prefix == "revenue":
            f["revenue_growth_3y_cagr"] = (
                ((latest / values[-4]) ** (1 / 3) - 1) * 100
                if len(values) >= 4 and latest is not None and latest >= 0
                and values[-4] is not None and values[-4] > 0 else None
            )
        else:
            complete = bool(values) and all(v is not None for v in values)
            f["net_profit_5y_positive"] = sum(v > 0 for v in values[-5:]) if complete else None
            streak = 0
            if complete:
                for value in reversed(values):
                    if value <= 0:
                        break
                    streak += 1
            f["consecutive_profit_years"] = streak if complete else None

    roe = [_f(v, None) for v in fin.get("roe_history") or []]
    valid_roe = [v for v in roe[-5:] if v is not None]
    f["roe_latest"] = roe[-1] if roe else None
    f["roe_5y_avg"] = sum(valid_roe) / len(valid_roe) if valid_roe else None
    f["roe_5y_min"] = min(valid_roe) if valid_roe else None
    for threshold in (10, 15):
        f[f"roe_5y_above_{threshold}"] = (
            sum(v > threshold for v in roe[-5:])
            if roe and all(v is not None for v in roe[-5:]) else None
        )
    f["roe_trend_up"] = (roe[-1] > sum(roe[:-1]) / len(roe[:-1])
                          if len(roe) >= 3 and all(v is not None for v in roe) else None)
    f["consecutive_dividend_years"] = len(fin["dividend_years"]) if isinstance(fin.get("dividend_years"), list) else None
    amounts = [_f(v, None) for v in fin.get("dividend_amounts") or []]
    f["total_dividend_5y_per_10"] = sum(amounts[-5:]) if amounts and all(v is not None for v in amounts[-5:]) else None
    f["dividend_yield"] = first(basic.get("dividend_yield_ttm"), valuation.get("dividend_yield"))
    f["pe"] = first(basic.get("pe_ttm"), valuation.get("pe"))
    f["pb"] = first(basic.get("pb"), valuation.get("pb"))
    numbers(valuation, {"industry_pe": "industry_pe"})
    f["dcf_intrinsic_yi"] = _f(valuation.get("dcf"), None)
    numbers(kline, {"rsi": "rsi"})
    numbers(indicators, {k: k for k in ("kdj_k", "kdj_d", "kdj_j", "williams_r")})
    f["kdj_golden_cross"] = f["kdj_k"] > f["kdj_d"] if f["kdj_k"] is not None and f["kdj_d"] is not None else None
    f["obv_trend_up"] = indicators.get("obv_trend_up") if isinstance(indicators.get("obv_trend_up"), bool) else None
    numbers(kline.get("kline_stats") or {}, {"ytd_return": "ytd_return", "volatility_1y": "volatility", "max_drawdown_1y": "max_drawdown"})
    candles = kline.get("candles_60d") or []
    for output, field, reducer in (("pct_from_60d_high", "high", max), ("pct_from_60d_low", "low", min)):
        values = [_f(row.get(field), None) for row in candles]
        close = _f(candles[-1].get("close"), None) if candles else None
        if close is None or close <= 0 or not values or any(v is None or v <= 0 for v in values):
            f[output] = None
        else:
            f[output] = (close / reducer(values) - 1) * 100

    research = data("6_research")
    numbers(research, {k: k for k in ("buy_rating_pct", "target_price_avg", "consensus_eps_2026", "consensus_pe_2026")})
    f["research_coverage"] = first(research.get("coverage_count"), research.get("report_count"))
    numbers(data("17_sentiment"), {"sentiment_heat": "thermometer_value", "sentiment_positive_pct": "positive_pct"})
    numbers(data("19_contests").get("summary") or {}, {"xq_cube_count": "xueqiu_cubes_total", "xq_high_return_count": "high_return_cubes"})
    numbers(data("14_moat").get("scores") or {}, {"moat_" + k: k for k in ("intangible", "switching", "network", "scale")})

    # Text/list-derived flags need an actual observation, not a fallback label.
    for source, field, outputs in (
        (kline, "stage", ("stage_num",)), (kline, "ma_align", ("ma_bull_aligned",)),
        (kline, "macd", ("macd_golden_cross",)),
        (industry, "lifecycle", ("industry_is_growing", "industry_in_decline")),
        (capital, "holders_trend", ("holders_concentrating",)),
        (capital, "unlock_schedule", ("unlock_pressure_12m",)),
        (gov, "pledge", ("has_pledge_issue",)),
        (events, "event_timeline", ("recent_events_count", "has_positive_catalyst", "has_negative_catalyst")),
        (data("18_trap"), "trap_level", ("trap_level", "is_safe")),
        (data("3_macro"), "rate_cycle", ("macro_rate_cycle", "macro_rate_easing")),
        (data("13_policy"), "policy_dir", ("policy_supportive", "policy_tightening")),
    ):
        if source.get(field) is None or source.get(field) in ("", "—", "N/A"):
            for key in outputs:
                f[key] = None
    numbers(data("18_trap"), {"trap_signals_hit": "signals_hit_count"})
    for key in ("vcp_hint", "is_industry_leader", "no_violations", "insider_net_buy", "gross_margin_expanding"):
        f[key] = None  # No validated calculation/provider for these claims yet.

    peer_table = data("4_peers").get("peer_table")
    peer_pes = [_f(row.get("pe"), None) for row in peer_table or [] if not row.get("is_self")]
    peer_pes = [value for value in peer_pes if value is not None and value > 0]
    f["peers_count"] = len(peer_table) if isinstance(peer_table, list) else None
    f["peer_avg_pe"] = sum(peer_pes) / len(peer_pes) if peer_pes else None
    if not f.get("industry_rank"):
        f["industry_rank"] = None
    managers = (raw or {}).get("fund_managers")
    f["fund_manager_count"] = len(managers) if isinstance(managers, list) and not any(m.get("error") for m in managers) else None
    returns = [_f(m.get("return_5y"), None) for m in managers or []]
    returns = [value for value in returns if value is not None]
    f["fund_manager_max_5y_return"] = max(returns) if returns else None
    f["has_top_fund_holder"] = any(value > 100 for value in returns) if returns else None
    growth_raw = industry.get("growth")
    growth = _f(growth_raw, None)
    if growth is None and isinstance(growth_raw, str):
        match = re.search(r"([+\-]?\d+(?:\.\d+)?)\s*%", growth_raw)
        growth = _f(match.group(1), None) if match else None
    f["industry_growth"] = f["industry_growth_pct"] = growth
    if not (f.get("market_cap_yi") and _f((industry.get("cninfo_metrics") or {}).get("total_mcap_yi"), None)):
        f["market_share"] = None
    ocf = _f(fin.get("operating_cash_flow_yi"), None)
    f["fcf_known"] = ocf is not None
    f["fcf_positive"] = ocf > 0 if ocf is not None else None
    f["fcf_is_proxy"] = ocf is None
    profit = f["net_profit_latest_yi"]
    f["fcf_latest_yi"] = round(ocf, 2) if ocf is not None else round(profit * 0.8, 2) if profit is not None else None
    if f["net_profit_latest_yi"] is None:
        f["ebitda_yi"] = None
    industry_text = str(basic.get("industry") or "").strip()
    if industry_text in {"", "—", "-", "N/A"} and not data("5_chain"):
        f["ai_chain_hit"] = None
    if f["ai_chain_hit"] is None or f["market_cap_yi"] is None:
        f["ai_chokepoint_score"] = None
    elif f["ai_chain_hit"] and (f["moat_switching"] is None or f["moat_scale"] is None):
        f["ai_chokepoint_score"] = None
    f["ai_score_is_heuristic"] = True

    net = window_net(capital.get("main_fund_flow_20d"), 5)
    f["main_fund_5d_net_yi"] = round(net / 1e8, 2) if net is not None else None
    f["main_fund_net_positive"] = net > 0 if net is not None else None
    f["northbound_20d_yi"] = f["main_fund_5d_net_yi"]
    f["northbound_net_positive"] = f["main_fund_net_positive"]

    # Invalidate derived values whenever any necessary input is unavailable.
    dependencies = {
        "pe_x_pb": ("pe", "pb"), "pe_vs_industry": ("pe", "industry_pe"),
        "vs_peer_avg_pe": ("pe", "peer_avg_pe"),
        "safety_margin": ("dcf_intrinsic_yi", "market_cap_yi"),
        "rsi_overbought": ("rsi",), "rsi_oversold": ("rsi",),
        "williams_overbought": ("williams_r",), "williams_oversold": ("williams_r",),
        "upside_to_target": ("target_price_avg", "price"),
        "consensus_growth_to_2026": ("consensus_eps_2026",),
        "moat_total": ("moat_intangible", "moat_switching", "moat_network", "moat_scale"),
        "moat_clear": ("moat_total",), "ai_irreplaceable": ("moat_switching", "moat_scale"),
        "ai_smallcap": ("market_cap_yi",),
        "shares_outstanding_yi": ("market_cap_yi", "price"),
        "eps": ("net_profit_latest_yi", "shares_outstanding_yi"),
        "bvps": ("equity_yi", "shares_outstanding_yi"),
        "ps": ("market_cap_yi", "revenue_latest_yi"),
        "peg": ("pe", "revenue_growth_3y_cagr"),
    }
    for output, inputs in dependencies.items():
        if any(f.get(key) is None for key in inputs):
            f[output] = None
    f["moat_known"] = f["moat_total"] is not None
    # Recompute ratios after normalization so a real zero never selects a fallback.
    def ratio(output, numerator, denominator, multiplier=1, offset=0):
        n, d = f.get(numerator), f.get(denominator)
        f[output] = (n / d + offset) * multiplier if n is not None and d is not None and d > 0 else None

    f["pe_x_pb"] = f["pe"] * f["pb"] if f["pe"] is not None and f["pb"] is not None else None
    ratio("pe_vs_industry", "pe", "industry_pe", 100, -1)
    ratio("vs_peer_avg_pe", "pe", "peer_avg_pe", 100, -1)
    ratio("safety_margin", "dcf_intrinsic_yi", "market_cap_yi", 100, -1)
    ratio("upside_to_target", "target_price_avg", "price", 100, -1)
    ratio("shares_outstanding_yi", "market_cap_yi", "price")
    ratio("ps", "market_cap_yi", "revenue_latest_yi")
    ratio("eps", "net_profit_latest_yi", "shares_outstanding_yi")
    ratio("bvps", "equity_yi", "shares_outstanding_yi")
    ratio("peg", "pe", "revenue_growth_3y_cagr")
    if _f(basic.get("eps"), None) in (None, 0):
        f["consensus_growth_to_2026"] = None
    for key, source in {"pe_ttm": "pe", "rev_growth_3y": "revenue_growth_3y_cagr", "rev_growth_yoy": "revenue_growth_latest", "roe": "roe_latest", "net_profit_growth_3y": "net_profit_growth_latest"}.items():
        f[key] = f[source]
    f["missing_features"] = sorted(key for key, value in f.items() if value is None)
    return f
