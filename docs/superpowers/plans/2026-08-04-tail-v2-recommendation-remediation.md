# Tail v2 Recommendation Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the credential-free tail-decision system to `tail-v2`, prevent any non-authoritative run from becoming a buy instruction, reject stale/overextended/reversing/relatively weak candidates, rank only on auditable net-return evidence, and apply one conservative next-session five-minute failure exit policy to ETF and stock paper positions.

**Architecture:** Keep `workflow.py` as the only decision-state authority and split three concepts that `tail-v1` conflated: a scored `Candidate`, a non-actionable `PaperIntent` used only to accumulate forward evidence, and an actionable `Allocation` released only after the version-isolated forward gate passes. Final-window freshness and strategy hard gates run before evidence calibration; `portfolio.py` selects at most one cross-asset result; `recorder.py`, `phase_ledger.py`, and the CLI consume a shared actionability predicate and cannot infer a trade independently. A pure exit policy evaluates next-session opening context, the first complete five-minute bar, VWAP, hard stops, profit targets, and time exits without fabricating fills.

**Tech Stack:** Python 3.11+, pandas, pytest, standard-library dataclasses/enums/json/hashlib/pathlib/datetime, existing Eastmoney/Tencent quote adapters, existing append-only JSON/Markdown recorders.

## Global Constraints

- Core execution must remain valid without `TUSHARE_TOKEN`, `.env`, a weekly card, or paid Tushare permissions.
- Do not import Tushare from `lib/tail_decision`; the local archive remains read-only and free live quotes remain the production path.
- Do not connect a broker, submit orders, restore 179-item full-catalog collection, or collect full-market historical minute bars.
- Preserve every `tail-v1` decision, snapshot, paper ledger event, and forward record. New release summaries must filter by exact strategy version rather than rewriting old files.
- A user-actionable result requires one `tail-v2` final allocation plus a passing shared actionability predicate. `PaperIntent` is internal calibration state and must never render quantity, buy limit, or imperative buy wording in the human report.
- `blocked`, `no_trade`, `watch_only`, preview runs, stale runs, replay-inconsistent runs, and forward-gate-ineligible runs must remain non-actionable.
- All final prices must come from a same-day 14:10-14:30 dual-source `PASS` decision boundary. Preview objects and prior-day prices cannot be reused.
- Thresholds are conservative, versioned fields in `DecisionConfig`; changing them changes `config_hash` and requires a new strategy-version forward count.
- ETF and stock candidates share one account allocator, one CNY 8,000 total-exposure cap, and one-result maximum.
- Preserve the dirty worktree. Stage and commit only files named by the current task; do not modify `run.py`, Tushare exporters, or unrelated pipeline files.
- Every behavior change is test-first: observe the stated RED failure, add the minimum implementation, rerun focused tests, then commit that task.

---

## File Map

```text
skills/deep-analysis/scripts/lib/tail_decision/
  contracts.py       CandidateEvidence, PaperIntent, strict DecisionRun invariants
  config.py          tail-v2 thresholds, evidence gates, exit parameters, config hash inputs
  actionability.py   one shared publication/actionability decision
  features.py        same-day final-window, reversal, close-location, and benchmark features
  snapshot_store.py  phase-separated snapshots; no preview-to-final reuse
  gateway.py         fresh final context composition and same-boundary quote/date checks
  stock_strategy.py  stock hard gates before scoring
  etf_strategy.py    ETF hard gates before scoring
  evidence.py        versioned analog/forward net-return evidence construction
  portfolio.py       cross-asset PaperIntent versus Allocation selection
  workflow.py        only authority for status, intent, and allocation state
  recorder.py        DO_NOT_TRADE/PAPER_ONLY/ACTIONABLE rendering
  exit_policy.py     pure next-session five-minute failure state machine
  simulator.py       cost-aware fills driven by ExitDecision
  phase_ledger.py    authoritative final plan and next-session lifecycle
  forward.py         tail-v1/tail-v2 isolation and release/evidence summaries
skills/deep-analysis/scripts/run_tail_decision.py
skills/deep-analysis/scripts/tests/tail_decision/
  fixtures.py
  test_contracts.py
  test_config.py
  test_actionability.py
  test_features.py
  test_snapshot_store.py
  test_gateway.py
  test_stock_strategy.py
  test_etf_strategy.py
  test_evidence.py
  test_portfolio.py
  test_workflow.py
  test_recorder.py
  test_exit_policy.py
  test_simulator.py
  test_phase_ledger.py
  test_forward.py
  test_cli.py
  test_no_token_e2e.py
  test_production_no_token_e2e.py
  test_tail_v2_postmortem_regression.py
docs/data/tail-decision-operations.md
docs/data/tail-v2-remediation-verification.md
```

The new tests and modules do not touch the active Tushare harvesting process or its state files.

---

### Task 1: Tail-v2 Contracts, Paper Calibration Boundary, and Versioned Configuration

**Files:**
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/contracts.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/config.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/fixtures.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_contracts.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_config.py`

**Interfaces:**
- Add `EvidenceLevel` with `unvalidated`, `shadow_calibrated`, and `forward_validated`.
- Add frozen `CandidateEvidence` carrying cost-adjusted return, benchmark-relative return, sample count, sample boundaries, and evidence level.
- Replace candidate order-like state with `canonical_price`, `decision_quote_timestamp`, and `evidence`; only an `Allocation` or internal `PaperIntent` may carry quantity and entry limit.
- Add frozen `PaperIntent` for append-only simulation. It is not an allocation and is never actionable.
- Extend `DecisionRun` with `phase`, `decision_trade_date`, and `paper_intents`, and enforce status/intents/allocations consistency in `__post_init__`.
- Change the default strategy version to `tail-v2` and add all strategy/evidence/exit thresholds as hashed config fields.

- [ ] **Step 1: Write failing contract tests for evidence and state invariants**

```python
def test_watch_only_can_hold_one_internal_paper_intent_but_no_allocation():
    run = decision_run(
        status=DecisionStatus.WATCH_ONLY,
        candidates=(candidate(evidence_level=EvidenceLevel.UNVALIDATED),),
        paper_intents=(paper_intent(),),
        allocations=(),
    )
    assert len(run.paper_intents) == 1
    assert run.allocations == ()


