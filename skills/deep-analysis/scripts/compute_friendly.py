"""Tier 4 友好层计算器.

输入：raw_data.json + dimensions.json
输出：friendly 字段 for synthesis.json
  - scenarios: 5 情景模拟（基于历史波动率）
  - exit_triggers: 5 条自动生成的离场触发条件
  - next_day_bias: 次日方向分（启发式，不是训练模型）
  - backtest: 过去 3 个月滚动回测（OHLCV-only）
  - similar_stocks: pass-through from fetch_similar_stocks

Usage:
  python compute_friendly.py {ticker}
"""
from __future__ import annotations

import json
import math
import sys
from statistics import mean
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from lib.cache import read_task_output  # noqa: E402
from lib.market_router import parse_ticker  # noqa: E402
from lib.stock_features import extract_features  # noqa: E402


def _parse_pct(s) -> float:
    try:
        return float(str(s).replace("%", "").replace("+", ""))
    except (ValueError, TypeError):
        return 0.0


def compute_scenarios(raw: dict, dimensions: dict) -> dict:
    """5 级情景（最坏/偏差/合理/乐观/极致乐观）基于历史波动率。"""
    basic = (raw.get("dimensions", {}).get("0_basic") or {}).get("data") or {}
    kline = (raw.get("dimensions", {}).get("2_kline") or {}).get("data") or {}
    research = (raw.get("dimensions", {}).get("6_research") or {}).get("data") or {}

    entry_price = basic.get("price") or 0
    stats = kline.get("kline_stats") or {}
    # 1 年化波动率
    vol_str = stats.get("volatility", "30%")
    sigma = _parse_pct(vol_str) or 30.0

    # 研报目标价隐含的预期收益
    upside_str = research.get("upside", "+15%")
    base_return = _parse_pct(upside_str) or 15.0

    return {
        "entry_price": entry_price,
        "cases": [
            {"name": "最坏情况", "probability": "5%",  "return": round(-2 * sigma, 1)},
            {"name": "偏差情况", "probability": "25%", "return": round(-1 * sigma + base_return * 0.2, 1)},
            {"name": "合理情况", "probability": "40%", "return": round(base_return, 1)},
            {"name": "乐观情况", "probability": "25%", "return": round(1 * sigma + base_return * 0.5, 1)},
            {"name": "极致乐观", "probability": "5%",  "return": round(2 * sigma + base_return, 1)},
        ],
    }


def compute_exit_triggers(raw: dict, dimensions: dict, synthesis: dict) -> list[str]:
    """自动从已有数据生成 5 条离场触发条件。"""
    triggers = []
    basic = (raw.get("dimensions", {}).get("0_basic") or {}).get("data") or {}
    kline = (raw.get("dimensions", {}).get("2_kline") or {}).get("data") or {}
    val = (raw.get("dimensions", {}).get("10_valuation") or {}).get("data") or {}
    chain = (raw.get("dimensions", {}).get("5_chain") or {}).get("data") or {}
    lhb = (raw.get("dimensions", {}).get("16_lhb") or {}).get("data") or {}
    research = (raw.get("dimensions", {}).get("6_research") or {}).get("data") or {}

    # 1. 技术止损 ~ MA60
    ma60 = (kline.get("ma60_60d") or [])
    ma60_last = next((v for v in reversed(ma60) if v), None)
    if ma60_last:
        triggers.append(f"股价跌破 ¥{ma60_last:.2f}（60 日均线支撑位）→ 无条件止损")
    else:
        price = basic.get("price") or 0
        triggers.append(f"股价跌破 ¥{price * 0.88:.2f}（当前价 -12%）→ 无条件止损")

    # 2. 基本面恶化 — 大客户
    downstream = chain.get("downstream", "")
    if downstream and downstream != "—":
        main_client = downstream.split("/")[0].strip()
        triggers.append(f"{main_client} 季度指引下修 > 10% → 产业链逻辑动摇")
    else:
        triggers.append("下季度营收同比转负 → 基本面反转信号")

    # 3. 业绩不达
    growth_str = research.get("upside", "+15%")
    g = _parse_pct(growth_str)
    if g > 0:
        min_growth = max(10, int(g - 15))
        triggers.append(f"下次业绩预告低于 +{min_growth}% → 预期管理失守")
    else:
        triggers.append("连续两期业绩不及券商预期中位数 → 逻辑失效")

    # 4. 游资撤离
    matched = lhb.get("matched_youzi", "")
    if isinstance(matched, list):
        matched_str = " / ".join(matched[:2])
    else:
        matched_str = str(matched).split("/")[0] if matched else "顶级游资"
    if matched_str and matched_str not in ("", "—"):
        triggers.append(f"{matched_str} 席位大额卖出 > 2 亿 → 顶级资金撤离信号")

    # 5. 估值泡沫
    pe_quant = val.get("pe_quantile", "")
    import re
    m = re.search(r'(\d+)', str(pe_quant))
    if m:
        cur_q = int(m.group(1))
        target = min(95, cur_q + 15)
        triggers.append(f"PE 站上 5 年 {target} 分位（≈ {val.get('pe', '—')} × {1 + (target - cur_q) / 100:.2f}）→ 泡沫区获利了结")
    else:
        triggers.append("PE 站上 5 年 90 分位 → 泡沫区获利了结")

    return triggers[:5]


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _component_score(base: float, deltas: list[float]) -> float:
    return _clamp(base + sum(deltas))


