"""按股票特性动态加权评分 · v2.7

问题：旧公式 `consensus = bullish/active*100`+`overall=fund*0.6+consensus*0.4` 偏严苛，
51 评委里价值派+严苛筛选派占多，任何股票都难拿到 30+ 看多 → 一片回避。

修法：先识别股票"风格"（白马 / 高成长 / 周期 / 小盘投机 / 分红防御 / 困境反转 /
量化因子 / 中性兜底），然后按 style 调整：
  1. 评委权重（A-G 7 组 × style 矩阵 + 8 个个体 override）
  2. 22 维 fundamental 权重 multiplier
  3. neutral 半权计入 consensus（修正旧公式 0% 权重的问题）
阈值 85/70/55/40 不动，只靠加权让真正适合该 style 的评委话语权变大。

使用：
    from lib.stock_style import detect_style, apply_style_weights, STYLE_LABELS
    style = detect_style(features, raw)
    adj = apply_style_weights(panel_investors, dims_scored, style)
    fund_score = adj["fundamental_score"]
    consensus  = adj["panel_consensus"]
"""
from __future__ import annotations


# ─── 7 + 1 个 style 名称 ──
WHITE_HORSE        = "white_horse"          # 白马价值
GROWTH_TECH        = "growth_tech"          # 高成长科技
CYCLE              = "cycle"                # 周期股
SMALL_SPECULATIVE  = "small_speculative"    # 小盘投机
DIVIDEND_DEFENSE   = "dividend_defense"     # 分红防御
DISTRESSED         = "distressed"           # 困境反转
QUANT_FACTOR       = "quant_factor"         # 量化因子型
BALANCED           = "balanced"             # 兜底（无明显倾向）

ALL_STYLES = (WHITE_HORSE, GROWTH_TECH, CYCLE, SMALL_SPECULATIVE,
              DIVIDEND_DEFENSE, DISTRESSED, QUANT_FACTOR, BALANCED)

STYLE_LABELS = {
    WHITE_HORSE:       "白马价值",
    GROWTH_TECH:       "高成长科技",
    CYCLE:             "周期股",
    SMALL_SPECULATIVE: "小盘投机",
    DIVIDEND_DEFENSE:  "分红防御",
    DISTRESSED:        "困境反转",
    QUANT_FACTOR:      "量化因子型",
    BALANCED:          "中性兜底",
}

STYLE_EXPLANATIONS = {
    WHITE_HORSE:       "大盘 + 高 ROE + 低 PE · 价值派 (A 组+E 组) 加权 ×1.5、游资降权 ×0.3",
    GROWTH_TECH:       "高成长 + 科技/医药/新能源 · 成长派 (B 组) 加权 ×1.5、技术派 ×1.2",
    CYCLE:             "周期行业 · 宏观派 (C 组) 加权 ×1.5、原料/期货维度加权 ×1.5",
    SMALL_SPECULATIVE: "A 股小盘 · 游资 (F 组) 加权 ×1.5、龙虎榜/舆情维度加权 ×1.5",
    DIVIDEND_DEFENSE:  "高股息 + 银行/电力 · 价值派加权、财务/治理维度加权 ×1.3",
    DISTRESSED:        "PB<1 + ROE 低 · 卡拉曼/邓普顿加权 ×1.5、估值/财务维度加权",
    QUANT_FACTOR:      "多家量化基金重仓 · 量化派 (G 组) 加权 ×1.5、资金流维度加权",
    BALANCED:          "无明显风格倾向 · 全派系等权",
}


# ─── 行业分类（用于 style 判定）──
CYCLE_INDUSTRIES = frozenset({
    "煤炭", "钢铁", "有色金属", "化工", "石油石化", "建材", "水泥",
    "航运", "猪肉", "种植业", "造纸", "玻璃", "工程机械", "海运", "原油",
})

GROWTH_INDUSTRIES = frozenset({
    "半导体", "光学光电子", "电池", "光模块", "汽车整车", "医药生物", "医疗器械",
    "软件服务", "云计算", "AI", "数字经济", "信息技术", "新能源", "新材料",
    "生物医药", "创新药", "锂电池", "电动汽车", "5G",
})

DEFENSIVE_INDUSTRIES = frozenset({
    "银行", "保险", "电力", "燃气", "水务", "公用事业", "高速公路", "港口",
    "白酒", "食品饮料", "家电",
})


