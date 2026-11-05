"""CITIC 40-industry factors ported from the user-owned allw_lbw research.

No source data, credentials or backtest-performance claims are bundled.
"""
from __future__ import annotations

import csv
import hashlib
import math
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence

from .flow import _zscore, infer_flow_graph


@dataclass(frozen=True)
class IndustrySpec:
    key: str
    name: str
    source_level: str
    source_code: str


@dataclass(frozen=True)
class IndustryDay:
    active_buy: float
    active_sell: float
    turnover: float
    float_market_cap: float
    daily_return: float


# 顺序与研报图表 1 一致。一级行业汇总其全部二级行业；被拆分的一级行业
# 只保留图表中明确列出的二级行业。
INDUSTRIES: tuple[IndustrySpec, ...] = (
    IndustrySpec("L1_100000", "石油石化", "l1", "100000"),
    IndustrySpec("L1_110000", "煤炭", "l1", "110000"),
    IndustrySpec("L2_122000", "工业金属", "l2", "122000"),
    IndustrySpec("L2_123000", "稀有金属", "l2", "123000"),
    IndustrySpec("L2_121000", "贵金属", "l2", "121000"),
    IndustrySpec("L1_210000", "钢铁", "l1", "210000"),
    IndustrySpec("L1_220000", "基础化工", "l1", "220000"),
    IndustrySpec("L1_240000", "建材", "l1", "240000"),
    IndustrySpec("L1_260000", "机械", "l1", "260000"),
    IndustrySpec("L1_270000", "电力设备及新能源", "l1", "270000"),
    IndustrySpec("L1_280000", "国防军工", "l1", "280000"),
    IndustrySpec("L2_303000", "汽车零部件", "l2", "303000"),
    IndustrySpec("L2_301000", "乘用车", "l2", "301000"),
    IndustrySpec("L2_302000", "商用车", "l2", "302000"),
    IndustrySpec("L1_330000", "家电", "l1", "330000"),
    IndustrySpec("L2_361000", "酒类", "l2", "361000"),
    IndustrySpec("L1_320000", "消费者服务", "l1", "320000"),
    IndustrySpec("L1_630000", "传媒", "l1", "630000"),
    IndustrySpec("L2_363000", "食品", "l2", "363000"),
    IndustrySpec("L2_362000", "饮料", "l2", "362000"),
    IndustrySpec("L2_352000", "中药生产", "l2", "352000"),
    IndustrySpec("L2_371000", "种植业", "l2", "371000"),
    IndustrySpec("L2_372000", "畜牧业", "l2", "372000"),
    IndustrySpec("L1_310000", "商贸零售", "l1", "310000"),
    IndustrySpec("L1_340000", "纺织服装", "l1", "340000"),
    IndustrySpec("L1_250000", "轻工制造", "l1", "250000"),
    IndustrySpec("L1_400000", "银行", "l1", "400000"),
    IndustrySpec("L2_412000", "保险", "l2", "412000"),
    IndustrySpec("L2_411000", "证券", "l2", "411000"),
    IndustrySpec("L1_420000", "房地产", "l1", "420000"),
    IndustrySpec("L1_620000", "计算机", "l1", "620000"),
    IndustrySpec("L1_600000", "电子", "l1", "600000"),
    IndustrySpec("L2_612000", "通信设备", "l2", "612000"),
    IndustrySpec("L2_353000", "生物医药", "l2", "353000"),
    IndustrySpec("L2_351000", "化学制药", "l2", "351000"),
    IndustrySpec("L1_500000", "交通运输", "l1", "500000"),
    IndustrySpec("L2_201000", "发电及电网", "l2", "201000"),
    IndustrySpec("L2_202000", "环保及公用事业", "l2", "202000"),
    IndustrySpec("L2_611000", "电信运营", "l2", "611000"),
    IndustrySpec("L1_230000", "建筑", "l1", "230000"),
)


def _finite_float(value: str) -> float:
    if value in ("", None):
        raise ValueError("资金流输入缺少数值，不得填零或跳过")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("资金流输入必须是有限数值")
    return number


