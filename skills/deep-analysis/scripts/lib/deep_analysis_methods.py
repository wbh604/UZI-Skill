"""Deep analysis methods — adapted from financial-services-plugins:
    - private-equity: ic-memo, unit-economics, value-creation-plan, dd-checklist
    - financial-analysis: competitive-analysis (Porter 5 Forces + BCG)
    - wealth-management: portfolio-rebalance, tax-loss-harvesting

All as pure-python computational modules returning structured dicts.
"""
from __future__ import annotations

from typing import Any


def _num(v, default=0.0) -> float:
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return default


# ═══════════════════════════════════════════════════════════════
# 1. IC MEMO (Investment Committee)
# ═══════════════════════════════════════════════════════════════

def build_ic_memo(
    features: dict,
    raw_data: dict,
    dcf_result: dict | None = None,
    comps_result: dict | None = None,
    thesis_pillars: list | None = None,
) -> dict:
    """Structured IC memo for formal investment decision."""
    dims = raw_data.get("dimensions", {}) or {}
    basic = (dims.get("0_basic") or {}).get("data") or {}
    fin = (dims.get("1_financials") or {}).get("data") or {}
    moat = (dims.get("14_moat") or {}).get("data") or {}

    name = basic.get("name", "—")
    price = _num(basic.get("price"))

    # I. Executive Summary
    rec_headline, recommendation = _ic_recommendation(features, dcf_result)

    # II. Company Overview
    company = {
        "name": name,
        "industry": basic.get("industry", "—"),
        "business_model": (dims.get("5_chain") or {}).get("data", {}).get("main_business_raw", "—"),
        "market_cap_yi": _num(features.get("market_cap_yi")),
        "revenue_last_yi": _num(features.get("revenue_latest_yi")),
    }

    # III. Industry & Market
    industry_info = {
        "industry_name": basic.get("industry", "—"),
        "tam": (dims.get("7_industry") or {}).get("data", {}).get("tam", "—"),
        "growth": (dims.get("7_industry") or {}).get("data", {}).get("growth", "—"),
        "lifecycle": (dims.get("7_industry") or {}).get("data", {}).get("lifecycle", "—"),
    }

    # IV. Financial Analysis
    financial_snapshot = {
        "roe_5yr": fin.get("roe_history", [])[-5:],
        "revenue_hist_yi": fin.get("revenue_history", [])[-5:],
        "net_profit_hist_yi": fin.get("net_profit_history", [])[-5:],
        "net_margin": features.get("net_margin", 0),
        "debt_ratio": features.get("debt_ratio", 0),
        "fcf_positive": features.get("fcf_positive", False),
    }

    # V. Valuation
    valuation = {}
    if dcf_result:
        valuation["dcf"] = {
            "intrinsic_per_share": dcf_result.get("intrinsic_per_share", 0),
            "safety_margin_pct": dcf_result.get("safety_margin_pct", 0),
            "verdict": dcf_result.get("verdict", ""),
        }
    if comps_result:
        valuation["comps"] = {
            "target_percentile": comps_result.get("target_percentile", {}),
            "implied_price": comps_result.get("implied_price", {}),
            "verdict": comps_result.get("valuation_verdict", ""),
        }

    # VI. Key Risks & Mitigants
    risks = _ic_risks(features, moat)

    # VII. Returns Analysis (3 scenarios)
    scenarios = _ic_scenarios(price, dcf_result)

    # VIII. Top 3 risks + mitigants
    top_3_risks = risks[:3]

    return {
        "method": "Investment Committee Memo",
        "sections": {
            "I_exec_summary": {
                "headline": rec_headline,
                "recommendation": recommendation,
                "top_3_risks": top_3_risks,
            },
            "II_company_overview": company,
            "III_industry_market": industry_info,
            "IV_financial_analysis": financial_snapshot,
            "V_valuation": valuation,
            "VI_risks_mitigants": risks,
            "VII_returns_scenarios": scenarios,
            "VIII_recommendation": recommendation,
        },
        "methodology_log": [
            "Step 1 · 汇总公司/行业/财务快照",
            "Step 2 · 结合 DCF/Comps 形成估值结论",
            "Step 3 · 构建三情景回报",
            f"Step 4 · 出具建议: {recommendation}",
        ],
    }