@pytest.mark.parametrize("status", [DecisionStatus.NO_TRADE, DecisionStatus.BLOCKED])
def test_terminal_non_trade_status_rejects_intents_and_allocations(status):
    with pytest.raises(ValueError, match="cannot contain paper intents or allocations"):
        decision_run(status=status, paper_intents=(paper_intent(),))


def test_recommended_requires_exactly_one_tail_v2_final_allocation():
    with pytest.raises(ValueError, match="recommended requires one final allocation"):
        decision_run(
            status=DecisionStatus.RECOMMENDED,
            strategy_version="tail-v2",
            phase="preview",
            allocations=(allocation(),),
        )


def test_candidate_has_canonical_quote_but_no_order_quantity_or_buy_limit():
    item = candidate()
    assert item.canonical_price == Decimal("10.00")
    assert item.decision_quote_timestamp.tzinfo is not None
    assert not hasattr(item, "quantity")
    assert not hasattr(item, "max_buy_price")
```

- [ ] **Step 2: Run contract tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_contracts.py -q`

Expected: collection fails because `EvidenceLevel`, `CandidateEvidence`, `PaperIntent`, `phase`, and `paper_intents` do not exist and the old `Candidate` still exposes `max_buy_price`.

- [ ] **Step 3: Add the exact contract types and invariants**

```python
class EvidenceLevel(str, Enum):
    UNVALIDATED = "unvalidated"
    SHADOW_CALIBRATED = "shadow_calibrated"
    FORWARD_VALIDATED = "forward_validated"


@dataclass(frozen=True)
class CandidateEvidence:
    expected_net_return_pct: float | None
    benchmark_relative_return_pct: float | None
    analog_sample_count: int
    sample_start_date: str | None
    sample_end_date: str | None
    level: EvidenceLevel

    def __post_init__(self) -> None:
        if self.analog_sample_count < 0:
            raise ValueError("analog_sample_count cannot be negative")
        if self.analog_sample_count == 0 and (
            self.sample_start_date is not None or self.sample_end_date is not None
        ):
            raise ValueError("empty evidence cannot have sample boundaries")


@dataclass(frozen=True)
class PaperIntent:
    instrument_id: str
    instrument_type: InstrumentType
    quantity: int
    max_entry_price: Decimal
    planned_notional: Decimal
    strategy_version: str


@dataclass(frozen=True)
class Candidate:
    instrument_id: str
    name: str
    instrument_type: InstrumentType
    score: float
    canonical_price: Decimal
    decision_quote_timestamp: datetime
    evidence: CandidateEvidence
    reasons: tuple[str, ...]
    rejections: tuple[str, ...]
    exit_plan: Mapping[str, float | str]
    theme: str | None = None
```

In `DecisionRun.__post_init__`, require `phase == "final"`, `strategy_version == "tail-v2"`, exactly one allocation, and no paper intents for `recommended`. Require zero allocations for `watch_only`; permit at most one paper intent. Require zero allocations and paper intents for `no_trade` and `blocked`. Preserve tuple normalization and recursive immutability.

- [ ] **Step 4: Write failing config-version tests**

```python
def test_default_config_is_tail_v2_and_hashes_all_new_gates():
    base = DecisionConfig()
    assert base.strategy_version == "tail-v2"
    changed = replace(base, max_close_extension_pct=base.max_close_extension_pct + 0.1)
    assert base.config_hash != changed.config_hash


def test_tail_v2_defaults_keep_shadow_and_forward_thresholds_separate():
    config = DecisionConfig()
    assert config.min_shadow_samples < config.min_forward_entries
    assert config.min_expected_net_return_pct > 0
    assert config.first_five_minute_recovery_seconds > 0
```

- [ ] **Step 5: Run config tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_config.py -q`

Expected: assertions fail because the default remains `tail-v1` and the named fields are absent.

- [ ] **Step 6: Add conservative versioned fields to `DecisionConfig`**

Add these fields with decimal-percentage semantics matching existing feature values:

```python
strategy_version: str = "tail-v2"
final_window_start: time = time(14, 10)
final_window_end: time = time(14, 30)
max_final_quote_age_seconds: int = 90
max_close_extension_pct: float = 3.0
max_intraday_drawdown_from_high_pct: float = 2.0
min_close_location: float = 0.65
min_stock_relative_strength_pct: float = 0.30
max_etf_underlying_dislocation_pct: float = 0.50
min_shadow_samples: int = 20
min_forward_entries: int = 40
min_forward_trading_days: int = 60
min_expected_net_return_pct: float = 0.20
first_five_minute_recovery_seconds: int = 120
positive_gap_failure_floor_pct: float = 0.20
```

Include every field in the existing deterministic `config_hash`. Keep existing CNY exposure, fee, dual-source, hard-stop, profit-target, and time-exit fields unchanged unless a focused test proves an incompatible name.

- [ ] **Step 7: Update shared fixtures and run the focused suite GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_contracts.py skills/deep-analysis/scripts/tests/tail_decision/test_config.py -q`

Expected: all tests pass, and fixture factories default to timezone-aware same-day final timestamps and explicit evidence.

- [ ] **Step 8: Commit Task 1**

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/contracts.py skills/deep-analysis/scripts/lib/tail_decision/config.py skills/deep-analysis/scripts/tests/tail_decision/fixtures.py skills/deep-analysis/scripts/tests/tail_decision/test_contracts.py skills/deep-analysis/scripts/tests/tail_decision/test_config.py
git commit -m "feat: define tail-v2 decision contracts"
```

---

### Task 2: Shared Actionability Predicate and Non-Misleading Reports

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/actionability.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/recorder.py`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/test_actionability.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_recorder.py`

**Interfaces:**
- Add `PublicationMode`: `DO_NOT_TRADE`, `PAPER_ONLY`, `ACTIONABLE`.
- Add `classify_publication(run, *, forward_release_eligible, replay_verified) -> PublicationDecision`.
- `ACTIONABLE` requires a `tail-v2` final `recommended` run, one allocation, no paper intent, dual-source `PASS` quality for the selected instrument, candidate/allocation identity agreement, a same-day decision timestamp, a passing release gate, and replay verification.
- `DecisionRecorder.persist_audit(run, raw_quotes) -> PersistedRun` writes canonical JSON before publication.
- `DecisionRecorder.verify_replay(persisted_run) -> bool` reads the run back and verifies its canonical hash.
- `DecisionRecorder.render_report(persisted_run, publication) -> RecordedArtifact` verifies the publication binding and never recomputes or upgrades the mode.

- [ ] **Step 1: Write failing publication-mode tests**

```python
@pytest.mark.parametrize(
    "status",
    [DecisionStatus.BLOCKED, DecisionStatus.NO_TRADE, DecisionStatus.WATCH_ONLY],
)
def test_non_trade_states_are_always_do_not_trade(status):
    run = decision_run(status=status, allocations=(), paper_intents=())
    result = classify_publication(run, forward_release_eligible=True, replay_verified=True)
    assert result.mode is PublicationMode.DO_NOT_TRADE


