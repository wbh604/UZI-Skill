"""FinancialsRenderer · 财务指标 section · 对应 1_financials."""
from __future__ import annotations

from .base import SectionRenderer, RenderContext


def _fmt_pct(v, default="—"):
    if v is None or v == "":
        return default
    if isinstance(v, str):
        return v
    try:
        return f"{float(v):.1f}%"
    except (ValueError, TypeError):
        return str(v) if v else default


class FinancialsRenderer(SectionRenderer):
    section_id = "financials"
    section_title = "📊 财务指标"

    def render_full(self, ctx: RenderContext) -> str:
        data = ctx.data
        roe = _fmt_pct(data.get("roe_ttm") or data.get("roe_latest"))
        roe_5y_min = _fmt_pct(data.get("roe_5y_min"))
        net_margin = _fmt_pct(data.get("net_margin"))
        gross_margin = _fmt_pct(data.get("gross_margin"))
        rev_growth = _fmt_pct(data.get("revenue_growth") or data.get("revenue_growth_yoy"))
        debt_ratio = _fmt_pct(data.get("debt_ratio") or data.get("asset_liability_ratio"))
        current_ratio = data.get("current_ratio") or "—"

        return f'''<section id="{self.section_id}">
  <h2>{self.section_title}</h2>
  <div class="fin-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
    <div class="fin-metric"><div class="label">ROE(近季)</div><div class="value"><strong>{roe}</strong></div></div>
    <div class="fin-metric"><div class="label">ROE 5年低</div><div class="value"><strong>{roe_5y_min}</strong></div></div>
    <div class="fin-metric"><div class="label">净利率</div><div class="value"><strong>{net_margin}</strong></div></div>
    <div class="fin-metric"><div class="label">毛利率</div><div class="value">{gross_margin}</div></div>
    <div class="fin-metric"><div class="label">营收增速</div><div class="value">{rev_growth}</div></div>
    <div class="fin-metric"><div class="label">资产负债率</div><div class="value">{debt_ratio}</div></div>
    <div class="fin-metric"><div class="label">流动比率</div><div class="value">{current_ratio}</div></div>
  </div>
</section>'''