def load_bigquant_panel(
    path: Path,
    as_of: date | None = None,
) -> tuple[list[date], dict[date, dict[str, IndustryDay]], dict[str, object]]:
    l1_targets = {x.source_code: x.key for x in INDUSTRIES if x.source_level == "l1"}
    l2_targets = {x.source_code: x.key for x in INDUSTRIES if x.source_level == "l2"}
    accumulators: dict[date, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(float))
    )
    rows = 0
    selected_rows = 0
    source_names: dict[str, set[str]] = defaultdict(set)
    seen = set()

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = {
            "date",
            "l1_code",
            "l1_name",
            "l2_code",
            "l2_name",
            "active_buy_amount",
            "active_sell_amount",
            "turnover_amount",
            "float_market_cap",
            "industry_return",
        }
        if not reader.fieldnames or not expected.issubset(reader.fieldnames):
            raise ValueError(f"BigQuant 文件缺少字段：{sorted(expected - set(reader.fieldnames or []))}")
        for row in reader:
            rows += 1
            day = date.fromisoformat(row["date"])
            if as_of is not None and day > as_of:
                continue
            target = l1_targets.get(row["l1_code"])
            if target is None:
                target = l2_targets.get(row["l2_code"])
            if target is None:
                continue
            selected_rows += 1
            identity = (day, row["l2_code"])
            if identity in seen:
                raise ValueError(f"重复的日期/二级行业：{identity}")
            seen.add(identity)
            buy = _finite_float(row["active_buy_amount"])
            sell = _finite_float(row["active_sell_amount"])
            turnover = _finite_float(row["turnover_amount"])
            market_cap = _finite_float(row["float_market_cap"])
            daily_return = _finite_float(row["industry_return"])
            if min(buy, sell) < 0 or min(turnover, market_cap) <= 0 or daily_return <= -1:
                raise ValueError(f"{day} {target} 金额、市值或收益率非法")
            start_cap = market_cap / (1.0 + daily_return)
            acc = accumulators[day][target]
            acc["buy"] += buy
            acc["sell"] += sell
            acc["turnover"] += turnover
            acc["market_cap"] += market_cap
            acc["return_numerator"] += daily_return * start_cap
            acc["return_denominator"] += start_cap
            acc["source_rows"] += 1
            source_names[target].add(row["l2_name"])

    keys = {x.key for x in INDUSTRIES}
    panel: dict[date, dict[str, IndustryDay]] = {}
    for day, by_key in sorted(accumulators.items()):
        missing = sorted(keys - set(by_key))
        invalid = sorted(
            key
            for key, acc in by_key.items()
            if acc["turnover"] <= 0
            or acc["market_cap"] <= 0
            or acc["return_denominator"] <= 0
            or any(not math.isfinite(value) for value in acc.values())
        )
        if missing or invalid:
            raise ValueError(f"{day} 非完整40行业截面：{missing + invalid}")
        panel[day] = {
            key: IndustryDay(
                active_buy=acc["buy"],
                active_sell=acc["sell"],
                turnover=acc["turnover"],
                float_market_cap=acc["market_cap"],
                daily_return=acc["return_numerator"] / acc["return_denominator"],
            )
            for key, acc in by_key.items()
        }

    if not panel:
        raise ValueError("BigQuant 数据无法形成完整的 40 行业面板")
    days = sorted(panel)
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "file_name": path.name,
        "sha256": sha256,
        "raw_rows": rows,
        "selected_source_rows": selected_rows,
        "complete_days": len(days),
        "first_date": days[0].isoformat(),
        "last_date": days[-1].isoformat(),
        "dropped_day_count": 0,
        "dropped_days": {},
        "industry_sources": {
            spec.key: {
                "name": spec.name,
                "source_level": spec.source_level,
                "source_code": spec.source_code,
                "included_l2_names": sorted(source_names[spec.key]),
            }
            for spec in INDUSTRIES
        },
    }
    return days, panel, manifest


