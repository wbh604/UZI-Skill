"""report.institutional · 机构级建模渲染 · v3.2 从 assemble_report.py 抽离.

### 内容
- `trap_color_emoji(level)` · 杀猪盘风险级 → 颜色+emoji
- `_render_dcf_block(dim20)` · DCF 内在价值 + safety margin
- `_render_comps_block(dim20)` · 同行估值比较
- `_render_lbo_block(dim20)` · LBO IRR 分析
- `_render_initiating_coverage(dim21)` · 首次覆盖研报
- `_render_ic_memo(dim22)` · 投委会备忘录
- `_render_catalyst_calendar(dim21)` · 催化剂日历
- `_render_competitive_analysis(dim22)` · 竞争分析 (BCG/Porter)
- `_render_style_chip(syn)` · 股票风格 chip
- `_render_data_gap_banner(data_gaps)` · 数据缺口橙色 banner
- `_render_institutional_section(raw)` · 机构板块总入口

### 依赖
- `_safe` / `_score_class` · 局部 helper
- `lib.report.svg_primitives` · svg_gauge 等图元

### 为什么搬出来
这些是 assemble_report.py 后半部分的"深度分析"区块 · ~490 行独立内容 ·
与 render_dim_card 解耦 · 适合独立文件.

### 向后兼容
assemble_report.py 做 `from lib.report.institutional import *` · 调用不变.
"""
from __future__ import annotations

from lib.report.svg_primitives import (
    COLOR_BULL, COLOR_BEAR, COLOR_GOLD, COLOR_CYAN, COLOR_MUTED,
    svg_gauge, svg_progress_row, svg_radar,
    svg_sparkline,  # v3.3.2 · issue #50 修复 · institutional 块用了但 v3.2 拆分时漏 import
)
from lib.report.dim_viz import _score_class


def _safe(v, default="—"):
    """local helper · 避免循环 import assemble_report."""
    if v is None or v == "" or v == "—":
        return default
    return v


def trap_color_emoji(level: str) -> tuple[str, str]:
    if "🟢" in level or "安全" in level:
        return "green", "🟢"
    if "🟡" in level or "注意" in level:
        return "yellow", "🟡"
    if "🟠" in level or "警惕" in level:
        return "orange", "🟠"
    return "red", "🔴"



# ═══════════════════════════════════════════════════════════════
# v2.0 · Institutional Modeling Renderers (dim 20 / 21 / 22)
# ═══════════════════════════════════════════════════════════════

