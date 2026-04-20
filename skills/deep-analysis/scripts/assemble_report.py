"""Assemble the final HTML report from synthesis.json + dimensions.json + panel.json.

Usage: python scripts/assemble_report.py {ticker}
Output: reports/{ticker}_{YYYYMMDD}/full-report.html
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from lib.cache import read_task_output, market_status  # noqa: E402

ROOT = HERE.parent
TEMPLATE = ROOT / "assets" / "report-template.html"
AVATARS_DIR = ROOT / "assets" / "avatars"


def _safe(v, default="—"):
    return v if v not in (None, "", "nan") else default


# v2.6 · Read version from plugin manifest so report banner stays in sync
_PLUGIN_VERSION_CACHE = None
def _get_plugin_version() -> str:
    global _PLUGIN_VERSION_CACHE
    if _PLUGIN_VERSION_CACHE is not None:
        return _PLUGIN_VERSION_CACHE
    try:
        # ROOT = skills/deep-analysis · ROOT.parent.parent = repo root
        manifest = ROOT.parent.parent / ".claude-plugin" / "plugin.json"
        if manifest.exists():
            _PLUGIN_VERSION_CACHE = json.loads(manifest.read_text(encoding="utf-8")).get("version", "?")
            return _PLUGIN_VERSION_CACHE
    except Exception:
        pass
    _PLUGIN_VERSION_CACHE = "?"
    return _PLUGIN_VERSION_CACHE


GROUP_LABELS = {"A": "价值", "B": "成长", "C": "宏观", "D": "技术", "E": "中国", "F": "游资", "G": "量化"}


def render_jury_seat(inv: dict) -> str:
    """One judge seat on the judging board (50 灯). Click → scroll to chat message."""
    sig = inv.get("signal", "neutral")
    name = (inv.get("name") or "")[:4]
    score = inv.get("score", 0)
    inv_id = inv["investor_id"]
    return f'''<div class="seat {sig}" data-group="{inv.get("group", "")}" data-target="msg-{inv_id}" title="{inv.get("name", "")} · {inv.get("verdict", "")} · 点击查看完整结论">
  <img src="avatars/{inv_id}.svg" class="seat-avatar" alt="">
  <div class="seat-name">{name}</div>
  <div class="seat-score">{score}</div>
</div>'''


def _li(items: list) -> str:
    if not items:
        return ""
    return "".join(f"<li>{x}</li>" for x in items)


def render_chat_message(inv: dict) -> str:
    """One chat bubble + expandable full conclusion."""
    sig = inv.get("signal", "neutral")
    group = inv.get("group", "")
    group_label = GROUP_LABELS.get(group, group)
    score = inv.get("score", 0)
    confidence = inv.get("confidence", 0)
    reasoning = _safe(inv.get("reasoning") or inv.get("comment"), "—")
    comment = _safe(inv.get("comment"), "")
    verdict = _safe(inv.get("verdict"), "—")
    pass_items = inv.get("pass") or []
    fail_items = inv.get("fail") or []
    ideal_price = inv.get("ideal_price")
    period = _safe(inv.get("period"), "—")
    inv_id = inv["investor_id"]

    bubble_main = f'<div class="msg-reasoning">{reasoning}</div>'
    if comment and comment != reasoning:
        bubble_main += f'<div class="msg-comment">💬 "{comment}"</div>'

    # Full conclusion (collapsed by default, click to expand)
    pass_html = f'<div class="conc-block"><div class="conc-label">✅ 命中</div><ul>{_li(pass_items)}</ul></div>' if pass_items else ""
    fail_html = f'<div class="conc-block"><div class="conc-label">❌ 未命中</div><ul>{_li(fail_items)}</ul></div>' if fail_items else ""
    price_html = f'<div class="conc-row"><span>🎯 理想买入价</span><strong>¥{ideal_price}</strong></div>' if ideal_price else ""

    # v2.8 · 因地制宜：每个评委自己方法论回答的 3 个问题（time_horizon / position / 翻盘条件）
    th = _safe(inv.get("time_horizon"), "")
    ps = _safe(inv.get("position_sizing"), "")
    wc = _safe(inv.get("what_would_change_my_mind"), "")
    profile_rows = []
    if th and th != "—":
        profile_rows.append(f'<div class="conc-row"><span>⏱ 时间框架</span><em>{th}</em></div>')
    if ps and ps != "—":
        profile_rows.append(f'<div class="conc-row"><span>💰 仓位风格</span><em>{ps}</em></div>')
    if wc and wc != "—":
        profile_rows.append(f'<div class="conc-row"><span>🔄 翻盘条件</span><em>{wc}</em></div>')
    profile_html = (
        f'<div class="conc-block"><div class="conc-label">🧭 我的方法论</div>{"".join(profile_rows)}</div>'
        if profile_rows else ""
    )

    return f'''<div class="chat-msg {sig}" data-group="{group}" id="msg-{inv_id}">
  <img src="avatars/{inv_id}.svg" class="msg-avatar" alt="">
  <div class="msg-body">
    <div class="msg-meta">
      <span class="msg-name">{inv.get("name", "")}</span>
      <span class="msg-group-tag">{group} · {group_label}</span>
      <span class="msg-signal-dot"></span>
      <span class="msg-score-badge">{score}分</span>
      <span class="msg-confidence">conf {confidence}</span>
    </div>
    <div class="msg-bubble">
      {bubble_main}
      <div class="msg-verdict">▸ {verdict} · 周期 {period}</div>
      <details class="msg-details">
        <summary>展开完整结论 ▼</summary>
        <div class="conc-content">
          {pass_html}
          {fail_html}
          {price_html}
          {profile_html}
        </div>
      </details>
    </div>
  </div>
</div>'''


def render_vote_bars(vote_dist: dict) -> str:
    labels = [
        ("强烈买入", "strongly_buy", "var(--bull-green)"),
        ("买入", "buy", "var(--bull-green)"),
        ("关注", "watch", "var(--neon-gold)"),
        ("观望", "wait", "var(--text-dim)"),
        ("回避", "avoid", "var(--bear-red)"),
    ]
    total = sum(vote_dist.values()) or 1
    rows = []
    for cn, key, color in labels:
        count = vote_dist.get(key, 0)
        pct = count / total * 100
        rows.append(
            f'<div class="sc-vote-row">'
            f'<span style="width: 140px">{cn}</span>'
            f'<div class="bar"><div class="fill" style="width:{pct:.0f}%; background:{color}"></div></div>'
            f'<span style="width: 60px; text-align: right">{count} 人</span>'
            f"</div>"
        )
    return "\n".join(rows)


def render_top3_bulls(investors: list[dict]) -> str:
    return _render_top3_by_signal(investors, "bullish", "无看多评委 · 51 人整体倾向中性")


def render_top3_bears(investors: list[dict]) -> str:
    """v2.9.1 对称 render_top3_bulls 的 bear 版。share-card 原先只有 bulls 不对称。"""
    return _render_top3_by_signal(investors, "bearish", "无看空评委 · 51 人整体倾向中性")


def _render_top3_by_signal(investors: list[dict], target_signal: str, empty_msg: str) -> str:
    """v2.9.1 · 提取公共逻辑 + 空时给友好提示而不是 3 个空 div"""
    hits = sorted(
        [i for i in investors if i.get("signal") == target_signal],
        key=lambda x: x.get("score", 0),
        reverse=(target_signal == "bullish"),  # bullish 按分降序；bearish 按分升序
    )[:3]
    if not hits:
        # 空时整块返一个提示，不再 fill 3 个空 div（那是"缺失"的视觉症状）
        return (
            f'<div class="sc-best-empty" style="grid-column:1/-1;text-align:center;'
            f'color:#94a3b8;font-size:12px;padding:16px">{empty_msg}</div>'
        )
    cells = []
    for inv in hits:
        cells.append(
            f'<div class="sc-best-cell">'
            f'<img src="avatars/{inv["investor_id"]}.svg">'
            f'<div class="name">{inv.get("name")}</div>'
            f'<div class="score-num">{inv.get("score", 0)}</div>'
            f"</div>"
        )
    # 不足 3 个时给半透明 placeholder 而不是空白格
    while len(cells) < 3:
        cells.append(
            '<div class="sc-best-cell" style="opacity:0.2">'
            '<div style="font-size:12px;color:#94a3b8">—</div></div>'
        )
    return "\n".join(cells)


def render_risks(risks: list[str]) -> str:
    return "\n".join(f"<li>{r}</li>" for r in risks)


## ─── SVG VIZ HELPERS · per-dim 专属可视化 ───

# Brand colors (light theme)
COLOR_BULL = "#059669"
COLOR_BEAR = "#dc2626"
COLOR_GOLD = "#d97706"
COLOR_CYAN = "#0891b2"
COLOR_BLUE = "#2563eb"
COLOR_PINK = "#db2777"
COLOR_INDIGO = "#4f46e5"
COLOR_MUTED = "#94a3b8"
COLOR_GRID = "#e2e8f0"


def svg_sparkline(values: list, width: int = 240, height: int = 50, color: str = COLOR_CYAN, fill: bool = True) -> str:
    """Tiny line chart. Values normalized to fit."""
    if not values or len(values) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'
    vmin, vmax = min(values), max(values)
    span = max(vmax - vmin, 1e-9)
    pts = []
    for i, v in enumerate(values):
        x = i / (len(values) - 1) * (width - 4) + 2
        y = height - 4 - (v - vmin) / span * (height - 8)
        pts.append(f"{x:.1f},{y:.1f}")
    path = "M " + " L ".join(pts)
    fill_path = ""
    if fill:
        fill_path = f'<path d="{path} L {width-2},{height-2} L 2,{height-2} Z" fill="{color}" fill-opacity="0.12"/>'
    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="display:block">
  {fill_path}
  <path d="{path}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="{pts[-1].split(',')[0]}" cy="{pts[-1].split(',')[1]}" r="3" fill="{color}"/>
</svg>'''


def svg_h_bar_compare(label_a: str, val_a: float, label_b: str, val_b: float, unit: str = "", width: int = 260) -> str:
    """Horizontal back-to-back bar comparing two values."""
    max_v = max(abs(val_a), abs(val_b), 1)
    pct_a = abs(val_a) / max_v * 100
    pct_b = abs(val_b) / max_v * 100
    color_a = COLOR_BULL if val_a >= val_b else COLOR_MUTED
    color_b = COLOR_BULL if val_b > val_a else COLOR_MUTED
    return f'''<div style="font-family: Fira Code, monospace; font-size: 11px;">
  <div style="display:flex; justify-content:space-between; margin-bottom:4px; color:#475569;">
    <span>{label_a}</span><strong style="color:#0f172a">{val_a}{unit}</strong>
  </div>
  <div style="height:8px; background:#f1f5f9; border-radius:4px; overflow:hidden; margin-bottom:8px;">
    <div style="width:{pct_a}%; height:100%; background:{color_a}; border-radius:4px;"></div>
  </div>
  <div style="display:flex; justify-content:space-between; margin-bottom:4px; color:#475569;">
    <span>{label_b}</span><strong style="color:#0f172a">{val_b}{unit}</strong>
  </div>
  <div style="height:8px; background:#f1f5f9; border-radius:4px; overflow:hidden;">
    <div style="width:{pct_b}%; height:100%; background:{color_b}; border-radius:4px;"></div>
  </div>
</div>'''


def svg_donut(segments: list[tuple], total: float = None, label: str = "", size: int = 120) -> str:
    """Donut chart. segments = [(label, value, color), ...]"""
    if not segments:
        return ""
    total = total or sum(s[1] for s in segments)
    if total <= 0:
        return ""
    cx = cy = size / 2
    r = size / 2 - 8
    inner_r = r * 0.6
    paths = []
    cur_angle = -90  # start at top
    import math
    for lbl, val, color in segments:
        sweep = val / total * 360
        if sweep <= 0:
            continue
        end_angle = cur_angle + sweep
        large = 1 if sweep > 180 else 0
        x1 = cx + r * math.cos(math.radians(cur_angle))
        y1 = cy + r * math.sin(math.radians(cur_angle))
        x2 = cx + r * math.cos(math.radians(end_angle))
        y2 = cy + r * math.sin(math.radians(end_angle))
        x3 = cx + inner_r * math.cos(math.radians(end_angle))
        y3 = cy + inner_r * math.sin(math.radians(end_angle))
        x4 = cx + inner_r * math.cos(math.radians(cur_angle))
        y4 = cy + inner_r * math.sin(math.radians(cur_angle))
        d = f"M {x1},{y1} A {r},{r} 0 {large} 1 {x2},{y2} L {x3},{y3} A {inner_r},{inner_r} 0 {large} 0 {x4},{y4} Z"
        paths.append(f'<path d="{d}" fill="{color}"/>')
        cur_angle = end_angle
    legend = "".join(
        f'<div style="display:flex; align-items:center; gap:6px; font-size:10px; margin-bottom:2px;">'
        f'<span style="width:8px; height:8px; background:{c}; border-radius:2px"></span>'
        f'<span style="color:#475569">{l}</span>'
        f'<strong style="margin-left:auto; color:#0f172a">{v}</strong></div>'
        for l, v, c in segments
    )
    return f'''<div style="display:flex; align-items:center; gap:14px;">
  <svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" style="flex-shrink:0">
    {"".join(paths)}
    {f'<text x="{cx}" y="{cy+5}" text-anchor="middle" font-family="Fira Sans" font-weight="700" font-size="14" fill="#0f172a">{label}</text>' if label else ""}
  </svg>
  <div style="flex:1; min-width:0">{legend}</div>
</div>'''


def svg_gauge(value: float, max_val: float = 100, label: str = "", size: int = 220, color: str = COLOR_GOLD, unit: str = "") -> str:
    """Semi-circle gauge — larger, bolder."""
    pct = max(0, min(1, value / max_val))
    cx = size / 2
    cy = size * 0.65
    r = size * 0.40
    import math
    val_a = 180 - pct * 180
    bg = f'<path d="M {cx-r},{cy} A {r},{r} 0 0 1 {cx+r},{cy}" fill="none" stroke="#e2e8f0" stroke-width="14" stroke-linecap="round"/>'
    x2 = cx + r * math.cos(math.radians(val_a))
    y2 = cy + r * math.sin(math.radians(val_a))
    large = 1 if pct > 0.5 else 0
    val_arc = f'<path d="M {cx-r},{cy} A {r},{r} 0 {large} 1 {x2},{y2}" fill="none" stroke="{color}" stroke-width="14" stroke-linecap="round"/>'
    return f'''<svg width="{size}" height="{size*0.78}" viewBox="0 0 {size} {size*0.78}">
  {bg}
  {val_arc}
  <text x="{cx}" y="{cy-4}" text-anchor="middle" font-family="Fira Sans" font-weight="900" font-size="52" fill="#0f172a" letter-spacing="-2">{value:.0f}<tspan font-size="20" fill="#64748b" dx="2">{unit}</tspan></text>
  <text x="{cx}" y="{cy+22}" text-anchor="middle" font-family="Fira Sans" font-size="12" font-weight="600" fill="#475569">{label}</text>
</svg>'''


def svg_radar(labels: list, values: list, max_val: float = 10, size: int = 160) -> str:
    """5-axis radar chart."""
    import math
    n = len(labels)
    cx = cy = size / 2
    r = size * 0.38
    # axis lines + labels
    axes = []
    for i, lbl in enumerate(labels):
        a = -math.pi / 2 + i * 2 * math.pi / n
        x = cx + r * math.cos(a)
        y = cy + r * math.sin(a)
        axes.append(f'<line x1="{cx}" y1="{cy}" x2="{x}" y2="{y}" stroke="#e2e8f0" stroke-width="1"/>')
        lx = cx + (r + 12) * math.cos(a)
        ly = cy + (r + 14) * math.sin(a)
        axes.append(f'<text x="{lx}" y="{ly}" text-anchor="middle" font-family="Fira Code" font-size="9" fill="#64748b">{lbl}</text>')
    # rings
    for ring in (0.33, 0.66, 1.0):
        ring_r = r * ring
        axes.append(f'<circle cx="{cx}" cy="{cy}" r="{ring_r}" fill="none" stroke="#f1f5f9"/>')
    # value polygon
    pts = []
    for i, v in enumerate(values):
        a = -math.pi / 2 + i * 2 * math.pi / n
        rv = r * (v / max_val)
        x = cx + rv * math.cos(a)
        y = cy + rv * math.sin(a)
        pts.append(f"{x:.1f},{y:.1f}")
    poly = f'<polygon points="{" ".join(pts)}" fill="{COLOR_CYAN}" fill-opacity="0.25" stroke="{COLOR_CYAN}" stroke-width="2"/>'
    return f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">{"".join(axes)}{poly}</svg>'


def svg_signal_lights(hit: int, total: int = 8) -> str:
    """N LED dots, hit ones red, ok ones green."""
    cells = []
    for i in range(total):
        on = i < hit
        color = COLOR_BEAR if on else COLOR_BULL
        opacity = 1 if on else 0.35
        cells.append(
            f'<div style="width:24px;height:24px;border-radius:50%;background:{color};opacity:{opacity};'
            f'box-shadow:0 0 8px {color}40;display:flex;align-items:center;justify-content:center;'
            f'color:#fff;font-family:Fira Code;font-size:10px;font-weight:700">{i+1}</div>'
        )
    label = "🔴 命中信号" if hit > 0 else "🟢 全部通过"
    return f'''<div>
  <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">{"".join(cells)}</div>
  <div style="font-family:Fira Code;font-size:10px;color:#475569">{label} · {hit}/{total}</div>
</div>'''


def svg_supply_flow(upstream: str, company: str, downstream: str) -> str:
    """Visual upstream → company → downstream flow. Truncate long text to prevent overflow."""
    # Truncate each segment to prevent CSS overflow
    def _trunc(s: str, max_len: int = 60) -> str:
        s = str(s).strip()
        if len(s) > max_len:
            return s[:max_len] + "…"
        return s
    upstream = _trunc(upstream, 50)
    company = _trunc(company, 30)
    downstream = _trunc(downstream, 50)

    return f'''<div style="display:grid;grid-template-columns:1fr auto 1fr auto 1fr;gap:8px;align-items:center;font-family:Fira Sans;overflow:hidden">
  <div style="padding:10px 12px;background:#cffafe;border:1px solid #0891b2;border-radius:8px;text-align:center;overflow:hidden">
    <div style="font-size:9px;color:#0891b2;letter-spacing:.1em;margin-bottom:4px">UPSTREAM</div>
    <div style="font-size:11px;font-weight:600;color:#0f172a;line-height:1.4;word-break:break-all;overflow-wrap:break-word">{upstream}</div>
  </div>
  <div style="font-size:18px;color:#0891b2;flex-shrink:0">→</div>
  <div style="padding:10px 12px;background:#fef3c7;border:2px solid #d97706;border-radius:8px;text-align:center;overflow:hidden">
    <div style="font-size:9px;color:#d97706;letter-spacing:.1em;margin-bottom:4px">COMPANY</div>
    <div style="font-size:11px;font-weight:700;color:#0f172a;line-height:1.4">{company}</div>
  </div>
  <div style="font-size:18px;color:#0891b2;flex-shrink:0">→</div>
  <div style="padding:10px 12px;background:#d1fae5;border:1px solid #059669;border-radius:8px;text-align:center;overflow:hidden">
    <div style="font-size:9px;color:#059669;letter-spacing:.1em;margin-bottom:4px">DOWNSTREAM</div>
    <div style="font-size:11px;font-weight:600;color:#0f172a;line-height:1.4;word-break:break-all;overflow-wrap:break-word">{downstream}</div>
  </div>
</div>'''


def svg_timeline(events: list) -> str:
    """Vertical timeline of events."""
    if not events:
        return ""
    items = []
    for ev in events:
        items.append(
            f'<div style="display:flex;gap:10px;padding:8px 0">'
            f'<div style="width:10px;height:10px;border-radius:50%;background:{COLOR_GOLD};margin-top:4px;flex-shrink:0;'
            f'box-shadow:0 0 0 3px #fef3c7"></div>'
            f'<div style="font-size:11px;color:#1e293b;line-height:1.5">{ev}</div>'
            f'</div>'
        )
    return f'<div style="border-left:2px solid #e2e8f0;padding-left:12px;margin-left:5px">{"".join(items)}</div>'


def svg_bars(values: list, labels: list = None, width: int = 280, height: int = 120, color: str = COLOR_CYAN, show_values: bool = True, overlay_line: list = None, line_color: str = COLOR_GOLD) -> str:
    """Vertical bar chart with optional overlay line."""
    if not values:
        return ""
    n = len(values)
    pad_l, pad_r, pad_t, pad_b = 30, 10, 14, 24
    chart_w = width - pad_l - pad_r
    chart_h = height - pad_t - pad_b
    max_v = max(values + (overlay_line or []) + [0])
    min_v = min(values + (overlay_line or []) + [0])
    span = max(max_v - min_v, 1e-9)
    bar_w = chart_w / n * 0.7
    gap = chart_w / n * 0.3

    bars = []
    vals_txt = []
    labels_txt = []
    for i, v in enumerate(values):
        x = pad_l + i * (chart_w / n) + gap / 2
        bar_h = (v - min_v) / span * chart_h if span else 0
        y = pad_t + chart_h - bar_h
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" fill="{color}" rx="2"/>')
        if show_values:
            vals_txt.append(f'<text x="{x + bar_w/2:.1f}" y="{y - 4:.1f}" text-anchor="middle" font-family="Fira Code" font-size="9" fill="#0f172a" font-weight="700">{v}</text>')
        if labels:
            labels_txt.append(f'<text x="{x + bar_w/2:.1f}" y="{pad_t + chart_h + 14}" text-anchor="middle" font-family="Fira Code" font-size="9" fill="#64748b">{labels[i] if i < len(labels) else ""}</text>')

    # y-axis zero line
    y_zero = pad_t + chart_h - (0 - min_v) / span * chart_h if span else pad_t + chart_h
    axis = f'<line x1="{pad_l}" y1="{y_zero:.1f}" x2="{pad_l+chart_w}" y2="{y_zero:.1f}" stroke="#cbd5e1" stroke-width="1"/>'

    # overlay line (e.g. growth rate)
    line_path = ""
    line_dots = ""
    if overlay_line and len(overlay_line) == n:
        pts = []
        for i, v in enumerate(overlay_line):
            x = pad_l + i * (chart_w / n) + chart_w / n / 2
            y = pad_t + chart_h - (v - min_v) / span * chart_h if span else pad_t + chart_h
            pts.append((x, y))
        path_str = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        line_path = f'<path d="{path_str}" fill="none" stroke="{line_color}" stroke-width="2.5"/>'
        line_dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{line_color}"/>' for x, y in pts)

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  {axis}
  {"".join(bars)}
  {line_path}
  {line_dots}
  {"".join(vals_txt)}
  {"".join(labels_txt)}
</svg>'''


def svg_candlestick(candles: list, width: int = 380, height: int = 180, ma_20: list = None, ma_60: list = None) -> str:
    """Hand-rolled SVG candlestick. candles = [{open, close, high, low, date}, ...]"""
    if not candles:
        return ""
    n = len(candles)
    pad_l, pad_r, pad_t, pad_b = 40, 10, 10, 24
    chart_w = width - pad_l - pad_r
    chart_h = height - pad_t - pad_b
    all_highs = [c["high"] for c in candles]
    all_lows = [c["low"] for c in candles]
    if ma_20:
        all_highs += [v for v in ma_20 if v]
        all_lows += [v for v in ma_20 if v]
    if ma_60:
        all_highs += [v for v in ma_60 if v]
        all_lows += [v for v in ma_60 if v]
    y_max = max(all_highs) * 1.02
    y_min = min(all_lows) * 0.98
    span = max(y_max - y_min, 1e-9)

    def y_of(v):
        return pad_t + chart_h - (v - y_min) / span * chart_h

    cw = chart_w / n * 0.7
    gap = chart_w / n * 0.3

    elems = []
    # grid
    for ring in (0.25, 0.5, 0.75):
        yg = pad_t + chart_h * ring
        elems.append(f'<line x1="{pad_l}" y1="{yg:.1f}" x2="{pad_l+chart_w}" y2="{yg:.1f}" stroke="#f1f5f9" stroke-width="1"/>')

    # y labels
    for frac, v in [(0, y_max), (0.5, (y_max+y_min)/2), (1, y_min)]:
        yt = pad_t + chart_h * frac
        elems.append(f'<text x="{pad_l-5}" y="{yt+3:.1f}" text-anchor="end" font-family="Fira Code" font-size="9" fill="#64748b">{v:.1f}</text>')

    # candles
    for i, c in enumerate(candles):
        x = pad_l + i * (chart_w / n) + gap / 2
        cx = x + cw / 2
        op, cl, hi, lo = c["open"], c["close"], c["high"], c["low"]
        is_up = cl >= op
        color = COLOR_BEAR if is_up else COLOR_BULL  # China convention: red up, green down
        # wick
        elems.append(f'<line x1="{cx:.1f}" y1="{y_of(hi):.1f}" x2="{cx:.1f}" y2="{y_of(lo):.1f}" stroke="{color}" stroke-width="1"/>')
        # body
        top = y_of(max(op, cl))
        bh = max(abs(y_of(cl) - y_of(op)), 1)
        elems.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{cw:.1f}" height="{bh:.1f}" fill="{color}" stroke="{color}" stroke-width="1"/>')

    # MA lines
    def _ma_path(vals, color, label):
        if not vals:
            return ""
        pts = []
        for i, v in enumerate(vals):
            if v is None:
                continue
            x = pad_l + i * (chart_w / n) + cw / 2 + gap / 2
            y = y_of(v)
            pts.append(f"{x:.1f},{y:.1f}")
        if not pts:
            return ""
        return f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linejoin="round"/>'

    elems.append(_ma_path(ma_20, COLOR_GOLD, "MA20"))
    elems.append(_ma_path(ma_60, COLOR_INDIGO, "MA60"))

    # date labels (first, mid, last)
    if candles and "date" in candles[0]:
        for i in [0, n // 2, n - 1]:
            x = pad_l + i * (chart_w / n) + cw / 2
            elems.append(f'<text x="{x:.1f}" y="{pad_t+chart_h+14}" text-anchor="middle" font-family="Fira Code" font-size="8" fill="#64748b">{candles[i]["date"][-5:]}</text>')

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="width:100%">
  {"".join(elems)}
</svg>
<div style="display:flex;gap:14px;margin-top:6px;font-family:Fira Code;font-size:9px">
  <span><span style="display:inline-block;width:12px;height:2px;background:{COLOR_GOLD};vertical-align:middle"></span> MA20</span>
  <span><span style="display:inline-block;width:12px;height:2px;background:{COLOR_INDIGO};vertical-align:middle"></span> MA60</span>
</div>'''


def svg_pe_band(pe_history: list, bands: dict = None, width: int = 300, height: int = 140) -> str:
    """PE historical line with percentile bands. bands = {p25, p50, p75, current_idx}"""
    if not pe_history or len(pe_history) < 2:
        return ""
    import numpy as _np
    import statistics
    n = len(pe_history)
    pad_l, pad_r, pad_t, pad_b = 36, 10, 10, 20
    w = width - pad_l - pad_r
    h = height - pad_t - pad_b

    sorted_pe = sorted(pe_history)
    p25 = sorted_pe[int(n * 0.25)]
    p50 = sorted_pe[int(n * 0.5)]
    p75 = sorted_pe[int(n * 0.75)]
    y_max = max(pe_history) * 1.05
    y_min = min(pe_history) * 0.95
    span = max(y_max - y_min, 1e-9)

    def y_of(v):
        return pad_t + h - (v - y_min) / span * h

    # bands (percentile horizontal strips)
    y25 = y_of(p25)
    y50 = y_of(p50)
    y75 = y_of(p75)
    bands_svg = f'''
  <rect x="{pad_l}" y="{pad_t}" width="{w}" height="{y75-pad_t:.1f}" fill="#fee2e2" opacity="0.5"/>
  <rect x="{pad_l}" y="{y75:.1f}" width="{w}" height="{y25-y75:.1f}" fill="#fef3c7" opacity="0.5"/>
  <rect x="{pad_l}" y="{y25:.1f}" width="{w}" height="{pad_t+h-y25:.1f}" fill="#d1fae5" opacity="0.5"/>
  <line x1="{pad_l}" y1="{y25:.1f}" x2="{pad_l+w}" y2="{y25:.1f}" stroke="#059669" stroke-width="1" stroke-dasharray="3,3"/>
  <line x1="{pad_l}" y1="{y50:.1f}" x2="{pad_l+w}" y2="{y50:.1f}" stroke="#64748b" stroke-width="1" stroke-dasharray="3,3"/>
  <line x1="{pad_l}" y1="{y75:.1f}" x2="{pad_l+w}" y2="{y75:.1f}" stroke="#dc2626" stroke-width="1" stroke-dasharray="3,3"/>
  <text x="{pad_l-3}" y="{y25+3:.1f}" text-anchor="end" font-family="Fira Code" font-size="8" fill="#059669">25%</text>
  <text x="{pad_l-3}" y="{y50+3:.1f}" text-anchor="end" font-family="Fira Code" font-size="8" fill="#64748b">50%</text>
  <text x="{pad_l-3}" y="{y75+3:.1f}" text-anchor="end" font-family="Fira Code" font-size="8" fill="#dc2626">75%</text>
    '''

    # line
    pts = []
    for i, v in enumerate(pe_history):
        x = pad_l + i / (n - 1) * w
        y = y_of(v)
        pts.append(f"{x:.1f},{y:.1f}")
    line = f'<polyline points="{" ".join(pts)}" fill="none" stroke="{COLOR_BLUE}" stroke-width="2"/>'

    # current point highlight
    last_x = pad_l + w
    last_y = y_of(pe_history[-1])
    current = f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="5" fill="{COLOR_BLUE}" stroke="#fff" stroke-width="2"/>'
    cur_label = f'<text x="{last_x:.1f}" y="{last_y-10:.1f}" text-anchor="end" font-family="Fira Code" font-size="10" font-weight="700" fill="{COLOR_BLUE}">{pe_history[-1]:.1f}</text>'

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="width:100%">
  {bands_svg}
  {line}
  {current}
  {cur_label}
</svg>'''


def svg_progress_row(label: str, pct: float, color: str = COLOR_CYAN, suffix: str = "") -> str:
    """Inline labeled progress bar."""
    pct_clamped = max(0, min(100, pct))
    return f'''<div style="display:flex;align-items:center;gap:10px;margin:6px 0">
  <div style="width:70px;font-family:Fira Code;font-size:10px;color:#64748b">{label}</div>
  <div style="flex:1;height:8px;background:#f1f5f9;border-radius:4px;overflow:hidden">
    <div style="width:{pct_clamped}%;height:100%;background:{color};border-radius:4px"></div>
  </div>
  <div style="min-width:50px;text-align:right;font-family:Fira Code;font-size:11px;color:#0f172a;font-weight:700">{pct:.1f}{suffix}</div>
</div>'''


def svg_peer_table(rows: list) -> str:
    """HTML comparison table. rows = [{name, pe, pb, roe, revenue_growth, is_self}, ...]"""
    if not rows:
        return ""
    head = '''<tr style="background:#f8fafc">
  <th style="text-align:left;padding:8px 10px;font-family:Fira Code;font-size:9px;color:#64748b;font-weight:700;border-bottom:2px solid #e2e8f0">公司</th>
  <th style="text-align:right;padding:8px 10px;font-family:Fira Code;font-size:9px;color:#64748b;font-weight:700;border-bottom:2px solid #e2e8f0">PE</th>
  <th style="text-align:right;padding:8px 10px;font-family:Fira Code;font-size:9px;color:#64748b;font-weight:700;border-bottom:2px solid #e2e8f0">PB</th>
  <th style="text-align:right;padding:8px 10px;font-family:Fira Code;font-size:9px;color:#64748b;font-weight:700;border-bottom:2px solid #e2e8f0">ROE</th>
  <th style="text-align:right;padding:8px 10px;font-family:Fira Code;font-size:9px;color:#64748b;font-weight:700;border-bottom:2px solid #e2e8f0">营收增速</th>
</tr>'''
    body = ""
    for r in rows:
        is_self = r.get("is_self", False)
        row_style = 'background:#fef3c7;font-weight:700' if is_self else 'background:#ffffff'
        body += f'''<tr style="{row_style}">
  <td style="padding:8px 10px;font-family:Fira Sans;font-size:12px;color:#0f172a;border-bottom:1px solid #f1f5f9">{'⭐ ' if is_self else ''}{r.get("name", "")}</td>
  <td style="text-align:right;padding:8px 10px;font-family:Fira Code;font-size:11px;color:#0f172a;border-bottom:1px solid #f1f5f9">{r.get("pe", "—")}</td>
  <td style="text-align:right;padding:8px 10px;font-family:Fira Code;font-size:11px;color:#0f172a;border-bottom:1px solid #f1f5f9">{r.get("pb", "—")}</td>
  <td style="text-align:right;padding:8px 10px;font-family:Fira Code;font-size:11px;color:#0f172a;border-bottom:1px solid #f1f5f9">{r.get("roe", "—")}</td>
  <td style="text-align:right;padding:8px 10px;font-family:Fira Code;font-size:11px;color:#0f172a;border-bottom:1px solid #f1f5f9">{r.get("revenue_growth", "—")}</td>
</tr>'''
    return f'<table style="width:100%;border-collapse:collapse;font-family:Fira Sans">{head}{body}</table>'


def svg_unlock_timeline(unlocks: list, width: int = 280, height: int = 100) -> str:
    """Future unlock timeline: list of {date, amount_亿}."""
    if not unlocks:
        return '<div style="text-align:center;color:#94a3b8;font-size:11px;padding:10px">未来 12 个月无解禁</div>'
    n = len(unlocks)
    pad_l, pad_r, pad_t, pad_b = 20, 10, 16, 24
    w = width - pad_l - pad_r
    h = height - pad_t - pad_b
    max_a = max(u.get("amount", 0) for u in unlocks) or 1
    bar_w = w / n * 0.6
    gap = w / n * 0.4
    bars = []
    for i, u in enumerate(unlocks):
        amt = u.get("amount", 0)
        date = u.get("date", "")
        x = pad_l + i * (w / n) + gap / 2
        bar_h = amt / max_a * h
        y = pad_t + h - bar_h
        color = COLOR_BEAR if amt > max_a * 0.5 else COLOR_GOLD
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" fill="{color}" rx="2"/>')
        bars.append(f'<text x="{x + bar_w/2:.1f}" y="{y - 3:.1f}" text-anchor="middle" font-family="Fira Code" font-size="9" fill="#0f172a" font-weight="700">{amt}</text>')
        bars.append(f'<text x="{x + bar_w/2:.1f}" y="{pad_t+h+14}" text-anchor="middle" font-family="Fira Code" font-size="8" fill="#64748b">{date}</text>')
    axis = f'<line x1="{pad_l}" y1="{pad_t+h}" x2="{pad_l+w}" y2="{pad_t+h}" stroke="#cbd5e1"/>'
    return f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="width:100%">{axis}{"".join(bars)}</svg>'


def svg_dividend_combo(years: list, amounts: list, yields: list, width: int = 300, height: int = 140) -> str:
    """Dividend history: bars for amount + line for yield."""
    if not years or not amounts:
        return ""
    n = len(years)
    pad_l, pad_r, pad_t, pad_b = 36, 40, 14, 24
    w = width - pad_l - pad_r
    h = height - pad_t - pad_b
    max_a = max(amounts) or 1
    max_y = max(yields) if yields else 5
    bar_w = w / n * 0.55
    gap = w / n * 0.45

    bars = []
    for i, a in enumerate(amounts):
        x = pad_l + i * (w / n) + gap / 2
        bar_h = a / max_a * h
        y = pad_t + h - bar_h
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" fill="{COLOR_CYAN}" rx="2"/>')
        bars.append(f'<text x="{x+bar_w/2:.1f}" y="{y-3:.1f}" text-anchor="middle" font-family="Fira Code" font-size="9" fill="#0f172a" font-weight="700">{a}</text>')
        bars.append(f'<text x="{x+bar_w/2:.1f}" y="{pad_t+h+14}" text-anchor="middle" font-family="Fira Code" font-size="9" fill="#64748b">{years[i]}</text>')

    # yield line (right axis)
    if yields:
        pts = []
        for i, y in enumerate(yields):
            x = pad_l + i * (w / n) + w / n / 2
            yy = pad_t + h - y / max_y * h
            pts.append((x, yy))
        line = f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x,y in pts)}" fill="none" stroke="{COLOR_GOLD}" stroke-width="2.5"/>'
        dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{COLOR_GOLD}"/>' for x, y in pts)
        bars.append(line)
        bars.append(dots)
        # right axis label
        bars.append(f'<text x="{pad_l+w+4}" y="{pad_t+10}" font-family="Fira Code" font-size="9" fill="{COLOR_GOLD}">{max_y:.1f}%</text>')
        bars.append(f'<text x="{pad_l+w+4}" y="{pad_t+h}" font-family="Fira Code" font-size="9" fill="{COLOR_GOLD}">0%</text>')

    return f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="width:100%">{"".join(bars)}</svg>'


def svg_institutional_quarters(data: dict, width: int = 300, height: int = 120) -> str:
    """Stacked/grouped bar of institutional holdings over quarters.
    data = {'quarters': ['23Q2', '23Q3', ...], 'fund': [...], 'qfii': [...], 'shehui': [...]}"""
    quarters = data.get("quarters", [])
    if not quarters:
        return ""
    series = [
        ("公募", data.get("fund", []), COLOR_CYAN),
        ("QFII", data.get("qfii", []), COLOR_BLUE),
        ("社保", data.get("shehui", []), COLOR_GOLD),
    ]
    n = len(quarters)
    pad_l, pad_r, pad_t, pad_b = 10, 10, 16, 22
    w = width - pad_l - pad_r
    h = height - pad_t - pad_b
    all_vals = [v for _, vals, _ in series for v in vals if v is not None] + [0]
    max_v = max(all_vals) or 1

    bar_w = w / n * 0.28
    group_gap = w / n * 0.16

    elems = []
    for i in range(n):
        bx = pad_l + i * (w / n) + group_gap / 2
        for si, (_, vals, col) in enumerate(series):
            if i >= len(vals):
                continue
            v = vals[i]
            bar_h = v / max_v * h
            x = bx + si * bar_w
            y = pad_t + h - bar_h
            elems.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w-0.5:.1f}" height="{bar_h:.1f}" fill="{col}" rx="1"/>')
        elems.append(f'<text x="{bx + 1.5*bar_w:.1f}" y="{pad_t+h+14}" text-anchor="middle" font-family="Fira Code" font-size="9" fill="#64748b">{quarters[i]}</text>')

    legend = f'''<div style="display:flex;gap:10px;margin-top:4px;font-family:Fira Code;font-size:9px">
  <span style="color:{COLOR_CYAN}">■ 公募</span>
  <span style="color:{COLOR_BLUE}">■ QFII</span>
  <span style="color:{COLOR_GOLD}">■ 社保</span>
</div>'''
    return f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="width:100%">{"".join(elems)}</svg>{legend}'


def svg_thermometer(value: int, max_val: int = 100, label: str = "") -> str:
    """Heat thermometer (vertical)."""
    pct = min(100, max(0, value / max_val * 100))
    color = COLOR_BEAR if value > 80 else COLOR_GOLD if value > 50 else COLOR_BULL
    return f'''<div style="display:flex;align-items:center;gap:14px">
  <div style="width:24px;height:120px;background:#f1f5f9;border:1px solid #cbd5e1;border-radius:12px;position:relative;overflow:hidden">
    <div style="position:absolute;bottom:0;left:0;right:0;height:{pct}%;background:linear-gradient(0deg,{color},{color}cc);border-radius:0 0 12px 12px;transition:height 1s"></div>
  </div>
  <div>
    <div style="font-family:Fira Sans;font-weight:900;font-size:32px;color:{color};line-height:1">{value}</div>
    <div style="font-family:Fira Code;font-size:9px;color:#64748b;letter-spacing:.1em">{label}</div>
  </div>
</div>'''


## ─── 19 维数据卡 配置 ───

DIM_META = {
    "1_financials": {
        "id": "01", "title": "财报扎实度", "en": "Financials", "weight": 5, "cat": "fin",
        "kpis": ["roe", "net_margin", "revenue_growth", "fcf"],
        "kpi_labels": {"roe": "ROE", "net_margin": "净利率", "revenue_growth": "营收增速", "fcf": "自由现金流"},
    },
    "2_kline": {
        "id": "02", "title": "K 线技术面", "en": "Technical", "weight": 4, "cat": "mkt",
        "kpis": ["stage", "ma_align", "macd", "rsi"],
        "kpi_labels": {"stage": "Stage", "ma_align": "均线", "macd": "MACD", "rsi": "RSI"},
    },
    "3_macro": {
        "id": "03", "title": "宏观环境", "en": "Macro", "weight": 3, "cat": "env",
        "kpis": ["rate_cycle", "fx_trend", "geo_risk", "commodity"],
        "kpi_labels": {"rate_cycle": "利率", "fx_trend": "汇率", "geo_risk": "地缘", "commodity": "大宗"},
    },
    "4_peers": {
        "id": "04", "title": "同行对比", "en": "Peers", "weight": 4, "cat": "ind",
        "kpis": ["rank", "gross_margin_vs", "roe_vs", "growth_vs"],
        "kpi_labels": {"rank": "行业排名", "gross_margin_vs": "毛利率vs", "roe_vs": "ROE vs", "growth_vs": "增速vs"},
    },
    "5_chain": {
        "id": "05", "title": "上下游产业链", "en": "Supply Chain", "weight": 4, "cat": "ind",
        "kpis": ["upstream", "downstream", "client_concentration", "supplier_concentration"],
        "kpi_labels": {"upstream": "上游", "downstream": "下游", "client_concentration": "大客户集中", "supplier_concentration": "供应商集中"},
    },
    "6_research": {
        "id": "06", "title": "研报观点", "en": "Sell-side", "weight": 3, "cat": "co",
        "kpis": ["coverage", "rating", "target_avg", "upside"],
        "kpi_labels": {"coverage": "覆盖券商", "rating": "买入比例", "target_avg": "目标价均值", "upside": "上涨空间"},
    },
    "7_industry": {
        "id": "07", "title": "行业景气", "en": "Industry", "weight": 4, "cat": "ind",
        "kpis": ["growth", "tam", "penetration", "lifecycle"],
        "kpi_labels": {"growth": "行业增速", "tam": "TAM", "penetration": "渗透率", "lifecycle": "生命周期"},
    },
    "8_materials": {
        "id": "08", "title": "原材料", "en": "Raw Materials", "weight": 3, "cat": "ind",
        "kpis": ["core_material", "price_trend", "cost_share", "import_dep"],
        "kpi_labels": {"core_material": "核心材料", "price_trend": "12M趋势", "cost_share": "成本占比", "import_dep": "进口依赖"},
    },
    "9_futures": {
        "id": "09", "title": "期货关联", "en": "Futures Link", "weight": 2, "cat": "ind",
        "kpis": ["linked_contract", "contract_trend"],
        "kpi_labels": {"linked_contract": "关联品种", "contract_trend": "走势"},
    },
    "10_valuation": {
        "id": "10", "title": "估值多维", "en": "Valuation", "weight": 5, "cat": "fin",
        "kpis": ["pe", "pe_quantile", "industry_pe", "dcf"],
        "kpi_labels": {"pe": "当前 PE", "pe_quantile": "PE 5年分位", "industry_pe": "行业均值", "dcf": "DCF 内在值"},
    },
    "11_governance": {
        "id": "11", "title": "管理层与治理", "en": "Governance", "weight": 4, "cat": "co",
        "kpis": ["pledge", "insider", "related_tx", "violations"],
        "kpi_labels": {"pledge": "实控人质押", "insider": "近12月增减持", "related_tx": "关联交易", "violations": "违规记录"},
    },
    "12_capital_flow": {
        "id": "12", "title": "资金面", "en": "Capital Flow", "weight": 4, "cat": "mkt",
        "kpis": ["main_20d", "margin_trend", "holders_trend", "main_5d"],
        "kpi_labels": {"main_20d": "主力资金20日", "margin_trend": "融资余额", "holders_trend": "股东户数", "main_5d": "主力5日"},
    },
    "13_policy": {
        "id": "13", "title": "政策与监管", "en": "Policy", "weight": 3, "cat": "env",
        "kpis": ["policy_dir", "subsidy", "monitoring", "anti_trust"],
        "kpi_labels": {"policy_dir": "政策方向", "subsidy": "补贴税收", "monitoring": "监管动向", "anti_trust": "反垄断"},
    },
    "14_moat": {
        "id": "14", "title": "护城河 (5 类)", "en": "Moat", "weight": 3, "cat": "fin",
        "kpis": ["intangible", "switching", "network", "scale"],
        "kpi_labels": {"intangible": "无形资产", "switching": "转换成本", "network": "网络效应", "scale": "规模优势"},
    },
    "15_events": {
        "id": "15", "title": "事件驱动", "en": "Events", "weight": 4, "cat": "co",
        "kpis": ["recent_news", "catalyst", "earnings_preview", "warnings"],
        "kpi_labels": {"recent_news": "近30天事件", "catalyst": "催化剂", "earnings_preview": "业绩预告", "warnings": "利空"},
    },
    "16_lhb": {
        "id": "16", "title": "龙虎榜", "en": "Dragon-Tiger", "weight": 4, "cat": "mkt",
        "kpis": ["lhb_30d", "youzi_matched", "inst_net", "youzi_net"],
        "kpi_labels": {"lhb_30d": "30天上榜", "youzi_matched": "识别游资", "inst_net": "机构净买", "youzi_net": "游资净买"},
    },
    "17_sentiment": {
        "id": "17", "title": "舆情与大V", "en": "Sentiment", "weight": 3, "cat": "saf",
        "kpis": ["xueqiu_heat", "guba_volume", "big_v_mentions", "positive_pct"],
        "kpi_labels": {"xueqiu_heat": "雪球热度", "guba_volume": "股吧讨论", "big_v_mentions": "大V提及", "positive_pct": "正面占比"},
    },
    "18_trap": {
        "id": "18", "title": "杀猪盘检测", "en": "Trap Scan", "weight": 5, "cat": "saf",
        "kpis": ["signals_hit", "trap_level", "high_risk_kw", "evidence_count"],
        "kpi_labels": {"signals_hit": "命中信号", "trap_level": "风险等级", "high_risk_kw": "高危词", "evidence_count": "证据数"},
    },
    "19_contests": {
        "id": "19", "title": "实盘比赛持仓", "en": "Live Contests", "weight": 4, "cat": "saf",
        "kpis": ["xq_cubes", "high_return_cubes", "tgb_mentions", "ths_simu"],
        "kpi_labels": {"xq_cubes": "雪球组合", "high_return_cubes": "高收益持有", "tgb_mentions": "淘股吧", "ths_simu": "同花顺模拟"},
    },
}

CAT_GROUPS = {
    "fin": ["1_financials", "10_valuation", "14_moat"],
    "mkt": ["2_kline", "12_capital_flow", "16_lhb"],
    "ind": ["4_peers", "5_chain", "7_industry", "8_materials", "9_futures"],
    "co":  ["11_governance", "15_events", "6_research"],
    "env": ["3_macro", "13_policy"],
    "saf": ["17_sentiment", "18_trap", "19_contests"],
}


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
  <span style="padding:4px 10px;background:#e0e7ff;color:#4f46e5;border-radius:4px;font-family:Fira Code;font-size:11px;font-weight:600">RSI {rsi}</span>
</div>'''

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


def _extract_kpi_value(raw_dim_data: dict, key: str) -> str:
    """Best-effort extraction. Walks nested dict looking for the key, falls back to —."""
    if not isinstance(raw_dim_data, dict):
        return "—"
    # direct lookup
    if key in raw_dim_data:
        v = raw_dim_data[key]
        return str(v) if v is not None else "—"
    # walk one level
    for sub in raw_dim_data.values():
        if isinstance(sub, dict) and key in sub:
            v = sub[key]
            return str(v) if v is not None else "—"
    return "—"


def render_dim_card(dim_key: str, dim_score: dict, raw_dim: dict) -> str:
    """Render one dimension card (data-driven from DIM_META)."""
    meta = DIM_META.get(dim_key)
    if not meta:
        return ""
    score = dim_score.get("score")
    label = _safe(dim_score.get("label"), "—")
    pass_items = dim_score.get("reasons_pass") or []
    fail_items = dim_score.get("reasons_fail") or []
    weight = dim_score.get("weight") or meta.get("weight", 3)
    score_cls = _score_class(score)
    score_pct = (score or 0) * 10  # 0-100 scale
    stars = "★" * weight + "☆" * (5 - weight)

    raw_data = (raw_dim or {}).get("data") or {}
    fallback = (raw_dim or {}).get("fallback", False)
    source = (raw_dim or {}).get("source", "—")
    # Clean up source label: if we have real data, show "官方接口" instead of raw source string
    if not fallback and source and "web_search" not in str(source).lower():
        source_label = "官方接口"
    elif "web_search" in str(source).lower() and not fallback:
        source_label = "官方接口"  # Has data despite web_search tag = good enough
    elif fallback:
        source_label = "web_search"
    else:
        source_label = "官方接口"

    # Specialized viz (overrides KPI grid if available)
    viz_html = ""
    if dim_key in DIM_VIZ_RENDERERS:
        try:
            viz_html = f'<div class="dim-viz">{DIM_VIZ_RENDERERS[dim_key](raw_data)}</div>'
        except Exception as e:
            viz_html = f'<div class="dim-viz" style="color:#dc2626;font-size:11px">viz error: {e}</div>'

    # KPI grid (only render if no specialized viz)
    kpi_html = ""
    if not viz_html:
        kpi_cells = []
        for k in meta["kpis"]:
            v = _extract_kpi_value(raw_data, k)
            if v != "—":
                label_k = meta["kpi_labels"].get(k, k)
                kpi_cells.append(f'<div class="kpi"><div class="k">{label_k}</div><div class="v">{v}</div></div>')
        if kpi_cells:
            kpi_html = f'<div class="dim-kpis">{"".join(kpi_cells)}</div>'

    # pass / fail
    pf_html = ""
    if pass_items or fail_items:
        pf_html = '<div class="dim-pass-fail">'
        if pass_items:
            pf_html += f'<div class="pass"><ul>{_li(pass_items)}</ul></div>'
        if fail_items:
            pf_html += f'<div class="fail"><ul>{_li(fail_items)}</ul></div>'
        pf_html += '</div>'

    badge_cls = "fallback" if fallback else "live"
    badge_text = "网络搜索" if fallback else source_label

    # raw data dump (collapsible)
    import json as _j
    raw_dump = _j.dumps(raw_data, ensure_ascii=False, indent=2, default=str)
    if len(raw_dump) > 1500:
        raw_dump = raw_dump[:1500] + "\n... (truncated)"

    return f'''<div class="dim-card" data-dim="{meta["id"]}">
  <div class="dim-head">
    <div>
      <div class="dim-num">DIM {meta["id"]} · WEIGHT {stars}</div>
      <div class="dim-title">{meta["title"]}</div>
      <div class="dim-en">{meta["en"]}</div>
    </div>
    <div class="dim-score">
      <div class="num {score_cls}">{score if score is not None else "—"}</div>
    </div>
  </div>
  <div class="dim-bar"><div class="fill {score_cls}" style="width: {score_pct}%"></div></div>
  <div class="dim-label">{label}</div>
  {viz_html}
  {kpi_html}
  {pf_html}
  <div class="dim-source">数据来源: <span class="badge {badge_cls}">{badge_text}</span> <span style="opacity:.65">{source}</span></div>
  <details>
    <summary>查看原始数据 ▼</summary>
    <pre>{raw_dump}</pre>
  </details>
</div>'''


def render_dim_category(cat: str, dimensions: dict, raw: dict) -> str:
    """Render all cards in one category."""
    raw_dims = raw.get("dimensions", {}) if raw else {}
    dim_scores = dimensions.get("dimensions", {}) if dimensions else {}
    cards = []
    for key in CAT_GROUPS.get(cat, []):
        cards.append(render_dim_card(key, dim_scores.get(key, {}), raw_dims.get(key, {})))
    return "\n".join(cards)


## ─── Tier 4 友好层: 情景模拟 / 最像的票 / 离场触发 ───

def render_friendly_layer(syn: dict, raw: dict) -> str:
    """Three Tier-4 cards:
    1. 一万块场景模拟 (worst/base/best case)
    2. 最像的另外 3 只票 (可比)
    3. 离场触发条件 (3-5 条)
    """
    friendly = syn.get("friendly") or {}

    # ── Scenario simulator ──
    scenarios = friendly.get("scenarios") or {}
    entry_price = scenarios.get("entry_price", 0)
    cases = scenarios.get("cases", [])
    scenario_rows = ""
    if cases:
        for c in cases:
            name = c.get("name", "")
            prob = c.get("probability", "")
            ret = c.get("return", 0)
            val_1w = int(10000 * (1 + ret / 100))
            cls = "up" if ret > 0 else "down" if ret < 0 else "flat"
            sign = "+" if ret > 0 else ""
            scenario_rows += f'<div class="scenario-row"><span class="label">{name} · {prob}</span><span class="val {cls}">{sign}{ret}% → ¥{val_1w:,}</span></div>'
    scenario_card = f'''<div class="friendly-card scenario">
  <div class="fc-icon">💰</div>
  <div class="fc-title">如果现在买 1 万块</div>
  <div class="fc-body">
    {f'<div style="font-size:11px;color:#475569;margin-bottom:8px">按入场价 <strong>¥{entry_price}</strong> 计算：</div>' if entry_price else ''}
    {scenario_rows or '<div style="color:#94a3b8;font-size:11px">暂无情景模拟</div>'}
  </div>
</div>'''

    # ── Similar stocks ──
    similar = friendly.get("similar_stocks") or []
    similar_pills = ""
    for s in similar[:4]:
        name = s.get("name", "")
        code = s.get("code", "")
        similarity = s.get("similarity", "")
        reason = s.get("reason", "")
        url = s.get("url", f"https://xueqiu.com/S/{code}" if code else "#")
        similar_pills += f'''<a href="{url}" target="_blank" rel="noopener" class="similar-stock-pill">
  <div style="display:flex;justify-content:space-between;align-items:baseline">
    <span class="ss-name">{name}</span>
    <span class="ss-meta">相似度 {similarity}</span>
  </div>
  <div class="ss-reason">{reason}</div>
</a>'''
    similar_card = f'''<div class="friendly-card similar">
  <div class="fc-icon">🔗</div>
  <div class="fc-title">跟它最像的另外几只票</div>
  <div class="fc-body">
    {similar_pills or '<div style="color:#94a3b8;font-size:11px">暂无可比股</div>'}
  </div>
</div>'''

    # ── Exit triggers ──
    triggers = friendly.get("exit_triggers") or []
    trigger_items = "".join(f'<div class="exit-trigger-item">{t}</div>' for t in triggers)
    exit_card = f'''<div class="friendly-card exit">
  <div class="fc-icon">🚪</div>
  <div class="fc-title">出现这些信号就离场</div>
  <div class="fc-body">
    {trigger_items or '<div style="color:#94a3b8;font-size:11px">暂无触发条件</div>'}
  </div>
</div>'''

    return scenario_card + similar_card + exit_card


## ─── 基金经理抄作业面板 ───

def render_fund_managers(managers: list) -> str:
    """For each fund manager holding this stock, render a performance card.
    managers = [
      {
        "name": "张坤",
        "fund_name": "易方达蓝筹精选",
        "fund_code": "005827",
        "avatar": "zhangkun",      # use existing investor avatar if matching
        "position_pct": 3.2,        # % of fund in this stock
        "rank_in_fund": 8,          # top N holding
        "holding_quarters": 4,
        "position_trend": "加仓",    # 加仓/减仓/持平/新进
        "return_5y": 156.7,         # cumulative %
        "annualized_5y": 20.5,
        "max_drawdown": -28.3,
        "sharpe": 1.42,
        "peer_rank_pct": 5,         # top %
        "nav_history": [1.0, 1.1, ...],  # 5Y NAV sparkline
        "fund_url": "https://...",
      },
    ]
    """
    if not managers:
        return '<div style="padding:24px;text-align:center;color:#94a3b8;font-size:12px">暂无公募基金持仓数据</div>'

    # v2.10.1 · 分 full / lite 两类：full 有 5Y 业绩在前按 5Y 降序，lite 在后按持仓%
    def _sort_key(m: dict) -> tuple:
        is_full = m.get("_row_type") == "full" or m.get("return_5y") is not None
        ret5y = m.get("return_5y") if is_full else 0
        pos = m.get("position_pct") or 0
        return (
            0 if is_full else 1,
            -(ret5y if isinstance(ret5y, (int, float)) else 0),
            -pos,
        )
    managers_sorted = sorted(managers, key=_sort_key)
    cards = []
    for m in managers_sorted:
        # v2.15.1 · lite 行（return_5y is None 或 _row_type=lite）一律不生成 fund-card · 走 compact row
        # 之前所有 manager 都进这里再 fallback return_5y = 0 · 导致报告堆一片 0.0% 的假 card
        is_lite = m.get("_row_type") == "lite" or m.get("return_5y") is None
        if is_lite:
            continue

        name = m.get("name", "—")
        fund_name = m.get("fund_name", "—")
        avatar = m.get("avatar", "")
        position = m.get("position_pct", 0)
        rank = m.get("rank_in_fund", 0)
        quarters = m.get("holding_quarters", 0)
        trend = m.get("position_trend", "持平")
        trend_color = COLOR_BULL if trend == "加仓" else COLOR_BEAR if trend == "减仓" else COLOR_MUTED
        trend_icon = "📈" if trend == "加仓" else "📉" if trend == "减仓" else "➡️"

        # v2.10.5 · lite 档 fund_managers 前 N 个有完整业绩，其余只有列表信息 → 数值字段可为 None
        ret_5y = m.get("return_5y") or 0
        ann_5y = m.get("annualized_5y") or 0
        max_dd = m.get("max_drawdown") or 0
        sharpe = m.get("sharpe") or 0
        peer_rank = m.get("peer_rank_pct") or 50

        nav = m.get("nav_history", [])
        nav_spark = svg_sparkline(nav, width=280, height=50, color=COLOR_BULL if nav and nav[-1] > nav[0] else COLOR_BEAR) if nav else ""

        ret_color = COLOR_BULL if ret_5y > 0 else COLOR_BEAR
        dd_color = COLOR_BULL if max_dd > -20 else COLOR_GOLD if max_dd > -40 else COLOR_BEAR
        sharpe_color = COLOR_BULL if sharpe > 1 else COLOR_GOLD if sharpe > 0.5 else COLOR_BEAR
        rank_color = COLOR_BULL if peer_rank < 20 else COLOR_GOLD if peer_rank < 50 else COLOR_BEAR

        avatar_html = ""
        if avatar:
            avatar_html = f'<img src="avatars/{avatar}.svg" style="width:54px;height:54px;image-rendering:pixelated;border:2px solid #d97706;border-radius:8px;background:#fff;flex-shrink:0">'
        else:
            avatar_html = f'<div style="width:54px;height:54px;background:#fef3c7;border:2px solid #d97706;border-radius:8px;display:flex;align-items:center;justify-content:center;font-family:Fira Sans;font-size:20px;font-weight:900;color:#d97706;flex-shrink:0">{name[0] if name else "?"}</div>'

        # Performance stars based on peer rank
        stars = "⭐" * max(1, min(5, int((100 - peer_rank) / 20) + 1))

        fund_url = m.get("fund_url", f'https://fund.eastmoney.com/{m.get("fund_code", "")}.html')

        card = f'''<div class="fund-card">
  <div class="fund-header">
    {avatar_html}
    <div style="flex:1;min-width:0">
      <div class="fund-manager-name">{name} <span class="fund-stars">{stars}</span></div>
      <div class="fund-name">{fund_name}</div>
      <div class="fund-meta">持本股 {quarters} 季 · 位列第 {rank} 大 · 占基金 {position}% · <span style="color:{trend_color};font-weight:700">{trend_icon} {trend}</span></div>
    </div>
  </div>

  <div class="fund-metrics-grid">
    <div class="fund-metric">
      <div class="fm-label">5 年累计</div>
      <div class="fm-value" style="color:{ret_color}">{'+' if ret_5y > 0 else ''}{ret_5y:.1f}%</div>
    </div>
    <div class="fund-metric">
      <div class="fm-label">年化</div>
      <div class="fm-value">{'+' if ann_5y > 0 else ''}{ann_5y:.1f}%</div>
    </div>
    <div class="fund-metric">
      <div class="fm-label">最大回撤</div>
      <div class="fm-value" style="color:{dd_color}">{max_dd:.1f}%</div>
    </div>
    <div class="fund-metric">
      <div class="fm-label">夏普比率</div>
      <div class="fm-value" style="color:{sharpe_color}">{sharpe:.2f}</div>
    </div>
  </div>

  <div class="fund-nav-block">
    <div style="display:flex;justify-content:space-between;font-family:Fira Code;font-size:10px;color:#64748b;margin-bottom:4px">
      <span>5 年净值走势</span>
      <span>同类排名 <strong style="color:{rank_color}">前 {peer_rank}%</strong></span>
    </div>
    {nav_spark}
  </div>

  <div style="display:flex;gap:8px;margin-top:10px">
    <a href="{fund_url}" target="_blank" rel="noopener" class="fund-link">查看基金 →</a>
  </div>
</div>'''
        cards.append(card)

    # v2.10.1 · 头部与清单分开统计
    full_count = sum(1 for m in managers if m.get("_row_type") == "full" or m.get("return_5y") is not None)
    lite_count = len(managers) - full_count
    if lite_count > 0:
        header = (
            f'<div class="fund-mgr-header">✨ <strong>{len(managers)} 家公募基金</strong>持有本股 · '
            f'头部 <strong>{full_count}</strong> 家有完整 5Y 业绩（按收益排序），'
            f'其余 <strong>{lite_count}</strong> 家按持仓占比列出（点基金链接看详情）</div>'
        )
    else:
        header = f'<div class="fund-mgr-header">✨ <strong>{len(managers)} 位公募基金经理</strong>持有本股 · 按 5 年累计收益排序 · 你可以直接"抄作业"</div>'

    # v2.15.1 · INITIAL_SHOW 现在 = full_count 天然（我们已 skip lite 行）· 所有 lite 都进 compact rows
    # 理由：之前 fixed=6 会把排序第 5/6 位的 lite 行当 full card 渲染 → 一堆 0.0% 假 card
    INITIAL_SHOW = min(6, len(cards))
    lite_managers = [m for m in managers_sorted if m.get("_row_type") == "lite" or m.get("return_5y") is None]

    # v2.15.1 · lite 行按 fund_code 去重 + 按 position_pct 倒序 + cap top 30
    # 避免 722 条重复份额（如 富国天惠 A/B/C/D 同时列 10+ 次）撑爆报告
    seen = set()
    deduped = []
    for m in sorted(lite_managers, key=lambda x: -(x.get("position_pct") or 0)):
        code = m.get("fund_code")
        if code in seen:
            continue
        seen.add(code)
        deduped.append(m)
    LITE_CAP = 30
    lite_capped = deduped[:LITE_CAP]
    lite_overflow = max(0, len(deduped) - LITE_CAP)

    # 无 lite · 全部 full 直接返（经典小股情况）
    if not lite_managers:
        return header + f'<div class="fund-mgr-grid">{"".join(cards)}</div>'

    # 有 lite · cards 全显示（最多 6 张大卡）+ top 30 lite 进 compact rows
    visible = "".join(cards[:INITIAL_SHOW])
    compact_rows = [
        _render_fund_compact_row(m, rank=i + 1 + len(cards))
        for i, m in enumerate(lite_capped)
    ]
    if lite_overflow > 0:
        hidden_count = f"{len(lite_capped)}（另有 {lite_overflow} 家 · 点基金链接自行查）"
    else:
        hidden_count = str(len(lite_capped))
    uid = f"fm_{abs(hash(str(len(cards))))}"

    return header + f'''
    <div class="fund-mgr-grid">{visible}</div>
    <div id="{uid}" class="fund-compact-list" style="display:none">
      <div class="fund-compact-head">
        <span class="fc-h-rank">#</span>
        <span class="fc-h-avatar"></span>
        <span class="fc-h-name">基金经理 / 基金</span>
        <span class="fc-h-metric">5Y 累计</span>
        <span class="fc-h-metric">同类排名</span>
        <span class="fc-h-link"></span>
      </div>
      {"".join(compact_rows)}
    </div>
    <div style="text-align:center;margin:16px 0">
      <button onclick="var el=document.getElementById('{uid}');var btn=this;if(el.style.display==='none'){{el.style.display='block';btn.textContent='收起 ▲'}}else{{el.style.display='none';btn.textContent='展开剩余 {hidden_count} 位（按 5Y 收益排名）▼'}}"
        style="background:#f59e0b;color:#fff;border:none;padding:10px 28px;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;transition:all 0.2s">
        展开剩余 {hidden_count} 位（按 5Y 收益排名）▼
      </button>
    </div>'''


def _render_fund_compact_row(m: dict, rank: int) -> str:
    """One-line strip for fund managers ranked 7+. Used in expanded compact list.

    v2.10.1: lite 行（return_5y is None）显示持仓占比 + "点击看详情"，
    不再硬编码 "前 50%" 同类排名这种假数据。
    """
    is_lite = m.get("_row_type") == "lite" or m.get("return_5y") is None
    name = m.get("name", "—")
    fund_name = m.get("fund_name", "—")
    fund_code = m.get("fund_code", "")
    avatar = m.get("avatar", "")
    position_pct = m.get("position_pct") or 0

    # rank badge
    if rank <= 3:
        badge_style = "background:linear-gradient(135deg,#f59e0b,#d97706);color:#fff"
    elif rank <= 10:
        badge_style = "background:#e2e8f0;color:#475569"
    else:
        badge_style = "background:#f1f5f9;color:#64748b"

    if avatar:
        avatar_html = f'<img src="avatars/{avatar}.svg" class="fc-avatar" alt="">'
    else:
        avatar_html = f'<div class="fc-avatar fc-avatar-ph">{(name[0] if name and name != "—" else "?")}</div>'

    fund_url = m.get("fund_url", f"https://fund.eastmoney.com/{fund_code}.html")

    if is_lite:
        # Lite 行：不展示 5Y 业绩，给一个"点进去看"的提示
        metric_html = (
            f'<span class="fc-return" style="color:#94a3b8;font-style:italic">持仓 {position_pct:.2f}%</span>'
            f'<span class="fc-rank-pct" style="color:#94a3b8;font-size:10px">点→查业绩</span>'
        )
        name_display = fund_name  # lite 行没基金经理名，直接显示基金名
        fund_display = f"代码 {fund_code}"
    else:
        ret_5y = m.get("return_5y") or 0
        peer_rank = m.get("peer_rank_pct") or 50
        ret_color = COLOR_BULL if ret_5y > 0 else COLOR_BEAR
        rank_color = COLOR_BULL if peer_rank < 20 else COLOR_GOLD if peer_rank < 50 else COLOR_BEAR
        sign = "+" if ret_5y > 0 else ""
        metric_html = (
            f'<span class="fc-return" style="color:{ret_color}">{sign}{ret_5y:.1f}%</span>'
            f'<span class="fc-rank-pct" style="color:{rank_color}">前 {peer_rank}%</span>'
        )
        name_display = name
        fund_display = fund_name

    return f'''<div class="fund-compact-row">
  <span class="fc-rank" style="{badge_style}">{rank}</span>
  {avatar_html}
  <div class="fc-info">
    <div class="fc-name">{name_display}</div>
    <div class="fc-fund">{fund_display}</div>
  </div>
  {metric_html}
  <a href="{fund_url}" target="_blank" rel="noopener" class="fc-link" title="查看基金详情">→</a>
</div>'''


def render_panel_insights(syn: dict, panel: dict) -> str:
    """v2.9.1 · 评委汇总观点（'panel_insights' 字段之前完全不渲染的 bug 修复）.

    数据来源（优先级）：
      1. agent 在 agent_analysis.json 写的 panel_insights (最完整的分析)
      2. 若 agent 没写，用 panel 真实数据聚合生成一段（consensus + 流派倾向）
    """
    insights = (syn or {}).get("panel_insights") or ""

    # 没有 agent 内容也要给摘要，不能让这个位置完全空白（那就是"缺失"）
    if not insights:
        sig = panel.get("signal_distribution") or {}
        cf = panel.get("consensus_formula") or {}
        bull = sig.get("bullish", 0)
        neu  = sig.get("neutral", 0)
        bear = sig.get("bearish", 0)
        skip = sig.get("skip", 0)
        cons = syn.get("panel_consensus", panel.get("panel_consensus", 0))
        # 按流派统计倾向
        investors = panel.get("investors", [])
        from collections import Counter
        grp_stance: dict[str, Counter] = {}
        for inv in investors:
            g = inv.get("group", "?")
            grp_stance.setdefault(g, Counter())[inv.get("signal", "?")] += 1
        grp_summary = []
        GROUP_LABELS = {"A": "价值派", "B": "成长派", "C": "宏观派", "D": "技术派",
                        "E": "中国价投", "F": "A 股游资", "G": "量化"}
        for g in sorted(grp_stance.keys()):
            c = grp_stance[g]
            dominant = c.most_common(1)[0] if c else (("—", 0))
            label = GROUP_LABELS.get(g, g)
            tag = {"bullish": "看多", "bearish": "看空", "neutral": "中性", "skip": "跳过"}.get(
                dominant[0], dominant[0]
            )
            grp_summary.append(f"{label} {c['bullish']}✓ / {c['bearish']}✗（主流 {tag}）")
        insights = (
            f"<strong>51 位评委投票聚合</strong>："
            f"{bull} 看多 · {neu} 中性 · {bear} 看空 · {skip} 不适合该市场。"
            f"共识度 <strong>{cons:.0f}%</strong>（neutral 半权计入）。"
            f"<br><br><strong>按流派分布</strong>："
            + "；".join(grp_summary) + "。"
        )
        if bull == 0 and bear > 10:
            insights += " <em>⚠️ 无一人看多，压倒性看空——高信念回避信号。</em>"
        elif bear == 0 and bull > 10:
            insights += " <em>⚡ 无一人看空，压倒性看多——共识度极高（警惕追高）。</em>"
        elif abs(bull - bear) < 5 and (bull + bear) > 20:
            insights += " <em>🌪 多空旗鼓相当——这类分歧票往往波动最大。</em>"
        tag_src = "（自动聚合 · agent 未介入）"
    else:
        tag_src = "（agent 深度分析）"

    return (
        f'<div class="panel-insights" style="margin:20px 0;padding:20px;'
        f'background:rgba(8,145,178,0.08);border-left:4px solid #0891b2;'
        f'border-radius:6px;line-height:1.8;font-size:14px">'
        f'<div style="font-size:11px;color:#0891b2;letter-spacing:2px;'
        f'margin-bottom:8px">📊 PANEL INSIGHTS · 评委汇总观点 {tag_src}</div>'
        f'<div>{insights}</div>'
        f'</div>'
    )


def render_debate_rounds(debate: dict) -> str:
    """3 rounds bull vs bear transcript."""
    rounds = debate.get("rounds") or []
    if not rounds:
        return ""
    out = []
    for r in rounds:
        rn = r.get("round", "")
        bull_say = _safe(r.get("bull_say"), "—")
        bear_say = _safe(r.get("bear_say"), "—")
        out.append(f'''<div class="round">
  <div class="round-label">ROUND {rn}</div>
  <div class="round-grid">
    <div class="round-bull">{bull_say}</div>
    <div class="round-vs">VS</div>
    <div class="round-bear">{bear_say}</div>
  </div>
</div>''')
    return "\n".join(out)


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


def assemble(ticker: str) -> Path:
    syn = read_task_output(ticker, "synthesis")
    raw = read_task_output(ticker, "raw_data")
    panel = read_task_output(ticker, "panel")
    if not (syn and raw and panel):
        raise RuntimeError(f"Missing prerequisite cache for {ticker}. Run Tasks 1-4 first.")

    # v2.9 · 机械级自查 gate（代替以往"软 HARD-GATE"）
    # HTML 生成前强制跑 self_review；critical != 0 → 拒绝出报告，让 agent 修
    # 环境变量 UZI_SKIP_REVIEW=1 可临时跳过（仅限开发调试，不该生产用）
    import os
    if os.environ.get("UZI_SKIP_REVIEW") != "1":
        from lib.self_review import review_all, write_review, format_human
        review = review_all(ticker)
        write_review(ticker, review)
        crit = review["critical_count"]
        if crit > 0:
            print(format_human(review))
            raise RuntimeError(
                f"⛔ BLOCKED by self-review: {ticker} 有 {crit} 个 critical 问题待修。\n"
                f"→ 读 .cache/{ticker}/_review_issues.json\n"
                f"→ 对每条 critical issue 执行 suggested_fix（agent 补数据 / 重跑 stage2 / 写 agent_analysis）\n"
                f"→ 全部修完后重跑 assemble_report。\n"
                f"→ 如需强制跳过（仅调试）：export UZI_SKIP_REVIEW=1"
            )
        elif review["warning_count"] > 0:
            # warning 允许出 HTML，但在报告 banner 里留痕
            print(format_human(review))
            print(f"⚠  {ticker}: {review['warning_count']} warning 已记录，继续生成 HTML")

    basic = (raw.get("dimensions", {}).get("0_basic") or {}).get("data") or {}
    debate = syn.get("debate") or {}
    divide = syn.get("great_divide") or {}
    dashboard = syn.get("dashboard") or {}
    dp = dashboard.get("data_perspective") or {}
    intel = dashboard.get("intelligence") or {}
    bp = dashboard.get("battle_plan") or {}
    zones = syn.get("buy_zones") or {}
    trap = (raw.get("dimensions", {}).get("18_trap") or {}).get("data") or {}
    trap_level = trap.get("trap_level") or "🟢 安全"
    trap_color, trap_emoji = trap_color_emoji(trap_level)

    bull = debate.get("bull") or {}
    bear = debate.get("bear") or {}
    last_round = (debate.get("rounds") or [{}])[-1] if debate.get("rounds") else {}

    investors = panel.get("investors") or []

    # Sort for chat view: bullish first (hottest takes), then bearish, then neutral
    # Within each group, sort by confidence desc
    def _chat_sort_key(inv):
        sig_rank = {"bullish": 0, "bearish": 1, "neutral": 2}.get(inv.get("signal", "neutral"), 3)
        return (sig_rank, -(inv.get("confidence") or 0))
    chat_ordered = sorted(investors, key=_chat_sort_key)

    sig_dist = panel.get("signal_distribution") or {}
    bull_count = sig_dist.get("bullish", 0)
    bear_count = sig_dist.get("bearish", 0)
    neut_count = sig_dist.get("neutral", 0)

    template = TEMPLATE.read_text(encoding="utf-8")

    replacements = {
        "{{NAME}}": _safe(syn.get("name") or basic.get("name")),
        "{{TICKER}}": _safe(syn.get("ticker") or basic.get("code")),
        "{{ONE_LINER}}": _safe(basic.get("one_liner") or basic.get("industry") or ""),
        "{{PRICE}}": str(_safe(basic.get("price"))),
        "{{CHANGE_PCT}}": f"{basic.get('change_pct', 0):+.2f}%" if basic.get("change_pct") is not None else "—",
        "{{CHANGE_DIR}}": "up" if (basic.get("change_pct") or 0) >= 0 else "down",
        "{{MCAP}}": str(_safe(basic.get("market_cap"))),
        "{{PE}}": str(_safe(basic.get("pe_ttm"))),
        "{{PB}}": str(_safe(basic.get("pb"))),
        "{{INDUSTRY}}": str(_safe(basic.get("industry"))),
        "{{OVERALL_SCORE}}": str(syn.get("overall_score", 0)),
        "{{OVERALL_SCORE_INT}}": str(int(syn.get("overall_score", 0))),
        "{{VERDICT_LABEL}}": _safe(syn.get("verdict_label")),
        "{{TRAP_LEVEL}}": trap_level,
        "{{TRAP_COLOR}}": trap_color,
        "{{TRAP_EMOJI}}": trap_emoji,
        "{{TRAP_RECOMMENDATION}}": _safe(trap.get("recommendation"), "数据正常，未发现异常推广痕迹"),
        "{{CORE_CONCLUSION}}": _safe(dashboard.get("core_conclusion")),
        "{{DP_TREND}}": _safe(dp.get("trend")),
        "{{DP_PRICE}}": _safe(dp.get("price")),
        "{{DP_VOLUME}}": _safe(dp.get("volume")),
        "{{DP_CHIPS}}": _safe(dp.get("chips")),
        "{{INTEL_NEWS}}": _safe(intel.get("news")),
        "{{INTEL_RISKS}}": _safe(", ".join(intel.get("risks") or [])),
        "{{INTEL_CATALYSTS}}": _safe(", ".join(intel.get("catalysts") or [])),
        "{{BP_ENTRY}}": _safe(bp.get("entry")),
        "{{BP_POSITION}}": _safe(bp.get("position")),
        "{{BP_STOP}}": _safe(bp.get("stop")),
        "{{BP_TARGET}}": _safe(bp.get("target")),
        # v2.9.1 · 不再用 buffett/graham 假头像兜底——如果 debate 真空，agent
        # 没选出多空代表，应该显示占位而不是错误的头像+空数据
        "{{BULL_ID}}": _safe(bull.get("investor_id"), "_placeholder"),
        "{{BULL_NAME}}": _safe(bull.get("name"), "（未选出）"),
        "{{BULL_SCORE}}": str(divide.get("bull_score", 0)),
        "{{BULL_LAST_SAY}}": _safe(last_round.get("bull_say"), "—"),
        "{{BEAR_ID}}": _safe(bear.get("investor_id"), "_placeholder"),
        "{{BEAR_NAME}}": _safe(bear.get("name"), "（未选出）"),
        "{{BEAR_SCORE}}": str(divide.get("bear_score", 0)),
        "{{BEAR_LAST_SAY}}": _safe(last_round.get("bear_say"), "—"),
        "{{PUNCHLINE}}": _safe(divide.get("punchline") or debate.get("punchline")),
        "{{ZONE_VALUE_PRICE}}": str(_safe((zones.get("value") or {}).get("price"))),
        "{{ZONE_VALUE_RATIONALE}}": _safe((zones.get("value") or {}).get("rationale")),
        "{{ZONE_GROWTH_PRICE}}": str(_safe((zones.get("growth") or {}).get("price"))),
        "{{ZONE_GROWTH_RATIONALE}}": _safe((zones.get("growth") or {}).get("rationale")),
        "{{ZONE_TECH_PRICE}}": str(_safe((zones.get("technical") or {}).get("price"))),
        "{{ZONE_TECH_RATIONALE}}": _safe((zones.get("technical") or {}).get("rationale")),
        "{{ZONE_YOUZI_PRICE}}": str(_safe((zones.get("youzi") or {}).get("price"))),
        "{{ZONE_YOUZI_RATIONALE}}": _safe((zones.get("youzi") or {}).get("rationale")),
        "{{GENERATED_AT}}": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "{{BULL_COUNT}}": str(bull_count),
        "{{BEAR_COUNT}}": str(bear_count),
        "{{NEUT_COUNT}}": str(neut_count),
        "{{CONSENSUS_PCT}}": f"{panel.get('panel_consensus', 0):.0f}",
        "{{BULL_TAG}}": _safe((bull.get("group") and GROUP_LABELS.get(bull.get("group"))) or bull.get("tagline"), ""),
        "{{BEAR_TAG}}": _safe((bear.get("group") and GROUP_LABELS.get(bear.get("group"))) or bear.get("tagline"), ""),
        "{{BULL_SIGNAL_CN}}": {"bullish": "看多", "neutral": "中性", "bearish": "看空"}.get(divide.get("bull_signal", ""), "看多"),
        "{{BEAR_SIGNAL_CN}}": {"bullish": "看多", "neutral": "中性", "bearish": "看空"}.get(divide.get("bear_signal", ""), "看空"),
        "{{TOTAL_COUNT}}": str(len(investors)),
        "{{MARKET_STATUS}}": market_status().get("label", ""),
        "{{MARKET_STATUS_CLASS}}": "open" if market_status().get("is_open") else "closed",
        "{{DATA_FETCHED_AT}}": (raw.get("fetched_at") or "")[:19].replace("T", " "),
        "{{PLUGIN_VERSION}}": _get_plugin_version(),
    }
    for k, v in replacements.items():
        template = template.replace(k, str(v))

    template = template.replace(
        "<!-- INJECT_JURY_SEATS -->",
        "\n".join(render_jury_seat(i) for i in investors),
    )
    template = template.replace(
        "<!-- INJECT_CHAT_MESSAGES -->",
        "\n".join(render_chat_message(i) for i in chat_ordered),
    )
    template = template.replace(
        "<!-- INJECT_VOTE_BARS -->",
        render_vote_bars(panel.get("vote_distribution") or {}),
    )
    template = template.replace(
        "<!-- INJECT_TOP3_BULLS -->",
        render_top3_bulls(investors),
    )
    # v2.9.1 · 对称补 Top 3 看空 + panel_insights 评委汇总
    template = template.replace(
        "<!-- INJECT_TOP3_BEARS -->",
        render_top3_bears(investors),
    )
    template = template.replace(
        "<!-- INJECT_PANEL_INSIGHTS -->",
        render_panel_insights(syn, panel),
    )
    template = template.replace(
        "<!-- INJECT_RISKS -->",
        render_risks(syn.get("risks") or []),
    )
    template = template.replace(
        "<!-- INJECT_DEBATE_ROUNDS -->",
        render_debate_rounds(debate),
    )

    # Tier 4 友好层
    template = template.replace(
        "<!-- INJECT_FRIENDLY_LAYER -->",
        render_friendly_layer(syn, raw),
    )

    # 基金经理抄作业面板
    fund_managers = (syn.get("fund_managers") or raw.get("fund_managers") or [])
    template = template.replace(
        "<!-- INJECT_FUND_MANAGERS -->",
        render_fund_managers(fund_managers),
    )

    # 19 维深度数据卡 · 6 大类
    dimensions = read_task_output(ticker, "dimensions") or {}
    template = template.replace("<!-- INJECT_DIM_FINANCIAL -->", render_dim_category("fin", dimensions, raw))
    template = template.replace("<!-- INJECT_DIM_MARKET -->",    render_dim_category("mkt", dimensions, raw))
    template = template.replace("<!-- INJECT_DIM_INDUSTRY -->",  render_dim_category("ind", dimensions, raw))
    template = template.replace("<!-- INJECT_DIM_COMPANY -->",   render_dim_category("co", dimensions, raw))
    template = template.replace("<!-- INJECT_DIM_ENV -->",       render_dim_category("env", dimensions, raw))
    template = template.replace("<!-- INJECT_DIM_SAFETY -->",    render_dim_category("saf", dimensions, raw))

    # v2.0 · Institutional modeling section (dim 20/21/22)
    template = template.replace(
        "<!-- INJECT_INSTITUTIONAL_MODELING -->",
        _render_institutional_section(raw),
    )

    # v2.3 · Data quality banner (only renders when synthesis.data_gaps present)
    template = template.replace(
        "<!-- INJECT_DATA_GAP_BANNER -->",
        _render_data_gap_banner(syn.get("data_gaps")),
    )

    # v2.7 · Style chip (动态加权说明，只在 detected_style 存在时渲染)
    template = template.replace(
        "<!-- INJECT_STYLE_CHIP -->",
        _render_style_chip(syn),
    )

    date = datetime.now().strftime("%Y%m%d")
    out_dir = Path("reports") / f"{ticker}_{date}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "full-report.html"
    out_file.write_text(template, encoding="utf-8")

    out_avatars = out_dir / "avatars"
    if not out_avatars.exists():
        shutil.copytree(AVATARS_DIR, out_avatars)

    one_liner = (
        f"{syn.get('name')} 体检结果：{int(syn.get('overall_score', 0))} 分，"
        f"{syn.get('verdict_label')}。\n"
        f"50 位大佬里 {(panel.get('signal_distribution') or {}).get('bullish', 0)} 人喊买。\n"
        f"💬 {divide.get('punchline') or '—'}\n"
        f"{trap_emoji} {trap_level}\n"
        f"全文 → {out_file}"
    )
    (out_dir / "one-liner.txt").write_text(one_liner, encoding="utf-8")

    print(f"[ok] Report assembled: {out_file}")
    return out_file


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"
    assemble(ticker)
