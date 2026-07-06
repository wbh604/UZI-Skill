"""22 fetcher 的 adapter 注册表 · factory 模式 · 每个 < 30 行.

每条注册声明：
- dim_key
- legacy_module · 调老 fetch_X.py
- required_fields · quality=FULL 的最低要求
- optional_fields · 补充字段
- top_level_fields · 要写到 raw 顶层的溢出字段（如 fund_managers）
- depends_on · 需要先跑的 dim（拿 industry）
- args_fn · 从 ticker + raw 提取老 main() 的参数

老 fetcher 的调用方式各不相同（有的只要 ticker · 有的要 industry）· args_fn 统一抽象.
"""
from __future__ import annotations

import importlib
from typing import Any, Callable

from ..base_fetcher import BaseFetcher
from ..schema import DimResult, FetcherSpec, Quality


def _make_adapter(
    dim_key: str,
    legacy_module: str,
    required: list[str],
    optional: list[str],
    args_fn: Callable[[Any, dict], tuple],
    top_level: list[str] = None,
    depends_on: list[str] = None,
    markets: tuple[str, ...] = ("A", "H", "U"),
    sources: list[str] = None,
    keep_zero_fields: set[str] = None,
) -> type:
    """工厂函数 · 生成一个 BaseFetcher 子类."""
    spec = FetcherSpec(
        dim_key=dim_key,
        required_fields=required,
        optional_fields=optional or [],
        top_level_fields=top_level or [],
        depends_on=depends_on or [],
        markets=markets,
        sources=sources or [f"legacy:{legacy_module}"],
    )
    kzf = keep_zero_fields or set()

    def _fetch_raw(self, ticker, raw=None):
        mod = importlib.import_module(self._legacy_module)
        args = self._args_fn(ticker, raw or {})
        result = mod.main(*args)
        # 老 fetcher 有两种返回风格：
        # 1. {"ticker": ..., "data": {...}, "source": ..., "fallback": bool}
        # 2. 裸 dict（fetch_macro / fetch_policy / fetch_industry）
        if isinstance(result, dict) and "data" in result and isinstance(result["data"], dict):
            return result["data"]
        return result if isinstance(result, dict) else {}

    # 用 type(name, bases, ns) 一次性创建 · 规避 __init_subclass__ 提前检查
    cls_name = f"{dim_key.replace('_', ' ').title().replace(' ', '')}Adapter"
    namespace = {
        "spec": spec,
        "keep_zero_fields": kzf,
        "_legacy_module": legacy_module,
        "_args_fn": staticmethod(args_fn),
        "_fetch_raw": _fetch_raw,
    }
    return type(cls_name, (BaseFetcher,), namespace)


# ═══ 22 Fetcher 注册（按 dim_key 排序）═══════════════════════════