def test_shadow_intent_is_paper_only_and_never_actionable():
    run = decision_run(
        status=DecisionStatus.WATCH_ONLY,
        paper_intents=(paper_intent(),),
        allocations=(),
    )
    result = classify_publication(run, forward_release_eligible=False, replay_verified=True)
    assert result.mode is PublicationMode.PAPER_ONLY


def test_recommended_run_requires_release_and_replay_to_be_actionable():
    run = decision_run(status=DecisionStatus.RECOMMENDED, allocations=(allocation(),))
    assert classify_publication(
        run, forward_release_eligible=False, replay_verified=True
    ).mode is PublicationMode.PAPER_ONLY
    assert classify_publication(
        run, forward_release_eligible=True, replay_verified=False
    ).mode is PublicationMode.DO_NOT_TRADE
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_actionability.py -q`

Expected: import fails because `actionability.py` does not exist.

- [ ] **Step 3: Implement the pure classifier**

```python
class PublicationMode(str, Enum):
    DO_NOT_TRADE = "do_not_trade"
    PAPER_ONLY = "paper_only"
    ACTIONABLE = "actionable"


@dataclass(frozen=True)
class PublicationDecision:
    mode: PublicationMode
    reasons: tuple[str, ...]
    run_id: str
    run_hash: str


def classify_publication(
    run: DecisionRun,
    *,
    forward_release_eligible: bool,
    replay_verified: bool,
) -> PublicationDecision:
    reasons: list[str] = []
    if run.status in {DecisionStatus.BLOCKED, DecisionStatus.NO_TRADE}:
        return publication_decision(run, PublicationMode.DO_NOT_TRADE, (run.status.value,))
    if run.status is DecisionStatus.WATCH_ONLY:
        mode = PublicationMode.PAPER_ONLY if run.paper_intents else PublicationMode.DO_NOT_TRADE
        return publication_decision(run, mode, ("not_released",))
    if not replay_verified:
        reasons.append("replay_not_verified")
    if not forward_release_eligible:
        reasons.append("forward_release_gate_not_met")
    if reasons:
        mode = PublicationMode.DO_NOT_TRADE if "replay_not_verified" in reasons else PublicationMode.PAPER_ONLY
        return publication_decision(run, mode, tuple(reasons))
    return publication_decision(run, PublicationMode.ACTIONABLE, ())
```

`publication_decision` computes a canonical hash from the immutable run and binds that hash and run ID into `PublicationDecision`. Before returning `ACTIONABLE`, validate the selected candidate, allocation, quality decision, strategy version, phase, trade date, and decision quote timestamp. Return stable reason codes for every failure.

- [ ] **Step 4: Write failing recorder tests that prohibit buy wording outside ACTIONABLE**

```python
def test_paper_only_markdown_hides_quantity_and_buy_limit(tmp_path):
    run = decision_run(
        status=DecisionStatus.WATCH_ONLY,
        paper_intents=(paper_intent(quantity=300, max_entry_price=Decimal("25.08")),),
    )
    writer = recorder(tmp_path)
    persisted = writer.persist_audit(run, raw_quotes={})
    publication = classify_publication(
        run,
        forward_release_eligible=False,
        replay_verified=writer.verify_replay(persisted),
    )
    artifact = writer.render_report(persisted, publication)
    text = artifact.markdown_path.read_text(encoding="utf-8")
    assert "PAPER_ONLY" in text
    assert "300" not in text
    assert "25.08" not in text
    assert "买入" not in text


def test_actionable_markdown_contains_exactly_one_allocation(tmp_path):
    run = decision_run(status=DecisionStatus.RECOMMENDED, allocations=(allocation(),))
    writer = recorder(tmp_path)
    persisted = writer.persist_audit(run, raw_quotes={})
    publication = classify_publication(
        run,
        forward_release_eligible=True,
        replay_verified=writer.verify_replay(persisted),
    )
    artifact = writer.render_report(persisted, publication)
    text = artifact.markdown_path.read_text(encoding="utf-8")
    assert text.count("ACTIONABLE") == 1
    assert text.count("max_buy_price") == 1
```

- [ ] **Step 5: Run recorder tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_recorder.py -q`

Expected: calls fail because `record` does not accept a publication decision and paper details are currently rendered.

- [ ] **Step 6: Make JSON audit-rich and Markdown authority-safe**

Persist the full `PaperIntent` only in JSON under `audit.paper_intents`. Render one of three fixed banners at the top of Markdown. For `DO_NOT_TRADE` and `PAPER_ONLY`, omit quantity, max entry price, max buy price, and imperative trading verbs. For `ACTIONABLE`, render only the single official allocation and the run ID. Verify that the publication run ID and canonical run hash match the supplied run; a mismatch produces a blocked audit artifact and no order fields. The recorder never upgrades publication mode.

- [ ] **Step 7: Run focused tests GREEN and commit**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_actionability.py skills/deep-analysis/scripts/tests/tail_decision/test_recorder.py -q`

Expected: all tests pass.

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/actionability.py skills/deep-analysis/scripts/lib/tail_decision/recorder.py skills/deep-analysis/scripts/tests/tail_decision/test_actionability.py skills/deep-analysis/scripts/tests/tail_decision/test_recorder.py
git commit -m "feat: enforce tail publication authority"
```

---

### Task 3: Same-Day Final-Window Freshness and Preview Isolation

