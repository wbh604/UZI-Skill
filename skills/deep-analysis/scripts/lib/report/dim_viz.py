"""report.dim_viz · 22 维数据卡的特化可视化 · v3.2 从 assemble_report.py 抽离.

### 内容
- `_score_class(score)` · 分数 → CSS class（great/good/ok/poor/bad/na）
- 19 个 `_viz_xxx(raw_data_of_dim)` · 每个维度的特化可视化
- `DIM_VIZ_RENDERERS` · dim_key → viz function 分发 dict

### 依赖
- `lib.report.svg_primitives` · SVG 图元 + COLOR_* 常量
- 这些 _viz 函数被 `assemble_report.render_dim_card` 调用

### 为什么搬出来
assemble_report.py 有 2964 行 · 其中 700+ 行是 _viz_xxx + 580 行是 SVG 图元 · 共占 43%.
v3.2 拆分后 assemble_report 只保留 shell 组装 + render_dim_card 框架.

### 向后兼容
assemble_report.py 做 `from lib.report.dim_viz import *` · 所有历史引用不变.
"""
from __future__ import annotations

from lib.report.svg_primitives import (
    COLOR_BULL, COLOR_BEAR, COLOR_GOLD, COLOR_CYAN,
    COLOR_BLUE, COLOR_PINK, COLOR_INDIGO, COLOR_MUTED, COLOR_GRID,
    svg_sparkline, svg_h_bar_compare, svg_donut, svg_gauge, svg_radar,
    svg_signal_lights, svg_supply_flow, svg_timeline, svg_bars,
    svg_candlestick, svg_pe_band, svg_progress_row, svg_peer_table,
    svg_unlock_timeline, svg_dividend_combo, svg_institutional_quarters,
    svg_thermometer,
)


def _safe(v, default="—"):
    """local _safe helper · 避免循环 import assemble_report."""
    if v is None or v == "" or v == "—":
        return default
    return v


def _score_class(score: int) -> str:
    if score is None:
        return "na"
    if score >= 7:
        return "high"
    if score >= 4:
        return "mid"
    return "low"


## ─── 维度专属可视化 dispatch ───

def _viz_chain(raw: dict) -> str:
    upstream = raw.get("upstream", "—")
    downstream = raw.get("downstream", "—")
    client_conc = raw.get("client_concentration", "")
    supplier_conc = raw.get("supplier_concentration", "")
    flow = svg_supply_flow(upstream, "本公司", downstream)

    extras = ""
    if client_conc or supplier_conc:
        extras = f'''<div style="display:flex;justify-content:space-around;margin-top:10px;padding:10px;background:#ffffff;border:1px solid #e2e8f0;border-radius:6px;font-family:Fira Code;font-size:11px;color:#475569">
  <span>🔧 供应商 <strong style="color:#0f172a">{supplier_conc}</strong></span>
  <span>🎯 大客户 <strong style="color:#0f172a">{client_conc}</strong></span>
</div>'''

    # 主营业务构成 pie
    main_biz = raw.get("main_business_breakdown", [])
    pie = ""
    if main_biz:
        COLORS = [COLOR_CYAN, COLOR_BLUE, COLOR_GOLD, COLOR_BULL, COLOR_INDIGO, COLOR_PINK]
        segments = []
        for i, item in enumerate(main_biz[:6]):
            name = item.get("name", "")
            value = item.get("value", 0)
            segments.append((name, value, COLORS[i % len(COLORS)]))
        if segments:
            pie = '<div style="margin-top:12px;padding-top:10px;border-top:1px solid #e2e8f0">'
            pie += '<div style="font-family:Fira Code;font-size:10px;color:#64748b;margin-bottom:8px">🥧 主营业务构成</div>'
            pie += svg_donut(segments, label="主营")
            pie += '</div>'

    return flow + extras + pie


def _viz_trap(raw: dict) -> str:
    import re
    hit_str = str(raw.get("signals_hit", "0/8"))
    m = re.search(r'(\d+)', hit_str)
    hit = int(m.group(1)) if m else 0
    level = raw.get("trap_level", "🟢 安全")
    lights = svg_signal_lights(hit, 8)
    return f'{lights}<div style="margin-top:10px;font-family:Fira Sans;font-size:14px;font-weight:700;color:#0f172a">{level}</div>'