def _ic_recommendation(features: dict, dcf: dict | None) -> tuple[str, str]:
    """Simple recommendation logic based on quality + valuation."""
    quality_score = 0
    if features.get("roe_5y_above_15", 0) >= 3:
        quality_score += 2
    if features.get("fcf_positive"):
        quality_score += 1
    if features.get("net_margin", 0) > 15:
        quality_score += 1
    if features.get("moat_total", 0) >= 28:
        quality_score += 2

    val_score = 0
    if dcf:
        sm = dcf.get("safety_margin_pct", 0)
        if sm > 20:
            val_score = 2
        elif sm > 0:
            val_score = 1
        elif sm > -20:
            val_score = 0
        else:
            val_score = -1

    total = quality_score + val_score
    if total >= 5:
        return ("🟢 强烈建议通过 (PASS)", "推荐投委会批准建仓 — 高质量 × 安全边际充足")
    if total >= 3:
        return ("🟡 建议通过 (CONDITIONAL PASS)", "可批准但建议分批建仓，控制初始仓位")
    if total >= 0:
        return ("⚪ 观望 (HOLD)", "暂不建议建仓，等待估值回落或信号强化")
    return ("🔴 建议回避 (PASS)", "质量或估值不达标 — 投委会建议不进场")


def _ic_risks(features: dict, moat: dict) -> list[dict]:
    risks = []
    if features.get("debt_ratio", 0) > 60:
        risks.append({
            "risk": "财务杠杆风险",
            "detail": f"资产负债率 {features.get('debt_ratio', 0):.0f}% 偏高",
            "severity": "High",
            "mitigant": "监控利息覆盖倍数与再融资窗口",
        })
    if features.get("moat_total", 0) < 20:
        risks.append({
            "risk": "护城河偏弱",
            "detail": f"4 项合计 {features.get('moat_total', 0):.0f}/40",
            "severity": "Medium",
            "mitigant": "密切跟踪市场份额变化",
        })
    if features.get("pe", 0) > 60:
        risks.append({
            "risk": "估值偏贵",
            "detail": f"PE {features.get('pe', 0):.0f}x",
            "severity": "Medium",
            "mitigant": "等待 PE 回归 40 以下再建仓",
        })
    if not features.get("fcf_positive", True):
        risks.append({
            "risk": "现金流为负",
            "detail": "依赖外部融资",
            "severity": "High",
            "mitigant": "要求管理层提供扭转路线图",
        })
    risks.append({
        "risk": "行业周期下行",
        "detail": "需求侧宏观冲击",
        "severity": "Medium",
        "mitigant": "行业景气度月度跟踪",
    })
    return risks


def _ic_scenarios(price: float, dcf: dict | None) -> list[dict]:
    if not dcf or price <= 0:
        return []
    intrinsic = dcf.get("intrinsic_per_share", price)
    return [
        {
            "scenario": "Bull (乐观)",
            "price_target": round(intrinsic * 1.3, 2),
            "return_pct": round((intrinsic * 1.3 - price) / price * 100, 1),
            "probability_pct": 25,
            "assumptions": "超预期增速 + 估值扩张",
        },
        {
            "scenario": "Base (中性)",
            "price_target": round(intrinsic, 2),
            "return_pct": round((intrinsic - price) / price * 100, 1),
            "probability_pct": 50,
            "assumptions": "DCF 基础假设",
        },
        {
            "scenario": "Bear (悲观)",
            "price_target": round(intrinsic * 0.7, 2),
            "return_pct": round((intrinsic * 0.7 - price) / price * 100, 1),
            "probability_pct": 25,
            "assumptions": "增速放缓 + 估值压缩",
        },
    ]


# ═══════════════════════════════════════════════════════════════
# 2. UNIT ECONOMICS (for SaaS / recurring / transaction biz)
# ═══════════════════════════════════════════════════════════════

