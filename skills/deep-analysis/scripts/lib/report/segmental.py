"""report.segmental · 分业务收入模型 · v2.10 → v3.3 整合到 lib/report/.

### 内容

- `_render_segmental_block(ticker)` · 分业务卡片主入口 · 读 segmental_model.json
- `_render_segmental_projection_table(segments, currency)` · 3×3 三情景预测表
- `_svg_segment_donut(segments, total_rev, currency, size)` · 营收份额圆环
- `_svg_segment_projection(segments, rev_hist, width, height)` · 历史 + 3 情景预测线

### 数据源
- `segmental_model.json` · `lib/segmental_model.py::compute_segmental` 产出
- `segmental_validation.json` · 交叉校验
- `synthesis.json` · DCF cross-check

### 视觉特性 (v2.10+ 富数据扩充)
1. 毛利率 + 利润贡献徽章（每卡片顶部金属色条）
2. Segment sparkline（>=3 历史点）
3. 3×3 projection table（bull/base/bear × Y+1/Y+2/Y+3）
4. CAGR 徽章 v2 含端点值
5. DCF cross-check 徽章

### v3.3 整合记
原本在 feature/v2.10-segmental-revenue-model 分支 · v3.2 拆分时未合 ·
v3.3 cherry-pick 到 lib/report/segmental.py · 与 v3.2 架构对齐.

### 向后兼容
assemble_report.py 仍可 `from lib.report.segmental import _render_segmental_block`.
"""
from __future__ import annotations

import json
from pathlib import Path

from lib.cache import read_task_output
from lib.report.svg_primitives import (
    COLOR_BULL, COLOR_BEAR, COLOR_GOLD, COLOR_CYAN,
    COLOR_BLUE, COLOR_PINK, COLOR_INDIGO, COLOR_MUTED, COLOR_GRID,
)


def _safe(v, default="—"):
    if v is None or v == "" or v == "—":
        return default
    return v


