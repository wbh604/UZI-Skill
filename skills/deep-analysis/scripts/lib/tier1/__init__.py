"""Tier-1 方法包 · 从 anthropics/financial-services 续引入（v3.8.0）。

5 个与个股研究强相关的新方法，适配 A 股 / 港股 / 美股，纯函数 + methodology_log：

    build_ai_readiness        — 单票 AI 就绪度/卡位评估（复用 Serenity ai_chokepoint_score）
    build_earnings_preview    — 财报前预览（一致预期 + Bull/Base/Bear + 关注指标）
    build_model_update        — 新财报/指引增量更新模型（DCF/Comps/thesis delta）
    build_returns_attribution — 二级市场组合收益归因（按持仓/行业拆解）
    build_rebalance           — 逐持仓再平衡（漂移 + 交易清单 + 本地化换手成本）

每个方法也有对应的 slash 命令（commands/）与方法论文档（references/fin-methods/）。
"""
from __future__ import annotations

from lib.tier1.ai_readiness import build_ai_readiness
from lib.tier1.earnings_preview import build_earnings_preview
from lib.tier1.model_update import build_model_update
from lib.tier1.returns_attrib import build_returns_attribution
from lib.tier1.rebalance import build_rebalance

__all__ = [
    "build_ai_readiness",
    "build_earnings_preview",
    "build_model_update",
    "build_returns_attribution",
    "build_rebalance",
]