def build_unit_economics(features: dict, raw_data: dict) -> dict:
    """ARR / LTV / CAC / Cohort analysis.

    For non-SaaS companies this returns a gross-margin decomposition instead.
    """
    dims = raw_data.get("dimensions", {}) or {}
    fin = (dims.get("1_financials") or {}).get("data") or {}
    industry = dims.get("0_basic", {}).get("data", {}).get("industry", "")

    is_recurring = any(kw in (industry or "") for kw in ["软件", "服务", "云", "互联网", "SaaS"])

    if is_recurring:
        # SaaS-style cohort metrics
        arpu = _num(features.get("revenue_latest_yi")) / max(_num(features.get("customer_count"), 1), 1)
        gross_margin = _num(features.get("gross_margin", 50)) / 100
        churn_rate = 0.15  # annual churn default
        ltv = (arpu * gross_margin) / churn_rate if churn_rate > 0 else 0
        cac = arpu * 0.5  # rough proxy
        ltv_cac = ltv / cac if cac > 0 else 0
        payback_months = cac / (arpu * gross_margin / 12) if arpu > 0 else 0

        return {
            "method": "Unit Economics (SaaS/recurring)",
            "business_type": "recurring",
            "metrics": {
                "arpu_yi": round(arpu, 3),
                "gross_margin_pct": round(gross_margin * 100, 1),
                "churn_rate_pct": round(churn_rate * 100, 1),
                "ltv_yi": round(ltv, 3),
                "cac_yi": round(cac, 3),
                "ltv_cac_ratio": round(ltv_cac, 2),
                "payback_months": round(payback_months, 1),
            },
            "healthy": ltv_cac >= 3 and payback_months <= 24,
            "verdict": "🟢 健康" if ltv_cac >= 3 else "🔴 不健康",
            "methodology_log": [
                f"Step 1 · ARPU {arpu:.3f} 亿 · 毛利率 {gross_margin*100:.0f}%",
                f"Step 2 · LTV {ltv:.2f} / CAC {cac:.2f} = {ltv_cac:.1f}x",
                f"Step 3 · 回本周期 {payback_months:.0f} 个月",
            ],
        }

    # Non-recurring: gross margin decomposition
    rev = _num(features.get("revenue_latest_yi"))
    gm_pct = _num(features.get("gross_margin", 30))
    nm_pct = _num(features.get("net_margin", 10))
    opex_pct = gm_pct - nm_pct

    return {
        "method": "Margin Decomposition",
        "business_type": "non-recurring",
        "revenue_yi": rev,
        "gross_margin_pct": gm_pct,
        "opex_pct_of_rev": round(opex_pct, 1),
        "net_margin_pct": nm_pct,
        "waterfall": [
            {"stage": "收入", "value": 100, "label": "100%"},
            {"stage": "毛利", "value": gm_pct, "label": f"{gm_pct:.0f}%"},
            {"stage": "税前", "value": nm_pct / 0.75, "label": f"{nm_pct/0.75:.0f}%"},
            {"stage": "净利", "value": nm_pct, "label": f"{nm_pct:.0f}%"},
        ],
        "methodology_log": [
            f"Step 1 · 营收 {rev:.1f} 亿",
            f"Step 2 · 毛利率 {gm_pct:.0f}% · 运营费率 {opex_pct:.0f}% · 净利率 {nm_pct:.0f}%",
        ],
    }


# ═══════════════════════════════════════════════════════════════
# 3. VALUE CREATION PLAN (EBITDA bridge)
# ═══════════════════════════════════════════════════════════════

