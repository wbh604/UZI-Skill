# Tail v2 Broad Universe and Single Position Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand Tail v2 from a roughly 20-stock, CNY 4,000-per-name search into an auditable full-A-share funnel with at least 300 researched stocks, reuse existing AI discovery and UZI review evidence, and select at most one stock or ETF under available cash and a CNY 12,000 configured cap.

**Architecture:** Keep `tail_decision` as the production authority. Add read-only research-evidence adapters and a deterministic candidate funnel before the existing credential-free gateway; only the narrowed observation pool receives free realtime quotes and announcement checks. Keep Tail v2 hard gates and cross-asset allocator intact, but replace legacy exposure fields with an effective position cap derived from configured cap and locally supplied available cash.

**Tech Stack:** Python 3.11+, frozen dataclasses, pandas, pytest, local JSON/JSONL archives, Eastmoney and Tencent credential-free quote providers, Windows Task Scheduler scripts.

## Global Constraints

- Final output is exactly one best stock or ETF, or an explicit `watch_only`, `no_trade`, or `blocked` result.
- `configured_position_cap_cny` defaults to CNY 12,000; actual exposure must not exceed `available_cash_cny`.
- No leverage, broker connection, account scraping, automatic order, Tushare Token, or paid realtime dependency.
- The local Tushare archive remains read-only evidence; do not delete or rewrite it.
- The normal research stock pool target is at least 300 qualified names; low-quality names must not be added merely to reach 300.
- Only about 30 stocks and 10 ETFs receive realtime observation, and no more than five candidates reach the final cross-asset comparison.
- AI recommendations and UZI scores are research evidence only; they never bypass same-day dual-source quotes, Tail v2 hard gates, event risk, or cash checks.
- Existing user changes outside the listed files must not be staged, reverted, reformatted, or committed.
- Every implementation task follows RED → minimal GREEN → focused regression → scoped commit.

---

### Task 1: Account Cash and CNY 12,000 Position Contract

**Files:**
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/config.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_config.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py`

**Interfaces:**
- Produces: `DecisionConfig.configured_position_cap_cny: float = 12_000.0`.
- Produces: `DecisionConfig.available_cash_cny: float | None = 12_000.0`.
- Produces: `DecisionConfig.effective_position_cap_cny -> float | None`.
- Preserves: read-only compatibility properties `max_total_exposure` and `max_instrument_exposure`, both returning the effective cap when cash is known.
- Produces: `research_stock_limit=300`, `realtime_stock_limit=30`, `realtime_etf_limit=10`, `max_stock_candidates=3`, and `max_etf_candidates=2`.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_default_config_uses_cash_aware_12000_single_position_cap():
    config = DecisionConfig()
    assert config.configured_position_cap_cny == 12_000.0
    assert config.available_cash_cny == 12_000.0
    assert config.effective_position_cap_cny == 12_000.0
    assert config.research_stock_limit == 300
    assert config.realtime_stock_limit == 30
    assert config.max_stock_candidates + config.max_etf_candidates == 5


def test_available_cash_is_the_effective_cap_when_lower():
    config = DecisionConfig(
        configured_position_cap_cny=12_000.0,
        available_cash_cny=7_600.0,
    )
    assert config.effective_position_cap_cny == 7_600.0


def test_missing_available_cash_has_no_effective_cap():
    assert DecisionConfig(available_cash_cny=None).effective_position_cap_cny is None
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_config.py -q`

Expected: tests fail because the new cash-aware fields and property do not exist.

- [ ] **Step 3: Implement the minimal validated configuration**

```python
@dataclass(frozen=True)
class DecisionConfig:
    account_assets: float = 12_000.0
    configured_position_cap_cny: float = 12_000.0
    available_cash_cny: float | None = 12_000.0
    research_stock_limit: int = 300
    realtime_stock_limit: int = 30
    realtime_etf_limit: int = 10
    max_etf_candidates: int = 2
    max_stock_candidates: int = 3

    @property
    def effective_position_cap_cny(self) -> float | None:
        if self.available_cash_cny is None:
            return None
        return min(self.configured_position_cap_cny, self.available_cash_cny)

    @property
    def max_total_exposure(self) -> float | None:
        return self.effective_position_cap_cny

    @property
    def max_instrument_exposure(self) -> float | None:
        return self.effective_position_cap_cny
```

