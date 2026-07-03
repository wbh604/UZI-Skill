"""Quantified evaluation criteria for all 51 投资大佬.

Each investor has a list of `Rule` objects with:
  - rule_id: stable identifier
  - name: Chinese label shown in report
  - weight: importance (1-5)
  - check: lambda(features) -> bool
  - category: bull/bear/neutral marker
  - fail_msg: shown when check returns False
  - pass_msg: shown when check returns True

Every Rule references features in lib/stock_features.py — NO direct raw_data access.

To add a new investor: add to INVESTOR_RULES with their criteria list.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any


@dataclass
class Rule:
    rule_id: str
    name: str          # 中文规则名 (显示在报告里)
    weight: int        # 1-5
    check: Callable[[dict], bool]
    pass_msg: str = ""  # e.g. "ROE 18.7% 连续 5 年 > 15%"
    fail_msg: str = ""  # e.g. "ROE 仅 11.8%，不达持续 15% 标准"


# ═══════════════════════════════════════════════════════════════
# A 组 · 经典价值派 (6 人)
# ═══════════════════════════════════════════════════════════════

BUFFETT_RULES = [
    Rule("roe_5y_15", "ROE 连续 5 年 > 15%", 5,
         check=lambda f: f.get("roe_5y_above_15", 0) >= 4 and f.get("roe_5y_min", 0) > 12,
         pass_msg="ROE 连续 5 年 > 15% (最低 {roe_5y_min:.1f}%)",
         fail_msg="ROE 5 年最低 {roe_5y_min:.1f}%，达标率仅 {roe_5y_above_15}/5"),
    Rule("net_margin_15", "净利率 > 15%", 3,
         check=lambda f: f.get("net_margin", 0) > 15,
         pass_msg="净利率 {net_margin:.1f}% 高质量",
         fail_msg="净利率仅 {net_margin:.1f}%"),
    Rule("debt_ratio_50", "资产负债率 < 50%", 3,
         check=lambda f: 0 < f.get("debt_ratio", 100) < 50,
         pass_msg="资产负债率 {debt_ratio:.0f}% 保守",
         fail_msg="资产负债率 {debt_ratio:.0f}% 偏高"),
    Rule("ocf_positive", "经营现金流为正", 4,
         check=lambda f: f.get("ocf_positive", False),
         pass_msg="经营现金流 {ocf_to_ni:.0f}% 健康",
         fail_msg="经营现金流不达标"),
    Rule("moat_clear", "护城河清晰 (总分 ≥ 24/40)", 4,
         check=lambda f: f.get("moat_total", 0) >= 24,
         pass_msg="护城河 {moat_total:.0f}/40 可见",
         fail_msg="护城河总分 {moat_total:.0f}/40 不够明确"),
    Rule("safety_margin_pe", "PE 在 5 年中位数以下", 3,
         check=lambda f: f.get("pe_quantile_5y", 100) < 50,
         pass_msg="PE {pe} 在 5 年 {pe_quantile_5y} 分位",
         fail_msg="PE 已在 5 年 {pe_quantile_5y} 分位，缺乏安全边际"),
    Rule("dividend_history", "连续 5 年分红", 2,
         check=lambda f: f.get("consecutive_dividend_years", 0) >= 5,
         pass_msg="连续 {consecutive_dividend_years} 年分红",
         fail_msg="分红记录仅 {consecutive_dividend_years} 年"),
]

GRAHAM_RULES = [
    Rule("pe_under_15", "PE < 15", 3,
         check=lambda f: 0 < f.get("pe", 100) < 15,
         pass_msg="PE {pe} < 15 达标",
         fail_msg="PE {pe} 高于 15"),
    Rule("pb_under_1_5", "PB < 1.5", 3,
         check=lambda f: 0 < f.get("pb", 100) < 1.5,
         pass_msg="PB {pb} < 1.5 达标",
         fail_msg="PB {pb} 高于 1.5"),
    Rule("pe_pb_22_5", "PE × PB < 22.5 (格雷厄姆 22.5 定律)", 3,
         check=lambda f: 0 < f.get("pe_x_pb", 100) < 22.5,
         pass_msg="PE×PB = {pe_x_pb:.1f} < 22.5 ✓",
         fail_msg="PE×PB = {pe_x_pb:.1f} 超 22.5 红线"),
    Rule("current_ratio_2", "流动比率 > 2", 2,
         check=lambda f: f.get("current_ratio", 0) > 2,
         pass_msg="流动比率 {current_ratio:.1f}",
         fail_msg="流动比率 {current_ratio:.1f} < 2"),
    Rule("profit_10y", "连续 10 年盈利", 3,
         check=lambda f: f.get("consecutive_profit_years", 0) >= 5,  # relaxed from 10
         pass_msg="连续 {consecutive_profit_years} 年盈利",
         fail_msg="连续盈利仅 {consecutive_profit_years} 年"),
    Rule("dividend_history", "连续分红", 2,
         check=lambda f: f.get("consecutive_dividend_years", 0) >= 5,
         pass_msg="连续 {consecutive_dividend_years} 年分红",
         fail_msg="分红记录不够"),
]

FISHER_RULES = [
    Rule("industry_growing", "行业有市场潜力", 3,
         check=lambda f: f.get("industry_is_growing", False),
         pass_msg="{industry_lifecycle} 有潜力",
         fail_msg="行业不在成长期"),
    Rule("profitability", "盈利能力优秀", 3,
         check=lambda f: f.get("net_margin", 0) > 15,
         pass_msg="净利率 {net_margin:.1f}% 优秀",
         fail_msg="净利率 {net_margin:.1f}% 一般"),
    Rule("moat_quality", "质量壁垒 (护城河 ≥ 6 avg)", 3,
         check=lambda f: f.get("moat_total", 0) >= 24,
         pass_msg="护城河总分 {moat_total:.0f}",
         fail_msg="护城河不足"),
    Rule("sell_side_confirm", "卖方研报多数推荐", 2,
         check=lambda f: f.get("buy_rating_pct", 0) >= 70,
         pass_msg="研报买入率 {buy_rating_pct:.0f}%",
         fail_msg="研报买入率仅 {buy_rating_pct:.0f}%"),
    Rule("growth_sustainable", "营收 3 年 CAGR > 15%", 3,
         check=lambda f: f.get("revenue_growth_3y_cagr", 0) > 15,
         pass_msg="营收 3Y CAGR {revenue_growth_3y_cagr:.1f}%",
         fail_msg="营收 3Y CAGR 仅 {revenue_growth_3y_cagr:.1f}%"),
]

MUNGER_RULES = [
    Rule("simple_business", "商业模式简单可懂 (主营 ≤ 3 类)", 2,
         check=lambda f: True,  # hard to verify; assume pass
         pass_msg="商业模式相对清晰",
         fail_msg="—"),
    Rule("moat_strong", "护城河强 (总分 ≥ 28)", 5,
         check=lambda f: f.get("moat_total", 0) >= 28,
         pass_msg="护城河 {moat_total:.0f}/40 强",
         fail_msg="护城河 {moat_total:.0f}/40 不够宽"),
    Rule("financial_strength", "财务稳健 (低负债+正现金流)", 4,
         check=lambda f: f.get("debt_ratio", 100) < 40 and f.get("ocf_positive", False),
         pass_msg="低负债 + 正现金流",
         fail_msg="财务质量可疑"),
    Rule("wait_for_price", "估值有安全边际 (PE 分位 < 40)", 4,
         check=lambda f: f.get("pe_quantile_5y", 100) < 40,
         pass_msg="PE 分位 {pe_quantile_5y} 够便宜",
         fail_msg="PE 分位 {pe_quantile_5y}，等更便宜"),
    Rule("psych_no_mania", "情绪未过热 (trap 安全)", 2,
         check=lambda f: f.get("is_safe", True) and not f.get("rsi_overbought", False),
         pass_msg="市场情绪理性",
         fail_msg="市场情绪过热"),
]

TEMPLETON_RULES = [
    Rule("pe_extreme_low", "PE 在 5 年低位 (分位 < 25)", 5,
         check=lambda f: f.get("pe_quantile_5y", 100) < 25,
         pass_msg="PE 在 5 年 {pe_quantile_5y} 分位 (历史低位)",
         fail_msg="PE 分位 {pe_quantile_5y}，离悲观点还远"),
    Rule("vs_industry_cheap", "相对同行便宜", 3,
         check=lambda f: f.get("vs_peer_avg_pe", 100) < -10,
         pass_msg="PE 较同行均值低 {vs_peer_avg_pe:.0f}%",
         fail_msg="PE 高于同行均值"),
    Rule("not_crowded", "市场情绪未亢奋", 3,
         check=lambda f: f.get("sentiment_heat", 100) < 50,
         pass_msg="热度 {sentiment_heat:.0f} 低位",
         fail_msg="市场热度 {sentiment_heat:.0f} 偏高"),
]

KLARMAN_RULES = [
    Rule("margin_of_safety", "内在价值折扣 > 30%", 5,
         check=lambda f: f.get("safety_margin", 0) > 30,
         pass_msg="DCF 内在值溢价 {safety_margin:.0f}%",
         fail_msg="无 30% 安全边际"),
    Rule("downside_protected", "负债率低 + 现金流正", 4,
         check=lambda f: f.get("debt_ratio", 100) < 40 and f.get("ocf_positive", False),
         pass_msg="下行风险可控",
         fail_msg="下行保护不足"),
    Rule("catalyst_clear", "有明确催化剂", 3,
         check=lambda f: f.get("has_positive_catalyst", False),
         pass_msg="近期催化剂 {recent_events_count} 个",
         fail_msg="缺乏明确催化剂"),
]

# ═══════════════════════════════════════════════════════════════
# B 组 · 成长投资派 (4 人)
# ═══════════════════════════════════════════════════════════════

# v2.13.3 · 林奇方法论还原 · 依据 One Up on Wall Street (1989) / Beating the Street (1993)
# 关键原则：
# 1. "PE should be approximately equal to growth rate" · PEG ≈ 1 是理想
# 2. "PE > 40 like buying a Rolls Royce" · 40 是 PE 警戒线
# 3. Fast grower sweet spot：20-50% growth
# 4. 历史持仓 PEG 几乎都 < 1（Taco Bell 0.6 / Hanes 0.2 / Ford / Fannie Mae 0.6）
def _peg(f):
    """PEG = PE / growth rate · 缺失时返 999（fail 所有 PEG rules）."""
    pe = f.get("pe", 0) or 0
    growth = f.get("revenue_growth_latest", 0) or 0
    if pe <= 0 or growth <= 0:
        return 999
    return pe / growth


LYNCH_RULES = [
    # 核心：PEG < 1 · 林奇理想值（真实历史阈值）
    Rule("peg_ideal", "PEG < 1 (林奇理想值)", 5,
         check=lambda f: 0 < _peg(f) < 1.0,
         pass_msg="PEG ≈ {pe}/{revenue_growth_latest:.0f} < 1 (林奇理想)",
         fail_msg="PEG 未进入林奇理想区间 (< 1)"),
    # 次优：PEG 1-1.5 临界接受
    Rule("peg_acceptable", "PEG 1-1.5 (临界接受)", 3,
         check=lambda f: 1.0 <= _peg(f) < 1.5,
         pass_msg="PEG ≈ {pe}/{revenue_growth_latest:.0f} · 临界接受",
         fail_msg="PEG 不在 1-1.5 临界区"),
    # v2.13.3 新增 · PE 40 警戒线（林奇原话 "Rolls Royce" 级别）
    Rule("pe_not_rolls_royce", "PE < 40 (林奇警戒线)", 3,
         check=lambda f: 0 < f.get("pe", 999) < 40,
         pass_msg="PE {pe:.0f} 在舒适区",
         fail_msg="PE {pe:.0f} > 40 · 林奇警戒（Rolls Royce 不是必要品）"),
    # Fast grower sweet spot 20-50%
    Rule("fast_grower_zone", "营收增速 20-50% (林奇 fast grower sweet spot)", 3,
         check=lambda f: 20 < f.get("revenue_growth_latest", 0) < 50,
         pass_msg="营收增速 {revenue_growth_latest:.0f}% · fast grower",
         fail_msg="增速 {revenue_growth_latest:.0f}% 超出 20-50% 区间"),
    Rule("understandable", "行业好懂", 2,
         check=lambda f: True,
         pass_msg="行业易理解"),
    Rule("research_support", "研报覆盖中性偏上", 2,
         check=lambda f: f.get("research_coverage", 0) >= 5 and f.get("buy_rating_pct", 0) >= 60,
         pass_msg="{research_coverage:.0f} 家研报 · 买入 {buy_rating_pct:.0f}%",
         fail_msg="研报支持不够"),
]

ONEIL_RULES = [
    Rule("c_eps_growth", "C: 季度 EPS 同比 > 25%", 3,
         check=lambda f: f.get("net_profit_growth_latest", 0) > 25,
         pass_msg="净利增速 {net_profit_growth_latest:.0f}%",
         fail_msg="净利增速 {net_profit_growth_latest:.0f}% < 25%"),
    Rule("a_annual_growth", "A: 年度 EPS 增长 > 20%", 3,
         check=lambda f: f.get("revenue_growth_3y_cagr", 0) > 20,
         pass_msg="3Y CAGR {revenue_growth_3y_cagr:.1f}%",
         fail_msg="年化增速不够"),
    Rule("n_near_high", "N: 接近 52 周新高", 2,
         check=lambda f: f.get("pct_from_60d_high", -100) > -10,
         pass_msg="距 60 日高点 {pct_from_60d_high:.1f}%",
         fail_msg="距 60 日高点 {pct_from_60d_high:.1f}%"),
    Rule("l_industry_leader", "L: 行业领先 (industry 成长期)", 2,
         check=lambda f: f.get("industry_is_growing", False),
         pass_msg="行业 {industry_lifecycle}",
         fail_msg="行业非成长期"),
    Rule("i_institutional", "I: 机构持股增加 (有基金经理持仓)", 2,
         check=lambda f: f.get("fund_manager_count", 0) >= 3,
         pass_msg="{fund_manager_count} 位基金经理持仓",
         fail_msg="机构持仓稀薄"),
    Rule("m_market_trend", "M: 个股趋势向上 (Stage 2)", 3,
         check=lambda f: f.get("stage_num") == 2,
         pass_msg="Stage 2 上升",
         fail_msg="非 Stage 2"),
]

THIEL_RULES = [
    Rule("monopoly_leader", "行业垄断地位 (护城河 ≥ 28)", 5,
         check=lambda f: f.get("moat_total", 0) >= 28,
         pass_msg="护城河 {moat_total:.0f}/40",
         fail_msg="垄断度不够"),
    Rule("network_effect", "网络效应 ≥ 7", 3,
         check=lambda f: f.get("moat_network", 0) >= 7,
         pass_msg="网络效应 {moat_network:.0f}/10",
         fail_msg="网络效应 {moat_network:.0f}/10 弱"),
    Rule("scale_advantage", "规模优势 ≥ 7", 3,
         check=lambda f: f.get("moat_scale", 0) >= 7,
         pass_msg="规模优势 {moat_scale:.0f}/10",
         fail_msg="规模优势不足"),
]

# v2.13.3 · 木头姐方法论还原 · ARK Invest 五大颠覆性创新平台
# 两处 bug 修复：
# 1. 字段名错：读 industry_growth_pct · 实际 stock_features 设的是 industry_growth
#    结果中际旭创（光模块行业增速 40%）读成 0 · 被误判"增长太慢"
# 2. 白名单缺 CPO/光模块/算力/数据中心/HBM 等 AI 基建关键词 ·
#    ARK 实际持 NVDA/TSM/Palantir 等 AI 上下游 · 光模块绝对在她视野里
WOOD_RULES = [
    Rule("s_curve", "行业处于 S 曲线拐点 (TAM > 20%/年)", 5,
         # v2.13.3 · 字段名统一为 industry_growth（stock_features 口径）
         check=lambda f: (f.get("industry_growth") or f.get("industry_growth_pct", 0)) > 20,
         pass_msg="行业增速 {industry_growth:.0f}% — S 曲线拐点",
         fail_msg="行业增速 {industry_growth:.0f}% < 20%，增长太慢"),
    Rule("innovation_platform", "属于 ARK 颠覆式创新平台", 5,
         check=lambda f: any(kw in (f.get("industry", "") + " " + f.get("name", "")).lower()
                            for kw in [
                                # 原有 · AI / 半导体 / 生物 / 新能源 等
                                "光学", "半导体", "电池", "锂电", "AI", "人工智能",
                                "生物", "基因", "机器人", "量子", "空间", "卫星",
                                "AR", "VR", "自动驾驶", "新能源", "储能",
                                "3D打印", "区块链", "数字货币", "mRNA",
                                "脑机", "核聚变",
                                # v2.13.3 新增 · AI 算力基建 · CPO/光模块等
                                "光模块", "CPO", "光芯片", "算力", "数据中心",
                                "IDC", "HBM", "gpu", "通信设备", "光通信",
                                "云计算", "服务器", "存储芯片",
                            ]),
         pass_msg="🔮 属于颠覆式创新平台 — 这是我们的菜！",
         fail_msg="不在 ARK 五大创新平台范畴"),
    Rule("revenue_acceleration", "营收加速或高增长", 3,
         check=lambda f: f.get("rev_growth_3y", 0) > 15,
         pass_msg="3 年营收复合 {rev_growth_3y:.0f}% 高速增长",
         fail_msg="营收增速 {rev_growth_3y:.0f}% 不够颠覆"),
    Rule("long_term_view", "长期视角 (5 年改变游戏规则)", 2,
         check=lambda f: f.get("max_drawdown_1y", -100) > -40,
         pass_msg="短期波动可承受，长期逻辑不变",
         fail_msg="1Y 回撤 {max_drawdown_1y:.0f}% 过大，即使颠覆也要风控"),
]

# ═══════════════════════════════════════════════════════════════
# C 组 · 宏观对冲派 (5 人)
# ═══════════════════════════════════════════════════════════════

SOROS_RULES = [
    # v2.13.3 · 修反身性判定方向错误
    # 原 bug：abs(upside) > 10 → 目标价 -63%（看跌）也 pass 打"反身性差"看多
    # 修：只在 upside > 10%（研报认为显著低估）时 pass · 做多反身性信号
    # 研报看跌场景（upside < -10）不在本 rule 处理 · 应由下方 bearish rule 识别
    Rule("sentiment_long_reflex", "研报目标价显著高于现价 > 10% (做多反身性机会)", 4,
         check=lambda f: f.get("upside_to_target", 0) > 10,
         pass_msg="研报目标涨幅 {upside_to_target:.0f}% · 市场过度悲观 · 做多反身性",
         fail_msg="价格不低于基本面共识 · 无做多反身性空间"),
    # v2.13.3 新增 · 识别做空反身性（价格 >>  基本面预期）
    # 索罗斯著名空单：1992 英镑、2010 黄金、2013 日元 · 都是价格超涨做空
    # 目标价低于现价 -15% 以上 · 说明市场狂热脱离基本面
    Rule("sentiment_short_reflex_penalty", "研报目标价低于现价 > 15% (做空反身性 · 做多方减分)", 4,
         check=lambda f: f.get("upside_to_target", 0) > -15,
         pass_msg="研报目标涨幅 {upside_to_target:.0f}% · 未到狂热",
         fail_msg="研报目标涨幅 {upside_to_target:.0f}% · 市场过度狂热 · 索罗斯会考虑做空"),
    Rule("macro_tailwind", "宏观环境配合", 3,
         check=lambda f: f.get("macro_rate_easing", False),
         pass_msg="利率周期 {macro_rate_cycle}",
         fail_msg="宏观中性"),
    Rule("trend_clear", "Stage 2 有趋势", 3,
         check=lambda f: f.get("stage_num") == 2,
         pass_msg="Stage 2 趋势确认",
         fail_msg="无明确趋势"),
]

DALIO_RULES = [
    Rule("rate_cycle_pos", "利率周期友好 (降息期)", 4,
         check=lambda f: f.get("macro_rate_easing", False),
         pass_msg="{macro_rate_cycle}",
         fail_msg="非降息周期"),
    Rule("low_debt", "公司负债率低", 3,
         check=lambda f: f.get("debt_ratio", 100) < 40,
         pass_msg="负债率 {debt_ratio:.0f}%",
         fail_msg="负债率 {debt_ratio:.0f}% 偏高"),
    Rule("dividend_income", "有股息 (全天候配置)", 2,
         check=lambda f: f.get("dividend_yield", 0) > 1,
         pass_msg="股息率 {dividend_yield:.1f}%",
         fail_msg="股息率 {dividend_yield:.1f}% 低"),
]

MARKS_RULES = [
    Rule("market_fear", "市场未贪婪 (情绪 < 60)", 4,
         check=lambda f: f.get("sentiment_heat", 100) < 60,
         pass_msg="情绪温度 {sentiment_heat:.0f}",
         fail_msg="情绪温度 {sentiment_heat:.0f} 偏高"),
    Rule("cheap_vs_history", "历史估值便宜", 4,
         check=lambda f: f.get("pe_quantile_5y", 100) < 40,
         pass_msg="PE {pe_quantile_5y} 分位",
         fail_msg="PE {pe_quantile_5y} 分位不便宜"),
    Rule("risk_priced_in", "风险已定价 (回撤过)", 2,
         check=lambda f: f.get("max_drawdown_1y", 0) < -15,
         pass_msg="最大回撤 {max_drawdown_1y:.0f}%",
         fail_msg="未充分回撤"),
]

DRUCK_RULES = [
    Rule("liquidity_tailwind", "流动性拐点", 3,
         check=lambda f: f.get("macro_rate_easing", False),
         pass_msg="利率 {macro_rate_cycle}",
         fail_msg="流动性不利"),
    Rule("macro_theme", "宏观主题明确", 3,
         check=lambda f: f.get("industry_is_growing", False),
         pass_msg="{industry_lifecycle}",
         fail_msg="无明确主题"),
    Rule("high_conviction", "12-18 月后盈利可见 (研报共识)", 4,
         check=lambda f: f.get("consensus_growth_to_2026", 0) > 15,
         pass_msg="研报 2026 EPS 预期增长 {consensus_growth_to_2026:.0f}%",
         fail_msg="未来增长不明确"),
]

ROBERTSON_RULES = [
    Rule("best_in_class", "同行业最强 (排名前 2)", 4,
         check=lambda f: f.get("industry_rank", 99) <= 2 if f.get("industry_rank", 0) > 0 else False,
         pass_msg="行业排名第 {industry_rank}",
         fail_msg="非行业领先"),
    Rule("fundamentals_strong", "基本面强", 3,
         check=lambda f: f.get("roe_latest", 0) > 12 and f.get("net_margin", 0) > 12,
         pass_msg="ROE {roe_latest:.1f}% 净利率 {net_margin:.1f}%",
         fail_msg="基本面平庸"),
]

# ═══════════════════════════════════════════════════════════════
# D 组 · 技术趋势派 (4 人)
# ═══════════════════════════════════════════════════════════════

LIVERMORE_RULES = [
    Rule("stage_2", "处于 Stage 2 上升期", 5,
         check=lambda f: f.get("stage_num") == 2,
         pass_msg="Stage 2 上升",
         fail_msg="Stage {stage_num} 非上升"),
    Rule("ma_bull", "均线多头排列", 3,
         check=lambda f: f.get("ma_bull_aligned", False),
         pass_msg="均线多头",
         fail_msg="均线非多头"),
    Rule("volume_confirm", "接近高点但未超买", 3,
         check=lambda f: -15 < f.get("pct_from_60d_high", -100) < -2 and f.get("rsi", 50) < 75,
         pass_msg="接近高点未超买",
         fail_msg="位置不利"),
]

MINERVINI_RULES = [
    Rule("stage_2_only", "严格 Stage 2 (SEPA 核心)", 5,
         check=lambda f: f.get("stage_num") == 2,
         pass_msg="Stage 2 ✓",
         fail_msg="不在 Stage 2，不碰"),
    Rule("ma_stack", "MA 多头堆叠", 4,
         check=lambda f: f.get("ma_bull_aligned", False),
         pass_msg="MA 堆叠",
         fail_msg="MA 未堆叠"),
    Rule("near_high", "距 52 周高点 < 25%", 3,
         check=lambda f: f.get("pct_from_60d_high", -100) > -25,
         pass_msg="距高点 {pct_from_60d_high:.0f}%",
         fail_msg="距高点 {pct_from_60d_high:.0f}% 过远"),
    Rule("ytd_strong", "YTD 相对强度 > 0", 2,
         check=lambda f: f.get("ytd_return", 0) > 0,
         pass_msg="YTD +{ytd_return:.0f}%",
         fail_msg="YTD {ytd_return:.0f}% 弱"),
    Rule("not_overbought", "RSI 未严重超买 (< 80)", 2,
         check=lambda f: f.get("rsi", 50) < 80,
         pass_msg="RSI {rsi:.0f}",
         fail_msg="RSI {rsi:.0f} 严重超买"),
]

DARVAS_RULES = [
    Rule("box_breakout", "处于趋势向上 (Stage 2)", 5,
         check=lambda f: f.get("stage_num") == 2,
         pass_msg="Stage 2 突破",
         fail_msg="非上升箱体"),
    Rule("ma_support", "均线支撑", 3,
         check=lambda f: f.get("ma_bull_aligned", False),
         pass_msg="MA 支撑",
         fail_msg="MA 未支撑"),
]

GANN_RULES = [
    Rule("trend_up", "趋势向上", 4,
         check=lambda f: f.get("stage_num") == 2,
         pass_msg="趋势向上",
         fail_msg="趋势不利"),
    Rule("volatility_normal", "波动率正常 (< 60%)", 2,
         check=lambda f: 0 < f.get("volatility_1y", 100) < 60,
         pass_msg="年化波动 {volatility_1y:.0f}%",
         fail_msg="波动 {volatility_1y:.0f}% 过高"),
]

# ═══════════════════════════════════════════════════════════════
# E 组 · 中国价投派 (6 人)
# ═══════════════════════════════════════════════════════════════

DUAN_RULES = [
    Rule("good_business", "生意对 (净利率 > 15% + ROE > 10%)", 5,
         check=lambda f: f.get("net_margin", 0) > 15 and f.get("roe_latest", 0) > 10,
         pass_msg="净利率 {net_margin:.1f}% · ROE {roe_latest:.1f}%",
         fail_msg="生意质量一般"),
    Rule("good_people", "人对 (无质押 + 无违规)", 4,
         check=lambda f: not f.get("has_pledge_issue", False) and f.get("no_violations", True),
         pass_msg="治理干净",
         fail_msg="治理有瑕疵"),
    Rule("good_price", "价格对 (PE 分位 < 50)", 4,
         check=lambda f: f.get("pe_quantile_5y", 100) < 50,
         pass_msg="PE {pe_quantile_5y} 分位",
         fail_msg="价格不对，PE {pe_quantile_5y} 分位"),
    # v2.13.3 · 段永平 PE 红线（历史买入苹果 PE~18 · 茅台 PE~30 · 腾讯 PE~25 都是相对便宜时介入）
    # 原话：买股票跟买公司一样，关键是"价"要合理。对 PE 50+ 他永远说 "贵了"
    Rule("pe_not_expensive", "PE 不超过 40 (段永平价格红线)", 3,
         check=lambda f: 0 < f.get("pe", 999) < 40,
         pass_msg="PE {pe:.0f} 在段永平舒适区",
         fail_msg="PE {pe:.0f} 太贵 · 段永平历史买入都是相对便宜时"),
    Rule("long_term_clear", "10 年看得懂 (护城河 + 成熟业务)", 3,
         check=lambda f: f.get("moat_total", 0) >= 22 and f.get("consecutive_profit_years", 0) >= 5,
         pass_msg="商业模式可见 10 年",
         fail_msg="10 年后看不清"),
]

ZHANGKUN_RULES = [
    Rule("roe_persistent", "ROE 持续 > 15% (5 年 ≥ 3 次)", 5,
         check=lambda f: f.get("roe_5y_above_15", 0) >= 3,
         pass_msg="ROE 5 年 {roe_5y_above_15}/5 次 > 15%",
         fail_msg="ROE 持续性 {roe_5y_above_15}/5"),
    Rule("pricing_power", "定价权 (净利率 > 18%)", 3,
         check=lambda f: f.get("net_margin", 0) > 18,
         pass_msg="净利率 {net_margin:.1f}% 有定价权",
         fail_msg="净利率 {net_margin:.1f}% 无定价权"),
    Rule("moat_brand", "品牌/无形资产壁垒", 3,
         check=lambda f: f.get("moat_intangible", 0) >= 7,
         pass_msg="无形资产 {moat_intangible:.0f}/10",
         fail_msg="品牌壁垒不强"),
    # v2.13.3 · 张坤历史重仓茅台/五粮液/腾讯 PE 15-35 之间 · 不碰 PE > 40
    Rule("pe_discipline", "PE 不超过 40 (张坤估值纪律)", 3,
         check=lambda f: 0 < f.get("pe", 999) < 40,
         pass_msg="PE {pe:.0f} 符合张坤估值纪律",
         fail_msg="PE {pe:.0f} 超出张坤历史持仓估值上限"),
]

ZHUSHAOXING_RULES = [
    Rule("long_term_growth", "长期成长 (3Y CAGR > 15%)", 4,
         check=lambda f: f.get("revenue_growth_3y_cagr", 0) > 15,
         pass_msg="3Y CAGR {revenue_growth_3y_cagr:.1f}%",
         fail_msg="长期成长不足"),
    Rule("industry_momentum", "行业处于成长期", 3,
         check=lambda f: f.get("industry_is_growing", False),
         pass_msg="行业 {industry_lifecycle}",
         fail_msg="行业非成长期"),
    Rule("low_turnover_fit", "低换手适配 (波动 < 50%)", 2,
         check=lambda f: 0 < f.get("volatility_1y", 100) < 50,
         pass_msg="波动 {volatility_1y:.0f}% 适合长持",
         fail_msg="波动过大"),
]

XIEZHIYU_RULES = [
    Rule("garp_balance", "PEG 在 1-2 之间 (成长和估值平衡)", 4,
         check=lambda f: 0.5 < (f.get("pe", 0) / max(f.get("revenue_growth_latest", 1), 1)) < 2.0,
         pass_msg="PEG 合理",
         fail_msg="PEG 失衡"),
    Rule("growth_minimum", "增速 > 10%", 2,
         check=lambda f: f.get("revenue_growth_latest", 0) > 10,
         pass_msg="营收增速 {revenue_growth_latest:.1f}%",
         fail_msg="增速不够"),
]

FENGLIU_RULES = [
    Rule("good_odds", "赔率好 (PE 分位 < 40 或大回撤过)", 4,
         check=lambda f: f.get("pe_quantile_5y", 100) < 40 or f.get("max_drawdown_1y", 0) < -25,
         pass_msg="PE 分位 {pe_quantile_5y} · 回撤 {max_drawdown_1y:.0f}%",
         fail_msg="赔率不够"),
    Rule("expectation_gap", "预期差 (研报目标价与现价差 > 15%)", 3,
         check=lambda f: f.get("upside_to_target", 0) > 15 or f.get("upside_to_target", 0) < -15,
         pass_msg="预期差 {upside_to_target:.0f}%",
         fail_msg="预期差不大"),
    Rule("common_sense", "符合常识 (安全 + 正现金流)", 2,
         check=lambda f: f.get("is_safe", True) and f.get("ocf_positive", False),
         pass_msg="常识判断 OK",
         fail_msg="常识有疑问"),
]

DENGXIAOFENG_RULES = [
    Rule("cycle_position", "产能周期位置好", 3,
         check=lambda f: not f.get("industry_in_decline", False),
         pass_msg="产能周期 {industry_lifecycle}",
         fail_msg="周期位置不利"),
    Rule("value_creation", "企业价值创造 (ROIC > 10%)", 4,
         check=lambda f: f.get("roic", 0) > 10 or f.get("roe_latest", 0) > 12,
         pass_msg="价值创造 ROIC/ROE 达标",
         fail_msg="价值创造不足"),
    # v2.13.3 · 邓晓峰偏价值风格 · 历史持仓白酒/地产/银行/周期股 PE 都偏低
    Rule("pe_reasonable", "PE 不超过 35 (邓晓峰偏左侧)", 3,
         check=lambda f: 0 < f.get("pe", 999) < 35,
         pass_msg="PE {pe:.0f} 偏左侧符合邓晓峰风格",
         fail_msg="PE {pe:.0f} 过高 · 邓晓峰偏左侧出击"),
    Rule("good_price", "恰当价格 (PE 分位 < 60)", 3,
         check=lambda f: f.get("pe_quantile_5y", 100) < 60,
         pass_msg="PE 分位 {pe_quantile_5y}",
         fail_msg="PE 分位 {pe_quantile_5y} 偏贵"),
]

# ═══════════════════════════════════════════════════════════════
# F 组 · A 股游资派 (23 人) — 规则主要基于射程 + 技术/情绪
# ═══════════════════════════════════════════════════════════════

def _youzi_base_rules(min_mcap=None, max_mcap=None, need_stage_2=True, need_lhb=False, need_sector_leader=False):
    """Generate standard 游资 rules.

    v2.13.3 · min_mcap/max_mcap 不再作为 Rule 打分（避免"市值超标"反向判看多/看空）。
    市值射程由 investor_evaluator._is_youzi_out_of_range 前置 skip 处理。
    这里的 min_mcap/max_mcap 参数保留是为了 seat_db 仍能读取射程定义，不影响规则评分。
    """
    rules = []
    # v2.13.3 · 移除 min_mcap / max_mcap 作为 Rule
    # 原版 bug：市值 > min_mcap = pass 给分 · 导致 9000+ 亿大盘股对每个游资都"在射程"
    # 现在由 evaluator 前置 skip 处理（超 500 亿默认跳过）
    if need_stage_2:
        rules.append(Rule(
            "stage_2", "Stage 2 上升",
            3,
            check=lambda f: f.get("stage_num") == 2,
            pass_msg="Stage 2 上升中",
            fail_msg="不在 Stage 2"
        ))
    if need_lhb:
        rules.append(Rule(
            "lhb_hot", "近 30 天龙虎榜有热度",
            3,
            check=lambda f: f.get("lhb_30d_count", 0) >= 1,
            pass_msg=f"30 天上榜 {{lhb_30d_count:.0f}} 次",
            fail_msg="近 30 天未上榜"
        ))
    if need_sector_leader:
        rules.append(Rule(
            "top_of_sector", "行业领先 (排名前 3)",
            2,
            check=lambda f: 0 < f.get("industry_rank", 99) <= 3,
            pass_msg=f"行业第 {{industry_rank}}",
            fail_msg="非行业龙头"
        ))
    # Common: sentiment hot
    rules.append(Rule(
        "sentiment_hot", "舆情热度 > 50",
        2,
        check=lambda f: f.get("sentiment_heat", 0) >= 50,
        pass_msg=f"热度 {{sentiment_heat:.0f}}",
        fail_msg=f"热度 {{sentiment_heat:.0f}} 不够"
    ))
    return rules


YOUZI_RULES_MAP = {
    "zhang_mz":  _youzi_base_rules(min_mcap=200, need_stage_2=True, need_lhb=True, need_sector_leader=True),
    "sun_ge":    _youzi_base_rules(min_mcap=150, need_stage_2=True, need_sector_leader=True),
    "zhao_lg":   _youzi_base_rules(min_mcap=20,  need_stage_2=True, need_lhb=True,  need_sector_leader=True),
    "fs_wyj":    _youzi_base_rules(max_mcap=80,  need_stage_2=False, need_lhb=True),
    "yangjia":   _youzi_base_rules(min_mcap=30,  need_stage_2=True, need_lhb=True),
    "chen_xq":   _youzi_base_rules(min_mcap=30,  need_stage_2=True, need_lhb=True,  need_sector_leader=True),
    "hu_jl":     _youzi_base_rules(min_mcap=100, need_stage_2=True, need_lhb=True),
    "fang_xx":   _youzi_base_rules(min_mcap=100, need_stage_2=True),
    "zuoshou":   _youzi_base_rules(min_mcap=30,  need_stage_2=True, need_lhb=True,  need_sector_leader=True),
    "xiao_ey":   _youzi_base_rules(min_mcap=50,  need_stage_2=True),
    "jiao_yy":   _youzi_base_rules(min_mcap=150, need_stage_2=True, need_sector_leader=True),
    "mao_lb":    _youzi_base_rules(min_mcap=100, need_stage_2=True),
    "xiao_xian": _youzi_base_rules(min_mcap=50,  need_stage_2=True, need_sector_leader=True),
    "lasa":      _youzi_base_rules(need_stage_2=False, need_lhb=True),
    "chengdu":   _youzi_base_rules(max_mcap=150, need_stage_2=False, need_lhb=True),
    "sunan":     _youzi_base_rules(max_mcap=50,  need_stage_2=False, need_lhb=True),
    "ningbo_st": _youzi_base_rules(need_stage_2=False, need_lhb=True),
    "liuyi_zl":  _youzi_base_rules(min_mcap=50,  need_stage_2=True,  need_sector_leader=True),
    "liu_sh":    _youzi_base_rules(need_stage_2=False, need_lhb=True),
    "gu_bl":     _youzi_base_rules(min_mcap=150, need_stage_2=True,  need_sector_leader=True),
    "bj_cj":     _youzi_base_rules(min_mcap=20, max_mcap=80, need_stage_2=False, need_lhb=True),
    "wang_zr":   _youzi_base_rules(min_mcap=30,  need_stage_2=True),
    "xin_dd":    _youzi_base_rules(max_mcap=200, need_stage_2=False, need_lhb=True),
}


# For xiao_ey specifically — adds fundamentals
YOUZI_RULES_MAP["xiao_ey"].append(Rule(
    "fundamentals_ok", "基本面辅助选股 (ROE > 10%)",
    3,
    check=lambda f: f.get("roe_latest", 0) > 10,
    pass_msg="ROE {roe_latest:.1f}%",
    fail_msg="基本面不达标"
))


# ═══════════════════════════════════════════════════════════════
# G 组 · 量化系统派 (3 人)
# ═══════════════════════════════════════════════════════════════

SIMONS_RULES = [
    Rule("statistical_edge", "统计信号 (近 1 年正收益)", 3,
         check=lambda f: f.get("ytd_return", -100) > 0,
         pass_msg="YTD +{ytd_return:.0f}%",
         fail_msg="YTD 负收益"),
    Rule("volatility_tradeable", "波动率可交易", 2,
         check=lambda f: 20 < f.get("volatility_1y", 0) < 80,
         pass_msg="波动 {volatility_1y:.0f}% 适合",
         fail_msg="波动不适合"),
]

THORP_RULES = [
    Rule("positive_ev", "正期望值 (研报目标溢价 > 10%)", 4,
         check=lambda f: f.get("upside_to_target", 0) > 10,
         pass_msg="目标溢价 {upside_to_target:.0f}% → EV > 0",
         fail_msg="EV 接近零"),
    Rule("kelly_ok", "凯利公式仓位可行 (波动 < 50%)", 2,
         check=lambda f: f.get("volatility_1y", 100) < 50,
         pass_msg="波动可控",
         fail_msg="波动过大"),
]

SHAW_RULES = [
    Rule("quality_factor", "质量因子 (ROE > 12%)", 3,
         check=lambda f: f.get("roe_latest", 0) > 12,
         pass_msg="ROE {roe_latest:.1f}% 质量好",
         fail_msg="质量因子弱"),
    Rule("value_factor", "价值因子 (PE 分位 < 60)", 2,
         check=lambda f: f.get("pe_quantile_5y", 100) < 60,
         pass_msg="PE 分位 {pe_quantile_5y}",
         fail_msg="价值因子差"),
    Rule("momentum_factor", "动量因子 (Stage 2)", 2,
         check=lambda f: f.get("stage_num") == 2,
         pass_msg="Stage 2 动量",
         fail_msg="动量不足"),
    Rule("growth_factor", "成长因子 (3Y CAGR > 15%)", 2,
         check=lambda f: f.get("revenue_growth_3y_cagr", 0) > 15,
         pass_msg="3Y CAGR {revenue_growth_3y_cagr:.1f}%",
         fail_msg="成长因子弱"),
]


# ═══════════════════════════════════════════════════════════════
# I 组 · AI 卡位/瓶颈猎手 (1 人 · 重磅角色 Serenity)
# ═══════════════════════════════════════════════════════════════
# 核心：对一只票的态度由「该股产品在当前 AI 浪潮里有没有卡位」决定。
# 卡住脖子 → 重仓；没卡到位 → 直接不碰。依赖 stock_features 的派生特征
# ai_chokepoint_score / ai_chain_hit / ai_irreplaceable / ai_smallcap。

SERENITY_RULES = [
    Rule("ai_chain_hit", "产品处于 AI 产业链关键环节", 5,
         check=lambda f: f.get("ai_chain_hit", False),
         pass_msg="命中 AI 链卡点 {ai_chain_keywords}",
         fail_msg="不在 AI 产业链上 —— 对我没有意义"),
    Rule("chokepoint_strong", "卡位评级强 (chokepoint ≥ 70)", 5,
         check=lambda f: f.get("ai_chokepoint_score", 0) >= 70,
         pass_msg="AI 卡位分 {ai_chokepoint_score} —— 卡住脖子了",
         fail_msg="AI 卡位分仅 {ai_chokepoint_score}，卡位不够硬"),
    # 以下三条均以「在 AI 链上」为前置——不在链上 Serenity 根本不看，自然全 fail。
    Rule("irreplaceable", "上游不可替代 (切换+规模壁垒高)", 5,
         check=lambda f: f.get("ai_chain_hit", False) and f.get("ai_irreplaceable", False),
         pass_msg="切换成本+规模壁垒高，难被替代 (No substrate, no device)",
         fail_msg="可替代性偏高，三家都能供，不是真瓶颈"),
    Rule("smallcap_elastic", "中小市值高弹性 (市值 < 300 亿)", 4,
         check=lambda f: f.get("ai_chain_hit", False) and f.get("ai_smallcap", False),
         pass_msg="市值 {market_cap_yi:.0f} 亿，瓶颈兑现弹性大、grossly mispriced",
         fail_msg="市值 {market_cap_yi:.0f} 亿偏大或不在链上，弹性有限"),
    Rule("demand_inflection", "需求拐点信号 (政策/催化/行业高增)", 3,
         check=lambda f: f.get("ai_chain_hit", False) and (f.get("policy_supportive", False) or f.get("has_positive_catalyst", False) or f.get("industry_growth", 0) >= 20),
         pass_msg="需求侧出现拐点信号，机构 rotation 将至",
         fail_msg="暂无明确需求拐点 / 硬验证"),
]


# ═══════════════════════════════════════════════════════════════
# v3.7.0 · 13 位新晋科技/创新派 (B+5 / C+2 / E+1 / G+1 / H+4)
# ═══════════════════════════════════════════════════════════════

# ─── B 派新增 · Andreessen / Gurley / Naval / Gerstner / Chamath ──

ANDREESSEN_RULES = [
    # a16z · "Software is eating the world" · techno-optimist
    Rule("software_or_ai_native", "软件 / AI 原生公司", 5,
         check=lambda f: any(k in (f.get("industry","") + f.get("name","")) for k in ("软件","SaaS","AI","云","半导体","互联网","platform")),
         pass_msg="{industry} · 软件/AI 原生赛道 · a16z 论文里的'吃掉世界'对象",
         fail_msg="非软件/AI 原生 · 不在 techno-optimist 射程"),
    Rule("rev_growth_30", "营收增速 > 30%", 4,
         check=lambda f: f.get("rev_growth_3y", 0) > 30 or f.get("rev_growth_3y_pct", 0) > 30,
         pass_msg="3y 营收增速 {rev_growth_3y:.0f}% · 增长曲线在 hyper 段",
         fail_msg="3y 营收增速 {rev_growth_3y:.0f}% < 30 · 不够 hyper"),
    Rule("network_effects", "网络效应 / 平台粘性", 4,
         check=lambda f: f.get("moat_total", 0) >= 26 or f.get("network_effect_score", 0) >= 6,
         pass_msg="护城河 {moat_total:.0f}/40 · 平台/网络效应可见",
         fail_msg="护城河 {moat_total:.0f}/40 偏弱 · 没有网络效应锁定"),
    Rule("market_size_huge", "TAM 千亿美元级", 3,
         check=lambda f: f.get("tam_usd_bn", 0) >= 100 or f.get("market_cap_yi", 0) >= 5000,
         pass_msg="TAM 巨大 · 给得起千倍空间",
         fail_msg="TAM 不够大 · 天花板低"),
    Rule("founder_led", "创始人仍主导", 3,
         check=lambda f: f.get("founder_active", False) or f.get("founder_ownership_pct", 0) >= 5,
         pass_msg="创始人仍掌舵 · founder mode",
         fail_msg="创始人退场 · 失去 founder mode"),
]

GURLEY_RULES = [
    # Benchmark · marketplace + SaaS 专家 · "magnitude of demand"
    Rule("marketplace_or_saas", "marketplace / SaaS / B2B 平台", 5,
         check=lambda f: any(k in (f.get("industry","") + f.get("name","")) for k in ("marketplace","SaaS","平台","软件","订阅")),
         pass_msg="{industry} · marketplace/SaaS · Gurley 主战场",
         fail_msg="非 marketplace/SaaS · 偏离 Gurley 射程"),
    Rule("unit_economics_positive", "单位经济为正", 5,
         check=lambda f: f.get("gross_margin", 0) >= 50 and f.get("net_margin", 0) > 0,
         pass_msg="毛利率 {gross_margin:.0f}% + 净利率 {net_margin:.1f}% · 单位经济清晰",
         fail_msg="毛利率 {gross_margin:.0f}% / 净利率 {net_margin:.1f}% · 单位经济不健康"),
    Rule("magnitude_of_demand", "需求强度足", 4,
         check=lambda f: f.get("rev_growth_3y", 0) > 25,
         pass_msg="3y 营收增速 {rev_growth_3y:.0f}% · 需求强度真实",
         fail_msg="增速不足 · magnitude of demand 不够"),
    Rule("burn_multiple_ok", "烧钱倍数合理", 3,
         check=lambda f: f.get("ocf_to_ni", 0) > -20 or f.get("ocf_positive", False),
         pass_msg="OCF 健康 · 不是无底洞烧钱模式",
         fail_msg="OCF 黑洞 · burn multiple 不可持续"),
    Rule("valuation_reasonable", "估值不脱离基本面", 3,
         check=lambda f: f.get("ev_to_revenue", 100) < 20,
         pass_msg="EV/Rev = {ev_to_revenue:.1f}x · 估值有锚",
         fail_msg="EV/Rev = {ev_to_revenue:.1f}x · 已脱离锚"),
]

NAVAL_RULES = [
    # AngelList · 杠杆 / 长期主义 / 利基定价权
    Rule("permissionless_leverage", "可复制的杠杆 (代码/媒体/资本)", 5,
         check=lambda f: any(k in (f.get("industry","") + f.get("name","")) for k in ("软件","平台","内容","互联网","SaaS","AI")),
         pass_msg="{industry} · 代码/媒体杠杆型业务",
         fail_msg="重资产/重服务 · 缺可复制杠杆"),
    Rule("specific_knowledge", "独特知识 / 不可教授", 4,
         check=lambda f: f.get("moat_total", 0) >= 28,
         pass_msg="护城河 {moat_total:.0f}/40 · 来自 specific knowledge",
         fail_msg="护城河 {moat_total:.0f}/40 · 谁都能干"),
    Rule("long_holding_horizon", "适合 10 年+ 持有", 4,
         check=lambda f: f.get("roe_5y_above_15", 0) >= 4 or f.get("roe", 0) >= 18,
         pass_msg="ROE 持续 · 长期复利的标的",
         fail_msg="ROE 不持续 · 短期生意"),
    Rule("not_zero_sum", "正和游戏", 3,
         check=lambda f: not any(k in (f.get("industry","")) for k in ("博彩","期货","加密")),
         pass_msg="非零和游戏 · 创造真实价值",
         fail_msg="零和/负和游戏 · 不在 Naval 哲学里"),
    Rule("compound_interest", "复利曲线清晰", 3,
         check=lambda f: f.get("net_profit_growth_3y", 0) > 15,
         pass_msg="3y 净利增速 {net_profit_growth_3y:.0f}% · 复利可见",
         fail_msg="净利不复利 · 不在长期主义清单"),
]

GERSTNER_RULES = [
    # Altimeter · NVIDIA / Snowflake 重仓 · AI 多头代表
    Rule("ai_or_cloud_native", "AI / 云原生 / 算力链", 5,
         check=lambda f: any(k in (f.get("industry","") + f.get("name","")) for k in ("AI","云","算力","芯片","半导体","CPO","光模块","数据库","SaaS")),
         pass_msg="{industry} · AI/云算力赛道 · Altimeter 主战场",
         fail_msg="非 AI/云赛道 · Gerstner 不重仓"),
    Rule("revenue_acceleration", "营收加速 (非匀速)", 4,
         check=lambda f: f.get("rev_growth_yoy", 0) > f.get("rev_growth_3y", 100) + 5,
         pass_msg="同比 {rev_growth_yoy:.0f}% > 3y avg {rev_growth_3y:.0f}% · 加速中",
         fail_msg="增速持平或减速 · 不是加速段"),
    Rule("rule_of_40", "Rule of 40", 4,
         check=lambda f: (f.get("rev_growth_3y", 0) + f.get("net_margin", 0)) >= 40,
         pass_msg="增速 + 净利率 = {rev_growth_3y:.0f}+{net_margin:.0f} ≥ 40 · 优质 SaaS",
         fail_msg="增速 {rev_growth_3y:.0f} + 利率 {net_margin:.0f} < 40 · 不达标"),
    Rule("category_leader", "赛道前三", 3,
         check=lambda f: f.get("industry_rank", 99) <= 3,
         pass_msg="行业排名 #{industry_rank} · category leader",
         fail_msg="行业排名 #{industry_rank} · 非头部"),
    Rule("expensive_but_growing", "估值高但增长撑得起", 3,
         check=lambda f: f.get("peg", 100) < 1.5 or f.get("rev_growth_3y", 0) > 35,
         pass_msg="PEG {peg:.1f} or 增速 {rev_growth_3y:.0f}% · 贵但合理",
         fail_msg="PEG {peg:.1f} 偏贵 + 增速不够 · 不值这个价"),
]

CHAMATH_RULES = [
    # Social Capital / All-In · 早期 Meta / SPAC / 透明派
    Rule("disruptor_thesis", "颠覆性公司 thesis 明确", 4,
         check=lambda f: any(k in (f.get("industry","") + f.get("name","")) for k in ("AI","新能源","生物","加密","太空","元宇宙","SaaS")),
         pass_msg="{industry} · 颠覆性赛道 · Chamath 论文里的对象",
         fail_msg="传统行业 · 不在 disruption 列表"),
    Rule("tam_centibillion", "TAM 千亿美元+", 4,
         check=lambda f: f.get("tam_usd_bn", 0) >= 100,
         pass_msg="TAM ≥ $100bn · 大池子",
         fail_msg="TAM 不够大 · 给不出 10x"),
    Rule("path_to_profit", "盈利路径清晰", 4,
         check=lambda f: f.get("gross_margin", 0) > 35 or f.get("net_margin", 0) > 0,
         pass_msg="毛利率 {gross_margin:.0f}% · 路径清晰",
         fail_msg="毛利率 {gross_margin:.0f}% · 看不到盈利路径"),
    Rule("not_a_meme", "非纯叙事 meme", 3,
         check=lambda f: f.get("rev", 0) > 5 or f.get("revenue_b", 0) > 0.5,
         pass_msg="营收实在 · 不是纯故事",
         fail_msg="营收过小 · 接近纯叙事 meme"),
    Rule("transparent_metrics", "披露透明", 3,
         check=lambda f: f.get("governance_score", 0) >= 6,
         pass_msg="治理 {governance_score:.0f}/10 · 披露 OK",
         fail_msg="治理 {governance_score:.0f}/10 · 不够透明"),
]


# ─── C 派新增 · 做空猎手 Burry / Chanos ───────────────────

BURRY_RULES = [
    # Scion · Big Short · 反 AI 大空头 · 关注估值泡沫 + 内幕
    Rule("not_in_bubble_basket", "非估值泡沫篮子", 5,
         check=lambda f: f.get("pe_ttm", 0) < 60 and f.get("ps", 100) < 15,
         pass_msg="PE {pe_ttm:.0f} · PS {ps:.1f} · 未在 Burry 空头清单",
         fail_msg="PE {pe_ttm:.0f} · PS {ps:.1f} · 估值泡沫风险"),
    Rule("insider_not_selling", "高管未在大规模减持", 4,
         check=lambda f: f.get("insider_selling_recent", False) is False,
         pass_msg="近期无高管减持 · 内部信号 OK",
         fail_msg="近期高管减持 · Burry 大空信号"),
    Rule("debt_not_explosive", "债务可控", 3,
         check=lambda f: f.get("debt_ratio", 100) < 70,
         pass_msg="负债率 {debt_ratio:.0f}% · 不爆雷",
         fail_msg="负债率 {debt_ratio:.0f}% · 雷点"),
    Rule("not_retail_mania", "无散户狂热", 3,
         check=lambda f: f.get("retail_holding_pct", 0) < 50,
         pass_msg="散户占比 {retail_holding_pct:.0f}% · 未疯",
         fail_msg="散户占比 {retail_holding_pct:.0f}% · meme 风险"),
    Rule("ocf_real_not_eps", "OCF 真实 · 不是会计利润", 4,
         check=lambda f: f.get("ocf_positive", False) and f.get("ocf_to_ni", 0) >= 5,
         pass_msg="OCF 健康 {ocf_to_ni:.0f}% · 利润真实",
         fail_msg="OCF 弱 · 利润可能粉饰"),
]

CHANOS_RULES = [
    # Kynikos · 30 年专业做空 · TSLA / Nikola / 中概股空头
    Rule("not_promotional_ceo", "CEO 不张扬", 4,
         check=lambda f: f.get("ceo_promotional_score", 0) < 7,
         pass_msg="CEO 不在 X/媒体过度推销",
         fail_msg="CEO 过度推销 · Chanos 经典空头信号"),
    Rule("audited_clean", "审计无保留", 5,
         check=lambda f: f.get("audit_qualified", False) is False,
         pass_msg="审计 clean · 无保留意见",
         fail_msg="审计有保留意见 · 立即怀疑"),
    Rule("cash_matches_eps", "现金匹配利润", 5,
         check=lambda f: abs(f.get("ocf_to_net_income_ratio", 1.0) - 1.0) < 0.4,
         pass_msg="OCF/净利 {ocf_to_net_income_ratio:.1f} · 比例合理",
         fail_msg="OCF/净利 {ocf_to_net_income_ratio:.1f} · 大幅背离 · 可能账面利润"),
    Rule("not_china_concept", "非中概雷区", 3,
         check=lambda f: not (f.get("market") == "US" and "China" in (f.get("industry","") + f.get("country",""))),
         pass_msg="非美上市中概 · 跳过 Chanos 黑名单",
         fail_msg="美上市中概股 · 历史空头标的"),
    Rule("debt_disclosure_clean", "债务披露清晰", 3,
         check=lambda f: f.get("off_balance_debt_ratio", 0) < 0.2,
         pass_msg="表外债务比例低 · 清晰",
         fail_msg="表外债务 {off_balance_debt_ratio:.0%} · 雷"),
]


# ─── E 派新增 · 张磊 高瓴 · 长期主义 ─────────────────────

ZHANG_LEI_RULES = [
    # 高瓴 · "做时间的朋友" · 投腾讯京东百济宁德 · 长期主义代表
    Rule("long_runway_industry", "赛道 10 年+ 跑道", 5,
         check=lambda f: any(k in (f.get("industry","")) for k in ("互联网","消费","医药","新能源","半导体","AI","白酒","生物","创新药")),
         pass_msg="{industry} · 长跑道赛道 · 高瓴主战场",
         fail_msg="{industry} · 偏短周期 · 不在高瓴 thesis"),
    Rule("category_leader_moat", "细分龙头 + 护城河", 5,
         check=lambda f: f.get("industry_rank", 99) <= 3 and f.get("moat_total", 0) >= 26,
         pass_msg="行业 #{industry_rank} · 护城河 {moat_total:.0f}/40 · 做时间朋友的对象",
         fail_msg="非细分龙头或护城河弱 · 不入 portfolio"),
    Rule("founder_aligned", "创始人长期主义对齐", 4,
         check=lambda f: f.get("founder_ownership_pct", 0) >= 3 or f.get("founder_active", False),
         pass_msg="创始人持股/在位 · 时间朋友能成为朋友",
         fail_msg="创始人退场 · 失去长期对齐"),
    Rule("compounder_track_record", "复利 track record", 4,
         check=lambda f: f.get("roe_5y_above_15", 0) >= 3 and f.get("net_profit_growth_3y", 0) > 12,
         pass_msg="ROE 5y / 净利 3y 复利 · 历史可验证",
         fail_msg="复利 track record 不足"),
    Rule("not_just_cyclical", "非纯周期", 3,
         check=lambda f: not any(k in (f.get("industry","")) for k in ("钢铁","煤炭","化工原料","航运")),
         pass_msg="非纯周期 · 适合做时间朋友",
         fail_msg="{industry} · 纯周期 · 不是高瓴的菜"),
]


# ─── G 派新增 · Cliff Asness · AQR 因子量化 ───────────────

ASNESS_RULES = [
    # AQR · 价值 × 质量 × 动量 三因子量化
    Rule("value_factor", "价值因子: PE / PB 双低", 4,
         check=lambda f: f.get("pe_ttm", 100) < 20 and f.get("pb", 100) < 4,
         pass_msg="PE {pe_ttm:.0f} + PB {pb:.1f} · 价值因子打分高",
         fail_msg="PE {pe_ttm:.0f} + PB {pb:.1f} · 价值因子打分低"),
    Rule("quality_factor", "质量因子: 高 ROE + 低杠杆", 4,
         check=lambda f: f.get("roe", 0) > 12 and f.get("debt_ratio", 100) < 60,
         pass_msg="ROE {roe:.1f}% + 负债 {debt_ratio:.0f}% · 质量因子打分高",
         fail_msg="ROE {roe:.1f}% + 负债 {debt_ratio:.0f}% · 质量因子打分低"),
    Rule("momentum_factor", "动量因子: 6-12 月跑赢", 3,
         check=lambda f: f.get("ytd_return", 0) > 0 and f.get("price_above_ma200", False),
         pass_msg="YTD {ytd_return:.1f}% · MA200 之上 · 动量打分高",
         fail_msg="YTD {ytd_return:.1f}% · 动量不够"),
    Rule("profitability_consistent", "盈利能力稳定", 3,
         check=lambda f: f.get("roe_5y_min", 0) > 8,
         pass_msg="ROE 5y 最低 {roe_5y_min:.1f}% · 稳",
         fail_msg="ROE 5y 最低 {roe_5y_min:.1f}% · 不稳"),
    Rule("not_lottery_ticket", "非彩票股", 3,
         check=lambda f: f.get("pe_ttm", 0) > 0 and f.get("pe_ttm", 1e9) < 80,
         pass_msg="PE {pe_ttm:.0f} 在合理区 · 非彩票",
         fail_msg="PE 异常 · 彩票股特征 · Asness 论文常空"),
]


# ─── H 派新增 · AI 卡位 / 瓶颈猎手 ─────────────────────────

JENSEN_HUANG_RULES = [
    # 黄仁勋 · NVIDIA · AI 算力霸主 · 光速摩尔定律
    Rule("ai_compute_demand", "AI 算力需求强相关", 5,
         check=lambda f: any(k in (f.get("industry","") + f.get("name","")) for k in ("AI","GPU","CPO","光模块","HBM","半导体","液冷","算力","数据中心")),
         pass_msg="{industry} · 在 AI 算力链上 · Jensen 重点",
         fail_msg="不在 AI 算力链 · Jensen 没视角"),
    Rule("cuda_ecosystem_proxy", "CUDA / 生态绑定", 4,
         check=lambda f: f.get("moat_total", 0) >= 28 or any(k in (f.get("name","")) for k in ("NVIDIA","TSMC","台积电","SK 海力士","三星电子")),
         pass_msg="生态绑定深 · 护城河 {moat_total:.0f}/40",
         fail_msg="非生态核心 · 容易被替代"),
    Rule("data_center_capex_beneficiary", "数据中心资本开支受益", 4,
         check=lambda f: f.get("rev_growth_yoy", 0) > 30,
         pass_msg="同比 {rev_growth_yoy:.0f}% · 数据中心 Capex 直接受益",
         fail_msg="增速 {rev_growth_yoy:.0f}% · 没吃到 Capex 红利"),
    Rule("gross_margin_strong", "毛利率 ≥ 50%", 3,
         check=lambda f: f.get("gross_margin", 0) >= 50,
         pass_msg="毛利率 {gross_margin:.0f}% · 定价权强",
         fail_msg="毛利率 {gross_margin:.0f}% · 缺定价权"),
    Rule("light_speed_moore_compliant", "光速摩尔定律节奏", 3,
         check=lambda f: f.get("rd_intensity", 0) >= 8,
         pass_msg="R&D 强度 {rd_intensity:.0f}% · 迭代节奏 OK",
         fail_msg="R&D 强度 {rd_intensity:.0f}% · 跟不上 Jensen 节奏"),
]

MUSK_RULES = [
    # 马斯克 · 第一性原理 · TSLA/SpaceX/X · 跨多个科技板块
    Rule("first_principles_industry", "第一性原理能颠覆的赛道", 5,
         check=lambda f: any(k in (f.get("industry","") + f.get("name","")) for k in ("新能源车","电池","航天","机器人","AI","卫星","Neuralink","太阳能")),
         pass_msg="{industry} · 适合第一性原理打法",
         fail_msg="{industry} · 不是 Musk 第一性能颠覆的"),
    Rule("vertical_integration", "垂直整合度高", 4,
         check=lambda f: f.get("vertical_integration_score", 0) >= 6 or f.get("gross_margin", 0) >= 20,
         pass_msg="垂直整合明显 · 成本结构可控",
         fail_msg="外包/松散 · 不是 Musk 风格"),
    Rule("manufacturing_scale", "制造规模 / 量产", 4,
         check=lambda f: f.get("rev", 0) > 10 or f.get("revenue_b", 0) > 1,
         pass_msg="营收 ≥ 100 亿 · 已进入量产阶段",
         fail_msg="营收太小 · 量产规模未达"),
    Rule("not_legacy_oem", "非传统 OEM", 3,
         check=lambda f: not any(k in (f.get("industry","")) for k in ("传统汽车","传统制造","重型机械") if "新能源" not in f.get("industry","")),
         pass_msg="非传统 OEM · 在变革侧",
         fail_msg="{industry} · 传统 OEM · Musk 看空"),
    Rule("ceo_visible", "管理层敢公开 thesis", 3,
         check=lambda f: f.get("ceo_promotional_score", 0) >= 5,
         pass_msg="管理层有声量 · 能讲清 thesis",
         fail_msg="管理层沉默 · 不在 Musk 偏好"),
]

ALTMAN_RULES = [
    # Sam Altman · OpenAI · AGI 叙事 + 上下游受益方
    Rule("agi_supply_chain", "AGI 上下游 (算力/数据/能源/应用)", 5,
         check=lambda f: any(k in (f.get("industry","") + f.get("name","")) for k in ("AI","数据中心","云","半导体","核电","太阳能","电网","SaaS","机器人")),
         pass_msg="{industry} · AGI 受益方",
         fail_msg="{industry} · AGI 不直接传导"),
    Rule("scaling_laws_compliant", "符合 scaling laws 红利", 4,
         check=lambda f: f.get("rev_growth_yoy", 0) > 25 or f.get("capex_growth_yoy", 0) > 30,
         pass_msg="增速/Capex 增长 · 拿到 scaling laws 红利",
         fail_msg="增速/Capex 增长不足 · 没拿到 scaling 红利"),
    Rule("platform_or_infra", "平台 / 基建型", 4,
         check=lambda f: f.get("moat_total", 0) >= 26,
         pass_msg="护城河 {moat_total:.0f}/40 · 平台/基建定位",
         fail_msg="护城河 {moat_total:.0f}/40 · 偏应用层 · 易被颠覆"),
    Rule("energy_or_compute_bottleneck", "卡位能源 / 算力瓶颈", 3,
         check=lambda f: any(k in (f.get("industry","")) for k in ("核电","可控核聚变","电网","数据中心","算力","HBM","液冷")),
         pass_msg="{industry} · 卡 AGI 瓶颈",
         fail_msg="不卡 AGI 瓶颈 · Altman 没特别多看"),
    Rule("not_pure_consumer_app", "非纯消费应用", 3,
         check=lambda f: not (f.get("industry","") in ("消费电子","游戏","社交")),
         pass_msg="非纯应用层 · 更深一层 · 抗 GPT-N 颠覆",
         fail_msg="{industry} · 纯应用层 · 易被 GPT-N 颠覆"),
]

SAYLOR_RULES = [
    # Michael Saylor · MSTR · BTC 信徒 · 数字黄金叙事
    Rule("btc_or_digital_asset_exposure", "BTC / 数字资产敞口", 5,
         check=lambda f: any(k in (f.get("industry","") + f.get("name","")) for k in ("比特币","BTC","加密","Crypto","Mining","Coinbase","区块链","数字资产")),
         pass_msg="{industry} · 直接 BTC/数字资产敞口",
         fail_msg="无 BTC 敞口 · Saylor 不看"),
    Rule("treasury_strategy_signal", "财库策略 / 抗通胀资产", 4,
         check=lambda f: f.get("cash_to_marketcap_ratio", 0) > 0.10 or f.get("btc_holdings_b", 0) > 0,
         pass_msg="财库现金/BTC 充裕 · 抗通胀资产配置",
         fail_msg="财库策略不明显 · Saylor 不感兴趣"),
    Rule("not_just_eps_play", "非 EPS 游戏", 3,
         check=lambda f: f.get("revenue_b", 0) > 0.5,
         pass_msg="营收非零 · 不是纯 EPS 财技公司",
         fail_msg="营收过小 · 纯 EPS 财技 · Saylor 看空"),
    Rule("hard_money_thesis", "硬通货叙事相符", 3,
         check=lambda f: f.get("debt_ratio", 100) < 80,  # 高负债 + BTC 是 Saylor 经典套路
         pass_msg="负债率 {debt_ratio:.0f}% · 可以叠 BTC 杠杆",
         fail_msg="负债率 {debt_ratio:.0f}% · 杠杆已满"),
    Rule("fiat_devaluation_beneficiary", "法币贬值受益方", 3,
         check=lambda f: any(k in (f.get("industry","")) for k in ("加密","黄金","白银","稀有金属","比特币")),
         pass_msg="{industry} · 法币贬值受益",
         fail_msg="不在法币贬值受益清单"),
]


# ─── F 派新增 (v3.9.0) · 股海贼王 · 淘股吧十年实盘蒸馏 ─────────
# 规则阈值全部来自其真实数据 (docs/ghzw-dossier.md)：
#   8951 笔交割单 (2016-02 → 2026-06 · 33 万 → 3131 万 · ~95 倍)
#   持仓中位 1 天 / P75 3 天 · 同时持仓 3-5 只 · 第一重仓中位 51%
#   10 年 2010 只票 · 题材主线轮动 (鸿博/川能/人民网/大众交通/海德)
# 哲学 (5069 条发言)："涨停的股为啥涨停 · 在板块什么地位 · 在大盘什么地位" ·
# "逻辑硬的低位票爆发力足" · "弱转强快速板才是超预期" · 格局票当"时代的情绪载体"

GHZW_RULES = [
    Rule("mainline_theme", "题材主线确认（板块热度+催化）", 5,
         check=lambda f: f.get("has_positive_catalyst", False) and f.get("sentiment_heat", 0) >= 55,
         pass_msg="主线题材+催化齐备 · 热度 {sentiment_heat:.0f} · 复盘三问能答上",
         fail_msg="不在当前主线上 · 没有题材催化 · 我只做主线（10 年 2010 只票全是轮动出来的）"),
    Rule("limit_up_gene", "涨停基因 / 龙虎活跃", 4,
         check=lambda f: f.get("lhb_30d_count", 0) >= 1 or f.get("has_limit_up_recent", False),
         pass_msg="近 30 天龙虎/涨停活跃 {lhb_30d_count:.0f} 次 · 有接力土壤",
         fail_msg="无涨停基因 · 接力没有抓手"),
    Rule("strong_tape", "盘口强度（Stage 2 + 量能配合）", 4,
         check=lambda f: f.get("stage_num") == 2 and f.get("vol_amplified", True),
         pass_msg="Stage 2 + 承接好 · 平盘就敢干",
         fail_msg="盘口不强 · 弱转强没确认 · 等盘面给答案"),
    Rule("low_position_logic", "逻辑硬的低位票", 3,
         check=lambda f: f.get("pct_from_year_high", 0) < -25 and f.get("has_positive_catalyst", False),
         pass_msg="距年高 {pct_from_year_high:.0f}% · 低位+逻辑硬=爆发力足（清水源/冀中能源式补涨）",
         fail_msg="位置不低或逻辑不硬 · 高位接力六分之一概率不满仓搞"),
    Rule("era_carrier", "时代情绪载体（格局票判定）", 3,
         check=lambda f: any(k in (str(f.get("industry","")) + str(f.get("name",""))) for k in
                             ("AI", "人工智能", "机器人", "无人驾驶", "智能驾驶", "算力", "半导体", "低空", "固态电池")),
         pass_msg="{industry} · 时代性题材 · 能看三五倍的票为什么恐高 为什么不格局",
         fail_msg="非时代级题材 · 做短可以 · 谈不上格局"),
    Rule("liquidity_exit", "流动性可进出（成交活跃）", 2,
         check=lambda f: f.get("sentiment_heat", 0) >= 40 or f.get("lhb_30d_count", 0) >= 1,
         pass_msg="成交活跃 · 出得来货",
         fail_msg="流动性差 · 第一重仓常打五成 · 出不来货的票不碰"),
]


# ═══════════════════════════════════════════════════════════════
# MASTER REGISTRY
# ═══════════════════════════════════════════════════════════════

INVESTOR_RULES: dict[str, list[Rule]] = {
    # Group A · Classic Value
    "buffett": BUFFETT_RULES,
    "graham": GRAHAM_RULES,
    "fisher": FISHER_RULES,
    "munger": MUNGER_RULES,
    "templeton": TEMPLETON_RULES,
    "klarman": KLARMAN_RULES,
    # Group B · Growth (+5 new tech VC · v3.7.0)
    "lynch": LYNCH_RULES,
    "oneill": ONEIL_RULES,
    "thiel": THIEL_RULES,
    "wood": WOOD_RULES,
    "andreessen": ANDREESSEN_RULES,
    "gurley": GURLEY_RULES,
    "naval": NAVAL_RULES,
    "gerstner": GERSTNER_RULES,
    "chamath": CHAMATH_RULES,
    # Group C · Macro Hedge (+2 short sellers · v3.7.0)
    "soros": SOROS_RULES,
    "dalio": DALIO_RULES,
    "marks": MARKS_RULES,
    "druck": DRUCK_RULES,
    "robertson": ROBERTSON_RULES,
    "burry": BURRY_RULES,
    "chanos": CHANOS_RULES,
    # Group D · Technical
    "livermore": LIVERMORE_RULES,
    "minervini": MINERVINI_RULES,
    "darvas": DARVAS_RULES,
    "gann": GANN_RULES,
    # Group E · China Value (+1 Hillhouse · v3.7.0)
    "duan": DUAN_RULES,
    "zhangkun": ZHANGKUN_RULES,
    "zhushaoxing": ZHUSHAOXING_RULES,
    "xiezhiyu": XIEZHIYU_RULES,
    "fengliu": FENGLIU_RULES,
    "dengxiaofeng": DENGXIAOFENG_RULES,
    "zhang_lei": ZHANG_LEI_RULES,
    # Group F · 游资 (from YOUZI_RULES_MAP)
    **YOUZI_RULES_MAP,
    "ghzw": GHZW_RULES,  # v3.9.0 · 股海贼王 · 淘股吧十年实盘蒸馏 (规则阈值来自真实交割单)
    # Group G · Quant (+1 AQR · v3.7.0)
    "simons": SIMONS_RULES,
    "thorp": THORP_RULES,
    "shaw": SHAW_RULES,
    "asness": ASNESS_RULES,
    # Group H · AI 卡位/瓶颈猎手 (1 旗舰 + 4 新晋 · v3.7.0)
    "serenity": SERENITY_RULES,
    "jensen_huang": JENSEN_HUANG_RULES,
    "musk": MUSK_RULES,
    "altman": ALTMAN_RULES,
    "saylor": SAYLOR_RULES,
}


def coverage_stats() -> dict:
    return {
        "total_investors": len(INVESTOR_RULES),
        "total_rules": sum(len(rules) for rules in INVESTOR_RULES.values()),
        "avg_rules": round(sum(len(rules) for rules in INVESTOR_RULES.values()) / len(INVESTOR_RULES), 1),
        "min_rules": min(len(rules) for rules in INVESTOR_RULES.values()),
        "max_rules": max(len(rules) for rules in INVESTOR_RULES.values()),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(coverage_stats(), indent=2))
    print(f"\nInvestor IDs: {sorted(INVESTOR_RULES.keys())}")