**Files:**
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/features.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/snapshot_store.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/gateway.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_features.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_snapshot_store.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_gateway.py`

**Interfaces:**
- `build_intraday_features` returns `trade_date`, `window_start`, `window_end`, `window_complete`, `first_price`, `session_high`, `session_low`, `close_location`, `drawdown_from_high_pct`, and existing tail/VWAP metrics.
- `SnapshotStore.read_phase_window(instrument_id, trade_date, phase, start, end)` returns only records captured for that phase and date.
- `ProductionGateway.build_contexts(*, phase: str, as_of: datetime)` performs new live reads and rejects contexts whose canonical quote, source quotes, intraday bars, daily boundary, or risk boundary disagree on trade date.

- [ ] **Step 1: Add failing final-window feature tests**

```python
def test_final_window_requires_same_day_start_and_end_boundaries():
    bars = intraday_bars(
        timestamps=("2026-08-04 14:10:00+08:00", "2026-08-04 14:29:00+08:00")
    )
    features = build_intraday_features(bars, as_of=shanghai_dt(2026, 8, 4, 14, 30))
    assert features["window_complete"] is False


def test_intraday_features_expose_reversal_inputs():
    bars = intraday_bars(prices=(10.0, 10.8, 10.7, 10.1))
    features = build_intraday_features(bars, as_of=shanghai_dt(2026, 8, 4, 14, 30))
    assert features["session_high"] == pytest.approx(10.8)
    assert features["drawdown_from_high_pct"] > 6.0
    assert 0.0 <= features["close_location"] <= 1.0
```

- [ ] **Step 2: Run feature tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_features.py -q`

Expected: keys are missing and the current production-ready check incorrectly accepts an incomplete final window.

- [ ] **Step 3: Implement deterministic window and reversal features**

Filter bars to `as_of.date()` before all calculations. Define completeness as at least one bar at or before `final_window_start`, one bar whose completed interval reaches `final_window_end`, monotonic timestamps, and no bar after `as_of`. Define:

```python
price_range = session_high - session_low
close_location = 0.5 if price_range == 0 else (last_price - session_low) / price_range
drawdown_from_high_pct = 0.0 if session_high == 0 else (session_high - last_price) / session_high * 100.0
```

Do not forward-fill missing final-window endpoints.

- [ ] **Step 4: Add failing snapshot/gateway isolation tests**

```python
def test_final_phase_does_not_read_preview_snapshots(tmp_path):
    store = SnapshotStore(tmp_path)
    store.append(snapshot(captured_at=shanghai_dt(2026, 8, 4, 14, 5)), phase="preview")
    result = store.read_phase_window(
        "600406.SH", date(2026, 8, 4), "final", time(14, 10), time(14, 30)
    )
    assert result.empty


def test_gateway_rejects_prior_day_canonical_quote(final_gateway):
    final_gateway.quote_adapter.fetch.return_value = dual_quote_pair(
        timestamp=shanghai_dt(2026, 8, 3, 14, 30)
    )
    contexts = final_gateway.build_contexts(phase="final", as_of=shanghai_dt(2026, 8, 4, 14, 30))
    assert contexts[0].quality.level is QualityLevel.BLOCKED
    assert "quote_trade_date_mismatch" in contexts[0].quality.reasons
```

- [ ] **Step 5: Run snapshot/gateway tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_snapshot_store.py skills/deep-analysis/scripts/tests/tail_decision/test_gateway.py -q`

Expected: phase-window API is absent and final context construction reuses undifferentiated stored snapshots or accepts stale dates.

- [ ] **Step 6: Implement phase-separated reads and final forced refresh**

Store `phase` with every normalized snapshot. The final gateway must call both free quote adapters during the final invocation, persist those reads as `phase="final"`, run existing dual-source quality checks, and use only final-phase rows to build intraday features. Add stable blocked reasons for quote-date mismatch, source-date mismatch, incomplete window, stale canonical quote, daily-boundary mismatch, and risk-boundary mismatch.

- [ ] **Step 7: Run focused tests GREEN and commit**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_features.py skills/deep-analysis/scripts/tests/tail_decision/test_snapshot_store.py skills/deep-analysis/scripts/tests/tail_decision/test_gateway.py -q`

Expected: all tests pass.

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/features.py skills/deep-analysis/scripts/lib/tail_decision/snapshot_store.py skills/deep-analysis/scripts/lib/tail_decision/gateway.py skills/deep-analysis/scripts/tests/tail_decision/test_features.py skills/deep-analysis/scripts/tests/tail_decision/test_snapshot_store.py skills/deep-analysis/scripts/tests/tail_decision/test_gateway.py
git commit -m "feat: enforce fresh final decision windows"
```

---

### Task 4: Pre-Score Overextension, Reversal, Relative-Strength, and ETF Dislocation Gates

**Files:**
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/stock_strategy.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/etf_strategy.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_stock_strategy.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_etf_strategy.py`

**Interfaces:**
- Stock hard rejection codes: `overextended_close`, `intraday_reversal`, `relative_strength_below_gate`.
- ETF hard rejection codes: `overextended_close`, `intraday_reversal`, `underlying_dislocation`.
- Hard gates run before score construction. A rejected context returns no candidate regardless of momentum score.

- [ ] **Step 1: Write failing stock hard-gate tests**

```python
@pytest.mark.parametrize(
    ("features", "reason"),
    [
        ({"daily_gain_pct": 4.2, "close_location": 0.92}, "overextended_close"),
        ({"drawdown_from_high_pct": 2.6, "close_location": 0.42}, "intraday_reversal"),
        ({"relative_strength_pct": 0.05}, "relative_strength_below_gate"),
    ],
)
def test_stock_hard_gates_reject_before_scoring(features, reason):
    context = stock_context_with_features(features)
    result = rank_stock(context, DecisionConfig())
    assert result.candidate is None
    assert reason in result.rejections
```

