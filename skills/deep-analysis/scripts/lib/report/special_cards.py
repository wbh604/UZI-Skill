"""report.special_cards · 特殊功能卡片 · v3.2 从 assemble_report.py 抽离.

### 内容
- `render_friendly_layer(syn, raw)` · 一万块场景模拟 + exit triggers + 类似股票
- `render_fund_managers(managers)` · 基金经理抄作业（重点修复区 v2.15.1/v2.15.2）
- `_render_fund_compact_row(m, rank)` · fund_managers 的紧凑行变体
- `render_panel_insights(syn, panel)` · 评委汇总观点
- `render_school_scores(syn, panel)` · 7 大流派各自评分（v2.15.4 / v2.15.5）
- `render_debate_rounds(debate)` · 多空辩论 3 回合

### 依赖
- `lib.report.svg_primitives` · svg 图元
- `lib.report.institutional.trap_color_emoji` · friendly_layer 用

### 为什么搬出来
特殊卡片各自独立 · ~506 行 · 没被 render_dim_card 通用渲染链用 · 适合独立文件.
v2.15.1/2/4/5 hotfix 都在 fund_managers + school_scores 这块 · 独立文件后续更好维护.

### 向后兼容
assemble_report.py 做 re-export · 所有历史调用不变.
"""
from __future__ import annotations

from lib.report.svg_primitives import (
    COLOR_BULL, COLOR_BEAR, COLOR_GOLD, COLOR_CYAN,
    COLOR_BLUE, COLOR_PINK, COLOR_INDIGO, COLOR_MUTED, COLOR_GRID,
    svg_sparkline, svg_progress_row, svg_donut,
)
from lib.report.institutional import trap_color_emoji


def _safe(v, default="—"):
    """local helper · 避免循环 import."""
    if v is None or v == "" or v == "—":
        return default
    return v


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


def render_school_scores(syn: dict, panel: dict) -> str:
    """v2.15.4 · 按流派打分卡片.

    7 个流派 (A-G) 各自给出 consensus / avg_score / verdict ·
    一眼看出不同哲学在该票上的分歧（e.g. 价值派高分 but 技术派低分 → 白马但趋势坏）.
    数据源优先 synthesis.school_scores · fallback panel.school_scores.
    """
    school = (syn or {}).get("school_scores") or (panel or {}).get("school_scores") or {}
    if not school:
        return ""

    # verdict → 配色（和总评一致的语义）
    VERDICT_COLOR = {
        "重仓": ("#065f46", "rgba(16,185,129,0.15)"),  # 深绿
        "买入": ("#047857", "rgba(16,185,129,0.10)"),  # 绿
        "关注": ("#b45309", "rgba(245,158,11,0.10)"),  # 琥珀
        "谨慎": ("#b91c1c", "rgba(239,68,68,0.10)"),   # 淡红
        "回避": ("#991b1b", "rgba(239,68,68,0.18)"),   # 深红
        "不适合": ("#6b7280", "rgba(107,114,128,0.10)"),  # 灰
    }
    SIG_ICON = {"bullish": "📈", "bearish": "📉", "neutral": "⚖️", "skip": "—"}

    # 按 group 字母顺序排列（A-G）· 保留顺序稳定
    order = ["A", "B", "C", "D", "E", "F", "G"]
    items = []
    for g in order:
        s = school.get(g)
        if not s:
            continue
        label = s.get("label", g)
        cons = s.get("consensus", 0)
        avg = s.get("avg_score", 0)
        score_mean = s.get("score_mean", avg)     # v2.15.5 分量
        vote_cons = s.get("vote_consensus", cons)  # v2.15.5 分量
        verdict = s.get("verdict", "—")
        n_members = s.get("n_members", 0)
        n_active = s.get("n_active", 0)
        bull = s.get("bullish", 0)
        neu = s.get("neutral", 0)
        bear = s.get("bearish", 0)
        skip = s.get("skip", 0)
        desc = s.get("desc", "")
        dom = s.get("dominant_signal", "skip")
        fg, bg = VERDICT_COLOR.get(verdict, ("#374151", "rgba(107,114,128,0.10)"))
        icon = SIG_ICON.get(dom, "")

        # 柱状共识度（0-100）· 用 linear-gradient 直观表达
        bar_fill = max(0, min(100, cons))
        # v2.15.5 · 分量 tooltip：让鼠标悬停能看到"实分 x.x · 投票 y.y"
        tip = f"score_mean={score_mean:.1f} · vote_weighted={vote_cons:.1f} · 极化后 {cons:.1f}"
    # compute skip display before f-string to avoid nested f-string syntax error
    skip_display = f'<span style="color:#9ca3af">—{skip}</span>' if skip else ''
    items.append(
        f'<div title="{tip}" style="background:{bg};border-radius:8px;padding:14px 16px;'
        f'border:1px solid rgba(0,0,0,0.05)">'
        f'  <div style="display:flex;justify-content:space-between;align-items:baseline">'
        f'    <div style="font-weight:600;font-size:14px;color:{fg}">'
        f'      {icon} {label} <span style="font-weight:400;font-size:11px;color:#9ca3af">· {n_members} 人</span>'
        f'    </div>'
        f'    <div style="font-size:11px;color:{fg};font-weight:600;letter-spacing:1px">{verdict}</div>'
        f'  </div>'
        f'  <div style="margin-top:6px;font-size:11px;color:#6b7280">{desc}</div>'
        f'  <div style="display:flex;gap:12px;margin-top:10px;align-items:center">'
        f'    <div style="flex:1">'
        f'      <div style="height:6px;background:rgba(0,0,0,0.06);border-radius:3px;overflow:hidden">'
        f'        <div style="height:100%;width:{bar_fill}%;background:linear-gradient(90deg,{fg} 0%,{fg} 100%);opacity:0.75"></div>'
        f'      </div>'
        f'      <div style="font-size:10px;color:#9ca3af;margin-top:3px">'
        f'        流派分 <strong style="color:{fg};font-size:12px">{cons:.1f}</strong>'
        f'        <span style="color:#d1d5db"> · 实分均值 {score_mean:.1f} · 投票共识 {vote_cons:.0f}%</span>'
        f'      </div>'
        f'    </div>'
        f'    <div style="font-size:11px;color:#374151;white-space:nowrap">'
        f'      <span style="color:#059669">📈{bull}</span> · '
        f'      <span style="color:#6b7280">⚖️{neu}</span> · '
        f'      <span style="color:#dc2626">📉{bear}</span>'
        f'      {skip_display}'
        f'    </div>'
        f'  </div>'
        f'</div>'
    )

    if not items:
        return ""

    return (
        f'<div class="school-scores" style="margin:20px 0;padding:20px;'
        f'background:rgba(139,92,246,0.06);border-left:4px solid #8b5cf6;'
        f'border-radius:6px">'
        f'  <div style="font-size:11px;color:#7c3aed;letter-spacing:2px;'
        f'margin-bottom:4px">🎭 SCHOOL SCORES · 七大流派各自评分</div>'
        f'  <div style="font-size:12px;color:#6b7280;margin-bottom:14px">'
        f'混合打分 = 0.65 × 实分均值 + 0.35 × 投票共识 · 再做极化拉伸(k=1.3) · '
        f'不同哲学给出不同分数 · 分歧越大意味着结论越不稳 · 鼠标悬停查看分量'
        f'  </div>'
        f'  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px">'
        + "".join(items) +
        f'  </div>'
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