def _render_segmental_block(ticker: str) -> str:
    """v2.10 · 分业务收入模型块.

    数据源: segmental_model.json + segmental_validation.json + synthesis.json

    视觉（v2.10+ 扩充版）:
      ┌─ 核心叙事 + 对账徽章 + Base 3Y + DCF cross-check ────────┐
      ├─ [Donut: 当前营收构成] · [Line: 历史+3情景预测]         ─┤
      ├─ [3 年数字预测表] 每 segment × 3 情景 × Y+1/Y+2/Y+3    ─┤
      └─ [卡片: driver + 毛利率 + 利润贡献 + sparkline 历史]   ─┘
    """
    from lib.cache import read_task_output
    model = read_task_output(ticker, "segmental_model")
    if not model or not model.get("segments"):
        return ""  # 未跑 → 整块不显示

    validation = read_task_output(ticker, "segmental_validation") or {}
    summary = validation.get("summary") or {}
    synthesis = read_task_output(ticker, "synthesis") or {}

    segments = model.get("segments") or []
    thesis = model.get("core_thesis") or model.get("thesis") or "—"
    total_rev = model.get("total_revenue_latest_yi", 0)
    rev_hist = model.get("total_revenue_history_yi") or []
    currency = model.get("currency", "CNY")

    # ═══ 对账徽章 + DCF cross-check ═══
    gap = summary.get("reconciliation_gap_pct", 0)
    base_3y = summary.get("base_3y_total_growth_pct", 0)
    passed = validation.get("passed", True)
    badge_color = "#059669" if passed and gap < 5 else ("#d97706" if passed else "#dc2626")
    badge_icon = "✓" if passed else "✗"
    badge_html = (
        f'<span style="background:{badge_color};color:#fff;padding:4px 10px;'
        f'border-radius:999px;font-size:11px;font-weight:700;letter-spacing:1px">'
        f'{badge_icon} 对账 gap {gap:.1f}%</span>'
    )
    # 换算 3Y CAGR (annualized)
    try:
        base_3y_cagr = ((1 + base_3y / 100) ** (1/3) - 1) * 100
    except Exception:
        base_3y_cagr = 0
    growth_badge = (
        f'<span style="background:#0891b2;color:#fff;padding:4px 10px;'
        f'border-radius:999px;font-size:11px;font-weight:700">'
        f'📈 Bottom-Up Base 3Y 总增速 {base_3y:+.1f}% (CAGR {base_3y_cagr:+.1f}%)</span>'
    )

    # DCF cross-check：自下而上 base vs 自上而下 DCF 隐含 CAGR
    dcf_cagr = None
    inst = synthesis.get("institutional_modeling") or {}
    # DCF 模型里 stage1_growth 如果有就用；否则估算
    dcf_d = ((synthesis.get("raw_data") or {}).get("dimensions") or {}).get("20_valuation_models") or {}
    d20 = dcf_d.get("data") or {}
    dcf_obj = d20.get("dcf") or {}
    assumptions = (dcf_obj.get("wacc_breakdown") or {}).get("assumptions") or dcf_obj.get("assumptions") or {}
    dcf_g1 = assumptions.get("stage1_growth") or assumptions.get("growth_5y")
    if dcf_g1 is not None:
        try:
            dcf_cagr = float(dcf_g1) * 100
        except (ValueError, TypeError):
            pass

    cross_check_badge = ""
    if dcf_cagr is not None:
        diff = abs(base_3y_cagr - dcf_cagr)
        if diff < 3:
            ic_color = "#059669"; ic_icon = "✓"; ic_verdict = "一致"
        elif diff < 6:
            ic_color = "#d97706"; ic_icon = "⚠"; ic_verdict = "小分歧"
        else:
            ic_color = "#dc2626"; ic_icon = "✗"; ic_verdict = "严重打架"
        cross_check_badge = (
            f'<span style="background:{ic_color};color:#fff;padding:4px 10px;'
            f'border-radius:999px;font-size:11px;font-weight:700">'
            f'🔀 {ic_icon} vs DCF 自上而下 {dcf_cagr:.1f}% · {ic_verdict}</span>'
        )

    # ═══ Donut: 当前营收构成 ═══
    donut_svg = _svg_segment_donut(segments, total_rev, currency, size=220)

    # ═══ Line chart: 历史 + 3 情景预测 ═══
    line_svg = _svg_segment_projection(segments, rev_hist, width=420, height=220)

    # ═══ 3 年 × 3 情景具体数字表 ═══
    projection_table = _render_segmental_projection_table(segments, currency)

    # ═══ 各 segment driver 卡片 (v2.10+ 含毛利/利润贡献/sparkline) ═══
    segment_cards = ""
    THESIS_ICONS = {
        "cash_cow": ("💰", "#059669", "稳定现金牛"),
        "growth_engine": ("🚀", "#0891b2", "成长引擎"),
        "declining": ("📉", "#dc2626", "衰退中"),
        "cyclical": ("🔄", "#d97706", "周期波动"),
        "turnaround": ("🔁", "#7c3aed", "困境反转"),
        "stable_cash_cow": ("💰", "#059669", "稳定现金牛"),
        "": ("❓", "#94a3b8", "未分类"),
    }
    for i, s in enumerate(segments, 1):
        name = _safe(s.get("name"), f"分段{i}")
        rev = s.get("latest_revenue_yi", 0)
        share = s.get("latest_share_pct", 0)
        drivers = s.get("drivers") or []
        tag = s.get("thesis_tag") or ""
        bull = s.get("bull_growth_3y_cagr")
        base = s.get("base_growth_3y_cagr")
        bear = s.get("bear_growth_3y_cagr")
        note = s.get("agent_note") or ""
        # v2.10 富字段
        gm = s.get("gross_margin_pct")
        profit_share = s.get("profit_share_pct")
        hist_rev = s.get("revenue_history_yi") or []
        hist_periods = s.get("history_periods") or []

        icon, color, tag_cn = THESIS_ICONS.get(tag, THESIS_ICONS[""])
        drivers_html = "".join(
            f'<span class="seg-driver">{d}</span>' for d in drivers[:5]
        ) or '<span class="seg-driver muted">（agent 未填 drivers）</span>'

        # 毛利率 + 利润贡献徽章
        margin_badges = ""
        if gm is not None:
            margin_color = "#059669" if gm >= 40 else ("#d97706" if gm >= 20 else "#dc2626")
            margin_badges += (
                f'<span class="seg-metric" style="color:{margin_color}">'
                f'毛利率 <strong>{gm:.1f}%</strong></span>'
            )
        if profit_share is not None and share:
            # 利润占比 vs 营收占比 对比：高于营收占比 = 高毛利段
            delta = profit_share - share
            if abs(delta) >= 2:
                sign = "+" if delta > 0 else ""
                delta_color = "#059669" if delta > 0 else "#dc2626"
                margin_badges += (
                    f'<span class="seg-metric" style="color:{delta_color}">'
                    f'利润贡献 {profit_share:.1f}% <small>({sign}{delta:.1f}pp vs 营收)</small></span>'
                )

        # 历史 sparkline (>= 3 点才画)
        sparkline_html = ""
        if len(hist_rev) >= 3:
            sparkline_html = (
                f'<div class="seg-spark">'
                f'<span class="spark-lbl">{hist_periods[0][:7]} → {hist_periods[-1][:7]}</span>'
                f'{svg_sparkline(hist_rev, width=160, height=32, color=color, fill=True)}'
                f'<span class="spark-val">{hist_rev[-1]:.0f}亿</span>'
                f'</div>'
            )

        cagr_row = ""
        if bull is not None and base is not None and bear is not None:
            # 3 年后的每一情景终点营收
            latest = rev
            bull_end = latest * ((1 + bull / 100) ** 3)
            base_end = latest * ((1 + base / 100) ** 3)
            bear_end = latest * ((1 + bear / 100) ** 3)
            cagr_row = (
                f'<div class="seg-cagr">'
                f'<div class="cagr-cell bull">'
                f'  <span class="lbl">Bull CAGR</span>'
                f'  <span class="val">{bull:+.1f}%</span>'
                f'  <span class="end">→ {bull_end:,.0f}</span>'
                f'</div>'
                f'<div class="cagr-cell base">'
                f'  <span class="lbl">Base CAGR</span>'
                f'  <span class="val">{base:+.1f}%</span>'
                f'  <span class="end">→ {base_end:,.0f}</span>'
                f'</div>'
                f'<div class="cagr-cell bear">'
                f'  <span class="lbl">Bear CAGR</span>'
                f'  <span class="val">{bear:+.1f}%</span>'
                f'  <span class="end">→ {bear_end:,.0f}</span>'
                f'</div>'
                f'</div>'
            )
        else:
            cagr_row = '<div class="muted" style="font-size:11px">（agent 未填 3 情景 CAGR）</div>'

        note_html = f'<div class="seg-note">💡 {note}</div>' if note else ""
        metrics_html = f'<div class="seg-metrics-row">{margin_badges}</div>' if margin_badges else ""

        segment_cards += (
            f'<div class="seg-card">'
            f'  <div class="seg-head">'
            f'    <span class="seg-icon" style="color:{color}">{icon}</span>'
            f'    <span class="seg-name">{name}</span>'
            f'    <span class="seg-tag" style="background:{color}20;color:{color}">{tag_cn}</span>'
            f'    <span class="seg-share">{share:.1f}%</span>'
            f'  </div>'
            f'  <div class="seg-rev">{currency} <strong>{rev:,.1f}</strong> 亿</div>'
            f'  {metrics_html}'
            f'  {sparkline_html}'
            f'  <div class="seg-drivers">{drivers_html}</div>'
            f'  {cagr_row}'
            f'  {note_html}'
            f'</div>'
        )

    # ═══ 溯源信息（底部小字） ═══
    source_notes = model.get("source_notes") or []
    src_line = " · ".join(str(n) for n in source_notes)
    warnings = validation.get("warnings") or []
    warn_line = ""
    if warnings:
        warn_line = (
            '<div class="seg-warnings">⚠ '
            + " · ".join(str(w) for w in warnings[:3])
            + '</div>'
        )

    return f'''
<div class="segmental-section">
  <div class="seg-section-header">
    <div class="seg-section-title">
      <div class="section-tag">SEGMENTAL · 分业务建模</div>
      <h3>{_safe(model.get("name"))} · 分业务收入 Build-Up</h3>
    </div>
    <div class="seg-badges">{badge_html} {growth_badge} {cross_check_badge}</div>
  </div>

  <div class="seg-thesis">
    <span class="lbl">CORE THESIS</span>
    <span class="txt">{thesis}</span>
  </div>

  <div class="seg-charts-grid">
    <div class="seg-chart-cell">
      <div class="seg-chart-title">当前营收构成 · {currency} {total_rev:,.1f} 亿</div>
      {donut_svg}
    </div>
    <div class="seg-chart-cell">
      <div class="seg-chart-title">历史 + 3 情景预测</div>
      {line_svg}
    </div>
  </div>

  {projection_table}

  <div class="seg-cards-grid">{segment_cards}</div>

  {warn_line}
  <div class="seg-source">数据来源 · {src_line}</div>
</div>
'''


