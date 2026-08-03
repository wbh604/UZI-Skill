# Self-Sustaining Tail Decision System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first 14:10 tail-decision engine that produces ETF and overnight-stock candidates, enforces one shared CNY 8,000 exposure cap, records auditable outputs, and remains fully usable without a Tushare token or paid weekly card.

**Architecture:** Add a new isolated `lib/tail_decision` package rather than modifying the dirty legacy analysis pipeline. Provider adapters normalize free Eastmoney and Tencent quotes; a quality gate decides whether data can support recommendations; separate ETF and stock strategies produce candidates; one portfolio allocator produces the only account-level plan; an orchestrator, recorder, simulator, CLI, and Windows scheduler make the workflow repeatable without Codex or broker integration.

**Tech Stack:** Python 3.11+, standard-library dataclasses/typing/json/hashlib/pathlib/zoneinfo, existing `requests`, `pandas`, `pytest`, PowerShell Task Scheduler integration.

## Global Constraints

- Core execution must succeed with `TUSHARE_TOKEN`, `.env`, and paid Tushare permissions absent.
- Tushare may be an optional after-close enhancement only; no task below may import it in the core execution path.
- Historical features read existing files under `D:/work/gupiao/data/tushare_calendar`; no full-catalog or historical-minute download is allowed.
- Free realtime quotes require two independent sources for a `recommended` portfolio; one good source may produce `watch_only` but never an allocation.
- Realtime quote age must be at most 60 seconds and cross-source last-price deviation at most 0.3%.
- Account assets default to CNY 10,000; combined ETF plus stock exposure must not exceed CNY 8,000; initial per-instrument cap is CNY 4,000.
- The system must not connect to a broker or submit orders.
- Preserve raw, normalized, manifest, and all unrelated dirty worktree changes.
- All result records are append-only and include strategy version, configuration hash, input timestamps, candidates, rejection reasons, and final status.
- Every production behavior is implemented test-first: run the named test and confirm the expected failure before creating or editing production code.

---

## File Map

Create the following focused package and entry points:

```text
skills/deep-analysis/scripts/lib/tail_decision/
  __init__.py          public package exports only
  contracts.py         immutable normalized types and status enums
  config.py            validated account, quality, and strategy settings
  free_quotes.py       Eastmoney and Tencent free quote adapters
  archive.py           read-only access to existing local normalized datasets
  quality.py           freshness, source count, identity, and deviation gates
  features.py          deterministic historical and intraday features
  etf_strategy.py      ETF hard filters, scoring, and exit template
  stock_strategy.py    overnight-stock hard filters, scoring, and exit template
  portfolio.py         shared exposure allocation and correlation guard
  recorder.py          append-only JSON/JSONL snapshots and run artifacts
  simulator.py         next-session fills, costs, exits, and performance ledger
  workflow.py          phase orchestration and status resolution
skills/deep-analysis/scripts/run_tail_decision.py
scripts/install_tail_decision_tasks.ps1
skills/deep-analysis/scripts/tests/tail_decision/
  __init__.py
  fixtures.py
  test_contracts.py
  test_config.py
  test_free_quotes.py
  test_archive.py
  test_quality.py
  test_features.py
  test_etf_strategy.py
  test_stock_strategy.py
  test_portfolio.py
  test_recorder.py
  test_simulator.py
  test_workflow.py
  test_cli.py
  test_scheduler_script.py
  test_no_token_e2e.py
docs/data/tail-decision-operations.md
```

Do not modify `lib/data_sources.py`, `lib/pipeline/*`, `run.py`, or existing dirty tests unless a fresh failing integration test proves an unavoidable compatibility issue.

---

### Task 1: Normalized Contracts and Status Model

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/__init__.py`
- Create: `skills/deep-analysis/scripts/lib/tail_decision/contracts.py`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/__init__.py`
- Create: `skills/deep-analysis/scripts/tests/tail_decision/fixtures.py`
- Test: `skills/deep-analysis/scripts/tests/tail_decision/test_contracts.py`

**Interfaces:**
- Produces: `InstrumentType`, `DecisionStatus`, `QualityLevel`, `QuoteSnapshot`, `QualityDecision`, `InstrumentContext`, `Candidate`, `Allocation`, `DecisionRun`.
- All later tasks import these types; field names are frozen in this task.

- [ ] **Step 1: Write the failing contract test**

```python
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from lib.tail_decision.contracts import (
    DecisionStatus,
    InstrumentType,
    QuoteSnapshot,
)


def test_quote_snapshot_rejects_non_positive_price():
    with pytest.raises(ValueError, match="last_price must be positive"):
        QuoteSnapshot(
            instrument_id="600406.SH",
            instrument_type=InstrumentType.STOCK,
            timestamp=datetime(2026, 8, 3, 14, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
            last_price=0.0,
            open=25.0,
            high=25.1,
            low=24.8,
            pre_close=24.5,
            volume=1000.0,
            amount=25000.0,
            source="fixture",
            fetched_at=datetime(2026, 8, 3, 14, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
        )


def test_decision_status_keeps_blocked_distinct_from_no_trade():
    assert DecisionStatus.BLOCKED.value == "blocked"
    assert DecisionStatus.NO_TRADE.value == "no_trade"
    assert DecisionStatus.BLOCKED is not DecisionStatus.NO_TRADE
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_contracts.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'lib.tail_decision'`.