def _viz_valuation(raw: dict) -> str:
    import re
    q_str = str(raw.get("pe_quantile", ""))
    m = re.search(r'(\d+)', q_str)
    val = int(m.group(1)) if m else 50
    color = COLOR_BULL if val < 30 else (COLOR_GOLD if val < 70 else COLOR_BEAR)
    pe = raw.get("pe", "—")
    industry_pe = raw.get("industry_pe", "—")
    dcf = raw.get("dcf", "—")

    # Gauge
    viz = f'<div style="text-align:center">{svg_gauge(val, 100, "PE 5 年分位数", color=color, unit="%")}</div>'

    # PE Band historical chart
    pe_hist = raw.get("pe_history", [])
    if pe_hist:
        viz += '<div style="margin-top:12px">'
        viz += '<div style="font-family:Fira Code;font-size:10px;color:#64748b;margin-bottom:4px">📉 PE 历史 Band · 红区=偏贵 / 黄区=合理 / 绿区=便宜</div>'
        viz += svg_pe_band(pe_hist, width=320, height=160)
        viz += '</div>'

    # KPI trio
    viz += f'''<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:12px;padding-top:10px;border-top:1px solid #e2e8f0;text-align:center">
  <div style="padding:8px;background:#ffffff;border:1px solid #e2e8f0;border-radius:6px">
    <div style="font-family:Fira Code;font-size:9px;color:#64748b">当前 PE</div>
    <div style="font-family:Fira Sans;font-size:16px;color:#0f172a;font-weight:700">{pe}</div>
  </div>
  <div style="padding:8px;background:#ffffff;border:1px solid #e2e8f0;border-radius:6px">
    <div style="font-family:Fira Code;font-size:9px;color:#64748b">行业均值</div>
    <div style="font-family:Fira Sans;font-size:16px;color:#0f172a;font-weight:700">{industry_pe}</div>
  </div>
  <div style="padding:8px;background:#ffffff;border:1px solid #e2e8f0;border-radius:6px">
    <div style="font-family:Fira Code;font-size:9px;color:#64748b">DCF 内在</div>
    <div style="font-family:Fira Sans;font-size:16px;color:#0f172a;font-weight:700">{dcf}</div>
  </div>
</div>'''

    # DCF sensitivity matrix if present
    dcf_matrix = raw.get("dcf_sensitivity", {})
    if dcf_matrix.get("waccs") and dcf_matrix.get("growths") and dcf_matrix.get("values"):
        waccs = dcf_matrix["waccs"]
        growths = dcf_matrix["growths"]
        values_matrix = dcf_matrix["values"]
        current_price = dcf_matrix.get("current_price", 0)
        viz += '<div style="margin-top:12px;padding-top:10px;border-top:1px solid #e2e8f0">'
        viz += '<div style="font-family:Fira Code;font-size:10px;color:#64748b;margin-bottom:6px">🧮 DCF 敏感度矩阵 (行=WACC, 列=增长率)</div>'
        viz += '<table style="width:100%;border-collapse:collapse;font-family:Fira Code;font-size:10px">'
        # header
        viz += '<tr><td></td>' + "".join(f'<td style="padding:4px;text-align:center;color:#64748b">{g}%</td>' for g in growths) + '</tr>'
        for ri, w in enumerate(waccs):
            viz += f'<tr><td style="padding:4px;color:#64748b">{w}%</td>'
            for ci, g in enumerate(growths):
                v = values_matrix[ri][ci] if ri < len(values_matrix) and ci < len(values_matrix[ri]) else 0
                rel = (v - current_price) / current_price if current_price else 0
                bg = COLOR_BULL if rel > 0.1 else (COLOR_GOLD if rel > -0.1 else COLOR_BEAR)
                viz += f'<td style="padding:4px;text-align:center;background:{bg};color:#fff;font-weight:700">{v:.1f}</td>'
            viz += '</tr>'
        viz += '</table>'
        viz += '</div>'

    return viz


def _viz_financials(raw: dict) -> str:
    """营收柱状 + 增速线 + ROE/净利趋势 + 分红历史 + 财务健康"""
    rev_hist = raw.get("revenue_history", [])
    roe_hist = raw.get("roe_history", [])
    np_hist = raw.get("net_profit_history", [])
    years = raw.get("financial_years", [f"{i}Y" for i in range(1, len(rev_hist) + 1)])

    # Part 1: revenue bars + growth rate overlay
    viz = ""
    if rev_hist:
        growth = []
        for i in range(len(rev_hist)):
            if i == 0:
                growth.append(0)
            else:
                growth.append(round((rev_hist[i] - rev_hist[i-1]) / rev_hist[i-1] * 100, 1) if rev_hist[i-1] else 0)
        viz += '<div style="font-family:Fira Code;font-size:10px;color:#64748b;margin-bottom:4px">📊 营收（亿）· 金线=同比增速 %</div>'
        viz += svg_bars(rev_hist, labels=years, color=COLOR_CYAN, overlay_line=growth, line_color=COLOR_GOLD, width=320, height=130)

    # Part 2: sparkline rows for ROE + net profit
    def _spark_row(label: str, values: list, unit: str, color: str) -> str:
        if not values or len(values) < 2:
            return ""
        last = values[-1]
        first = values[0]
        delta = last - first
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        dcolor = COLOR_BULL if delta > 0 else COLOR_BEAR if delta < 0 else COLOR_MUTED
        spark = svg_sparkline(values, width=150, height=30, color=color)
        return f'''<div style="display:flex;align-items:center;gap:10px;padding:6px 0;border-top:1px solid #f1f5f9">
  <div style="width:52px;font-family:Fira Code;font-size:10px;color:#64748b">{label}</div>
  <div style="flex:1">{spark}</div>
  <div style="font-family:Fira Code;font-size:11px;text-align:right;min-width:72px">
    <div style="color:#0f172a;font-weight:700">{last}{unit}</div>
    <div style="color:{dcolor};font-size:9px">{arrow} {abs(delta):.1f}</div>
  </div>
</div>'''
    viz += '<div style="margin-top:10px">'
    viz += _spark_row("ROE", roe_hist, "%", COLOR_BULL)
    viz += _spark_row("净利", np_hist, "亿", COLOR_GOLD)
    viz += '</div>'

    # Part 3: dividend history (if present)
    div_years = raw.get("dividend_years", [])
    div_amounts = raw.get("dividend_amounts", [])
    div_yields = raw.get("dividend_yields", [])
    if div_years and div_amounts:
        viz += '<div style="margin-top:12px;padding-top:10px;border-top:1px solid #e2e8f0">'
        viz += '<div style="font-family:Fira Code;font-size:10px;color:#64748b;margin-bottom:4px">💰 分红（元/10股）· 金线=股息率 %</div>'
        viz += svg_dividend_combo(div_years, div_amounts, div_yields, width=320, height=130)
        viz += '</div>'

    # Part 4: financial health progress bars
    health = raw.get("financial_health", {})
    if health:
        viz += '<div style="margin-top:12px;padding-top:10px;border-top:1px solid #e2e8f0">'
        viz += '<div style="font-family:Fira Code;font-size:10px;color:#64748b;margin-bottom:6px">💪 财务健康度</div>'
        for k, label, max_v, good_high in [
            ("current_ratio", "流动比率", 3.0, True),
            ("debt_ratio", "资产负债率 %", 100, False),
            ("fcf_margin", "现金流/净利 %", 150, True),
            ("roic", "ROIC %", 30, True),
        ]:
            v = health.get(k)
            if v is None:
                continue
            pct = min(100, v / max_v * 100)
            if not good_high:
                pct = 100 - pct
            color = COLOR_BULL if pct > 66 else COLOR_GOLD if pct > 33 else COLOR_BEAR
            viz += svg_progress_row(label, v, color=color, suffix="")
        viz += '</div>'

    if not viz:
        return f'<div style="color:#64748b;font-size:11px">{raw.get("roe", "—")} · {raw.get("net_margin", "—")} · {raw.get("revenue_growth", "—")}</div>'
    return viz