def _render_segmental_projection_table(segments: list, currency: str) -> str:
    """v2.10 · 3 情景 × 3 年具体数字预测表 (不只 CAGR)."""
    if not segments:
        return ""

    # 对每个 segment 计算 Y+1/Y+2/Y+3 的具体营收（3 情景）
    rows_html = ""
    totals = {"bull": [0, 0, 0], "base": [0, 0, 0], "bear": [0, 0, 0]}
    for s in segments:
        name = s.get("name", "")
        rev = s.get("latest_revenue_yi", 0)
        bull = s.get("bull_growth_3y_cagr")
        base = s.get("base_growth_3y_cagr")
        bear = s.get("bear_growth_3y_cagr")
        if bull is None or base is None or bear is None:
            continue

        projections = {"bull": [], "base": [], "bear": []}
        for sc, cagr in [("bull", bull), ("base", base), ("bear", bear)]:
            for yr in (1, 2, 3):
                val = rev * ((1 + cagr / 100) ** yr)
                projections[sc].append(val)
                totals[sc][yr-1] += val

        rows_html += (
            f'<tr>'
            f'<td class="seg-tbl-name">{name}</td>'
            f'<td class="seg-tbl-cur">{rev:,.0f}</td>'
            + "".join(
                f'<td class="seg-tbl-val {sc}">{v:,.0f}</td>'
                for sc in ("bull", "base", "bear")
                for v in projections[sc]
            ) +
            '</tr>'
        )

    # Total 行
    if any(totals["base"]):
        total_row = (
            f'<tr class="seg-tbl-total">'
            f'<td class="seg-tbl-name"><strong>合计</strong></td>'
            f'<td class="seg-tbl-cur"><strong>{sum(s.get("latest_revenue_yi", 0) for s in segments):,.0f}</strong></td>'
            + "".join(
                f'<td class="seg-tbl-val {sc}"><strong>{v:,.0f}</strong></td>'
                for sc in ("bull", "base", "bear")
                for v in totals[sc]
            ) +
            '</tr>'
        )
    else:
        total_row = ""
        return ""  # 没有 CAGR 就不显示表

    if not rows_html:
        return ""

    return (
        '<div class="seg-projection-table-wrap">'
        '<div class="seg-chart-title">3 情景 × 3 年营收预测 · 单位 ' + currency + ' 亿</div>'
        '<table class="seg-projection-table">'
        '<thead>'
        '<tr>'
        '<th rowspan="2" class="seg-tbl-name">业务线</th>'
        '<th rowspan="2" class="seg-tbl-cur">当前</th>'
        '<th colspan="3" class="bull">Bull 🚀</th>'
        '<th colspan="3" class="base">Base 📊</th>'
        '<th colspan="3" class="bear">Bear 📉</th>'
        '</tr>'
        '<tr>'
        + "".join(f'<th class="{sc}">Y+{y}</th>' for sc in ("bull", "base", "bear") for y in (1, 2, 3))
        + '</tr>'
        '</thead>'
        '<tbody>' + rows_html + total_row + '</tbody>'
        '</table>'
        '</div>'
    )


