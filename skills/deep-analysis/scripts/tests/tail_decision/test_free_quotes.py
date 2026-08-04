from datetime import datetime
from pathlib import Path
import sys
import threading
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.free_quotes import (
    EastmoneyQuoteProvider,
    fetch_from_providers,
)

NOW = datetime(2026, 8, 3, 14, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_eastmoney_parser_normalizes_scaled_fields():
    payload = {
        "data": {
            "f57": "600406",
            "f58": "国电南瑞",
            "f43": 2506,
            "f59": 2,
            "f46": 2448,
            "f44": 2509,
            "f45": 2446,
            "f60": 2435,
            "f47": 1000,
            "f48": 2506000,
            "f124": int(NOW.timestamp()),
        }
    }
    quote = EastmoneyQuoteProvider.parse_payload("600406.SH", payload, NOW)
    assert quote.last_price == 25.06
    assert quote.source == "eastmoney"


def test_provider_failure_does_not_discard_other_source():
    class Good:
        name = "good"

        def fetch_quotes(self, ids, now):
            return {
                ids[0]: EastmoneyQuoteProvider.parse_payload(
                    ids[0],
                    {
                        "data": {
                            "f57": "600406",
                            "f58": "国电南瑞",
                            "f43": 2506,
                            "f59": 2,
                            "f46": 2448,
                            "f44": 2509,
                            "f45": 2446,
                            "f60": 2435,
                            "f47": 1000,
                            "f48": 2506000,
                            "f124": int(now.timestamp()),
                        }
                    },
                    now,
                )
            }

    class Bad:
        name = "bad"

        def fetch_quotes(self, ids, now):
            raise TimeoutError("offline")

    result = fetch_from_providers([Bad(), Good()], ["600406.SH"], NOW)
    assert [quote.source for quote in result["600406.SH"]] == ["eastmoney"]


def test_eastmoney_fetches_instruments_with_bounded_concurrency():
    barrier = threading.Barrier(2)

    class Response:
        def __init__(self, code):
            self.code = code

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "f57": self.code,
                    "f58": "fixture",
                    "f43": 1000,
                    "f59": 2,
                    "f46": 990,
                    "f44": 1010,
                    "f45": 980,
                    "f60": 990,
                    "f47": 1000,
                    "f48": 1_000_000,
                    "f124": int(NOW.timestamp()),
                }
            }

    class Session:
        def __init__(self):
            self.lock = threading.Lock()
            self.active = 0
            self.max_active = 0

        def get(self, url, *, params, headers, timeout):
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                try:
                    barrier.wait(timeout=0.2)
                except threading.BrokenBarrierError:
                    pass
                return Response(params["secid"].split(".", 1)[1])
            finally:
                with self.lock:
                    self.active -= 1

    session = Session()
    provider = EastmoneyQuoteProvider(session=session, max_workers=8)

    quotes = provider.fetch_quotes(("600001.SH", "600002.SH"), NOW)

    assert set(quotes) == {"600001.SH", "600002.SH"}
    assert session.max_active == 2