def build_value_creation_plan(features: dict, raw_data: dict) -> dict:
    """Post-investment value creation roadmap — 5 years."""
    dims = raw_data.get("dimensions", {}) or {}
    fin = (dims.get("1_financials") or {}).get("data") or {}

    rev = _num(features.get("revenue_latest_yi"))
    ebitda_est = rev * 0.20 if rev > 0 else 1  # rough
    current_ebitda = _num(features.get("ebitda_yi"), default=ebitda_est)
    current_ebitda_margin = current_ebitda / rev * 100 if rev > 0 else 0

    # 5 levers with assumed impact
    levers = [
        {
            "category": "Revenue · Organic Growth",
            "lever": "现有市场渗透率提升",
            "current_state": f"市场份额 ~{features.get('market_share', '—')}%",
            "target_state": "5 年内提升 3pp",
            "ebitda_impact_yi": round(rev * 0.03 * 0.25, 2),
            "timeline": "Y1-Y5",
            "confidence": "Medium",
        },
        {
            "category": "Revenue · Cross-Sell",
            "lever": "新产品交叉销售",
            "current_state": "核心产品",
            "target_state": "5 年新增 20% 营收占比",
            "ebitda_impact_yi": round(rev * 0.20 * 0.20, 2),
            "timeline": "Y2-Y5",
            "confidence": "Medium",
        },
        {
            "category": "Margin · Pricing Power",
            "lever": "定价优化",
            "current_state": f"毛利率 {features.get('gross_margin', 30):.0f}%",
            "target_state": "+300bps",
            "ebitda_impact_yi": round(rev * 0.03, 2),
            "timeline": "Y1-Y3",
            "confidence": "High",
        },
        {
            "category": "Margin · COGS",
            "lever": "采购集中 + 供应链优化",
            "current_state": "多点采购",
            "target_state": "−200bps COGS",
            "ebitda_impact_yi": round(rev * 0.02, 2),
            "timeline": "Y1-Y2",
            "confidence": "High",
        },
        {
            "category": "Capital Efficiency",
            "lever": "营运资本优化",
            "current_state": "存货周转 —",
            "target_state": "存货周转 +20%",
            "ebitda_impact_yi": round(rev * 0.01, 2),
            "timeline": "Y1-Y3",
            "confidence": "Medium",
        },
    ]

    total_uplift = sum(l["ebitda_impact_yi"] for l in levers)
    target_ebitda = current_ebitda + total_uplift

    return {
        "method": "Value Creation Plan (EBITDA Bridge)",
        "current_ebitda_yi": round(current_ebitda, 2),
        "current_margin_pct": round(current_ebitda_margin, 1),
        "levers": levers,
        "total_uplift_yi": round(total_uplift, 2),
        "target_ebitda_yi": round(target_ebitda, 2),
        "target_margin_pct": round(target_ebitda / rev * 100, 1) if rev > 0 else 0,
        "hundred_day_priorities": [
            "Day 30 · 财务 QoE 验证",
            "Day 60 · 新管理层招募",
            "Day 90 · 季度 KPI 仪表盘上线",
        ],
        "methodology_log": [
            f"Step 1 · 现 EBITDA {current_ebitda:.1f} 亿 ({current_ebitda_margin:.0f}% 利润率)",
            f"Step 2 · 5 大杠杆合计加厚 {total_uplift:.1f} 亿",
            f"Step 3 · 目标 EBITDA {target_ebitda:.1f} 亿 ({target_ebitda / rev * 100 if rev > 0 else 0:.0f}%)",
        ],
    }


# ═══════════════════════════════════════════════════════════════
# 4. DD CHECKLIST
# ═══════════════════════════════════════════════════════════════

def build_dd_checklist(features: dict, raw_data: dict) -> dict:
    """Auto-generated due-diligence checklist with status inference."""
    dims = raw_data.get("dimensions", {}) or {}

    def _check(has: bool) -> str:
        return "✅ 已有数据" if has else "❌ 缺失"

    workstreams = [
        {
            "workstream": "财务尽调 (Financial DD)",
            "items": [
                {"item": "5 年营收 / 净利历史", "status": _check(bool(dims.get("1_financials", {}).get("data", {}).get("revenue_history")))},
                {"item": "ROE / 毛利 / 净利率", "status": _check(bool(features.get("roe_last", 0)))},
                {"item": "资产负债率", "status": _check(bool(features.get("debt_ratio", 0)))},
                {"item": "自由现金流", "status": _check(bool(features.get("fcf_positive", False)))},
                {"item": "审计意见 / 会计政策", "status": "⚪ 需人工核查"},
            ],
        },
        {
            "workstream": "商业尽调 (Commercial DD)",
            "items": [
                {"item": "市场规模 (TAM)", "status": _check(bool(dims.get("7_industry", {}).get("data", {}).get("tam")))},
                {"item": "竞争格局", "status": _check(bool(dims.get("4_peers", {}).get("data", {}).get("peer_table")))},
                {"item": "客户集中度", "status": "⚪ 需年报披露"},
                {"item": "上下游分析", "status": _check(bool(dims.get("5_chain", {}).get("data", {}).get("upstream")))},
            ],
        },
        {
            "workstream": "法律尽调 (Legal DD)",
            "items": [
                {"item": "股权结构", "status": _check(bool(dims.get("11_governance", {}).get("data", {}).get("pledge")))},
                {"item": "重大诉讼", "status": "⚪ 需披露核查"},
                {"item": "关联交易", "status": "⚪ 需年报披露"},
                {"item": "股权质押 / 内部交易", "status": _check(bool(dims.get("11_governance", {}).get("data", {}).get("insider_trades_1y")))},
            ],
        },
        {
            "workstream": "运营尽调 (Operational DD)",
            "items": [
                {"item": "护城河评估", "status": _check(features.get("moat_total", 0) > 0)},
                {"item": "研发投入", "status": "⚪ 需年报披露"},
                {"item": "管理层背景", "status": "⚪ 需人工核查"},
                {"item": "ESG 评级", "status": "⚪ 需第三方数据"},
            ],
        },
        {
            "workstream": "市场尽调 (Market DD)",
            "items": [
                {"item": "政策环境", "status": _check(bool(dims.get("13_policy", {}).get("data", {}).get("snippets")))},
                {"item": "舆情扫描", "status": _check(bool(dims.get("17_sentiment", {}).get("data", {}).get("thermometer_value")))},
                {"item": "事件驱动监控", "status": _check(bool(dims.get("15_events", {}).get("data", {}).get("recent_news")))},
                {"item": "杀猪盘排查", "status": _check(bool(dims.get("18_trap", {}).get("data", {}).get("trap_level")))},
            ],
        },
    ]

    total_items = sum(len(ws["items"]) for ws in workstreams)
    done = sum(1 for ws in workstreams for it in ws["items"] if "✅" in it["status"])
    pct = round(done / total_items * 100, 0) if total_items else 0

    return {
        "method": "Due Diligence Checklist",
        "workstreams": workstreams,
        "total_items": total_items,
        "items_auto_verified": done,
        "completion_pct": pct,
        "manual_review_required": total_items - done,
        "methodology_log": [
            f"Step 1 · 生成 5 大工作流 {total_items} 条清单",
            f"Step 2 · 自动命中 {done} 条 ({pct}%)",
            f"Step 3 · 剩余 {total_items - done} 条需人工复核",
        ],
    }