def _svg_segment_donut(segments: list, total_rev: float, currency: str, size: int = 220) -> str:
    """Donut chart of revenue share per segment."""
    if not segments:
        return f'<svg width="{size}" height="{size}"></svg>'
    PALETTE = ["#0891b2", "#d97706", "#059669", "#7c3aed", "#dc2626", "#db2777", "#64748b"]
    cx = cy = size // 2
    r_outer = size // 2 - 12
    r_inner = r_outer - 28

    total_share = sum(s.get("latest_share_pct", 0) or 0 for s in segments) or 100
    paths = []
    labels = []
    start_angle = -90  # 12 点方向开始

    import math
    for i, s in enumerate(segments):
        share = s.get("latest_share_pct", 0) or 0
        angle = share / total_share * 360
        end_angle = start_angle + angle
        color = PALETTE[i % len(PALETTE)]

        # Arc path
        rad_start = math.radians(start_angle)
        rad_end = math.radians(end_angle)
        x1 = cx + r_outer * math.cos(rad_start)
        y1 = cy + r_outer * math.sin(rad_start)
        x2 = cx + r_outer * math.cos(rad_end)
        y2 = cy + r_outer * math.sin(rad_end)
        x3 = cx + r_inner * math.cos(rad_end)
        y3 = cy + r_inner * math.sin(rad_end)
        x4 = cx + r_inner * math.cos(rad_start)
        y4 = cy + r_inner * math.sin(rad_start)
        large = 1 if angle > 180 else 0
        path = (
            f'M {x1:.1f} {y1:.1f} '
            f'A {r_outer} {r_outer} 0 {large} 1 {x2:.1f} {y2:.1f} '
            f'L {x3:.1f} {y3:.1f} '
            f'A {r_inner} {r_inner} 0 {large} 0 {x4:.1f} {y4:.1f} Z'
        )
        paths.append(f'<path d="{path}" fill="{color}" opacity="0.88"><title>{s.get("name")} · {share:.1f}%</title></path>')

        # Label (only if >= 5%)
        if share >= 5:
            mid = math.radians((start_angle + end_angle) / 2)
            lx = cx + (r_outer + 8) * math.cos(mid)
            ly = cy + (r_outer + 8) * math.sin(mid)
            anchor = "start" if math.cos(mid) > 0.1 else ("end" if math.cos(mid) < -0.1 else "middle")
            labels.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
                f'font-size="10" fill="#374151" font-weight="600">{s.get("name")[:8]}</text>'
            )
        start_angle = end_angle

    center_text = (
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" font-size="13" fill="#111" font-weight="700">{len(segments)} 条</text>'
        f'<text x="{cx}" y="{cy + 12}" text-anchor="middle" font-size="10" fill="#64748b">业务线</text>'
    )

    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        + "".join(paths)
        + center_text
        + "".join(labels)
        + '</svg>'
    )


