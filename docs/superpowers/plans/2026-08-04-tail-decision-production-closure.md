# Tail Decision Production Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the production gaps left after the no-token offline acceptance so the local CLI can build real ETF and overnight-stock contexts, maintain next-session paper exits, and start auditable forward validation without Tushare or Codex.

**Architecture:** Keep the existing `lib/tail_decision` boundary and add four explicit local services: recent-archive access, a deterministic liquid universe, an append-only quote snapshot store, and an append-only paper-position ledger. A credential-free production gateway composes those services with the existing Eastmoney/Tencent adapters and conservative announcement risk checks; the CLI remains the only entry point, while Windows Task Scheduler drives phases and a forward journal measures readiness.

**Tech Stack:** Python 3.11+, pandas, requests, pytest, standard-library dataclasses/json/pathlib/concurrent.futures, PowerShell ScheduledTasks.

## Global Constraints

- Core execution must succeed with `TUSHARE_TOKEN`, `.env`, and paid Tushare permissions absent.
- Tushare remains an optional after-close enhancement and must not be imported by any module in `lib/tail_decision`.
- Read historical data only from `D:/work/gupiao/data/tushare_calendar`; never mutate `raw`, `normalized`, or manifests.
- Do not restore 179-item full-catalog collection or fetch historical full-market minute bars.
- Persist only forward snapshots collected by the scheduled 14:00/14:10/14:20/14:30/15:05/09:25/09:35 phases.
- Two independent realtime quotes are required for a `recommended` allocation; one source is `watch_only`, and conflicts above 0.3% are `blocked`.
- ETF plus stock exposure shares one CNY 8,000 cap; initial per-instrument exposure remains CNY 4,000.
- Announcement status that cannot be checked is not treated as safe: that stock may be observed but cannot be allocated.
- No broker connection, order submission, credential logging, or automatic conversion of paper fills into real fills.
- All state files are append-only, deterministic for identical inputs, recursively redacted, and rooted under the configured output root.
- Preserve the dirty worktree. Stage and commit only files explicitly named by the current task.
- Every production behavior is test-first: run the named test, verify the stated RED reason, implement the minimum behavior, rerun focused tests, then commit.

---

## File Map

```text
skills/deep-analysis/scripts/lib/tail_decision/
  archive.py          recent dated partitions and static master files
  universe.py         deterministic liquid ETF/stock universe from local archive
  snapshot_store.py   append-only normalized forward quote snapshots and intraday bars
  event_risk.py       credential-free announcement title check and conservative classifier
  gateway.py          production context composition; no CLI-private gateway logic
  phase_ledger.py     final-plan, paper-entry, exit-signal, and paper-exit lifecycle
  forward.py          daily forward evidence and 60-day/40-trade gate summary
  workflow.py         phase orchestration hook for ledger advancement
  recorder.py         existing immutable decision artifacts
skills/deep-analysis/scripts/run_tail_decision.py
scripts/install_tail_decision_tasks.ps1
scripts/check_tail_decision_tasks.ps1
skills/deep-analysis/scripts/tests/tail_decision/
  test_archive.py
  test_universe.py
  test_snapshot_store.py
  test_event_risk.py
  test_gateway.py
  test_phase_ledger.py
  test_forward.py
  test_cli.py
  test_scheduler_script.py
  test_production_no_token_e2e.py
docs/data/tail-decision-operations.md
docs/data/tail-decision-implementation-report.md
```

Do not modify `run.py`, `lib/data_sources.py`, `lib/pipeline/*`, or the Tushare exporters. Reuse only their public data artifacts, not their runtime import graph.

---

### Task 1: Recent Archive Windows and Static Masters

**Files:**
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/archive.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_archive.py`

**Interfaces:**
- Produces: `ArchiveReader.read_recent(dataset: str, as_of: date | datetime, partition_count: int, *, required: bool = True) -> pd.DataFrame`.
- Produces: `ArchiveReader.read_static(dataset: str, candidates: tuple[str, ...], *, required: bool = True) -> pd.DataFrame`.
- `read_recent` concatenates only the newest `partition_count` dated files at or before `as_of`, adds `_archive_partition`, and sorts deterministically by partition and original row order.
- `read_static` accepts exact filenames such as `("listed.csv.gz",)` and never selects an arbitrary file.

- [ ] **Step 1: Write failing recent/static archive tests**

```python
def test_read_recent_combines_only_latest_requested_partitions(tmp_path):
    root = tmp_path / "normalized" / "daily"
    root.mkdir(parents=True)
    for day, close in (("20260728", 10), ("20260729", 11), ("20260730", 12)):
        pd.DataFrame([{"ts_code": "600000.SH", "trade_date": day, "close": close}]).to_csv(
            root / f"{day}.csv.gz", index=False
        )
    frame = ArchiveReader(tmp_path).read_recent("daily", date(2026, 7, 30), 2)
    assert frame["trade_date"].astype(str).tolist() == ["20260729", "20260730"]
    assert frame["_archive_partition"].tolist() == ["20260729", "20260730"]


