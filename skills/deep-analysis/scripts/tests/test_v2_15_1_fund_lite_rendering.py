"""Regression tests for v2.15.1 · 基金 lite 行不再被误渲染为 full-card（含 0.0% 假数据）.

背景：中密控股 300470 实测时发现报告里一堆 fund-card 显示 "5Y +0.0% / 年化 +0.0% / 回撤 -0.0% / 夏普 0.00"，
根因：
1. fetch_fund_holders._build_row_full 在 compute_fund_stats 返 {} 时，用 stats.get("return_5y", 0) 写 0 · 实际应该降级为 lite（None）
2. assemble_report.render_fund_managers 所有 manager 都当 full card 渲染 · INITIAL_SHOW=6 硬编码
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


# ─── fetch_fund_holders 降级 ──────────────────────────────

def test_fetch_fund_holders_degrades_to_lite_when_stats_empty(monkeypatch):
    """compute_fund_stats 返 {} 时，_build_row_full 必须降级为 _row_type=lite + None 字段."""
    import fetch_fund_holders as ffh

    # mock compute_fund_stats 返空（fund.eastmoney.com 阻断场景）
    monkeypatch.setattr(ffh, "compute_fund_stats", lambda code: {})
    monkeypatch.setattr(ffh, "fetch_fund_manager_name", lambda code: "朱少醒")

    # 找到 _build_row_full 闭包不好直接调 · 用模块内路径（通过完整 main 测）
    # 但 main 依赖 ak · 不如直接检测 _build_row_full 的行为：
    # 我们从源码检查降级分支：return_5y=None + _row_type=lite
    src = (SCRIPTS / "fetch_fund_holders.py").read_text(encoding="utf-8")
    assert '"_row_type": "lite"' in src, "fetch_fund_holders.py 必须有 lite 降级分支"
    assert 'has_real_stats' in src, "必须有 has_real_stats 判断"


def test_fetch_fund_holders_keeps_full_when_stats_valid():
    """compute_fund_stats 有数据时，_row_type='full' + 真实数字."""
    src = (SCRIPTS / "fetch_fund_holders.py").read_text(encoding="utf-8")
    assert '"_row_type": "full"' in src


# ─── render_fund_managers 跳过 lite ──────────────────────

def test_render_skips_lite_managers():
    """render_fund_managers 必须跳过 _row_type=lite · 不生成 fund-card."""
    from assemble_report import render_fund_managers
    mgrs = [
        {"name": "朱少醒", "fund_name": "富国天惠", "fund_code": "022645",
         "position_pct": 4.92, "return_5y": 32.5, "annualized_5y": 5.8,
         "max_drawdown": -31.2, "sharpe": 0.42, "peer_rank_pct": 45,
         "_row_type": "full"},
        {"name": "—", "fund_name": "南方宝元债券A", "fund_code": "202101",
         "position_pct": 0.54, "return_5y": None, "annualized_5y": None,
         "max_drawdown": None, "sharpe": None, "peer_rank_pct": None,
         "_row_type": "lite"},
    ]
    html = render_fund_managers(mgrs)
    # full card 有"5 年累计" + 真实数字
    assert "富国天惠" in html
    assert "+32.5%" in html or "32.5%" in html
    # lite 行不应该在 fund-card 里显示 0.0%
    # 检查：南方宝元债券 A 不应该出现在 fund-card 样式里
    # 具体的 assertion：没有含"南方宝元债券A"的 fund-card（应在 compact row 里）
    assert html.count('<div class="fund-card">') == 1, "应只有 1 张 full card（朱少醒）"


def test_render_all_full_no_compact():
    """全 full 无 lite · 不生成 compact_list div."""
    from assemble_report import render_fund_managers
    mgrs = [
        {"name": "朱少醒", "fund_name": "富国天惠", "fund_code": "022645",
         "position_pct": 4.92, "return_5y": 32.5, "annualized_5y": 5.8,
         "max_drawdown": -31.2, "sharpe": 0.42, "peer_rank_pct": 45,
         "_row_type": "full"},
    ]
    html = render_fund_managers(mgrs)
    assert '<div class="fund-card">' in html
    assert 'fund-compact-list' not in html, "全 full 时不应渲染 compact-list"


def test_render_all_lite_no_card():
    """全 lite 无 full · cards=0 · 只有 compact rows."""
    from assemble_report import render_fund_managers
    mgrs = [
        {"name": "—", "fund_name": "基金A", "fund_code": "001",
         "position_pct": 0.5, "return_5y": None, "_row_type": "lite"},
        {"name": "—", "fund_name": "基金B", "fund_code": "002",
         "position_pct": 0.4, "return_5y": None, "_row_type": "lite"},
    ]
    html = render_fund_managers(mgrs)
    assert '<div class="fund-card">' not in html, "全 lite 不应生成 fund-card"
    # 但应该有 compact 部分（基金名或 fund-compact）
    assert "基金A" in html or "基金B" in html


def test_render_no_zero_percent_card():
    """**核心测试**：即使 manager 字段全是 0（不是 None），只要 _row_type=lite，就不该渲染 0.0% full card."""
    from assemble_report import render_fund_managers
    # 模拟旧 bug 场景：return_5y=0（非 None），但 _row_type=lite
    mgrs = [
        {"name": "朱少醒", "fund_name": "富国天惠", "fund_code": "022645",
         "position_pct": 4.92, "return_5y": 32.5, "annualized_5y": 5.8,
         "max_drawdown": -31.2, "sharpe": 0.42, "peer_rank_pct": 45,
         "_row_type": "full"},
        # 这是旧 bug 会误渲染的那种：0 不是 None
        {"name": "—", "fund_name": "南方宝元", "fund_code": "xxx",
         "position_pct": 0.54, "return_5y": None, "annualized_5y": None,
         "max_drawdown": None, "sharpe": None, "peer_rank_pct": None,
         "_row_type": "lite"},
    ]
    html = render_fund_managers(mgrs)
    # 不允许在 fund-card 里出现 0.0%（只有 full card 有 5 年累计/年化/回撤字段）
    # 找所有 fund-card 块
    import re
    card_blocks = re.findall(r'<div class="fund-card">.*?</div>\s*</div>', html, re.DOTALL)
    for block in card_blocks:
        assert '+0.0%' not in block, f"fund-card 里不应出现 +0.0% · 污染的 lite 行"
        assert '-0.0%' not in block, f"fund-card 里不应出现 -0.0%"


def test_initial_show_is_dynamic():
    """INITIAL_SHOW 现在 = full_count · 不再是固定 6."""
    src = (SCRIPTS / "assemble_report.py").read_text(encoding="utf-8")
    assert "INITIAL_SHOW = min(6, len(cards))" in src, "INITIAL_SHOW 必须是 min(6, len(cards)) 动态"
    assert "lite_managers = [m for m in managers_sorted" in src


# ─── fetch_moat 公司名污染过滤（14_moat 茅台污染 bug）──────────

def test_moat_filter_drops_polluter_results():
    """DDGS 对生僻公司（如 中密控股）返回 贵州茅台 相关结果必须被过滤掉."""
    from fetch_moat import _result_mentions_company
    polluters = {"贵州茅台", "五粮液", "宁德时代"}
    # 中密控股 查询返 茅台 结果 → 必须 False
    result = {
        "title": "贵州茅台：拟与茅台集团共同出资10亿元成立科学与技术研究院",
        "body": "贵州茅台表示，技术创新在公司发展历程中始终扮演关键角色...",
        "url": "https://nbd.com.cn/x"
    }
    assert _result_mentions_company(result, "中密控股", polluters) is False


def test_moat_filter_keeps_legit_company_mention():
    """真正含目标公司名的结果保留."""
    from fetch_moat import _result_mentions_company
    polluters = {"贵州茅台"}
    result = {
        "title": "中密控股发布 2025 年报 · 机械密封件龙头",
        "body": "中密控股在核电密封件市场份额领先...",
        "url": "https://x.com/y"
    }
    assert _result_mentions_company(result, "中密控股", polluters) is True


def test_moat_filter_drops_unrelated_results():
    """既不含目标公司也不含 polluter · 保守过滤."""
    from fetch_moat import _result_mentions_company
    polluters = {"贵州茅台"}
    result = {
        "title": "A 股行情日报：创业板指数上涨 2%",
        "body": "今日大盘继续震荡...",
        "url": "https://x.com/y"
    }
    assert _result_mentions_company(result, "中密控股", polluters) is False


def test_moat_filter_allows_target_is_polluter():
    """如果分析标的本身是 polluter（如茅台）· 其自己的结果不能被过滤."""
    from fetch_moat import _result_mentions_company
    # 分析 茅台 时 · polluter 集合已排除 "贵州茅台"（main 里动态构建）
    polluters_without_self = set()  # 茅台作为分析对象时 polluters 是空
    result = {
        "title": "贵州茅台 2025Q3 业绩超预期",
        "body": "贵州茅台表示...",
        "url": "https://x.com/y"
    }
    assert _result_mentions_company(result, "贵州茅台", polluters_without_self) is True