# ═══════════════════════════════════════════════════════════════
# 5. PORTER 5 FORCES + BCG MATRIX
# ═══════════════════════════════════════════════════════════════

def build_competitive_analysis(features: dict, raw_data: dict) -> dict:
    """Structured Porter 5 Forces + BCG position from raw data."""
    dims = raw_data.get("dimensions", {}) or {}
    moat = (dims.get("14_moat") or {}).get("data") or {}
    industry = (dims.get("7_industry") or {}).get("data") or {}
    peers = (dims.get("4_peers") or {}).get("data") or {}

    moat_scores = moat.get("scores", {}) if isinstance(moat, dict) else {}

    # Porter 5 Forces — 1-5 scale (1 = low threat / 5 = high threat)
    # Lower threat = better for incumbent
    barriers = _num(moat_scores.get("intangible", 5))  # 1-10 scale
    switching = _num(moat_scores.get("switching", 5))
    scale = _num(moat_scores.get("scale", 5))

    # Invert moat scores to threat scores (high moat = low threat)
    new_entrants_threat = max(1, 6 - int(barriers / 2))  # 1-5
    substitutes_threat = max(1, 6 - int(switching / 2))
    supplier_power = 3  # medium default
    buyer_power = 3
    rivalry = max(1, 6 - int(scale / 2))

    total_threat = new_entrants_threat + substitutes_threat + supplier_power + buyer_power + rivalry
    attractiveness = round((25 - total_threat) / 20 * 100, 0)  # 0-100

    # v2.12.1 · BCG 矩阵定位
    # market_share 真实 = 公司市值 / 行业总市值 × 100（stock_features 已修复）
    # industry_growth 从 industry.growth 文本解析（fetch_industry regex 已修复）
    # 阈值调整：A 股单股很少能过 15% 市占率；3% 已属行业前 top · 15% growth 是成长期线
    market_share = _num(features.get("market_share", 0))    # % 真实计算
    market_growth = _num(features.get("industry_growth", 0))  # % 真实计算

    if market_share > 3 and market_growth > 15:
        bcg = "Star (明星)"
        bcg_action = "继续投入，抢占市场"
    elif market_share > 3:
        bcg = "Cash Cow (现金牛)"
        bcg_action = "维持运营，最大化现金回收"
    elif market_growth > 15:
        bcg = "Question Mark (问号)"
        bcg_action = "选择性投入 / 或退出"
    else:
        bcg = "Dog (瘦狗)"
        bcg_action = "考虑剥离 / 收缩"

    return {
        "method": "Competitive Analysis (Porter + BCG)",
        "porter_five_forces": {
            "new_entrants_threat": {"score": new_entrants_threat, "rationale": f"进入壁垒分 {barriers:.0f}/10 (无形资产)"},
            "substitutes_threat": {"score": substitutes_threat, "rationale": f"转换成本分 {switching:.0f}/10"},
            "supplier_power": {"score": supplier_power, "rationale": "中性（未细分）"},
            "buyer_power": {"score": buyer_power, "rationale": "中性（未细分）"},
            "rivalry_intensity": {"score": rivalry, "rationale": f"规模优势分 {scale:.0f}/10"},
        },
        "industry_attractiveness_pct": attractiveness,
        "bcg_position": {
            "category": bcg,
            "market_share_pct": market_share,
            "market_growth_pct": market_growth,
            "strategic_action": bcg_action,
        },
        "methodology_log": [
            f"Step 1 · Porter 5 力合计威胁分 {total_threat}/25，行业吸引力 {attractiveness}%",
            f"Step 2 · BCG 定位 {bcg} — {bcg_action}",
        ],
    }


