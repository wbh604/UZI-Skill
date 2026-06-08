"""组合再平衡 (portfolio rebalance) — 纯函数计算模块.

改编自 anthropics/financial-services wealth-management/portfolio-rebalance，
A 股适配:
  · 去掉 TLH (税损收割) — A 股个人无资本利得税，没有收割动机
  · 去掉 wash-sale / asset-location / 多账户税优 (IRA/Roth/401k) — A 股无此体系
  · 换手成本本地化 — A 股印花税 0.05% (2023-08 下调) + 双边佣金 ~0.025%；
    港股印花税 0.1%；美股极低 (按 0 估)。分市场标注。

聚焦三件事:
  ① 漂移 (drift): 当前权重 vs 目标权重，标出超阈值的持仓
  ② 交易清单 (trades): 把组合拉回目标的买入/卖出，含金额与估算股数
  ③ 换手成本 (turnover_cost): 双边交易成本，分市场拆解
  ④ 集中度 (concentration): 前 N 大集中度 + 行业分散 的再平衡前后变化

用户用法:
    from lib.tier1.rebalance import build_rebalance
    holdings = [
        {"ticker": "600519.SH", "weight": 0.40, "market": "A", "industry": "白酒"},
        {"ticker": "000858.SZ", "weight": 0.35, "market": "A", "industry": "白酒"},
        {"ticker": "00700.HK",  "weight": 0.25, "market": "HK", "industry": "互联网"},
    ]
    # targets=None → 默认等权；drift_threshold 默认 5 (个百分点)
    out = build_rebalance(holdings, targets=None, drift_threshold=5.0)

输入约定:
    holdings = [{ticker, weight, market, ...}]
        · weight: 0-1 小数 或 0-100 百分数（自动判别归一化）
        · market: "A" / "HK" / "US"（缺省按 ticker 后缀推断，再缺省按 A 股）
        · industry: 可选，用于行业分散度
        · value / market_value: 可选，组合总市值（用于把权重差换算成金额/股数）
        · price: 可选，个股现价（用于估算股数）
    targets:
        · None        → 等权目标 (1/N)
        · {ticker: w} → 显式目标权重（同样自动归一化）

返回 dict:
    {drift_table, trades, turnover_cost, concentration, summary, methodology_log}
"""
from __future__ import annotations

from typing import Any

# ─── 换手成本参数（分市场，双边）──────────────────────────────────
# 卖出印花税 (仅 A/HK 卖方单边) + 佣金 (双边)。美股印花税 0。
STAMP_DUTY = {
    "A": 0.0005,    # A 股印花税 0.05%，2023-08-28 起从 0.1% 下调，仅卖出
    "HK": 0.001,    # 港股印花税 0.1%，买卖双边各收（这里按单边率，买卖各算一次）
    "US": 0.0,      # 美股无印花税（SEC 费极小，忽略）
}
COMMISSION = {
    "A": 0.00025,   # A 股佣金 ~万 2.5（双边，最低 5 元此处不建模）
    "HK": 0.00025,  # 港股佣金近似
    "US": 0.0,      # 美股多为零佣金
}
MARKET_LABEL = {"A": "A 股", "HK": "港股", "US": "美股"}

DEFAULT_TOP_N = 3  # 前 N 大集中度


def _num(v, default=0.0) -> float:
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _infer_market(ticker: str, given: str | None) -> str:
    """market 缺省时按 ticker 推断 · 默认 A 股."""
    if given:
        g = str(given).strip().upper()
        if g in ("A", "CN", "SH", "SZ", "A股"):
            return "A"
        if g in ("HK", "港股"):
            return "HK"
        if g in ("US", "美股"):
            return "US"
    t = str(ticker).upper()
    if t.endswith(".HK") or (t.isdigit() and len(t) == 5):
        return "HK"
    if t.endswith(".US") or (t.replace(".", "").isalpha() and "." not in t.replace(".US", "")):
        # 纯字母 ticker (AAPL) 视为美股
        if t.replace(".US", "").isalpha():
            return "US"
    if t.endswith(".SH") or t.endswith(".SZ") or t.endswith(".BJ"):
        return "A"
    return "A"


