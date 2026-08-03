from datetime import datetime
from pathlib import Path
import sys
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