def _parse_date(value) -> str:
    text = str(value or "")
    return text[:10]


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_kline_bars(raw: dict, ticker: str) -> list[dict]:
    """Load daily bars for backtest from cache, fallback to raw candles_60d."""
    bars: list[dict] = []

    def _coerce(rows: list[dict]) -> list[dict]:
        out = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            out.append({
                "date": _parse_date(row.get("Date") or row.get("date")),
                "open": _safe_float(row.get("Open") or row.get("open")),
                "high": _safe_float(row.get("High") or row.get("high")),
                "low": _safe_float(row.get("Low") or row.get("low")),
                "close": _safe_float(row.get("Close") or row.get("close")),
                "volume": _safe_float(row.get("Volume") or row.get("volume")),
            })
        return [r for r in out if r["date"] and r["close"] > 0]

    ti = parse_ticker(ticker or (raw or {}).get("ticker", ""))
    cache_root = HERE / ".cache" / ti.full / "api_cache"
    if cache_root.exists():
        candidates = sorted(
            cache_root.glob(f"kline__{ti.code}*daily*json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            candidates = sorted(
                cache_root.glob("kline__*daily*json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        for path in candidates:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                rows = payload.get("data") if isinstance(payload, dict) else payload
                bars = _coerce(rows if isinstance(rows, list) else [])
                if bars:
                    return bars
            except Exception:
                continue

    candles = (((raw or {}).get("dimensions", {}).get("2_kline") or {}).get("data") or {}).get("candles_60d") or []
    bars = _coerce(candles)
    return bars


def _moving_average(values: list[float], n: int) -> float | None:
    if len(values) < n or n <= 0:
        return None
    return sum(values[-n:]) / n


def _stage_from_bars(closes: list[float], ma200: float | None) -> int:
    if len(closes) < 60 or ma200 is None:
        return 0
    last = closes[-1]
    ma200_series = [sum(closes[max(0, i - 199):i + 1]) / min(i + 1, 200) for i in range(len(closes))]
    ma200_now = ma200_series[-1]
    ma200_60ago = ma200_series[-60] if len(ma200_series) >= 60 else ma200_series[0]
    above = last > ma200_now
    rising = ma200_now > ma200_60ago
    if above and rising:
        return 2
    if not above and rising:
        return 1
    if above and not rising:
        return 3
    return 4


def _ma_align_from_bars(closes: list[float]) -> str:
    ma5 = _moving_average(closes, 5)
    ma10 = _moving_average(closes, 10)
    ma20 = _moving_average(closes, 20)
    ma60 = _moving_average(closes, 60)
    ma120 = _moving_average(closes, 120)
    if not all(v is not None for v in (ma5, ma10, ma20, ma60, ma120)):
        return "非多头"
    if ma5 > ma10 > ma20 > ma60 > ma120:
        return "多头排列"
    if ma5 < ma10 < ma20 < ma60 < ma120:
        return "空头排列"
    return "非多头"


def _backtest_snapshot(ticker: str, bars: list[dict], end_idx: int) -> dict:
    hist = bars[: end_idx + 1]
    closes = [b["close"] for b in hist]
    highs = [b["high"] for b in hist]
    lows = [b["low"] for b in hist]

    last_close = closes[-1]
    ma200 = _moving_average(closes, 200)
    ma200_series = [sum(closes[max(0, i - 199):i + 1]) / min(i + 1, 200) for i in range(len(closes))]
    stage = _stage_from_bars(closes, ma200)

    if len(closes) >= 2:
        start_idx = max(0, len(closes) - 252)
        base_close = closes[start_idx]
        ytd_return = ((last_close - base_close) / base_close * 100) if base_close else 0.0
        returns = [
            (closes[i] / closes[i - 1] - 1)
            for i in range(max(1, len(closes) - 252), len(closes))
            if closes[i - 1] > 0
        ]
        vol = (mean([(r - mean(returns)) ** 2 for r in returns]) ** 0.5 * (252 ** 0.5) * 100) if len(returns) > 1 else 0.0
        peak = closes[start_idx]
        max_dd = 0.0
        for c in closes[start_idx:]:
            if c > peak:
                peak = c
            dd = (c - peak) / peak * 100 if peak else 0.0
            if dd < max_dd:
                max_dd = dd
    else:
        ytd_return = 0.0
        vol = 0.0
        max_dd = 0.0

    candles_60d = [
        {
            "date": row["date"],
            "open": round(row["open"], 2),
            "close": round(row["close"], 2),
            "high": round(row["high"], 2),
            "low": round(row["low"], 2),
        }
        for row in hist[-60:]
    ]

    return {
        "ticker": ticker,
        "market": parse_ticker(ticker).market,
        "dimensions": {
            "0_basic": {
                "data": {
                    "name": (parse_ticker(ticker).code or ticker),
                    "code": parse_ticker(ticker).code or ticker,
                    "market": parse_ticker(ticker).market,
                    "price": last_close,
                }
            },
            "2_kline": {
                "data": {
                    "stage": f"Stage {stage}" if stage else "—",
                    "ma_align": _ma_align_from_bars(closes),
                    "candles_60d": candles_60d,
                    "kline_stats": {
                        "ytd_return": f"{ytd_return:+.1f}%",
                        "volatility": f"{vol:.1f}%",
                        "max_drawdown": f"{max_dd:.1f}%",
                    },
                }
            },
        },
    }


def compute_next_day_backtest(
    raw: dict,
    dimensions: dict | None = None,
    *,
    months: int = 3,
    thresholds: list[int] | None = None,
) -> dict:
    """Backtest the next-day bias over the last ~3 months of bars.

    This is deliberately OHLCV-only to avoid leakage from future fundamentals/news.
    """
    ticker = (raw or {}).get("ticker", "")
    bars = _load_kline_bars(raw or {}, ticker)
    if len(bars) < 30:
        return {}

    window = min(len(bars), 63 if months == 3 else max(20, months * 21))
    start = max(0, len(bars) - window)
    eval_start = start
    eval_end = len(bars) - 5
    if eval_end <= eval_start:
        return {}

    records = []
    for idx in range(eval_start, eval_end):
        snap = _backtest_snapshot(ticker, bars, idx)
        bias = compute_next_day_bias(snap, snap.get("dimensions", {}))
        cur = bars[idx]
        next_close = bars[idx + 1]["close"]
        week_close = bars[idx + 5]["close"]
        next_ret = (next_close - cur["close"]) / cur["close"] * 100 if cur["close"] else 0.0
        week_ret = (week_close - cur["close"]) / cur["close"] * 100 if cur["close"] else 0.0
        records.append({
            "date": cur["date"],
            "score": bias["score"],
            "confidence": bias["confidence"],
            "direction": bias["direction"],
            "next_day_return": round(next_ret, 2),
            "week_return": round(week_ret, 2),
            "next_day_hit": next_ret > 0,
            "week_win": week_ret > 0,
        })

    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 2) if values else 0.0

    sweep = []
    thresholds = thresholds or list(range(35, 66))
    for n in thresholds:
        selected = [r for r in records if r["score"] >= n]
        if not selected:
            continue
        sweep.append({
            "n": n,
            "buy_count": len(selected),
            "next_day_hit_rate": round(sum(1 for r in selected if r["next_day_hit"]) / len(selected) * 100, 1),
            "week_win_rate": round(sum(1 for r in selected if r["week_win"]) / len(selected) * 100, 1),
            "avg_week_return": _avg([r["week_return"] for r in selected]),
            "avg_next_day_return": _avg([r["next_day_return"] for r in selected]),
        })

    best = None
    for item in sweep:
        if best is None:
            best = item
            continue
        candidate = (
            item["week_win_rate"],
            item["avg_week_return"],
            item["buy_count"],
            -abs(item["n"] - 50),
        )
        current = (
            best["week_win_rate"],
            best["avg_week_return"],
            best["buy_count"],
            -abs(best["n"] - 50),
        )
        if candidate > current:
            best = item

    latest = records[-1]
    latest_buy = best["n"] if best else None
    current_signal = latest["score"] >= latest_buy if latest_buy is not None else False

    return {
        "window_days": len(records),
        "window_start": records[0]["date"],
        "window_end": records[-1]["date"],
        "bars_used": len(bars),
        "thresholds": sweep,
        "best_threshold": best,
        "latest": {
            **latest,
            "buy_signal": current_signal,
            "threshold": latest_buy,
        },
        "methodology": "OHLCV-only rolling backtest; score calculated with historical bars only, no future fundamentals/news.",
    }


def compute_next_day_bias(raw: dict, dimensions: dict, features: dict | None = None) -> dict:
    """Heuristic next-day direction score.

    这是一个可解释的启发式分数，不是训练出来的预测模型。
    输出分数越高越偏多，越低越偏空。
    """
    feat = features or extract_features(raw, dimensions)
    dims = raw.get("dimensions", {}) or {}
    basic = (dims.get("0_basic") or {}).get("data") or {}
    kline = (dims.get("2_kline") or {}).get("data") or {}
    capital = (dims.get("12_capital_flow") or {}).get("data") or {}
    events = (dims.get("15_events") or {}).get("data") or {}
    sentiment = (dims.get("17_sentiment") or {}).get("data") or {}
    valuation = (dims.get("10_valuation") or {}).get("data") or {}
    lhb = (dims.get("16_lhb") or {}).get("data") or {}
    trap = (dims.get("18_trap") or {}).get("data") or {}

    stage = int(feat.get("stage_num", 0) or 0)
    ma_align = str(feat.get("ma_align", "") or "")
    pct_from_60d_high = float(feat.get("pct_from_60d_high", 0) or 0)
    ytd_return = float(feat.get("ytd_return", 0) or 0)
    volatility = float(feat.get("volatility_1y", 0) or 0)
    main_5d = float(feat.get("main_fund_5d_net_yi", 0) or 0)
    lhb_hits = int(float(feat.get("lhb_30d_count", 0) or 0))
    matched_youzi = feat.get("matched_youzi_count", 0) or 0
    inst_net = float(feat.get("inst_net_buy_lhb", 0) or 0)
    youzi_net = float(feat.get("youzi_net_buy_lhb", 0) or 0)
    sentiment_heat = float(feat.get("sentiment_heat", 0) or 0)
    positive_catalyst = bool(feat.get("has_positive_catalyst"))
    negative_catalyst = bool(feat.get("has_negative_catalyst"))
    pe_q = int(feat.get("pe_quantile_5y", 50) or 50)
    pe = float(feat.get("pe", 0) or 0)
    trap_level = str(feat.get("trap_level", "") or "")
    safe = bool(feat.get("is_safe")) if trap_level else True

    notes: list[dict] = []
    caveats: list[str] = []

    trend_deltas = [0.0]
    if stage == 2:
        trend_deltas.append(14.0)
        notes.append({"name": "技术面", "weight": 35, "delta": 14.0, "note": "Stage 2 上升"})
    elif stage == 1:
        trend_deltas.append(7.0)
        notes.append({"name": "技术面", "weight": 35, "delta": 7.0, "note": "Stage 1 早期修复"})
    elif stage == 3:
        trend_deltas.append(-9.0)
        notes.append({"name": "技术面", "weight": 35, "delta": -9.0, "note": "Stage 3 末端"})
    elif stage == 4:
        trend_deltas.append(-14.0)
        notes.append({"name": "技术面", "weight": 35, "delta": -14.0, "note": "Stage 4 退潮"})

    if "多头" in ma_align:
        trend_deltas.append(9.0)
        notes.append({"name": "均线", "weight": 35, "delta": 9.0, "note": "均线多头排列"})
    elif "空头" in ma_align:
        trend_deltas.append(-9.0)
        notes.append({"name": "均线", "weight": 35, "delta": -9.0, "note": "均线空头排列"})

    if pct_from_60d_high > -3:
        trend_deltas.append(6.0)
    elif pct_from_60d_high > -8:
        trend_deltas.append(3.0)
    elif pct_from_60d_high > -15:
        trend_deltas.append(-2.0)
    else:
        trend_deltas.append(-6.0)

    if ytd_return > 10:
        trend_deltas.append(4.0)
    elif ytd_return > 0:
        trend_deltas.append(2.0)
    elif ytd_return < -10:
        trend_deltas.append(-4.0)

    if volatility > 70:
        trend_deltas.append(-3.0)
    elif 20 <= volatility <= 55:
        trend_deltas.append(2.0)

    trend_score = _component_score(50.0, trend_deltas[1:])

    flow_deltas = [0.0]
    if main_5d > 5:
        flow_deltas.append(12.0)
        notes.append({"name": "资金面", "weight": 20, "delta": 12.0, "note": f"主力 5 日净流入 {main_5d:.2f} 亿"})
    elif main_5d > 0:
        flow_deltas.append(7.0)
        notes.append({"name": "资金面", "weight": 20, "delta": 7.0, "note": f"主力 5 日净流入 {main_5d:.2f} 亿"})
    elif main_5d < 0:
        flow_deltas.append(-10.0)
        notes.append({"name": "资金面", "weight": 20, "delta": -10.0, "note": f"主力 5 日净流出 {abs(main_5d):.2f} 亿"})

    if lhb_hits > 0 and matched_youzi:
        if youzi_net > 0:
            flow_deltas.append(5.0)
            notes.append({"name": "龙虎榜", "weight": 20, "delta": 5.0, "note": "游资席位净买"})
        elif youzi_net < 0:
            flow_deltas.append(-5.0)
            notes.append({"name": "龙虎榜", "weight": 20, "delta": -5.0, "note": "游资席位净卖"})
        else:
            flow_deltas.append(2.0)
            notes.append({"name": "龙虎榜", "weight": 20, "delta": 2.0, "note": "龙虎榜有席位参与"})

    if inst_net > 0:
        flow_deltas.append(2.0)
    elif inst_net < 0:
        flow_deltas.append(-2.0)

    flow_score = _component_score(50.0, flow_deltas[1:])

    catalyst_deltas = [0.0]
    if positive_catalyst:
        catalyst_deltas.append(10.0)
        notes.append({"name": "催化剂", "weight": 20, "delta": 10.0, "note": "事件维度存在正向催化"})
    if negative_catalyst:
        catalyst_deltas.append(-12.0)
        notes.append({"name": "风险事件", "weight": 20, "delta": -12.0, "note": "事件维度存在负向信号"})

    if sentiment_heat >= 70:
        catalyst_deltas.append(3.0)
    elif 45 <= sentiment_heat < 70:
        catalyst_deltas.append(5.0)
    elif sentiment_heat < 25:
        catalyst_deltas.append(-3.0)
    elif sentiment_heat > 85:
        catalyst_deltas.append(-4.0)

    pos_pct = float(feat.get("sentiment_positive_pct", 0) or 0)
    if pos_pct >= 60:
        catalyst_deltas.append(3.0)
    elif pos_pct < 40:
        catalyst_deltas.append(-3.0)

    if events.get("recent_news") or events.get("event_timeline"):
        catalyst_deltas.append(2.0)
    catalyst_score = _component_score(50.0, catalyst_deltas[1:])

    valuation_deltas = [0.0]
    if pe_q < 25:
        valuation_deltas.append(8.0)
    elif pe_q < 40:
        valuation_deltas.append(5.0)
    elif pe_q > 80:
        valuation_deltas.append(-6.0)
    elif pe_q > 65:
        valuation_deltas.append(-3.0)

    if 0 < pe < 15:
        valuation_deltas.append(3.0)
    elif pe > 80:
        valuation_deltas.append(-3.0)

    dcf_intrinsic = float(feat.get("dcf_intrinsic_yi", 0) or 0)
    market_cap = float(feat.get("market_cap_yi", 0) or 0)
    if dcf_intrinsic > 0 and market_cap > 0:
        safety_margin = (dcf_intrinsic - market_cap) / market_cap * 100
        if safety_margin > 15:
            valuation_deltas.append(3.0)
        elif safety_margin < 0:
            valuation_deltas.append(-3.0)
    valuation_score = _component_score(50.0, valuation_deltas[1:])

    risk_deltas = [0.0]
    if not safe:
        risk_deltas.append(-12.0)
        caveats.append(f"风险标签: {trap_level}")
    if volatility > 80:
        risk_deltas.append(-4.0)
    elif 20 <= volatility <= 60:
        risk_deltas.append(2.0)
    if ytd_return < -15:
        risk_deltas.append(-3.0)
    risk_score = _component_score(50.0, risk_deltas[1:])

    components = [
        {"name": "趋势", "weight": 35, "score": round(trend_score, 1),
         "note": "；".join([n["note"] for n in notes if n["name"] in ("技术面", "均线")]) or "技术面与均线综合判断"},
        {"name": "资金", "weight": 20, "score": round(flow_score, 1),
         "note": "；".join([n["note"] for n in notes if n["name"] in ("资金面", "龙虎榜")]) or "资金面与龙虎榜综合判断"},
        {"name": "催化", "weight": 20, "score": round(catalyst_score, 1),
         "note": "；".join([n["note"] for n in notes if n["name"] in ("催化剂", "风险事件")]) or "事件与情绪综合判断"},
        {"name": "估值", "weight": 15, "score": round(valuation_score, 1),
         "note": f"PE 分位 {pe_q} · PE {pe:.1f}x" if pe or pe_q else "估值信息不足"},
        {"name": "风险", "weight": 10, "score": round(risk_score, 1),
         "note": "；".join(caveats) or "风险约束温和"},
    ]

    final_score = round(
        sum(c["score"] * c["weight"] for c in components) / sum(c["weight"] for c in components),
        1,
    )
    final_score = _clamp(final_score)

    direction = "看涨" if final_score >= 60 else "看跌" if final_score <= 40 else "中性"
    short_score = round(100 - final_score, 1)

    signal_count = sum(
        1 for flag in [
            stage > 0,
            abs(main_5d) > 0,
            lhb_hits > 0,
            positive_catalyst or negative_catalyst,
            sentiment_heat > 0,
            pe_q > 0,
            not safe,
        ] if flag
    )
    confidence = _clamp(35 + signal_count * 6 + (5 if stage == 2 else 0) + (5 if abs(main_5d) > 0 else 0), 20, 92)

    drivers = [
        c["note"] for c in components
        if c["score"] >= 55 and c["note"] not in ("技术面与均线综合判断", "资金面与龙虎榜综合判断", "事件与情绪综合判断")
    ]
    if not drivers:
        drivers = [
            c["note"] for c in components
            if c["score"] >= 50 and c["note"]
        ][:3]

    cautions = [
        c["note"] for c in components
        if c["score"] < 50 and c["note"]
    ]

    summary = f"次日方向分 {final_score:.1f}/100，{direction}，置信度 {confidence:.0f}%。"

    return {
        "score": final_score,
        "short_score": short_score,
        "direction": direction,
        "confidence": round(confidence, 0),
        "components": components,
        "drivers": drivers[:4],
        "cautions": cautions[:4],
        "summary": summary,
        "method": "Next-Day Bias (heuristic)",
        "methodology_log": [
            "Step 1 · 技术面 / 资金面 / 催化 / 估值 / 风险五桶打分",
            f"Step 2 · 综合分 {final_score:.1f}/100 → {direction}",
            f"Step 3 · 置信度 {confidence:.0f}% · 信号数 {signal_count}",
        ],
    }


def main(ticker: str) -> dict:
    raw = read_task_output(ticker, "raw_data") or {}
    dimensions = read_task_output(ticker, "dimensions") or {}
    synthesis = read_task_output(ticker, "synthesis") or {}

    scenarios = compute_scenarios(raw, dimensions)
    exit_triggers = compute_exit_triggers(raw, dimensions, synthesis)
    next_day_bias = compute_next_day_bias(raw, dimensions)
    backtest = compute_next_day_backtest(raw, dimensions)

    # Similar stocks: 从 raw_data 的 similar_stocks stub 或独立 cache
    similar = (raw.get("similar_stocks") or [])[:4]

    friendly = {
        "scenarios": scenarios,
        "exit_triggers": exit_triggers,
        "next_day_bias": next_day_bias,
        "backtest": backtest,
        "similar_stocks": similar,
    }

    return friendly


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"), ensure_ascii=False, indent=2, default=str))