def test_read_static_requires_an_exact_candidate_name(tmp_path):
    root = tmp_path / "normalized" / "stock_basic"
    root.mkdir(parents=True)
    pd.DataFrame([{"ts_code": "600000.SH"}]).to_csv(root / "listed.csv.gz", index=False)
    frame = ArchiveReader(tmp_path).read_static("stock_basic", ("listed.csv.gz",))
    assert frame["ts_code"].tolist() == ["600000.SH"]
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_archive.py -v`

Expected: both tests fail with `AttributeError` because `read_recent` and `read_static` do not exist.

- [ ] **Step 3: Implement deterministic multi-partition reads**

Add a private `_dated_partitions(dataset, as_of)` that reuses `_partition_date`, sorts by `(date, filename)`, and never walks outside `root/normalized/<dataset>`. Reject non-positive `partition_count`; use the existing `ArchiveDataError` wrapping for malformed CSV/Parquet files. Normalize `_archive_partition` to `YYYYMMDD` strings.

```python
def read_recent(self, dataset, as_of, partition_count, *, required=True):
    if partition_count <= 0:
        raise ValueError("partition_count must be positive")
    selected = self._dated_partitions(dataset, as_of)[-partition_count:]
    if not selected:
        if required:
            raise ArchiveDataError(f"no dated partitions for dataset {dataset!r}")
        return pd.DataFrame()
    frames = []
    for partition_date, path in selected:
        frame = _read_frame(path)
        frame["_archive_partition"] = partition_date.strftime("%Y%m%d")
        frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False)
```

- [ ] **Step 4: Run focused and existing archive tests**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_archive.py -v`

Expected: all archive tests pass; existing `read_latest` and `read_trade_dates` behavior remains unchanged.

- [ ] **Step 5: Commit only Task 1**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/archive.py skills/deep-analysis/scripts/tests/tail_decision/test_archive.py
git commit -m "feat: read recent tail archive windows"
```

---

### Task 2: Deterministic Local Liquid Universe

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/universe.py`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/test_universe.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/__init__.py`

**Interfaces:**
- Produces: immutable `Universe(etfs: tuple[str, ...], stocks: tuple[str, ...])`.
- Produces: `build_liquid_universe(stock_daily, fund_daily, stock_basic, etf_basic, *, max_stocks=20, max_etfs=10) -> Universe`.
- Amount columns from Tushare daily/fund_daily are normalized from thousand CNY to CNY before thresholding.
- Explicit `tail_decision_universe.json` remains an override; empty or malformed overrides are blocked instead of silently falling back.

- [ ] **Step 1: Write the failing universe test**

```python
def test_universe_uses_twenty_day_liquidity_and_excludes_risky_masters():
    stock_daily = pd.DataFrame([
        {"ts_code": "600001.SH", "trade_date": "20260729", "amount": 500_000},
        {"ts_code": "600001.SH", "trade_date": "20260730", "amount": 700_000},
        {"ts_code": "600002.SH", "trade_date": "20260730", "amount": 900_000},
    ])
    stock_basic = pd.DataFrame([
        {"ts_code": "600001.SH", "name": "正常股份", "list_date": "20100101"},
        {"ts_code": "600002.SH", "name": "*ST风险", "list_date": "20100101"},
    ])
    fund_daily = pd.DataFrame([
        {"ts_code": "510300.SH", "trade_date": "20260730", "amount": 800_000},
    ])
    etf_basic = pd.DataFrame([
        {"ts_code": "510300.SH", "list_status": "L", "index_name": "沪深300"},
    ])
    universe = build_liquid_universe(stock_daily, fund_daily, stock_basic, etf_basic)
    assert universe.stocks == ("600001.SH",)
    assert universe.etfs == ("510300.SH",)
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_universe.py -v`

Expected: import fails because `lib.tail_decision.universe` does not exist.

- [ ] **Step 3: Implement stable ranking and exclusions**

Group by `ts_code`, use the newest 20 rows per instrument, rank by descending mean CNY amount then ascending `ts_code`, and cap to 20 stocks/10 ETFs. Exclude stock names beginning with `ST`/`*ST` or containing `退`, missing/too-recent listings, and non-listed ETF masters. Preserve explicit user order only for a valid override file.

```python
@dataclass(frozen=True)
class Universe:
    etfs: tuple[str, ...]
    stocks: tuple[str, ...]