def _render_dcf_block(dim20: dict) -> str:
    """DCF methodology + WACC breakdown + sensitivity heatmap."""
    dcf = (dim20 or {}).get("dcf") or {}
    if not dcf or "intrinsic_per_share" not in dcf:
        return '<div class="dcf-block"><p class="muted">DCF 数据缺失</p></div>'

    wacc_info = dcf.get("wacc_breakdown", {}) or {}
    wacc_pct = wacc_info.get("wacc", 0) * 100
    ke_pct = wacc_info.get("cost_of_equity", 0) * 100
    kd_pct = wacc_info.get("after_tax_kd", 0) * 100

    intrinsic = dcf.get("intrinsic_per_share", 0)
    cur_px = dcf.get("current_price", 0)
    sm = dcf.get("safety_margin_pct", 0)
    verdict = dcf.get("verdict", "")

    # Methodology log
    log_items = "".join(f"<li>{l}</li>" for l in (dcf.get("methodology_log") or [])[:7])

    # Sensitivity heatmap 5x5
    sens = dcf.get("sensitivity_table") or {}
    wacc_axis = sens.get("wacc_axis") or []
    g_axis = sens.get("g_axis") or []
    values = sens.get("values_per_share") or []

    heat_rows = ""
    if values and wacc_axis and g_axis:
        header = "<tr><th></th>" + "".join(f"<th>g={g}</th>" for g in g_axis) + "</tr>"
        body = ""
        for i, row in enumerate(values):
            cells = ""
            for val in row:
                if cur_px > 0:
                    ratio = val / cur_px
                    if ratio >= 1.3:
                        color = "#065f46"; fg = "#fff"
                    elif ratio >= 1.1:
                        color = "#10b981"; fg = "#fff"
                    elif ratio >= 0.9:
                        color = "#e5e7eb"; fg = "#111"
                    elif ratio >= 0.7:
                        color = "#f97316"; fg = "#fff"
                    else:
                        color = "#b91c1c"; fg = "#fff"
                else:
                    color = "#e5e7eb"; fg = "#111"
                cells += f'<td style="background:{color};color:{fg};padding:6px 10px;text-align:center;font-weight:700">¥{val}</td>'
            body += f'<tr><th style="padding:6px 8px;background:#f3f4f6;font-size:12px">WACC {wacc_axis[i]}</th>{cells}</tr>'
        heat_rows = f'<table class="sens-heatmap" style="border-collapse:collapse;margin:12px 0;font-size:13px">{header}{body}</table>'

    sm_color = "#10b981" if sm > 10 else ("#f59e0b" if sm > -10 else "#ef4444")

    # TV 占比
    tv_pct = dcf.get("tv_pct_of_ev", 0)

    return f'''
    <div class="dcf-block" style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,0.06)">
      <div class="dcf-head" style="display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #06b6d4;padding-bottom:8px;margin-bottom:14px">
        <div>
          <span style="background:#06b6d4;color:#fff;padding:4px 10px;border-radius:4px;font-size:11px;font-weight:700;letter-spacing:1px">DCF VALUATION</span>
          <span style="margin-left:12px;font-size:14px;color:#6b7280">2-Stage FCF + Gordon Growth Terminal</span>
        </div>
        <div style="font-size:11px;color:#9ca3af">dim 20.dcf</div>
      </div>
      <div class="dcf-summary" style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:16px">
        <div><div style="font-size:11px;color:#6b7280">WACC</div><div style="font-size:22px;font-weight:800;color:#111">{wacc_pct:.2f}%</div><div style="font-size:10px;color:#9ca3af">k_e {ke_pct:.1f}% · k_d {kd_pct:.1f}%</div></div>
        <div><div style="font-size:11px;color:#6b7280">内在价值 / 股</div><div style="font-size:22px;font-weight:800;color:#111">¥{intrinsic}</div><div style="font-size:10px;color:#9ca3af">vs 当前 ¥{cur_px}</div></div>
        <div><div style="font-size:11px;color:#6b7280">安全边际</div><div style="font-size:22px;font-weight:800;color:{sm_color}">{sm:+.1f}%</div><div style="font-size:10px;color:#9ca3af">{verdict}</div></div>
        <div><div style="font-size:11px;color:#6b7280">终值占 EV</div><div style="font-size:22px;font-weight:800;color:#111">{tv_pct}%</div><div style="font-size:10px;color:#9ca3af">高度依赖 g</div></div>
      </div>
      <details style="margin-bottom:14px">
        <summary style="cursor:pointer;color:#0369a1;font-weight:600;font-size:13px">📐 计算推导（7 步）</summary>
        <ol style="margin:10px 0 0 20px;color:#374151;font-size:13px;line-height:1.8">{log_items}</ol>
      </details>
      <div>
        <div style="font-size:12px;color:#6b7280;margin-bottom:6px">📊 5×5 敏感性表（WACC × 终值 g）· 中心 = 基础案例</div>
        {heat_rows}
      </div>
    </div>
    '''