def _svg_segment_projection(segments: list, rev_hist: list, width: int = 420, height: int = 220) -> str:
    """Line chart: 历史总营收 + 3 情景 3 年预测（Bull/Base/Bear）."""
    if not segments or not rev_hist:
        return f'<svg width="{width}" height="{height}"></svg>'

    # 计算 3 年 projection
    latest_rev = rev_hist[-1]
    bull_sum_3y, base_sum_3y, bear_sum_3y = 0, 0, 0
    for s in segments:
        share = (s.get("latest_share_pct", 0) or 0) / 100
        bull_cagr = (s.get("bull_growth_3y_cagr") or 0) / 100
        base_cagr = (s.get("base_growth_3y_cagr") or 0) / 100
        bear_cagr = (s.get("bear_growth_3y_cagr") or 0) / 100
        # 按份额加权
        bull_sum_3y += share * ((1 + bull_cagr) ** 3)
        base_sum_3y += share * ((1 + base_cagr) ** 3)
        bear_sum_3y += share * ((1 + bear_cagr) ** 3)

    bull_3y_rev = latest_rev * bull_sum_3y
    base_3y_rev = latest_rev * base_sum_3y
    bear_3y_rev = latest_rev * bear_sum_3y

    # Build full timeline: 历史 N 年 + 未来 3 年
    n_hist = len(rev_hist)
    all_x = list(range(n_hist + 3))
    hist_y = list(rev_hist)

    # 3 条预测线从 latest 点分叉
    # 线性插值 Year+1 / +2 / +3（简化：假设年均复合）
    def project(cagr_3y_total: float) -> list[float]:
        # cagr_3y_total 是 3 年总倍数（e.g. 1.33 = +33%）
        yr_growth = cagr_3y_total ** (1/3)
        return [latest_rev * (yr_growth ** i) for i in range(1, 4)]
    bull_y = project(bull_sum_3y)
    base_y = project(base_sum_3y)
    bear_y = project(bear_sum_3y)

    all_y = hist_y + [max(bull_y[-1], base_y[-1], bear_y[-1])]
    ymin = min(all_y + hist_y + bear_y) * 0.9
    ymax = max(all_y + hist_y + bull_y) * 1.05
    span = max(ymax - ymin, 1e-6)

    pad = 40
    chart_w = width - pad - 20
    chart_h = height - pad - 20

    def sx(i): return pad + i / (len(all_x) - 1) * chart_w
    def sy(v): return pad + (1 - (v - ymin) / span) * chart_h

    # 历史线（灰）
    hist_pts = [f"{sx(i):.1f},{sy(y):.1f}" for i, y in enumerate(hist_y)]
    hist_path = "M " + " L ".join(hist_pts)

    # 三条未来线各自从 (n_hist-1, latest) 延伸
    def future_path(y_list: list[float]) -> str:
        start_idx = n_hist - 1
        pts = [f"{sx(start_idx):.1f},{sy(latest_rev):.1f}"]
        for j, y in enumerate(y_list, 1):
            pts.append(f"{sx(start_idx + j):.1f},{sy(y):.1f}")
        return "M " + " L ".join(pts)

    bull_path = future_path(bull_y)
    base_path = future_path(base_y)
    bear_path = future_path(bear_y)

    # Y 轴 gridlines
    grid = ""
    for frac in (0.25, 0.5, 0.75, 1.0):
        y = pad + frac * chart_h
        v = ymax - frac * span
        grid += (
            f'<line x1="{pad}" y1="{y:.1f}" x2="{width-20}" y2="{y:.1f}" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="2,2"/>'
            f'<text x="{pad-6}" y="{y:.1f}" text-anchor="end" font-size="9" fill="#94a3b8" dy="3">{v:.0f}</text>'
        )

    # X 轴 labels (历史年份 + 未来 Y+1/+2/+3)
    x_labels = ""
    for i in range(len(all_x)):
        if i < n_hist:
            lbl = f"T-{n_hist - 1 - i}" if i < n_hist - 1 else "T"
        else:
            lbl = f"T+{i - n_hist + 1}"
        x_labels += (
            f'<text x="{sx(i):.1f}" y="{height - 10}" text-anchor="middle" font-size="9" fill="#64748b">{lbl}</text>'
        )

    # Legend
    legend = (
        f'<g transform="translate({width - 120}, {pad - 22})">'
        f'<rect x="-4" y="-12" width="120" height="16" fill="#fff" opacity="0.8" rx="3"/>'
        f'<line x1="0" y1="0" x2="12" y2="0" stroke="#059669" stroke-width="2"/>'
        f'<text x="16" y="3" font-size="10" fill="#059669">Bull</text>'
        f'<line x1="40" y1="0" x2="52" y2="0" stroke="#d97706" stroke-width="2"/>'
        f'<text x="56" y="3" font-size="10" fill="#d97706">Base</text>'
        f'<line x1="80" y1="0" x2="92" y2="0" stroke="#dc2626" stroke-width="2"/>'
        f'<text x="96" y="3" font-size="10" fill="#dc2626">Bear</text>'
        f'</g>'
    )

    # End-point labels
    end_labels = (
        f'<text x="{sx(n_hist + 2) + 4:.1f}" y="{sy(bull_y[-1]):.1f}" font-size="10" fill="#059669" font-weight="700" dy="3">{bull_y[-1]:.0f}</text>'
        f'<text x="{sx(n_hist + 2) + 4:.1f}" y="{sy(base_y[-1]):.1f}" font-size="10" fill="#d97706" font-weight="700" dy="3">{base_y[-1]:.0f}</text>'
        f'<text x="{sx(n_hist + 2) + 4:.1f}" y="{sy(bear_y[-1]):.1f}" font-size="10" fill="#dc2626" font-weight="700" dy="3">{bear_y[-1]:.0f}</text>'
    )

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  {grid}
  <path d="{hist_path}" stroke="#64748b" stroke-width="2" fill="none"/>
  <path d="{bull_path}" stroke="#059669" stroke-width="2.5" fill="none" stroke-dasharray="5,3"/>
  <path d="{base_path}" stroke="#d97706" stroke-width="2.5" fill="none" stroke-dasharray="5,3"/>
  <path d="{bear_path}" stroke="#dc2626" stroke-width="2.5" fill="none" stroke-dasharray="5,3"/>
  {"".join(f'<circle cx="{sx(i):.1f}" cy="{sy(y):.1f}" r="3" fill="#64748b"/>' for i, y in enumerate(hist_y))}
  {x_labels}
  {legend}
  {end_labels}
</svg>'''