def _rank_amount(frame: pd.DataFrame, limit: int) -> tuple[str, ...]:
    ranked = (
        frame.sort_values(["ts_code", "trade_date"], kind="stable")
        .groupby("ts_code", sort=True).tail(20)
        .assign(amount_cny=lambda value: pd.to_numeric(value["amount"], errors="coerce") * 1000.0)
        .groupby("ts_code", sort=True)["amount_cny"].mean()
        .sort_values(ascending=False, kind="stable")
    )
    return tuple(ranked.head(limit).index.astype(str))
```

- [ ] **Step 4: Verify universe determinism**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_universe.py skills/deep-analysis/scripts/tests/tail_decision/test_archive.py -v`

Expected: all tests pass, including the same ordering after shuffled input rows.

- [ ] **Step 5: Commit only Task 2**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/universe.py skills/deep-analysis/scripts/lib/tail_decision/__init__.py skills/deep-analysis/scripts/tests/tail_decision/test_universe.py
git commit -m "feat: derive local liquid tail universe"
```

---

### Task 3: Append-Only Forward Snapshot Store

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/snapshot_store.py`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/test_snapshot_store.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/features.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_features.py`

**Interfaces:**
- Produces: `QuoteSnapshotStore(root: Path)`.
- Produces: `append(*, phase: str, quotes: Mapping[str, Sequence[QuoteSnapshot]]) -> Path`.
- Produces: `read_intraday(instrument_id: str, as_of: datetime) -> pd.DataFrame` with `timestamp/open/high/low/close/volume/amount`, where volume and amount are per-snapshot deltas derived from cumulative provider counters.
- A retry may append a duplicate raw record, but `read_intraday` deduplicates by `(instrument_id, source, timestamp, fetched_at)` and selects one provider per timestamp by fixed priority `eastmoney`, then `tencent`.

- [ ] **Step 1: Write failing append/read tests**

```python
from .fixtures import quote


def test_snapshot_store_reconstructs_forward_intraday_deltas(tmp_path):
    store = QuoteSnapshotStore(tmp_path)
    at_1400 = datetime.fromisoformat("2026-08-04T14:00:00+08:00")
    at_1410 = datetime.fromisoformat("2026-08-04T14:10:00+08:00")
    first = quote(
        instrument_id="510300.SH", instrument_type=InstrumentType.ETF,
        timestamp=at_1400, fetched_at=at_1400, volume=1000, amount=10_000,
    )
    second = quote(
        instrument_id="510300.SH", instrument_type=InstrumentType.ETF,
        timestamp=at_1410, fetched_at=at_1410, volume=1300, amount=13_600,
    )
    store.append(phase="warmup", quotes={"510300.SH": [first]})
    store.append(phase="preview", quotes={"510300.SH": [second]})
    bars = store.read_intraday("510300.SH", at_1410)
    assert bars["volume"].tolist() == [1000.0, 300.0]
    assert bars["amount"].tolist() == [10_000.0, 3_600.0]
    assert build_intraday_features(bars, at_1410)["production_ready"] is True
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_snapshot_store.py -v`

Expected: import fails because `snapshot_store.py` does not exist.

- [ ] **Step 3: Implement atomic JSONL append and deterministic bars**

Use one file per Shanghai calendar day under `<output-root>/cache/tail_decision/snapshots/YYYYMMDD.jsonl`. Acquire an exclusive sibling lock with `os.open(..., O_CREAT | O_EXCL)` and bounded retry; write one compact redacted JSON object per quote, flush, and `fsync`. Reject paths escaping the configured root. Convert cumulative counters to non-negative deltas; a counter reset starts a new baseline rather than producing a negative bar.

```python
def _counter_deltas(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0).clip(lower=0.0)
    delta = numeric.diff()
    delta.iloc[0] = numeric.iloc[0]
    return delta.where(delta >= 0.0, numeric)
```

- [ ] **Step 4: Verify snapshots and feature cutoff behavior**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_snapshot_store.py skills/deep-analysis/scripts/tests/tail_decision/test_features.py -v`

Expected: append-only, duplicate-read, counter-reset, and post-`as_of` exclusion tests all pass.

- [ ] **Step 5: Commit only Task 3**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/snapshot_store.py skills/deep-analysis/scripts/lib/tail_decision/features.py skills/deep-analysis/scripts/tests/tail_decision/test_snapshot_store.py skills/deep-analysis/scripts/tests/tail_decision/test_features.py
git commit -m "feat: persist forward tail quote snapshots"
```

---

### Task 4: Conservative Event Risk and Production Context Gateway

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/event_risk.py`
- Create: `skills/deep-analysis/scripts/lib/tail_decision/gateway.py`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/test_event_risk.py`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/test_gateway.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/free_quotes.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_free_quotes.py`
- Modify: `skills/deep-analysis/scripts/run_tail_decision.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_cli.py`