def _render_comps_block(dim20: dict) -> str:
    comps = (dim20 or {}).get("comps") or {}
    if not comps or "peer_stats" not in comps:
        return '<div class="comps-block"><p class="muted">Comps 同行数据缺失</p></div>'

    stats = comps.get("peer_stats") or {}
    target_pct = comps.get("target_percentile") or {}
    verdict = comps.get("valuation_verdict", "—")
    implied = comps.get("implied_price") or {}

    def _pct_color(p):
        if p <= 25: return "#10b981"
        if p <= 50: return "#06b6d4"
        if p <= 75: return "#f59e0b"
        return "#ef4444"

    metric_rows = ""
    for m in ("pe", "pb", "ps", "ev_ebitda", "roe", "net_margin"):
        s = stats.get(m)
        if not s: continue
        pct = target_pct.get(m, 50)
        bar = f'<div style="background:#e5e7eb;height:6px;border-radius:3px;overflow:hidden"><div style="background:{_pct_color(pct)};height:100%;width:{pct}%"></div></div>'
        metric_rows += f'''
        <tr>
          <td style="padding:8px;font-weight:600">{m.upper().replace("_", "-")}</td>
          <td style="padding:8px;text-align:right">{s.get("min", "—")}</td>
          <td style="padding:8px;text-align:right">{s.get("median", "—")}</td>
          <td style="padding:8px;text-align:right">{s.get("max", "—")}</td>
          <td style="padding:8px;text-align:center"><span style="color:{_pct_color(pct)};font-weight:700">{pct:.0f}%</span><br>{bar}</td>
        </tr>'''

    implied_rows = "".join(
        f'<div style="display:inline-block;margin-right:20px"><span style="color:#6b7280;font-size:11px">{k}</span><div style="font-size:20px;font-weight:800">¥{v}</div></div>'
        for k, v in implied.items()
    ) or '<span class="muted">—</span>'

    return f'''
    <div class="comps-block" style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,0.06)">
      <div style="display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #8b5cf6;padding-bottom:8px;margin-bottom:14px">
        <div>
          <span style="background:#8b5cf6;color:#fff;padding:4px 10px;border-radius:4px;font-size:11px;font-weight:700;letter-spacing:1px">COMPS</span>
          <span style="margin-left:12px;font-size:14px;color:#6b7280">同行对标 · 分位分析</span>
        </div>
        <div style="font-size:14px;font-weight:700">{verdict}</div>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead style="background:#f9fafb;color:#6b7280;font-size:11px;letter-spacing:0.5px">
          <tr><th style="padding:8px;text-align:left">METRIC</th><th style="padding:8px;text-align:right">MIN</th><th style="padding:8px;text-align:right">MEDIAN</th><th style="padding:8px;text-align:right">MAX</th><th style="padding:8px;text-align:center">目标分位</th></tr>
        </thead>
        <tbody>{metric_rows}</tbody>
      </table>
      <div style="margin-top:14px;padding-top:12px;border-top:1px dashed #e5e7eb">
        <div style="font-size:11px;color:#6b7280;margin-bottom:6px">隐含每股价（基于同行中位数倍数）</div>
        {implied_rows}
      </div>
    </div>
    '''


def _render_lbo_block(dim20: dict) -> str:
    lbo = (dim20 or {}).get("lbo") or {}
    if not lbo:
        return ""
    irr = lbo.get("irr_pct", 0)
    moic = lbo.get("moic", 0)
    verdict = lbo.get("verdict", "")
    debt_sched = lbo.get("debt_schedule", [])
    ebitda_path = lbo.get("ebitda_path", [])
    irr_color = "#10b981" if irr >= 20 else ("#f59e0b" if irr >= 15 else "#ef4444")

    ebitda_sparks = svg_sparkline(ebitda_path, width=220, height=40, color="#06b6d4") if ebitda_path else ""
    debt_sparks = svg_sparkline(debt_sched, width=220, height=40, color="#ef4444") if debt_sched else ""

    return f'''
    <div class="lbo-block" style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,0.06)">
      <div style="display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #f59e0b;padding-bottom:8px;margin-bottom:14px">
        <div>
          <span style="background:#f59e0b;color:#fff;padding:4px 10px;border-radius:4px;font-size:11px;font-weight:700;letter-spacing:1px">QUICK LBO</span>
          <span style="margin-left:12px;font-size:14px;color:#6b7280">PE 买方视角 · 5 年退出</span>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:16px">
        <div><div style="font-size:11px;color:#6b7280">入场 EBITDA</div><div style="font-size:20px;font-weight:800">{lbo.get("entry_ebitda_yi", 0)} 亿</div><div style="font-size:10px;color:#9ca3af">EV {lbo.get("entry_ev_yi", 0)} 亿</div></div>
        <div><div style="font-size:11px;color:#6b7280">杠杆倍数</div><div style="font-size:20px;font-weight:800">{lbo.get("leverage_turns", 0)}x</div><div style="font-size:10px;color:#9ca3af">债 {lbo.get("entry_debt_yi", 0)} 亿</div></div>
        <div><div style="font-size:11px;color:#6b7280">退出 IRR</div><div style="font-size:24px;font-weight:900;color:{irr_color}">{irr}%</div><div style="font-size:10px;color:#9ca3af">MOIC {moic}x</div></div>
        <div><div style="font-size:11px;color:#6b7280">结论</div><div style="font-size:14px;font-weight:700;color:{irr_color}">{verdict}</div></div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
        <div><div style="font-size:11px;color:#6b7280;margin-bottom:4px">5 年 EBITDA 路径</div>{ebitda_sparks}</div>
        <div><div style="font-size:11px;color:#6b7280;margin-bottom:4px">债务偿还进度</div>{debt_sparks}</div>
      </div>
    </div>
    '''


