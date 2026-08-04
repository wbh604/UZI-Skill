from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.event_risk import (
    Announcement,
    EastmoneyAnnouncementProvider,
    evaluate_event_risk,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 4, hour, minute, tzinfo=SHANGHAI)


def test_unknown_announcement_source_blocks_stock_allocation():
    result = evaluate_event_risk((), source_ok=False)

    assert result == {
        "event_status": "unknown",
        "adverse_event": True,
        "risk_titles": (),
    }


def test_event_risk_classifies_only_recent_deterministic_keywords():
    announcements = (
        Announcement("关于股东减持计划的公告", _at(13), "eastmoney"),
        Announcement("关于现金分红实施的公告", _at(12), "eastmoney"),
        Announcement(
            "历史诉讼事项进展公告",
            datetime(2026, 8, 3, 14, 59, tzinfo=SHANGHAI),
            "eastmoney",
        ),
    )

    result = evaluate_event_risk(
        announcements,
        source_ok=True,
        since=datetime(2026, 8, 3, 15, 0, tzinfo=SHANGHAI),
        as_of=_at(14, 30),
    )

    assert result["event_status"] == "checked"
    assert result["adverse_event"] is True
    assert result["risk_titles"] == ("关于股东减持计划的公告",)


def test_successful_safe_check_is_not_adverse():
    result = evaluate_event_risk(
        (Announcement("年度权益分派实施公告", _at(10), "eastmoney"),),
        source_ok=True,
        since=datetime(2026, 8, 3, 15, 0, tzinfo=SHANGHAI),
        as_of=_at(14, 30),
    )

    assert result == {
        "event_status": "checked",
        "adverse_event": False,
        "risk_titles": (),
    }


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "data": {
                "list": [
                    {
                        "title": "样本公告",
                        "notice_date": "2026-08-04 13:05:00",
                        "codes": [{"stock_code": "600001"}],
                    }
                ]
            }
        }


class _Session:
    def __init__(self):
        self.params = None

    def get(self, url, *, params, headers, timeout):
        self.params = params
        return _Response()


def test_eastmoney_provider_queries_the_exact_stock_and_returns_aware_times():
    session = _Session()
    provider = EastmoneyAnnouncementProvider(session=session)

    announcements = provider.fetch("600001.SH", _at(14, 30))

    assert session.params["stock_list"] == "600001"
    assert announcements == (
        Announcement("样本公告", _at(13, 5), "eastmoney"),
    )
