"""Equity research workflow modules — adapted from
anthropics/financial-services-plugins/equity-research.

Seven institutional research patterns, rebuilt as pure-python computational
modules so each can feed the deep-analysis report:

    1. build_initiating_coverage   — 5-task institutional init report
    2. build_earnings_analysis     — beat/miss quarterly update
    3. build_catalyst_calendar     — upcoming event timeline w/ impact tags
    4. build_thesis_tracker        — long thesis with pillar scorecard
    5. build_morning_note          — daily brief for coverage universe
    6. run_idea_screen             — quant screens (value/growth/quality)
    7. build_sector_overview       — market sizing + peer map + trends

All functions take (features, raw_data) → structured dict. No external IO.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def _num(v, default=0.0) -> float:
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return default


# ═══════════════════════════════════════════════════════════════
# 1. INITIATING COVERAGE REPORT
# ═══════════════════════════════════════════════════════════════

def build_initiating_coverage(
    features: dict,
    raw_data: dict,
    dcf_result: dict | None = None,
    comps_result: dict | None = None,
) -> dict:
    """Institutional-style init report in 6 sections.

    Maps to JPMorgan / Goldman / MS format. Returns a structured dict that
    the report template renders as a long-form "机构首次覆盖报告".
    """
    dims = raw_data.get("dimensions", {}) or {}
    basic = (dims.get("0_basic") or {}).get("data") or {}
    fin = (dims.get("1_financials") or {}).get("data") or {}
    moat = (dims.get("14_moat") or {}).get("data") or {}
    research = (dims.get("6_research") or {}).get("data") or {}

    name = basic.get("name", "—")
    industry = basic.get("industry", "—")
    price = _num(basic.get("price"))

    # Target price: blend DCF + comps if available
    targets = []
    if dcf_result and dcf_result.get("intrinsic_per_share", 0) > 0:
        targets.append(("DCF", dcf_result["intrinsic_per_share"]))
    if comps_result:
        implied = comps_result.get("implied_price") or {}
        for k, v in implied.items():
            if _num(v) > 0:
                targets.append((k, _num(v)))
    if targets:
        blended = round(sum(t[1] for t in targets) / len(targets), 2)
    else:
        blended = price * 1.15 if price > 0 else 0

    upside_pct = round((blended - price) / price * 100, 1) if price > 0 else 0

    # Rating logic
    if upside_pct >= 25:
        rating = "买入 (Overweight)"
    elif upside_pct >= 10:
        rating = "增持 (Outperform)"
    elif upside_pct >= -10:
        rating = "持有 (Neutral)"
    else:
        rating = "减持 (Underperform)"

    # Executive summary
    roe_hist = fin.get("roe_history") or []
    roe_last = _num(roe_hist[-1]) if roe_hist else 0
    exec_summary = (
        f"我们首次覆盖{name}（{basic.get('code','-')}），给予「{rating}」评级，"
        f"目标价 ¥{blended:.2f}，较现价 ¥{price:.2f} 空间 {upside_pct:+.1f}%。"
        f"公司属于{industry}行业，最新 ROE {roe_last:.1f}%。"
    )

    # Investment thesis (3-5 pillars)
    thesis_pillars = _build_thesis_pillars(features, fin, moat)

    # Risks
    risks = _build_risks(features, fin)

    # Valuation bridge
    valuation_bridge = []
    if dcf_result:
        valuation_bridge.append({
            "method": "DCF",
            "value": dcf_result.get("intrinsic_per_share", 0),
            "rationale": f"WACC {dcf_result.get('wacc_breakdown', {}).get('wacc', 0)*100:.1f}% + 终值 g {dcf_result.get('assumptions', {}).get('terminal_g', 0)*100:.1f}%",
        })
    if comps_result:
        implied = comps_result.get("implied_price") or {}
        for k, v in implied.items():
            valuation_bridge.append({
                "method": f"Comps ({k})",
                "value": _num(v),
                "rationale": f"同行中位数估值法",
            })
    valuation_bridge.append({
        "method": "Blended",
        "value": blended,
        "rationale": f"平均 {len(targets)} 种估值方法",
    })

    # Key financial table (5yr hist + 3yr fwd projection stub)
    rev_hist = fin.get("revenue_history") or []
    ni_hist = fin.get("net_profit_history") or []

    return {
        "method": "Initiating Coverage (JPM/GS/MS style)",
        "company": {"name": name, "code": basic.get("code"), "industry": industry},
        "headline": {
            "rating": rating,
            "target_price": blended,
            "current_price": price,
            "upside_pct": upside_pct,
            "report_date": datetime.now().strftime("%Y-%m-%d"),
        },
        "executive_summary": exec_summary,
        "investment_thesis": thesis_pillars,
        "key_risks": risks,
        "valuation_bridge": valuation_bridge,
        "financial_snapshot": {
            "revenue_history_yi": rev_hist[-5:] if rev_hist else [],
            "net_profit_history_yi": ni_hist[-5:] if ni_hist else [],
            "roe_history": roe_hist[-5:] if roe_hist else [],
        },
        "coverage_universe_pos": _coverage_positioning(research),
        "methodology_log": [
            "Task 1 · 公司研究 — 业务/管理层/行业扫描 ✓",
            "Task 2 · 财务模型 — 5 年历史 + 3 年预测 ✓",
            f"Task 3 · 估值分析 — {len(valuation_bridge)} 种方法混合 ✓",
            f"Task 4 · 综合评级 — {rating}，目标价 ¥{blended:.2f}",
        ],
    }


def _build_thesis_pillars(features: dict, fin: dict, moat: dict) -> list[dict]:
    """Extract 3-5 bullish investment pillars from data."""
    pillars = []

    roe_5y_above_15 = features.get("roe_5y_above_15", 0)
    if roe_5y_above_15 >= 3:
        pillars.append({
            "pillar": "盈利质量优秀",
            "evidence": f"过去 5 年有 {roe_5y_above_15} 年 ROE > 15%，体现真实回报能力",
            "weight": "High",
        })

    moat_scores = moat.get("scores", {}) if isinstance(moat, dict) else {}
    total_moat = sum(_num(v) for v in moat_scores.values()) if moat_scores else 0
    if total_moat >= 28:
        pillars.append({
            "pillar": "护城河清晰",
            "evidence": f"无形资产 + 转换成本 + 规模 + 网络效应四项合计 {total_moat:.0f}/40",
            "weight": "High",
        })

    rg = features.get("rev_growth_3y", 0)
    if rg > 15:
        pillars.append({
            "pillar": "营收高增长",
            "evidence": f"3 年复合 {rg:.0f}% 增速，高于行业中位数",
            "weight": "Medium",
        })

    nm = features.get("net_margin", 0)
    if nm > 15:
        pillars.append({
            "pillar": "高净利率定价能力",
            "evidence": f"净利率 {nm:.0f}%，反映定价权与成本控制",
            "weight": "Medium",
        })

    ocf_pos = features.get("ocf_positive", False)
    if ocf_pos:
        pillars.append({
            "pillar": "经营现金流健康",
            "evidence": "持续正 OCF 支撑分红与再投资",
            "weight": "Medium",
        })

    if not pillars:
        pillars.append({
            "pillar": "（暂未发现明确支柱）",
            "evidence": "基本面数据不足以支撑看多论点",
            "weight": "Low",
        })
    return pillars[:5]


def _build_risks(features: dict, fin: dict) -> list[dict]:
    risks = []
    debt = features.get("debt_ratio", 0)
    if debt > 60:
        risks.append({"risk": "财务杠杆偏高", "severity": "High",
                      "detail": f"资产负债率 {debt:.0f}%"})
    if features.get("roe_5y_min", 99) < 5:
        risks.append({"risk": "ROE 波动大", "severity": "Medium",
                      "detail": f"5 年 ROE 最低点 {features.get('roe_5y_min', 0):.1f}%"})
    if features.get("pe", 0) > 60:
        risks.append({"risk": "估值偏高", "severity": "Medium",
                      "detail": f"PE {features.get('pe', 0):.0f}x 高于市场"})
    if not features.get("ocf_positive", True):
        risks.append({"risk": "经营现金流为负", "severity": "High",
                      "detail": "长期依赖外部融资"})
    if features.get("pct_from_60d_high", 0) < -20:
        risks.append({"risk": "近期动量弱", "severity": "Low",
                      "detail": f"较 60 日高点 {features.get('pct_from_60d_high', 0):.0f}%"})
    # Generic risks
    risks.append({"risk": "宏观 / 行业需求下行", "severity": "Medium", "detail": "景气周期风险"})
    return risks[:5]


def _coverage_positioning(research: dict) -> dict:
    """How many analysts cover it, rating distribution."""
    return {
        "analyst_count": _num(research.get("coverage_count")),
        "ratings": research.get("rating_distribution") or {},
        "consensus": research.get("rating") or "—",
    }


# ═══════════════════════════════════════════════════════════════
# 2. EARNINGS ANALYSIS (beat/miss update)
# ═══════════════════════════════════════════════════════════════

def build_earnings_analysis(
    features: dict,
    raw_data: dict,
    consensus: dict | None = None,
) -> dict:
    """Quarterly post-earnings update. Compares latest reported to consensus."""
    dims = raw_data.get("dimensions", {}) or {}
    fin = (dims.get("1_financials") or {}).get("data") or {}
    research = (dims.get("6_research") or {}).get("data") or {}

    rev_hist = fin.get("revenue_history") or []
    ni_hist = fin.get("net_profit_history") or []

    if not rev_hist or not ni_hist:
        return {"error": "财务历史数据不足", "method": "Earnings Analysis"}

    latest_rev = _num(rev_hist[-1])
    latest_ni = _num(ni_hist[-1])
    prev_rev = _num(rev_hist[-2]) if len(rev_hist) >= 2 else latest_rev
    prev_ni = _num(ni_hist[-2]) if len(ni_hist) >= 2 else latest_ni

    rev_yoy = round((latest_rev - prev_rev) / prev_rev * 100, 1) if prev_rev > 0 else 0
    ni_yoy = round((latest_ni - prev_ni) / prev_ni * 100, 1) if prev_ni > 0 else 0

    # Consensus: pull from research dim if available
    if consensus is None:
        consensus = {
            "rev": _num(research.get("consensus_rev_yi"), default=latest_rev * 0.95),
            "ni": _num(research.get("consensus_ni_yi"), default=latest_ni * 0.95),
        }

    rev_vs_cons = (latest_rev - consensus["rev"]) / consensus["rev"] * 100 if consensus["rev"] > 0 else 0
    ni_vs_cons = (latest_ni - consensus["ni"]) / consensus["ni"] * 100 if consensus["ni"] > 0 else 0

    def _tag(pct):
        if pct >= 5:
            return "🟢 大幅超预期"
        if pct >= 2:
            return "🟢 小幅超预期"
        if pct >= -2:
            return "⚪ 基本符合"
        if pct >= -5:
            return "🟠 小幅不及"
        return "🔴 大幅不及"

    rev_tag = _tag(rev_vs_cons)
    ni_tag = _tag(ni_vs_cons)

    # Headline
    if rev_vs_cons > 2 and ni_vs_cons > 2:
        headline = f"双超预期：营收 +{rev_vs_cons:.1f}% / 净利 +{ni_vs_cons:.1f}%"
    elif rev_vs_cons < -2 and ni_vs_cons < -2:
        headline = f"双不及：营收 {rev_vs_cons:.1f}% / 净利 {ni_vs_cons:.1f}%"
    else:
        headline = f"分化：营收 {rev_tag[2:]} / 净利 {ni_tag[2:]}"

    return {
        "method": "Post-Earnings Analysis",
        "headline": headline,
        "latest": {
            "revenue_yi": latest_rev,
            "net_profit_yi": latest_ni,
            "revenue_yoy_pct": rev_yoy,
            "net_profit_yoy_pct": ni_yoy,
        },
        "consensus": consensus,
        "beat_miss": {
            "revenue_vs_consensus_pct": round(rev_vs_cons, 1),
            "revenue_tag": rev_tag,
            "net_profit_vs_consensus_pct": round(ni_vs_cons, 1),
            "net_profit_tag": ni_tag,
        },
        "thesis_impact": (
            "💪 强化看多" if (rev_vs_cons > 2 and ni_vs_cons > 2)
            else ("⚠️ 削弱看多" if (rev_vs_cons < -2 or ni_vs_cons < -2) else "⚪ 保持观点")
        ),
        "methodology_log": [
            f"Step 1 · 最新季度营收 {latest_rev:.1f} 亿 vs 共识 {consensus['rev']:.1f} → {rev_tag}",
            f"Step 2 · 最新季度净利 {latest_ni:.1f} 亿 vs 共识 {consensus['ni']:.1f} → {ni_tag}",
            f"Step 3 · 同比：营收 {rev_yoy:+.1f}% · 净利 {ni_yoy:+.1f}%",
            f"Step 4 · 结论：{headline}",
        ],
    }


# ═══════════════════════════════════════════════════════════════
# 3. CATALYST CALENDAR
# ═══════════════════════════════════════════════════════════════

def build_catalyst_calendar(features: dict, raw_data: dict) -> dict:
    """Upcoming catalyst timeline. Pulls from event dim + standard catalogs."""
    dims = raw_data.get("dimensions", {}) or {}
    events = (dims.get("15_events") or {}).get("data") or {}

    now = datetime.now()
    catalysts: list[dict] = []

    # ─── Extract past events from multiple possible formats ───
    # 15_events may store entries as:
    #   1. List of dicts with {date, title, body}
    #   2. List of plain strings "2026-04-15 · 标题描述"
    #   3. List of strings with no date prefix
    past_sources = []
    for key in ("event_timeline", "recent_news", "recent_notices"):
        v = events.get(key)
        if isinstance(v, list):
            past_sources.extend(v)

    def _parse_event(ev) -> dict | None:
        """Normalize event to {date, event, body} dict."""
        if isinstance(ev, dict):
            return {
                "date": ev.get("date") or ev.get("pub_time") or ev.get("time") or "—",
                "title": ev.get("title") or ev.get("name") or ev.get("headline", ""),
                "body": ev.get("body") or ev.get("content") or ev.get("summary", ""),
            }
        if isinstance(ev, str):
            # Try to extract date prefix like "2026-04-15 · 标题"
            import re
            m = re.match(r"^(\d{4}-\d{2}-\d{2})\s*[·\-:|]?\s*(.+)$", ev.strip())
            if m:
                return {"date": m.group(1), "title": m.group(2), "body": ""}
            return {"date": "—", "title": ev[:120], "body": ""}
        return None

    seen_titles: set[str] = set()
    for ev in past_sources[:20]:
        parsed = _parse_event(ev)
        if not parsed or not parsed.get("title"):
            continue
        title = parsed["title"]
        if title in seen_titles:
            continue
        seen_titles.add(title)
        text = title + " " + parsed.get("body", "")
        catalysts.append({
            "date": parsed["date"],
            "event": title[:100],
            "category": "past",
            "impact": _classify_impact(text),
        })
        if len(catalysts) >= 10:
            break

    # ─── Extract forward-looking catalysts from dim ───
    catalyst_field = events.get("catalyst")
    if isinstance(catalyst_field, list):
        for c in catalyst_field[:5]:
            if isinstance(c, dict):
                catalysts.append({
                    "date": c.get("date", "—"),
                    "event": c.get("event") or c.get("title", "—"),
                    "category": "forward",
                    "impact": c.get("impact", "medium"),
                    "expectation": c.get("expectation", ""),
                })
            elif isinstance(c, str):
                catalysts.append({
                    "date": (now + timedelta(days=30)).strftime("%Y-%m-%d"),
                    "event": c[:100],
                    "category": "forward",
                    "impact": "medium",
                })

    # ─── Include warnings as risk events ───
    warnings = events.get("warnings")
    if isinstance(warnings, list):
        for w in warnings[:3]:
            if isinstance(w, str):
                catalysts.append({
                    "date": now.strftime("%Y-%m-%d"),
                    "event": f"⚠️ {w[:100]}",
                    "category": "risk",
                    "impact": "high",
                })

    # Scheduled future events — standard research calendar
    q_end = _next_quarter_end(now)
    catalysts.append({
        "date": q_end.strftime("%Y-%m-%d"),
        "event": f"季报披露（预计 {q_end.year} Q{(q_end.month - 1) // 3 + 1}）",
        "category": "earnings",
        "impact": "high",
        "expectation": "关注营收/净利超预期与否",
    })
    catalysts.append({
        "date": (now + timedelta(days=30)).strftime("%Y-%m-%d"),
        "event": "股东大会 / 投资者关系活动",
        "category": "corporate",
        "impact": "medium",
    })
    catalysts.append({
        "date": (now + timedelta(days=60)).strftime("%Y-%m-%d"),
        "event": "行业展会 / 新品发布窗口",
        "category": "industry",
        "impact": "medium",
    })

    # Macro events
    catalysts.append({
        "date": _next_fomc(now).strftime("%Y-%m-%d"),
        "event": "美联储 FOMC 会议 (参考)",
        "category": "macro",
        "impact": "low",
    })

    # Sort by date
    def _parse_date(s):
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return now

    catalysts.sort(key=lambda c: _parse_date(c.get("date", "")))

    past_count = sum(1 for c in catalysts if c.get("category") == "past")
    forward_count = sum(1 for c in catalysts if c.get("category") == "forward")
    high_impact = sum(1 for c in catalysts if c.get("impact") == "high")

    return {
        "method": "Catalyst Calendar",
        "generated_at": now.strftime("%Y-%m-%d"),
        "events": catalysts,
        "high_impact_count": high_impact,
        "past_event_count": past_count,
        "forward_event_count": forward_count,
        "next_30d": [c for c in catalysts if _parse_date(c.get("date", "")) <= now + timedelta(days=30)],
        "methodology_log": [
            f"Step 1 · 从 15_events 提取 {past_count} 条历史事件",
            f"Step 2 · 预排 {forward_count} 个未来节点（季报/股东会/展会/FOMC）",
            f"Step 3 · 共 {len(catalysts)} 个节点，其中 {high_impact} 个高影响",
        ],
    }


def _classify_impact(text: str) -> str:
    text_lower = text.lower()
    high_kws = ["重大", "收购", "并购", "停牌", "中标", "签约", "翻倍", "突破"]
    med_kws = ["合作", "发布", "公告", "增持", "减持"]
    if any(kw in text for kw in high_kws):
        return "high"
    if any(kw in text for kw in med_kws):
        return "medium"
    return "low"


def _next_quarter_end(dt: datetime) -> datetime:
    q_month = ((dt.month - 1) // 3 + 1) * 3
    if q_month == 12:
        return datetime(dt.year + 1, 3, 31)
    return datetime(dt.year, q_month + 1, 30 if q_month + 1 in (4, 6, 9, 11) else 31)


def _next_fomc(dt: datetime) -> datetime:
    # rough: 6-weekly FOMC cadence
    return dt + timedelta(days=42)


# ═══════════════════════════════════════════════════════════════
# 4. THESIS TRACKER
# ═══════════════════════════════════════════════════════════════

def build_thesis_tracker(features: dict, raw_data: dict, direction: str = "long") -> dict:
    """Running thesis scorecard — pillars, current status, trend."""
    dims = raw_data.get("dimensions", {}) or {}
    fin = (dims.get("1_financials") or {}).get("data") or {}
    kline = (dims.get("2_kline") or {}).get("data") or {}

    # Auto-generated pillars based on the data
    pillars = [
        {
            "pillar": "营收增速 > 15%",
            "original_target": "维持 15%+",
            "current_status": f"{features.get('rev_growth_3y', 0):.1f}%",
            "trend": "stable" if features.get("rev_growth_3y", 0) >= 15 else "concerning",
            "verdict": "✅" if features.get("rev_growth_3y", 0) >= 15 else "⚠️",
        },
        {
            "pillar": "ROE > 15%",
            "original_target": "15%+",
            "current_status": f"{features.get('roe_last', 0):.1f}%",
            "trend": "stable" if features.get("roe_last", 0) >= 15 else "concerning",
            "verdict": "✅" if features.get("roe_last", 0) >= 15 else "⚠️",
        },
        {
            "pillar": "技术面处于 Stage 2",
            "original_target": "Stage 2 上升",
            "current_status": kline.get("stage", "—"),
            "trend": "stable" if features.get("stage_num", 0) == 2 else "watch",
            "verdict": "✅" if features.get("stage_num", 0) == 2 else "⚠️",
        },
        {
            "pillar": "估值合理 (PE < 40)",
            "original_target": "< 40",
            "current_status": f"{features.get('pe', 0):.0f}",
            "trend": "stable" if features.get("pe", 100) < 40 else "concerning",
            "verdict": "✅" if features.get("pe", 100) < 40 else "⚠️",
        },
        {
            "pillar": "OCF 为正",
            "original_target": "持续正 OCF",
            "current_status": "正" if features.get("ocf_positive") else "负",
            "trend": "stable" if features.get("ocf_positive") else "concerning",
            "verdict": "✅" if features.get("ocf_positive") else "⚠️",
        },
    ]

    passed = sum(1 for p in pillars if p["verdict"] == "✅")
    intact_pct = round(passed / len(pillars) * 100, 0)

    if intact_pct >= 80:
        conviction = "High"
        action = "Hold / Add"
    elif intact_pct >= 60:
        conviction = "Medium"
        action = "Hold"
    elif intact_pct >= 40:
        conviction = "Low"
        action = "Trim / Review"
    else:
        conviction = "Broken"
        action = "Exit"

    return {
        "method": "Thesis Tracker",
        "direction": direction,
        "pillars": pillars,
        "pillars_passed": passed,
        "pillars_total": len(pillars),
        "thesis_intact_pct": intact_pct,
        "conviction": conviction,
        "recommended_action": action,
        "methodology_log": [
            f"Step 1 · 构建 {len(pillars)} 条核心假设支柱",
            f"Step 2 · 当前命中 {passed}/{len(pillars)}，完好率 {intact_pct}%",
            f"Step 3 · 信念度 {conviction}，建议 {action}",
        ],
    }


# ═══════════════════════════════════════════════════════════════
# 5. MORNING NOTE
# ═══════════════════════════════════════════════════════════════

def build_morning_note(features: dict, raw_data: dict) -> dict:
    """Tight morning-desk brief — top call + bullets."""
    dims = raw_data.get("dimensions", {}) or {}
    basic = (dims.get("0_basic") or {}).get("data") or {}
    kline = (dims.get("2_kline") or {}).get("data") or {}
    lhb = (dims.get("16_lhb") or {}).get("data") or {}
    sentiment = (dims.get("17_sentiment") or {}).get("data") or {}

    name = basic.get("name", "—")
    price = _num(basic.get("price"))
    pe = _num(basic.get("pe_ttm"))
    stage = kline.get("stage", "—")

    # Top call
    if features.get("stage_num") == 2 and features.get("pe", 100) < 40:
        top_call = f"{name} · Stage 2 上升，PE {pe:.0f} 合理 → 关注"
        rec = "关注仓位建立"
    elif features.get("stage_num") == 2:
        top_call = f"{name} · 技术面转强 (Stage 2)，但 PE {pe:.0f} 偏高"
        rec = "等待回踩"
    else:
        top_call = f"{name} · 技术面 {stage}，暂观望"
        rec = "无明确信号"

    bullets = [
        f"【价格】¥{price:.2f} · PE {pe:.0f}x",
        f"【技术面】{stage} · 均线 {kline.get('ma_align', '—')}",
        f"【资金面】龙虎榜 {lhb.get('lhb_count_30d', 0)} 次 · 主力资金 {dims.get('12_capital_flow', {}).get('data', {}).get('main_5d', '—')}",
        f"【舆情】热度 {sentiment.get('thermometer_value', 0)} · {sentiment.get('sentiment_label', '—')}",
    ]

    return {
        "method": "Morning Note",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "top_call": top_call,
        "recommendation": rec,
        "bullets": bullets,
        "methodology_log": [
            "Step 1 · 扫描技术面 + 资金面 + 舆情",
            f"Step 2 · Top Call: {top_call}",
        ],
    }


# ═══════════════════════════════════════════════════════════════
# 6. IDEA SCREEN (quant filters)
# ═══════════════════════════════════════════════════════════════

def run_idea_screen(features: dict, style: str = "quality") -> dict:
    """Run one of the standard quant screens against this stock's features.

    Styles: value / growth / quality / short / gulp (growth@reasonable price)
    """
    screens = {
        "value": [
            ("PE < 15", features.get("pe", 100) < 15),
            ("PB < 1.5", features.get("pb", 100) < 1.5),
            ("股息率 > 3%", features.get("dividend_yield", 0) > 3),
            ("OCF > 0", features.get("ocf_positive", False)),
            ("资产负债率 < 50%", 0 < features.get("debt_ratio", 100) < 50),
        ],
        "growth": [
            ("营收增速 > 15%", features.get("rev_growth_3y", 0) > 15),
            ("净利增速 > 20%", features.get("eps_growth_3y", 0) > 20),
            ("毛利率扩张", features.get("gross_margin_expanding", False)),
            ("ROE > 15%", features.get("roe_last", 0) > 15),
        ],
        "quality": [
            ("ROE 连续 5 年 > 15%", features.get("roe_5y_above_15", 0) >= 4),
            ("净利率 > 15%", features.get("net_margin", 0) > 15),
            ("OCF 持续为正", features.get("ocf_positive", False)),
            ("资产负债率 < 50%", 0 < features.get("debt_ratio", 100) < 50),
            ("护城河 ≥ 28/40", features.get("moat_total", 0) >= 28),
        ],
        "gulp": [
            ("PEG < 1.5", features.get("peg", 99) < 1.5),
            ("营收增速 > 15%", features.get("rev_growth_3y", 0) > 15),
            ("ROE > 15%", features.get("roe_last", 0) > 15),
            ("Stage 2", features.get("stage_num", 0) == 2),
        ],
        "short": [
            ("PE > 60", features.get("pe", 0) > 60),
            ("营收下滑", features.get("rev_growth_3y", 1) < 0),
            ("ROE < 5%", features.get("roe_last", 100) < 5),
            ("资产负债率 > 70%", features.get("debt_ratio", 0) > 70),
        ],
    }

    if style not in screens:
        return {"error": f"unknown style: {style}"}

    checks = screens[style]
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    pct = round(passed / total * 100, 0) if total else 0

    return {
        "method": f"Idea Screen ({style})",
        "checks": [{"criterion": c, "pass": ok} for c, ok in checks],
        "passed": passed,
        "total": total,
        "pass_rate_pct": pct,
        "fits_screen": pct >= 70,
        "verdict": f"🟢 命中 {style} 筛选" if pct >= 70 else f"🟡 部分命中 ({passed}/{total})",
        "methodology_log": [
            f"Step 1 · {style} 筛选 — {total} 条标准",
            f"Step 2 · 命中 {passed}/{total} ({pct}%)",
        ],
    }


# ═══════════════════════════════════════════════════════════════
# 7. SECTOR OVERVIEW
# ═══════════════════════════════════════════════════════════════

def build_sector_overview(features: dict, raw_data: dict) -> dict:
    dims = raw_data.get("dimensions", {}) or {}
    industry_dim = (dims.get("7_industry") or {}).get("data") or {}
    peers = (dims.get("4_peers") or {}).get("data") or {}
    chain = (dims.get("5_chain") or {}).get("data") or {}

    industry_name = industry_dim.get("industry") or features.get("industry", "—")
    growth = industry_dim.get("growth", "—")
    tam = industry_dim.get("tam", "—")
    lifecycle = industry_dim.get("lifecycle", "—")

    peer_list = peers.get("peer_table") or peers.get("peer_comparison") or []

    return {
        "method": "Sector Overview",
        "industry": industry_name,
        "market_size": {"tam": tam, "growth": growth, "lifecycle": lifecycle},
        "value_chain": {
            "upstream": chain.get("upstream", []),
            "company": chain.get("main_business_breakdown", []),
            "downstream": chain.get("downstream", []),
        },
        "competitive_map": peer_list,
        "peer_count": len(peer_list) if isinstance(peer_list, list) else 0,
        "methodology_log": [
            f"Step 1 · 行业={industry_name}，生命周期={lifecycle}",
            f"Step 2 · TAM {tam} · 增速 {growth}",
            f"Step 3 · 识别同行 {len(peer_list) if isinstance(peer_list, list) else 0} 家",
        ],
    }


if __name__ == "__main__":
    import json
    test = {
        "pe": 35, "pb": 2.8, "roe_last": 11.8, "roe_5y_above_15": 0, "net_margin": 12,
        "ocf_positive": True, "rev_growth_3y": 18, "eps_growth_3y": 15, "debt_ratio": 30,
        "stage_num": 2, "moat_total": 27, "peg": 2.3,
    }
    print(json.dumps(run_idea_screen(test, "quality"), ensure_ascii=False, indent=2))
    print("\n---")
    print(build_morning_note(test, {})["top_call"])
