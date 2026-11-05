"""Synthetic, offline contracts for the isolated industry rotation tool."""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.industry_rotation.core import INDUSTRIES, daily_factors, load_bigquant_panel, make_schedule, signal_scores
from lib.industry_rotation.flow import infer_flow_graph
from lib.industry_rotation.report import render_report
from lib.industry_rotation.snapshot import build_snapshot, load_proxy
from rotate import main


def sample_rows(count=40):
    days = []
    day = date(2026, 8, 3)
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    rows = []
    for n, day in enumerate(days):
        for i, spec in enumerate(INDUSTRIES):
            rows.append({
                "date": str(day), "l1_code": spec.source_code if spec.source_level == "l1" else "X" + str(i),
                "l1_name": spec.name, "l2_code": spec.source_code if spec.source_level == "l2" else "Y" + str(i),
                "l2_name": spec.name, "active_buy_amount": 100 + i + n,
                "active_sell_amount": 100 + (i * 7 + n) % 39, "turnover_amount": 300 + i,
                "float_market_cap": 10000 + i * 100, "industry_return": 0.01 * math.sin(i + n),
            })
    return rows


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture
def panel_file(tmp_path):
    return write_csv(tmp_path / "panel.csv", sample_rows())


@pytest.fixture
def proxy_file(tmp_path):
    rows = [{"rank": i + 1, "code": f"SW{i}", "name": f"行业{i}", "score": 5 - i} for i in range(5)]
    payload = {"status": "public_proxy_nowcast_not_bigquant_or_wind", "as_of": "2026-09-25",
               "windows": {str(w): {"base": rows, "composite": rows} for w in range(20, 25)}}
    path = tmp_path / "proxy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_mapping_and_factor_math(panel_file):
    days, panel, manifest = load_bigquant_panel(panel_file)
    assert len(INDUSTRIES) == len({spec.key for spec in INDUSTRIES}) == 40
    assert manifest["complete_days"] == 40
    factors = daily_factors(days[-20:], panel)
    base, composite = signal_scores(days[-20:], factors, 20)
    raw = []
    for spec in INDUSTRIES:
        values = []
        for day in days[-20:]:
            row = panel[day][spec.key]
            total_buy = sum(x.active_buy for x in panel[day].values())
            total_sell = sum(x.active_sell for x in panel[day].values())
            total_turnover = sum(x.turnover for x in panel[day].values())
            values.append((row.active_buy / total_buy - row.active_sell / total_sell) / (row.turnover / total_turnover))
        raw.append(statistics.fmean(values))
    mean, std = statistics.fmean(raw), statistics.pstdev(raw)
    assert list(base[days[-1]].values()) == pytest.approx([(v - mean) / std for v in raw])
    assert all(math.isfinite(v) for v in composite[days[-1]].values())


@pytest.mark.parametrize("field,value", [
    ("active_buy_amount", "nan"), ("active_sell_amount", "inf"), ("active_buy_amount", -1),
    ("turnover_amount", 0), ("float_market_cap", ""), ("industry_return", -1),
])
def test_reject_bad_numbers(tmp_path, field, value):
    rows = sample_rows(1)
    rows[0][field] = value
    with pytest.raises(ValueError):
        load_bigquant_panel(write_csv(tmp_path / "bad.csv", rows))


def test_duplicates_and_incomplete_cross_section(tmp_path):
    rows = sample_rows(1)
    with pytest.raises(ValueError, match="重复"):
        load_bigquant_panel(write_csv(tmp_path / "duplicate.csv", rows + [rows[0]]))
    with pytest.raises(ValueError, match="非完整40"):
        load_bigquant_panel(write_csv(tmp_path / "missing.csv", rows[1:]))


def test_l1_aggregation_uses_start_cap(tmp_path):
    rows = sample_rows(1)
    rows[0].update(float_market_cap=110, industry_return=0.1)
    extra = dict(rows[0], l2_code="EXTRA", float_market_cap=90, industry_return=-0.1)
    days, panel, _ = load_bigquant_panel(write_csv(tmp_path / "aggregate.csv", rows + [extra]))
    assert panel[days[0]][INDUSTRIES[0].key].daily_return == pytest.approx(0)


def test_graph_conserves_mass_and_is_antisymmetric():
    net = [0.03, -0.02, -0.01]
    flow = infer_flow_graph(net, [0.01, -0.02, 0.03])
    assert [sum(row) for row in flow] == pytest.approx([0, *net], abs=1e-10)
    for i, row in enumerate(flow):
        for j, value in enumerate(row):
            assert value == pytest.approx(-flow[j][i])


