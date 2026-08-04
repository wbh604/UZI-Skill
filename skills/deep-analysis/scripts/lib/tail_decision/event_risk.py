"""Credential-free announcement risk checks for overnight stock candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

import requests


SHANGHAI = ZoneInfo("Asia/Shanghai")
RISK_KEYWORDS = (
    "立案",
    "调查",
    "处罚",
    "减持",
    "终止",
    "退市",
    "预亏",
    "诉讼",
    "冻结",
    "逾期",
    "平仓",
    "重大损失",
)


@dataclass(frozen=True)
class Announcement:
    title: str
    published_at: datetime
    source: str

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if not self.source.strip():
            raise ValueError("source must not be empty")
        if self.published_at.tzinfo is None or self.published_at.utcoffset() is None:
            raise ValueError("published_at must be timezone-aware")


class EastmoneyAnnouncementProvider:
    endpoint = "https://np-anotice-stock.eastmoney.com/api/security/ann"

    def __init__(self, session: requests.Session | None = None, timeout: float = 8.0):
        self.session = session or requests.Session()
        self.timeout = timeout

    def fetch(
        self, instrument_id: str, as_of: datetime
    ) -> tuple[Announcement, ...]:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        code = _stock_code(instrument_id)
        response = self.session.get(
            self.endpoint,
            params={
                "sr": "-1",
                "page_size": 50,
                "page_index": 1,
                "ann_type": "A",
                "client_source": "web",
                "stock_list": code,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return self.parse_payload(response.json(), code=code, as_of=as_of)

    @staticmethod
    def parse_payload(
        payload: Mapping[str, object], *, code: str, as_of: datetime
    ) -> tuple[Announcement, ...]:
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ValueError("eastmoney announcement payload has no data")
        rows = data.get("list") or ()
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise ValueError("eastmoney announcement payload has invalid list")

        announcements: list[Announcement] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            codes = row.get("codes") or ()
            if isinstance(codes, Sequence) and not isinstance(codes, (str, bytes)):
                listed_codes = {
                    str(item.get("stock_code", ""))
                    for item in codes
                    if isinstance(item, Mapping)
                }
                if listed_codes and code not in listed_codes:
                    continue
            title = str(row.get("title") or "").strip()
            timestamp = row.get("notice_date") or row.get("display_time")
            if not title or not timestamp:
                continue
            published_at = _parse_timestamp(str(timestamp), as_of.tzinfo)
            if published_at > as_of:
                continue
            announcements.append(
                Announcement(
                    title=title[:200],
                    published_at=published_at,
                    source="eastmoney",
                )
            )
        return tuple(
            sorted(announcements, key=lambda item: (item.published_at, item.title))
        )


def evaluate_event_risk(
    announcements: Sequence[Announcement],
    *,
    source_ok: bool,
    since: datetime | None = None,
    as_of: datetime | None = None,
) -> dict[str, object]:
    if not source_ok:
        return {
            "event_status": "unknown",
            "adverse_event": True,
            "risk_titles": (),
        }
    if since is not None and (since.tzinfo is None or since.utcoffset() is None):
        raise ValueError("since must be timezone-aware")
    if as_of is not None and (as_of.tzinfo is None or as_of.utcoffset() is None):
        raise ValueError("as_of must be timezone-aware")

    risk_titles = tuple(
        item.title
        for item in announcements
        if (since is None or item.published_at >= since)
        and (as_of is None or item.published_at <= as_of)
        and any(keyword in item.title for keyword in RISK_KEYWORDS)
    )
    return {
        "event_status": "checked",
        "adverse_event": bool(risk_titles),
        "risk_titles": risk_titles,
    }


def _stock_code(instrument_id: str) -> str:
    try:
        code, exchange = instrument_id.upper().split(".", 1)
    except ValueError as exc:
        raise ValueError(f"invalid instrument id: {instrument_id!r}") from exc
    if len(code) != 6 or not code.isdigit() or exchange not in {"SH", "SZ"}:
        raise ValueError(f"invalid instrument id: {instrument_id!r}")
    return code


def _parse_timestamp(value: str, timezone) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid announcement timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone or SHANGHAI)
    return parsed.astimezone(timezone or SHANGHAI)
