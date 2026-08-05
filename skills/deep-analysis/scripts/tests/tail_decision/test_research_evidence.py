from datetime import date, datetime
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.research_evidence import (
    ResearchEvidence,
    load_ai_discovery,
    load_uzi_evidence,
    merge_research_evidence,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def aware_at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=SHANGHAI)


def write_weekly_file(root: Path, *, as_of: str, code: str) -> Path:
    path = root / f"weekly_candidates_{as_of.replace('-', '')}.json"
    path.write_text(json.dumps({
        "as_of": as_of,
        "candidates": [{"code": code, "score": 80.0}],
        "review_queue": [],
    }), encoding="utf-8")
    return path


def write_uzi_cache(
    root: Path,
    *,
    overall_score: float,
    data_coverage: float,
    panel_consensus: float,
    blocked: bool,
) -> None:
    root.mkdir(parents=True)
    (root / "synthesis.json").write_text(json.dumps({
        "ticker": root.name,
        "overall_score": overall_score,
        "data_coverage": data_coverage,
        "panel_consensus": panel_consensus,
        "uzi_decision_state": "blocked" if blocked else "approved",
    }), encoding="utf-8")


def test_ai_discovery_reads_candidates_and_review_queue_without_making_orders(tmp_path):
    path = tmp_path / "weekly_candidates_20260804.json"
    path.write_text(json.dumps({
        "as_of": "2026-08-04",
        "candidates": [{"code": "sz.300170", "score": 82.0}],
        "review_queue": [{
            "code": "sh.600489",
            "score": 74.0,
            "uzi": {"score": 69.0, "data_coverage": 0.70},
            "uzi_decision": {"state": "approved"},
        }],
    }), encoding="utf-8")

    evidence = load_ai_discovery(tmp_path, date(2026, 8, 5))

    assert evidence["300170.SZ"].ai_score == 82.0
    assert evidence["600489.SH"].uzi_score == 69.0
    assert not hasattr(evidence["300170.SZ"], "quantity")


def test_stale_ai_file_is_ignored_with_no_exception(tmp_path):
    write_weekly_file(tmp_path, as_of="2026-07-01", code="sz.300170")
    assert load_ai_discovery(tmp_path, date(2026, 8, 5), max_age_days=10) == {}


def test_ai_discovery_merges_hints_for_same_candidate_across_both_lists(tmp_path):
    (tmp_path / "weekly_candidates_20260804.json").write_text(json.dumps({
        "as_of": "2026-08-04",
        "candidates": [{"code": "sz.300170", "score": 82.0}],
        "review_queue": [{
            "code": "300170.SZ",
            "uzi": {"score": 69.0, "data_coverage": 0.70},
        }],
    }), encoding="utf-8")

    evidence = load_ai_discovery(tmp_path, date(2026, 8, 5))

    assert evidence["300170.SZ"].ai_score == 82.0
    assert evidence["300170.SZ"].uzi_score == 69.0


def test_future_ai_file_and_invalid_score_are_ignored(tmp_path):
    future = write_weekly_file(tmp_path, as_of="2026-08-06", code="sz.300170")
    invalid = tmp_path / "weekly_candidates_20260805.json"
    invalid.write_text(json.dumps({
        "as_of": "2026-08-05",
        "candidates": [{"code": "300759.SZ", "score": 101.0}],
        "review_queue": [],
    }), encoding="utf-8")

    assert load_ai_discovery(tmp_path, date(2026, 8, 5)) == {}
    assert future.exists()


def test_uzi_cache_uses_score_coverage_and_explicit_block(tmp_path):
    write_uzi_cache(
        tmp_path / "300170.SZ",
        overall_score=72.0,
        data_coverage=0.68,
        panel_consensus=66.0,
        blocked=True,
    )
    evidence = load_uzi_evidence(
        tmp_path, ["300170.SZ"], aware_at(2026, 8, 5)
    )
    assert evidence["300170.SZ"].uzi_state == "blocked"
    assert evidence["300170.SZ"].uzi_score == 72.0


def test_malformed_uzi_json_is_recorded_as_unavailable(tmp_path):
    cache = tmp_path / "300170.SZ"
    cache.mkdir()
    (cache / "synthesis.json").write_text("not-json", encoding="utf-8")
    evidence = load_uzi_evidence(
        tmp_path, ["300170.SZ"], aware_at(2026, 8, 5)
    )
    assert evidence["300170.SZ"].uzi_state == "unavailable"
    assert "uzi_invalid_json" in evidence["300170.SZ"].reasons


def test_uzi_stale_cache_degrades_to_unavailable(tmp_path):
    cache = tmp_path / "300759.SZ"
    write_uzi_cache(
        cache, overall_score=72.0, data_coverage=0.68,
        panel_consensus=66.0, blocked=False,
    )
    source = cache / "synthesis.json"
    stale = aware_at(2026, 7, 1).timestamp()
    os.utime(source, (stale, stale))

    evidence = load_uzi_evidence(
        tmp_path, ["sz.300759"], aware_at(2026, 8, 5), max_age_days=10
    )

    assert evidence["300759.SZ"].uzi_state == "unavailable"
    assert "uzi_stale" in evidence["300759.SZ"].reasons


def test_merge_normalizes_ids_and_preserves_explicit_uzi_block():
    ai = ResearchEvidence("sz.300759", ai_score=81.0, uzi_state="approved")
    uzi = ResearchEvidence(
        "300759.SZ", uzi_score=71.0, uzi_coverage=0.72,
        uzi_state="blocked", source_dates=("2026-08-05",),
        source_paths=("cache/synthesis.json",), reasons=("uzi_blocked",),
    )

    merged = merge_research_evidence({"sz.300759": ai}, {"300759.SZ": uzi})

    result = merged["300759.SZ"]
    assert result.ai_score == 81.0
    assert result.uzi_score == 71.0
    assert result.uzi_state == "blocked"
    assert result.source_dates == ("2026-08-05",)
    assert result.reasons == ("uzi_blocked",)
    assert isinstance(result.source_paths, tuple)