def _render_initiating_coverage(dim21: dict) -> str:
    ic = (dim21 or {}).get("initiating_coverage") or {}
    if not ic: return ""
    head = ic.get("headline") or {}
    rating = head.get("rating", "—")
    tp = head.get("target_price", 0)
    cur = head.get("current_price", 0)
    ups = head.get("upside_pct", 0)

    rating_color = "#10b981" if "买入" in rating or "增持" in rating else ("#f59e0b" if "持有" in rating else "#ef4444")
    pillars = ic.get("investment_thesis") or []
    risks = ic.get("key_risks") or []

    pillar_html = "".join(
        f'<li style="margin-bottom:8px"><strong>{p.get("pillar", "—")}</strong> <span style="background:#e0e7ff;color:#3730a3;padding:2px 6px;border-radius:3px;font-size:10px;margin-left:4px">{p.get("weight", "")}</span><br><span style="color:#6b7280;font-size:12px">{p.get("evidence", "")}</span></li>'
        for p in pillars[:5]
    )
    risk_html = "".join(
        f'<li style="margin-bottom:6px"><span style="color:#ef4444">●</span> <strong>{r.get("risk", "—")}</strong> <span style="color:#9ca3af;font-size:11px">({r.get("severity", "")})</span><br><span style="color:#6b7280;font-size:12px">{r.get("detail", "")}</span></li>'
        for r in risks[:5]
    )

    return f'''
    <div class="initiating-block" style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,0.06)">
      <div style="display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #0369a1;padding-bottom:8px;margin-bottom:14px">
        <div>
          <span style="background:#0369a1;color:#fff;padding:4px 10px;border-radius:4px;font-size:11px;font-weight:700;letter-spacing:1px">INITIATING COVERAGE</span>
          <span style="margin-left:12px;font-size:14px;color:#6b7280">机构首次覆盖 · JPM/GS/MS 格式</span>
        </div>
      </div>
      <div style="display:flex;gap:24px;margin-bottom:14px;padding:12px;background:#f9fafb;border-radius:8px">
        <div><div style="font-size:11px;color:#6b7280">RATING</div><div style="font-size:18px;font-weight:800;color:{rating_color}">{rating}</div></div>
        <div><div style="font-size:11px;color:#6b7280">TARGET</div><div style="font-size:18px;font-weight:800">¥{tp}</div></div>
        <div><div style="font-size:11px;color:#6b7280">CURRENT</div><div style="font-size:18px;font-weight:800">¥{cur}</div></div>
        <div><div style="font-size:11px;color:#6b7280">UPSIDE</div><div style="font-size:18px;font-weight:800;color:{rating_color}">{ups:+.1f}%</div></div>
      </div>
      <div style="padding:10px;background:#f0f9ff;border-left:3px solid #0369a1;margin-bottom:14px;font-size:13px;line-height:1.6">{ic.get("executive_summary", "")}</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
        <div>
          <div style="font-size:11px;color:#6b7280;font-weight:700;margin-bottom:8px">💪 INVESTMENT THESIS</div>
          <ul style="margin:0;padding-left:18px;font-size:13px">{pillar_html}</ul>
        </div>
        <div>
          <div style="font-size:11px;color:#6b7280;font-weight:700;margin-bottom:8px">⚠️ KEY RISKS</div>
          <ul style="margin:0;padding-left:18px;font-size:13px">{risk_html}</ul>
        </div>
      </div>
    </div>
    '''