def _normalize(weights: list[float]) -> list[float]:
    """权重归一化到 1.0；支持 0-100 百分数输入。"""
    vals = [max(0.0, _num(w)) for w in weights]
    total = sum(vals)
    if total <= 0:
        n = len(vals) or 1
        return [1.0 / n] * len(vals)
    # 若总和明显 > 1.5，判定为百分数（如 40/35/25），先 /100 再归一
    if total > 1.5:
        vals = [v / 100.0 for v in vals]
        total = sum(vals)
    return [v / total for v in vals]


def _resolve_targets(holdings: list[dict], targets: dict | None) -> list[float]:
    """计算每只持仓的目标权重（与 holdings 同序）。

    targets=None → 等权 1/N
    targets=dict → 按 ticker 取，缺失补 0，再整体归一化
    """
    n = len(holdings)
    if not targets:
        return [1.0 / n] * n
    raw = [_num(targets.get(h["ticker"]), default=0.0) for h in holdings]
    return _normalize(raw)


def _concentration(rows: list[dict], weight_key: str, top_n: int) -> dict:
    """前 N 大集中度 + 行业分散度（基于某个权重字段）。"""
    sorted_w = sorted((r[weight_key] for r in rows), reverse=True)
    top_n_sum = sum(sorted_w[:top_n])
    max_single = sorted_w[0] if sorted_w else 0.0

    # HHI（赫芬达尔指数，0-1，越高越集中）
    hhi = sum(w * w for w in sorted_w)

    # 行业分散
    ind_weight: dict[str, float] = {}
    for r in rows:
        ind = (r.get("industry") or "—").strip() or "—"
        ind_weight[ind] = ind_weight.get(ind, 0.0) + r[weight_key]
    top_industry = max(ind_weight.values()) if ind_weight else 0.0
    n_industries = len([k for k in ind_weight if k != "—"])

    return {
        "top_n": top_n,
        "top_n_weight": round(top_n_sum, 4),
        "max_single_weight": round(max_single, 4),
        "hhi": round(hhi, 4),
        "n_industries": n_industries,
        "top_industry_weight": round(top_industry, 4),
        "industry_breakdown": {k: round(v, 4) for k, v in
                               sorted(ind_weight.items(), key=lambda kv: -kv[1])},
    }