def daily_factors(
    days: Sequence[date],
    panel: dict[date, dict[str, IndustryDay]],
    optimizer_iterations: int = 18,
) -> dict[date, dict[str, tuple[float, float, float, float, float]]]:
    keys = [x.key for x in INDUSTRIES]
    output: dict[date, dict[str, tuple[float, float, float, float, float]]] = {}
    for day in days:
        rows = [panel[day][key] for key in keys]
        total_buy = sum(x.active_buy for x in rows)
        total_sell = sum(x.active_sell for x in rows)
        total_turnover = sum(x.turnover for x in rows)
        total_cap = sum(x.float_market_cap for x in rows)
        totals = (total_buy, total_sell, total_turnover, total_cap)
        if min(totals) <= 0 or any(not math.isfinite(value) for value in totals):
            raise ValueError(f"{day} 主动买卖或规模合计非正")
        net = [x.active_buy / total_buy - x.active_sell / total_sell for x in rows]
        net[-1] -= sum(net)
        volume_share = [x.turnover / total_turnover for x in rows]
        size_share = [x.float_market_cap / total_cap for x in rows]
        market_return = statistics.fmean(x.daily_return for x in rows)
        excess_returns = [x.daily_return - market_return for x in rows]
        flow = infer_flow_graph(
            net,
            excess_returns,
            volume_share=volume_share,
            size_share=size_share,
            iterations=optimizer_iterations,
        )
        factors: dict[str, tuple[float, float, float, float, float]] = {}
        for index, key in enumerate(keys, start=1):
            volume = max(volume_share[index - 1], 1e-12)
            industry_edges = [
                flow[index][other]
                for other in range(1, len(keys) + 1)
                if other != index
            ]
            factors[key] = (
                net[index - 1] / volume,
                max(industry_edges) / volume,
                sum(value > 0 for value in industry_edges) / len(industry_edges),
                sum(value for value in industry_edges if value < 0) / volume,
                flow[index][0] / volume,
            )
        output[day] = factors
        if any(not math.isfinite(value) for values in factors.values() for value in values):
            raise ValueError(f"{day} 因子计算溢出")
    return output


def signal_scores(
    days: Sequence[date],
    factors: dict[date, dict[str, tuple[float, float, float, float, float]]],
    window: int,
) -> tuple[dict[date, dict[str, float]], dict[date, dict[str, float]]]:
    if window < 1:
        raise ValueError("window 必须为正整数")
    keys = [x.key for x in INDUSTRIES]
    history = {key: [deque(maxlen=window) for _ in range(5)] for key in keys}
    base_scores: dict[date, dict[str, float]] = {}
    composite_scores: dict[date, dict[str, float]] = {}
    for day in days:
        if day not in factors:
            continue
        for key in keys:
            for factor_index, value in enumerate(factors[day][key]):
                history[key][factor_index].append(value)
        if len(history[keys[0]][0]) < window:
            continue
        smoothed = [
            [statistics.fmean(history[key][factor_index]) for key in keys]
            for factor_index in range(5)
        ]
        standardized = [_zscore(values) for values in smoothed]
        base_scores[day] = {key: standardized[0][i] for i, key in enumerate(keys)}
        composite_scores[day] = {
            key: statistics.fmean(standardized[k][i] for k in range(5))
            for i, key in enumerate(keys)
        }
    return base_scores, composite_scores


def weekly_signal_days(days: Sequence[date], available: set[date]) -> list[date]:
    return [
        day
        for day, next_day in zip(days, days[1:])
        if day in available and day.isocalendar()[:2] != next_day.isocalendar()[:2]
    ]


def make_schedule(
    days: Sequence[date],
    scores: dict[date, dict[str, float]],
    top_n: int = 5,
) -> list[tuple[date, date, tuple[str, ...]]]:
    day_index = {day: i for i, day in enumerate(days)}
    schedule: list[tuple[date, date, tuple[str, ...]]] = []
    for signal_day in weekly_signal_days(days, set(scores)):
        index = day_index[signal_day]
        ranked = sorted(scores[signal_day], key=lambda key: (-scores[signal_day][key], key))
        schedule.append((signal_day, days[index + 1], tuple(ranked[:top_n])))
    return schedule