Validation must reject non-positive configured caps and non-positive supplied cash, but accept `available_cash_cny=None`. Include all new fields in `config_hash` through `asdict`.

- [ ] **Step 4: Update the no-token default assertion and run GREEN**

```python
def test_no_token_end_to_end_records_bounded_portfolio(tmp_path):
    assert DecisionConfig().effective_position_cap_cny == 12_000.0
```

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_config.py skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/config.py skills/deep-analysis/scripts/tests/tail_decision/test_config.py skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py
git commit -m "feat: add cash-aware tail position cap"
```

---

### Task 2: Read-Only AI Discovery and UZI Evidence Adapters

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/research_evidence.py`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/test_research_evidence.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/__init__.py`

**Interfaces:**
- Produces frozen `ResearchEvidence(instrument_id, ai_score, uzi_score, uzi_coverage, uzi_state, source_dates, source_paths, reasons)`.
- Produces `load_ai_discovery(root: Path, as_of: date, max_age_days: int = 10) -> dict[str, ResearchEvidence]`.
- Produces `load_uzi_evidence(cache_root: Path, instrument_ids: Iterable[str], as_of: datetime, max_age_days: int = 10) -> dict[str, ResearchEvidence]`.
- Produces `merge_research_evidence(*groups) -> dict[str, ResearchEvidence]`.
- Normalizes `sz.300759`, `300759.SZ`, `sh600489`, and `600489.SH` into the canonical `000000.SH|SZ` contract.

Define these test helpers in `test_research_evidence.py` before the tests that use them:

```python
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
```

- [ ] **Step 1: Write failing AI discovery tests**

```python
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
```

- [ ] **Step 2: Write failing freshness and corruption tests**

```python
def test_stale_ai_file_is_ignored_with_no_exception(tmp_path):
    write_weekly_file(tmp_path, as_of="2026-07-01", code="sz.300170")
    assert load_ai_discovery(tmp_path, date(2026, 8, 5), max_age_days=10) == {}


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
```

- [ ] **Step 3: Run the adapter tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_research_evidence.py -q`

Expected: import fails because `research_evidence.py` does not exist.

- [ ] **Step 4: Implement strict, non-actionable adapters**

Implement canonical-code parsing, date selection that never reads a future artifact, finite 0–100 score validation, file-age validation, and immutable tuples for paths/reasons. AI `candidates` and `review_queue` are both discovery hints. UZI explicit `state == "blocked"` survives merging; missing evidence becomes `uzi_state="unavailable"` and never blocks the entire run.

```python
@dataclass(frozen=True)
class ResearchEvidence:
    instrument_id: str
    ai_score: float | None = None
    uzi_score: float | None = None
    uzi_coverage: float | None = None
    uzi_state: str = "unavailable"
    source_dates: tuple[str, ...] = ()
    source_paths: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
```

- [ ] **Step 5: Run tests GREEN and export the contract**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_research_evidence.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit Task 2**

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/research_evidence.py skills/deep-analysis/scripts/lib/tail_decision/__init__.py skills/deep-analysis/scripts/tests/tail_decision/test_research_evidence.py
git commit -m "feat: load AI and UZI tail research evidence"
```

---

### Task 3: Full-A-Share Research Universe and Deterministic Observation Funnel

**Files:**
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/universe.py`
- Create: `skills/deep-analysis/scripts/lib/tail_decision/funnel.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/__init__.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_universe.py`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/test_funnel.py`

**Interfaces:**
- Extends `build_liquid_universe(..., max_stocks=300, max_etfs=30, max_stock_lot_notional_cny=12_000.0, stock_lot_size=100, min_history_sessions=20)`.
- Produces frozen `FunnelAudit(base_stocks, research_stocks, observation_stocks, research_etfs, observation_etfs, reasons)`.
- Produces frozen `CandidateFunnel(research: Universe, observation: Universe, evidence: Mapping[str, ResearchEvidence], audit: FunnelAudit)`.
- Produces `build_candidate_funnel(universe, stock_daily, fund_daily, evidence, *, max_stocks=30, max_etfs=10) -> CandidateFunnel`.

Define deterministic dataframe helpers in the two test files. `liquid_stock_fixture(count, sessions)` must generate `count * sessions` rows with columns `ts_code`, `trade_date`, `close`, and `amount`, plus matching `stock_basic` rows with `name` and `list_date`. `one_stock_fixture` is the one-code specialization. `empty_fund_daily()` and `empty_etf_basic()` must return empty frames with the production-required columns. `stock_codes(count)` returns zero-padded valid Shanghai IDs beginning at `600000.SH`; `daily_for_codes(ids)` generates 20 sessions for each ID. These helpers must use fixed dates and no network calls.

```python
def empty_fund_daily() -> pd.DataFrame:
    return pd.DataFrame(columns=["ts_code", "trade_date", "close", "amount"])


