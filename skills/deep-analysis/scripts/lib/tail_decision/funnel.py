"""Deterministic research-to-observation narrowing for Tail decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from types import MappingProxyType
from typing import Mapping

import pandas as pd

from .research_evidence import ResearchEvidence
from .universe import Universe


@dataclass(frozen=True)
class FunnelAudit:
    base_stocks: int
    research_stocks: int
    observation_stocks: int
    research_etfs: int
    observation_etfs: int
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))


@dataclass(frozen=True)
class CandidateFunnel:
    research: Universe
    observation: Universe
    evidence: Mapping[str, ResearchEvidence]
    audit: FunnelAudit

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))


def build_candidate_funnel(
    universe: Universe,
    stock_daily: pd.DataFrame,
    fund_daily: pd.DataFrame,
    evidence: Mapping[str, ResearchEvidence],
    *,
    as_of: date | datetime,
    max_stocks: int = 30,
    max_etfs: int = 10,
    research_stock_target: int = 300,
) -> CandidateFunnel:
    """Keep all qualified research names and deterministically narrow observation."""

    if max_stocks <= 0 or max_etfs <= 0:
        raise ValueError("observation limits must be positive")
    if research_stock_target <= 0:
        raise ValueError("research_stock_target must be positive")
    as_of_date = _as_of_date(as_of)
    normalized_evidence = {
        instrument_id: item
        for instrument_id, item in evidence.items()
        if instrument_id in {*universe.stocks, *universe.etfs}
    }
    blocked = {
        instrument_id
        for instrument_id, item in normalized_evidence.items()
        if item.uzi_state == "blocked"
    }
    reasons = list(universe.reasons)
    if len(universe.stocks) < research_stock_target:
        reasons.append(
            f"research_stock_target_unmet:{len(universe.stocks)}/{research_stock_target}"
        )
    reasons.extend(f"uzi_blocked:{instrument_id}" for instrument_id in sorted(blocked))
    observation = Universe(
        stocks=_narrow(
            universe.stocks,
            stock_daily,
            normalized_evidence,
            blocked,
            max_stocks,
            as_of_date,
        ),
        etfs=_narrow(
            universe.etfs,
            fund_daily,
            normalized_evidence,
            blocked,
            max_etfs,
            as_of_date,
        ),
    )
    return CandidateFunnel(
        research=universe,
        observation=observation,
        evidence=normalized_evidence,
        audit=FunnelAudit(
            base_stocks=len(universe.stocks),
            research_stocks=len(universe.stocks),
            observation_stocks=len(observation.stocks),
            research_etfs=len(universe.etfs),
            observation_etfs=len(observation.etfs),
            reasons=tuple(reasons),
        ),
    )


def _narrow(
    instrument_ids: tuple[str, ...],
    daily: pd.DataFrame,
    evidence: Mapping[str, ResearchEvidence],
    blocked: set[str],
    limit: int,
    as_of: date,
) -> tuple[str, ...]:
    metrics = _local_metrics(daily, instrument_ids, as_of)
    scored = [
        (
            _local_score(metrics.get(instrument_id, {}))
            + _evidence_bonus(evidence.get(instrument_id)),
            instrument_id,
        )
        for instrument_id in instrument_ids
        if instrument_id not in blocked
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(instrument_id for _, instrument_id in scored[:limit])


def _local_metrics(
    daily: pd.DataFrame, instrument_ids: tuple[str, ...], as_of: date
) -> dict[str, dict[str, float]]:
    required = {"ts_code", "trade_date", "close", "amount"}
    if daily.empty or not required.issubset(daily.columns) or not instrument_ids:
        return {}
    frame = daily.loc[:, ["ts_code", "trade_date", "close", "amount"]].copy()
    frame["ts_code"] = frame["ts_code"].astype(str).str.upper()
    frame = frame[frame["ts_code"].isin(instrument_ids)]
    frame["trade_date"] = pd.to_datetime(
        frame["trade_date"].astype(str), format="%Y%m%d", errors="coerce"
    )
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    frame = frame.dropna(subset=["trade_date", "close", "amount"])
    frame = frame[frame["trade_date"] <= pd.Timestamp(as_of)]
    frame = frame[(frame["close"] > 0.0) & (frame["amount"] >= 0.0)]
    if frame.empty:
        return {}
    recent = (
        frame.sort_values(["ts_code", "trade_date"], kind="stable")
        .groupby("ts_code", sort=True)
        .tail(20)
    )
    rows: list[dict[str, float | str]] = []
    for instrument_id, group in recent.groupby("ts_code", sort=True):
        closes = group["close"].tolist()
        five_day_return = 0.0
        if len(closes) >= 5 and closes[-5] > 0.0:
            five_day_return = closes[-1] / closes[-5] - 1.0
        rows.append({
            "ts_code": instrument_id,
            "liquidity": group["amount"].mean(),
            "completeness": min(group["trade_date"].nunique() / 20.0, 1.0),
            "return": five_day_return,
            "volatility": group["close"].pct_change().std(ddof=0) or 0.0,
        })
    metrics = pd.DataFrame(rows).set_index("ts_code")
    for field in ("liquidity", "return", "volatility"):
        metrics[f"{field}_percentile"] = metrics[field].rank(
            method="average", pct=True
        )
    return {
        instrument_id: {
            "liquidity": row["liquidity_percentile"],
            "completeness": row["completeness"],
            "return": row["return_percentile"],
            "volatility": row["volatility_percentile"],
        }
        for instrument_id, row in metrics.iterrows()
    }


def _local_score(metrics: Mapping[str, float]) -> float:
    values = {key: _finite_non_negative(value) for key, value in metrics.items()}
    return (
        0.45 * values.get("liquidity", 0.0)
        + 0.25 * values.get("completeness", 0.0)
        + 0.20 * values.get("return", 0.0)
        - 0.10 * values.get("volatility", 0.0)
    )


def _evidence_bonus(evidence: ResearchEvidence | None) -> float:
    if evidence is None:
        return 0.0
    ai_bonus = _priority_bonus(evidence.ai_score)
    uzi_bonus = _priority_bonus(evidence.uzi_score) if evidence.uzi_state == "approved" else 0.0
    return ai_bonus + uzi_bonus


def _as_of_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError("as_of must be a date or datetime")


def _priority_bonus(value: object) -> float:
    return min(_finite_non_negative(value) / 100.0 * 0.05, 0.05)


def _finite_non_negative(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if math.isfinite(result) and result >= 0.0 else 0.0
