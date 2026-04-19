"""Rule engine executor — turns (investor_id, features) into a quantified verdict.

Every investor's evaluation is traceable to the specific rules in
`investor_criteria.INVESTOR_RULES[investor_id]`. No fuzzy templates.

Output schema:
    {
        "investor_id": "buffett",
        "score": 0-100,                     # weighted rule pass rate
        "signal": "bullish"|"bearish"|"neutral",
        "confidence": 0-100,                # coverage-adjusted confidence
        "weight_pass": int,                 # sum of weights of passed rules
        "weight_total": int,                # sum of all rule weights
        "pass_rules": [{rule_id, name, weight, msg}, ...],
        "fail_rules": [{rule_id, name, weight, msg}, ...],
        "headline": "1-sentence summary citing top hit/miss",
        "rationale": "multi-line detailed reasoning",
    }
"""
from __future__ import annotations

from typing import Any

from lib.investor_criteria import INVESTOR_RULES, Rule
from lib.investor_knowledge import reality_check
from lib.investor_profile import get_profile as _get_profile
from lib.investor_db import INVESTORS as _INVESTORS

# v2.8 · 预构建 id → group 索引，用于 profile 的 group-level fallback
_INVESTOR_GROUP_MAP: dict[str, str] = {inv["id"]: inv.get("group", "") for inv in _INVESTORS}
# v2.13.3 · F 组射程检查用：id → 中文 name（供 seat_db.is_in_range 查 SEATS key）
_INVESTOR_NAME_MAP: dict[str, str] = {inv["id"]: inv.get("name", "") for inv in _INVESTORS}


def _is_youzi_out_of_range(investor_id: str, features: dict) -> tuple[bool, str]:
    """v2.13.3 · F 组游资射程前置检查.

    对 F 组投资者 · 调 seat_db.is_in_range · 不在射程则 skip（不打分）.
    解决 v2.13.2 之前"大市值股对所有游资都判看多/看空"的 bug.

    Returns:
        (out_of_range: bool, reason: str)
    """
    if _INVESTOR_GROUP_MAP.get(investor_id) != "F":
        return False, ""
    try:
        from lib.seat_db import SEATS, is_in_range
    except Exception:
        return False, ""
    nickname = _INVESTOR_NAME_MAP.get(investor_id, "")
    if not nickname or nickname not in SEATS:
        return False, ""  # seat 没定义 · 不做 skip 决策
    # is_in_range 需要 market_cap 字段（元）· features 里常叫 market_cap_yi（亿）或 market_cap
    mc = features.get("market_cap") or 0
    # 兼容：features 可能只有 market_cap_yi（亿）· 换算为元
    if not mc and features.get("market_cap_yi"):
        mc = float(features["market_cap_yi"]) * 1e8
    probe = dict(features)
    probe["market_cap"] = mc
    if not is_in_range(nickname, probe):
        mc_yi = mc / 1e8 if mc else 0
        return True, f"市值 {mc_yi:.0f} 亿不在 {nickname} 射程"
    return False, ""


# ────────────────────────────────────────────────────────────────
# Signal thresholds
# ────────────────────────────────────────────────────────────────
BULLISH_THRESHOLD = 65   # score ≥ 65 → bullish
BEARISH_THRESHOLD = 35   # score < 35 → bearish


def _fmt_msg(template: str, features: dict) -> str:
    """Format a rule's pass_msg / fail_msg with feature values.

    Gracefully handles missing keys — unknown placeholders stay as literals.
    """
    if not template:
        return ""
    try:
        return template.format(**features)
    except (KeyError, IndexError, ValueError):
        # Fall back: strip unresolved placeholders
        try:
            # replace missing keys with "?"
            safe = {k: features.get(k, "?") for k in _extract_keys(template)}
            return template.format(**safe)
        except Exception:
            return template


def _extract_keys(template: str) -> list[str]:
    import re
    return re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)", template)


def _safe_check(rule: Rule, features: dict) -> bool:
    """Run rule.check guarded against exceptions (missing features, type errors)."""
    try:
        return bool(rule.check(features))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False