def empty_etf_basic() -> pd.DataFrame:
    return pd.DataFrame(columns=["ts_code", "list_status"])


def stock_codes(count: int) -> tuple[str, ...]:
    return tuple(f"{600000 + index:06d}.SH" for index in range(count))
```

- [ ] **Step 1: Write failing broad-universe tests**

```python
def test_normal_archive_builds_at_least_300_research_stocks():
    daily, basic = liquid_stock_fixture(count=360, sessions=20)
    universe = build_liquid_universe(
        daily,
        empty_fund_daily(),
        basic,
        empty_etf_basic(),
        max_stocks=300,
        min_history_sessions=20,
        max_stock_lot_notional_cny=12_000.0,
    )
    assert len(universe.stocks) == 300


def test_stock_above_40_is_kept_when_one_lot_fits_12000():
    daily, basic = one_stock_fixture(code="688318.SH", close=79.50, sessions=20)
    universe = build_liquid_universe(
        daily,
        empty_fund_daily(),
        basic,
        empty_etf_basic(),
        max_stock_lot_notional_cny=12_000.0,
    )
    assert universe.stocks == ("688318.SH",)


def test_stock_is_excluded_when_one_lot_exceeds_cap():
    daily, basic = one_stock_fixture(code="600519.SH", close=1_600.0, sessions=20)
    universe = build_liquid_universe(
        daily,
        empty_fund_daily(),
        basic,
        empty_etf_basic(),
        max_stock_lot_notional_cny=12_000.0,
    )
    assert universe.stocks == ()
```

- [ ] **Step 2: Run universe tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_universe.py -q`

Expected: new arguments are rejected and the old default still limits stocks to 20.

- [ ] **Step 3: Implement affordability and history completeness before ranking**

Use each instrument's latest non-null close and at least `min_history_sessions` distinct sessions. Apply ST/delisting/listing-age rules before ranking. Preserve deterministic turnover-descending, code-ascending order. Never lower the configured minimum turnover merely to reach 300.

- [ ] **Step 4: Write failing funnel tests**

```python
def test_ai_hint_can_enter_research_pool_but_only_top_30_get_realtime_observation():
    universe = Universe(etfs=(), stocks=tuple(stock_codes(320)))
    evidence = {
        "600319.SH": ResearchEvidence("600319.SH", ai_score=95.0)
    }
    funnel = build_candidate_funnel(
        universe,
        daily_for_codes(universe.stocks),
        empty_fund_daily(),
        evidence,
        max_stocks=30,
        max_etfs=10,
    )
    assert len(funnel.research.stocks) == 320
    assert len(funnel.observation.stocks) == 30
    assert "600319.SH" in funnel.observation.stocks


def test_uzi_blocked_name_is_not_in_observation_pool():
    evidence = {
        "600001.SH": ResearchEvidence("600001.SH", uzi_score=90, uzi_state="blocked")
    }
    funnel = build_candidate_funnel(
        Universe(etfs=(), stocks=("600001.SH", "600002.SH")),
        daily_for_codes(("600001.SH", "600002.SH")),
        empty_fund_daily(),
        evidence,
        max_stocks=2,
        max_etfs=1,
    )
    assert "600001.SH" not in funnel.observation.stocks
    assert "uzi_blocked:600001.SH" in funnel.audit.reasons
```