# ═══════════════════════════════════════════════════════════════
# 6. PORTFOLIO REBALANCE (retail-adapted)
# ═══════════════════════════════════════════════════════════════

def build_portfolio_rebalance(
    positions: list[dict],
    target_allocation: dict | None = None,
) -> dict:
    """Retail portfolio drift analyzer.

    positions: list of {ticker, name, market_value_yuan, asset_class, cost_basis}
    target_allocation: {asset_class: target_pct}, default = balanced retail
    """
    if not positions:
        return {"error": "no positions provided"}

    if target_allocation is None:
        target_allocation = {
            "A股蓝筹": 30, "A股成长": 25, "港股": 15,
            "美股": 10, "债券/货币": 15, "现金": 5,
        }

    total = sum(_num(p.get("market_value_yuan")) for p in positions)
    if total <= 0:
        return {"error": "portfolio total is 0"}

    # Current by asset class
    by_class: dict[str, float] = {}
    for p in positions:
        cls = p.get("asset_class", "A股蓝筹")
        by_class[cls] = by_class.get(cls, 0) + _num(p.get("market_value_yuan"))

    drift_rows = []
    for cls, target_pct in target_allocation.items():
        cur_value = by_class.get(cls, 0)
        cur_pct = cur_value / total * 100
        drift = cur_pct - target_pct
        target_value = total * target_pct / 100
        dollar_drift = cur_value - target_value
        drift_rows.append({
            "asset_class": cls,
            "target_pct": target_pct,
            "current_pct": round(cur_pct, 1),
            "drift_pct": round(drift, 1),
            "dollar_drift_yuan": round(dollar_drift, 0),
            "action": "减持" if drift > 5 else ("买入" if drift < -5 else "维持"),
        })

    # Flag positions outside ±5pp band
    needs_rebalance = any(abs(r["drift_pct"]) > 5 for r in drift_rows)

    return {
        "method": "Portfolio Rebalance Analysis",
        "portfolio_total_yuan": round(total, 0),
        "drift_rows": drift_rows,
        "needs_rebalance": needs_rebalance,
        "rebalance_trades": [r for r in drift_rows if abs(r["drift_pct"]) > 5],
        "methodology_log": [
            f"Step 1 · 组合总值 ¥{total:,.0f}",
            f"Step 2 · {len(drift_rows)} 个资产类别漂移检查",
            f"Step 3 · 需再平衡: {needs_rebalance}",
        ],
    }


if __name__ == "__main__":
    import json
    test = {
        "roe_5y_above_15": 0, "fcf_positive": True, "net_margin": 12.5,
        "moat_total": 27, "pe": 35, "debt_ratio": 30,
        "revenue_latest_yi": 52, "ebitda_yi": 10, "gross_margin": 35,
        "market_cap_yi": 260, "market_share": 12, "industry_growth": 14,
    }
    raw = {"dimensions": {}}
    print("=== IC Memo ===")
    m = build_ic_memo(test, raw)
    print(m["sections"]["I_exec_summary"]["headline"])
    print("\n=== Competitive ===")
    print(json.dumps(build_competitive_analysis(test, raw)["bcg_position"], ensure_ascii=False, indent=2))
    print("\n=== Value Creation ===")
    vc = build_value_creation_plan(test, raw)
    print(f"Uplift {vc['total_uplift_yi']} → Target EBITDA {vc['target_ebitda_yi']} 亿")
    print("\n=== DD Checklist ===")
    dd = build_dd_checklist(test, raw)
    print(f"{dd['items_auto_verified']}/{dd['total_items']} auto-verified")
