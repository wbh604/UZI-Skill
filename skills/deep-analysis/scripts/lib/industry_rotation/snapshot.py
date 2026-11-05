"""Dated rotation snapshots; imported proxy observations never enter formal factors."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from pathlib import Path

from .core import INDUSTRIES, daily_factors, load_industry_panel, make_schedule, signal_scores

WINDOWS = tuple(range(20, 25))
NAMES = {item.key: item.name for item in INDUSTRIES}


def rank_rows(scores):
    return [
        {"rank": rank, "code": key, "name": NAMES[key], "score": value}
        for rank, (key, value) in enumerate(
            sorted(scores.items(), key=lambda item: (-item[1], item[0])), 1
        )
    ]


def common_core(windows, variant):
    pools = [{row["code"] for row in windows[str(w)][variant][:5]} for w in WINDOWS]
    common = set.intersection(*pools)
    return [row["name"] for row in windows["20"][variant][:5] if row["code"] in common]


def load_proxy(path: Path, as_of: date):
    """Accept the documented local observation schema, not arbitrary HTML."""
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("临时观察 JSON 不能超过 2 MiB")
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("临时观察 JSON 顶层必须为对象")
    if payload.get("status") != "public_proxy_observation":
        raise ValueError("临时观察口径不匹配")
    proxy_day = date.fromisoformat(payload["as_of"])
    if proxy_day > as_of:
        raise ValueError("临时观察日期晚于 --as-of，禁止前视")
    windows = {}
    for window in WINDOWS:
        block = payload["windows"][str(window)]
        windows[str(window)] = {}
        for variant in ("base", "composite"):
            rows = block[variant]
            if len(rows) != 5:
                raise ValueError("临时观察必须提供每个窗口的 Top 5")
            clean = []
            for index, row in enumerate(rows, 1):
                if not isinstance(row, dict):
                    raise ValueError("临时观察记录必须为对象")
                score = row["score"]
                if (isinstance(score, bool) or not isinstance(score, (int, float))
                        or not math.isfinite(score) or row["rank"] != index):
                    raise ValueError("临时观察排名或分数无效")
                if any(not isinstance(row[key], str) or not row[key].strip()
                       or len(row[key]) > 100 for key in ("code", "name")):
                    raise ValueError("临时观察行业标识无效")
                clean.append({key: row[key] for key in ("rank", "code", "name", "score")})
            if len({row["code"] for row in clean}) != 5:
                raise ValueError("临时观察行业重复")
            if any(a["score"] < b["score"] for a, b in zip(clean, clean[1:])):
                raise ValueError("临时观察分数与排名不一致")
            windows[str(window)][variant] = clean
    return {
        "status": "imported_observation_only",
        "as_of": proxy_day.isoformat(),
        "age_calendar_days": (as_of - proxy_day).days,
        "universe": "申万一级30行业代理模型（源文件声明，未在此重新采集）",
        "method": "价格位置 Money Flow Multiplier × 成交额；规模为60日均成交额代理",
        "file_name": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "windows": windows,
        "common_core": {variant: common_core(windows, variant) for variant in ("base", "composite")},
        "warning": "导入的历史观察，不是实测主动买卖额，不与中信40拼接或替代正式持仓。",
    }


def build_snapshot(path: Path, as_of: date, proxy_path: Path | None = None):
    days, panel, manifest = load_industry_panel(path, as_of=as_of)
    if len(days) < max(WINDOWS) + 1:
        raise ValueError("至少需要25个完整交易日，以计算全部窗口及前一日变化")
    # Only the latest and previous weekly signal are needed, not a full backtest.
    recent_days = days[-(max(WINDOWS) + 10):]
    factors = daily_factors(recent_days, panel)
    windows = {}
    for window in WINDOWS:
        base, composite = signal_scores(recent_days, factors, window)
        block = {}
        for variant, scores in (("base", base), ("composite", composite)):
            current = rank_rows(scores[days[-1]])
            previous = rank_rows(scores[days[-2]])
            previous_ranks = {row["code"]: row["rank"] for row in previous}
            for row in current:
                row["rank_change"] = previous_ranks[row["code"]] - row["rank"]
            block[variant] = current
            current_top = {row["code"] for row in current[:5]}
            previous_top = {row["code"] for row in previous[:5]}
            block[variant + "_changes"] = {
                "entered": [NAMES[key] for key in sorted(current_top - previous_top)],
                "exited": [NAMES[key] for key in sorted(previous_top - current_top)],
            }
            schedule = make_schedule(recent_days, scores)
            if schedule:
                signal_day, entry_day, selected = schedule[-1]
                block[variant + "_weekly_target"] = {
                    "signal_date": signal_day.isoformat(),
                    "model_entry_close": entry_day.isoformat(),
                    "names": [NAMES[key] for key in selected],
                    "codes": list(selected),
                    "target_weight_each": 1 / len(selected),
                    "status": "model_target_not_actual_holdings",
                }
            else:
                block[variant + "_weekly_target"] = None
        windows[str(window)] = block
    proxy = load_proxy(proxy_path, as_of) if proxy_path else None
    return {
        "schema_version": 1,
        "strategy": "citic40-active-flow-rotation",
        "as_of": as_of.isoformat(),
        "execution_status": "observation_only",
        "formal": {
            "source": "用户提供的本地 CSV；数据授权由提供者负责，禁止公开分发",
            "universe": "中信40行业（一级聚合 + 指定二级）",
            "data_date": days[-1].isoformat(),
            "previous_data_date": days[-2].isoformat(),
            "age_calendar_days": (as_of - days[-1]).days,
            "input": manifest,
            "windows": windows,
            "common_core": {variant: common_core(windows, variant) for variant in ("base", "composite")},
        },
        "proxy": proxy,
        "warnings": [
            "仅供研究；行业排名不是个股买入建议，也不代表真实持仓。",
            "综合五因子的资金流图是守恒约束近似求解，不是原研报未公开优化器的精确复现。",
            "周频信号取已观察到跨周边界的前一周末数据，次周首个数据日收盘调仓，随后才计新组合收益。",
            "未连接交易所日历；CSV须包含连续、完整的交易日和各一级行业的全部二级成分，整日/成分缺失无法完全识别。",
            "as-of 限制交易日期而非信息发布日期；输入历史修订仍可能影响点时复现。",
            "报告不包含回测收益、ETF映射、成交确认或自动交易；消息、流动性、风险仍需单独核验。",
        ],
    }