- [ ] **Step 5: Run funnel tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_funnel.py -q`

Expected: import fails because `funnel.py` does not exist.

- [ ] **Step 6: Implement deterministic local narrowing**

Rank research stocks using only information known before `as_of`: 20-day data completeness, average turnover, 5-day return, volatility penalty, AI discovery score, and available UZI score. UZI explicit block is a hard observation-pool exclusion. AI/UZI numerical evidence only affects observation order; it never creates a `Candidate` or `Allocation`.

```python
local_score = (
    0.45 * liquidity_percentile
    + 0.25 * completeness_ratio
    + 0.20 * bounded_return_percentile
    - 0.10 * volatility_percentile
)
research_score = local_score + ai_priority_bonus + uzi_review_bonus
```

Bound each optional bonus to 0.05 so absent AI/UZI evidence cannot dominate local data. Sort by score descending and instrument ID ascending.

- [ ] **Step 7: Run universe and funnel tests GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_universe.py skills/deep-analysis/scripts/tests/tail_decision/test_funnel.py -q`

Expected: all tests pass.

- [ ] **Step 8: Commit Task 3**

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/universe.py skills/deep-analysis/scripts/lib/tail_decision/funnel.py skills/deep-analysis/scripts/lib/tail_decision/__init__.py skills/deep-analysis/scripts/tests/tail_decision/test_universe.py skills/deep-analysis/scripts/tests/tail_decision/test_funnel.py
git commit -m "feat: build broad tail research funnel"
```

---

### Task 4: Gateway Integration, Evidence Audit, and Per-Instrument Failure Isolation

**Files:**
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/gateway.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_gateway.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/free_quotes.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_free_quotes.py`

**Interfaces:**
- Extends `CredentialFreeGateway.__init__` with `research_root: Path | None` and `uzi_cache_root: Path | None`.
- Gateway builds the 300-name research universe, loads AI/UZI evidence, narrows to the observation universe, and fetches realtime quotes only for observation IDs.
- Adds `raw_quotes["funnel_audit"]` and `raw_quotes["research_evidence"]` without credentials or full UZI report bodies.
- Stock context metadata includes a compact `research_evidence` mapping with scores, state, dates, and reason codes.

Extend the existing `_Archive` and `_QuoteProvider` fixtures rather than creating an alternate gateway implementation. `broad_archive(stock_count=320)` returns an `_Archive` whose daily/basic frames contain 20 sessions per stock. `RecordingQuoteProvider` subclasses `_QuoteProvider`, stores the last tuple passed to `fetch_quotes` as `requested_ids`, and delegates quote construction to the parent. `MatchingQuoteProvider` is `_QuoteProvider("tencent", 0.001)`. `production_gateway` is a thin test factory that instantiates the real `CredentialFreeGateway` with these fixtures, optional research roots, and no universe override.

- [ ] **Step 1: Write failing gateway funnel tests**

```python
def test_gateway_quotes_only_observation_pool_and_audits_research_count(tmp_path):
    archive = broad_archive(stock_count=320)
    provider = RecordingQuoteProvider()
    gateway = production_gateway(
        tmp_path,
        archive=archive,
        providers=(provider, MatchingQuoteProvider()),
    )
    inputs = gateway.collect(as_of=_at(14, 10), phase="preview")
    assert inputs.raw_quotes["funnel_audit"]["research_stocks"] >= 300
    assert inputs.raw_quotes["funnel_audit"]["observation_stocks"] == 30
    assert len(provider.requested_ids) <= 40


def test_gateway_attaches_fresh_uzi_evidence_without_replacing_live_quote(tmp_path):
    write_uzi_cache(tmp_path / "uzi" / "600001.SH", overall_score=71.0)
    inputs = production_gateway(tmp_path, uzi_cache_root=tmp_path / "uzi").collect(
        as_of=_at(14, 30), phase="final"
    )
    stock = next(item for item in inputs.stock_contexts if item.instrument_id == "600001.SH")
    assert stock.metadata["research_evidence"]["uzi_score"] == 71.0
    assert stock.quote.timestamp == _at(14, 30)
```

- [ ] **Step 2: Add exact mixed-batch failure regression**

```python
def test_one_malformed_symbol_does_not_discard_other_batch_quotes():
    provider = TencentQuoteProvider(http_get=fake_batch_with_one_malformed_record)
    quotes = provider.fetch_quotes(["600001.SH", "600002.SH"], NOW)
    assert quotes["600001.SH"].last_price == 10.20
    assert "600002.SH" not in quotes
```