- [ ] **Step 2: Run stock tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_stock_strategy.py -q`

Expected: high-scoring overextended/reversing/relatively weak contexts still produce candidates.

- [ ] **Step 3: Add stock hard gates before the score block**

`overextended_close` requires both `daily_gain_pct > max_close_extension_pct` and `close_location >= min_close_location`. `intraday_reversal` requires both `drawdown_from_high_pct > max_intraday_drawdown_from_high_pct` and `close_location < min_close_location`. Relative strength must exceed both the broad benchmark and sector benchmark values supplied by the gateway; missing benchmark evidence produces `relative_strength_below_gate`, not a neutral score.

- [ ] **Step 4: Write failing ETF hard-gate tests**

```python
def test_etf_rejects_closed_underlying_dislocation():
    context = etf_context_with_features(
        underlying_market_open=False,
        underlying_proxy_move_pct=0.1,
        etf_move_pct=1.2,
    )
    result = rank_etf(context, DecisionConfig())
    assert result.candidate is None
    assert "underlying_dislocation" in result.rejections


def test_etf_overextension_is_not_only_a_score_penalty():
    context = etf_context_with_features(daily_gain_pct=5.5, close_location=0.95)
    result = rank_etf(context, DecisionConfig())
    assert result.candidate is None
    assert "overextended_close" in result.rejections
```

- [ ] **Step 5: Run ETF tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_etf_strategy.py -q`

Expected: the current strategy only subtracts points for excessive gain and does not reject underlying dislocation.

- [ ] **Step 6: Add ETF hard gates and construct order-free candidates**

Use the same overextension and reversal formulas as stocks. Compute `underlying_dislocation_pct = abs(etf_move_pct - underlying_proxy_move_pct)` and reject when the underlying market is closed and the value exceeds `max_etf_underlying_dislocation_pct`. Candidate construction stores the canonical quote and an explicit unvalidated evidence object, not quantity or max-buy price.

- [ ] **Step 7: Run strategy tests GREEN and commit**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_stock_strategy.py skills/deep-analysis/scripts/tests/tail_decision/test_etf_strategy.py -q`

Expected: all tests pass and every hard-gate reason is stable.

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/stock_strategy.py skills/deep-analysis/scripts/lib/tail_decision/etf_strategy.py skills/deep-analysis/scripts/tests/tail_decision/test_stock_strategy.py skills/deep-analysis/scripts/tests/tail_decision/test_etf_strategy.py
git commit -m "feat: add tail-v2 momentum failure gates"
```

---

### Task 5: Cost-Adjusted Evidence, Version-Isolated Calibration, and One Cross-Asset Selection

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/evidence.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/portfolio.py`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/test_evidence.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py`

**Interfaces:**
- `EvidenceBuilder.build(candidate, analog_rows, forward_summary, config) -> CandidateEvidence`.
- Analog rows must match exact strategy version and asset type and end before the decision trade date.
- Expected return is net of the existing instrument-specific round-trip cost model.
- `PortfolioAllocator.select(candidates, contexts, forward_release, config) -> SelectionOutcome` returns either one `Allocation`, one internal `PaperIntent`, or neither.
- Raw strategy scores only break ties inside the same evidence level; primary ordering is expected net return, benchmark-relative return, then deterministic instrument ID.

- [ ] **Step 1: Write failing evidence tests**

```python
def test_evidence_excludes_tail_v1_and_future_rows():
    rows = pd.DataFrame(
        [
            {"strategy_version": "tail-v1", "trade_date": "20260801", "net_return_pct": 9.0},
            {"strategy_version": "tail-v2", "trade_date": "20260802", "net_return_pct": 0.8},
            {"strategy_version": "tail-v2", "trade_date": "20260805", "net_return_pct": 8.0},
        ]
    )
    evidence = EvidenceBuilder().build(
        candidate(decision_quote_timestamp=shanghai_dt(2026, 8, 4, 14, 30)),
        rows,
        forward_summary(entries=1),
        DecisionConfig(),
    )
    assert evidence.analog_sample_count == 1
    assert evidence.sample_end_date == "20260802"


def test_expected_return_is_net_of_asset_specific_costs():
    etf = build_evidence_for_returns(InstrumentType.ETF, gross_returns=[0.30] * 20)
    stock = build_evidence_for_returns(InstrumentType.STOCK, gross_returns=[0.30] * 20)
    assert etf.expected_net_return_pct > stock.expected_net_return_pct
```

- [ ] **Step 2: Run evidence tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_evidence.py -q`

Expected: import fails because `evidence.py` does not exist.

- [ ] **Step 3: Implement deterministic evidence construction**

Filter by `config.strategy_version`, `candidate.instrument_type`, completed exit status, and `trade_date < candidate.decision_quote_timestamp.date()`. Subtract the cost-model percentage from gross returns before averaging. Use `UNVALIDATED` below `min_shadow_samples`, `SHADOW_CALIBRATED` at or above `min_shadow_samples`, and `FORWARD_VALIDATED` only when the exact-version forward summary is release-eligible. Preserve sample start/end and benchmark-relative mean. Empty or non-finite data returns an explicit unvalidated evidence object with no expected return.

- [ ] **Step 4: Write failing allocator tests for the calibration boundary**

```python
def test_unvalidated_best_score_creates_only_paper_intent():
    outcome = allocator().select(
        (candidate(score=99, evidence_level=EvidenceLevel.UNVALIDATED),),
        contexts_by_id(),
        forward_release=forward_release(eligible=False),
        config=DecisionConfig(),
    )
    assert outcome.allocation is None
    assert outcome.paper_intent is not None


def test_negative_net_edge_never_receives_real_allocation():
    outcome = allocator().select(
        (candidate(evidence_level=EvidenceLevel.FORWARD_VALIDATED, expected_net=-0.01),),
        contexts_by_id(),
        forward_release=forward_release(eligible=True),
        config=DecisionConfig(),
    )
    assert outcome.allocation is None


def test_positive_forward_validated_candidate_can_receive_one_allocation():
    outcome = allocator().select(
        (
            candidate("510300.SH", expected_net=0.35, evidence_level=EvidenceLevel.FORWARD_VALIDATED),
            candidate("600406.SH", expected_net=0.28, evidence_level=EvidenceLevel.FORWARD_VALIDATED),
        ),
        contexts_by_id(),
        forward_release=forward_release(eligible=True),
        config=DecisionConfig(),
    )
    assert outcome.allocation.instrument_id == "510300.SH"
    assert outcome.paper_intent is None
```

- [ ] **Step 5: Run portfolio tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py -q`

Expected: the existing allocator ranks raw score and allocates without evidence.

- [ ] **Step 6: Implement one-result selection and derive order fields only there**