def _viz_kline(raw: dict) -> str:
    """Real SVG candlestick (60 days) with MA20/MA60 overlay"""
    candles = raw.get("candles_60d", [])
    ma20 = raw.get("ma20_60d", [])
    ma60 = raw.get("ma60_60d", [])
    closes = raw.get("close_60d", [])

    stage = raw.get("stage", "—")
    ma_align = raw.get("ma_align", "—")
    macd = raw.get("macd", "—")
    rsi = raw.get("rsi", "—")

    viz = ""
    if candles and len(candles) >= 10:
        viz += svg_candlestick(candles, width=340, height=200, ma_20=ma20, ma_60=ma60)
    elif closes:
        viz += svg_sparkline(closes, width=320, height=80, color=COLOR_BULL if closes[-1] > closes[0] else COLOR_BEAR)

    badges = f'''<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px">
  <span style="padding:4px 10px;background:#fef3c7;color:#d97706;border-radius:4px;font-family:Fira Code;font-size:11px;font-weight:600">{stage}</span>
  <span style="padding:4px 10px;background:#cffafe;color:#0891b2;border-radius:4px;font-family:Fira Code;font-size:11px;font-weight:600">MA {ma_align}</span>
  <span style="padding:4px 10px;background:#d1fae5;color:#059669;border-radius:4px;font-family:Fira Code;font-size:11px;font-weight:600">MACD {macd}</span>
  <span style="padding:4px 10px;background:#e0e7ff;color:#4f46e5;border-radius:4px;font-family:Fira Code;font-size:11px;font-weight:600">RSI {rsi}</span>'''
    # v3.8.0 · KDJ / OBV / Williams%R 副指标徽章 (参考 ashare-mcp 指标广度)
    _ind = raw.get("indicators") or {}
    _kj = _ind.get("kdj_j")
    if _kj is not None:
        _kc = "#dc2626" if _kj > 100 else ("#059669" if _kj < 0 else "#7c3aed")
        badges += (f'<span style="padding:4px 10px;background:#f3e8ff;color:{_kc};border-radius:4px;'
                   f'font-family:Fira Code;font-size:11px;font-weight:600">KDJ-J {_kj:.0f}</span>')
    _wr = _ind.get("williams_r")
    if _wr is not None:
        _wc = "#dc2626" if _wr > -20 else ("#059669" if _wr < -80 else "#64748b")
        badges += (f'<span style="padding:4px 10px;background:#f1f5f9;color:{_wc};border-radius:4px;'
                   f'font-family:Fira Code;font-size:11px;font-weight:600">W%R {_wr:.0f}</span>')
    if _ind.get("obv_trend_up") is not None:
        _ot = "OBV↑" if _ind.get("obv_trend_up") else "OBV↓"
        _oc = "#059669" if _ind.get("obv_trend_up") else "#dc2626"
        badges += (f'<span style="padding:4px 10px;background:#ecfdf5;color:{_oc};border-radius:4px;'
                   f'font-family:Fira Code;font-size:11px;font-weight:600">{_ot}</span>')
    badges += '</div>'

    # Bonus: volatility / beta / max drawdown if available
    stats = raw.get("kline_stats", {})
    if stats:
        stat_items = []
        for k, lbl in [("beta", "Beta"), ("volatility", "年化波动"), ("max_drawdown", "最大回撤"), ("ytd_return", "年初至今")]:
            if k in stats:
                stat_items.append(f'<div><div style="font-family:Fira Code;font-size:9px;color:#64748b">{lbl}</div><div style="font-family:Fira Code;font-size:12px;color:#0f172a;font-weight:700">{stats[k]}</div></div>')
        if stat_items:
            badges += f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px;padding-top:10px;border-top:1px solid #e2e8f0">{"".join(stat_items)}</div>'

    return viz + badges