- [ ] **Step 3: Run gateway and provider tests and verify RED where new behavior is missing**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_gateway.py skills/deep-analysis/scripts/tests/tail_decision/test_free_quotes.py -q`

Expected: gateway tests fail because it quotes the whole universe and exposes no funnel/evidence audit. The malformed-symbol regression may already pass from the earlier resilience fix; record that as an existing GREEN safety invariant instead of weakening it.

- [ ] **Step 4: Integrate the funnel without changing quote-quality authority**

Use `config.effective_position_cap_cny or config.configured_position_cap_cny` only for research affordability. Use the observation IDs for `fetch_from_providers`, quality decisions, contexts, snapshots, and announcement checks. Missing AI/UZI roots return empty evidence. Do not catch and hide `UniverseDataError`; convert it into a stable `system_errors` reason.

- [ ] **Step 5: Run focused tests GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_gateway.py skills/deep-analysis/scripts/tests/tail_decision/test_free_quotes.py -q`

Expected: all tests pass, including single-symbol failure isolation.

- [ ] **Step 6: Commit Task 4**

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/gateway.py skills/deep-analysis/scripts/lib/tail_decision/free_quotes.py skills/deep-analysis/scripts/tests/tail_decision/test_gateway.py skills/deep-analysis/scripts/tests/tail_decision/test_free_quotes.py
git commit -m "feat: connect research funnel to free quote gateway"
```

---

### Task 5: UZI Review in Stock Hard Gates and Five-Candidate Final Pool

**Files:**
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/stock_strategy.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_stock_strategy.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/etf_strategy.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_etf_strategy.py`

**Interfaces:**
- UZI `blocked` is a stable stock rejection reason `uzi_review_blocked`.
- UZI score, coverage, AI score, and evidence dates appear in candidate reasons when available.
- Missing UZI evidence adds `uzi_unavailable` but does not reject an otherwise qualified stock.
- Rankers return at most three stocks and two ETFs; the combined final pool therefore contains at most five names.

Define strategy-test helpers with immutable replacement so production contracts stay frozen:

```python
def with_research_evidence(context, **evidence):
    metadata = dict(context.metadata)
    metadata["research_evidence"] = evidence
    return replace(context, metadata=metadata)


def valid_stocks(count: int):
    return [
        stock_context(f"{600000 + index:06d}.SH", price=10 + index, name=f"S{index}")
        for index in range(count)
    ]
```

`valid_etfs(count)` follows the existing `etf_context` fixture and emits valid unique `51xxxx.SH` IDs with sufficient amount, Tail return, VWAP distance, and `quality="pass"`.

- [ ] **Step 1: Write failing UZI hard-gate and audit tests**

```python
def test_explicit_uzi_block_cannot_be_recovered_by_high_tail_momentum():
    context = stock_context("300170.SZ", price=18.0, name="汉得信息")
    context = with_research_evidence(
        context,
        uzi_state="blocked",
        uzi_score=90.0,
        uzi_coverage=0.70,
    )
    candidates, rejected = rank_overnight_stocks((context,), DecisionConfig())
    assert candidates == []
    assert "uzi_review_blocked" in rejected["300170.SZ"]


def test_missing_uzi_is_audited_but_not_a_hard_reject():
    context = stock_context("300253.SZ", price=7.9, name="卫宁健康")
    candidates, rejected = rank_overnight_stocks((context,), DecisionConfig())
    assert [item.instrument_id for item in candidates] == ["300253.SZ"]
    assert "uzi_unavailable" in candidates[0].reasons
```

- [ ] **Step 2: Write failing combined-size tests**

```python
def test_default_ranker_limits_produce_at_most_five_finalists():
    config = DecisionConfig()
    stocks, _ = rank_overnight_stocks(tuple(valid_stocks(10)), config)
    etfs, _ = rank_etfs(tuple(valid_etfs(10)), config)
    assert len(stocks) == 3
    assert len(etfs) == 2
    assert len(stocks) + len(etfs) == 5
```