Add frozen `SelectionOutcome` with `allocation`, `paper_intent`, and `reasons`. Reject non-positive or missing expected net return for real allocation. For unvalidated/shadow candidates, select at most one calibration candidate and derive a `PaperIntent` under the same lot-size, per-instrument, and account caps. Derive `max_buy_price` from the candidate canonical price and existing slippage configuration only inside the allocator. Keep total exposure at or below CNY 8,000 and deterministic tie-breaking.

- [ ] **Step 7: Run evidence/portfolio tests GREEN and commit**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_evidence.py skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py -q`

Expected: all tests pass.

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/evidence.py skills/deep-analysis/scripts/lib/tail_decision/portfolio.py skills/deep-analysis/scripts/tests/tail_decision/test_evidence.py skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py
git commit -m "feat: select tail candidates on net evidence"
```

---

### Task 6: Workflow State Authority and Immutable Final Decisions

**Files:**
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/workflow.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py`

**Interfaces:**
- `TailDecisionWorkflow.run` is the only constructor of production `DecisionRun` state.
- Preview never calls the allocator and always has zero allocations and zero paper intents.
- Final blocked quality returns `blocked`; all strategy rejects return `no_trade`; a selected paper intent returns `watch_only`; one released allocation returns `recommended`.
- The recorder receives a publication classification but cannot change run state.

- [ ] **Step 1: Write failing workflow state-table tests**

```python
@pytest.mark.parametrize(
    ("quality", "selection", "expected_status"),
    [
        ("blocked", "none", DecisionStatus.BLOCKED),
        ("pass", "none", DecisionStatus.NO_TRADE),
        ("pass", "paper", DecisionStatus.WATCH_ONLY),
        ("pass", "allocation", DecisionStatus.RECOMMENDED),
    ],
)
def test_final_state_is_derived_only_from_quality_and_selection(
    quality, selection, expected_status
):
    run = run_final_workflow(quality=quality, selection=selection)
    assert run.status is expected_status


def test_preview_never_reuses_candidates_as_final_orders():
    deps = workflow_dependencies(preview_candidates=(candidate(),), final_candidates=())
    preview = deps.workflow.run(phase="preview", as_of=preview_time())
    final = deps.workflow.run(phase="final", as_of=final_time())
    assert preview.allocations == ()
    assert preview.paper_intents == ()
    assert final.status is DecisionStatus.NO_TRADE
```

- [ ] **Step 2: Run workflow tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py -q`

Expected: the old workflow lacks paper-intent/evidence state and does not enforce the complete table.

- [ ] **Step 3: Refactor final orchestration in one direction**

For final runs: fetch fresh contexts, stop on blocked quality, run strategy hard gates, build evidence, call the allocator once, derive one status from `SelectionOutcome`, instantiate `DecisionRun`, persist the canonical audit JSON, verify replay, classify publication, and render the report. Do not read prior preview candidates. If `DecisionRun` construction raises an invariant error, write a blocked audit artifact with `state_invariant_violation` and no order fields.

- [ ] **Step 4: Add exact regression for formal no-trade authority**

```python
def test_no_trade_final_cannot_be_upgraded_by_recorder_or_ledger():
    deps = workflow_dependencies(final_candidates=())
    run = deps.workflow.run(phase="final", as_of=final_time())
    assert run.status is DecisionStatus.NO_TRADE
    assert deps.recorder.last_publication.mode is PublicationMode.DO_NOT_TRADE
    assert deps.ledger.events_for(run.run_id) == ()
```

- [ ] **Step 5: Run workflow tests GREEN and commit**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py -q`

Expected: all tests pass.

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/workflow.py skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py
git commit -m "feat: make workflow the sole tail authority"
```

---

### Task 7: Unified Five-Minute Failure Exit Policy and Auditable Paper Fills

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/exit_policy.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/simulator.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/phase_ledger.py`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/test_exit_policy.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_simulator.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_phase_ledger.py`

**Interfaces:**
- Add `ExitStatus`: `HOLD`, `EXIT`, `BLOCKED`.
- Add frozen `ExitContext` with entry price, open price, first-five-minute OHLC, current price, current VWAP, current timestamp, quote quality, tradability, instrument type, and strategy version.
- Add frozen `ExitDecision` with status, reason, trigger price, evidence timestamp, and observed thresholds.
- `evaluate_exit(context, config) -> ExitDecision` is pure and shared by ETF and stock.
- `exit_open` records gap/tradability only. `exit_check` is the first phase allowed to produce a five-minute failure fill.

- [ ] **Step 1: Write failing exit-policy tests**

```python
@pytest.mark.parametrize("instrument_type", [InstrumentType.ETF, InstrumentType.STOCK])
def test_positive_gap_then_break_of_first_five_low_exits_early(instrument_type):
    context = exit_context(
        instrument_type=instrument_type,
        entry_price=Decimal("10.00"),
        open_price=Decimal("10.12"),
        first_five_low=Decimal("10.08"),
        current_price=Decimal("10.05"),
        current_vwap=Decimal("10.09"),
        quote_quality=QualityLevel.PASS,
    )
    decision = evaluate_exit(context, DecisionConfig())
    assert decision.status is ExitStatus.EXIT
    assert decision.reason == "failed_follow_through_exit"


def test_missing_complete_five_minute_bar_blocks_instead_of_fabricating_fill():
    decision = evaluate_exit(exit_context(first_five_complete=False), DecisionConfig())
    assert decision.status is ExitStatus.BLOCKED
    assert decision.trigger_price is None


def test_dynamic_failure_exit_does_not_widen_hard_stop():
    context = exit_context(current_price=Decimal("9.70"), hard_stop_price=Decimal("9.80"))
    decision = evaluate_exit(context, DecisionConfig())
    assert decision.reason == "hard_stop_exit"
```