def _viz_macro(raw: dict) -> str:
    items = [
        ("利率", raw.get("rate_cycle", "—"), "📉"),
        ("汇率", raw.get("fx_trend", "—"), "💱"),
        ("地缘", raw.get("geo_risk", "—"), "🌐"),
        ("大宗", raw.get("commodity", "—"), "📦"),
    ]
    cells = "".join(
        f'<div style="padding:10px;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;text-align:center">'
        f'<div style="font-size:18px;margin-bottom:4px">{ic}</div>'
        f'<div style="font-family:Fira Code;font-size:9px;color:#64748b;letter-spacing:.1em">{l}</div>'
        f'<div style="font-family:Fira Sans;font-size:11px;color:#0f172a;font-weight:600;margin-top:2px">{v}</div>'
        f'</div>'
        for l, v, ic in items
    )
    return f'<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:6px">{cells}</div>'


def _viz_peers(raw: dict) -> str:
    """Full peer valuation comparison table"""
    peer_table = raw.get("peer_table", [])
    viz = ""
    if peer_table:
        viz += '<div style="font-family:Fira Code;font-size:10px;color:#64748b;margin-bottom:6px">🏆 同业估值对比</div>'
        viz += svg_peer_table(peer_table)

    metrics = raw.get("peer_comparison", [])
    if metrics:
        viz += '<div style="margin-top:12px;padding-top:10px;border-top:1px solid #e2e8f0">'
        viz += '<div style="font-family:Fira Code;font-size:10px;color:#64748b;margin-bottom:6px">📊 关键指标 vs 行业均值</div>'
        for m in metrics[:4]:
            name = m.get("name", "")
            self_v = m.get("self", 0)
            peer_v = m.get("peer", 0)
            max_v = max(abs(self_v), abs(peer_v), 1)
            self_pct = abs(self_v) / max_v * 100
            peer_pct = abs(peer_v) / max_v * 100
            self_color = COLOR_BULL if self_v >= peer_v else COLOR_BEAR
            viz += f'''<div style="margin-bottom:10px">
  <div style="display:flex;justify-content:space-between;font-size:11px;color:#64748b;margin-bottom:4px">
    <span>{name}</span>
    <span><strong style="color:#0f172a">自己 {self_v}</strong> vs 行业 {peer_v}</span>
  </div>
  <div style="position:relative;height:10px;background:#f1f5f9;border-radius:5px">
    <div style="position:absolute;height:100%;width:{peer_pct}%;background:{COLOR_MUTED};border-radius:5px;opacity:.6"></div>
    <div style="position:absolute;height:100%;width:{self_pct}%;background:{self_color};border-radius:5px"></div>
  </div>
</div>'''
        viz += '</div>'
    return viz or '<div style="color:#94a3b8;font-size:11px">未获取同行数据</div>'


def _viz_research(raw: dict) -> str:
    """Donut for rating distribution + target price"""
    rating = str(raw.get("rating", ""))
    # parse "买入 18 / 增持 6 / 中性 2"
    import re
    buy_m = re.search(r'买入[\s·]*(\d+)', rating)
    overwt_m = re.search(r'增持[\s·]*(\d+)', rating)
    neu_m = re.search(r'中性[\s·]*(\d+)', rating)
    buy_n = int(buy_m.group(1)) if buy_m else 0
    overwt_n = int(overwt_m.group(1)) if overwt_m else 0
    neu_n = int(neu_m.group(1)) if neu_m else 0
    total = buy_n + overwt_n + neu_n
    if total == 0:
        return f'<div style="font-family:Fira Code;font-size:11px">{rating}</div>'
    donut = svg_donut([
        ("买入", buy_n, COLOR_BULL),
        ("增持", overwt_n, COLOR_CYAN),
        ("中性", neu_n, COLOR_MUTED),
    ], label=f"{total}家")
    target_avg = raw.get("target_avg", "—")
    upside = raw.get("upside", "—")
    tail = f'''<div style="display:flex;justify-content:space-between;margin-top:10px;padding:8px;background:#fef3c7;border-radius:6px">
  <span style="font-family:Fira Code;font-size:10px;color:#64748b">一致目标价</span>
  <span style="font-family:Fira Code;font-size:12px;color:#d97706;font-weight:700">{target_avg} ({upside})</span>
</div>'''
    return donut + tail


def _viz_industry(raw: dict) -> str:
    growth = raw.get("growth", "—")
    tam = raw.get("tam", "—")
    penetration = raw.get("penetration", "—")
    lifecycle = raw.get("lifecycle", "—")
    # parse growth pct
    import re
    m = re.search(r'(\d+)', str(growth))
    growth_val = int(m.group(1)) if m else 0
    gauge = svg_gauge(min(growth_val, 100), 100, "行业增速 %", color=COLOR_BULL if growth_val > 15 else COLOR_GOLD)
    tail = f'''<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px;text-align:center">
  <div style="padding:6px;background:#ffffff;border:1px solid #e2e8f0;border-radius:6px">
    <div style="font-family:Fira Code;font-size:9px;color:#64748b">TAM</div>
    <div style="font-family:Fira Sans;font-size:13px;font-weight:700;color:#0f172a">{tam}</div>
  </div>
  <div style="padding:6px;background:#ffffff;border:1px solid #e2e8f0;border-radius:6px">
    <div style="font-family:Fira Code;font-size:9px;color:#64748b">渗透率</div>
    <div style="font-family:Fira Sans;font-size:13px;font-weight:700;color:#0f172a">{penetration}</div>
  </div>
  <div style="padding:6px;background:#ffffff;border:1px solid #e2e8f0;border-radius:6px">
    <div style="font-family:Fira Code;font-size:9px;color:#64748b">周期</div>
    <div style="font-family:Fira Sans;font-size:11px;font-weight:700;color:#0f172a">{lifecycle}</div>
  </div>
</div>'''
    return f'<div style="text-align:center">{gauge}</div>{tail}'