def _render_ic_memo(dim22: dict) -> str:
    ic = (dim22 or {}).get("ic_memo") or {}
    sections = ic.get("sections") or {}
    exec_sum = sections.get("I_exec_summary") or {}
    scenarios = sections.get("VII_returns_scenarios") or []
    risks = sections.get("VI_risks_mitigants") or []

    if not sections: return ""

    headline = exec_sum.get("headline", "—")
    rec_color = "#10b981" if "🟢" in headline else ("#f59e0b" if "🟡" in headline else ("#6b7280" if "⚪" in headline else "#ef4444"))

    scen_html = ""
    for s in scenarios:
        ret = s.get("return_pct", 0)
        ret_color = "#10b981" if ret > 0 else "#ef4444"
        scen_html += f'''
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:10px">
          <div style="font-size:11px;color:#6b7280;font-weight:700">{s.get("scenario", "—")} · p={s.get("probability_pct", 0)}%</div>
          <div style="font-size:20px;font-weight:800;margin:4px 0">¥{s.get("price_target", 0)}</div>
          <div style="font-size:13px;font-weight:700;color:{ret_color}">{ret:+.1f}%</div>
          <div style="font-size:10px;color:#9ca3af;margin-top:4px">{s.get("assumptions", "")}</div>
        </div>'''

    risk_html = "".join(
        f'<li style="margin-bottom:6px"><strong>{r.get("risk", "—")}</strong> <span style="color:#ef4444;font-size:10px">({r.get("severity", "")})</span><br><span style="color:#6b7280;font-size:12px">{r.get("detail", "")}</span> · <span style="color:#059669;font-size:11px">缓解：{r.get("mitigant", "—")}</span></li>'
        for r in risks[:5]
    )

    return f'''
    <div class="ic-memo-block" style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,0.06)">
      <div style="display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #be123c;padding-bottom:8px;margin-bottom:14px">
        <div>
          <span style="background:#be123c;color:#fff;padding:4px 10px;border-radius:4px;font-size:11px;font-weight:700;letter-spacing:1px">IC MEMO</span>
          <span style="margin-left:12px;font-size:14px;color:#6b7280">投委会备忘录 · 8 章节</span>
        </div>
      </div>
      <div style="padding:14px;background:#fef2f2;border-left:4px solid {rec_color};margin-bottom:14px">
        <div style="font-size:11px;color:#6b7280;font-weight:700;margin-bottom:4px">RECOMMENDATION</div>
        <div style="font-size:18px;font-weight:800;color:{rec_color}">{headline}</div>
      </div>
      <div style="margin-bottom:14px">
        <div style="font-size:11px;color:#6b7280;font-weight:700;margin-bottom:8px">📊 三情景回报分析</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">{scen_html}</div>
      </div>
      <div>
        <div style="font-size:11px;color:#6b7280;font-weight:700;margin-bottom:8px">⚠️ 核心风险 + 缓解</div>
        <ul style="margin:0;padding-left:18px;font-size:13px">{risk_html}</ul>
      </div>
    </div>
    '''