**Interfaces:**
- Produces: `Announcement(title: str, published_at: datetime, source: str)`.
- Produces: `EastmoneyAnnouncementProvider.fetch(instrument_id: str, as_of: datetime) -> tuple[Announcement, ...]` using `https://np-anotice-stock.eastmoney.com/api/security/ann` without credentials.
- Produces: `evaluate_event_risk(announcements, *, source_ok: bool) -> Mapping[str, object]`; source failure sets `event_status="unknown"` and `adverse_event=True`.
- Produces: `CredentialFreeGateway(config, archive_reader, snapshot_store, quote_providers, announcement_provider, universe_override=None)` implementing `WorkflowGateway.collect`.
- Eastmoney quote requests use bounded `ThreadPoolExecutor(max_workers=8)` with per-instrument isolation; Tencent remains one batch request.

- [ ] **Step 1: Write failing event and gateway tests**

```python
def test_unknown_announcement_status_blocks_stock_allocation():
    risk = evaluate_event_risk((), source_ok=False)
    assert risk == {"event_status": "unknown", "adverse_event": True, "risk_titles": ()}


def test_gateway_builds_real_context_from_archive_and_forward_snapshots(tmp_path, fake_providers):
    archive_root = tmp_path / "archive"
    state_root = tmp_path / "state"
    seed_gateway_archive(archive_root)
    gateway = CredentialFreeGateway(
        config=DecisionConfig(),
        archive_reader=ArchiveReader(archive_root),
        snapshot_store=QuoteSnapshotStore(state_root),
        quote_providers=fake_providers,
        announcement_provider=SafeAnnouncementProvider(),
        universe_override=Universe(etfs=("510300.SH",), stocks=("600001.SH",)),
    )
    inputs = gateway.collect(
        as_of=datetime.fromisoformat("2026-08-04T14:30:00+08:00"),
        phase="final",
    )
    stock = inputs.stock_contexts[0]
    assert stock.intraday["production_ready"] is True
    assert stock.historical["avg_amount_20d"] == 600_000_000.0
    assert stock.metadata["name"] == "正常股份"
    assert stock.events["event_status"] == "checked"
```

Define the named test helpers in the same test file; they are deterministic and perform no network I/O:

```python
class SafeAnnouncementProvider:
    def fetch(self, instrument_id, as_of):
        return ()


def seed_gateway_archive(root):
    normalized = root / "normalized"
    for day in ("20260729", "20260730"):
        for dataset, code, amount in (
            ("daily", "600001.SH", 600_000),
            ("fund_daily", "510300.SH", 800_000),
        ):
            target = normalized / dataset
            target.mkdir(parents=True, exist_ok=True)
            pd.DataFrame([{
                "ts_code": code, "trade_date": day, "close": 10.0,
                "amount": amount,
            }]).to_csv(target / f"{day}.csv.gz", index=False)
    masters = {
        "stock_basic/listed.csv.gz": [{
            "ts_code": "600001.SH", "name": "正常股份", "list_date": "20100101",
        }],
        "etf_basic/20260730.csv.gz": [{
            "ts_code": "510300.SH", "list_status": "L", "index_name": "沪深300",
        }],
    }
    for relative, rows in masters.items():
        target = normalized / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(target, index=False)


class StaticQuoteProvider:
    def __init__(self, name):
        self.name = name

    def fetch_quotes(self, ids, now):
        result = {}
        for instrument_id in ids:
            kind = InstrumentType.ETF if instrument_id == "510300.SH" else InstrumentType.STOCK
            result[instrument_id] = quote(
                instrument_id=instrument_id, instrument_type=kind,
                timestamp=now, fetched_at=now, source=self.name,
            )
        return result


@pytest.fixture
def fake_providers():
    return (StaticQuoteProvider("eastmoney"), StaticQuoteProvider("tencent"))
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_event_risk.py skills/deep-analysis/scripts/tests/tail_decision/test_gateway.py -v`

Expected: imports fail because `event_risk.py` and `gateway.py` do not exist.

- [ ] **Step 3: Implement event classification and context composition**

Classify only titles published between the previous trading close and `as_of`. Risk keywords are exact deterministic configuration data: `立案`, `调查`, `处罚`, `减持`, `终止`, `退市`, `预亏`, `诉讼`, `冻结`, `逾期`, `平仓`, `重大损失`. Do not use article bodies or an LLM. Gateway steps are fixed: load 20 recent `daily`, `fund_daily`, `daily_basic`, and optional `moneyflow`; load exact `stock_basic/listed.csv.gz` and latest `etf_basic`; build/override the universe; fetch both quote sources; append snapshots; evaluate quality; build intraday and historical features; attach `stock_st`, `suspend_d`, and `stk_limit`; attach conservative event risk; return `WorkflowInputs`.