def _viz_materials(raw: dict) -> str:
    core = raw.get("core_material", "—")
    trend_str = raw.get("price_trend", "—")
    cost_share = raw.get("cost_share", "—")
    import_dep = raw.get("import_dep", "—")
    trend_vals = raw.get("price_history_12m", [])
    spark_html = ""
    if trend_vals:
        color = COLOR_BULL if trend_vals[-1] < trend_vals[0] else COLOR_BEAR
        spark_html = svg_sparkline(trend_vals, width=260, height=48, color=color)
    return f'''{spark_html}
<div style="margin-top:8px;font-family:Fira Code;font-size:11px;line-height:1.9;color:#475569">
  <div>🔩 核心: <strong style="color:#0f172a">{core}</strong></div>
  <div>📉 12M: <strong style="color:#0f172a">{trend_str}</strong></div>
  <div>💰 成本占比: <strong style="color:#0f172a">{cost_share}</strong> · 🌍 进口依赖: <strong style="color:#0f172a">{import_dep}</strong></div>
</div>'''


def _viz_futures(raw: dict) -> str:
    linked = raw.get("linked_contract", "—")
    trend = raw.get("contract_trend", "—")
    return f'''<div style="padding:16px;text-align:center;background:#ffffff;border:1px dashed #cbd5e1;border-radius:8px">
  <div style="font-family:Fira Code;font-size:9px;color:#64748b;letter-spacing:.15em">LINKED CONTRACT</div>
  <div style="font-family:Fira Sans;font-size:16px;color:#0f172a;font-weight:700;margin-top:4px">{linked}</div>
  <div style="font-size:11px;color:#475569;margin-top:4px">{trend}</div>
</div>'''


def _viz_governance(raw: dict) -> str:
    # Parse pledge data (can be list of dicts or string)
    pledge_raw = raw.get("pledge", "—")
    if isinstance(pledge_raw, list) and pledge_raw:
        # Extract pledge ratio from first record
        first = pledge_raw[0] if isinstance(pledge_raw[0], dict) else {}
        ratio = first.get("质押比例", 0)
        pledge = f"质押比例 {ratio}%" if ratio else f"有 {len(pledge_raw)} 条质押记录"
    elif isinstance(pledge_raw, str):
        pledge = pledge_raw
    else:
        pledge = "—"

    # Parse insider trades
    insider_raw = raw.get("insider_trades_1y") or raw.get("insider", "—")
    if isinstance(insider_raw, list) and insider_raw:
        insider = f"近 1 年 {len(insider_raw)} 笔交易"
    elif isinstance(insider_raw, str) and insider_raw:
        insider = insider_raw
    else:
        insider = "暂无近期增减持"

    # Qualitative search results
    qual = raw.get("qualitative_search") or []
    related_tx = "已查询" if qual else "—"
    violations = "未发现" if qual else "—"

    def _badge(label, val, positive):
        color = COLOR_BULL if positive else COLOR_BEAR if positive is False else COLOR_GOLD
        bg = "#d1fae5" if positive else "#fee2e2" if positive is False else "#fef3c7"
        return f'''<div style="padding:10px 12px;background:{bg};border-left:3px solid {color};border-radius:0 8px 8px 0">
  <div style="font-family:Fira Code;font-size:9px;color:#64748b;letter-spacing:.1em">{label}</div>
  <div style="font-family:Fira Sans;font-size:13px;color:#0f172a;font-weight:700;margin-top:2px">{val}</div>
</div>'''
    low_pledge = isinstance(pledge_raw, list) and len(pledge_raw) > 0 and (isinstance(pledge_raw[0], dict) and pledge_raw[0].get("质押比例", 100) < 20)
    insider_positive = "增持" in str(insider) or "买入" in str(insider)
    no_violations = "未发现" in str(violations) or violations == "—"
    rows = _badge("实控人质押", pledge, low_pledge)
    rows += _badge("近12月增减持", insider, insider_positive)
    rows += _badge("关联交易/违规", violations, no_violations)
    return f'<div style="display:flex;flex-direction:column;gap:6px">{rows}</div>'