def test_window_requires_history_and_zero_variance():
    days = [date(2026, 1, 2), date(2026, 1, 5)]
    factors = {day: {spec.key: (1, 1, 1, 1, 1) for spec in INDUSTRIES} for day in days}
    base, composite = signal_scores(days, factors, 2)
    assert days[0] not in base
    assert set(base[days[1]].values()) == {0}
    assert set(composite[days[1]].values()) == {0}
    with pytest.raises(ValueError):
        signal_scores(days, factors, 0)


def test_weekly_signal_lags_and_does_not_trade_midweek():
    days = [date(2026, 10, 30), date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)]
    scores = {days[0]: {"A": 2, "B": 1}, **{day: {"A": 1, "B": 5} for day in days[1:]}}
    assert make_schedule(days, scores, 1) == [(days[0], days[1], ("A",))]


def test_as_of_filters_future_rows_and_keeps_proxy_isolated(panel_file, proxy_file, tmp_path):
    cutoff = date(2026, 9, 25)
    result = build_snapshot(panel_file, cutoff)
    with_proxy = build_snapshot(panel_file, cutoff, proxy_file)
    assert result["formal"] == with_proxy["formal"]
    assert with_proxy["execution_status"] == "observation_only"
    rows = sample_rows(41)
    rows[-1]["active_buy_amount"] = 1e12
    extended = build_snapshot(write_csv(tmp_path / "extended.csv", rows), cutoff)
    assert extended["formal"]["windows"] == result["formal"]["windows"]
    assert len(result["formal"]["windows"]) == 5
    for block in result["formal"]["windows"].values():
        assert len(block["base"]) == 40
        assert block["base_weekly_target"]["signal_date"] < block["base_weekly_target"]["model_entry_close"]


@pytest.mark.parametrize("mutation", ["future", "duplicate", "nan", "missing_window", "wrong_status", "unsorted"])
def test_proxy_contract_rejects_invalid(proxy_file, mutation):
    payload = json.loads(proxy_file.read_text())
    if mutation == "future":
        payload["as_of"] = "2026-09-26"
    elif mutation == "duplicate":
        payload["windows"]["20"]["base"][1]["code"] = "SW0"
    elif mutation == "nan":
        payload["windows"]["20"]["base"][0]["score"] = float("nan")
    elif mutation == "missing_window":
        del payload["windows"]["24"]
    elif mutation == "unsorted":
        payload["windows"]["20"]["base"][0]["score"] = -999
    else:
        payload["status"] = "formal"
    proxy_file.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises((ValueError, KeyError)):
        load_proxy(proxy_file, date(2026, 9, 25))


def test_html_escapes_external_names_and_cli_outputs(panel_file, proxy_file, tmp_path):
    result = build_snapshot(panel_file, date(2026, 9, 25), proxy_file)
    result["proxy"]["windows"]["20"]["base"][0]["name"] = "<script>alert('x')</script>"
    html = render_report(result)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    assert "https://" not in html
    output = tmp_path / "report"
    main(["--bigquant", str(panel_file), "--as-of", "2026-09-25", "--output-dir", str(output)])
    assert {p.name for p in output.iterdir()} == {"rotation.json", "rankings.csv", "report.html"}
    payload = json.loads((output / "rotation.json").read_text())
    assert payload["proxy"] is None
    assert len(list(csv.DictReader((output / "rankings.csv").open(encoding="utf-8-sig")))) == 400


def test_insufficient_history_stops(tmp_path):
    with pytest.raises(ValueError, match="25"):
        build_snapshot(write_csv(tmp_path / "short.csv", sample_rows(24)), date(2026, 9, 25))


def test_proxy_rejects_non_object(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="顶层"):
        load_proxy(path, date(2026, 9, 25))


def test_input_overflow_is_rejected(tmp_path):
    rows = sample_rows(1)
    for row in rows:
        row["active_buy_amount"] = 1e308
    days, panel, _ = load_bigquant_panel(write_csv(tmp_path / "large.csv", rows))
    with pytest.raises(ValueError):
        daily_factors(days, panel)


def test_cli_refuses_input_overwrite(panel_file, tmp_path):
    protected = tmp_path / "rankings.csv"
    protected.write_bytes(panel_file.read_bytes())
    before = protected.read_bytes()
    with pytest.raises(SystemExit):
        main(["--bigquant", str(protected), "--as-of", "2026-09-25", "--output-dir", str(tmp_path)])
    assert protected.read_bytes() == before