For ETF `premium_proxy_pct`, use the maximum current cross-source last-price deviation as an explicitly labeled market-price anomaly proxy, not as NAV premium. Set `metadata["premium_proxy_source"] = "cross_source_price_deviation"`; missing dual-source quotes leave the proxy absent and prevent recommendation through the quality gate.

```python
class CredentialFreeGateway:
    def collect(self, *, as_of: datetime, phase: str) -> WorkflowInputs:
        universe = self._universe(as_of)
        quotes = fetch_from_providers(self.quote_providers, (*universe.etfs, *universe.stocks), as_of)
        self.snapshot_store.append(phase=phase, quotes=quotes)
        historical = self._historical_features(as_of)
        return self._contexts(as_of, phase, universe, quotes, historical)
```

- [ ] **Step 4: Move production wiring out of the CLI**

Delete CLI-private `_CredentialFreeGateway`, `_live_context`, and hard-coded production defaults. Instantiate `ArchiveReader`, `QuoteSnapshotStore`, `CredentialFreeGateway`, and the optional explicit universe override from arguments. Add `--state-root` defaulting to `<output-root>/cache/tail_decision`; keep `--offline-fixture` unchanged for deterministic acceptance.

- [ ] **Step 5: Verify production composition without network**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_event_risk.py skills/deep-analysis/scripts/tests/tail_decision/test_gateway.py skills/deep-analysis/scripts/tests/tail_decision/test_free_quotes.py skills/deep-analysis/scripts/tests/tail_decision/test_cli.py -v
```

Expected: fake-provider production flow yields real historical/intraday context; source failure is conservative; CLI fixture behavior remains passing; no test reads a token.

- [ ] **Step 6: Commit only Task 4**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/event_risk.py skills/deep-analysis/scripts/lib/tail_decision/gateway.py skills/deep-analysis/scripts/lib/tail_decision/free_quotes.py skills/deep-analysis/scripts/run_tail_decision.py skills/deep-analysis/scripts/tests/tail_decision/test_event_risk.py skills/deep-analysis/scripts/tests/tail_decision/test_gateway.py skills/deep-analysis/scripts/tests/tail_decision/test_free_quotes.py skills/deep-analysis/scripts/tests/tail_decision/test_cli.py
git commit -m "feat: build credential-free production contexts"
```

---

### Task 5: Persistent Paper Position and Next-Session Exit Ledger

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/phase_ledger.py`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/test_phase_ledger.py`
- Modify: `skills/deep-analysis/scripts/run_tail_decision.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_cli.py`
- Modify: `docs/data/tail-decision-operations.md`

**Interfaces:**
- Produces: `PhaseLedger(root: Path)` with append-only `<state-root>/ledger/events.jsonl`.
- Produces: `advance(*, phase: str, run: DecisionRun) -> tuple[Mapping[str, object], ...]`.
- Event kinds are frozen: `plan_created`, `paper_entry`, `paper_entry_unfilled`, `exit_signal`, `paper_exit`, `paper_exit_blocked`.
- `current_positions(as_of)` replays events; it never edits prior lines.
- `final` records plans, `close` creates paper entries only when a PASS canonical quote is at/below the limit, `exit_open` records advice, and `exit_check` closes on a tradable PASS quote or records a block. Real fills require a future explicit manual-import interface and are out of scope.

- [ ] **Step 1: Write the failing lifecycle test**

```python
def test_phase_ledger_replays_plan_entry_signal_and_exit(tmp_path):
    ledger = PhaseLedger(tmp_path)
    final = decision_run(run_id="20260804T143000_final")
    ledger.advance(phase="final", run=final)
    ledger.advance(phase="close", run=phase_run("close", "2026-08-04T15:05:00+08:00", 24.99))
    next_open = datetime.fromisoformat("2026-08-05T09:25:00+08:00")
    assert ledger.current_positions(as_of=next_open).keys() == {"600406.SH"}
    ledger.advance(phase="exit_open", run=phase_run("exit_open", "2026-08-05T09:25:00+08:00", 25.40))
    ledger.advance(phase="exit_check", run=phase_run("exit_check", "2026-08-05T09:35:00+08:00", 25.30))
    assert ledger.current_positions(as_of=datetime.fromisoformat("2026-08-05T09:35:00+08:00")) == {}
    assert [row["kind"] for row in ledger.read_events()] == [
        "plan_created", "paper_entry", "exit_signal", "paper_exit"
]
```