def _viz_capital_flow(raw: dict) -> str:
    """4 mini sparklines + 机构持仓变化 + 解禁时间表"""
    def _mini(label, values, summary, color):
        if not values or len(values) < 2:
            return f'''<div style="padding:10px;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px">
  <div style="font-family:Fira Code;font-size:9px;color:#64748b">{label}</div>
  <div style="font-family:Fira Code;font-size:12px;font-weight:700;color:#0f172a;margin-top:2px">{summary}</div>
</div>'''
        spark = svg_sparkline(values, width=120, height=34, color=color)
        return f'''<div style="padding:10px;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
    <span style="font-family:Fira Code;font-size:9px;color:#64748b">{label}</span>
    <strong style="font-family:Fira Code;font-size:10px;color:#0f172a">{summary}</strong>
  </div>
  {spark}
</div>'''
    # 北向已关停，用主力资金流向替代
    main_flow = raw.get("main_fund_flow_20d") or []
    main_values = [abs(float(r.get("主力净流入-净额", 0))) for r in main_flow[:20] if isinstance(r, dict)] if isinstance(main_flow, list) else []
    main_5d_summary = raw.get("main_5d", "—")
    if main_5d_summary == "—" and main_flow and isinstance(main_flow, list):
        recent = main_flow[:5]
        net = sum(float(r.get("主力净流入-净额", 0)) for r in recent if isinstance(r, dict))
        main_5d_summary = f"{'净流入' if net > 0 else '净流出'} {abs(net)/1e8:.1f}亿" if abs(net) > 0 else "—"

    # 大宗交易
    block = raw.get("block_trades_recent") or []
    block_summary = f"近期 {len(block)} 笔" if isinstance(block, list) and block else "无近期大宗"

    holders_hist = raw.get("holder_count_history") or []
    holders_vals = [r.get("股东户数-本次", 0) for r in holders_hist[:10] if isinstance(r, dict)] if isinstance(holders_hist, list) else []

    north = _mini("主力资金 20日", main_values, main_5d_summary, COLOR_CYAN)
    margin = _mini("大宗交易", [], block_summary, COLOR_BLUE)
    holders = _mini("股东户数", holders_vals, raw.get("holders_trend", "—"), COLOR_GOLD)
    main = _mini("融资余额", [], raw.get("margin_trend", "—") if raw.get("margin_trend") != "—" else "数据暂缺", COLOR_MUTED)

    viz = f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">{north}{margin}{holders}{main}</div>'

    # Institutional holdings over 8 quarters
    inst = raw.get("institutional_history", {})
    if inst.get("quarters"):
        viz += '<div style="margin-top:12px;padding-top:10px;border-top:1px solid #e2e8f0">'
        viz += '<div style="font-family:Fira Code;font-size:10px;color:#64748b;margin-bottom:4px">🏛 机构持仓变化（近 8 季）</div>'
        viz += svg_institutional_quarters(inst, width=320, height=120)
        viz += '</div>'

    # Future unlock timeline
    unlocks = raw.get("unlock_schedule", [])
    if unlocks:
        viz += '<div style="margin-top:12px;padding-top:10px;border-top:1px solid #e2e8f0">'
        viz += '<div style="font-family:Fira Code;font-size:10px;color:#64748b;margin-bottom:4px">🔓 未来 12 月解禁时间表（亿元）</div>'
        viz += svg_unlock_timeline(unlocks, width=320, height=110)
        viz += '</div>'

    return viz


def _viz_policy(raw: dict) -> str:
    items = [
        ("方向", raw.get("policy_dir", "—"), True),
        ("补贴", raw.get("subsidy", "—"), True),
        ("监管", raw.get("monitoring", "—"), None),
        ("反垄断", raw.get("anti_trust", "—"), None),
    ]
    cells = ""
    for label, val, positive in items:
        if val in ("—", "不适用", "无"):
            cells += f'<div style="padding:10px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px"><div style="font-family:Fira Code;font-size:9px;color:#94a3b8">{label}</div><div style="font-size:11px;color:#94a3b8;margin-top:2px">{val}</div></div>'
        else:
            color = COLOR_BULL if positive else COLOR_GOLD
            bg = "#d1fae5" if positive else "#fef3c7"
            cells += f'<div style="padding:10px;background:{bg};border:1px solid {color};border-radius:8px"><div style="font-family:Fira Code;font-size:9px;color:#64748b">{label}</div><div style="font-family:Fira Sans;font-size:11px;color:#0f172a;font-weight:600;margin-top:2px">{val}</div></div>'
    return f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">{cells}</div>'


def _viz_moat(raw: dict) -> str:
    """5-axis radar"""
    cats = {
        "intangible": "无形", "switching": "转换", "network": "网络",
        "scale": "规模", "efficient_scale": "有效规模",
    }
    values = []
    labels = []
    for k, lbl in cats.items():
        raw_v = raw.get(k, "")
        score = 5
        if isinstance(raw_v, (int, float)):
            score = float(raw_v)
        elif "强" in str(raw_v) or "高" in str(raw_v) or "最" in str(raw_v):
            score = 8
        elif "弱" in str(raw_v) or "低" in str(raw_v):
            score = 3
        elif raw_v and raw_v != "—":
            score = 6
        else:
            score = 2
        values.append(score)
        labels.append(lbl)
    while len(values) < 5:
        values.append(0); labels.append("—")
    radar = svg_radar(labels[:5], values[:5], max_val=10, size=180)
    tail = "".join(
        f'<div style="font-size:10px;color:#475569;padding:3px 0">• {k}: <strong style="color:#0f172a">{raw.get(k, "—")}</strong></div>'
        for k in ["intangible", "switching", "network", "scale"]
        if raw.get(k) and raw.get(k) != "—"
    )
    return f'<div style="text-align:center">{radar}</div><div style="margin-top:6px">{tail}</div>'


def _viz_events(raw: dict) -> str:
    events = raw.get("event_timeline", [])
    if not events:
        events = [v for v in [raw.get("recent_news"), raw.get("catalyst"), raw.get("earnings_preview")] if v and v != "—"]
    if not events:
        return '<div style="color:#94a3b8;font-size:11px">暂无事件</div>'
    return svg_timeline(events)


