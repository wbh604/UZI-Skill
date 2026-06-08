"""单只个股 · AI 就绪度 / 卡位评估模块。

改编自 anthropics/financial-services
  plugins/vertical-plugins/private-equity/skills/ai-readiness/SKILL.md

原版做的是「在 PE 组合里扫描多家 portco、按美元杠杆排序、找可复用 playbook」。
本模块把它适配成 **单只个股**——评估这一家公司在 AI 浪潮里的
暴露度 / 就绪度 / 卡位强度，并复用 Serenity 的派生特征 `ai_chokepoint_score`
作为「AI 卡位强度」的量化锚（见 lib/stock_features.py 的 AI 卡位/瓶颈点段落）。

原版三道 gate（数据在不在 / 有没有 owner / 30 天能否试点）被改写成个股版：
  ① 是否真在 AI 产业链上              (ai_chain_hit)
  ② 是否有可验证的 AI 真实收入/订单/产能 (从 5_chain / 15_events / 7_industry 推断)
  ③ 卡位是否不可替代且可持续           (ai_irreplaceable + moat)
三 yes = 「强就绪 / Go」，否则「观察 / Wait」并注明缺口。

原版里与「组合」强相关的部分（Step 3 跨公司排序、Step 4 replays、
Step 5 aggregate EBITDA）在单票语境下无意义，本模块标注 N/A，不实现。

纯函数、无 IO：
    build_ai_readiness(features: dict, raw_data: dict) -> dict
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _num(v, default=0.0) -> float:
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return default


# 关键词字典：用于从行业 + 供应链文本推断 AI 杠杆点类别
_LEVERAGE_PATTERNS: list[tuple[str, list[str]]] = [
    ("算力 / AI 芯片", ["算力", "ai 芯片", "ai芯片", "asic", "gpu", "risc-v",
                        "交换机", "ai server", "ai 服务器", "数据中心", "data center"]),
    ("光互连 / 光模块", ["光模块", "光芯片", "cpo", "光引擎", "硅光", "光通信",
                        "光器件", "激光器", "eml", "vcsel", "inp", "磷化铟",
                        "光纤", "空芯光纤"]),
    ("存储 / HBM", ["hbm", "存储", "ddr", "封装基板", "abf", "载板", "cowos", "先进封装"]),
    ("供电 / 散热", ["液冷", "散热", "电源", "bbu", "服务器电源", "pdu"]),
    ("互连 / 连接器 / PCB", ["pcb", "高速铜", "铜连接", "铜缆", "背板连接器", "连接器"]),
    ("AI 终端光学 (AR/VR)", ["光波导", "衍射光波导", "waveguide", "micro-led", "microled",
                            "硅基oled", "近眼显示", "头显", "增强现实", "虚拟现实",
                            "ar 眼镜", "ar眼镜", "车载光学", "晶圆级光学", "镜头", "摄像模组"]),
    ("AI 应用 / 软件", ["大模型", "生成式", "aigc", "智能体", "agent", "ai 应用",
                       "推理", "训练", "算法", "ai saas"]),
    ("AI 赋能传统业务", ["智能化", "数字化", "降本增效", "自动化", "机器视觉", "智能制造"]),
]


def _infer_leverage_points(blob: str, ai_keywords: list[str]) -> list[dict]:
    """从行业 + 供应链文本推断 top AI 杠杆点（最多 3 个）。

    每个杠杆点：类别 + 命中关键词 + 一句话定位（卡位 vs 赋能）。
    """
    blob = blob.lower()
    points: list[dict] = []
    for category, kws in _LEVERAGE_PATTERNS:
        hits = [kw for kw in kws if kw in blob]
        if not hits:
            continue
        # 卡位型（硬件/材料/上游）vs 赋能型（软件/传统业务 AI 化）
        if category in ("AI 应用 / 软件", "AI 赋能传统业务"):
            stance = "赋能 — AI 提升自身业务效率/产品力"
        else:
            stance = "卡位 — 处于 AI 算力/终端供应链关键环节"
        points.append({
            "category": category,
            "keywords": hits[:4],
            "stance": stance,
        })
    return points[:3]


def build_ai_readiness(features: dict, raw_data: dict) -> dict:
    """单票 AI 就绪度 / 卡位评估。

    Args:
        features: extract_features() 产出的扁平特征 dict。必含
            ai_chokepoint_score / ai_chain_hit / ai_chain_keywords /
            ai_irreplaceable / ai_smallcap（来自 lib/stock_features.py）。
        raw_data: 含 dimensions 的原始数据 dict（用于读 5_chain / 15_events / 7_industry）。

    Returns:
        结构化 dict：rating / gates / leverage_points / conclusion / methodology_log。
        与「组合」相关的字段（cross_portfolio_ranking / replays /
        aggregate_ebitda）标注 N/A — 单票语境不适用。
    """
    dims = (raw_data or {}).get("dimensions", {}) or {}

    def _dd(key: str) -> dict:
        return (dims.get(key) or {}).get("data") or {}

    chain = _dd("5_chain")
    events = _dd("15_events")
    industry = _dd("7_industry")

    name = features.get("name", "—")
    code = features.get("code") or features.get("ticker") or "—"

    # ── 复用 Serenity 派生特征作为卡位强度锚 ──
    choke = _num(features.get("ai_chokepoint_score"))
    ai_chain_hit = bool(features.get("ai_chain_hit"))
    ai_keywords = list(features.get("ai_chain_keywords") or [])
    ai_irreplaceable = bool(features.get("ai_irreplaceable"))
    ai_smallcap = bool(features.get("ai_smallcap"))
    moat_total = _num(features.get("moat_total"))

    # ── Gate ②：是否有可验证的 AI 真实收入/订单/产能 ──
    # 从 5_chain / 15_events / 7_industry 推断「真实需求」证据，而非纯概念标签。
    import json as _json
    try:
        chain_txt = _json.dumps(chain, ensure_ascii=False) if chain else ""
    except (TypeError, ValueError):
        chain_txt = str(chain)
    timeline = events.get("event_timeline") or []
    events_txt = " ".join(str(t) for t in timeline) if isinstance(timeline, list) else str(timeline)
    industry_growth = _num(features.get("industry_growth")) or _num(industry.get("growth"))

    evidence_blob = (chain_txt + " " + events_txt).lower()
    _REVENUE_EVIDENCE_KW = [
        "订单", "中标", "签约", "长协", "在手", "backlog", "供货", "导入", "量产",
        "扩产", "产能", "predict", "放量", "提价", "缺货", "满产", "认证", "送样",
    ]
    evidence_hits = [kw for kw in _REVENUE_EVIDENCE_KW if kw in evidence_blob]
    # 真实需求成立：链上 + (有订单/产能类证据 OR 行业高增景气)
    has_real_demand = ai_chain_hit and (len(evidence_hits) > 0 or industry_growth >= 20)

    gates = [
        {
            "gate": "① 是否真在 AI 产业链上",
            "pass": ai_chain_hit,
            "basis": (
                f"命中 AI 链关键词 {ai_keywords[:5]}" if ai_chain_hit
                else "未在 AI 算力/终端供应链上检出关键词"
            ),
        },
        {
            "gate": "② 是否有可验证的 AI 真实收入/订单/产能",
            "pass": has_real_demand,
            "basis": (
                (f"证据词 {evidence_hits[:4]}" if evidence_hits else "")
                + (f" · 行业增速 {industry_growth:.0f}%" if industry_growth >= 20 else "")
            ).strip(" ·") or "缺订单/产能/景气证据，疑似纯概念标签",
        },
        {
            "gate": "③ 卡位是否不可替代且可持续",
            "pass": ai_irreplaceable,
            "basis": (
                f"切换成本+规模壁垒达标（moat {moat_total:.0f}/40）" if ai_irreplaceable
                else f"不可替代性不足（moat {moat_total:.0f}/40，切换+规模未达 12/20）"
            ),
        },
    ]
    passed = sum(1 for g in gates if g["pass"])
    all_pass = passed == 3

    # ── AI 暴露评级（强/中/弱/无）——以 ai_chokepoint_score 为主锚 ──
    if not ai_chain_hit:
        rating = "无"
        rating_note = "不在 AI 产业链上 — AI 浪潮对其基本面无直接传导"
    elif choke >= 75 or (all_pass and choke >= 60):
        rating = "强"
        rating_note = "AI 卡位硬 + 真实需求可验证 + 不可替代 → 强就绪"
    elif choke >= 50 or passed >= 2:
        rating = "中"
        rating_note = "在 AI 链上且部分 gate 成立，卡位待验证"
    else:
        rating = "弱"
        rating_note = "AI 暴露偏弱 / 仅蹭概念，卡位证据不足"

    # ── 缺口（未通过的 gate）──
    gaps = [g["gate"] for g in gates if not g["pass"]]

    # Go / Wait 裁决
    if all_pass:
        verdict = "Go · 强就绪"
        verdict_note = "三道 gate 全通过 — AI 卡位可作为核心投资逻辑之一"
    else:
        verdict = "Wait · 观察"
        verdict_note = f"缺口：{'；'.join(gaps)}" if gaps else "待补充验证"

    # ── Top 2-3 AI 杠杆点 ──
    try:
        ind_txt = _json.dumps(industry, ensure_ascii=False) if isinstance(industry, dict) else str(industry)
    except (TypeError, ValueError):
        ind_txt = str(industry)
    leverage_blob = " ".join([
        str(features.get("industry", "")), str(name),
        chain_txt, ind_txt, events_txt, " ".join(ai_keywords),
    ])
    leverage_points = _infer_leverage_points(leverage_blob, ai_keywords)
    if not leverage_points and ai_chain_hit:
        leverage_points = [{
            "category": "AI 产业链关联（未归类）",
            "keywords": ai_keywords[:4],
            "stance": "卡位 — 已检出 AI 链关键词，建议人工细分环节",
        }]

    # ── 一句话结论 ──
    if rating == "无":
        conclusion = f"{name}（{code}）不在 AI 产业链上，AI 就绪度评级「无」，本维度对论点无加分（N/A）。"
    else:
        lev_str = "、".join(p["category"] for p in leverage_points) or "—"
        conclusion = (
            f"{name}（{code}）AI 暴露评级「{rating}」（卡位强度 {choke:.0f}/100），"
            f"通过 {passed}/3 道 gate → {verdict}；主要 AI 杠杆点：{lev_str}。"
        )

    return {
        "method": "AI Readiness (single-stock) · 改编自 PE ai-readiness + 复用 ai_chokepoint_score",
        "company": {"name": name, "code": code},
        "generated_at": datetime.now().strftime("%Y-%m-%d"),
        "rating": rating,
        "rating_note": rating_note,
        "ai_chokepoint_score": choke,
        "ai_smallcap": ai_smallcap,
        "gates": gates,
        "gates_passed": passed,
        "gates_total": 3,
        "verdict": verdict,
        "verdict_note": verdict_note,
        "gaps": gaps,
        "leverage_points": leverage_points,
        "conclusion": conclusion,
        # ── 组合维度 · 单票不适用 ──
        "cross_portfolio_ranking": "N/A · 单票评估，无跨公司排序（原版 Step 3）",
        "replays": "N/A · 单票评估，无跨公司可复用 playbook（原版 Step 4）",
        "aggregate_ebitda": "N/A · 单票评估，无组合级 EBITDA 汇总（原版 Step 5）",
        "methodology_log": [
            f"Step 1 · 复用 Serenity ai_chokepoint_score = {choke:.0f}/100（卡位强度锚）",
            f"Step 2 · Gate① AI 链命中={ai_chain_hit} · Gate② 真实需求={has_real_demand} · Gate③ 不可替代={ai_irreplaceable}",
            f"Step 3 · 通过 {passed}/3 → 评级「{rating}」· {verdict}",
            f"Step 4 · 推断 {len(leverage_points)} 个 AI 杠杆点",
            "Step 5 · 组合排序/replays/EBITDA 汇总 → 单票 N/A",
        ],
    }


if __name__ == "__main__":
    import json
    demo_features = {
        "name": "AXT科技", "code": "TEST.US", "industry": "磷化铟InP衬底/光模块",
        "market_cap_yi": 80, "moat_total": 25,
        "ai_chokepoint_score": 88.0, "ai_chain_hit": True,
        "ai_chain_keywords": ["inp", "磷化铟", "光模块", "cpo"],
        "ai_irreplaceable": True, "ai_smallcap": True, "industry_growth": 35,
    }
    demo_raw = {"dimensions": {
        "5_chain": {"data": {"desc": "磷化铟 InP 衬底 光模块 上游"}},
        "15_events": {"data": {"event_timeline": ["大订单 缺货涨价 扩产"]}},
        "7_industry": {"data": {"growth": "35%"}},
    }}
    print(json.dumps(build_ai_readiness(demo_features, demo_raw), ensure_ascii=False, indent=2))