Define `phase_run` in the test with existing frozen contracts:

```python
def phase_run(phase, as_of, price):
    instant = datetime.fromisoformat(as_of)
    first = quote(timestamp=instant, fetched_at=instant, last_price=price, source="eastmoney")
    second = quote(timestamp=instant, fetched_at=instant, last_price=price, source="tencent")
    quality = QualityDecision(
        instrument_id="600406.SH", level=QualityLevel.PASS, reasons=(),
        canonical_quote=first, source_quotes=(first, second),
    )
    return replace(
        decision_run(run_id=f"{instant.strftime('%Y%m%dT%H%M%S')}_{phase}"),
        as_of=instant, status=DecisionStatus.NO_TRADE, quality=(quality,),
        etf_candidates=(), stock_candidates=(), allocations=(),
        reasons=(f"{phase}_completed",),
    )
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_phase_ledger.py -v`

Expected: import fails because `phase_ledger.py` does not exist.

- [ ] **Step 3: Implement deterministic event replay**

Use `run_id + kind + instrument_id` as the idempotency key so Task Scheduler retries do not duplicate lifecycle transitions. Persist strategy/config hashes, planned quantity/limit/notional, candidate exit plan, quote source timestamps, paper entry/exit prices, gross P&L, costs from `simulator.py`, net P&L, and block reasons. Never infer that a real order was filled.

```python
def advance(self, *, phase: str, run: DecisionRun):
    handlers = {
        "final": self._record_plans,
        "close": self._record_entries,
        "exit_open": self._record_exit_signals,
        "exit_check": self._record_exits,
    }
    handler = handlers.get(phase)
    return () if handler is None else handler(run)
```

- [ ] **Step 4: Wire ledger advancement after immutable run recording**

The CLI calls `workflow.run`, then `ledger.advance`. If ledger advancement fails, print a `blocked` summary and return 2; do not rewrite the already-recorded decision artifact. Include `ledger_events` count in CLI JSON, never full secret-bearing environment data.

- [ ] **Step 5: Verify retry and next-session behavior**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_phase_ledger.py skills/deep-analysis/scripts/tests/tail_decision/test_cli.py skills/deep-analysis/scripts/tests/tail_decision/test_simulator.py -v`

Expected: lifecycle, retry idempotency, T+1 stock exit, untradeable exit blocking, and CLI failure semantics all pass.

- [ ] **Step 6: Commit only Task 5**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/phase_ledger.py skills/deep-analysis/scripts/run_tail_decision.py skills/deep-analysis/scripts/tests/tail_decision/test_phase_ledger.py skills/deep-analysis/scripts/tests/tail_decision/test_cli.py docs/data/tail-decision-operations.md
git commit -m "feat: persist tail paper exits"
```

---

### Task 6: Forward Validation Journal and Release Gates

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/forward.py`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/test_forward.py`
- Modify: `skills/deep-analysis/scripts/run_tail_decision.py`
- Modify: `docs/data/tail-decision-operations.md`
- Modify: `docs/data/tail-decision-implementation-report.md`

**Interfaces:**
- Produces: `ForwardJournal(root: Path)`.
- Produces: `record_day(run: DecisionRun, ledger_events: Sequence[Mapping[str, object]], *, is_trading_day: bool) -> Path`.
- Produces: `summary() -> Mapping[str, object]` with separate ETF, stock, and combined metrics.
- Release state is `collecting` until at least 60 distinct trading days and 40 paper entries; then `eligible` only when net P&L > 0, profit factor >= 1.2, max drawdown <= 8%, and saved snapshots reconcile with fills.

- [ ] **Step 1: Write failing release-gate tests**

```python
def test_forward_gate_never_relaxes_the_sample_minimum(tmp_path):
    journal = ForwardJournal(tmp_path)
    for index in range(59):
        day = datetime(2026, 8, 4, tzinfo=SHANGHAI) + timedelta(days=index)
        run = replace(decision_run(run_id=f"day-{index}"), as_of=day)
        journal.record_day(run, [
            {"kind": "paper_exit", "instrument_type": "etf", "net_pnl": 2.0},
            {"kind": "paper_exit", "instrument_type": "stock", "net_pnl": 1.0},
        ], is_trading_day=True)
    assert journal.summary()["release_state"] == "collecting"
    last_day = datetime(2026, 10, 2, tzinfo=SHANGHAI)
    journal.record_day(
        replace(decision_run(run_id="day-59"), as_of=last_day),
        [],
        is_trading_day=True,
    )
    summary = journal.summary()
    assert summary["trading_days"] == 60
    assert summary["release_state"] == "eligible"
    assert set(summary["by_instrument_type"]) == {"etf", "stock"}
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_forward.py -v`