- [ ] **Step 3: Implement immutable contracts**

Create enums with exact values:

```python
class InstrumentType(str, Enum):
    STOCK = "stock"
    ETF = "etf"


class DecisionStatus(str, Enum):
    RECOMMENDED = "recommended"
    WATCH_ONLY = "watch_only"
    NO_TRADE = "no_trade"
    BLOCKED = "blocked"


class QualityLevel(str, Enum):
    PASS = "pass"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
```

Implement frozen dataclasses. `QuoteSnapshot` uses the exact fields in the test. `QualityDecision` contains `instrument_id: str`, `level: QualityLevel`, `reasons: tuple[str, ...]`, `canonical_quote: QuoteSnapshot | None`, and `source_quotes: tuple[QuoteSnapshot, ...]`. `InstrumentContext` contains `instrument_id: str`, `name: str`, `instrument_type: InstrumentType`, `quality: QualityDecision`, `quote: QuoteSnapshot | None`, and read-only `Mapping[str, Any]` fields named `historical`, `intraday`, `events`, and `metadata`. `Candidate` contains `instrument_id: str`, `name: str`, `instrument_type: InstrumentType`, `score: float`, `max_buy_price: float`, `lot_size: int`, `reasons: tuple[str, ...]`, `rejections: tuple[str, ...]`, `exit_plan: Mapping[str, Any]`, and `theme: str`. `Allocation` contains `instrument_id: str`, `quantity: int`, `limit_price: float`, `notional: float`, and `candidate_score: float`. `DecisionRun` contains `run_id: str`, `as_of: datetime`, `status: DecisionStatus`, `quality: tuple[QualityDecision, ...]`, `etf_candidates: tuple[Candidate, ...]`, `stock_candidates: tuple[Candidate, ...]`, `allocations: tuple[Allocation, ...]`, `reasons: tuple[str, ...]`, `strategy_version: str`, and `config_hash: str`.

- [ ] **Step 4: Run the contract test and verify GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_contracts.py -v`

Expected: 2 tests pass.

- [ ] **Step 5: Commit the task**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/__init__.py skills/deep-analysis/scripts/lib/tail_decision/contracts.py skills/deep-analysis/scripts/tests/tail_decision
git commit -m "feat: add tail decision contracts"
```

---

### Task 2: Validated Configuration and Stable Hash

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/config.py`
- Test: `skills/deep-analysis/scripts/tests/tail_decision/test_config.py`

**Interfaces:**
- Consumes: `InstrumentType` from Task 1.
- Produces: frozen `DecisionConfig` and `config_hash(config) -> str`.

- [ ] **Step 1: Write the failing configuration tests**

```python
import pytest

from lib.tail_decision.config import DecisionConfig, config_hash


def test_default_config_uses_one_shared_8000_exposure_cap():
    config = DecisionConfig()
    assert config.account_assets == 10_000.0
    assert config.max_total_exposure == 8_000.0
    assert config.max_instrument_exposure == 4_000.0
    assert config.max_etf_candidates == 2
    assert config.max_stock_candidates == 2


def test_config_rejects_exposure_above_assets():
    with pytest.raises(ValueError, match="max_total_exposure"):
        DecisionConfig(account_assets=5_000.0, max_total_exposure=8_000.0)


def test_config_hash_is_deterministic():
    assert config_hash(DecisionConfig()) == config_hash(DecisionConfig())
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_config.py -v`

Expected: import fails because `config.py` does not exist.

- [ ] **Step 3: Implement `DecisionConfig`**

Use defaults from the design plus `max_quote_age_seconds=60`, `max_price_deviation_pct=0.3`, `min_sources_for_recommendation=2`, `decision_start="14:10"`, `final_decision_time="14:30"`, `strategy_version="tail-v1"`, stock lot 100, ETF default lot 100, and explicit fee/slippage settings. Serialize with `dataclasses.asdict`, canonical JSON (`sort_keys=True`, compact separators), and SHA256 for `config_hash`.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_config.py -v`

Expected: 3 tests pass.

- [ ] **Step 5: Commit the task**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/config.py skills/deep-analysis/scripts/tests/tail_decision/test_config.py
git commit -m "feat: validate tail decision configuration"
```

---

### Task 3: Free Realtime Quote Adapters

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/free_quotes.py`
- Test: `skills/deep-analysis/scripts/tests/tail_decision/test_free_quotes.py`