- [ ] **Step 2: Run exit-policy tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_exit_policy.py -q`

Expected: import fails because `exit_policy.py` does not exist.

- [ ] **Step 3: Implement deterministic exit precedence**

Apply this precedence: data/tradability block, hard stop, profit target, positive-gap first-five/VWAP failure after the configured recovery interval, time exit, hold. A failure exit requires both price below the first complete five-minute low and below VWAP after the recovery interval. Use the observed canonical quote as the paper trigger; do not use the bar low as a fill. Keep ETF and stock transaction costs in the simulator, not the policy.

- [ ] **Step 4: Add failing ledger lifecycle tests**

```python
def test_exit_open_never_creates_a_paper_exit_fill(tmp_path):
    ledger = PhaseLedger(tmp_path)
    ledger.record_entry(open_paper_position())
    events = ledger.advance_exit_open(open_quote(price="10.12"))
    assert [event.event_type for event in events] == ["exit_open_observation"]


def test_exit_check_persists_policy_evidence_and_costed_fill(tmp_path):
    ledger = seeded_ledger(tmp_path)
    events = ledger.advance_exit_check(failed_follow_through_context())
    exit_event = next(event for event in events if event.event_type == "paper_exit")
    assert exit_event.reason == "failed_follow_through_exit"
    assert exit_event.first_five_low is not None
    assert exit_event.vwap is not None
    assert exit_event.net_pnl != exit_event.gross_pnl
```

- [ ] **Step 5: Run simulator/ledger tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_simulator.py skills/deep-analysis/scripts/tests/tail_decision/test_phase_ledger.py -q`

Expected: the current ledger has no first-five/VWAP policy evidence and the simulator cannot consume `ExitDecision`.

- [ ] **Step 6: Integrate policy without changing T+1 or fee rules**

`PhaseLedger` records both `PaperIntent` and official `Allocation` final plans for simulation but marks their authority separately. At `exit_open`, append open/gap/tradability evidence and no fill. At `exit_check`, require a complete first-five bar and dual-source `PASS`, call `evaluate_exit`, then call the existing cost-aware round-trip simulator only for `EXIT`. Append blocked observations without a theoretical price.

- [ ] **Step 7: Run exit tests GREEN and commit**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_exit_policy.py skills/deep-analysis/scripts/tests/tail_decision/test_simulator.py skills/deep-analysis/scripts/tests/tail_decision/test_phase_ledger.py -q`

Expected: all tests pass.

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/exit_policy.py skills/deep-analysis/scripts/lib/tail_decision/simulator.py skills/deep-analysis/scripts/lib/tail_decision/phase_ledger.py skills/deep-analysis/scripts/tests/tail_decision/test_exit_policy.py skills/deep-analysis/scripts/tests/tail_decision/test_simulator.py skills/deep-analysis/scripts/tests/tail_decision/test_phase_ledger.py
git commit -m "feat: unify next-session tail exits"
```

---

### Task 8: Tail-v1/Tail-v2 Forward Isolation and Release Evidence

**Files:**
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/forward.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_forward.py`

**Interfaces:**
- `ForwardJournal.summary(strategy_version: str) -> ForwardSummary` requires an exact version.
- `ForwardSummary` exposes trading days, paper entries, closed exits, net P&L, profit factor, maximum drawdown, snapshot reconciliation, and release eligibility for that version only.
- `ForwardJournal.analog_rows(strategy_version, instrument_type, before_trade_date) -> pd.DataFrame` feeds `EvidenceBuilder` without future leakage.

- [ ] **Step 1: Write failing version-isolation tests**

```python
def test_tail_v1_records_cannot_release_tail_v2(tmp_path):
    journal = ForwardJournal(tmp_path)
    seed_release_eligible_history(journal, strategy_version="tail-v1")
    summary = journal.summary("tail-v2")
    assert summary.trading_days == 0
    assert summary.paper_entries == 0
    assert summary.release_eligible is False


def test_tail_v2_release_requires_closed_costed_samples_and_reconciled_snapshots(tmp_path):
    journal = ForwardJournal(tmp_path)
    seed_tail_v2_history(journal, trading_days=60, entries=40, closed_exits=39)
    summary = journal.summary("tail-v2")
    assert summary.release_eligible is False
    assert "closed_exit_count_below_gate" in summary.release_reasons
```

- [ ] **Step 2: Run forward tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_forward.py -q`

Expected: the current summary merges all versions or lacks an exact-version signature.

- [ ] **Step 3: Filter every count and metric before aggregation**

Reject an empty strategy version. Filter records first, then calculate all metrics. Release requires at least 60 trading days, 40 paper entries, 40 closed exits, positive net P&L, profit factor at least 1.2, maximum drawdown at most 8%, and reconciled snapshots. Keep the existing formal start-date semantics. `analog_rows` returns only completed, costed exits before the supplied decision date and includes benchmark-relative return.

- [ ] **Step 4: Add append-only compatibility test**

```python
def test_reading_legacy_tail_v1_records_does_not_rewrite_journal(tmp_path):
    path = write_legacy_journal(tmp_path)
    before = path.read_bytes()
    ForwardJournal(tmp_path).summary("tail-v2")
    assert path.read_bytes() == before
```

- [ ] **Step 5: Run forward tests GREEN and commit**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_forward.py -q`

Expected: all tests pass.

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/forward.py skills/deep-analysis/scripts/tests/tail_decision/test_forward.py
git commit -m "feat: isolate tail-v2 forward evidence"
```

---

### Task 9: CLI Integration, 2026-08-03 Regression, No-Token End-to-End Verification, and Operations Handoff

**Files:**
- Modify: `skills/deep-analysis/scripts/run_tail_decision.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_cli.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_production_no_token_e2e.py`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/test_tail_v2_postmortem_regression.py`
- Modify: `docs/data/tail-decision-operations.md`
- Create: `docs/data/tail-v2-remediation-verification.md`

**Interfaces:**
- CLI output includes `strategy_version`, `run_id`, `decision_trade_date`, `publication_mode`, `status`, and stable non-actionability reasons.
- Exit phases print observations or paper fills, never broker language.
- The 2026-08-03 regression fixture proves the formal no-trade result cannot be overridden and the observed overextension/reversal/weakness patterns cannot become an actionable allocation.

- [ ] **Step 1: Write the failing postmortem regression test**

```python
def test_august_3_failure_pattern_cannot_become_actionable(tmp_path):
    gateway = postmortem_gateway(
        etf={"instrument_id": "513050.SH", "daily_gain_pct": 3.1, "close_location": 0.94},
        stock={
            "instrument_id": "600406.SH",
            "drawdown_from_high_pct": 2.2,
            "close_location": 0.48,
            "relative_strength_pct": 0.05,
        },
    )
    result = run_cli_final(tmp_path, gateway=gateway, token_present=False)
    assert result.publication_mode in {"do_not_trade", "paper_only"}
    assert result.allocations == []
    assert "ACTIONABLE" not in result.markdown