Expected: import fails because `forward.py` does not exist.

- [ ] **Step 3: Implement append-only day records and metrics**

Reuse `summarize_ledger`; calculate cumulative net equity and peak-to-trough drawdown from ordered `paper_exit` events. Record blocked/no-trade days as real observations, but count a day toward the 60-day gate only when `is_trading_day=True`; the CLI derives that flag from `ArchiveReader.read_trade_dates`. If fewer than 40 paper entries exist after 60 days, keep `collecting`; never lower thresholds. Record the formal start date as the first trading day with a production-ready final snapshot and a functioning ledger, not the code deployment date.

- [ ] **Step 4: Wire final/exit_check journal updates and reports**

On `final`, record decision/snapshot quality for the day. On `exit_check`, append realized ledger results and regenerate `<output-root>/reports/tail_decision/forward/latest.json` and `latest.md`. Update operations docs with exact inspection commands and the implementation report with the actual formal start date or `not_started:<reason>`.

- [ ] **Step 5: Verify metrics and full tail suite**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_forward.py skills/deep-analysis/scripts/tests/tail_decision/test_simulator.py -v
python -m pytest skills/deep-analysis/scripts/tests/tail_decision -q
```

Expected: all tests pass; ETF, stock, and combined summaries are distinct; blocked days remain visible; release remains closed before both sample gates.

- [ ] **Step 6: Commit only Task 6**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/forward.py skills/deep-analysis/scripts/run_tail_decision.py skills/deep-analysis/scripts/tests/tail_decision/test_forward.py docs/data/tail-decision-operations.md docs/data/tail-decision-implementation-report.md
git commit -m "feat: track tail forward validation"
```

---

### Task 7: Scheduler Activation, Live No-Token Smoke, and Final Audit

**Files:**
- Create: `scripts/check_tail_decision_tasks.ps1`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/test_production_no_token_e2e.py`
- Modify: `scripts/install_tail_decision_tasks.ps1`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_scheduler_script.py`
- Modify: `docs/data/tail-decision-operations.md`
- Modify: `docs/data/tail-decision-implementation-report.md`

**Interfaces:**
- `check_tail_decision_tasks.ps1` exits 0 only when all seven exact task names exist, actions target the current Python/CLI, triggers match, and the latest scheduler log has no unreported failure.
- Production smoke may contact free providers but must run with `TUSHARE_TOKEN` removed; network failure is an accepted `blocked` observation only if artifacts and snapshot diagnostics are persisted.
- Scheduler installation is an explicit final mutation after `-WhatIf`, tests, and path checks pass.

- [ ] **Step 1: Write failing scheduler-health and production-smoke tests**

```python
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
    monkeypatch.setattr(
        run_tail_decision,
        "_OfflineGateway",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fixture used")),
    )
    exit_code = run_tail_decision.main([
        "--phase", "final",
        "--as-of", "2026-08-04T14:30:00+08:00",
        "--data-root", str(tmp_path / "archive"),
        "--output-root", str(tmp_path),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code in {0, 2}
    assert payload["status"] in {"recommended", "watch_only", "no_trade", "blocked"}
    assert payload["total_exposure"] <= 8_000.0
    artifact_text = "\n".join(
        path.read_text(encoding="utf-8") for path in tmp_path.rglob("*.json")
    )
    assert "offline_fixture" not in artifact_text

    import ast
    for path in Path("skills/deep-analysis/scripts/lib/tail_decision").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        ]
        assert not any(name.casefold().startswith("tushare") for name in imported)
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_scheduler_script.py skills/deep-analysis/scripts/tests/tail_decision/test_production_no_token_e2e.py -v`

Expected: scheduler health script is missing and production gateway assertions are not yet satisfied.

- [ ] **Step 3: Implement scheduler health inspection**

Use `Get-ScheduledTask -TaskName <exact-name>` and `Get-ScheduledTaskInfo`; emit compact JSON with task name, state, next run, last result, executable, and arguments. Do not expose environment variables. Installation remains idempotent with `-Force`, `MultipleInstances IgnoreNew`, hidden execution, and logs under the project report root.

- [ ] **Step 4: Run final non-mutating verification**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/tail_decision -q
python -m pytest skills/deep-analysis/scripts/tests/test_trading_calendar_safety.py skills/deep-analysis/scripts/tests/test_providers_chain.py -q
$env:TUSHARE_TOKEN = $null
python skills/deep-analysis/scripts/run_tail_decision.py --phase warmup --output-root .cache/tail-production-smoke
python skills/deep-analysis/scripts/run_tail_decision.py --phase preview --output-root .cache/tail-production-smoke
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_tail_decision_tasks.ps1 -WhatIf
```

Expected: tests pass; production smoke records free-source diagnostics without credentials; exposure never exceeds 8,000; `-WhatIf` lists exactly seven tasks and performs no registration.

- [ ] **Step 5: Register and verify the seven Windows tasks**

Run only after Step 4 succeeds:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_tail_decision_tasks.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_tail_decision_tasks.ps1
```