- [ ] **Step 3: Run strategy tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_stock_strategy.py skills/deep-analysis/scripts/tests/tail_decision/test_etf_strategy.py -q`

Expected: UZI evidence is currently ignored and old candidate limits remain two plus two.

- [ ] **Step 4: Add UZI gate and compact reasons without double-counting its score**

Do not add UZI score again to the final Tail score because it already influenced observation-pool order and is not calibrated to next-day net return. Treat explicit UZI block as a hard rejection; otherwise attach compact reasons such as `uzi_score:71.0`, `uzi_coverage:0.68`, `ai_discovery_score:82.0`, or `uzi_unavailable`.

- [ ] **Step 5: Run strategy tests GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_stock_strategy.py skills/deep-analysis/scripts/tests/tail_decision/test_etf_strategy.py -q`

Expected: all tests pass and the combined candidate limit is five.

- [ ] **Step 6: Commit Task 5**

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/stock_strategy.py skills/deep-analysis/scripts/lib/tail_decision/etf_strategy.py skills/deep-analysis/scripts/tests/tail_decision/test_stock_strategy.py skills/deep-analysis/scripts/tests/tail_decision/test_etf_strategy.py
git commit -m "feat: apply UZI review to tail finalists"
```

---

### Task 6: Cash-Aware Single Allocation, Missing-Cash Block, and CLI Migration

**Files:**
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/portfolio.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/workflow.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py`
- Modify: `skills/deep-analysis/scripts/run_tail_decision.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_cli.py`

**Interfaces:**
- `allocate_portfolio` uses `config.effective_position_cap_cny` and still returns at most one allocation.
- Final workflow with `available_cash_cny=None` returns `blocked`, no allocations, and reason `available_cash_missing`.
- CLI accepts `--position-cap` and `--available-cash`, both defaulting to 12,000; deprecated `--max-exposure` remains an alias for one release and cannot create a separate 4,000 cap.
- CLI JSON adds `configured_position_cap_cny`, `available_cash_cny`, and `effective_position_cap_cny`.

Define `run_offline_cli` in `test_cli.py` as a subprocess helper that always passes `--phase final`, an aware fixed `--as-of`, `--offline-fixture`, and an isolated `--output-root`, appends the supplied extra arguments, asserts return code zero, and returns `json.loads(completed.stdout)`.

- [ ] **Step 1: Replace legacy allocator assertions with failing cash-aware tests**

```python
def test_allocator_can_buy_stock_above_40_when_one_lot_fits():
    stock = candidate("688318.SH", kind="stock", price=79.50, lot_size=100, score=90)
    allocations, _ = allocate_portfolio([], [stock], DecisionConfig())
    assert allocations[0].quantity == 100
    assert allocations[0].notional == 7_950.0


def test_allocator_never_exceeds_lower_available_cash():
    etf = candidate("513050.SH", kind="etf", price=1.20, lot_size=100, score=90)
    config = DecisionConfig(available_cash_cny=7_600.0)
    allocations, _ = allocate_portfolio([etf], [], config)
    assert len(allocations) == 1
    assert allocations[0].notional <= 7_600.0
    assert allocations[0].notional > 7_000.0
```

- [ ] **Step 2: Write failing workflow missing-cash test**

```python
def test_final_blocks_when_available_cash_is_missing():
    dependencies = workflow_dependencies()
    dependencies["config"] = DecisionConfig(available_cash_cny=None)
    result = TailDecisionWorkflow(**dependencies).run(
        as_of="2026-08-05T14:30:00+08:00", phase="final"
    )
    assert result.status is DecisionStatus.BLOCKED
    assert result.allocations == ()
    assert "available_cash_missing" in result.reasons
```

- [ ] **Step 3: Run portfolio/workflow tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py -q`

Expected: old 4,000 instrument cap rejects the 79.50 stock and workflow does not block missing cash.

- [ ] **Step 4: Implement one effective budget and stable missing-cash authority**

```python
effective_cap = config.effective_position_cap_cny
if effective_cap is None:
    return [], ["available_cash_missing"]
budget = Decimal(str(effective_cap))
```

Keep the existing candidate sort, legal-lot flooring, invalid-candidate skip, unaffordable fallback, and first-feasible `break`. In workflow, block missing cash before final allocation but allow warmup/preview research to continue.

- [ ] **Step 5: Write failing CLI migration tests**

```python
def test_cli_defaults_to_user_approved_12000_cash_cap():
    args = cli._parser().parse_args(["--phase", "preview"])
    assert args.position_cap == 12_000.0
    assert args.available_cash == 12_000.0