def _viz_lhb(raw: dict) -> str:
    matched = raw.get("youzi_matched", "")
    if isinstance(matched, str):
        matched_list = [m.strip() for m in matched.split("/") if m.strip()]
    else:
        matched_list = matched or []
    avatars_row = ""
    if matched_list:
        nick_to_id = {
            "章盟主": "zhang_mz", "孙哥": "sun_ge", "赵老哥": "zhao_lg",
            "佛山无影脚": "fs_wyj", "炒股养家": "yangjia", "陈小群": "chen_xq",
            "呼家楼": "hu_jl", "方新侠": "fang_xx", "作手新一": "zuoshou",
            "小鳄鱼": "xiao_ey", "交易猿": "jiao_yy", "毛老板": "mao_lb",
            "消闲派": "xiao_xian", "拉萨天团": "lasa", "成都帮": "chengdu",
            "苏南帮": "sunan", "宁波桑田路": "ningbo_st", "六一中路": "liuyi_zl",
            "流沙河": "liu_sh", "古北路": "gu_bl", "北京炒家": "bj_cj",
            "瑞鹤仙": "wang_zr", "鑫多多": "xin_dd",
        }
        cells = ""
        for nick in matched_list[:6]:
            inv_id = nick_to_id.get(nick, nick)
            cells += f'''<div style="display:flex;flex-direction:column;align-items:center;gap:3px">
  <img src="avatars/{inv_id}.svg" style="width:36px;height:36px;image-rendering:pixelated;border:2px solid #d97706;border-radius:6px;background:#fff">
  <span style="font-family:Fira Code;font-size:9px;color:#0f172a;font-weight:600">{nick}</span>
</div>'''
        avatars_row = f'<div style="display:flex;gap:8px;flex-wrap:wrap;padding:10px;background:#fef3c7;border-radius:8px;margin-bottom:10px">{cells}</div>'
    inst_vs = raw.get("inst_vs_youzi") or {}
    inst_net = inst_vs.get("institutional_net", 0) if isinstance(inst_vs, dict) else "—"
    youzi_net = inst_vs.get("youzi_net", 0) if isinstance(inst_vs, dict) else "—"
    inst_net = f"{inst_net/1e8:+.1f}亿" if isinstance(inst_net, (int, float)) and inst_net != 0 else "—"
    youzi_net = f"{youzi_net/1e8:+.1f}亿" if isinstance(youzi_net, (int, float)) and youzi_net != 0 else "—"
    lhb_30d = raw.get("lhb_count_30d") or "—"
    # balance bar
    import re
    def _parse(v):
        m = re.search(r'([+\-]?\d+\.?\d*)', str(v))
        return float(m.group(1)) if m else 0
    i = _parse(inst_net)
    y = _parse(youzi_net)
    total = abs(i) + abs(y) or 1
    i_pct = abs(i) / total * 100
    y_pct = abs(y) / total * 100
    balance = f'''<div>
  <div style="display:flex;justify-content:space-between;font-size:10px;margin-bottom:4px">
    <span style="color:#2563eb;font-weight:700">🏛 机构 {inst_net}</span>
    <span style="color:#d97706;font-weight:700">🐉 游资 {youzi_net}</span>
  </div>
  <div style="display:flex;height:10px;border-radius:5px;overflow:hidden;border:1px solid #e2e8f0">
    <div style="width:{i_pct}%;background:#2563eb"></div>
    <div style="width:{y_pct}%;background:#d97706"></div>
  </div>
  <div style="text-align:center;font-family:Fira Code;font-size:10px;color:#64748b;margin-top:6px">近 30 天上榜 <strong style="color:#0f172a">{lhb_30d}</strong></div>
</div>'''
    # If own LHB is empty, show sector LHB leaders
    sector_lhb = raw.get("sector_lhb_top50") or []
    sector_html = ""
    if (not matched_list) and isinstance(sector_lhb, list) and sector_lhb:
        rows = ""
        for r in sector_lhb[:5]:
            if isinstance(r, dict):
                name = r.get("名称", "—")
                date = str(r.get("最近上榜日", ""))[:10]
                reason = r.get("上榜原因", "—") if "上榜原因" in r else ""
                rows += f'<tr><td style="padding:4px 8px;font-size:12px;font-weight:600">{name}</td><td style="padding:4px 8px;font-size:11px;color:#6b7280">{date}</td><td style="padding:4px 8px;font-size:11px;color:#6b7280">{reason}</td></tr>'
        if rows:
            sector_html = f'''
            <div style="margin-top:10px;padding-top:8px;border-top:1px dashed #e2e8f0">
              <div style="font-size:10px;color:#94a3b8;margin-bottom:6px">📋 本股近期无龙虎榜 · 同板块龙虎榜 TOP 5:</div>
              <table style="width:100%;border-collapse:collapse;font-size:12px"><tbody>{rows}</tbody></table>
            </div>'''

    return avatars_row + balance + sector_html


def _viz_sentiment(raw: dict) -> str:
    import re
    heat_str = str(raw.get("xueqiu_heat", "50"))
    m = re.search(r'(\d+)', heat_str)
    heat_val = int(m.group(1)) if m else 50
    thermo = svg_thermometer(heat_val, 100, "雪球热度")
    big_v = raw.get("big_v_mentions", "—")
    positive = raw.get("positive_pct", "—")
    guba = raw.get("guba_volume", "—")
    tail = f'''<div style="flex:1;font-family:Fira Code;font-size:11px;line-height:1.8;color:#475569">
  <div>📣 <strong style="color:#0f172a">{big_v}</strong></div>
  <div>💬 股吧 <strong style="color:#0f172a">{guba}</strong></div>
  <div>😊 正面 <strong style="color:#059669">{positive}</strong></div>
</div>'''
    return f'<div style="display:flex;align-items:center;gap:14px">{thermo}{tail}</div>'