def _render_catalyst_calendar(dim21: dict) -> str:
    cat = (dim21 or {}).get("catalyst_calendar") or {}
    events = cat.get("events") or []
    if not events: return ""

    def _impact_color(imp):
        return {"high": "#ef4444", "medium": "#f59e0b", "low": "#9ca3af", "past": "#6b7280"}.get(imp, "#9ca3af")

    items = ""
    for ev in events[:12]:
        imp = ev.get("impact", "low")
        items += f'''
        <div style="display:flex;padding:10px;border-bottom:1px solid #f3f4f6">
          <div style="min-width:90px;font-size:12px;color:#6b7280;font-family:Menlo,monospace">{ev.get("date", "—")[:10]}</div>
          <div style="width:8px;height:8px;border-radius:50%;background:{_impact_color(imp)};margin:6px 10px 0 0"></div>
          <div style="flex:1"><div style="font-size:13px;color:#111">{ev.get("event", "—")}</div>
            {'<div style="font-size:11px;color:#9ca3af">'+ev.get("expectation","")+'</div>' if ev.get("expectation") else ""}
          </div>
          <div style="font-size:10px;color:{_impact_color(imp)};font-weight:700;text-transform:uppercase">{imp}</div>
        </div>'''

    return f'''
    <div class="catalyst-block" style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,0.06)">
      <div style="display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #059669;padding-bottom:8px;margin-bottom:10px">
        <div>
          <span style="background:#059669;color:#fff;padding:4px 10px;border-radius:4px;font-size:11px;font-weight:700;letter-spacing:1px">CATALYST CALENDAR</span>
          <span style="margin-left:12px;font-size:14px;color:#6b7280">催化剂日历 · 影响分级</span>
        </div>
        <div style="font-size:11px;color:#9ca3af">共 {len(events)} 条 · {cat.get("high_impact_count", 0)} 高影响</div>
      </div>
      <div>{items}</div>
    </div>
    '''


def _render_competitive_analysis(dim22: dict) -> str:
    ca = (dim22 or {}).get("competitive_analysis") or {}
    porter = ca.get("porter_five_forces") or {}
    bcg = ca.get("bcg_position") or {}
    attr = ca.get("industry_attractiveness_pct", 0)

    if not porter: return ""

    # Porter radar via existing svg_radar
    force_labels = ["新进入者", "替代品", "供应商", "买方", "现有竞争"]
    force_values = [
        porter.get("new_entrants_threat", {}).get("score", 3),
        porter.get("substitutes_threat", {}).get("score", 3),
        porter.get("supplier_power", {}).get("score", 3),
        porter.get("buyer_power", {}).get("score", 3),
        porter.get("rivalry_intensity", {}).get("score", 3),
    ]
    radar = svg_radar(force_labels, force_values, max_val=5, size=200)

    bcg_cat = bcg.get("category", "—")
    bcg_color = {"Star (明星)": "#10b981", "Cash Cow (现金牛)": "#06b6d4", "Question Mark (问号)": "#f59e0b", "Dog (瘦狗)": "#9ca3af"}.get(bcg_cat, "#9ca3af")

    return f'''
    <div class="competitive-block" style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,0.06)">
      <div style="display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #7c3aed;padding-bottom:8px;margin-bottom:14px">
        <div>
          <span style="background:#7c3aed;color:#fff;padding:4px 10px;border-radius:4px;font-size:11px;font-weight:700;letter-spacing:1px">COMPETITIVE</span>
          <span style="margin-left:12px;font-size:14px;color:#6b7280">Porter 5 Forces + BCG Matrix</span>
        </div>
        <div style="font-size:12px;color:#6b7280">行业吸引力 <strong style="color:#111">{attr}%</strong></div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:center">
        <div style="text-align:center">{radar}</div>
        <div>
          <div style="font-size:11px;color:#6b7280;margin-bottom:6px">BCG 矩阵定位</div>
          <div style="font-size:22px;font-weight:800;color:{bcg_color};margin-bottom:8px">{bcg_cat}</div>
          <div style="font-size:12px;color:#374151;margin-bottom:4px">市场份额 {bcg.get("market_share_pct", 0)}% · 市场增速 {bcg.get("market_growth_pct", 0)}%</div>
          <div style="padding:10px;background:#faf5ff;border-left:3px solid {bcg_color};font-size:12px">战略建议：{bcg.get("strategic_action", "—")}</div>
        </div>
      </div>
    </div>
    '''