FETCHER_REGISTRY: dict[str, type] = {
    # 0_basic · 基础信息（name/price/PE/PB/行业/实控人）
    "0_basic": _make_adapter(
        dim_key="0_basic",
        legacy_module="fetch_basic",
        required=["name", "price"],
        optional=["industry", "market_cap", "pe_ttm", "pb", "eps", "actual_controller", "listed_date", "full_name"],
        args_fn=lambda t, r: (t,),
        markets=("A", "H", "U"),
        sources=["legacy:fetch_basic"],
    ),

    # 1_financials · 财报三表
    "1_financials": _make_adapter(
        dim_key="1_financials",
        legacy_module="fetch_financials",
        required=["roe", "net_margin"],
        optional=[
            "gross_margin", "revenue_growth", "financial_health",
            "ocf", "ocf_history", "ocf_to_net_income_ratio",
        ],
        args_fn=lambda t, r: (t,),
    ),

    # 2_kline · K 线走势
    "2_kline": _make_adapter(
        dim_key="2_kline",
        legacy_module="fetch_kline",
        required=[],  # 允许部分数据 · kline 组合多 · 不设硬 required
        optional=["kline_daily", "ma5", "ma20", "ma60", "rsi", "price_change_1m", "price_change_3m"],
        args_fn=lambda t, r: (t,),
    ),

    # 3_macro · 宏观（按 industry 查）
    "3_macro": _make_adapter(
        dim_key="3_macro",
        legacy_module="fetch_macro",
        required=[],
        optional=["rate_cycle", "fx_trend", "geo_risk", "commodity", "growth_momentum"],
        args_fn=lambda t, r: (r.get("0_basic", {}).get("data", {}).get("industry", "") or "综合",),
        depends_on=["0_basic"],
    ),

    # 4_peers · 同行对比
    "4_peers": _make_adapter(
        dim_key="4_peers",
        legacy_module="fetch_peers",
        required=[],
        optional=["peer_table", "peer_comparison", "rank", "industry"],
        args_fn=lambda t, r: (t,),
    ),

    # 5_chain · 产业链
    "5_chain": _make_adapter(
        dim_key="5_chain",
        legacy_module="fetch_chain",
        required=[],
        optional=["main_business_breakdown", "upstream", "downstream", "client_concentration"],
        args_fn=lambda t, r: (t,),
    ),

    # 6_fund_holders · 公募基金持仓（含 fund_managers 顶层溢出）
    "6_fund_holders": _make_adapter(
        dim_key="6_fund_holders",
        legacy_module="fetch_fund_holders",
        required=[],
        optional=["total_funds_holding", "active_funds_count", "full_stats_count"],
        top_level=["fund_managers"],  # 关键：写 raw 顶层
        args_fn=lambda t, r: (t,),
        sources=["legacy:fetch_fund_holders", "akshare:fund_portfolio_hold_em"],
    ),

    # 6_research · 研报评级
    "6_research": _make_adapter(
        dim_key="6_research",
        legacy_module="fetch_research",
        required=[],
        optional=["coverage", "rating_distribution", "target_price_avg", "buy_rating_pct"],
        args_fn=lambda t, r: (t,),
    ),

    # 7_industry · 行业景气（按 industry 查）
    "7_industry": _make_adapter(
        dim_key="7_industry",
        legacy_module="fetch_industry",
        required=[],
        optional=["industry", "growth", "tam", "penetration", "industry_pe", "industry_pb", "cninfo_metrics"],
        args_fn=lambda t, r: (r.get("0_basic", {}).get("data", {}).get("industry", "") or "综合",),
        depends_on=["0_basic"],
    ),

    # 8_materials · 原材料
    "8_materials": _make_adapter(
        dim_key="8_materials",
        legacy_module="fetch_materials",
        required=[],
        optional=["core_material", "price_trend", "price_history_12m", "materials_detail", "cost_share"],
        args_fn=lambda t, r: (t,),
    ),

    # 9_futures · 期货
    "9_futures": _make_adapter(
        dim_key="9_futures",
        legacy_module="fetch_futures",
        required=[],
        optional=["linked_contract", "price_trend", "inventory"],
        args_fn=lambda t, r: (r.get("0_basic", {}).get("data", {}).get("industry", "") or "综合",),
        depends_on=["0_basic"],
    ),

    # 10_valuation · 估值
    "10_valuation": _make_adapter(
        dim_key="10_valuation",
        legacy_module="fetch_valuation",
        required=[],
        optional=["pe", "pb", "pe_quantile", "pb_quantile", "industry_pe", "dcf"],
        args_fn=lambda t, r: (t,),
    ),

    # 11_governance · 治理
    "11_governance": _make_adapter(
        dim_key="11_governance",
        legacy_module="fetch_governance",
        required=[],
        optional=["pledge", "insider_trades_1y", "chairman_turnover"],
        args_fn=lambda t, r: (t,),
    ),

    # 12_capital_flow · 主力资金
    "12_capital_flow": _make_adapter(
        dim_key="12_capital_flow",
        legacy_module="fetch_capital_flow",
        required=[],
        optional=["northbound", "margin_recent", "holder_count_history", "main_fund_flow_20d", "institutional_history"],
        args_fn=lambda t, r: (t,),
    ),

    # 13_policy · 政策（按 industry 查）
    "13_policy": _make_adapter(
        dim_key="13_policy",
        legacy_module="fetch_policy",
        required=[],
        optional=["policy_dir", "subsidy", "monitoring", "anti_trust", "snippets"],
        args_fn=lambda t, r: (r.get("0_basic", {}).get("data", {}).get("industry", "") or "综合",),
        depends_on=["0_basic"],
    ),

    # 14_moat · 护城河
    "14_moat": _make_adapter(
        dim_key="14_moat",
        legacy_module="fetch_moat",
        required=[],
        optional=["intangible", "switching", "network", "scale", "rd_summary", "scores", "web_search_snippets"],
        args_fn=lambda t, r: (t,),
    ),

    # 15_events · 事件驱动
    "15_events": _make_adapter(
        dim_key="15_events",
        legacy_module="fetch_events",
        required=[],
        optional=["event_timeline", "recent_news", "catalyst", "warnings", "disclosures_count"],
        args_fn=lambda t, r: (t,),
    ),

    # 16_lhb · 龙虎榜
    "16_lhb": _make_adapter(
        dim_key="16_lhb",
        legacy_module="fetch_lhb",
        required=[],
        optional=["lhb_count_30d", "lhb_records", "matched_youzi", "inst_vs_youzi"],
        args_fn=lambda t, r: (t,),
    ),

    # 17_sentiment · 舆情
    "17_sentiment": _make_adapter(
        dim_key="17_sentiment",
        legacy_module="fetch_sentiment",
        required=[],
        optional=["xueqiu_heat", "thermometer_value", "positive_pct", "sentiment_label", "platform_snippets", "hot_trend_mentions"],
        args_fn=lambda t, r: (t,),
    ),

    # 18_trap · 杀猪盘排查
    "18_trap": _make_adapter(
        dim_key="18_trap",
        legacy_module="fetch_trap_signals",
        required=[],
        optional=["risk_score", "pump_dump_signals", "warning_flags", "trap_likelihood"],
        args_fn=lambda t, r: (t,),
    ),

    # 19_contests · 实盘大赛 / 大V 组合
    "19_contests": _make_adapter(
        dim_key="19_contests",
        legacy_module="fetch_contests",
        required=[],
        optional=["xueqiu_cubes", "tgb_mentions", "ths_simu", "dpswang", "summary"],
        args_fn=lambda t, r: (t,),
    ),
}


def get_fetcher(dim_key: str) -> BaseFetcher | None:
    """根据 dim_key 取 fetcher 实例 · 未注册返 None."""
    cls = FETCHER_REGISTRY.get(dim_key)
    return cls() if cls else None


def list_fetchers() -> list[str]:
    """返回所有已注册的 dim_key · 按 key 字符串排序."""
    return sorted(FETCHER_REGISTRY.keys())