**Interfaces:**
- Consumes: `QuoteSnapshot`, `InstrumentType`.
- Produces: `QuoteProvider` protocol, `EastmoneyQuoteProvider`, `TencentQuoteProvider`, `fetch_from_providers(providers, ids, now) -> dict[str, list[QuoteSnapshot]]`.

- [ ] **Step 1: Write failing parser and isolation tests**

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from lib.tail_decision.free_quotes import (
    EastmoneyQuoteProvider,
    fetch_from_providers,
)

NOW = datetime(2026, 8, 3, 14, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_eastmoney_parser_normalizes_scaled_fields():
    payload = {"data": {"f57": "600406", "f58": "国电南瑞", "f43": 2506, "f59": 2,
                        "f46": 2448, "f44": 2509, "f45": 2446, "f60": 2435,
                        "f47": 1000, "f48": 2506000, "f124": int(NOW.timestamp())}}
    quote = EastmoneyQuoteProvider.parse_payload("600406.SH", payload, NOW)
    assert quote.last_price == 25.06
    assert quote.source == "eastmoney"


def test_provider_failure_does_not_discard_other_source():
    class Good:
        name = "good"
        def fetch_quotes(self, ids, now):
            return {ids[0]: EastmoneyQuoteProvider.parse_payload(ids[0], {
                "data": {"f57": "600406", "f58": "国电南瑞", "f43": 2506, "f59": 2,
                         "f46": 2448, "f44": 2509, "f45": 2446, "f60": 2435,
                         "f47": 1000, "f48": 2506000, "f124": int(now.timestamp())}}, now)}
    class Bad:
        name = "bad"
        def fetch_quotes(self, ids, now):
            raise TimeoutError("offline")
    result = fetch_from_providers([Bad(), Good()], ["600406.SH"], NOW)
    assert [q.source for q in result["600406.SH"]] == ["eastmoney"]
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_free_quotes.py -v`

Expected: import fails because `free_quotes.py` does not exist.

- [ ] **Step 3: Implement providers without credentials**

Use injected `requests.Session` and timeout values. Eastmoney requests `api/qt/stock/get`; Tencent requests `qt.gtimg.cn`. Normalize Shanghai/SZ market prefixes, timestamps, volume, amount, and instrument type. Eastmoney price scaling must use response precision field `f59` (`raw / 10**f59`) so both two-decimal stocks and three-decimal ETFs parse correctly. Do not read environment tokens. `fetch_from_providers` catches provider exceptions per provider and preserves successful quotes.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_free_quotes.py -v`

Expected: both tests pass without network access.

- [ ] **Step 5: Commit the task**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/free_quotes.py skills/deep-analysis/scripts/tests/tail_decision/test_free_quotes.py
git commit -m "feat: add free realtime quote adapters"
```

---

### Task 4: Read-Only Local Archive Gateway

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/archive.py`
- Test: `skills/deep-analysis/scripts/tests/tail_decision/test_archive.py`

**Interfaces:**
- Produces: `ArchiveReader(root)`, `latest_partition(dataset, as_of) -> Path | None`, `read_latest(dataset, as_of) -> pandas.DataFrame`, `read_trade_dates(start, end) -> list[str]`.
- Never opens an online provider.

- [ ] **Step 1: Write the failing archive selection test**

```python
from datetime import date
import gzip

from lib.tail_decision.archive import ArchiveReader


def test_reader_chooses_latest_partition_not_after_as_of(tmp_path):
    root = tmp_path / "normalized" / "daily"
    root.mkdir(parents=True)
    for name in ("20260730.csv.gz", "20260731.csv.gz", "20260803.csv.gz"):
        with gzip.open(root / name, "wt", encoding="utf-8") as handle:
            handle.write("ts_code,trade_date,close\n600406.SH," + name[:8] + ",25\n")
    reader = ArchiveReader(tmp_path)
    selected = reader.latest_partition("daily", date(2026, 7, 31))
    assert selected.name == "20260731.csv.gz"
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_archive.py -v`

Expected: import fails because `archive.py` does not exist.

- [ ] **Step 3: Implement deterministic read-only selection**

Search only `root/normalized/<dataset>`. Accept `.csv`, `.csv.gz`, and `.parquet`; parse `YYYYMMDD` from the filename; never select a future partition; raise a typed `ArchiveDataError` for malformed files; return an empty frame only when `required=False` is explicit.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_archive.py -v`

Expected: test passes and no files are created outside `tmp_path`.

- [ ] **Step 5: Commit the task**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/archive.py skills/deep-analysis/scripts/tests/tail_decision/test_archive.py
git commit -m "feat: read tail features from local archive"
```

---

### Task 5: Cross-Source Data Quality Gate

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/quality.py`
- Test: `skills/deep-analysis/scripts/tests/tail_decision/test_quality.py`

**Interfaces:**
- Consumes: `QuoteSnapshot`, `QualityDecision`, `QualityLevel`, `DecisionConfig`.
- Produces: `evaluate_quote_quality(instrument_id, quotes, now, config) -> QualityDecision`.

- [ ] **Step 1: Write failing quality tests**

```python
from dataclasses import replace
from datetime import timedelta

from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.contracts import QualityLevel
from lib.tail_decision.quality import evaluate_quote_quality
from .fixtures import quote


def test_two_fresh_sources_within_point_three_percent_pass():
    first = quote(source="eastmoney", last_price=25.00)
    second = quote(source="tencent", last_price=25.05)
    decision = evaluate_quote_quality(first.instrument_id, [first, second], first.fetched_at, DecisionConfig())
    assert decision.level is QualityLevel.PASS


def test_single_source_is_degraded_not_recommendable():
    first = quote(source="eastmoney", last_price=25.00)
    decision = evaluate_quote_quality(first.instrument_id, [first], first.fetched_at, DecisionConfig())
    assert decision.level is QualityLevel.DEGRADED
    assert "insufficient_independent_sources" in decision.reasons


def test_stale_or_conflicting_quotes_are_blocked():
    first = quote(source="eastmoney", last_price=25.00)
    stale = replace(quote(source="tencent", last_price=25.20), fetched_at=first.fetched_at - timedelta(seconds=61))
    decision = evaluate_quote_quality(first.instrument_id, [first, stale], first.fetched_at, DecisionConfig())
    assert decision.level is QualityLevel.BLOCKED
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_quality.py -v`

Expected: import fails because `quality.py` does not exist.

- [ ] **Step 3: Implement the gate**

Deduplicate by source, reject mismatched instrument IDs/types, reject non-finite values, compute maximum quote age, calculate deviation as `(max_price - min_price) / median_price * 100`, and choose the median-price quote as canonical. One valid source is `DEGRADED`; zero, stale data, or deviation above threshold is `BLOCKED`; two independent valid sources is `PASS`.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_quality.py -v`

Expected: 3 tests pass.

- [ ] **Step 5: Commit the task**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/quality.py skills/deep-analysis/scripts/tests/tail_decision/fixtures.py skills/deep-analysis/scripts/tests/tail_decision/test_quality.py
git commit -m "feat: gate tail decisions on quote quality"
```

---

### Task 6: Deterministic Historical and Intraday Features

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/features.py`
- Test: `skills/deep-analysis/scripts/tests/tail_decision/test_features.py`

**Interfaces:**
- Produces: `build_historical_features(daily_frame, daily_basic_frame, moneyflow_frame) -> dict[str, dict]`, `build_intraday_features(bars, as_of) -> dict`.

- [ ] **Step 1: Write failing no-lookahead tests**

```python
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from lib.tail_decision.features import build_intraday_features


def test_intraday_features_ignore_bars_after_as_of():
    bars = pd.DataFrame([
        {"timestamp": "2026-08-03 14:00:00+08:00", "close": 10.0, "volume": 100, "amount": 1000},
        {"timestamp": "2026-08-03 14:10:00+08:00", "close": 10.2, "volume": 100, "amount": 1020},
        {"timestamp": "2026-08-03 14:11:00+08:00", "close": 20.0, "volume": 100, "amount": 2000},
    ])
    as_of = datetime(2026, 8, 3, 14, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
    result = build_intraday_features(bars, as_of)
    assert result["last_price"] == 10.2
    assert result["tail_return_pct"] == 2.0
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_features.py -v`

Expected: import fails because `features.py` does not exist.

- [ ] **Step 3: Implement pure feature builders**

Normalize timestamps to Asia/Shanghai, restrict bars to `timestamp <= as_of`, require a bar at or after 14:10 for production scoring, calculate VWAP from cumulative amount/volume, tail return from the latest bar at or before 14:00, distance to VWAP, range position, recent turnover, 20-day average amount, 5/20-day returns, volatility, and latest money-flow values. Return finite numbers or explicit `None`; never silently substitute a future row.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_features.py -v`

Expected: test passes with `tail_return_pct == 2.0`.

- [ ] **Step 5: Commit the task**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/features.py skills/deep-analysis/scripts/tests/tail_decision/test_features.py
git commit -m "feat: compute deterministic tail features"
```

---

### Task 7: ETF Candidate Strategy

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/etf_strategy.py`
- Test: `skills/deep-analysis/scripts/tests/tail_decision/test_etf_strategy.py`

**Interfaces:**
- Consumes: `InstrumentContext`, `Candidate`, `DecisionConfig`, `QualityLevel`.
- Produces: `rank_etfs(contexts, config) -> tuple[list[Candidate], dict[str, list[str]]]`.

- [ ] **Step 1: Write failing ETF filter and ranking tests**

```python
from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.etf_strategy import rank_etfs
from .fixtures import etf_context


def test_etf_strategy_rejects_low_liquidity_and_ranks_tail_strength():
    strong = etf_context("513050.SH", amount=2_000_000_000, tail_return_pct=1.2,
                         vwap_distance_pct=0.4, quality="pass")
    weak = etf_context("513180.SH", amount=1_500_000_000, tail_return_pct=0.2,
                       vwap_distance_pct=0.1, quality="pass")
    illiquid = etf_context("560000.SH", amount=10_000_000, tail_return_pct=3.0,
                           vwap_distance_pct=1.0, quality="pass")
    candidates, rejected = rank_etfs([weak, illiquid, strong], DecisionConfig())
    assert [c.instrument_id for c in candidates] == ["513050.SH", "513180.SH"]
    assert "low_turnover" in rejected["560000.SH"]
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_etf_strategy.py -v`

Expected: import fails because `etf_strategy.py` does not exist.

- [ ] **Step 3: Implement ETF hard filters and score**

Hard-filter blocked/degraded quality, daily amount below CNY 50 million, unknown lot size, missing tracking metadata, and premium proxy above configured maximum. Score only documented inputs: tail return, VWAP distance, range position, normalized money flow, volume ratio, and penalties for excessive daily gain, stale NAV proxy, or an underlying market that has closed. Sort by `(-score, instrument_id)` and return at most 2 candidates. Provide a deterministic next-session exit template in `exit_plan`.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_etf_strategy.py -v`

Expected: test passes and the illiquid ETF is rejected.

- [ ] **Step 5: Commit the task**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/etf_strategy.py skills/deep-analysis/scripts/tests/tail_decision/test_etf_strategy.py
git commit -m "feat: rank executable ETF tail candidates"
```

---

### Task 8: Overnight Stock Candidate Strategy

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/stock_strategy.py`
- Test: `skills/deep-analysis/scripts/tests/tail_decision/test_stock_strategy.py`

**Interfaces:**
- Consumes: `InstrumentContext`, `Candidate`, `DecisionConfig`, `QualityLevel`.
- Produces: `rank_overnight_stocks(contexts, config) -> tuple[list[Candidate], dict[str, list[str]]]`.

- [ ] **Step 1: Write failing eligibility and affordability tests**

```python
from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.stock_strategy import rank_overnight_stocks
from .fixtures import stock_context


def test_stock_strategy_filters_st_limit_and_unaffordable_lots():
    valid = stock_context("600406.SH", price=25.0, name="国电南瑞", tail_return_pct=1.0)
    st = stock_context("000001.SZ", price=10.0, name="ST样本", is_st=True)
    near_limit = stock_context("000002.SZ", price=10.95, name="涨停样本",
                               pre_close=10.0, limit_up=11.0)
    expensive = stock_context("600519.SH", price=1600.0, name="高价样本")
    candidates, rejected = rank_overnight_stocks([st, near_limit, expensive, valid], DecisionConfig())
    assert [c.instrument_id for c in candidates] == ["600406.SH"]
    assert "st_or_delisting" in rejected["000001.SZ"]
    assert "near_unbuyable_limit" in rejected["000002.SZ"]
    assert "minimum_lot_exceeds_cap" in rejected["600519.SH"]
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_stock_strategy.py -v`

Expected: import fails because `stock_strategy.py` does not exist.

- [ ] **Step 3: Implement hard filters and score**

Reject ST/delisting, suspended, listing age below 60 natural days, 20-day average amount below CNY 300 million, 100-share lot above per-instrument cap, daily gain at or above 9.2%, price within 0.5% of a non-tradable limit-up, adverse event flags, and quality below `PASS`. Score tail return, VWAP position, range position, amount ratio, latest and five-day money flow, sector relative strength, and volatility/overextension penalties. Sort deterministically and return at most 2.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_stock_strategy.py -v`

Expected: test passes with only `600406.SH` eligible.

- [ ] **Step 5: Commit the task**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/stock_strategy.py skills/deep-analysis/scripts/tests/tail_decision/test_stock_strategy.py
git commit -m "feat: rank executable overnight stock candidates"
```

---

### Task 9: Shared Account Portfolio Allocator

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/portfolio.py`
- Test: `skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py`

**Interfaces:**
- Consumes: `Candidate`, `Allocation`, `DecisionConfig`.
- Produces: `allocate_portfolio(etfs, stocks, config) -> tuple[list[Allocation], list[str]]`.

- [ ] **Step 1: Write the failing shared-cap tests**

```python
from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.portfolio import allocate_portfolio
from .fixtures import candidate


def test_etf_and_stock_share_one_8000_cap():
    etf = candidate("513050.SH", kind="etf", price=1.18, lot_size=100, score=80)
    stock = candidate("600406.SH", kind="stock", price=25.0, lot_size=100, score=78)
    allocations, reasons = allocate_portfolio([etf], [stock], DecisionConfig())
    assert sum(item.notional for item in allocations) <= 8_000.0
    assert all(item.notional <= 4_000.0 for item in allocations)
    assert {item.instrument_id for item in allocations} == {"513050.SH", "600406.SH"}


def test_allocator_returns_empty_when_no_lot_fits():
    stock = candidate("600519.SH", kind="stock", price=1600.0, lot_size=100, score=99)
    allocations, reasons = allocate_portfolio([], [stock], DecisionConfig())
    assert allocations == []
    assert "no_affordable_candidate" in reasons
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py -v`

Expected: import fails because `portfolio.py` does not exist.

- [ ] **Step 3: Implement deterministic account allocation**

Merge candidates by score, reserve no more than one ETF and one stock, reject duplicate themes, allocate up to `max_instrument_exposure` in whole lots, recalculate remaining shared exposure after each allocation, and never exceed account cash. Return reasons for skipped candidates and for an empty portfolio.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py -v`

Expected: 2 tests pass and total notional is at most CNY 8,000.

- [ ] **Step 5: Commit the task**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/portfolio.py skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py
git commit -m "feat: allocate one shared tail portfolio"
```

---

### Task 10: Append-Only Recorder and Human Report

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/recorder.py`
- Test: `skills/deep-analysis/scripts/tests/tail_decision/test_recorder.py`

**Interfaces:**
- Consumes: `DecisionRun`.
- Produces: `DecisionRecorder(root).record(run, raw_quotes) -> Path`, `render_markdown(run) -> str`.

- [ ] **Step 1: Write failing audit and secret tests**

```python
import json

from lib.tail_decision.recorder import DecisionRecorder
from .fixtures import decision_run


def test_recorder_is_append_only_and_redacts_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-value")
    recorder = DecisionRecorder(tmp_path)
    first = recorder.record(decision_run(run_id="run-a"), raw_quotes={"token": "secret-value"})
    second = recorder.record(decision_run(run_id="run-b"), raw_quotes={})
    assert first != second
    assert "secret-value" not in first.read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["status"] == "recommended"
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_recorder.py -v`

Expected: import fails because `recorder.py` does not exist.

- [ ] **Step 3: Implement atomic append-only artifacts**

Write to `reports/tail_decision/YYYYMMDD/<timestamp>_<run_id>.json` via a temporary sibling and atomic rename. Refuse to overwrite an existing run ID. Recursively redact keys matching `token`, `secret`, `password`, and `authorization`. Write a sibling Markdown report with two candidate sections, one final account plan, status/reasons, source timestamps, limit prices, quantities, cancellation rules, and exits.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_recorder.py -v`

Expected: test passes; both artifacts remain and contain no secret.

- [ ] **Step 5: Commit the task**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/recorder.py skills/deep-analysis/scripts/tests/tail_decision/test_recorder.py
git commit -m "feat: record auditable tail decisions"
```

---

### Task 11: Forward Simulator and Next-Session Exit Ledger

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/simulator.py`
- Test: `skills/deep-analysis/scripts/tests/tail_decision/test_simulator.py`

**Interfaces:**
- Consumes: `Allocation`, saved minute bars, `DecisionConfig` fee fields.
- Produces: `simulate_entry`, `simulate_next_session_exit`, `summarize_ledger`.

- [ ] **Step 1: Write failing T+1 cost test**

```python
from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.simulator import simulate_round_trip
from .fixtures import allocation


def test_stock_round_trip_applies_minimum_commission_and_sell_tax():
    trade = simulate_round_trip(
        allocation("600406.SH", quantity=100, limit_price=25.0),
        entry_price=25.0,
        exit_price=25.5,
        instrument_type="stock",
        config=DecisionConfig(),
    )
    assert trade["entry_fee"] >= 5.0
    assert trade["exit_fee"] >= 5.0
    assert trade["sell_stamp_tax"] > 0
    assert trade["net_pnl"] < 50.0
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_simulator.py -v`

Expected: import fails because `simulator.py` does not exist.

- [ ] **Step 3: Implement conservative fills and metrics**

Stocks cannot exit on entry date. Entries above the limit price, zero-volume bars, limit-up buys, limit-down sells, and suspended bars remain unfilled. Apply configured slippage, minimum commission per order, sell stamp tax for stocks, and configured ETF costs. `summarize_ledger` returns net return, Profit Factor, maximum drawdown, trade count, win rate, average win/loss, and ETF/stock breakdowns.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_simulator.py -v`

Expected: test passes with positive but sub-CNY-50 net P&L.

- [ ] **Step 5: Commit the task**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/simulator.py skills/deep-analysis/scripts/tests/tail_decision/test_simulator.py
git commit -m "feat: simulate tail entries and next-session exits"
```

---

### Task 12: Workflow Orchestrator and Status Resolution

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tail_decision/workflow.py`
- Test: `skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py`

**Interfaces:**
- Consumes all prior components through constructor injection.
- Produces: `TailDecisionWorkflow.run(as_of, phase) -> DecisionRun` where phase is `warmup`, `preview`, `final`, `close`, `exit_open`, or `exit_check`.

- [ ] **Step 1: Write failing status tests**

```python
from lib.tail_decision.contracts import DecisionStatus
from lib.tail_decision.workflow import TailDecisionWorkflow
from .fixtures import workflow_dependencies


def test_workflow_does_not_turn_provider_failure_into_no_trade():
    workflow = TailDecisionWorkflow(**workflow_dependencies(all_providers_fail=True))
    result = workflow.run(as_of="2026-08-03T14:10:00+08:00", phase="preview")
    assert result.status is DecisionStatus.BLOCKED


def test_single_source_produces_watch_only_without_allocations():
    workflow = TailDecisionWorkflow(**workflow_dependencies(single_source=True))
    result = workflow.run(as_of="2026-08-03T14:10:00+08:00", phase="preview")
    assert result.status is DecisionStatus.WATCH_ONLY
    assert result.allocations == ()
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py -v`

Expected: import fails because `workflow.py` does not exist.

- [ ] **Step 3: Implement explicit phase orchestration**

`warmup` checks the local calendar/archive and provider reachability without producing allocations; `preview` fetches and records candidates; `final` reruns quality and allocates; `close` appends close snapshots; `exit_open` creates 09:25 exit instructions; `exit_check` records 09:35 simulation outcomes. Resolve statuses in this order: system/data failure -> `BLOCKED`; candidates with degraded quality -> `WATCH_ONLY`; passed candidates but no qualifying strategy -> `NO_TRADE`; non-empty valid allocations -> `RECOMMENDED`.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py -v`

Expected: 2 tests pass with distinct blocked and watch-only states.

- [ ] **Step 5: Commit the task**

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/workflow.py skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py
git commit -m "feat: orchestrate tail decision phases"
```

---

### Task 13: Local CLI Without Paid Credentials

**Files:**
- Create: `skills/deep-analysis/scripts/run_tail_decision.py`
- Test: `skills/deep-analysis/scripts/tests/tail_decision/test_cli.py`

**Interfaces:**
- Consumes: `TailDecisionWorkflow`, `DecisionConfig`, `DecisionRecorder`.
- Produces CLI options `--phase`, `--as-of`, `--data-root`, `--output-root`, `--account-assets`, `--max-exposure`, `--offline-fixture`.

- [ ] **Step 1: Write the failing fixture-mode CLI test**

```python
import json
import subprocess
import sys


def test_cli_runs_without_tushare_token(tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    command = [
        sys.executable,
        "skills/deep-analysis/scripts/run_tail_decision.py",
        "--phase", "preview",
        "--as-of", "2026-08-03T14:10:00+08:00",
        "--offline-fixture",
        "--output-root", str(tmp_path),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] in {"recommended", "watch_only", "no_trade"}
    assert payload["total_exposure"] <= 8_000.0
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_cli.py -v`

Expected: subprocess fails because `run_tail_decision.py` does not exist.

- [ ] **Step 3: Implement the CLI**

Build production providers only when `--offline-fixture` is absent. Fixture mode uses deterministic in-memory quotes and local temporary historical frames. Print one compact JSON summary to stdout; send diagnostics to stderr; return 0 for recommended/watch/no-trade, 2 for blocked, and 3 for invalid configuration. Do not load `.env` or Tushare in this entry point.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_cli.py -v`

Expected: test passes with no token and exposure at most CNY 8,000.

- [ ] **Step 5: Commit the task**

```powershell
git add skills/deep-analysis/scripts/run_tail_decision.py skills/deep-analysis/scripts/tests/tail_decision/test_cli.py
git commit -m "feat: add local tail decision CLI"
```

---

### Task 14: Windows Local Scheduler

**Files:**
- Create: `scripts/install_tail_decision_tasks.ps1`
- Test: `skills/deep-analysis/scripts/tests/tail_decision/test_scheduler_script.py`

**Interfaces:**
- Produces seven idempotent scheduled tasks invoking the local CLI at 14:00 (`warmup`), 14:10 (`preview`), 14:20 (`preview` refresh), 14:30 (`final`), 15:05 (`close`), 09:25 (`exit_open`), and 09:35 (`exit_check`).
- No dependency on Codex automation.

- [ ] **Step 1: Write the failing script contract test**

```python
from pathlib import Path


def test_scheduler_uses_local_cli_and_no_credentials():
    script = Path("scripts/install_tail_decision_tasks.ps1")
    text = script.read_text(encoding="utf-8")
    assert "run_tail_decision.py" in text
    assert "--phase preview" in text
    assert "--phase final" in text
    assert "--phase exit_open" in text
    assert "TUSHARE_TOKEN" not in text
    assert "Start-Process" not in text or "-WindowStyle Hidden" in text
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_scheduler_script.py -v`

Expected: `FileNotFoundError` because the scheduler script does not exist.

- [ ] **Step 3: Implement idempotent task registration**

Resolve absolute project and Python paths, validate they remain under `D:/work/gupiao/UZI-Skill`, use explicit `Register-ScheduledTask` actions and weekday triggers, run hidden, write logs under `reports/tail_decision/scheduler`, and update existing task definitions by exact task name rather than creating duplicates. Include `-WhatIf` support so tests and users can inspect actions without mutation.

- [ ] **Step 4: Run and verify GREEN**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_scheduler_script.py -v`

Expected: test passes. Then run `powershell -ExecutionPolicy Bypass -File scripts/install_tail_decision_tasks.ps1 -WhatIf` and verify it prints the intended task names without registering them.

- [ ] **Step 5: Commit the task**

```powershell
git add scripts/install_tail_decision_tasks.ps1 skills/deep-analysis/scripts/tests/tail_decision/test_scheduler_script.py
git commit -m "feat: schedule local tail decision phases"
```

---

### Task 15: No-Token End-to-End Gate and Operations Guide

**Files:**
- Create: `skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py`
- Create: `docs/data/tail-decision-operations.md`
- Modify: `skills/deep-analysis/scripts/lib/tail_decision/__init__.py`

**Interfaces:**
- Consumes the public CLI and output files.
- Produces the final acceptance gate and operating instructions.

- [ ] **Step 1: Write the failing end-to-end acceptance test**

```python
import json
import os
import subprocess
import sys


def test_no_token_end_to_end_records_bounded_portfolio(tmp_path):
    env = os.environ.copy()
    env.pop("TUSHARE_TOKEN", None)
    completed = subprocess.run([
        sys.executable,
        "skills/deep-analysis/scripts/run_tail_decision.py",
        "--phase", "final",
        "--as-of", "2026-08-03T14:30:00+08:00",
        "--offline-fixture",
        "--output-root", str(tmp_path),
    ], env=env, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["total_exposure"] <= 8_000.0
    artifacts = list(tmp_path.rglob("*.json"))
    assert artifacts
    assert all("TUSHARE_TOKEN" not in path.read_text(encoding="utf-8") for path in artifacts)
```

- [ ] **Step 2: Run the test and verify the acceptance gap**

Run: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py -v`

Expected: fail if the public exports, fixture workflow, recorder, or bounded allocation are not fully wired.

- [ ] **Step 3: Wire public exports and write operations documentation**

Export `DecisionConfig`, `TailDecisionWorkflow`, and `DecisionRecorder` from `lib.tail_decision`. Document exact preview/final/close/exit commands, output paths, status meanings, scheduler installation with `-WhatIf`, no-token operation, recovery from `blocked`, strategy-version rules, simulation gates, and the explicit statement that reports are decision support and never broker orders.

- [ ] **Step 4: Run focused and regression verification**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/tail_decision -q
python -m pytest skills/deep-analysis/scripts/tests/test_trading_calendar_safety.py skills/deep-analysis/scripts/tests/test_providers_chain.py -q
python skills/deep-analysis/scripts/run_tail_decision.py --phase final --as-of 2026-08-03T14:30:00+08:00 --offline-fixture --output-root .cache/tail-decision-acceptance
```

Expected: all tests pass; CLI returns 0; JSON reports total exposure at most 8,000; no output contains credentials.

- [ ] **Step 5: Inspect scope and commit the acceptance task**

Run `git status --short` and `git diff --check`. Confirm no unrelated dirty file was staged. Then:

```powershell
git add skills/deep-analysis/scripts/lib/tail_decision/__init__.py skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py docs/data/tail-decision-operations.md
git commit -m "docs: verify no-token tail decision operations"
```

---

## Completion Audit

Before declaring the system complete:

- [ ] Map every requirement in `docs/superpowers/specs/2026-08-03-self-sustaining-tail-decision-system-design.md` to a passing test or documented operational check.
- [ ] Confirm the core import graph contains no Tushare import.
- [ ] Confirm an empty environment without `TUSHARE_TOKEN` completes fixture-mode preview and final phases.
- [ ] Confirm two-source disagreement above 0.3% produces `blocked` and zero allocations.
- [ ] Confirm one-source data produces `watch_only` and zero allocations.
- [ ] Confirm ETF plus stock combined exposure never exceeds CNY 8,000.
- [ ] Confirm the recorder distinguishes `blocked` from `no_trade`.
- [ ] Confirm all writes are limited to the configured report/cache roots.
- [ ] Confirm `-WhatIf` scheduler installation performs no external mutation.
- [ ] Confirm no broker, order-submission, paid-card, full-catalog, or historical-minute capability was added.
- [ ] Generate `docs/data/tail-decision-implementation-report.md` with test commands, results, known limitations, and the start date of the 60-trading-day forward simulation.

## Automated Execution Choice

The user authorized gradual background execution in the current task. Use **Inline Execution via `superpowers:executing-plans`** during automation heartbeats, completing one task or one tightly related TDD batch per heartbeat. Do not create user-owned subthreads. Preserve unrelated dirty files and report only milestones, genuine blockers, or final completion.
