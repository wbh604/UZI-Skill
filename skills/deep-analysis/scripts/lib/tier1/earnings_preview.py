"""Pre-earnings preview — multi-market (A股/港股/美股) adaptation.

改编自 anthropics/financial-services equity-research/earnings-preview。

这是 research_workflow.build_earnings_analysis（"财报后" beat/miss 解读）的
"财报前" 前瞻镜像：在公司披露季报**之前**，搭建一致预期对照表、按行业分类的
观察指标、bull/base/bear 三情景（营收/EPS 区间 + 触发条件 + 历史财报后股价反应）、
催化剂清单、以及隐含波动（A 股个股多数无期权 → 用历史财报日波动代替）。

纯函数风格，与本目录其它 build_X 一致：

    build_earnings_preview(features, raw_data) -> dict

返回 consensus_table / watch_metrics / scenarios(bull/base/bear)
/ catalyst_checklist / implied_move / methodology_log。无外部 IO。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def _num(v, default=0.0) -> float:
    try:
        return float(str(v).replace("%", "").replace(",", "").replace("¥", "").strip())
    except (TypeError, ValueError):
        return default


# ───────────────────────────────────────────────────────────────
# 行业 → 关注指标映射（含 A 股本土维度）
# ───────────────────────────────────────────────────────────────
# 每条 (关键词列表, 该行业财报前最该盯的运营指标列表)
_SECTOR_METRICS: list[tuple[list[str], list[str]]] = [
    (["软件", "saas", "云", "互联网", "信息技术", "应用"],
     ["ARR / 经常性收入", "净留存率 NRR", "RPO 在手合同", "付费客户数", "云收入占比"]),
    (["零售", "消费", "商超", "电商", "连锁", "餐饮"],
     ["同店销售 SSSG", "客流量", "客单价", "线上占比", "存货周转"]),
    (["工业", "机械", "设备", "制造", "工程", "军工"],
     ["在手订单 / backlog", "book-to-bill", "量 vs 价拆分", "产能利用率"]),
    (["银行", "保险", "证券", "金融", "信托"],
     ["净息差 NIM", "不良率 / 拨备", "信贷增速", "中间业务收入", "AUM"]),
    (["医药", "生物", "医疗", "制药", "疫苗", "器械"],
     ["核心品种放量", "处方量 / 入院", "集采影响", "在研管线进度"]),
    (["白酒", "酒", "食品饮料", "调味"],
     ["动销 / 终端动销", "渠道库存", "吨价 / 提价", "预收款（合同负债）"]),
    (["光模块", "光通信", "光器件", "cpo", "硅光", "光芯片"],
     ["800G/1.6T 出货量", "高端产品占比", "毛利率（供给紧→提价）", "大客户订单能见度"]),
    (["新能源", "光伏", "储能", "锂电", "风电", "电池"],
     ["装机 / 出货量 GW", "单位盈利（元/W·Wh）", "产能利用率", "原材料价格传导"]),
    (["半导体", "芯片", "晶圆", "封装", "材料"],
     ["产能利用率", "ASP / 提价", "库存周期位置", "先进制程占比"]),
    (["汽车", "整车", "零部件", "新能源车"],
     ["销量 / 交付量", "单车 ASP", "毛利率", "新车型周期"]),
]

_DEFAULT_METRICS = ["营收 vs 共识", "毛利率趋势", "经营性现金流", "前瞻指引 vs 共识"]


def _sector_watch_metrics(industry: str, name: str) -> tuple[str, list[str]]:
    blob = f"{industry} {name}".lower()
    for kws, metrics in _SECTOR_METRICS:
        if any(kw in blob for kw in kws):
            return industry or "通用", metrics
    return industry or "通用", _DEFAULT_METRICS


# ───────────────────────────────────────────────────────────────
# 一致预期对照表
# ───────────────────────────────────────────────────────────────
def _build_consensus_table(features: dict, research: dict) -> tuple[list[dict], list[str]]:
    """从 6_research（研报/一致预期）拿；拿不到的标注「需 web 补充」。"""
    rows: list[dict] = []
    notes: list[str] = []

    # EPS 共识（features 已从 6_research 归一化出 consensus_eps_2026 等）
    cons_eps = _num(features.get("consensus_eps_2026")) or _num(research.get("consensus_eps"))
    eps_now = _num(features.get("eps"))
    if cons_eps > 0:
        yoy = round((cons_eps / eps_now - 1) * 100, 1) if eps_now > 0 else None
        rows.append({
            "metric": "EPS（市场一致预期）",
            "consensus": round(cons_eps, 3),
            "yoy_pct": yoy,
            "source": "6_research 一致预期",
        })
    else:
        rows.append({
            "metric": "EPS（市场一致预期）",
            "consensus": None, "yoy_pct": None,
            "source": "⚠️ 需 web 补充（一致预期）",
        })
        notes.append("EPS 一致预期缺失 → 需 web 搜索补充")

    # 营收共识：research 若无，用历史最新 × (1+3yCAGR) 作占位并标注
    cons_rev = _num(research.get("consensus_rev_yi"))
    rev_latest = _num(features.get("revenue_latest_yi"))
    cagr = _num(features.get("revenue_growth_3y_cagr"))
    if cons_rev > 0:
        rows.append({
            "metric": "营收（亿，一致预期）",
            "consensus": round(cons_rev, 1),
            "yoy_pct": round((cons_rev / rev_latest - 1) * 100, 1) if rev_latest > 0 else None,
            "source": "6_research 一致预期",
        })
    elif rev_latest > 0:
        proxy = round(rev_latest * (1 + cagr / 100), 1)
        rows.append({
            "metric": "营收（亿，估算）",
            "consensus": proxy,
            "yoy_pct": round(cagr, 1),
            "source": "⚠️ 无一致预期 → 用 3yCAGR 外推，需 web 补充",
        })
        notes.append("营收一致预期缺失 → 用历史 3 年 CAGR 外推占位，建议 web 核对")

    # 目标价 / 评级分布
    tp = _num(features.get("target_price_avg"))
    if tp > 0:
        px = _num(features.get("price"))
        rows.append({
            "metric": "卖方平均目标价",
            "consensus": round(tp, 2),
            "yoy_pct": round((tp / px - 1) * 100, 1) if px > 0 else None,
            "source": f"6_research（覆盖 {int(_num(features.get('research_coverage')))} 家 / 买入率 {_num(features.get('buy_rating_pct')):.0f}%）",
        })

    return rows, notes


# ───────────────────────────────────────────────────────────────
# Bull / Base / Bear 三情景
# ───────────────────────────────────────────────────────────────
def _build_scenarios(features: dict, market: str) -> list[dict]:
    """基于历史营收增速 + 毛利率趋势给营收/EPS 区间 + 触发条件 + 历史财报后反应。"""
    rev_latest = _num(features.get("revenue_latest_yi"))
    cagr = _num(features.get("revenue_growth_3y_cagr"))
    last_growth = _num(features.get("revenue_growth_latest"))
    eps_now = _num(features.get("eps"))
    cons_eps = _num(features.get("consensus_eps_2026"))
    base_eps = cons_eps if cons_eps > 0 else (eps_now if eps_now > 0 else 0)
    gm = _num(features.get("gross_margin"))

    # base 增速 = 历史 3yCAGR 与最近一期增速的均值（更贴近趋势）
    base_g = round((cagr + last_growth) / 2, 1) if (cagr or last_growth) else 0.0
    bull_g = round(base_g + 8, 1)
    bear_g = round(base_g - 8, 1)

    def _rev(g):
        return round(rev_latest * (1 + g / 100), 1) if rev_latest > 0 else None

    # EPS 弹性：营收超预期时毛利杠杆放大 → bull 上修幅度 > 营收幅度
    def _eps(mult):
        return round(base_eps * mult, 3) if base_eps > 0 else None

    # 历史财报后股价反应：用年化波动近似单日财报波动（无个股期权时的代理）
    vol = _num(features.get("volatility_1y"))
    hist_move = round(vol / 16.0, 1) if vol > 0 else None  # √252≈16，年化→日

    react_note = "（历史财报日股价反应可 web 核对：搜 \"{}\" earnings reaction）".format(
        features.get("name", "该股"))

    scenarios = [
        {
            "scenario": "bull",
            "label": "🟢 Bull 乐观",
            "revenue_yi": _rev(bull_g),
            "revenue_growth_pct": bull_g,
            "eps": _eps(1.12),
            "gross_margin_assumption": f"毛利率扩张（基准 {gm:.1f}% → 提价/规模效应）" if gm else "毛利率扩张",
            "triggers": [
                "营收 / 核心运营指标显著超共识（量价齐升）",
                "管理层上修全年指引",
                "高毛利产品占比提升、费用率下降",
            ],
            "expected_stock_reaction": f"+{hist_move}% 量级（参考历史财报日波动）" if hist_move else "上行，幅度参考历史财报日波动",
        },
        {
            "scenario": "base",
            "label": "⚪ Base 中性",
            "revenue_yi": _rev(base_g),
            "revenue_growth_pct": base_g,
            "eps": _eps(1.0),
            "gross_margin_assumption": f"毛利率持平（约 {gm:.1f}%）" if gm else "毛利率持平",
            "triggers": [
                "营收 / EPS 基本符合一致预期（±2%）",
                "指引维持不变",
                "无重大叙事变化",
            ],
            "expected_stock_reaction": f"±{hist_move}% 区间内震荡" if hist_move else "窄幅波动",
        },
        {
            "scenario": "bear",
            "label": "🔴 Bear 悲观",
            "revenue_yi": _rev(bear_g),
            "revenue_growth_pct": bear_g,
            "eps": _eps(0.85),
            "gross_margin_assumption": f"毛利率收缩（基准 {gm:.1f}% → 竞争/成本压力）" if gm else "毛利率收缩",
            "triggers": [
                "营收 / 核心指标不及共识，或环比走弱",
                "管理层下修指引 / 谨慎措辞",
                "毛利率受成本或价格战拖累",
            ],
            "expected_stock_reaction": f"-{hist_move}% 量级（参考历史财报日波动）" if hist_move else "下行，幅度参考历史财报日波动",
        },
    ]
    for s in scenarios:
        s["reaction_note"] = react_note
    return scenarios


# ───────────────────────────────────────────────────────────────
# 催化剂清单（财报前 3-5 个决定股价反应的看点）
# ───────────────────────────────────────────────────────────────
def _build_catalyst_checklist(features: dict, watch_metrics: list[str]) -> list[dict]:
    checklist: list[dict] = []
    # 1) 头号财务看点
    checklist.append({
        "item": "营收 / EPS vs 一致预期（及 whisper number）",
        "why": "超预期/不及是财报日股价首要驱动；buy-side whisper 常比公开共识更相关（可 web 补充）",
        "importance": "high",
    })
    # 2) 指引
    checklist.append({
        "item": "前瞻指引 vs 共识（全年营收/利润、capex）",
        "why": "买方更看下一季/全年指引，而非当期数字本身",
        "importance": "high",
    })
    # 3) 行业头号运营指标
    if watch_metrics:
        checklist.append({
            "item": f"行业核心运营指标：{watch_metrics[0]}",
            "why": "该指标拐点最先反映需求真伪，领先于利润表",
            "importance": "high",
        })
    # 4) 毛利率叙事
    checklist.append({
        "item": "毛利率方向（扩张 / 收缩）+ 管理层归因",
        "why": "毛利率趋势决定盈利弹性，叙事比单点数值更影响估值",
        "importance": "medium",
    })
    # 5) 叙事/战略变化
    if features.get("has_positive_catalyst") or features.get("has_negative_catalyst"):
        checklist.append({
            "item": "战略 / 叙事变化（并购、回购、新品、产能、诉讼）",
            "why": "近期事件流显示存在叙事变量，可能盖过财务数字",
            "importance": "medium",
        })
    return checklist[:5]


# ───────────────────────────────────────────────────────────────
# 隐含波动 / 预期波幅
# ───────────────────────────────────────────────────────────────
def _build_implied_move(features: dict, market: str) -> dict:
    vol = _num(features.get("volatility_1y"))
    hist_daily = round(vol / 16.0, 1) if vol > 0 else None  # 年化→单日近似
    if market == "A":
        return {
            "method": "历史财报日波动代替（A 股个股无期权）",
            "options_available": False,
            "implied_move_pct": None,
            "historical_proxy_pct": hist_daily,
            "note": "A 股无个股期权 → 用历史财报日 ±波动估计预期波幅；"
                    f"年化波动 {vol:.0f}% → 单日近似 ±{hist_daily}%" if hist_daily
                    else "A 股无个股期权，且历史波动数据不足，需 web 补充历史财报日反应",
        }
    # 美股 / 港股：可用期权隐含波动
    return {
        "method": "期权隐含波动（at-the-money straddle）",
        "options_available": True,
        "implied_move_pct": None,
        "historical_proxy_pct": hist_daily,
        "note": "美股/港股可用财报到期 ATM straddle 报价反推 implied move（需 web 补充期权链）；"
                f"历史波动近似单日 ±{hist_daily}% 作为下限参考" if hist_daily
                else "可用财报到期 ATM straddle 反推 implied move（需 web 补充期权链）",
    }


# ───────────────────────────────────────────────────────────────
# 主函数
# ───────────────────────────────────────────────────────────────
def build_earnings_preview(features: dict, raw_data: dict) -> dict:
    """财报前预览（pre-earnings preview）· 多市场。

    Args:
        features: extract_features 输出的扁平特征字典。
        raw_data: 含 dimensions 的原始数据（用于直接读 6_research 等维度）。

    Returns:
        dict — consensus_table / watch_metrics / scenarios(bull/base/bear)
               / catalyst_checklist / implied_move / methodology_log。
    """
    features = features or {}
    raw_data = raw_data or {}
    dims = raw_data.get("dimensions", {}) or {}
    research = (dims.get("6_research") or {}).get("data") or {}

    name = features.get("name", "—")
    industry = features.get("industry", "—")
    market = features.get("market", "A")
    now = datetime.now()

    # 报告季度（粗略：当前下一个季度末）
    q_month = ((now.month - 1) // 3 + 1)
    report_quarter = f"{now.year} Q{q_month}"

    consensus_table, cons_notes = _build_consensus_table(features, research)
    sector_label, watch_metrics = _sector_watch_metrics(industry, name)
    scenarios = _build_scenarios(features, market)
    catalyst_checklist = _build_catalyst_checklist(features, watch_metrics)
    implied_move = _build_implied_move(features, market)

    market_name = {"A": "A股", "HK": "港股", "US": "美股"}.get(market, market)

    methodology_log = [
        f"Step 1 · 公司={name}（{market_name}）· 行业={industry} · 预览季度≈{report_quarter}",
        f"Step 2 · 一致预期对照：{len(consensus_table)} 行"
        + (f"（{len(cons_notes)} 项需 web 补充）" if cons_notes else "（数据齐备）"),
        f"Step 3 · 观察指标按行业分类 → {sector_label}：{len(watch_metrics)} 项",
        f"Step 4 · 三情景：Bull {scenarios[0]['revenue_growth_pct']}% / "
        f"Base {scenarios[1]['revenue_growth_pct']}% / Bear {scenarios[2]['revenue_growth_pct']}% 营收增速",
        f"Step 5 · 催化剂清单 {len(catalyst_checklist)} 项；"
        f"隐含波动 → {implied_move['method']}",
    ]

    return {
        "method": "Earnings Preview (pre-earnings)",
        "company": {"name": name, "code": features.get("code"),
                    "industry": industry, "market": market},
        "report_quarter": report_quarter,
        "generated_at": now.strftime("%Y-%m-%d"),
        "consensus_table": consensus_table,
        "consensus_notes": cons_notes,
        "watch_metrics": {"sector": sector_label, "metrics": watch_metrics},
        "scenarios": scenarios,
        "catalyst_checklist": catalyst_checklist,
        "implied_move": implied_move,
        "methodology_log": methodology_log,
    }


if __name__ == "__main__":
    import json
    demo_features = {
        "name": "中际旭创", "code": "300308.SZ", "industry": "光模块", "market": "A",
        "price": 120.0, "eps": 4.5, "consensus_eps_2026": 6.2,
        "revenue_latest_yi": 240.0, "revenue_growth_3y_cagr": 45.0,
        "revenue_growth_latest": 60.0, "gross_margin": 33.0,
        "target_price_avg": 150.0, "research_coverage": 28, "buy_rating_pct": 90,
        "volatility_1y": 55.0, "has_positive_catalyst": True,
    }
    print(json.dumps(build_earnings_preview(demo_features, {}), ensure_ascii=False, indent=2))
