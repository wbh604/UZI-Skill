"""pipeline.score_fns · 纯函数 · 从 run_real_test.py 搬迁 (v3.1).

### 搬迁内容
- `_f(v, default)` · 安全 float 解析（百分号 / 逗号 / 中文货币）
- `score_dimensions(raw)` · 22 维打分
- `generate_panel(dims_scored, raw)` · 51 评委投票 + school_scores
- `_auto_summarize_dim(dim_key, label, dim, score)` · 维度摘要
- `_autofill_qualitative_via_mx(raw, ticker)` · MX 兜底（原地改 raw）
- `_extract_mx_text(result)` · MX 响应解析 helper
- `generate_synthesis(raw, dims_scored, panel, agent_analysis=None)` · 综合研判

### 为什么独立模块
v2.15.x 连续 hotfix 集中在 run_real_test.py (2105 行) · 业务函数和 CLI 入口混杂。
v3.1 拆分：纯函数放这里 · rrt.py 只剩 stage1/stage2/main CLI 入口 + collect_raw_data.

### 向后兼容
rrt.py 仍 re-export 这些函数 (from lib.pipeline.score_fns import *)· 所有
`rrt.score_dimensions(...)` / `rrt.generate_panel(...)` / `rrt.generate_synthesis(...)`
调用保持工作 · pipeline.score 和 legacy 都能调.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

# rrt 当前 sys.path 里的依赖（由 rrt 加入 · score_fns 只要 import）
from lib.investor_db import INVESTORS
from lib.investor_personas import get_comment as _persona_comment
from lib.investor_evaluator import evaluate as _evaluate_investor
from lib.stock_features import extract_features
from lib.market_router import parse_ticker


# ═══════════════════════════════════════════════════════════════
# 以下为从 run_real_test.py 原样搬迁的纯函数（保持行为零差异）
# 搬迁日期：v3.1 · 2026-04-23
# ═══════════════════════════════════════════════════════════════


def _f(v, default=0.0):
    try:
        return float(str(v).replace("%", "").replace(",", "").replace("+", ""))
    except (ValueError, TypeError):
        return default


def score_dimensions(raw: dict) -> dict:
    dims = raw.get("dimensions", {})
    out = {}

    def _get(key: str) -> dict:
        return (dims.get(key) or {}).get("data") or {}

    # 1 · 财报
    fin = _get("1_financials")
    roe = _f(fin.get("roe"))
    last_roe = (fin.get("roe_history") or [0])[-1] if fin.get("roe_history") else roe
    net_margin = _f(fin.get("net_margin"))
    health = fin.get("financial_health") or {}
    debt = _f(health.get("debt_ratio"))
    rev_hist = fin.get("revenue_history") or []
    growth = ((rev_hist[-1] - rev_hist[-2]) / rev_hist[-2] * 100) if len(rev_hist) >= 2 and rev_hist[-2] else 0
    score_1 = 5
    if last_roe >= 15: score_1 += 2
    elif last_roe >= 10: score_1 += 1
    elif last_roe < 5: score_1 -= 2
    if net_margin >= 15: score_1 += 1
    if growth >= 20: score_1 += 1
    if debt >= 60: score_1 -= 1
    score_1 = max(1, min(10, score_1))
    reasons_pass_1 = []
    reasons_fail_1 = []
    if last_roe >= 15: reasons_pass_1.append(f"ROE 最新 {last_roe:.1f}%")
    elif last_roe < 8: reasons_fail_1.append(f"ROE 最新 {last_roe:.1f}% 偏低")
    if growth >= 20: reasons_pass_1.append(f"营收增速 {growth:.1f}%")
    elif growth < 5: reasons_fail_1.append(f"营收增速 {growth:.1f}% 停滞")
    if debt < 40: reasons_pass_1.append(f"资产负债率 {debt:.0f}% 健康")
    elif debt > 60: reasons_fail_1.append(f"资产负债率 {debt:.0f}% 偏高")
    out["1_financials"] = {"score": score_1, "weight": 5,
                            "label": f"ROE {last_roe:.1f}% · 营收增速 {growth:+.1f}% · 负债率 {debt:.0f}%",
                            "reasons_pass": reasons_pass_1, "reasons_fail": reasons_fail_1}

    # 2 · K 线
    kline = _get("2_kline")
    stage = str(kline.get("stage", ""))
    ma_align = str(kline.get("ma_align", ""))
    stats = kline.get("kline_stats") or {}
    score_2 = 5
    if "Stage 2" in stage: score_2 += 2
    elif "Stage 1" in stage: score_2 += 1
    elif "Stage 3" in stage or "Stage 4" in stage: score_2 -= 2
    if "多头" in ma_align: score_2 += 1
    dd_str = stats.get("max_drawdown", "0%")
    dd = _f(dd_str)
    if dd <= -30: score_2 -= 1
    score_2 = max(1, min(10, score_2))
    label_2 = f"{stage} · 均线{ma_align}"
    if stats.get("ytd_return"): label_2 += f" · YTD {stats['ytd_return']}"
    out["2_kline"] = {"score": score_2, "weight": 4, "label": label_2,
                      "reasons_pass": [f"{stage}"] if "Stage 2" in stage else [],
                      "reasons_fail": [f"最大回撤 {dd:.1f}%"] if dd <= -25 else []}

    # 3 · 宏观 (qualitative — give middle)
    out["3_macro"] = {"score": 6, "weight": 3, "label": "宏观环境中性"}

    # 4 · 同行
    peers = _get("4_peers")
    peer_table = peers.get("peer_table") or []
    score_4 = 5
    if peer_table and len(peer_table) > 1:
        score_4 = 7  # we have data
        try:
            self_row = next((p for p in peer_table if p.get("is_self")), None)
            if self_row:
                self_pe = _f(self_row.get("pe"))
                avg_pe = sum(_f(p.get("pe")) for p in peer_table if not p.get("is_self")) / max(1, len([p for p in peer_table if not p.get("is_self")]))
                if self_pe > 0 and avg_pe > 0:
                    if self_pe < avg_pe * 0.9: score_4 += 1
                    elif self_pe > avg_pe * 1.2: score_4 -= 1
        except Exception:
            pass
    out["4_peers"] = {"score": score_4, "weight": 4,
                      "label": f"同业 {len(peer_table) - 1} 家对比" if peer_table else "无同行数据",
                      "reasons_pass": [], "reasons_fail": []}

    # 5 · 上下游
    chain = _get("5_chain")
    breakdown = chain.get("main_business_breakdown") or []
    score_5 = 6 if breakdown else 5
    out["5_chain"] = {"score": score_5, "weight": 4,
                      "label": f"主营 {len(breakdown)} 类业务已识别" if breakdown else "产业链数据不完整",
                      "reasons_pass": [], "reasons_fail": []}

    # 6 · 研报
    research = _get("6_research")
    coverage = research.get("report_count", 0)
    ratings = research.get("rating_distribution") or {}
    buy_count = sum(v for k, v in ratings.items() if "买入" in str(k) or "增持" in str(k))
    score_6 = 5 + min(3, coverage // 5)
    if buy_count >= 10: score_6 += 1
    score_6 = min(10, score_6)
    out["6_research"] = {"score": score_6, "weight": 3,
                         "label": f"{coverage} 份研报 · 买入/增持 {buy_count} 份" if coverage else "研报数据稀少",
                         "reasons_pass": [f"覆盖券商 {coverage} 家"] if coverage >= 10 else [],
                         "reasons_fail": [] if coverage else ["缺乏覆盖"]}

    # 7 · 行业景气 (stub heavy qualitative)
    out["7_industry"] = {"score": 7, "weight": 4, "label": "行业处于成长期"}

    # 8 · 原材料
    out["8_materials"] = {"score": 6, "weight": 3, "label": "原材料成本关注中"}

    # 9 · 期货关联
    out["9_futures"] = {"score": 5, "weight": 2, "label": "无强关联期货品种"}

    # 10 · 估值
    val = _get("10_valuation")
    pe_q_str = str(val.get("pe_quantile", ""))
    import re
    m = re.search(r'(\d+)', pe_q_str)
    pe_q = int(m.group(1)) if m else 50
    score_10 = 5
    if pe_q < 30: score_10 = 9
    elif pe_q < 50: score_10 = 7
    elif pe_q < 70: score_10 = 5
    elif pe_q < 85: score_10 = 3
    else: score_10 = 2
    out["10_valuation"] = {"score": score_10, "weight": 5,
                            "label": f"PE {val.get('pe', '—')} · 5 年 {pe_q} 分位 · 行业均值 {val.get('industry_pe', '—')}",
                            "reasons_pass": ["PE 在 5 年中位数以下"] if pe_q < 50 else [],
                            "reasons_fail": ["PE 已在 5 年高位区"] if pe_q >= 75 else []}

    # 11 · 治理
    gov = _get("11_governance")
    pledge = gov.get("pledge") or []
    has_insider = bool(gov.get("insider_trades_1y"))
    score_11 = 6
    if not pledge or (isinstance(pledge, list) and len(pledge) == 0): score_11 += 1
    if has_insider: score_11 += 1
    out["11_governance"] = {"score": min(10, score_11), "weight": 4,
                             "label": f"质押记录 {len(pledge) if isinstance(pledge, list) else '—'} · 内部交易 {'有' if has_insider else '无'}"}

    # 12 · 资金面 (v2.2: 主力资金替代北向，北向已关停)
    cap = _get("12_capital_flow")
    main_flow = cap.get("main_fund_flow_20d") or []
    main_5d_net = 0
    if main_flow:
        for rec in main_flow[:5]:
            v = rec.get("主力净流入-净额", 0) if isinstance(rec, dict) else 0
            try:
                main_5d_net += float(v)
            except (ValueError, TypeError):
                pass
    main_5d_label = f"{main_5d_net / 1e8:+.1f}亿" if main_5d_net else "—"
    unlock = cap.get("unlock_schedule") or []
    score_12 = 5
    if main_5d_net > 0: score_12 += 2
    elif main_5d_net < 0: score_12 -= 1
    if len(unlock) == 0: score_12 += 1
    score_12 = max(1, min(10, score_12))
    out["12_capital_flow"] = {"score": score_12, "weight": 4,
                               "label": f"主力 5日 {main_5d_label} · 12 个月解禁 {len(unlock)} 次",
                               "reasons_pass": [f"主力资金 5 日净流入 {main_5d_label}"] if main_5d_net > 0 else [],
                               "reasons_fail": [f"主力资金 5 日净流出 {main_5d_label}"] if main_5d_net < 0 else []}

    # 13 · 政策
    out["13_policy"] = {"score": 6, "weight": 3, "label": "政策环境中性"}

    # 14 · 护城河
    out["14_moat"] = {"score": 6, "weight": 3, "label": "护城河需定性评估"}

    # 15 · 事件
    events = _get("15_events")
    news = events.get("news") or []
    notices = events.get("recent_notices") or []
    score_15 = 5 + min(3, len(news) // 10)
    out["15_events"] = {"score": score_15, "weight": 4,
                        "label": f"近期新闻 {len(news)} 条 · 公告 {len(notices)} 份"}

    # 16 · 龙虎榜
    lhb = _get("16_lhb")
    lhb_count = lhb.get("lhb_count_30d", 0)
    matched = lhb.get("matched_youzi") or []
    score_16 = 5 + min(3, lhb_count // 2)
    if matched: score_16 += 1
    score_16 = min(10, score_16)
    out["16_lhb"] = {"score": score_16, "weight": 4,
                     "label": f"近 30 天上榜 {lhb_count} 次 · 识别游资 {len(matched)} 位",
                     "reasons_pass": [f"{'/'.join(matched[:3])} 席位出现"] if matched else []}

    # 17 · 舆情
    hot = _get("17_sentiment")
    hot_rank = (hot.get("hot_rank") or {}).get("rank_history") or []
    score_17 = 6 + min(2, len(hot_rank) // 10)
    out["17_sentiment"] = {"score": score_17, "weight": 3,
                            "label": f"雪球热度上榜 {len(hot_rank)} 次"}

    # 18 · 杀猪盘 (stub → safe by default, 9 分)
    out["18_trap"] = {"score": 9, "weight": 5, "label": "🟢 未发现推广痕迹"}

    # 19 · 实盘赛
    contests = _get("19_contests")
    summary = contests.get("summary") or {}
    xq_total = summary.get("xueqiu_cubes_total", 0)
    hi = summary.get("high_return_cubes", 0)
    score_19 = 5 + min(3, xq_total // 5) + min(2, hi)
    score_19 = min(10, score_19)
    out["19_contests"] = {"score": score_19, "weight": 4,
                           "label": f"雪球 {xq_total} 个组合持有 · {hi} 个收益 >50%",
                           "reasons_pass": [f"{xq_total} 个雪球组合持有"] if xq_total else []}

    # Overall fundamental score
    total_weighted = sum(v["score"] * v["weight"] for v in out.values())
    total_weight = sum(v["weight"] for v in out.values())
    fundamental = (total_weighted / total_weight * 10) if total_weight else 0

    return {"ticker": raw["ticker"], "fundamental_score": round(fundamental, 1), "dimensions": out}


# ─────────── PANEL GENERATION (rule-based) ───────────

GROUP_VERDICTS = {
    "bullish":  ["强烈买入", "买入", "关注"],
    "bearish":  ["观望", "回避", "等待"],
    "neutral":  ["观望", "不适合", "不达标"],
}

COMMENT_TEMPLATES = {
    "A": {
        "bullish": [
            "ROE 和现金流都看得过去，长期持有没问题。",
            "商业模式清晰，10 年后还能赚钱的那种。",
            "安全边际尚可，不急着全仓。",
        ],
        "bearish": [
            "估值已透支未来几年的增长，等回调。",
            "护城河在侵蚀，这种价格不该买。",
            "现金流质量存疑，再观察两个季度。",
        ],
        "neutral": ["看不太懂，先放观察池。", "不在能力圈内。"],
    },
    "B": {
        "bullish": ["PEG 合理且成长性可见，可以进攻。", "CANSLIM 多数条件达标。"],
        "bearish": ["估值已脱离 PEG 合理区间。", "机构持股过高，不符合 CANSLIM S 项。"],
        "neutral": ["增长故事需要更多验证。"],
    },
    "C": {
        "bullish": ["宏观环境对这只票的反身性有利。", "流动性拐点已到，可以下注。"],
        "bearish": ["反身性正反馈进入晚期，小心。"],
        "neutral": ["宏观判断暂时不明。"],
    },
    "D": {
        "bullish": ["Stage 2 + 量能配合，技术面允许进场。", "VCP 形态已成，止损位清晰。"],
        "bearish": ["距 52 周高点太近，不是入场点。"],
        "neutral": ["等待明确突破。"],
    },
    "E": {
        "bullish": ["生意对、人对、价格还凑合。", "ROE 持续性强，可以重仓。"],
        "bearish": ["价格对不起生意质量。"],
        "neutral": ["看不懂就不要碰。"],
    },
    "F": {
        "bullish": ["板块有格局，趋势向上可以跟。", "二板定龙头，题材在线。", "情绪合力在，短线机会。"],
        "bearish": ["市值不在我的射程里。", "题材已过热，这不是我的菜。"],
        "neutral": ["不在风格里，不适合。"],
    },
    "G": {
        "bullish": ["多因子评分 top 20%，值得下注。", "凯利公式给出正仓位。"],
        "bearish": ["统计上已进入均值回归区。"],
        "neutral": ["因子中性，模型无信号。"],
    },
}


def generate_panel(dims_scored: dict, raw: dict) -> dict:
    """Rule-engine-based panel — each investor's verdict cites specific
    criteria from investor_criteria.py that were hit or missed.
    """
    # Build the flat feature dict once for all 51 investors
    features = extract_features(raw, raw.get("dimensions", {}))

    basic_ctx = (raw.get("dimensions", {}).get("0_basic") or {}).get("data") or {}
    kline_ctx = (raw.get("dimensions", {}).get("2_kline") or {}).get("data") or {}
    fin_ctx = (raw.get("dimensions", {}).get("1_financials") or {}).get("data") or {}

    investors_out = []
    vote_dist = {"strongly_buy": 0, "buy": 0, "watch": 0, "wait": 0, "avoid": 0, "n_a": 0, "skip": 0}
    sig_dist = {"bullish": 0, "neutral": 0, "bearish": 0, "skip": 0}

    def _score_to_verdict(score: float, signal: str) -> str:
        if signal == "bullish" and score >= 80:
            return "强烈买入"
        if signal == "bullish":
            return "买入"
        if signal == "bearish" and score <= 20:
            return "回避"
        if signal == "bearish":
            return "观望"
        # neutral
        return "关注" if score >= 50 else "观望"

    for inv in INVESTORS:
        inv_id = inv["id"]
        verdict_obj = _evaluate_investor(inv_id, features)

        sig = verdict_obj["signal"]
        score = int(max(0, verdict_obj["score"]))
        confidence = int(verdict_obj["confidence"])

        # Handle "skip" — investor won't look at this market
        if sig == "skip":
            verdict = "不适合"
            score = 0
            confidence = 0
            skip_reason = verdict_obj.get("skip_reason", "不在能力圈")
            headline = f"不适合 — {skip_reason}"
            comment = f"不在能力圈范围内，不做评价。\n{headline}"
            reasoning = verdict_obj.get("rationale", "")
        else:
            verdict = _score_to_verdict(score, sig)

            # Persona voice layer
            ctx = {
                "name": basic_ctx.get("name", "这只票"),
                "industry": basic_ctx.get("industry", "该行业"),
                "price": basic_ctx.get("price", "—"),
                "pe": basic_ctx.get("pe_ttm", "—"),
                "roe": str((fin_ctx.get("roe_history") or ["—"])[-1]),
                "stage": kline_ctx.get("stage", "—"),
                "growth": fin_ctx.get("revenue_growth", "—"),
            }
            persona_line = _persona_comment(inv_id, sig, ctx)

            headline = verdict_obj["headline"]
            comment = f"{persona_line}\n{headline}"
            reasoning = verdict_obj["rationale"]

        v_key = {"强烈买入": "strongly_buy", "买入": "buy", "关注": "watch",
                 "观望": "wait", "回避": "avoid", "不适合": "skip"}.get(verdict, "n_a")
        vote_dist[v_key] = vote_dist.get(v_key, 0) + 1
        sig_dist[sig] = sig_dist.get(sig, 0) + 1

        investors_out.append({
            "investor_id": inv_id,
            "name": inv["name"],
            "group": inv["group"],
            "avatar": f"avatars/{inv_id}.svg",
            "signal": sig,
            "confidence": confidence,
            "score": score,
            "verdict": verdict,
            "reasoning": reasoning,
            "comment": comment,
            "headline": headline,
            "pass": [{"name": r["name"], "msg": r["msg"], "weight": r["weight"]}
                     for r in verdict_obj["pass_rules"][:4]],
            "fail": [{"name": r["name"], "msg": r["msg"], "weight": r["weight"]}
                     for r in verdict_obj["fail_rules"][:4]],
            "weight_pass": verdict_obj["weight_pass"],
            "weight_total": verdict_obj["weight_total"],
            "ideal_price": None,
            "period": "中长线" if inv["group"] in ("A", "B", "E") else "短线",
            # v2.8 · 因地制宜：每个评委用自己方法论回答这 3 个问题
            "time_horizon": verdict_obj.get("time_horizon", "—"),
            "position_sizing": verdict_obj.get("position_sizing", "—"),
            "what_would_change_my_mind": verdict_obj.get("what_would_change_my_mind", "—"),
        })

    # v2.15.5 · 混合 consensus 公式（连续分 + 离散票）
    # 动机：v2.11 单一公式 `(bullish + 0.6*neutral)/active*100` 只看 signal 计数 ·
    # 把连续 score 压成 3 分类 · 导致 331 个打分中 bullish:neutral:bearish=9.9:13:18.5 ·
    # 多数股 consensus 聚集 40-55 区间分不开.
    # 实测：单 investor score stdev=30.3 信息很丰富 · 但 consensus stdev 只有 28.2 还聚集 ·
    # 说明 signal 分类丢失了"程度"信息（55 和 40 都算 neutral 但态度不同）.
    #
    # 新公式：consensus = 0.65 * score_mean + 0.35 * vote_weighted
    #   - score_mean:  active 成员 score 均值（连续 0-100 · 反映强度）
    #   - vote_weighted: 原 (bullish + 0.6*neutral)/active*100（保留投票机制）
    # 学派级 school_scores 同样用混合公式 · 让各流派分数拉开.
    # 回归风险：v2.11 下 65 分 = "可以蹲一蹲" · 新公式下因 score_mean 参与，
    # 历史白马可能从 40+ 涨到 55+ · 属校准而非 bug · overall 阈值不变.
    NEUTRAL_WEIGHT = 0.6
    SCORE_WEIGHT = 0.65   # score 均值权重（连续分 · 区分度）
    VOTE_WEIGHT  = 0.35   # vote 比例权重（离散投票 · 稳定性）
    POLARIZE_K = 1.30     # 极化系数 · >1 让两端拉开 · 50 为中心
    active_count = len(investors_out) - sig_dist.get("skip", 0)
    bullish = sig_dist.get("bullish", 0)
    neutral = sig_dist.get("neutral", 0)

    def _polarize(c: float, k: float = POLARIZE_K) -> float:
        """极化拉伸 · 50 为中心 · 距离 * k · 裁剪到 [0, 100].

        目的：rule-engine 评分先天居中（大多股 35-65 区间）· 聚合后 consensus
        更居中 · 用户反馈"大多数分在一个区间徘徊"· 极化让强势 70→86 · 弱势 22→14.
        保留 50 为"及格线"不动 · 只放大距离.
        """
        return max(0.0, min(100.0, 50.0 + (c - 50.0) * k))

    # 分量 1 · score 均值（active only · skip 不计）
    active_scores = [m["score"] for m in investors_out if m.get("signal") != "skip"]
    score_mean = (sum(active_scores) / len(active_scores)) if active_scores else 50.0
    # 分量 2 · vote 比例（原 v2.11 公式）
    vote_weighted = (bullish + NEUTRAL_WEIGHT * neutral) / max(active_count, 1) * 100
    consensus_raw = SCORE_WEIGHT * score_mean + VOTE_WEIGHT * vote_weighted
    consensus = _polarize(consensus_raw)

    # v2.15.4+ · 按流派打分（v2.15.5 同步升级为混合公式）
    # 譬如白马消费股：价值派 85 分（重仓），技术派 30 分（趋势破位）·
    # 现在可以一眼看出"不同哲学得出的结论有多不同"
    GROUP_META = {
        "A": {"label": "经典价值派", "desc": "巴菲特 / 格雷厄姆 / 费雪 / 芒格 一脉"},
        "B": {"label": "成长派",     "desc": "彼得·林奇 / 欧奈尔 / 蒂尔 / 伍德 一脉"},
        "C": {"label": "宏观派",     "desc": "索罗斯 / 达利欧 / 马克斯 一脉"},
        "D": {"label": "技术派",     "desc": "利弗莫尔 / Minervini / 达瓦斯 一脉"},
        "E": {"label": "中式价投",   "desc": "段永平 / 张坤 / 朱少醒 / 冯柳 一脉"},
        "F": {"label": "A 股游资",   "desc": "龙虎榜顶流 23 位·章盟主/孙哥/赵老哥为代表"},
        "G": {"label": "量化派",     "desc": "Simons / Thorp / Shaw 一脉"},
        "H": {"label": "科技领袖派", "desc": "黄仁勋 / 马斯克 / Altman / Saylor 一脉"},
        "I": {"label": "AI 卡位/瓶颈猎手", "desc": "Serenity · AI 供应链卡脖子/瓶颈点"},
    }

    def _consensus_to_verdict(c: float) -> str:
        """流派级 verdict · 阈值与综合分保持一致（80/65/50/35）."""
        if c >= 80: return "重仓"
        if c >= 65: return "买入"
        if c >= 50: return "关注"
        if c >= 35: return "谨慎"
        return "回避"

    by_group: dict[str, list[dict]] = {}
    for inv in investors_out:
        by_group.setdefault(inv.get("group", "?"), []).append(inv)

    school_scores: dict[str, dict] = {}
    for g in sorted(by_group.keys()):
        members = by_group[g]
        n_members = len(members)
        active_m = [m for m in members if m.get("signal") != "skip"]
        n_active = len(active_m)
        g_bull = sum(1 for m in members if m.get("signal") == "bullish")
        g_neu  = sum(1 for m in members if m.get("signal") == "neutral")
        g_bear = sum(1 for m in members if m.get("signal") == "bearish")
        g_skip = sum(1 for m in members if m.get("signal") == "skip")

        # v2.15.5 · 流派级混合公式（与总盘保持一致 · 同样极化）
        if n_active > 0:
            s_score_mean = sum(m.get("score", 0) for m in active_m) / n_active
            s_vote = (g_bull + NEUTRAL_WEIGHT * g_neu) / n_active * 100
            s_raw = SCORE_WEIGHT * s_score_mean + VOTE_WEIGHT * s_vote
            s_consensus = _polarize(s_raw)
        else:
            s_score_mean = 0.0
            s_vote = 0.0
            s_consensus = 0.0

        # 主流信号
        sig_counts = [("bullish", g_bull), ("neutral", g_neu), ("bearish", g_bear)]
        dominant = max(sig_counts, key=lambda x: x[1])[0] if n_active > 0 else "skip"

        meta = GROUP_META.get(g, {"label": g, "desc": ""})
        school_scores[g] = {
            "group": g,
            "label": meta["label"],
            "desc": meta["desc"],
            "n_members": n_members,
            "n_active": n_active,
            "consensus": round(s_consensus, 1),
            "avg_score": round(s_score_mean, 1),  # alias · 兼容 v2.15.4 字段
            "vote_consensus": round(s_vote, 1),   # v2.15.5 · vote 分量（可视化展开用）
            "score_mean": round(s_score_mean, 1), # v2.15.5 · score 分量 · 明确语义
            "verdict": _consensus_to_verdict(s_consensus) if n_active > 0 else "不适合",
            "bullish": g_bull,
            "neutral": g_neu,
            "bearish": g_bear,
            "skip": g_skip,
            "dominant_signal": dominant,
        }

    return {
        "ticker": raw["ticker"],
        "panel_consensus": round(consensus, 1),
        "vote_distribution": vote_dist,
        "signal_distribution": sig_dist,
        "investors": investors_out,
        # v2.15.4 · 按流派分数 · 7 个 school 各自 consensus/avg_score/verdict
        "school_scores": school_scores,
        # v2.15.5 · 诊断字段 · 混合公式各分量 + 极化前后值
        "consensus_formula": {
            "version": "v2.15.5 · polarize(0.65*score_mean + 0.35*vote_weighted, k=1.3)",
            "score_weight": SCORE_WEIGHT,
            "vote_weight": VOTE_WEIGHT,
            "neutral_weight": NEUTRAL_WEIGHT,
            "polarize_k": POLARIZE_K,
            "score_mean": round(score_mean, 2),
            "vote_weighted": round(vote_weighted, 2),
            "consensus_raw": round(consensus_raw, 2),     # 极化前
            "consensus_final": round(consensus, 2),        # 极化后（= panel_consensus）
            "bullish": bullish,
            "neutral_weighted": round(neutral * NEUTRAL_WEIGHT, 2),
            "bearish": sig_dist.get("bearish", 0),
            "skip": sig_dist.get("skip", 0),
            "active": active_count,
        },
    }


# ─────────────────────────────────────────────────────────────
# v2.6.1 · 自动综合各维度 raw_data 字段为可读 commentary
# 替代旧版 "[脚本占位]" 废话；让直跑模式（无 agent）也能产出有信息量的报告
# Agent 介入时仍可覆盖（agent_analysis.dim_commentary 优先级最高）
# ─────────────────────────────────────────────────────────────
def _auto_summarize_dim(dim_key: str, label: str, dim: dict, score: float) -> str:
    """Build a one-paragraph commentary from raw_data fields. NEVER returns
    "[占位]" type strings — either real content or empty."""
    if not isinstance(dim, dict):
        return ""
    data = dim.get("data") or {}
    if not data:
        return f"{label}：未拉取到数据（fetcher 失败或返回空）。"

    def _v(*keys, default="—"):
        for k in keys:
            v = data.get(k)
            if v not in (None, "", "—", "-", [], {}):
                return v
        return default

    def _join_list(lst, max_n=3, sep="；"):
        if not isinstance(lst, list) or not lst:
            return None
        out = []
        for x in lst[:max_n]:
            if isinstance(x, dict):
                t = x.get("title") or x.get("name") or x.get("date") or str(x)
                out.append(str(t)[:50])
            else:
                out.append(str(x)[:50])
        return sep.join(out)

    # ─── Per-dim auto summarizer ───
    if dim_key == "0_basic":
        return f"{label}：{_v('name')}（{_v('code')}），{_v('industry')} 行业。市值 {_v('market_cap')}，PE {_v('pe_ttm')}，PB {_v('pb')}。"

    if dim_key == "1_financials":
        roe = _v("roe_latest", "roe")
        rev_g = _v("revenue_growth_yoy", "revenue_yoy")
        np_g = _v("net_profit_yoy")
        margin = _v("net_margin", "gross_margin")
        return f"{label}：ROE {roe}，营收同比 {rev_g}，净利同比 {np_g}，净利率 {margin}。综合得分 {score}/10。"

    if dim_key == "2_kline":
        stage = _v("stage", "wyckoff_stage")
        ma = _v("ma_align", "trend")
        macd = _v("macd")
        return f"{label}：{stage} · 均线 {ma} · MACD {macd}。"

    if dim_key == "3_macro":
        return (f"{label}：利率周期 {_v('rate_cycle')}；汇率 {_v('fx_trend')}；"
                f"地缘 {_v('geo_risk')}；大宗商品 {_v('commodity', 'commodity_trend')}。"
                f"得分 {score}/10。")

    if dim_key == "4_peers":
        rank = _v("rank")
        peer_table = data.get("peer_table") or []
        ind = _v("industry")
        peers_str = _join_list([p.get("name") for p in peer_table if isinstance(p, dict) and not p.get("is_self")][:5], max_n=5, sep="、")
        return f"{label}：{ind} 行业，{rank}{('，主要同行：' + peers_str) if peers_str else ''}。得分 {score}/10。"

    if dim_key == "5_chain":
        return f"{label}：上游 {_v('upstream')}；下游 {_v('downstream')}；客户集中度 {_v('client_concentration')}。"

    if dim_key == "6_research":
        rep_count = _v("report_count", "n_reports")
        target = _v("avg_target_price", "target_price")
        rating = _v("consensus_rating", "rating")
        return f"{label}：近期券商研报 {rep_count} 篇，一致评级 {rating}，目标价均值 {target}。"

    if dim_key == "7_industry":
        ind_pe = _v("industry_pe_weighted") or (data.get("cninfo_metrics") or {}).get("industry_pe_weighted")
        ind_count = _v("total_companies") or (data.get("cninfo_metrics") or {}).get("company_count")
        growth = _v("growth")
        return f"{label}：所属 {_v('industry')} · 行业 PE 加权 {ind_pe} · 上市公司数 {ind_count} · 增速 {growth}。"

    if dim_key == "8_materials":
        core = _v("core_material")
        trend = _v("price_trend")
        cost = _v("cost_share")
        return f"{label}：核心原料 {core}；近期价格走势 {trend}；占成本比例 {cost}。"

    if dim_key == "9_futures":
        contract = _v("linked_contract")
        ftrend = _v("contract_trend")
        return f"{label}：关联合约 {contract}；近期走势 {ftrend}；{_v('note', default='')}。"

    if dim_key == "10_valuation":
        pe_q = _v("pe_quantile_5y", "pe_quantile")
        pb_q = _v("pb_quantile_5y", "pb_quantile")
        return f"{label}：PE 5 年分位 {pe_q}，PB 5 年分位 {pb_q}。得分 {score}/10。"

    if dim_key == "11_governance":
        ctrl = _v("actual_controller")
        recent = _v("recent_changes", "recent_holdings_change")
        return f"{label}：实控人 {ctrl}；近期变动 {recent}。"

    if dim_key == "12_capital_flow":
        north = _v("north_holding_pct", "north_change_5d", default=None)
        margin = _v("margin_balance", default=None)
        if north or margin:
            return f"{label}：北向持股 {north or '—'}；融资余额 {margin or '—'}。"
        return f"{label}：{_v('_note', default='资金面数据有限')}。"

    if dim_key == "13_policy":
        snippets = data.get("snippets") or {}
        non_empty = {k: v for k, v in snippets.items() if v}
        if non_empty:
            preview = "；".join(f"{k}: {len(v) if isinstance(v, list) else 1} 条" for k, v in non_empty.items())
            return f"{label}：{_v('industry', default='本行业')} {_v('year', default='')} 年政策检索：{preview}。"
        return f"{label}：{_v('industry', default='本行业')} 政策搜索未命中具体内容（建议 web_search 补抓）。"

    if dim_key == "14_moat":
        scores = data.get("scores") or {}
        total = sum(scores.values()) if scores else None
        if total is not None:
            return f"{label}：四力评分 无形资产 {scores.get('intangible')}/10、转换成本 {scores.get('switching')}/10、网络效应 {scores.get('network')}/10、规模 {scores.get('scale')}/10 · 综合 {total}/40。"
        return f"{label}：评估数据有限，得分 {score}/10。"

    if dim_key == "15_events":
        timeline = data.get("event_timeline") or []
        recent_news = data.get("recent_news") or []
        if timeline:
            head = "；".join([str(t)[:60] for t in timeline[:3]])
            return f"{label}：近期事件 {len(timeline)} 条，含：{head}。"
        if recent_news:
            head = "；".join([(n.get("title") or "")[:60] for n in recent_news[:3]])
            return f"{label}：近期新闻 {len(recent_news)} 条，含：{head}。"
        return f"{label}：暂无显著事件（fetcher 返回空）。"

    if dim_key == "16_lhb":
        n = _v("recent_lhb_count", "n_lhb_30d", default=None)
        seats = data.get("recent_seats") or data.get("top_seats") or []
        if n or seats:
            seat_str = "、".join([s.get("name", "") for s in seats[:3] if isinstance(s, dict)]) if seats else ""
            return f"{label}：近 30 天上榜 {n or '—'} 次{('，主要席位：' + seat_str) if seat_str else ''}。"
        return f"{label}：近期未上龙虎榜或非 A 股。"

    if dim_key == "17_sentiment":
        hot = _v("hot_rank", "hot_score")
        senti = _v("sentiment_label", "sentiment")
        return f"{label}：热度 {hot}；情绪 {senti}。"

    if dim_key == "18_trap":
        # v2.7.1: 字段名其实是 signals_hit_count（不是 hit_signals_count），修；显示 8 信号扫描结果
        level = _v("trap_level", "level")
        n_signals = data.get("signals_hit_count", data.get("hit_signals_count", 0))
        scanned = data.get("signals_hit", "?/8")
        rec = _v("recommendation")
        detail = data.get("signals_hit_detail") or []
        if detail:
            kws = [s.get("name", "") for s in detail[:3]]
            return f"{label}：{level} · 8 信号扫描命中 {scanned}（{('、'.join(kws))}）· 建议：{rec}"
        return f"{label}：{level} · 8 信号扫描命中 {scanned}（已扫 ddgs 24 条搜索结果）· 建议：{rec}"

    if dim_key == "19_contests":
        # v2.7.1: 字段名是 summary.xueqiu_cubes_total，不是 contests_count；要看 login_required
        summary = data.get("summary") or {}
        n_cubes = summary.get("xueqiu_cubes_total", 0)
        n_high = summary.get("high_return_cubes", 0)
        login_req = summary.get("xueqiu_login_required", False)
        src = summary.get("xueqiu_source", "http")
        if login_req and n_cubes == 0:
            return (f"{label}：⚠️ XueQiu cubes 接口需登录（2026 起新政），未启用 → 0 cube。"
                    f"启用方式：export UZI_XQ_LOGIN=1 + python -m lib.xueqiu_browser login")
        if n_cubes:
            return f"{label}：雪球 {n_cubes} 个组合持有本股（高收益 >50% 的有 {n_high} 个）· 来源 {src}"
        return f"{label}：雪球 0 个组合持有本股（可能小盘 / 冷门 / 接口未返）"

    # Default: just enumerate top fields
    items = []
    for k, v in list(data.items())[:5]:
        if v not in (None, "", "—", "-", [], {}) and not str(k).startswith("_"):
            items.append(f"{k}={str(v)[:30]}")
    return f"{label}：{'、'.join(items) if items else '无数据'}。" if items else ""


# v2.12.1 · MX/ddgs 返回垃圾数据的黑名单
# v2.13.0 · 抽到 lib/junk_filter.py 共用（Playwright 兜底也用）· 此处保留 BC delegate
try:
    from lib.junk_filter import JUNK_PATTERNS as _AUTOFILL_JUNK_PATTERNS, is_junk_autofill_text as _is_junk_autofill
except ImportError:
    # 兜底：旧环境直接内联定义（防止模块导入失败时整个文件崩）
    _AUTOFILL_JUNK_PATTERNS = (
        "类型；类型", "XXX", "TODO", "null", "undefined", "None",
        "抱歉，", "无法回答", "我不知道", "不清楚", "暂无数据",
        "（示例）", "（待补）",
    )
    def _is_junk_autofill(text):
        if not text: return True
        t = str(text).strip()
        if len(t) < 5: return True
        if any(j in t for j in _AUTOFILL_JUNK_PATTERNS): return True
        parts = [p.strip() for p in t.split("；") if p.strip()]
        return len(parts) >= 2 and len(set(parts)) == 1


def _autofill_qualitative_via_mx(raw: dict, ticker: str) -> None:
    """v2.6.1 · 自动补齐 6 个定性维度的空字段（in-place 修改 raw['dimensions']）.

    优先级：MX 妙想 API → ddgs WebSearch → 显式标记 autofill_failed。
    适用场景：直跑模式（无 agent 介入），fetcher 拿到空数据时不能让报告也空。

    v2.12.1 加入 _is_junk_autofill 质量过滤 · 垃圾数据（"类型；类型" 等）不写入字段.
    """
    try:
        from lib.mx_api import MXClient
    except ImportError:
        MXClient = None
    try:
        from lib.web_search import search as _ws_search
    except ImportError:
        _ws_search = None

    client = MXClient() if MXClient else None
    mx_ok = client is not None and client.available
    if not mx_ok and not _ws_search:
        print("   ⚠️ MX_APIKEY 未设置且 ddgs 不可用，跳过自动兜底")
        return

    dims = raw.get("dimensions", {})
    basic = (dims.get("0_basic") or {}).get("data") or {}
    name = basic.get("name") or ticker
    industry = basic.get("industry") or "综合"
    code_raw = ticker.split(".")[0] if "." in ticker else ticker

    def _is_default_or_empty(v) -> bool:
        """True if value is missing OR a generic-default placeholder."""
        if v in (None, "", "—", "-", [], {}, "n/a", "N/A"):
            return True
        s = str(v)
        # 这些都是 fetcher 的默认 fallback 字符串，没真实信息量
        if any(kw in s for kw in ["中性（", "中性(", "未拉取", "未命中", "无直接关联"]):
            return True
        return False

    # 6 个定性维度的"空判定" + MX query 模板（v2.6.1 加严：默认值也算空）
    targets = [
        ("3_macro",     lambda d: all(_is_default_or_empty(d.get(k)) for k in ("rate_cycle","fx_trend","geo_risk","commodity")),
                        lambda: f"{industry} 2026 宏观环境 利率周期 汇率 大宗商品 行业影响"),
        ("7_industry",  lambda d: _is_default_or_empty(d.get("growth")) and not (d.get("cninfo_metrics") or {}).get("industry_pe_weighted"),
                        lambda: f"{industry} 2026 行业增速 TAM 市场规模 渗透率"),
        ("8_materials", lambda d: _is_default_or_empty(d.get("core_material")),
                        lambda: f"{name} {code_raw} 主营业务 主要原材料 成本构成"),
        ("9_futures",   lambda d: _is_default_or_empty(d.get("linked_contract")) or "无直接" in str(d.get("linked_contract","")),
                        lambda: f"{industry} 行业 上下游 期货品种 套保 大宗"),
        ("13_policy",   lambda d: not any((d.get("snippets") or {}).get(k) for k in ("policy_dir","subsidy","monitoring","anti_trust")),
                        lambda: f"{industry} 2026 国家政策 监管动态 补贴 税收 影响"),
        ("15_events",   lambda d: not d.get("event_timeline") and not d.get("recent_news") and not d.get("recent_notices"),
                        lambda: f"{name} {code_raw} 最新公告 重大事件 业绩 合同"),
    ]
    fixed_count = 0
    skipped_full = 0
    failed_count = 0
    for dim_key, is_empty_fn, query_fn in targets:
        dim = dims.get(dim_key) or {}
        data = dim.get("data") or {}
        try:
            if not is_empty_fn(data):
                skipped_full += 1
                continue  # 该维度已有真实数据
        except Exception:
            skipped_full += 1
            continue

        query = query_fn()
        text = ""
        source_used = None

        # 优先 MX
        if mx_ok:
            try:
                r = client.query(query)
                text = _extract_mx_text(r)
                # v2.12.1 · 过滤 MX 返回的垃圾数据（"类型；类型"/"抱歉"/重复等）
                if _is_junk_autofill(text):
                    text = ""
                if text:
                    source_used = "mx_api"
            except Exception:
                pass

        # 回退 ddgs WebSearch
        if not text and _ws_search:
            try:
                results = _ws_search(query, max_results=3) or []
                snippets = []
                for r in results[:3]:
                    if isinstance(r, dict):
                        title = (r.get("title") or "").strip()
                        body = (r.get("body") or "").strip()
                        if title or body:
                            snippets.append(f"{title} — {body[:80]}".strip(" —"))
                text = "；".join(snippets)[:300]
                # v2.12.1 · 过滤 ddgs 拼接后的噪音（长度过短 / 模板占位符）
                if _is_junk_autofill(text):
                    text = ""
                if text:
                    source_used = "ddgs"
            except Exception:
                pass

        if text:
            data.setdefault("_autofill", {})
            data["_autofill"]["query"] = query
            data["_autofill"]["snippet"] = text
            data["_autofill"]["source"] = source_used
            # 把内容塞到对应字段，方便 _auto_summarize_dim 摘要
            if dim_key == "3_macro":
                data["rate_cycle"] = (text[:80] + "…") if len(text) > 80 else text
            elif dim_key == "7_industry":
                data["growth"] = (text[:80] + "…") if len(text) > 80 else text
            elif dim_key == "8_materials":
                data["core_material"] = (text[:60] + "…") if len(text) > 60 else text
            elif dim_key == "9_futures":
                data["contract_trend"] = (text[:60] + "…") if len(text) > 60 else text
            elif dim_key == "13_policy":
                snippets = data.setdefault("snippets", {})
                snippets.setdefault("policy_dir", []).append({"title": text[:120], "url": "", "source": source_used})
            elif dim_key == "15_events":
                data["event_timeline"] = [text[:120]]
            dims[dim_key] = {"ticker": ticker, "data": data,
                             "source": (dim.get("source", "") + f"+autofill:{source_used}").lstrip("+"),
                             "fallback": True}
            fixed_count += 1
            print(f"   ✓ {dim_key:14s} via {source_used}: {text[:60]}{'…' if len(text)>60 else ''}")
        else:
            data["_autofill_failed"] = {"query": query, "reason": "MX/ddgs 都没有返回内容"}
            dims[dim_key] = {"ticker": ticker, "data": data,
                             "source": (dim.get("source", "") + "+autofill_failed").lstrip("+"),
                             "fallback": True}
            failed_count += 1
            print(f"   ⚠️ {dim_key:14s} 兜底失败 · agent 应主动 web search 补抓")

    print(f"   合计 · 充足 {skipped_full} · 兜底成功 {fixed_count} · 失败 {failed_count}（共 6 维）")


def _extract_mx_text(result: dict) -> str:
    """Pull most readable text from MX query response.
    First tries dataTableDTOList[].title + entityName; else returns empty."""
    if not isinstance(result, dict) or result.get("error"):
        return ""
    data = result.get("data") or {}
    inner = data.get("data") or {}
    sr = inner.get("searchDataResultDTO") or {}
    dto_list = sr.get("dataTableDTOList") or []
    if not dto_list:
        # Try inner.entityName as last resort
        return str(inner.get("entityName") or "")[:200]
    parts = []
    for dto in dto_list[:2]:
        if not isinstance(dto, dict):
            continue
        title = dto.get("title") or dto.get("entityName") or ""
        if title:
            parts.append(str(title)[:120])
    return "；".join(parts)[:300] if parts else ""


def generate_synthesis(raw: dict, dims_scored: dict, panel: dict, agent_analysis: dict | None = None) -> dict:
    """Generate synthesis — merges agent_analysis.json if provided.

    agent_analysis keys (all optional, agent writes what it has):
      - dim_commentary: {dim_key: "agent's qualitative note"}
      - panel_insights: "agent's panel-level narrative"
      - great_divide_override: {punchline, bull_say_rounds, bear_say_rounds}
      - narrative_override: {core_conclusion, risks, buy_zones}
      - agent_reviewed: True  (marks that agent has intervened)
    """
    from compute_friendly import compute_scenarios, compute_exit_triggers
    ag = agent_analysis or {}

    basic = (raw.get("dimensions", {}).get("0_basic") or {}).get("data") or {}
    name = basic.get("name") or raw.get("ticker")
    price = basic.get("price") or 0

    # v2.7 · 按股票风格动态加权（解决 "几乎一片回避" 的系统性偏差）
    # detect_style 识别：白马/高成长/周期/小盘投机/分红防御/困境反转/量化因子/中性
    # apply_style_weights：评委组级×个体 override 加权 + 22 维 fundamental dim mult
    # neutral 半权计入 consensus（修正旧公式 0% 权重的问题）
    style_label = "balanced"
    style_diag = {}
    fund_score = dims_scored.get("fundamental_score", 60)
    consensus = panel.get("panel_consensus", 50)
    fund_score_old = fund_score
    consensus_old = consensus
    try:
        from lib.stock_style import detect_style, apply_style_weights, STYLE_LABELS, STYLE_EXPLANATIONS
        # Build feature dict for style detection
        bd = basic
        try:
            mcap_yi = float(bd.get("market_cap_raw") or 0) / 1e8 if bd.get("market_cap_raw") else 0
        except (ValueError, TypeError):
            mcap_yi = 0
        # 简化的局部数字转换（避开 generate_synthesis 内 _f 作用域冲突）
        def _ff(v, dflt=0.0):
            try:
                if v is None or v == "":
                    return dflt
                return float(str(v).replace(",", "").replace("%", "").replace("亿", "").replace("+", "").strip())
            except (ValueError, TypeError):
                return dflt
        d_fin = (dims_scored.get("dimensions", {}).get("1_financials") or {})
        feat_for_style = {
            "code": raw.get("ticker", ""),
            "market": raw.get("market", "A"),
            "industry": bd.get("industry", "") or "",
            "market_cap_yi": mcap_yi,
            "pe": _ff(bd.get("pe_ttm")),
            "pe_ttm": _ff(bd.get("pe_ttm")),
            "pb": _ff(bd.get("pb")),
            "roe_5y_avg": _ff(d_fin.get("roe_5y_avg")),
            "roe_5y_min": _ff(d_fin.get("roe_5y_min")),
            "revenue_growth_3y_cagr": _ff(d_fin.get("revenue_growth_3y_cagr")),
            "dividend_yield": _ff(bd.get("dividend_yield_ttm")),
        }
        style_label = detect_style(feat_for_style, raw)
        adj = apply_style_weights(panel.get("investors", []), dims_scored, style_label)
        fund_score = adj["fundamental_score"]
        consensus = adj["panel_consensus"]
        style_diag = adj["diagnostics"]
        print(f"\n  🎯 v2.7 风格识别: {style_label} ({STYLE_LABELS.get(style_label,'?')}) — fund {fund_score_old:.1f}→{fund_score:.1f} · consensus {consensus_old:.1f}→{consensus:.1f}")
    except Exception as _se:
        print(f"  ⚠️ v2.7 风格加权失败（沿用原始公式）: {type(_se).__name__}: {str(_se)[:120]}")

    overall = fund_score * 0.6 + consensus * 0.4

    # v2.11 · verdict 阈值重校准 · 论坛+微信反馈用户心理及格线是 65 分
    # 调整：85/70/55/40 → 80/65/50/35，让白马/真强股进"可以蹲一蹲"档
    # v3.4.1 · 用户反馈"神剑股份(002361 58分) 和博云新材(002297 60分) verdict 都是观望优先 ·
    #         看不出差异"。50-65 这个 15 分跨度太宽 · 拆成 50-55 / 55-60 / 60-65 三档 ·
    #         同时把流派分歧度作为后缀显示让差异更明显.
    if overall >= 80:
        verdict_label = "值得重仓"
    elif overall >= 70:
        verdict_label = "可以蹲一蹲"
    elif overall >= 65:
        verdict_label = "可以蹲（偏弱）"   # v3.4.1 新增细分
    elif overall >= 60:
        verdict_label = "观望偏多"          # v3.4.1 新增细分
    elif overall >= 55:
        verdict_label = "观望中性"          # v3.4.1 新增细分
    elif overall >= 50:
        verdict_label = "观望偏空"          # v3.4.1 新增细分
    elif overall >= 35:
        verdict_label = "谨慎"
    else:
        verdict_label = "回避"

    # v3.4.1 · 追加流派分歧指标 · 让用户能看到"5 派看空 + 2 派看多"这种结构信息
    school_scores = panel.get("school_scores", {})
    if school_scores:
        bullish_schools = [s["label"] for s in school_scores.values()
                          if s.get("verdict") in ("重仓", "买入")]
        bearish_schools = [s["label"] for s in school_scores.values()
                          if s.get("verdict") == "回避"]
        if bullish_schools and bearish_schools:
            verdict_label += f" · {len(bullish_schools)} 派看多 / {len(bearish_schools)} 派看空"
        elif bullish_schools:
            verdict_label += f" · {len(bullish_schools)} 派看多"
        elif bearish_schools:
            verdict_label += f" · {len(bearish_schools)} 派看空"

    # v3.4.1 · 同时记 verdict_detail · 含 fund + consensus 精确分（让相近股票能区分）
    verdict_detail = f"基本面 {fund_score:.1f} · 共识 {consensus:.1f}"

    # Pick bull and bear for great divide
    # CRITICAL: must pick from ACTUALLY bullish/bearish investors, never misattribute
    investors = panel.get("investors", [])

    # v2.6 · 防御性 panel 排序 (fix bug #5: "最看空 27 vs 下面 0 不一致")
    # 非 Claude LLM 可能写出 signal=bullish 但 score=5 这种自相矛盾输出。
    # 旧逻辑按 signal 先分组再选 → 实际可见的最低分(neutral/skip 里 0 分的)反而没被选为 bear。
    # 新逻辑：先排除 skip 和明显异常（score=0 通常是空数据），然后按 score 排序，
    #        bull = 最高分 · bear = 最低分。signal 仅作辅助检查。
    eligible = [
        i for i in investors
        if i.get("signal") != "skip"
        and i.get("score", 0) > 0  # 0 分通常是 fail_msg 幻觉，剔除
    ]
    if not eligible:
        eligible = [i for i in investors if i.get("signal") != "skip"] or investors

    inv_by_score = sorted(eligible, key=lambda x: -x.get("score", 0))
    bull = inv_by_score[0] if inv_by_score else (investors[0] if investors else {})
    bear = inv_by_score[-1] if inv_by_score else (investors[-1] if investors else {})

    # Safety: bull and bear must be different investors
    if bull.get("investor_id") == bear.get("investor_id") and len(inv_by_score) > 1:
        bear = inv_by_score[-2]

    # v2.6 · Sanity warnings: signal vs score 矛盾时打印（不阻断流程）
    def _check_signal_score(inv: dict, role: str) -> None:
        sig = inv.get("signal", "")
        sc = inv.get("score", 50)
        if role == "bull" and sig == "bearish":
            print(f"   ⚠️ Top bull '{inv.get('name')}' signal=bearish but score={sc} → 数据可能错乱")
        if role == "bear" and sig == "bullish":
            print(f"   ⚠️ Bottom bear '{inv.get('name')}' signal=bullish but score={sc} → 数据可能错乱")
    _check_signal_score(bull, "bull")
    _check_signal_score(bear, "bear")

    # Build debate rounds — use actual headline + reasoning from evaluator
    bull_headline = bull.get("headline", bull.get("comment", ""))
    bear_headline = bear.get("headline", bear.get("comment", ""))
    bull_reasoning = bull.get("reasoning", "")
    bear_reasoning = bear.get("reasoning", "")

    bull_pass_rules = bull.get("pass", [])
    bull_fail_rules = bull.get("fail", [])
    bear_pass_rules = bear.get("pass", [])
    bear_fail_rules = bear.get("fail", [])

    # Build debate rounds — agent can override with great_divide_override
    gd_override = ag.get("great_divide_override") or {}
    agent_bull_rounds = gd_override.get("bull_say_rounds") or []
    agent_bear_rounds = gd_override.get("bear_say_rounds") or []

    rounds = [
        {
            "round": 1,
            "bull_say": agent_bull_rounds[0] if len(agent_bull_rounds) > 0 else bull_headline,
            "bear_say": agent_bear_rounds[0] if len(agent_bear_rounds) > 0 else bear_headline,
        },
        {
            "round": 2,
            "bull_say": agent_bull_rounds[1] if len(agent_bull_rounds) > 1 else (" · ".join(r.get("msg", r.get("name", "")) for r in bull_pass_rules[:3]) or "数据支持我的判断。"),
            "bear_say": agent_bear_rounds[1] if len(agent_bear_rounds) > 1 else (" · ".join(r.get("msg", r.get("name", "")) for r in bear_fail_rules[:3]) or "风险点太多。"),
        },
        {
            "round": 3,
            "bull_say": agent_bull_rounds[2] if len(agent_bull_rounds) > 2 else f"综合看，{bull.get('score', 0)} 分，我的立场不变。",
            "bear_say": agent_bear_rounds[2] if len(agent_bear_rounds) > 2 else f"综合看，{bear.get('score', 0)} 分，风险大于收益。",
        },
    ]

    kline = (raw.get("dimensions", {}).get("2_kline") or {}).get("data") or {}
    val = (raw.get("dimensions", {}).get("10_valuation") or {}).get("data") or {}

    # v2.0 · Pull institutional modeling summaries
    d20 = (raw.get("dimensions", {}).get("20_valuation_models") or {}).get("data") or {}
    d21 = (raw.get("dimensions", {}).get("21_research_workflow") or {}).get("data") or {}
    d22 = (raw.get("dimensions", {}).get("22_deep_methods") or {}).get("data") or {}
    dcf_summary = d20.get("summary") or {}
    init_cov = d21.get("initiating_coverage") or {}
    ic_memo = d22.get("ic_memo") or {}
    competitive = d22.get("competitive_analysis") or {}

    # Build punchline with conflict — prefer real conflicts over platitudes
    dcf_sm = dcf_summary.get("dcf_safety_margin_pct", 0) or 0
    lbo_irr = dcf_summary.get("lbo_irr_pct", 0) or 0
    tp = (init_cov.get("headline") or {}).get("target_price") or 0
    upside = (init_cov.get("headline") or {}).get("upside_pct", 0) or 0
    rating = (init_cov.get("headline") or {}).get("rating", "")

    # Punchline: prefer agent override, fallback to script generation
    agent_punchline = gd_override.get("punchline") or ""
    if agent_punchline:
        punchline = agent_punchline
    elif dcf_sm and lbo_irr and abs(dcf_sm) > 10 and lbo_irr > 15:
        if dcf_sm < 0 and lbo_irr > 20:
            punchline = f"DCF 说高估 {abs(dcf_sm):.0f}%，但 LBO 测试显示 PE 买方仍能赚 {lbo_irr:.0f}% IRR — 冲突很有意思。"
        elif dcf_sm > 15 and lbo_irr > 20:
            punchline = f"DCF 认为低估 {dcf_sm:.0f}%，LBO IRR {lbo_irr:.0f}% 也确认 — 双重信号看多。"
        else:
            punchline = f"机构建模定调 {rating}，目标价 ¥{tp}（{upside:+.0f}%），LBO 视角 IRR {lbo_irr:.0f}%。"
    elif tp > 0 and abs(upside) > 5:
        punchline = f"首次覆盖 {rating}，目标价 ¥{tp}，空间 {upside:+.0f}%。"
    else:
        punchline = f"{name} · ROE 历史与当前估值存在结构性分歧，等待方向明朗。"

    # Risks: prefer agent-written, fallback to script generation from low-scoring dims
    narrative_override = ag.get("narrative_override") or {}
    agent_risks = narrative_override.get("risks") or []
    risks = list(agent_risks) if agent_risks else []
    if not risks:
        for key, dim in dims_scored["dimensions"].items():
            if dim["score"] <= 4:
                reasons = dim.get("reasons_fail", [])
                if reasons:
                    risks.extend(reasons[:1])
                else:
                    # Use dim name as fallback
                    dim_name = dim.get("name") or dim.get("label") or key
                    risks.append(f"{dim_name} 评分偏低 ({dim['score']}/10)")

    # If still empty, generate dynamic risks from actual data instead of hardcoded ones
    if not risks:
        pe_val = features.get("pe", 0) if "features" in dir() else 0
        debt_val = features.get("debt_ratio", 0) if "features" in dir() else 0
        # Use features from extract_features if available
        try:
            _f = extract_features(raw, raw.get("dimensions", {}))
            pe_val = _f.get("pe", 0)
            debt_val = _f.get("debt_ratio", 0)
            roe_min = _f.get("roe_5y_min", 0)
            industry = _f.get("industry", "所属行业")
        except Exception:
            pe_val, debt_val, roe_min, industry = 0, 0, 0, "所属行业"

        if pe_val > 30:
            risks.append(f"当前 PE {pe_val:.0f}x，估值偏高")
        if debt_val > 50:
            risks.append(f"资产负债率 {debt_val:.0f}%，财务杠杆偏高")
        if roe_min < 5:
            risks.append(f"ROE 最低 {roe_min:.1f}%，盈利稳定性不足")
        risks.append(f"{industry}行业竞争加剧风险")
        risks.append("宏观经济或政策环境变化")

    risks = risks[:5]

    # Friendly layer
    scenarios = compute_scenarios(raw, dims_scored)
    exit_triggers = compute_exit_triggers(raw, dims_scored, {})
    similar_stocks = raw.get("similar_stocks", [])

    # Dashboard — core_conclusion: agent override > script
    ytd_return = (kline.get("kline_stats") or {}).get("ytd_return", "—")
    agent_core_conclusion = narrative_override.get("core_conclusion") or ""
    core_conclusion = agent_core_conclusion or f"{name} · {int(overall)} 分 · {verdict_label}。51 位大佬里 {panel['signal_distribution']['bullish']} 人看多，YTD {ytd_return}。{punchline}"

    # v2.2 · dim_commentary: prefer agent-written, fallback to AUTO-SUMMARY (v2.6.1)
    # 关键修复：原 fallback 只生成 "[脚本占位]" 字符串，导致直跑模式下报告里
    # 5/6 定性维度是 missing/占位文字。新版直接把 raw_data 字段综合成实际中文。
    agent_dim_commentary = ag.get("dim_commentary") or {}
    dim_commentary_final: dict[str, str] = {}
    dim_labels = {
        "0_basic": "基础信息",
        "1_financials": "财报",
        "2_kline": "K线技术面",
        "3_macro": "宏观环境",
        "4_peers": "同行对比",
        "5_chain": "产业链",
        "6_research": "券商研报",
        "7_industry": "行业景气",
        "8_materials": "原材料",
        "9_futures": "期货关联",
        "10_valuation": "估值分位",
        "11_governance": "治理/减持",
        "12_capital_flow": "资金面",
        "13_policy": "政策与监管",
        "14_moat": "护城河",
        "15_events": "事件驱动",
        "16_lhb": "龙虎榜",
        "17_sentiment": "舆情",
        "18_trap": "杀猪盘",
        "19_contests": "实盘比赛",
    }
    for dim_key, label in dim_labels.items():
        # Agent-written commentary takes priority
        if dim_key in agent_dim_commentary and agent_dim_commentary[dim_key]:
            dim_commentary_final[dim_key] = agent_dim_commentary[dim_key]
        else:
            dim = (raw.get("dimensions", {}).get(dim_key) or {})
            score_info = dims_scored.get("dimensions", {}).get(dim_key) or {}
            score = score_info.get("score", 0)
            auto = _auto_summarize_dim(dim_key, label, dim, score)
            if auto:
                dim_commentary_final[dim_key] = auto

    # v3.5.0 · 读 UZI_SCHOOL env · 把 lock 编码进 synthesis 让报告层渲染 banner
    try:
        from lib.investor_evaluator import get_locked_school, SCHOOL_LABELS
        _locked = get_locked_school()
        school_lock = {"group": _locked, "label": SCHOOL_LABELS.get(_locked, "")} if _locked else None
    except Exception:
        school_lock = None

    return {
        "ticker": raw["ticker"],
        "name": name,
        "overall_score": round(overall, 1),
        "verdict_label": verdict_label,
        "verdict_detail": verdict_detail,  # v3.4.1 · 基本面/共识精确分 · 区分相近 verdict 段的票
        "fundamental_score": round(fund_score, 1),
        "panel_consensus": round(consensus, 1),
        # v3.5.0 · 用户锁定单一流派视角时 · 告诉报告层渲染 banner
        "school_lock": school_lock,
        # v2.15.4 · 按流派分数也带到 synthesis · 让报告层无须回拉 panel.json
        "school_scores": panel.get("school_scores", {}),
        "dim_commentary": dim_commentary_final,  # agent-written > stub
        "institutional_modeling": {
            "dcf_intrinsic": dcf_summary.get("dcf_intrinsic"),
            "dcf_safety_margin_pct": dcf_summary.get("dcf_safety_margin_pct"),
            "dcf_verdict": dcf_summary.get("dcf_verdict"),
            "lbo_irr_pct": dcf_summary.get("lbo_irr_pct"),
            "lbo_verdict": dcf_summary.get("lbo_verdict"),
            "comps_verdict": dcf_summary.get("comps_verdict"),
            "initiating_rating": (init_cov.get("headline") or {}).get("rating"),
            "target_price": (init_cov.get("headline") or {}).get("target_price"),
            "upside_pct": (init_cov.get("headline") or {}).get("upside_pct"),
            "ic_recommendation": (ic_memo.get("sections", {}).get("I_exec_summary", {}) or {}).get("headline"),
            "bcg_position": (competitive.get("bcg_position") or {}).get("category"),
            "industry_attractiveness": competitive.get("industry_attractiveness_pct"),
        },
        # v2.7 · 风格识别 + 加权诊断（让 HTML 报告显示 + agent 可在 agent_analysis.json 覆盖 style）
        "detected_style": style_label,
        "style_label_cn": (lambda: __import__("lib.stock_style", fromlist=["STYLE_LABELS"]).STYLE_LABELS.get(style_label, "?"))() if style_label else "?",
        "style_explanation": (lambda: __import__("lib.stock_style", fromlist=["STYLE_EXPLANATIONS"]).STYLE_EXPLANATIONS.get(style_label, ""))() if style_label else "",
        "style_diagnostics": style_diag,
        "agent_reviewed": bool(ag.get("agent_reviewed")),
        "panel_insights": ag.get("panel_insights") or "",
        "claude_narrative_stub": {
            "_note": "以下字段已由 agent 覆盖" if ag.get("agent_reviewed") else "以下字段是脚本生成的占位，Task 4 中 Claude 必须根据原始数据重写",
            "needs_rewrite": [] if ag.get("agent_reviewed") else [
                "great_divide.punchline", "dashboard.core_conclusion",
                "debate.rounds[*].bull_say", "debate.rounds[*].bear_say",
                "buy_zones.*.rationale", "risks[*]"],
        },
        "debate": {
            "bull": {"investor_id": bull["investor_id"], "name": bull["name"], "group": bull["group"]},
            "bear": {"investor_id": bear["investor_id"], "name": bear["name"], "group": bear["group"]},
            "rounds": rounds,
            "punchline": punchline,
        },
        "great_divide": {
            "bull_avatar": bull["investor_id"],
            "bear_avatar": bear["investor_id"],
            "bull_score": bull["score"],
            "bear_score": bear["score"],
            "bull_signal": bull["signal"],
            "bear_signal": bear["signal"],
            "punchline": punchline,
        },
        "risks": risks,
        "buy_zones": narrative_override.get("buy_zones") or {
            "value": {"price": round(price * 0.85, 2) if price else "—", "rationale": "历史 PE 25 分位"},
            "growth": {"price": round(price * 0.92, 2) if price else "—", "rationale": "PEG 合理区"},
            "technical": {"price": round(price * 0.95, 2) if price else "—", "rationale": "MA60 支撑位"},
            "youzi": {"price": price or "—", "rationale": "当前情绪未破"},
        },
        "friendly": {
            "scenarios": scenarios,
            "exit_triggers": exit_triggers,
            "similar_stocks": similar_stocks,
        },
        "fund_managers": raw.get("fund_managers", []),
        "dashboard": {
            "core_conclusion": core_conclusion,
            "data_perspective": {
                "trend": f"{kline.get('stage', '—')}",
                "price": f"¥{price}" if price else "—",
                "volume": "—",
                "chips": kline.get("ma_align", "—"),
            },
            "intelligence": {
                "news": "近期新闻 + 公告已采集",
                "risks": risks[:3],
                "catalysts": [
                    e.get("event", "季报")[:30]
                    for e in ((d21.get("catalyst_calendar") or {}).get("events") or [])
                    if e.get("impact") in ("high", "medium")
                ][:3] or ["季报窗口", "行业事件"],
            },
            "battle_plan": {
                "entry": f"¥{round(price * 0.92, 2) if price else '—'}",
                "position": "50% 起步",
                "stop": f"¥{round(price * 0.85, 2) if price else '—'}",
                "target": f"¥{round(price * 1.25, 2) if price else '—'}",
            },
        },
    }