# ─── 7 styles × 7 组（A-G）权重矩阵 ──
# A=经典价值, B=成长投资, C=宏观对冲, D=技术趋势, E=中国价投, F=A股游资, G=量化系统
STYLE_GROUP_WEIGHTS: dict[str, dict[str, float]] = {
    WHITE_HORSE:       {"A": 1.5, "B": 0.7, "C": 1.0, "D": 0.8, "E": 1.5, "F": 0.3, "G": 1.0},
    GROWTH_TECH:       {"A": 0.7, "B": 1.5, "C": 0.8, "D": 1.2, "E": 0.7, "F": 0.7, "G": 1.0},
    CYCLE:             {"A": 1.0, "B": 0.5, "C": 1.5, "D": 1.0, "E": 1.0, "F": 1.0, "G": 0.8},
    SMALL_SPECULATIVE: {"A": 0.4, "B": 0.7, "C": 0.5, "D": 1.3, "E": 0.5, "F": 1.5, "G": 0.7},
    DIVIDEND_DEFENSE:  {"A": 1.5, "B": 0.5, "C": 1.0, "D": 0.7, "E": 1.3, "F": 0.3, "G": 1.0},
    DISTRESSED:        {"A": 1.5, "B": 0.4, "C": 1.0, "D": 0.7, "E": 1.3, "F": 0.5, "G": 0.5},
    QUANT_FACTOR:      {"A": 0.8, "B": 0.8, "C": 0.8, "D": 1.0, "E": 0.8, "F": 0.7, "G": 1.5},
    BALANCED:          {"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0, "E": 1.0, "F": 1.0, "G": 1.0},
}


# ─── 个体 override (style × investor_id → multiplier，与 group weight 相乘) ──
PERSON_OVERRIDES: dict[tuple[str, str], float] = {
    (WHITE_HORSE,        "buffett"):    1.5,
    (WHITE_HORSE,        "duan"):       1.4,
    (WHITE_HORSE,        "munger"):     1.3,
    (DISTRESSED,         "klarman"):    1.5,
    (DISTRESSED,         "templeton"):  1.4,
    (GROWTH_TECH,        "wood"):       1.5,
    (GROWTH_TECH,        "thiel"):      1.3,
    (GROWTH_TECH,        "lynch"):      1.2,
    (CYCLE,              "soros"):      1.4,
    (CYCLE,              "dalio"):      1.3,
    (SMALL_SPECULATIVE,  "zhao_lg"):    1.5,
    (SMALL_SPECULATIVE,  "zhang_mz"):   1.3,
    (QUANT_FACTOR,       "simons"):     1.5,
    (QUANT_FACTOR,       "thorp"):      1.3,
    (QUANT_FACTOR,       "shaw"):       1.3,
}


# ─── 22 维 fundamental 权重 multiplier (per style) ──
# 未列出的 dim 默认 1.0（不变）
STYLE_DIM_MULTIPLIERS: dict[str, dict[str, float]] = {
    WHITE_HORSE: {
        "1_financials": 1.5, "10_valuation": 1.5, "14_moat": 1.5,
        "16_lhb": 0.3, "17_sentiment": 0.5,
    },
    GROWTH_TECH: {
        "7_industry": 1.5, "14_moat": 1.3, "1_financials": 0.8,
        "10_valuation": 0.7,
    },
    CYCLE: {
        "3_macro": 1.5, "8_materials": 1.5, "9_futures": 1.5,
    },
    SMALL_SPECULATIVE: {
        "16_lhb": 1.5, "17_sentiment": 1.5, "2_kline": 1.3, "12_capital_flow": 1.3,
        "1_financials": 0.5, "14_moat": 0.3,
    },
    DIVIDEND_DEFENSE: {
        "1_financials": 1.3, "11_governance": 1.3,
        "16_lhb": 0.3, "17_sentiment": 0.5,
    },
    DISTRESSED: {
        "1_financials": 1.5, "10_valuation": 1.5, "11_governance": 1.5,
    },
    QUANT_FACTOR: {
        "12_capital_flow": 1.5, "2_kline": 1.3, "16_lhb": 0.7,
    },
    BALANCED: {},
}


# ─── style 检测 ──
def detect_style(features: dict, raw: dict | None = None) -> str:
    """根据股票 features 判定 style。优先级硬规则 + 量化信号兜底。

    特征字段（来自 stock_features.extract_features）：
    - market: "A" | "H" | "U"
    - market_cap_yi: 总市值（亿）
    - pe / pe_ttm: PE
    - pb: PB
    - roe_5y_avg / roe_5y_min / roe_latest
    - revenue_growth_3y_cagr / revenue_growth_latest
    - dividend_yield
    - industry: 中文行业名
    """
    if not isinstance(features, dict):
        return BALANCED
    raw = raw or {}

    pb = _f(features.get("pb"))
    pe = _f(features.get("pe") or features.get("pe_ttm"))
    roe_5y_min = _f(features.get("roe_5y_min"))
    roe_5y_avg = _f(features.get("roe_5y_avg"))
    mcap_yi = _f(features.get("market_cap_yi"))
    rev_g = _f(features.get("revenue_growth_3y_cagr") or features.get("revenue_growth_latest"))
    div_y = _f(features.get("dividend_yield"))
    industry = (features.get("industry") or "").strip()
    market = features.get("market") or "A"

    # 1. 困境反转：PB<1 且 ROE 5 年最低 < 5（含负值 — ST 股 / 周期低谷）
    # BUG#R1 fix: 旧条件 `0 < roe_5y_min < 5` 漏掉了负 ROE（ST 股普遍亏损），
    # 导致负 ROE 反而被判为 small_speculative
    if 0 < pb < 1.0 and roe_5y_min < 5:
        return DISTRESSED

    # 2. 量化因子型：多家量化基金 top-10 重仓
    try:
        from .quant_signal import detect_quant_signal
        sig = detect_quant_signal(
            features.get("code") or raw.get("ticker", ""),
            raw.get("fund_managers", []),
        )
        if sig.get("is_quant_factor_style"):
            return QUANT_FACTOR
    except Exception:
        pass

    # 3. A 股小盘投机：mcap<100 亿 + A 股
    if market == "A" and 0 < mcap_yi < 100:
        return SMALL_SPECULATIVE

    # 4. 周期股
    if any(kw in industry for kw in CYCLE_INDUSTRIES):
        return CYCLE

    # 5. 高成长科技：3 年 CAGR > 20% + 科技/医药/新能源
    if rev_g > 20 and any(kw in industry for kw in GROWTH_INDUSTRIES):
        return GROWTH_TECH

    # 6. 分红防御：股息率 > 4% + 银行/电力
    if div_y > 4.0 and any(kw in industry for kw in DEFENSIVE_INDUSTRIES):
        return DIVIDEND_DEFENSE

    # 7. 白马价值：大盘 + 低 PE + 高 ROE
    if mcap_yi > 1000 and 0 < pe < 25 and roe_5y_avg > 12:
        return WHITE_HORSE

    return BALANCED


def apply_style_weights(panel_investors: list[dict],
                        dims_scored: dict,
                        style: str) -> dict:
    """改写 panel_consensus 和 fundamental_score 的计算 — 按 style 加权。

    Args:
        panel_investors: list of investor dicts from panel.json
        dims_scored: result of score_dimensions (含 dimensions[dim_key])
        style: one of ALL_STYLES

    Returns:
        {
          "panel_consensus": float (0-100, weighted),
          "fundamental_score": float (0-100, weighted),
          "style": str,
          "diagnostics": {
            "active_weight": float,
            "bullish_weight": float,
            "neutral_weight": float,
            "raw_consensus_old": float,  # 旧公式结果，对比用
            "raw_fund_old": float,
          }
        }
    """
    style = style if style in STYLE_GROUP_WEIGHTS else BALANCED
    group_w = STYLE_GROUP_WEIGHTS[style]
    dim_mults = STYLE_DIM_MULTIPLIERS.get(style, {})

    # ── Panel weighted consensus ──
    bullish_w = neutral_w = active_w = 0.0
    bullish_n = neutral_n = bearish_n = 0
    for inv in (panel_investors or []):
        sig = inv.get("signal", "neutral")
        if sig == "skip":
            continue
        gid = inv.get("group", "")
        gw = group_w.get(gid, 1.0)
        pw = PERSON_OVERRIDES.get((style, inv.get("investor_id", "")), 1.0)
        w = gw * pw
        active_w += w
        if sig == "bullish":
            bullish_w += w
            bullish_n += 1
        elif sig == "neutral":
            neutral_w += w * 0.5    # neutral 半权计入
            neutral_n += 1
        else:
            bearish_n += 1

    consensus = (bullish_w + neutral_w) / max(active_w, 0.001) * 100

    # 旧公式（仅 bullish 计入）— 对比用
    active_n = bullish_n + neutral_n + bearish_n
    raw_consensus_old = bullish_n / max(active_n, 1) * 100

    # ── Fundamental weighted score ──
    total_weighted = total_weight = 0.0
    total_weighted_old = total_weight_old = 0.0
    for dim_key, d in (dims_scored.get("dimensions") or {}).items():
        if not isinstance(d, dict):
            continue
        score = float(d.get("score", 0))
        base_w = float(d.get("weight", 1))
        mult = dim_mults.get(dim_key, 1.0)
        w = base_w * mult
        total_weighted += score * w
        total_weight += w
        total_weighted_old += score * base_w
        total_weight_old += base_w

    fund_score = (total_weighted / total_weight * 10) if total_weight else 0
    raw_fund_old = (total_weighted_old / total_weight_old * 10) if total_weight_old else 0

    return {
        "panel_consensus": round(consensus, 1),
        "fundamental_score": round(fund_score, 1),
        "style": style,
        "diagnostics": {
            "active_weight": round(active_w, 2),
            "bullish_weight": round(bullish_w, 2),
            "neutral_weight": round(neutral_w, 2),
            "active_count": active_n,
            "bullish_count": bullish_n,
            "neutral_count": neutral_n,
            "bearish_count": bearish_n,
            "raw_consensus_old": round(raw_consensus_old, 1),
            "raw_fund_old": round(raw_fund_old, 1),
        },
    }


def _f(v, default=0.0) -> float:
    if v is None:
        return default
    try:
        s = str(v).replace(",", "").replace("%", "").replace("亿", "").replace("+", "").strip()
        if s in ("", "—", "-", "nan", "None", "N/A"):
            return default
        return float(s)
    except (ValueError, TypeError):
        return default


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    code = sys.argv[1] if len(sys.argv) > 1 else "600120.SH"

    raw_path = Path(".cache") / code / "raw_data.json"
    dims_path = Path(".cache") / code / "dimensions.json"
    panel_path = Path(".cache") / code / "panel.json"
    if not (raw_path.exists() and dims_path.exists() and panel_path.exists()):
        print(f"Missing cache files for {code}; run stage1 first.")
        sys.exit(1)

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    dims = json.loads(dims_path.read_text(encoding="utf-8"))
    panel = json.loads(panel_path.read_text(encoding="utf-8"))

    # Build features (simplified — for testing only)
    basic = (raw["dimensions"].get("0_basic") or {}).get("data") or {}
    features = {
        "code": code,
        "market": raw.get("market", "A"),
        "industry": basic.get("industry", ""),
        "market_cap_yi": _f((basic.get("market_cap_raw") or 0) / 1e8) if basic.get("market_cap_raw") else 0,
        "pe": _f(basic.get("pe_ttm")),
        "pe_ttm": _f(basic.get("pe_ttm")),
        "pb": _f(basic.get("pb")),
        "roe_5y_avg": 8.0,  # placeholder
        "roe_5y_min": 5.0,
        "revenue_growth_3y_cagr": 5.0,
        "dividend_yield": _f(basic.get("dividend_yield_ttm")),
    }

    style = detect_style(features, raw)
    print(f"=== Detected style: {style} ({STYLE_LABELS[style]}) ===")
    print(f"  features: mcap={features['market_cap_yi']:.0f}亿  pe={features['pe']}  pb={features['pb']}  industry={features['industry']}")

    adj = apply_style_weights(panel.get("investors", []), dims, style)
    print()
    print(f"=== Score comparison ===")
    print(f"  fundamental:   {adj['fundamental_score']:5.1f}  (was {adj['diagnostics']['raw_fund_old']:5.1f})")
    print(f"  panel consensus: {adj['panel_consensus']:5.1f}  (was {adj['diagnostics']['raw_consensus_old']:5.1f})")
    overall_new = adj["fundamental_score"] * 0.6 + adj["panel_consensus"] * 0.4
    overall_old = adj["diagnostics"]["raw_fund_old"] * 0.6 + adj["diagnostics"]["raw_consensus_old"] * 0.4
    print(f"  OVERALL:       {overall_new:5.1f}  (was {overall_old:5.1f})")
    print()
    print(f"  diagnostics: {adj['diagnostics']}")