Expected: seven exact tasks are installed for weekdays; health JSON reports all present and no action references Codex, Tushare, `.env`, or a broker.

- [ ] **Step 6: Start the formal forward journal and perform the final audit**

Run one production `warmup`/`preview` sequence during market hours. The first day counts only if snapshots contain a 14:10-or-later point, the archive context is complete, and ledger writes succeed. Update the report with actual results; if the market is closed, record `not_started:outside_market_hours` and let the registered scheduler start it on the next trading day.

Audit commands:

```powershell
rg -n -i "import tushare|pro_api|broker|submit_order|TUSHARE_TOKEN" skills/deep-analysis/scripts/lib/tail_decision skills/deep-analysis/scripts/run_tail_decision.py scripts/install_tail_decision_tasks.ps1
git diff --check -- skills/deep-analysis/scripts/lib/tail_decision skills/deep-analysis/scripts/tests/tail_decision skills/deep-analysis/scripts/run_tail_decision.py scripts/install_tail_decision_tasks.ps1 scripts/check_tail_decision_tasks.ps1 docs/data/tail-decision-operations.md docs/data/tail-decision-implementation-report.md
```

Expected: no paid/broker import is present; the only `TUSHARE_TOKEN` mention is in tests/docs asserting absence; scoped diff check passes. Do not repair unrelated dirty files if a repository-wide diff check reports their pre-existing whitespace.

- [ ] **Step 7: Commit final operations evidence**

```powershell
git add scripts/install_tail_decision_tasks.ps1 scripts/check_tail_decision_tasks.ps1 skills/deep-analysis/scripts/tests/tail_decision/test_scheduler_script.py skills/deep-analysis/scripts/tests/tail_decision/test_production_no_token_e2e.py docs/data/tail-decision-operations.md docs/data/tail-decision-implementation-report.md
git commit -m "ops: activate self-sustaining tail decisions"
```

---

## Completion Audit

- [ ] `ArchiveReader` reads 20 recent stock/fund daily partitions and exact static masters without online calls.
- [ ] Production universe is archive-derived or an explicit validated override, never the old hard-coded pair.
- [ ] Each scheduled phase appends normalized free-source snapshots; final features contain a real 14:10-or-later observation.
- [ ] Production `InstrumentContext` contains normalized CNY liquidity, listing/ST/suspension/limit metadata, and conservative announcement status.
- [ ] Dual-source deviation above 0.3% is `blocked`; one source is `watch_only`; both produce zero allocation.
- [ ] A valid final run can allocate ETF plus stock without exceeding CNY 8,000 or CNY 4,000 per instrument.
- [ ] `close`, `exit_open`, and `exit_check` append paper lifecycle events and never claim a real broker fill.
- [ ] Forward reports separate ETF, stock, and combined metrics and cannot release before 60 trading days plus 40 paper entries.
- [ ] Seven local Windows tasks are installed and pass the health check; the system no longer depends on the Codex automation for daily operation.
- [ ] Full tail tests and focused legacy regressions pass without a Tushare token.
- [ ] Reports, snapshots, ledger, and logs contain no token, `.env` value, authorization header, or password.
- [ ] Existing Tushare archive files and unrelated dirty worktree changes remain untouched.

## Self-Review Result

- Spec coverage: the audit gaps map to Tasks 1–7; local archive, dual free sources, ETF/stock strategies, account cap, statuses, append-only records, next-session exits, scheduler independence, and forward gates all have an implementation and verification step.
- Placeholder scan: no placeholder marker, cross-task shorthand, unspecified error handling, or unnamed test step remains.
- Type consistency: `Universe`, `QuoteSnapshotStore`, `CredentialFreeGateway`, `PhaseLedger`, and `ForwardJournal` signatures are defined once and consumed with the same names in later tasks.
- Scope decision: archive/universe, snapshots/gateway, lifecycle ledger, and forward operations are separate reviewer-sized deliverables; no task requires modifying the dirty legacy pipeline.

## Automated Execution Choice

The user already authorized gradual implementation through this automation. Continue with **Inline Execution via `superpowers:executing-plans`**, one task or one tightly related TDD batch per heartbeat. Do not create a user-owned subthread. Report milestones and genuine blockers; keep no-change heartbeats quiet.
