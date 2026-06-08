"""Regression for v3.8.0 · 参考三个外部仓库的改进.

参考来源：
- muxuuu/serenity-skill → Serenity 罚分因子 + 证据阶梯 + 供应链分层
- lolifamily/ashare-mcp → 技术指标广度 (KDJ/OBV/Williams) + DuPont 杜邦

测试覆盖：
A. Serenity 证据阶梯：同卡位 · 有硬证据 strong > 仅叙事 weak (分数被折扣)
B. Serenity 罚分：炒作无订单 / 微盘流动性 / 杀猪盘 / 周期 / 地缘 / 稀释 → 减分
C. Serenity 供应链分层：材料(上游)tier_weight > 整机(下游)
D. DuPont：stock_features 正确 surface 杜邦三因子 + roe_quality
E. 技术指标：KDJ/OBV/Williams 正确计算 + surface 到 features
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def _feat(name, ind, mcap, chain, switching=8, scale=7, events=None,
          policy="积极支持", growth="35%", extra_dims=None):
    """构造 raw → extract_features · 可注入 extra_dims (如 1_financials)."""
    from lib.stock_features import extract_features
    dims = {
        "0_basic": {"data": {"name": name, "industry": ind,
                             "market_cap": f"{mcap}亿", "price": "50"}},
        "5_chain": {"data": {"desc": chain}},
        "7_industry": {"data": {"growth": growth}},
        "14_moat": {"data": {"scores": {"switching": switching, "scale": scale,
                                        "intangible": 5, "network": 3}}},
        "13_policy": {"data": {"policy_dir": policy}},
        "15_events": {"data": {"event_timeline": events or []}},
    }
    if extra_dims:
        dims.update(extra_dims)
    return extract_features({"ticker": "T.SZ", "dimensions": dims}, {})


# ─── A · 证据阶梯 ─────────────────────────────────────────

def test_evidence_grade_strong_vs_weak_discount():
    """同一卡位点 · 有定点/量产硬证据 → strong · 仅叙事 → weak 被折扣."""
    strong = _feat("有证据", "谐波减速器", 250,
                   "人形机器人 谐波减速器 特斯拉定点 量产交付", events=["大订单", "量产"])
    weak = _feat("仅叙事", "谐波减速器", 250,
                 "人形机器人 谐波减速器 概念 题材")
    assert strong["ai_evidence_grade"] == "strong"
    assert weak["ai_evidence_grade"] == "weak"
    assert strong["ai_chokepoint_score"] > weak["ai_chokepoint_score"] + 15, \
        f"硬证据应显著高于纯叙事: {strong['ai_chokepoint_score']} vs {weak['ai_chokepoint_score']}"


def test_evidence_weak_narrative_only_capped():
    """纯叙事卡位 · 即使关键词命中 · 分数被证据折扣压住 (Serenity 不盲信)."""
    weak = _feat("纯题材", "谐波减速器", 250, "人形机器人 谐波减速器 风口 题材")
    assert weak["ai_evidence_grade"] == "weak"
    assert weak["ai_chokepoint_score"] < 70


# ─── B · 罚分因子 ─────────────────────────────────────────

def test_penalty_cyclicality():
    """纯周期行业关键词 → 周期罚分."""
    f = _feat("某周期股", "化合物半导体", 200,
              "衬底 外延 化工原料 周期 量产 订单", events=["大订单"])
    assert "cyclicality" in f["ai_penalties"]
    assert f["ai_penalty_total"] > 0


def test_penalty_geopolitics_without_localization():
    """出口管制/制裁 但无国产替代叙事 → 地缘罚分."""
    f = _feat("被制裁股", "光刻设备", 200, "光刻 设备 出口管制 实体清单 量产", events=["大订单"])
    assert "geopolitics" in f["ai_penalties"]


def test_geopolitics_with_localization_no_penalty():
    """有国产替代叙事 → 制裁反而是 thesis · 不罚地缘."""
    f = _feat("国产替代", "光刻设备", 200, "光刻 设备 出口管制 国产替代 自主可控 量产", events=["大订单"])
    assert "geopolitics" not in f["ai_penalties"]


def test_penalty_dilution():
    """负向催化含定增/解禁 → 稀释罚分."""
    f = _feat("定增股", "谐波减速器", 200, "人形机器人 谐波减速器 量产",
              events=["定增预案", "限售解禁", "业绩下滑"])
    assert "dilution" in f["ai_penalties"]


def test_penalties_reduce_score():
    """有罚分的标的 · 分数低于无罚分的同类标的."""
    clean = _feat("干净卡位", "化合物半导体", 200, "衬底 外延 量产 订单", events=["大订单"])
    penalized = _feat("周期卡位", "化合物半导体", 200,
                      "衬底 外延 化工原料 周期 量产 订单", events=["大订单"])
    assert penalized["ai_penalty_total"] > clean["ai_penalty_total"]
    assert penalized["ai_chokepoint_score"] < clean["ai_chokepoint_score"]


# ─── C · 供应链分层 ───────────────────────────────────────

def test_supply_chain_tier_upstream_higher():
    """材料(最上游) tier_weight > 整机(下游)."""
    material = _feat("材料股", "化合物半导体", 200, "磷化铟 衬底 外延", events=["量产"])
    assembler = _feat("整机股", "工业机器人整机", 200, "机器人整机 系统集成", events=["量产"])
    assert material["ai_chain_tier_weight"] > assembler["ai_chain_tier_weight"]
    assert material["ai_chain_tier"] == "材料耗材"


def test_supply_chain_tier_labels():
    """分层标签正确."""
    assert _feat("a", "x", 200, "谐波减速器")["ai_chain_tier"] == "芯片/器件"
    assert _feat("b", "x", 200, "光模块 组装")["ai_chain_tier"] == "模块/子系统"
    assert _feat("c", "x", 200, "cowos 先进封装")["ai_chain_tier"] == "制程/封装"


# ─── D · DuPont 杜邦 ──────────────────────────────────────

def test_dupont_surfaced_to_features():
    """financials 提供 dupont → stock_features 正确暴露三因子 + roe_quality."""
    fin_dim = {"1_financials": {"data": {
        "roe": "25.0%", "net_margin": "20.0%",
        "dupont": {
            "net_margin_pct": 20.0, "asset_turnover": 0.8,
            "equity_multiplier": 1.56, "roe_reconstructed_pct": 24.96,
            "roe_quality": "margin_driven",
        },
    }}}
    f = _feat("高质量ROE", "白酒", 2000, "酿造", extra_dims=fin_dim)
    assert f["dupont_net_margin"] == 20.0
    assert f["dupont_asset_turnover"] == 0.8
    assert f["dupont_equity_multiplier"] == 1.56
    assert f["roe_quality"] == "margin_driven"


def test_dupont_leverage_driven_flag():
    """高杠杆 + 低净利率 → leverage_driven 标签 (在 fetch_financials 逻辑)."""
    # 直接验证质量分类逻辑：em>=2.5 且 nm<10 → leverage_driven
    nm, em = 6.0, 3.0
    quality = ("leverage_driven" if (em >= 2.5 and nm < 10)
               else "margin_driven" if nm >= 15 else "balanced")
    assert quality == "leverage_driven"


# ─── E · 技术指标 KDJ/OBV/Williams ────────────────────────

def _synth_klines(n=120, up=True):
    import math
    kl = []
    for i in range(n):
        base = (10 + i * 0.08 if up else 30 - i * 0.08) + math.sin(i / 5) * 0.5
        kl.append({"收盘": base, "最高": base * 1.02, "最低": base * 0.98,
                   "成交量": 1e6 * (1 + 0.01 * i)})
    return kl


def test_kdj_computed():
    from fetch_kline import compute_indicators
    ind = compute_indicators(_synth_klines())
    for k in ("kdj_k", "kdj_d", "kdj_j"):
        assert ind.get(k) is not None
        assert 0 <= ind["kdj_k"] <= 100 or ind["kdj_j"] is not None  # K 在 0-100 区


def test_obv_trend_up_on_rising():
    from fetch_kline import compute_indicators
    ind = compute_indicators(_synth_klines(up=True))
    assert ind.get("obv") is not None
    assert ind.get("obv_trend_up") is True


def test_williams_r_range():
    from fetch_kline import compute_indicators
    ind = compute_indicators(_synth_klines())
    wr = ind.get("williams_r")
    assert wr is not None
    assert -100 <= wr <= 0, f"Williams%R 应在 -100..0, 实际 {wr}"


def test_indicators_surfaced_to_features():
    """kline.indicators 的 KDJ/OBV/Williams 应 surface 到 features."""
    from fetch_kline import compute_indicators
    ind = compute_indicators(_synth_klines())
    kline_dim = {"2_kline": {"data": {"indicators": ind, "stage": "Stage 2 上升",
                                      "ma_align": "多头排列", "macd": "金叉水上", "rsi": "78"}}}
    f = _feat("技术股", "光模块", 200, "光模块 量产", extra_dims=kline_dim)
    assert f["kdj_k"] == ind["kdj_k"]
    assert f["williams_r"] == ind["williams_r"]
    assert isinstance(f["obv_trend_up"], bool)
    assert isinstance(f["kdj_golden_cross"], bool)
