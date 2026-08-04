import json
from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

import run_tail_decision
from .fixtures import workflow_dependencies


class _Archive:
    def __init__(self, root):
        self.root = root

    def read_trade_dates(self, start, end):
        return [end.strftime("%Y%m%d")]


def test_production_no_token_smoke_never_uses_fixture_or_paid_provider(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    production_gateway = workflow_dependencies()["gateway"]
    monkeypatch.setattr(
        run_tail_decision,
        "CredentialFreeGateway",
        lambda **kwargs: production_gateway,
    )
    monkeypatch.setattr(run_tail_decision, "ArchiveReader", _Archive)
    monkeypatch.setattr(
        run_tail_decision,
        "_OfflineGateway",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fixture used")),
    )

    exit_code = run_tail_decision.main(
        [
            "--phase",
            "final",
            "--as-of",
            "2026-08-04T14:30:00+08:00",
            "--data-root",
            str(tmp_path / "archive"),
            "--output-root",
            str(tmp_path),
            "--state-root",
            str(tmp_path / "state"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "recommended"
    assert payload["total_exposure"] <= 8_000.0
    assert payload["ledger_events"] == 1
    assert list((tmp_path / "reports" / "tail_decision").rglob("*.json"))