def test_cli_payload_exposes_effective_cap(tmp_path):
    payload = run_offline_cli(
        tmp_path,
        "--position-cap", "12000",
        "--available-cash", "7600",
    )
    assert payload["effective_position_cap_cny"] == 7_600.0
    assert payload["total_exposure"] <= 7_600.0
```

- [ ] **Step 6: Run CLI tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_cli.py -q`

Expected: new CLI flags and payload fields do not exist.

- [ ] **Step 7: Migrate CLI construction and run all Task 6 tests GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py skills/deep-analysis/scripts/tests/tail_decision/test_cli.py -q`

Expected: all tests pass; every final run has zero or one allocation.

- [ ] **Step 8: Commit Task 6**

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/portfolio.py skills/deep-analysis/scripts/lib/tail_decision/workflow.py skills/deep-analysis/scripts/run_tail_decision.py skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py skills/deep-analysis/scripts/tests/tail_decision/test_cli.py
git commit -m "feat: allocate one cash-aware tail position"
```

---

### Task 7: Audit Report, No-Token End-to-End Regression, and Windows Operations

**Files:**
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/recorder.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_recorder.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_production_no_token_e2e.py`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py`
- Modify: `scripts/install_tail_decision_tasks.ps1`
- Modify: `scripts/check_tail_decision_tasks.ps1`
- Modify: `skills/deep-analysis/scripts/tests/tail_decision/test_scheduler_script.py`
- Modify: `docs/data/tail-decision-operations.md`
- Create: `docs/data/tail-v2-broad-universe-verification.md`

**Interfaces:**
- JSON audit records funnel counts, ignored evidence reasons, source dates, cash fields, effective cap, and exactly one final allocation at most.
- User Markdown renders only the selected operation or explicit non-actionable state; the 300/30/5 pools remain audit summaries, not multiple order instructions.
- Windows tasks continue to run without Tushare or broker credentials and pass the 12,000 defaults explicitly for operational clarity.

Add `recommended_run_with_one_allocation()` to `test_recorder.py` by using the existing `decision_run` fixture as a field template and replacing `allocations` with exactly its first allocation. Do not reuse the fixture's historical two-allocation tuple as a valid Tail v2 result.

- [ ] **Step 1: Write failing recorder tests**

```python
def test_recorder_audits_funnel_without_rendering_research_names_as_orders(tmp_path):
    recorder = DecisionRecorder(tmp_path)
    path = recorder.record(
        recommended_run_with_one_allocation(),
        {
            "funnel_audit": {
                "research_stocks": 300,
                "observation_stocks": 30,
                "finalists": 5,
            },
            "research_evidence": {"300170.SZ": {"ai_score": 82.0}},
        },
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["raw_quotes"]["funnel_audit"]["research_stocks"] == 300
    markdown = path.with_suffix(".md").read_text(encoding="utf-8")
    assert markdown.count("Buy plan") <= 1
```

- [ ] **Step 2: Update production no-token expectations and add funnel assertions**

```python
def test_production_no_token_smoke_uses_broad_funnel_and_cash_cap(...):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    exit_code = run_tail_decision.main([
        "--phase", "final",
        "--as-of", "2026-08-05T14:30:00+08:00",
        "--position-cap", "12000",
        "--available-cash", "12000",
        "--data-root", str(archive_root),
        "--output-root", str(tmp_path),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert len(payload["allocations"]) <= 1
    assert payload["total_exposure"] <= 12_000.0
    assert "TUSHARE_TOKEN" not in json.dumps(payload)
```

- [ ] **Step 3: Run recorder and E2E tests and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_recorder.py skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py skills/deep-analysis/scripts/tests/tail_decision/test_production_no_token_e2e.py -q`

Expected: old tests still assert 8,000 and recorder has no explicit funnel/cash audit presentation.

- [ ] **Step 4: Implement compact audit rendering and scheduler arguments**

Add an audit summary with counts and reason codes. Do not render all research names in Markdown. Update each Windows task action to include `--position-cap 12000 --available-cash 12000`; the check script must assert the exact arguments. Keep hidden-window execution and existing phase times unchanged.

- [ ] **Step 5: Run scheduler tests GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_scheduler_script.py -q`