def evaluate(investor_id: str, features: dict) -> dict:
    """Evaluate one investor against one stock's features.

    Three-layer evaluation:
        Layer 1 · Reality check: market scope / known holdings / industry affinity
        Layer 2 · Rule engine: quantitative criteria from investor_criteria.py
        Layer 3 · Composite: merge rule score with reality adjustments
    """
    # ─── Layer 1: Reality Check ───
    market = features.get("market", "A")
    ticker = features.get("ticker", "")
    name = features.get("name", "")
    industry = features.get("industry", "")

    rc = reality_check(investor_id, market, ticker, name, industry)

    # If this investor wouldn't look at this market at all → "不适合"
    if not rc["should_evaluate"]:
        return _skip_result(investor_id, rc["skip_reason"] or "不在能力圈")

    # v2.13.3 · F 组游资射程前置检查 · 大市值超射程直接 skip 不打分
    out_of_range, range_reason = _is_youzi_out_of_range(investor_id, features)
    if out_of_range:
        return _skip_result(investor_id, range_reason)

    rules: list[Rule] = INVESTOR_RULES.get(investor_id, [])
    if not rules:
        return _unknown_result(investor_id)

    # ─── Layer 2: Rule Engine ───
    pass_list: list[dict] = []
    fail_list: list[dict] = []
    weight_pass = 0
    weight_total = 0

    for rule in rules:
        weight_total += rule.weight
        if _safe_check(rule, features):
            weight_pass += rule.weight
            pass_list.append({
                "rule_id": rule.rule_id,
                "name": rule.name,
                "weight": rule.weight,
                "msg": _fmt_msg(rule.pass_msg or rule.name, features),
            })
        else:
            fail_list.append({
                "rule_id": rule.rule_id,
                "name": rule.name,
                "weight": rule.weight,
                "msg": _fmt_msg(rule.fail_msg or f"未达{rule.name}", features),
            })

    # Base score from rules
    rule_score = round((weight_pass / weight_total) * 100, 1) if weight_total else 0.0

    # ─── Layer 3: Reality Adjustment ───
    affinity_adj = rc["affinity_adjust"]
    holding_match = rc["holding_match"]

    # If they actually HOLD this stock, that's a strong bullish signal
    # regardless of what the rules say
    if holding_match:
        attitude, note = holding_match
        if attitude in ("held", "bullish_known"):
            # Add a virtual "pass" rule for the holding
            pass_list.insert(0, {
                "rule_id": "known_holding",
                "name": "实际持仓 / 公开看好",
                "weight": 6,  # highest weight — real money talks
                "msg": f"📌 {note}",
            })
            weight_pass += 6
            weight_total += 6

    # Composite score = rule_score (re-calculated with holding) + affinity
    if weight_total > 0:
        score = round((weight_pass / weight_total) * 100 + affinity_adj, 1)
    else:
        score = round(50 + affinity_adj, 1)
    score = max(0, min(100, score))

    # Signal: if override from reality check (e.g. actual holding), respect it
    if rc["override_signal"]:
        signal = rc["override_signal"]
    elif score >= BULLISH_THRESHOLD:
        signal = "bullish"
    elif score < BEARISH_THRESHOLD:
        signal = "bearish"
    else:
        signal = "neutral"

    # Confidence
    n_rules = len(rules) + (1 if holding_match else 0)
    base_conf = min(100, 50 + n_rules * 8)
    extremeness = abs(score - 50) * 0.6
    confidence = round(min(100, base_conf * 0.6 + 40 + extremeness * 0.4), 0)

    # Sort rules by weight desc for display
    pass_list.sort(key=lambda r: -r["weight"])
    fail_list.sort(key=lambda r: -r["weight"])

    headline = _build_headline(signal, pass_list, fail_list)
    rationale = _build_rationale(signal, pass_list, fail_list)

    # v2.8 · 因地制宜：加入每人 authentic 3 字段（time_horizon / position_sizing /
    # what_would_change_my_mind）。不是模板，是按每个投资者自己的方法论填的。
    profile = _get_profile(investor_id, group=_INVESTOR_GROUP_MAP.get(investor_id, ""))

    return {
        "investor_id": investor_id,
        "score": score,
        "signal": signal,
        "confidence": confidence,
        "weight_pass": weight_pass,
        "weight_total": weight_total,
        "pass_count": len(pass_list),
        "fail_count": len(fail_list),
        "pass_rules": pass_list,
        "fail_rules": fail_list,
        "headline": headline,
        "rationale": rationale,
        # v2.8 · per-persona authentic decision profile
        "time_horizon": profile["time_horizon"],
        "position_sizing": profile["position_sizing"],
        "what_would_change_my_mind": profile["what_would_change_my_mind"],
    }


def _build_headline(signal: str, pass_list: list, fail_list: list) -> str:
    """One-sentence takeaway citing the top rule."""
    if signal == "bullish" and pass_list:
        top = pass_list[0]
        return f"看多核心：{top['msg']}"
    if signal == "bearish" and fail_list:
        top = fail_list[0]
        return f"看空核心：{top['msg']}"
    # neutral — cite most important passed + most important failed
    if pass_list and fail_list:
        return f"观望：{pass_list[0]['msg']}；但 {fail_list[0]['msg']}"
    if pass_list:
        return f"中性：{pass_list[0]['msg']}"
    if fail_list:
        return f"中性：{fail_list[0]['msg']}"
    return "数据不足，暂无判断"


def _build_rationale(signal: str, pass_list: list, fail_list: list) -> str:
    """Multi-line detailed reasoning with bullet points."""
    lines: list[str] = []

    if pass_list:
        lines.append("✅ 符合标准：")
        for r in pass_list[:4]:
            lines.append(f"  • [权{r['weight']}] {r['msg']}")

    if fail_list:
        lines.append("❌ 未达标准：")
        for r in fail_list[:4]:
            lines.append(f"  • [权{r['weight']}] {r['msg']}")

    return "\n".join(lines) if lines else "无有效规则命中"