```

- [ ] **Step 2: Run the regression and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_tail_v2_postmortem_regression.py -q`

Expected: the test fails because the CLI does not expose publication mode and the old strategy can allocate the high raw-score candidates.

- [ ] **Step 3: Wire exact-version release state and publication mode into the CLI**

At final phase, read `ForwardJournal.summary(config.strategy_version)` and execute the workflow. The workflow persists the run, reads it back by run ID, compares the canonical JSON hash, classifies publication, and renders the report in that order. Exit phases use the new exit context/policy path. CLI JSON prints no token, environment values, or credential paths.

- [ ] **Step 4: Add no-token E2E assertions**

```python
def test_tail_v2_no_token_e2e_is_safe_and_replayable(tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    result = run_production_fixture(tmp_path, strategy_version="tail-v2")
    assert result.exit_code == 0
    assert result.payload["strategy_version"] == "tail-v2"
    assert result.payload["publication_mode"] in {
        "do_not_trade", "paper_only", "actionable"
    }
    assert replay_hash(result.payload["run_id"]) == result.payload["run_hash"]
    assert result.payload["total_exposure"] <= 8000
```

- [ ] **Step 5: Run focused CLI and E2E tests**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_cli.py skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py skills/deep-analysis/scripts/tests/tail_decision/test_production_no_token_e2e.py skills/deep-analysis/scripts/tests/tail_decision/test_tail_v2_postmortem_regression.py -q`

Expected: all tests pass without a token.

- [ ] **Step 6: Run the complete tail-decision regression suite**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision -q`

Expected: all tests pass with no warnings that imply stale schema, mixed strategy versions, fabricated exit fills, or credential fallback.

- [ ] **Step 7: Run a local blocked/no-trade drill and inspect artifacts**

Run:

```powershell
$env:TAIL_DECISION_FIXTURE_MODE = 'blocked'
python skills/deep-analysis/scripts/run_tail_decision.py --phase final --output-root ..\data\tail_decision_v2_verification
Remove-Item Env:\TAIL_DECISION_FIXTURE_MODE
```

Expected: exit code 0; JSON and Markdown are written; `publication_mode` is `do_not_trade`; Markdown contains `DO_NOT_TRADE`; no quantity, buy limit, or buy imperative appears.

- [ ] **Step 8: Run a local paper-only drill and inspect ledger evidence**

Run:

```powershell
$env:TAIL_DECISION_FIXTURE_MODE = 'paper_only'
python skills/deep-analysis/scripts/run_tail_decision.py --phase final --output-root ..\data\tail_decision_v2_verification
Remove-Item Env:\TAIL_DECISION_FIXTURE_MODE
```

Expected: `status` is `watch_only`, `publication_mode` is `paper_only`, official allocations are empty, one internal paper intent exists only in the JSON audit and ledger, total planned paper exposure is at most CNY 8,000, and Markdown contains no order details.

- [ ] **Step 9: Update operations and write verification evidence**

Document the authority rule, publication modes, final-window requirements, tail-v1/tail-v2 isolation, paper-intent meaning, hard rejection codes, exit-state precedence, no-token operation, scheduler behavior, and exact commands used above. In `tail-v2-remediation-verification.md`, record test counts, command outputs, artifact paths, config hash, example run IDs, release-gate status, and proof that the blocked/no-trade drill cannot render an order.

- [ ] **Step 10: Commit Task 9**

```powershell
git add -- skills/deep-analysis/scripts/run_tail_decision.py skills/deep-analysis/scripts/tests/tail_decision/test_cli.py skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py skills/deep-analysis/scripts/tests/tail_decision/test_production_no_token_e2e.py skills/deep-analysis/scripts/tests/tail_decision/test_tail_v2_postmortem_regression.py docs/data/tail-decision-operations.md docs/data/tail-v2-remediation-verification.md
git commit -m "feat: complete tail-v2 recommendation remediation"
```

---

## Final Verification Checklist

- [ ] Run `git status --short` and confirm no unrelated file was staged or modified by this plan.
- [ ] Run `python -m pytest skills/deep-analysis/scripts/tests/tail_decision -q` and record the exact pass count.
- [ ] Run the no-token production E2E test with `TUSHARE_TOKEN` absent.
- [ ] Confirm `tail-v1` records remain byte-for-byte unchanged and cannot satisfy the `tail-v2` release gate.
- [ ] Confirm preview and prior-day quote fixtures cannot produce a final paper intent or allocation.
- [ ] Confirm overextended-close, intraday-reversal, relative-weakness, and ETF-dislocation fixtures have stable rejection reasons.
- [ ] Confirm an unvalidated or shadow-calibrated candidate has zero official allocation and no user-facing order details.
- [ ] Confirm only a replay-verified, release-eligible, same-day, dual-source `PASS`, final `tail-v2` run can be `ACTIONABLE`.
- [ ] Confirm first-five-minute/VWAP failure exits for ETF and stock occur before the wider hard stop when evidence is complete.
- [ ] Confirm missing five-minute evidence or non-`PASS` quotes produce blocked exit observations and no fabricated fill.
- [ ] Confirm official exposure never exceeds CNY 8,000 and at most one allocation exists.
- [ ] Confirm the active Tushare harvesting automation and archive were neither stopped nor modified.

## Self-Review Record

- The plan covers every accepted design requirement: authority, freshness, four hard gates, auditable net evidence, cross-asset comparability, one-result allocation, five-minute failure exits, version isolation, no-token operation, and regression proof.
- The `PaperIntent` boundary resolves the calibration/release dependency without weakening `watch_only`: paper evidence can accumulate while official allocations remain empty and reports remain non-actionable.
- All new state is append-only or derived. No migration rewrites `tail-v1` records.
- Every task names exact files, interfaces, RED commands, GREEN commands, and a scoped commit.
- New thresholds are config-hashed and are not fitted to the five observed symbols.
- The implementation does not broaden scope into broker execution, full-market minute history, paid-source dependency, or Tushare harvesting changes.
