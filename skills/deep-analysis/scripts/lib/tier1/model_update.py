"""Model Update — 用新数据增量更新财务模型并算 delta。

改编自 anthropics/financial-services equity-research/model-update。

原版是一份给分析师手填的 markdown 工作流（plug earnings → revise estimates →
recalc valuation → new PT）。这里重写为 UZI 范式的纯函数：吃 features + raw_data
+ 一组新假设 (updates)，输出关键假设 before→after 的 delta 表，并把 delta 传导到
DCF 内在价值、Comps 隐含价、投资逻辑 (thesis) 各支柱，给出更新后的 verdict。

A 股 / 港股 / 美股通用；估值参数沿用 UZI（A 股 rf 2.5% / ERP 6% / 税 25%，
见 references/task1.5-institutional-modeling.md）。

入口：
    build_model_update(features, raw_data, updates=None,
                       dcf_result=None, comps_result=None) -> dict

约定：
    - `updates` 是新假设 dict，键见 _ASSUMPTION_SPECS（rev_growth / gross_margin /
      net_margin / capex_pct / target_price / stage1_growth / terminal_g / beta / wacc）。
    - `updates=None` 时从 features 推断「最新 vs 上期」做 delta 演示（营收增速最新
      vs 3 年 CAGR、卖方目标价 vs 现价等），保证函数永远能跑出结构。
    - 传入 dcf_result / comps_result 时，按 updates 里的增长/利润率/目标价改动重算
      内在价值与隐含价并算 delta；不传则该影响段标记为「未提供」。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _num(v, default=0.0) -> float:
    try:
        return float(str(v).replace("%", "").replace(",", "").replace("¥", "").strip())
    except (TypeError, ValueError):
        return default


# ────────────────────────────────────────────────────────────────
# 假设规格：key → (中文标签, 单位, features 里的 before 推断源, 影响通道)
# unit: "pct" 百分比 · "x" 倍数 · "price" 价格
# channel: 该假设改动会传导到哪个估值 (dcf / comps / both / none)
# ────────────────────────────────────────────────────────────────
_ASSUMPTION_SPECS: dict[str, dict] = {
    "rev_growth": {"label": "营收增速", "unit": "pct", "channel": "dcf",
                   "from_features": ("revenue_growth_latest", "revenue_growth_3y_cagr")},
    "gross_margin": {"label": "毛利率", "unit": "pct", "channel": "dcf",
                     "from_features": ("gross_margin", None)},
    "net_margin": {"label": "净利率", "unit": "pct", "channel": "both",
                   "from_features": ("net_margin", None)},
    "capex_pct": {"label": "Capex/营收", "unit": "pct", "channel": "dcf",
                  "from_features": (None, None)},
    "stage1_growth": {"label": "DCF Stage1 增速", "unit": "pct", "channel": "dcf",
                      "from_features": (None, None)},
    "terminal_g": {"label": "DCF 终值 g", "unit": "pct", "channel": "dcf",
                   "from_features": (None, None)},
    "beta": {"label": "Beta", "unit": "x", "channel": "dcf",
             "from_features": (None, None)},
    "target_pe": {"label": "目标 PE", "unit": "x", "channel": "comps",
                  "from_features": ("pe", None)},
    "target_price": {"label": "目标价", "unit": "price", "channel": "comps",
                     "from_features": ("target_price_avg", "price")},
}


def _fmt(unit: str, v: float) -> str:
    if unit == "pct":
        return f"{v:.1f}%"
    if unit == "x":
        return f"{v:.2f}x"
    if unit == "price":
        return f"¥{v:.2f}"
    return f"{v:.2f}"


def _delta_dir(after: float, before: float) -> str:
    if after > before + 1e-9:
        return "↑"
    if after < before - 1e-9:
        return "↓"
    return "→"


def _infer_before_after(spec: dict, features: dict, after_raw) -> tuple[float, float]:
    """推断 before（旧假设），after 来自 updates。

    updates 未给该键时（演示模式），用 from_features 的两个源做「最新 vs 上期」。
    """
    src_after, src_before = spec.get("from_features", (None, None))
    before = _num(features.get(src_before)) if src_before else 0.0
    if after_raw is not None:
        # 用户显式给了新假设 → after = updates 值; before = features 推断或 after 兜底
        after = _num(after_raw)
        if src_after and before == 0.0:
            before = _num(features.get(src_after))
        if src_after and src_before is None:
            before = _num(features.get(src_after))
        return before, after
    # 演示模式：after = 最新值, before = 上期/基准值
    after = _num(features.get(src_after)) if src_after else 0.0
    if src_before is None:
        # 没有第二个源 → 制造一个温和基准（after 的 95%）做演示
        before = round(after * 0.95, 3)
    return before, after


# ═══════════════════════════════════════════════════════════════
# 估值传导：DCF
# ═══════════════════════════════════════════════════════════════

def _reprice_dcf(dcf_result: dict, deltas: list[dict], features: dict) -> dict:
    """按 delta 表里改动的增长/利润率假设线性近似重算 DCF 每股价值。

    精确做法是回灌 compute_dcf；为保持本模块纯粹 + 无副作用，这里用一阶弹性近似：
        - Stage1 增速每 +1pp → 内在价值约 +x%（用 PV 结构敏感性近似）
        - 净利率 / 毛利率改动直接按比例缩放基期 FCF
    返回 before / after 每股内在价值 + delta。
    """
    before_ps = _num(dcf_result.get("intrinsic_per_share"))
    if before_ps <= 0:
        return {"available": False, "reason": "dcf_result 无有效 intrinsic_per_share"}

    a = dcf_result.get("assumptions", {}) or {}
    g1_before = _num(a.get("stage1_growth"))  # 小数形式 e.g. 0.10
    tg_before = _num(a.get("terminal_g"))

    # 收集对 DCF 有影响的改动（统一转小数）
    fcf_scale = 1.0      # 基期 FCF 缩放（来自利润率改动）
    g1_after = g1_before
    tg_after = tg_before
    beta_after = _num(a.get("beta")) or 1.0
    notes: list[str] = []

    for d in deltas:
        key = d["key"]
        if key == "stage1_growth":
            g1_after = d["after"] / 100.0
            notes.append(f"Stage1 增速 {d['before']:.1f}%→{d['after']:.1f}%")
        elif key == "rev_growth":
            # 营收增速改动 → 近似映射到 Stage1 增速（取一半弹性，营收≠FCF）
            g1_after = max(0.0, g1_before + (d["after"] - d["before"]) / 100.0 * 0.5)
            notes.append(f"营收增速 {d['before']:.1f}%→{d['after']:.1f}% (传导 Stage1)")
        elif key == "terminal_g":
            tg_after = d["after"] / 100.0
            notes.append(f"终值 g {d['before']:.1f}%→{d['after']:.1f}%")
        elif key in ("net_margin", "gross_margin"):
            if d["before"] > 0:
                fcf_scale *= d["after"] / d["before"]
                notes.append(f"{_ASSUMPTION_SPECS[key]['label']} {d['before']:.1f}%→{d['after']:.1f}% (缩放基期 FCF)")
        elif key == "beta":
            beta_after = d["after"]
            notes.append(f"Beta {d['before']:.2f}→{d['after']:.2f}")
        elif key == "capex_pct":
            # capex 上升 → FCF 下降：每 +1pp capex 约 -3% FCF（粗略弹性）
            fcf_scale *= max(0.1, 1 - (d["after"] - d["before"]) / 100.0 * 3)
            notes.append(f"Capex/营收 {d['before']:.1f}%→{d['after']:.1f}% (压低 FCF)")

    # WACC 近似：beta 改动 → cost of equity 改动 → wacc 改动（沿用 UZI 默认 erp/rf）
    wacc_b = dcf_result.get("wacc_breakdown", {}) or {}
    wacc_before = _num(wacc_b.get("wacc")) or 0.08
    inp = wacc_b.get("inputs", {}) or {}
    rf = _num(inp.get("rf"), 0.025)
    erp = _num(inp.get("erp"), 0.06)
    beta_before = _num(inp.get("beta")) or 1.0
    eq_w = _num(wacc_b.get("equity_weight"), 0.70)
    wacc_after = wacc_before + eq_w * (beta_after - beta_before) * erp

    # Gordon-growth 风格的一阶近似重定价：
    #   value ∝ fcf_scale；对 g1（驱动显式期复利）与 (wacc - g) 终值因子敏感。
    # 近似比率：终值因子 (wacc_b - tg_b)/(wacc_a - tg_a) 捕捉折现 + 永续增长改动。
    denom_before = max(wacc_before - tg_before, 1e-4)
    denom_after = max(wacc_after - tg_after, 1e-4)
    tv_factor = denom_before / denom_after

    # 显式期增长改动：5 年高增长期，复利效应约 (1+g1_a)^5 / (1+g1_b)^5
    growth_factor = ((1 + g1_after) ** 5) / ((1 + g1_before) ** 5) if g1_before > -1 else 1.0

    after_ps = round(before_ps * fcf_scale * tv_factor * growth_factor, 2)
    delta_abs = round(after_ps - before_ps, 2)
    delta_pct = round(delta_abs / before_ps * 100, 1) if before_ps > 0 else 0.0

    cur_price = _num(features.get("price")) or _num(dcf_result.get("current_price"))
    sm_before = _num(dcf_result.get("safety_margin_pct"))
    sm_after = round((after_ps - cur_price) / cur_price * 100, 1) if cur_price > 0 else sm_before

    return {
        "available": True,
        "intrinsic_before": before_ps,
        "intrinsic_after": after_ps,
        "delta_abs": delta_abs,
        "delta_pct": delta_pct,
        "direction": _delta_dir(after_ps, before_ps),
        "wacc_before_pct": round(wacc_before * 100, 2),
        "wacc_after_pct": round(wacc_after * 100, 2),
        "safety_margin_before_pct": sm_before,
        "safety_margin_after_pct": sm_after,
        "drivers": notes or ["无 DCF 相关假设改动 → 内在价值不变"],
    }


# ═══════════════════════════════════════════════════════════════
# 估值传导：Comps
# ═══════════════════════════════════════════════════════════════

def _reprice_comps(comps_result: dict, deltas: list[dict], features: dict) -> dict:
    """按 EPS（净利率改动）/ 目标 PE 改动重算 Comps 隐含价。"""
    implied_before = comps_result.get("implied_price") or {}
    pe_implied_before = _num(implied_before.get("via_median_pe"))
    pb_implied_before = _num(implied_before.get("via_median_pb"))
    if pe_implied_before <= 0 and pb_implied_before <= 0:
        return {"available": False, "reason": "comps_result 无 implied_price"}

    target = comps_result.get("target", {}) or {}
    eps = _num(target.get("eps")) or _num(features.get("eps"))
    median_pe = _num((comps_result.get("peer_stats", {}) or {}).get("pe", {}).get("median"))

    eps_scale = 1.0
    pe_override = None
    notes: list[str] = []
    for d in deltas:
        if d["key"] == "net_margin" and d["before"] > 0:
            eps_scale *= d["after"] / d["before"]
            notes.append(f"净利率 {d['before']:.1f}%→{d['after']:.1f}% (放大 EPS)")
        elif d["key"] == "target_pe":
            pe_override = d["after"]
            notes.append(f"目标 PE {d['before']:.2f}x→{d['after']:.2f}x")

    eps_after = eps * eps_scale
    pe_used = pe_override if pe_override is not None else median_pe
    if pe_used > 0 and eps_after > 0:
        pe_implied_after = round(pe_used * eps_after, 2)
    else:
        # 没有可用 EPS/PE → 按 EPS 缩放近似旧隐含价
        pe_implied_after = round(pe_implied_before * eps_scale, 2)

    delta_abs = round(pe_implied_after - pe_implied_before, 2)
    delta_pct = round(delta_abs / pe_implied_before * 100, 1) if pe_implied_before > 0 else 0.0

    return {
        "available": True,
        "implied_pe_before": pe_implied_before,
        "implied_pe_after": pe_implied_after,
        "implied_pb_before": pb_implied_before,
        "delta_abs": delta_abs,
        "delta_pct": delta_pct,
        "direction": _delta_dir(pe_implied_after, pe_implied_before),
        "drivers": notes or ["无 Comps 相关假设改动 → 隐含价不变"],
    }


# ═══════════════════════════════════════════════════════════════
# 投资逻辑 (thesis) 各支柱影响
# ═══════════════════════════════════════════════════════════════

def _thesis_impact(deltas: list[dict]) -> list[dict]:
    """把每条假设改动映射到对应投资逻辑支柱的方向性影响。"""
    pillar_map = {
        "rev_growth": "成长性（营收增速）",
        "gross_margin": "盈利质量（毛利率）",
        "net_margin": "盈利质量（净利率）",
        "capex_pct": "现金流 / 资本纪律",
        "stage1_growth": "成长性（中期增速）",
        "terminal_g": "长期价值（永续增长）",
        "beta": "风险 / 折现率",
        "target_pe": "估值锚（倍数）",
        "target_price": "估值锚（目标价）",
    }
    out = []
    for d in deltas:
        if abs(d.get("delta", 0)) < 1e-9:
            continue
        # capex / beta 上升是利空，其余上升是利多
        bearish_up = d["key"] in ("capex_pct", "beta")
        up = d["direction"] == "↑"
        bullish = up != bearish_up  # XOR：上升且非利空键 → 利多
        out.append({
            "pillar": pillar_map.get(d["key"], d["label"]),
            "change": f"{d['before_fmt']} → {d['after_fmt']} ({d['direction']})",
            "impact": "💪 强化" if bullish else "⚠️ 削弱",
        })
    if not out:
        out.append({"pillar": "（无实质假设改动）", "change": "—", "impact": "⚪ 中性"})
    return out


# ═══════════════════════════════════════════════════════════════
# verdict
# ═══════════════════════════════════════════════════════════════

def _verdict(dcf_impact: dict, comps_impact: dict, thesis: list[dict]) -> dict:
    """综合 DCF / Comps / thesis 给更新后评级。"""
    score = 0.0
    if dcf_impact.get("available"):
        score += dcf_impact["delta_pct"]
    if comps_impact.get("available"):
        score += comps_impact["delta_pct"]
    strengthen = sum(1 for t in thesis if t["impact"].startswith("💪"))
    weaken = sum(1 for t in thesis if t["impact"].startswith("⚠️"))
    score += (strengthen - weaken) * 2  # 每条支柱 ±2 权重

    if score >= 10:
        rating, action = "🟢 上修 (Upgrade)", "上调目标价 / 加仓候选"
    elif score >= 3:
        rating, action = "🟡 小幅上修", "维持评级，目标价微升"
    elif score > -3:
        rating, action = "⚪ 维持 (Maintain)", "数据落在噪声区间，观点不变"
    elif score > -10:
        rating, action = "🟠 小幅下修", "维持评级，目标价微降"
    else:
        rating, action = "🔴 下修 (Downgrade)", "下调目标价 / 减仓候选"

    return {
        "rating": rating,
        "action": action,
        "composite_score": round(score, 1),
        "pillars_strengthened": strengthen,
        "pillars_weakened": weaken,
    }


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

def build_model_update(
    features: dict,
    raw_data: dict,
    updates: dict | None = None,
    dcf_result: dict | None = None,
    comps_result: dict | None = None,
) -> dict:
    """用新数据增量更新财务模型。

    Args:
        features:    lib.stock_features.extract_features 输出。
        raw_data:    原始 22 维数据（本函数主要用于公司名/code 取数）。
        updates:     新假设 dict，键见 _ASSUMPTION_SPECS。None → 演示模式
                     （从 features 推断「最新 vs 上期」）。
        dcf_result:  lib.fin_models.compute_dcf 输出，用于算内在价值 delta。
        comps_result:lib.fin_models.build_comps_table 输出，用于算隐含价 delta。

    Returns:
        结构化 dict：delta 表 + DCF/Comps/thesis 影响 + 更新后 verdict + methodology_log。
    """
    dims = (raw_data or {}).get("dimensions", {}) or {}
    basic = (dims.get("0_basic") or {}).get("data") or {}
    name = basic.get("name") or features.get("name") or "—"
    code = basic.get("code") or features.get("code") or features.get("ticker") or "—"

    demo_mode = updates is None
    updates = updates or {}

    # ─── ① 关键假设 before → after delta 表 ───
    deltas: list[dict] = []
    # 演示模式：遍历有 features 源的规格；显式模式：只看 updates 给到的键 + 有源的键
    keys = list(_ASSUMPTION_SPECS.keys()) if demo_mode else list(
        dict.fromkeys(list(updates.keys()) + [
            k for k, s in _ASSUMPTION_SPECS.items()
            if s["from_features"][0] and k in updates
        ])
    )
    for key in keys:
        spec = _ASSUMPTION_SPECS.get(key)
        if spec is None:
            continue
        after_raw = updates.get(key)
        # 演示模式下需要 features 源；显式模式下需要 updates 给值
        if demo_mode and not spec["from_features"][0]:
            continue
        if not demo_mode and after_raw is None:
            continue
        before, after = _infer_before_after(spec, features, after_raw)
        # 演示模式下若两值都是 0 → 跳过（无数据）
        if demo_mode and before == 0 and after == 0:
            continue
        delta = round(after - before, 3)
        deltas.append({
            "key": key,
            "label": spec["label"],
            "unit": spec["unit"],
            "channel": spec["channel"],
            "before": round(before, 3),
            "after": round(after, 3),
            "before_fmt": _fmt(spec["unit"], before),
            "after_fmt": _fmt(spec["unit"], after),
            "delta": delta,
            "delta_fmt": ("+" if delta >= 0 else "") + _fmt(spec["unit"], delta).replace("¥", "¥"),
            "direction": _delta_dir(after, before),
        })

    # ─── ② DCF 内在价值影响 ───
    if dcf_result:
        dcf_impact = _reprice_dcf(dcf_result, deltas, features)
    else:
        dcf_impact = {"available": False, "reason": "未提供 dcf_result"}

    # ─── ③ Comps 隐含价影响 ───
    if comps_result:
        comps_impact = _reprice_comps(comps_result, deltas, features)
    else:
        comps_impact = {"available": False, "reason": "未提供 comps_result"}

    # ─── ④ 投资逻辑各支柱影响 ───
    thesis_impact = _thesis_impact(deltas)

    # ─── ⑤ 更新后 verdict ───
    verdict = _verdict(dcf_impact, comps_impact, thesis_impact)

    # ─── methodology_log ───
    log = [
        f"Step 1 · {'演示模式（最新 vs 上期推断）' if demo_mode else f'用户传入 {len(updates)} 项新假设'} → {len(deltas)} 条 delta",
    ]
    for d in deltas[:6]:
        log.append(f"        · {d['label']}: {d['before_fmt']} → {d['after_fmt']} ({d['direction']})")
    if dcf_impact.get("available"):
        log.append(
            f"Step 2 · DCF 内在价值 ¥{dcf_impact['intrinsic_before']:.2f} → "
            f"¥{dcf_impact['intrinsic_after']:.2f} ({dcf_impact['delta_pct']:+.1f}%)"
        )
    else:
        log.append(f"Step 2 · DCF 影响：{dcf_impact.get('reason', '未提供')}")
    if comps_impact.get("available"):
        log.append(
            f"Step 3 · Comps 隐含价 ¥{comps_impact['implied_pe_before']:.2f} → "
            f"¥{comps_impact['implied_pe_after']:.2f} ({comps_impact['delta_pct']:+.1f}%)"
        )
    else:
        log.append(f"Step 3 · Comps 影响：{comps_impact.get('reason', '未提供')}")
    log.append(
        f"Step 4 · 投资逻辑：{verdict['pillars_strengthened']} 强化 / "
        f"{verdict['pillars_weakened']} 削弱"
    )
    log.append(f"Step 5 · 更新后评级：{verdict['rating']}（综合分 {verdict['composite_score']:+.1f}）→ {verdict['action']}")

    return {
        "method": "Model Update (增量更新财务模型)",
        "company": {"name": name, "code": code},
        "mode": "demo" if demo_mode else "explicit",
        "generated_at": datetime.now().strftime("%Y-%m-%d"),
        "assumption_deltas": deltas,
        "dcf_impact": dcf_impact,
        "comps_impact": comps_impact,
        "thesis_impact": thesis_impact,
        "verdict": verdict,
        "methodology_log": log,
    }


if __name__ == "__main__":
    import json
    feats = {
        "name": "演示科技", "code": "000001.SZ", "price": 18.5,
        "revenue_growth_latest": 22.0, "revenue_growth_3y_cagr": 15.0,
        "gross_margin": 38.0, "net_margin": 14.0, "pe": 35.0,
        "target_price_avg": 24.0, "eps": 0.62,
    }
    # 演示模式
    out = build_model_update(feats, {})
    print(json.dumps(out["methodology_log"], ensure_ascii=False, indent=2))
    # 显式 + DCF/Comps
    dcf = {"intrinsic_per_share": 20.0, "current_price": 18.5,
           "safety_margin_pct": 8.1, "assumptions": {"stage1_growth": 0.10, "terminal_g": 0.025, "beta": 1.0},
           "wacc_breakdown": {"wacc": 0.085, "equity_weight": 0.7, "inputs": {"rf": 0.025, "erp": 0.06, "beta": 1.0}}}
    comps = {"implied_price": {"via_median_pe": 22.0}, "target": {"eps": 0.62},
             "peer_stats": {"pe": {"median": 35.5}}}
    out2 = build_model_update(
        feats, {}, updates={"rev_growth": 26.0, "net_margin": 16.0, "capex_pct": 7.0},
        dcf_result=dcf, comps_result=comps,
    )
    print("\n--- explicit ---")
    print(json.dumps(out2["verdict"], ensure_ascii=False, indent=2))
    print("DCF:", out2["dcf_impact"]["intrinsic_before"], "→", out2["dcf_impact"]["intrinsic_after"])
    print("Comps:", out2["comps_impact"]["implied_pe_before"], "→", out2["comps_impact"]["implied_pe_after"])