def build_rebalance(
    holdings: list[dict],
    targets: dict | None = None,
    drift_threshold: float = 5.0,
) -> dict:
    """组合再平衡分析（纯函数，无 IO）。

    参数:
        holdings: [{ticker, weight, market, industry?, value?, price?}, ...]
        targets:  {ticker: target_weight} 或 None（None → 等权）
        drift_threshold: 触发再平衡的漂移阈值，单位「百分点」(默认 5.0)

    返回:
        {drift_table, trades, turnover_cost, concentration, summary, methodology_log}
    """
    if not holdings:
        return {"error": "holdings 为空", "method": "Portfolio Rebalance"}

    n = len(holdings)

    # ── 归一化当前权重 ──
    cur_weights = _normalize([h.get("weight") for h in holdings])
    tgt_weights = _resolve_targets(holdings, targets)
    target_mode = "显式目标" if targets else f"等权 (1/{n})"

    # ── 组合总市值（用于金额/股数估算）──
    total_value = 0.0
    for h in holdings:
        total_value += _num(h.get("value") or h.get("market_value"))
    has_value = total_value > 0

    # ── 漂移表 ──
    drift_table: list[dict] = []
    for h, cw, tw in zip(holdings, cur_weights, tgt_weights):
        mkt = _infer_market(h["ticker"], h.get("market"))
        drift_pp = (cw - tw) * 100.0  # 漂移，单位百分点
        breached = abs(drift_pp) > drift_threshold
        delta_value = (tw - cw) * total_value if has_value else None  # 需买入(+)/卖出(-)金额
        drift_table.append({
            "ticker": h["ticker"],
            "market": mkt,
            "industry": (h.get("industry") or "—"),
            "current_weight": round(cw, 4),
            "target_weight": round(tw, 4),
            "drift_pp": round(drift_pp, 2),
            "abs_drift_pp": round(abs(drift_pp), 2),
            "breached": breached,
            "direction": ("超配→卖" if drift_pp > 0 else "低配→买" if drift_pp < 0 else "持平"),
            "delta_value": (round(delta_value, 2) if delta_value is not None else None),
        })

    breached_rows = [d for d in drift_table if d["breached"]]
    any_breach = len(breached_rows) > 0
    max_drift = max((d["abs_drift_pp"] for d in drift_table), default=0.0)

    # ── 交易清单（仅对超阈值持仓动手）──
    trades: list[dict] = []
    for d, h in zip(drift_table, holdings):
        if not d["breached"]:
            continue
        action = "SELL" if d["drift_pp"] > 0 else "BUY"
        amount = abs(d["delta_value"]) if d["delta_value"] is not None else None
        price = _num(h.get("price"))
        shares = None
        if amount is not None and price > 0:
            shares = int(amount / price)
            # A 股按手 (100 股) 取整
            if d["market"] == "A":
                shares = (shares // 100) * 100
        trades.append({
            "ticker": d["ticker"],
            "market": d["market"],
            "action": action,
            "action_cn": ("卖出" if action == "SELL" else "买入"),
            "weight_change_pp": round(tgt_weights[holdings.index(h)] * 100 - d["current_weight"] * 100, 2),
            "amount": (round(amount, 2) if amount is not None else None),
            "est_shares": shares,
            "reason": f"漂移 {d['drift_pp']:+.1f}pp 超阈值 {drift_threshold:.0f}pp",
        })

    # ── 换手成本估算（分市场拆解）──
    # 成本 = 交易额 × (卖方印花税? + 佣金)。买入无印花税(A/US)，HK 双边均收。
    cost_by_market: dict[str, dict] = {}
    total_cost = 0.0
    total_turnover = 0.0
    for t in trades:
        if t["amount"] is None:
            continue
        mkt = t["market"]
        amt = t["amount"]
        comm = COMMISSION.get(mkt, 0.0) * amt
        if mkt == "HK":
            stamp = STAMP_DUTY["HK"] * amt          # 港股买卖双边均收印花税
        elif t["action"] == "SELL":
            stamp = STAMP_DUTY.get(mkt, 0.0) * amt  # A 股仅卖出收印花税
        else:
            stamp = 0.0                              # A/US 买入无印花税
        leg_cost = comm + stamp
        agg = cost_by_market.setdefault(mkt, {
            "market_label": MARKET_LABEL.get(mkt, mkt),
            "turnover": 0.0, "stamp_duty": 0.0, "commission": 0.0, "total": 0.0,
        })
        agg["turnover"] += amt
        agg["stamp_duty"] += stamp
        agg["commission"] += comm
        agg["total"] += leg_cost
        total_cost += leg_cost
        total_turnover += amt

    for agg in cost_by_market.values():
        for k in ("turnover", "stamp_duty", "commission", "total"):
            agg[k] = round(agg[k], 2)

    turnover_cost = {
        "has_value_input": has_value,
        "total_turnover": round(total_turnover, 2),
        "total_cost": round(total_cost, 2),
        "cost_pct_of_turnover": (round(total_cost / total_turnover * 100, 4)
                                 if total_turnover > 0 else 0.0),
        "by_market": cost_by_market,
        "note": ("已按交易额估算；A 股卖出印花税 0.05%(2023-08 下调)+双边佣金~0.025%，"
                 "港股印花税 0.1%(双边)，美股印花税近 0。"
                 if has_value else
                 "未提供组合市值 (value/price)，仅给出权重漂移与交易方向，无法估算金额/成本。"),
    }

    # ── 集中度变化（前后对比）──
    cur_rows = [{"weight": cw, "industry": h.get("industry")}
                for h, cw in zip(holdings, cur_weights)]
    tgt_rows = [{"weight": tw, "industry": h.get("industry")}
                for h, tw in zip(holdings, tgt_weights)]
    conc_before = _concentration(cur_rows, "weight", DEFAULT_TOP_N)
    conc_after = _concentration(tgt_rows, "weight", DEFAULT_TOP_N)
    concentration = {
        "before": conc_before,
        "after": conc_after,
        "top_n_change_pp": round(
            (conc_after["top_n_weight"] - conc_before["top_n_weight"]) * 100, 2),
        "max_single_change_pp": round(
            (conc_after["max_single_weight"] - conc_before["max_single_weight"]) * 100, 2),
        "hhi_change": round(conc_after["hhi"] - conc_before["hhi"], 4),
    }

    # ── 美股税损一句话提示 ──
    has_us = any(d["market"] == "US" for d in drift_table)
    us_tlh_note = (
        "持仓含美股：美股有资本利得税，卖出端可另议税损收割 (TLH) 与持有期 (短期/长期)；"
        "A 股 / 港股个人无资本利得税，本工具不做 TLH。"
        if has_us else
        "A 股 / 港股个人无资本利得税，本工具不做税损收割 (TLH)，仅算漂移 + 风险 + 换手成本。"
    )

    # ── 结论 ──
    if not any_breach:
        verdict = f"🟢 无需再平衡 · 最大漂移 {max_drift:.1f}pp ≤ 阈值 {drift_threshold:.0f}pp"
    else:
        verdict = (f"🟡 建议再平衡 · {len(breached_rows)} 只超阈值 "
                   f"(最大漂移 {max_drift:.1f}pp) · {len(trades)} 笔交易")

    summary = {
        "n_holdings": n,
        "target_mode": target_mode,
        "drift_threshold_pp": drift_threshold,
        "any_breach": any_breach,
        "n_breached": len(breached_rows),
        "max_drift_pp": round(max_drift, 2),
        "n_trades": len(trades),
        "estimated_cost": round(total_cost, 2) if has_value else None,
        "verdict": verdict,
        "tlh_note": us_tlh_note,
    }

    return {
        "method": "Portfolio Rebalance (A股适配 · 去TLH)",
        "summary": summary,
        "drift_table": drift_table,
        "trades": trades,
        "turnover_cost": turnover_cost,
        "concentration": concentration,
        "methodology_log": [
            f"Step 1 · 归一化当前权重 ({n} 只) + 解析目标 ({target_mode})",
            f"Step 2 · 计算漂移 · 阈值 {drift_threshold:.0f}pp · "
            f"{len(breached_rows)} 只超标 (最大 {max_drift:.1f}pp)",
            f"Step 3 · 生成交易清单 {len(trades)} 笔 "
            + ("(已估金额/股数)" if has_value else "(仅方向，缺市值)"),
            f"Step 4 · 换手成本估算 "
            + (f"¥{total_cost:.0f} (占交易额 {turnover_cost['cost_pct_of_turnover']:.3f}%)"
               if has_value else "跳过 (无市值输入)"),
            f"Step 5 · 集中度变化 · 前{DEFAULT_TOP_N}大 "
            f"{conc_before['top_n_weight']*100:.1f}% → {conc_after['top_n_weight']*100:.1f}% "
            f"· HHI {concentration['hhi_change']:+.3f}",
            f"Step 6 · A 股无资本利得税 → 不做 TLH；"
            + ("美股部分可另议税损" if has_us else "纯 A/港股，无税损议题"),
        ],
    }


if __name__ == "__main__":
    import json
    demo = [
        {"ticker": "600519.SH", "weight": 0.40, "market": "A", "industry": "白酒",
         "value": 400000, "price": 1500},
        {"ticker": "000858.SZ", "weight": 0.35, "market": "A", "industry": "白酒",
         "value": 350000, "price": 150},
        {"ticker": "00700.HK", "weight": 0.25, "market": "HK", "industry": "互联网",
         "value": 250000, "price": 400},
    ]
    out = build_rebalance(demo, targets=None, drift_threshold=5.0)
    print(json.dumps(out, ensure_ascii=False, indent=2))