def _skip_result(investor_id: str, reason: str) -> dict:
    """This investor would not evaluate this stock (market/scope mismatch)."""
    profile = _get_profile(investor_id, group=_INVESTOR_GROUP_MAP.get(investor_id, ""))
    return {
        "investor_id": investor_id,
        "score": -1,
        "signal": "skip",
        "confidence": 0,
        "weight_pass": 0,
        "weight_total": 0,
        "pass_count": 0,
        "fail_count": 0,
        "pass_rules": [],
        "fail_rules": [],
        "headline": f"不适合 — {reason}",
        "rationale": f"该投资者{reason}，不对此股票发表意见。",
        "skip_reason": reason,
        "time_horizon": profile["time_horizon"],
        "position_sizing": profile["position_sizing"],
        "what_would_change_my_mind": profile["what_would_change_my_mind"],
    }


def _unknown_result(investor_id: str) -> dict:
    profile = _get_profile(investor_id, group=_INVESTOR_GROUP_MAP.get(investor_id, ""))
    return {
        "investor_id": investor_id,
        "score": 50.0,
        "signal": "neutral",
        "confidence": 30,
        "weight_pass": 0,
        "weight_total": 0,
        "pass_count": 0,
        "fail_count": 0,
        "pass_rules": [],
        "fail_rules": [],
        "headline": "该投资者暂无量化评估规则",
        "rationale": "此投资者未配置规则库，使用默认中性判断。",
        "time_horizon": profile["time_horizon"],
        "position_sizing": profile["position_sizing"],
        "what_would_change_my_mind": profile["what_would_change_my_mind"],
    }


def evaluate_all(features: dict) -> dict[str, dict]:
    """Evaluate all 51 investors at once."""
    return {inv_id: evaluate(inv_id, features) for inv_id in INVESTOR_RULES}


def panel_summary(results: dict[str, dict]) -> dict:
    """Aggregate all investor verdicts into a consensus panel view.

    Handles "skip" signal — investors who wouldn't look at this stock's market.
    """
    if not results:
        return {"bullish": 0, "bearish": 0, "neutral": 0, "skip": 0, "avg_score": 50.0}

    # Split active vs skipped
    active = {k: v for k, v in results.items() if v["signal"] != "skip"}
    skipped = {k: v for k, v in results.items() if v["signal"] == "skip"}

    bullish = sum(1 for r in active.values() if r["signal"] == "bullish")
    bearish = sum(1 for r in active.values() if r["signal"] == "bearish")
    neutral = sum(1 for r in active.values() if r["signal"] == "neutral")

    active_scores = [r["score"] for r in active.values() if r["score"] >= 0]
    avg_score = round(sum(active_scores) / len(active_scores), 1) if active_scores else 50.0
    avg_conf = round(sum(r["confidence"] for r in active.values()) / max(len(active), 1), 0)

    # Top bulls & bears from ACTIVE only
    sorted_bull = sorted(active.items(), key=lambda kv: -kv[1]["score"])[:5]
    sorted_bear = sorted(active.items(), key=lambda kv: kv[1]["score"])[:5]

    n_active = len(active)
    return {
        "total": len(results),
        "active": n_active,
        "skip": len(skipped),
        "skip_names": [v.get("skip_reason", "") for v in skipped.values()],
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
        "avg_score": avg_score,
        "avg_confidence": avg_conf,
        "bullish_pct": round(bullish / n_active * 100, 0) if n_active else 0,
        "bearish_pct": round(bearish / n_active * 100, 0) if n_active else 0,
        "top_bulls": [{"id": k, "score": v["score"], "headline": v["headline"]} for k, v in sorted_bull],
        "top_bears": [{"id": k, "score": v["score"], "headline": v["headline"]} for k, v in sorted_bear],
    }


if __name__ == "__main__":
    import json
    # Sanity check with synthetic features
    test_features = {
        "roe_5y_above_15": 5,
        "roe_5y_min": 18.2,
        "net_margin": 22.5,
        "debt_ratio": 35,
        "fcf_positive": True,
        "fcf_margin": 12.0,
        "moat_total": 32,
        "pe": 18.5,
        "pe_quantile_5y": 45,
        "pb": 3.2,
        "pe_x_pb": 59.2,
        "dividend_5y": True,
        "safety_margin": 15.0,
        "dcf_intrinsic_yi": 800,
        "market_cap_yi": 700,
        "stage_num": 2,
        "ma_bull_aligned": True,
        "pct_from_60d_high": -5.0,
        "rev_growth_3y": 18.0,
        "eps_growth_3y": 25.0,
    }
    result = evaluate("buffett", test_features)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n--- Panel summary ---")
    all_res = evaluate_all(test_features)
    print(json.dumps(panel_summary(all_res), ensure_ascii=False, indent=2))
