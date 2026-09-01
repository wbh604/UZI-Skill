"""ValuationRenderer · 估值分位 · 对应 10_valuation."""
from __future__ import annotations

from .base import SectionRenderer, RenderContext


class ValuationRenderer(SectionRenderer):
    section_id = "valuation"
    section_title = "💹 估值水平"

    def render_full(self, ctx: RenderContext) -> str:
        d = ctx.data
        pe_ttm = d.get("pe_ttm") or "—"
        pb = d.get("pb") or "—"
        ps = d.get("ps_ttm") or d.get("ps") or "—"
        pe_pct = d.get("pe_percentile") or "—"
        pb_pct = d.get("pb_percentile") or "—"
        div_yield = d.get("dividend_yield") or d.get("dividend_yield_ttm")
        if div_yield is None and d.get("dividend_yield_status") == "unavailable":
            div_yield = "暂无可验证"
        div_yield = div_yield or "—"

        return f'''<section id="{self.section_id}">
  <h2>{self.section_title}</h2>
  <div class="valuation-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
    <div><div class="label">PE(TTM)</div><div class="value"><strong>{pe_ttm}</strong></div></div>
    <div><div class="label">PB</div><div class="value"><strong>{pb}</strong></div></div>
    <div><div class="label">PS(TTM)</div><div class="value">{ps}</div></div>
    <div><div class="label">PE 历史分位</div><div class="value">{pe_pct}</div></div>
    <div><div class="label">PB 历史分位</div><div class="value">{pb_pct}</div></div>
    <div><div class="label">股息率</div><div class="value">{div_yield}</div></div>
  </div>
</section>'''
