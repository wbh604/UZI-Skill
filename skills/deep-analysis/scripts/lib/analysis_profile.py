"""三档思考深度 · v2.10.2.

用户选择 `lite / medium / deep`，决定所有下游子系统的行为：
  - fetcher 集合（跑哪几维）
  - 评委数量（10/51/51+辩论）
  - 机构方法（1/17/18）
  - ddgs / agent 深度分析（全 skip / 按需 / 跑满）
  - fund_holders 策略（top 5/20/all）
  - 自查 gate 严格度

使用:
  from lib.analysis_profile import get_profile, DEPTH_LITE, DEPTH_MEDIUM, DEPTH_DEEP

  profile = get_profile()         # 从 UZI_DEPTH env 读，默认 medium
  profile = get_profile("lite")   # 显式指定

  if profile.should_run_fetcher("3_macro"):
      ...

CLI 集成（run.py）:
  python run.py 600519 --depth lite
  UZI_DEPTH=deep python run.py 600519

兼容:
  - UZI_LITE=1 向后兼容 → 等价于 UZI_DEPTH=lite
  - /quick-scan 隐式 depth=lite
  - /ic-memo / /initiate 隐式 depth=deep
  - /analyze-stock 默认 depth=medium
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

Depth = Literal["lite", "medium", "deep"]

DEPTH_LITE: Depth = "lite"
DEPTH_MEDIUM: Depth = "medium"
DEPTH_DEEP: Depth = "deep"


@dataclass(frozen=True)
class AnalysisProfile:
    depth: Depth
    label_cn: str
    estimated_minutes: str

    # === Fetcher 层 ===
    # 哪些 fetcher 跑 · 未列出的 skip
    fetchers_enabled: frozenset[str]
    # ddgs / web_search 预算上限（lib.web_search 读此值）
    ddg_budget: int
    # fetch_industry 是否跑 dynamic search_trusted (~3-9 次 ddgs)
    industry_dynamic_lookup: bool

    # === Panel 层 ===
    # 参与投票的评委数量（按 investor_db 前 N 或流派采样）
    investors_count: int
    # 是否启用 Bull-Bear 结构化辩论（v2.10.2 deep 才有）
    enable_bull_bear_debate: bool

    # === 机构方法层 ===
    # 跑哪几种机构方法
    institutional_methods: frozenset[str]
    # Segmental Revenue Build-Up（v2.10 新方法）
    enable_segmental_model: bool
    # Owner Earnings / Narrative Gap（v2.10.2 planned）
    enable_owner_earnings: bool
    enable_narrative_gap: bool

    # === Fund holders 策略 ===
    # 头部几家算完整 5Y 业绩
    fund_stats_top_n: int
    # 是否展开其余家的 lite 清单
    fund_lite_list_enabled: bool

    # === Agent 深度分析 ===
    # 6 维定性（3_macro / 13_policy / 14_moat / 15_events / 17_sentiment / 18_trap）是否要求 agent 深度介入
    require_qualitative_deep_dive: bool

    # === Self-review gate ===
    # warning 是否也 block HTML 生成
    self_review_block_warnings: bool

    # === v2.13.0 · Playwright 兜底层 ===
    # Playwright 通用兜底策略 · 按三档分级
    #   'off'      → 完全禁用（lite · 保持快扫）
    #   'opt-in'   → UZI_PLAYWRIGHT_ENABLE=1 / --enable-playwright 才启用（medium）
    #               · 未装时打印安装命令，本次跳过（不自动装）
    #   'default'  → 默认启用（deep · 用户选 deep 已同意深挖）
    #               · 未装时交互式询问 y/n，同意后自动装
    playwright_mode: str = "off"

    # 本档启用 Playwright 兜底时覆盖的维度白名单
    # 只对这些维度在主链失败后尝试浏览器抓取
    playwright_dims: frozenset[str] = frozenset()


# ═══════════════════════════════════════════════════════════════
# Profile 定义
# ═══════════════════════════════════════════════════════════════

# v2.13.0 · Playwright 兜底覆盖的维度（按档位）
# medium opt-in · 4 维最痛（Codex review 后砍掉 7_industry · 百度搜索信噪比差）
_PLAYWRIGHT_MEDIUM_DIMS = frozenset({"4_peers", "8_materials", "15_events", "17_sentiment"})
# deep default · medium 4 维 + 3_macro（stats.gov.cn 官方页 · 权威且无反爬）
# 注：Codex review 后明确排除 14_moat（百度百科质量差）/ 13_policy（ddgs site: 够用）/
#     18_trap（小红书抖音反爬+UGC 合规）/ 19_contests（UZI_XQ_LOGIN 专用路径已有）
_PLAYWRIGHT_DEEP_DIMS = _PLAYWRIGHT_MEDIUM_DIMS | frozenset({"3_macro"})

_CORE_FETCHERS = frozenset({
    "0_basic", "1_financials", "2_kline",
    "10_valuation", "11_governance", "15_events", "16_lhb",
})
_ALL_FETCHERS = frozenset({
    "0_basic", "1_financials", "2_kline", "3_macro", "4_peers", "5_chain",
    "6_research", "7_industry", "8_materials", "9_futures", "10_valuation",
    "11_governance", "12_capital_flow", "13_policy", "14_moat", "15_events",
    "16_lhb", "17_sentiment", "18_trap", "19_contests",
})

_PROFILES: dict[str, AnalysisProfile] = {
    DEPTH_LITE: AnalysisProfile(
        depth=DEPTH_LITE,
        label_cn="速判模式",
        estimated_minutes="1-2 分钟",
        fetchers_enabled=_CORE_FETCHERS,
        ddg_budget=0,                     # 全 skip
        industry_dynamic_lookup=False,
        investors_count=10,
        enable_bull_bear_debate=False,
        institutional_methods=frozenset({"dcf"}),
        enable_segmental_model=False,
        enable_owner_earnings=False,
        enable_narrative_gap=False,
        fund_stats_top_n=5,
        fund_lite_list_enabled=False,    # 不展开全量清单
        require_qualitative_deep_dive=False,
        self_review_block_warnings=False,
        playwright_mode="off",             # v2.13.0 · 保持 lite 快扫 · 不用浏览器
        playwright_dims=frozenset(),
    ),
    DEPTH_MEDIUM: AnalysisProfile(
        depth=DEPTH_MEDIUM,
        label_cn="标准分析",
        estimated_minutes="5-8 分钟",
        fetchers_enabled=_ALL_FETCHERS,
        ddg_budget=30,                    # 标准预算
        industry_dynamic_lookup=True,
        investors_count=51,
        enable_bull_bear_debate=False,
        institutional_methods=frozenset({
            "dcf", "comps", "lbo", "three_statement", "merger",
            "initiating", "earnings", "catalysts", "thesis", "morning", "screen", "sector",
            "ic_memo", "porter_bcg", "dd", "unit_economics", "portfolio_rebalance",
        }),
        enable_segmental_model=False,
        enable_owner_earnings=False,
        enable_narrative_gap=False,
        fund_stats_top_n=20,
        fund_lite_list_enabled=True,
        require_qualitative_deep_dive=True,
        self_review_block_warnings=False,
        playwright_mode="opt-in",          # v2.13.0 · UZI_PLAYWRIGHT_ENABLE=1 启用 · 未装时提示命令
        playwright_dims=_PLAYWRIGHT_MEDIUM_DIMS,
    ),
    DEPTH_DEEP: AnalysisProfile(
        depth=DEPTH_DEEP,
        label_cn="深度研究",
        estimated_minutes="15-20 分钟",
        fetchers_enabled=_ALL_FETCHERS,
        ddg_budget=60,                    # 允许跑满
        industry_dynamic_lookup=True,
        investors_count=51,
        enable_bull_bear_debate=True,     # ← deep 独享
        institutional_methods=frozenset({
            "dcf", "comps", "lbo", "three_statement", "merger",
            "initiating", "earnings", "catalysts", "thesis", "morning", "screen", "sector",
            "ic_memo", "porter_bcg", "dd", "unit_economics", "portfolio_rebalance",
            "segmental",  # v2.10 新方法
        }),
        enable_segmental_model=True,
        enable_owner_earnings=True,       # v2.10.2 planned
        enable_narrative_gap=True,         # v2.10.2 planned
        fund_stats_top_n=100,              # deep 给前 100 家完整
        fund_lite_list_enabled=True,
        require_qualitative_deep_dive=True,
        self_review_block_warnings=True,   # ← deep: warning 也 block
        playwright_mode="default",         # v2.13.0 · 默认启用 · 未装时 y/n 交互确认
        playwright_dims=_PLAYWRIGHT_DEEP_DIMS,
    ),
}


def get_profile(depth: str | None = None) -> AnalysisProfile:
    """取当前 profile.

    参数:
      depth: 显式指定 lite/medium/deep；None 时从 UZI_DEPTH env 读（默认 medium）

    向后兼容:
      UZI_LITE=1 → 等价 depth=lite
      UZI_LITE=0 → 等价 depth=medium（不强制 deep）
    """
    if depth is None:
        depth = os.environ.get("UZI_DEPTH")
        # 兼容老的 UZI_LITE
        if depth is None:
            lite_env = os.environ.get("UZI_LITE", "auto").lower()
            if lite_env in ("1", "true", "yes", "on"):
                depth = DEPTH_LITE
            else:
                depth = DEPTH_MEDIUM
    depth = (depth or DEPTH_MEDIUM).lower()
    if depth not in _PROFILES:
        raise ValueError(f"unknown depth {depth!r}; expected one of {list(_PROFILES.keys())}")
    return _PROFILES[depth]


def apply_profile_to_env(profile: AnalysisProfile) -> None:
    """把 profile 同步到下游子系统读的环境变量."""
    os.environ["UZI_DEPTH"] = profile.depth
    os.environ["UZI_LITE"] = "1" if profile.depth == DEPTH_LITE else "0"
    os.environ["UZI_DDG_BUDGET"] = str(profile.ddg_budget) if profile.ddg_budget > 0 else "0"
    os.environ["UZI_FUND_STATS_TOP"] = str(profile.fund_stats_top_n)


def format_banner(profile: AnalysisProfile) -> str:
    """启动时打印的 banner."""
    icons = {DEPTH_LITE: "⚡", DEPTH_MEDIUM: "📊", DEPTH_DEEP: "🔬"}
    icon = icons.get(profile.depth, "·")
    lines = [
        f"{icon} {profile.label_cn} · depth={profile.depth} · 预计 {profile.estimated_minutes}",
        f"  · fetchers: {len(profile.fetchers_enabled)}/{len(_ALL_FETCHERS)} 维",
        f"  · 评委: {profile.investors_count} 位" + ("（含 Bull-Bear 辩论）" if profile.enable_bull_bear_debate else ""),
        f"  · 机构方法: {len(profile.institutional_methods)} 种",
        f"  · ddgs 预算: {'无限' if profile.ddg_budget == 0 and profile.depth != DEPTH_LITE else profile.ddg_budget}",
        f"  · fund_holders: 头部 {profile.fund_stats_top_n} 家完整",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    for d in (DEPTH_LITE, DEPTH_MEDIUM, DEPTH_DEEP):
        p = get_profile(d)
        print(format_banner(p))
        print()