def _viz_contests(raw: dict) -> str:
    """Full drill-down list for 实盘赛 · every cube / mention clickable"""
    xq_cubes_list = raw.get("xq_cubes_list", [])
    tgb_list = raw.get("tgb_list", [])
    ths_list = raw.get("ths_list", [])

    xq_summary = raw.get("xq_cubes", "—")
    high_return = raw.get("high_return_cubes", "—")

    html = f'''<div style="padding:10px;background:#fef3c7;border:1px solid #d97706;border-radius:8px;margin-bottom:12px;display:flex;justify-content:space-around;text-align:center">
  <div><div style="font-family:Fira Sans;font-size:22px;font-weight:900;color:#d97706;line-height:1">{xq_summary}</div><div style="font-family:Fira Code;font-size:9px;color:#64748b;margin-top:2px">XUEQIU 组合</div></div>
  <div><div style="font-family:Fira Sans;font-size:22px;font-weight:900;color:#059669;line-height:1">{high_return}</div><div style="font-family:Fira Code;font-size:9px;color:#64748b;margin-top:2px">高收益 &gt;50%</div></div>
</div>'''

    # 雪球组合列表
    if xq_cubes_list:
        cube_rows = ""
        for c in xq_cubes_list[:30]:
            name = c.get("name", "")
            owner = c.get("owner", "")
            gain = c.get("total_gain", "")
            url = c.get("url", "")
            gain_color = COLOR_BULL if "+" in str(gain) or (isinstance(gain, (int, float)) and gain > 0) else COLOR_BEAR
            cube_rows += f'''<a href="{url}" target="_blank" rel="noopener" style="display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:#ffffff;border:1px solid #e2e8f0;border-radius:6px;text-decoration:none;margin-bottom:4px;transition:all .15s">
  <div style="min-width:0;flex:1">
    <div style="font-family:Fira Sans;font-size:12px;color:#0f172a;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name}</div>
    <div style="font-family:Fira Code;font-size:9px;color:#64748b">@{owner}</div>
  </div>
  <div style="font-family:Fira Code;font-size:13px;font-weight:700;color:{gain_color};margin-left:10px">{gain}</div>
</a>'''
        html += f'''<details open style="margin-bottom:10px">
  <summary style="cursor:pointer;font-family:Fira Code;font-size:10px;color:#0891b2;padding:4px 0;letter-spacing:.1em">▼ 雪球组合持仓 ({len(xq_cubes_list)} 个)</summary>
  <div style="max-height:280px;overflow-y:auto;padding-right:4px">{cube_rows}</div>
</details>'''

    if tgb_list:
        tgb_rows = ""
        for t in tgb_list[:20]:
            title = t.get("title", "")
            url = t.get("url", "")
            tgb_rows += f'<a href="{url}" target="_blank" rel="noopener" style="display:block;padding:6px 10px;background:#ffffff;border:1px solid #e2e8f0;border-radius:6px;text-decoration:none;margin-bottom:4px;font-size:11px;color:#1e293b">• {title}</a>'
        html += f'''<details style="margin-bottom:10px">
  <summary style="cursor:pointer;font-family:Fira Code;font-size:10px;color:#0891b2;padding:4px 0;letter-spacing:.1em">▼ 淘股吧讨论 ({len(tgb_list)} 条)</summary>
  <div style="max-height:220px;overflow-y:auto;padding-right:4px">{tgb_rows}</div>
</details>'''

    if ths_list:
        ths_rows = ""
        for p in ths_list[:20]:
            nickname = p.get("nickname", "")
            ret = p.get("return_pct", "")
            ths_rows += f'<div style="display:flex;justify-content:space-between;padding:6px 10px;background:#ffffff;border:1px solid #e2e8f0;border-radius:6px;margin-bottom:4px"><span style="font-size:11px;color:#1e293b">{nickname}</span><strong style="font-family:Fira Code;font-size:11px;color:#059669">+{ret}%</strong></div>'
        html += f'''<details>
  <summary style="cursor:pointer;font-family:Fira Code;font-size:10px;color:#0891b2;padding:4px 0;letter-spacing:.1em">▼ 同花顺模拟 ({len(ths_list)} 位)</summary>
  <div style="max-height:220px;overflow-y:auto;padding-right:4px">{ths_rows}</div>
</details>'''

    return html


DIM_VIZ_RENDERERS = {
    "1_financials":    _viz_financials,
    "2_kline":         _viz_kline,
    "3_macro":         _viz_macro,
    "4_peers":         _viz_peers,
    "5_chain":         _viz_chain,
    "6_research":      _viz_research,
    "7_industry":      _viz_industry,
    "8_materials":     _viz_materials,
    "9_futures":       _viz_futures,
    "10_valuation":    _viz_valuation,
    "11_governance":   _viz_governance,
    "12_capital_flow": _viz_capital_flow,
    "13_policy":       _viz_policy,
    "14_moat":         _viz_moat,
    "15_events":       _viz_events,
    "16_lhb":          _viz_lhb,
    "17_sentiment":    _viz_sentiment,
    "18_trap":         _viz_trap,
    "19_contests":     _viz_contests,
}