def _render_style_chip(syn: dict) -> str:
    """v2.7 · Render the style identification chip (动态加权说明)."""
    style = syn.get("detected_style")
    if not style:
        return ""
    label = syn.get("style_label_cn") or style
    explanation = syn.get("style_explanation") or ""
    diag = syn.get("style_diagnostics") or {}
    fund_old = diag.get("raw_fund_old", 0)
    fund_new = syn.get("fundamental_score", 0)
    cons_old = diag.get("raw_consensus_old", 0)
    cons_new = syn.get("panel_consensus", 0)

    def _delta(old, new):
        try:
            d = new - old
            if abs(d) < 0.05:
                return ""
            cls = "delta-up" if d > 0 else "delta-down"
            sign = "+" if d > 0 else ""
            return f' <span class="{cls}">({sign}{d:.1f})</span>'
        except (TypeError, ValueError):
            return ""

    compare = (
        f"fund {fund_old:.1f}→<strong>{fund_new:.1f}</strong>{_delta(fund_old, fund_new)} · "
        f"panel {cons_old:.1f}→<strong>{cons_new:.1f}</strong>{_delta(cons_old, cons_new)}"
    )

    return f'''<div class="style-chip-wrap">
  <span class="icon">🎯</span>
  <span class="label">本股识别为</span>
  <span class="value">{label}</span>
  <span class="hint">{explanation}</span>
  <span class="compare">{compare}</span>
</div>'''


def _render_data_gap_banner(data_gaps: dict | None) -> str:
    """v2.3 · Render orange banner listing data gaps. Returns empty string if no gaps.

    Reads synthesis.data_gaps which is populated in stage2() from _data_gaps.json
    (produced by data_integrity.generate_recovery_tasks). The banner tells readers
    upfront that the report has known holes — no silent fake numbers.
    """
    if not isinstance(data_gaps, dict) or not data_gaps.get("tasks"):
        return ""

    tasks = data_gaps["tasks"]
    total = len(tasks)
    unresolved = data_gaps.get("unresolved", total)
    ack = total - unresolved
    cov = data_gaps.get("coverage_pct", 0)

    # Build chip list — critical first, then optional, then enrichment
    order = {"critical": 0, "optional": 1, "enrichment": 2}
    sorted_tasks = sorted(tasks, key=lambda t: (order.get(t.get("severity"), 9), t.get("dim", "")))
    chips_html: list[str] = []
    for t in sorted_tasks[:20]:
        cls = "chip"
        if t.get("status") == "acknowledged":
            cls += " ack"
        chips_html.append(f'<span class="{cls}">{t.get("label","?")} · {t.get("dim","?")}</span>')
    chips_block = "\n      ".join(chips_html)
    overflow = ""
    if len(sorted_tasks) > 20:
        overflow = f'<span class="chip">+{len(sorted_tasks) - 20} 更多</span>'

    subtitle = (
        f"数据覆盖率 <strong>{cov}%</strong> · "
        f"共 <strong>{total}</strong> 个字段未从脚本采集到"
    )
    if ack:
        subtitle += f"（其中 <strong>{ack}</strong> 已由 agent 确认"
        subtitle += "真的拿不到）"

    hint = (
        "Agent 已尝试浏览器抓取 / MX API / WebSearch / 逻辑推导；"
        "划线字段为已确认无法补齐，其余字段显示为 “—”。"
    )

    return f'''<div class="data-gap-banner" role="alert">
  <div class="icon">⚠️</div>
  <div class="body">
    <div class="title">DATA QUALITY · 本报告存在已知数据缺口</div>
    <div class="subtitle">{subtitle}</div>
    <div class="list">
      {chips_block}
      {overflow}
    </div>
    <div class="hint">{hint}</div>
  </div>
</div>'''


def _render_institutional_section(raw: dict) -> str:
    """Combined dim 20/21/22 renderer — returns the full institutional modeling block."""
    dims = raw.get("dimensions", {}) or {}
    d20 = (dims.get("20_valuation_models") or {}).get("data") or {}
    d21 = (dims.get("21_research_workflow") or {}).get("data") or {}
    d22 = (dims.get("22_deep_methods") or {}).get("data") or {}

    if not (d20 or d21 or d22):
        return '<div class="muted" style="padding:20px;text-align:center;color:#9ca3af">Task 1.5 机构建模数据缺失 · 请运行 compute_deep_methods</div>'

    return (
        _render_dcf_block(d20) +
        _render_comps_block(d20) +
        _render_lbo_block(d20) +
        _render_initiating_coverage(d21) +
        _render_ic_memo(d22) +
        _render_catalyst_calendar(d21) +
        _render_competitive_analysis(d22)
    )