Expected: all tests pass and no task invokes a broker or Tushare credential.

- [ ] **Step 6: Run the complete Tail v2 regression suite**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision -q`

Expected: all tests pass with no stale 4,000/8,000 assertions, no mixed-source batch regression, and no credential requirement.

- [ ] **Step 7: Run a real no-token preview and final fixture verification**

```powershell
Remove-Item Env:\TUSHARE_TOKEN -ErrorAction SilentlyContinue
python skills/deep-analysis/scripts/run_tail_decision.py --phase preview --as-of 2026-08-05T14:10:00+08:00 --offline-fixture --position-cap 12000 --available-cash 12000 --output-root ..\data\tail_v2_broad_verification
python skills/deep-analysis/scripts/run_tail_decision.py --phase final --as-of 2026-08-05T14:30:00+08:00 --offline-fixture --position-cap 12000 --available-cash 12000 --output-root ..\data\tail_v2_broad_verification
```

Expected: preview has no allocation; final has zero or one allocation; total exposure is at most 12,000; JSON and Markdown are written; no artifact contains token, `.env`, or credential values.

- [ ] **Step 8: Write the verification report**

Record exact test commands and pass counts, commit IDs, sample run IDs, funnel counts, effective cap, evidence-source dates, no-token proof, archive preservation, and confirmation that no broker/automatic order path exists in `docs/data/tail-v2-broad-universe-verification.md`. Update operations documentation with AI/UZI evidence freshness and the new CLI flags.

- [ ] **Step 9: Commit Task 7**

```powershell
git add -- skills/deep-analysis/scripts/lib/tail_decision/recorder.py skills/deep-analysis/scripts/tests/tail_decision/test_recorder.py skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py skills/deep-analysis/scripts/tests/tail_decision/test_production_no_token_e2e.py scripts/install_tail_decision_tasks.ps1 scripts/check_tail_decision_tasks.ps1 skills/deep-analysis/scripts/tests/tail_decision/test_scheduler_script.py docs/data/tail-decision-operations.md docs/data/tail-v2-broad-universe-verification.md
git commit -m "feat: verify broad no-token tail decisions"
```

---

## Final Verification Checklist

- [ ] `git status --short` is inspected before every task; overlapping unknown edits are reported instead of overwritten.
- [ ] `python -m pytest skills/deep-analysis/scripts/tests/tail_decision -q` passes and the exact count is recorded.
- [ ] A normal local fixture demonstrates at least 300 researched stocks and no more than 30 realtime-observed stocks.
- [ ] AI `candidates` and `review_queue` can improve discovery priority but cannot create an allocation.
- [ ] Fresh UZI evidence is auditable; explicit UZI block rejects; missing/stale/corrupt evidence degrades safely.
- [ ] A stock priced above CNY 40 remains eligible when one lot fits the effective cap.
- [ ] Missing available cash yields `blocked: available_cash_missing`; supplied lower cash always wins over 12,000.
- [ ] Preview never produces an allocation; final produces at most one stock or ETF.
- [ ] Current-day dual-source price, Tail v2 hard gates, event risk, and integer-lot checks remain mandatory.
- [ ] No Tushare Token, paid permission, broker connection, leverage, auto-order, 179-item catalog harvest, or full-market historical minute collection is introduced.
- [ ] Existing Tushare archive files remain present and unmodified.

## Self-Review Record

- Spec coverage: account cap, available cash, broad research pool, 30-name observation pool, five finalists, AI discovery, UZI review, free-source isolation, single final selection, audit, Windows operation, and no-token verification each map to an explicit task.
- Type consistency: `ResearchEvidence`, `CandidateFunnel`, `FunnelAudit`, and `effective_position_cap_cny` are defined before use by later tasks; all paths and function names are stable across tasks.
- Scope: the plan reuses existing artifacts and pipeline boundaries; it does not add LLM calls, rerun full UZI analysis for 300 stocks, or broaden into order execution.
- Placeholder scan: the plan contains no TBD/TODO/later placeholders; each task includes exact RED/GREEN commands, expected outcomes, file lists, interfaces, and scoped commits.
