# A股尾盘隔夜回测与分钟归档 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立无未来函数、点时股票池、真实成交约束的 14:20 信号/14:30 买入/次日卖出回测器，并在不重叠现有在线采集的前提下归档可用的历史 1 分钟数据。

**Architecture:** 本地纯函数核心负责数据契约、股票池、复权、信号、执行、账户和统计，任何外部 API 都隔离在归档适配器与 CLI 中。先用小型 DataFrame 夹具完成完整红绿重构周期，再探测兼容端点的分钟接口；接口不支持时产出可审计的 blocked 结果，不用日线伪造分钟数据。

**Tech Stack:** Python 3.11+、pandas 2.x、numpy、pytest；Parquet 优先使用环境已有的 pyarrow，缺失时明确阻断标准化归档，不静默降级格式。

## Global Constraints

- 信号时刻 14:20:00 只能读取 `bar_end <= 14:19:59`。
- 首轮信号固定为个股 14:00–14:19 收益减沪深300同时段收益，每日最多一只。
- 买入窗口 14:30–14:34，卖出窗口下一可交易日 9:35–9:39。
- 真实账户按 100 股整数交易，每分钟参与率不超过 5%。
- 成交使用未复权价格；信号使用每日 `adj_factor` 映射后的连续价格。
- 默认测试 5、10、20 bps 滑点，20 bps 为压力情景。
- 股票佣金默认万分之 2.5、每个实际订单最低 5 元；卖出印花税默认万分之 5。
- 线上请求固定 120 次/分钟、最多 12 workers，全部 worker 共享启动限流器。
- 当前 `export_tushare_mainbz.py` 活跃时禁止启动分钟 API 请求。
- manifest append-only；成功分片不重复请求，不删除现有成功文件。
- Token 只从现有环境加载器读取，不进入命令行、日志、manifest 或归档文件。
- 不修改现有选股评分、报告管线和无关未提交工作。

## File Structure

```text
skills/deep-analysis/scripts/lib/intraday/
  __init__.py       公共类型导出
  contracts.py      分钟记录契约、时间边界和数据校验
  universe.py       点时资格与过去20日流动性前N股票池
  adjustments.py    日复权因子到分钟价格映射
  signals.py        相对尾盘动量与确定性候选选择
  execution.py      五分钟分笔成交、涨跌停、参与率和费用
  portfolio.py      统一名义账户与1万元现金账户状态机
  validation.py     时间切割、统计指标、block bootstrap、市场状态
  archive.py        分片生成、接口探测、raw/Parquet/manifest持久化

skills/deep-analysis/scripts/
  export_tushare_minutes.py       权限探测和可恢复分钟归档 CLI
  backtest_overnight_intraday.py  读取归档、运行实验和保存报告 CLI

skills/deep-analysis/scripts/tests/
  test_intraday_contracts.py
  test_intraday_universe.py
  test_intraday_adjustments.py
  test_intraday_signals.py
  test_intraday_execution.py
  test_intraday_portfolio.py
  test_intraday_validation.py
  test_tushare_minute_archive.py
  test_intraday_cli.py
```

---

### Task 1: 分钟数据契约与时间边界

**Files:**
- Create: `skills/deep-analysis/scripts/lib/intraday/__init__.py`
- Create: `skills/deep-analysis/scripts/lib/intraday/contracts.py`
- Test: `skills/deep-analysis/scripts/tests/test_intraday_contracts.py`

**Interfaces:**
- Produces: `MinuteDataError(ValueError)`.
- Produces: `normalize_minute_frame(frame: pd.DataFrame, *, requested_code: str, shard_start: date, shard_end: date, source: str, fetched_at: datetime) -> pd.DataFrame`.
- Produces: `available_at(frame: pd.DataFrame, cutoff: datetime) -> pd.DataFrame`.
- Produces: constants `SIGNAL_CUTOFF`, `ENTRY_MINUTES`, `EXIT_MINUTES`.

- [ ] **Step 1: Write failing contract tests**

```python
def test_signal_cutoff_excludes_bar_ending_at_142059():
    frame = pd.DataFrame({
        "bar_end": pd.to_datetime([
            "2026-07-30 14:19:59+08:00",
            "2026-07-30 14:20:59+08:00",
        ])
    })
    result = available_at(frame, pd.Timestamp("2026-07-30 14:20:00", tz="Asia/Shanghai"))
    assert result["bar_end"].dt.strftime("%H:%M:%S").tolist() == ["14:19:59"]


def test_normalizer_rejects_other_security_and_duplicate_minute():
    raw = pd.DataFrame([
        {"ts_code": "000001.SZ", "trade_time": "2026-07-30 14:19:00", "open": 10,
         "high": 10, "low": 10, "close": 10, "vol": 100, "amount": 1000},
        {"ts_code": "000002.SZ", "trade_time": "2026-07-30 14:19:00", "open": 10,
         "high": 10, "low": 10, "close": 10, "vol": 100, "amount": 1000},
    ])
    with pytest.raises(MinuteDataError, match="unexpected ts_code"):
        normalize_minute_frame(
            raw, requested_code="000001.SZ",
            shard_start=date(2026, 7, 1), shard_end=date(2026, 7, 31),
            source="fixture", fetched_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        )
```

- [ ] **Step 2: Run tests and confirm RED**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_contracts.py -q
```

Expected: collection fails because `lib.intraday.contracts` does not exist.

- [ ] **Step 3: Implement strict normalization**

```python
SIGNAL_CUTOFF = time(14, 20)
ENTRY_MINUTES = tuple(time(14, minute) for minute in range(30, 35))
EXIT_MINUTES = tuple(time(9, minute) for minute in range(35, 40))


class MinuteDataError(ValueError):
    pass


def available_at(frame: pd.DataFrame, cutoff: datetime) -> pd.DataFrame:
    return frame.loc[frame["bar_end"] < pd.Timestamp(cutoff)].copy()
```

`normalize_minute_frame` 将源字段映射成规格中的 11 个标准字段，使用
`Asia/Shanghai` 时区，把分钟标签解释为 `bar_start` 并生成
`bar_end = bar_start + 59秒`；拒绝其他代码、日期越界、午间记录、重复键、
OHLC 非正数、`high < max(open, close)`、`low > min(open, close)` 和负量额。
源字段单位只能由显式探测配置传入，不能在该函数中猜测。

- [ ] **Step 4: Run contract tests and confirm GREEN**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_contracts.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit the isolated contract**

```powershell
git add -- skills/deep-analysis/scripts/lib/intraday/__init__.py skills/deep-analysis/scripts/lib/intraday/contracts.py skills/deep-analysis/scripts/tests/test_intraday_contracts.py
git commit -m "feat: add strict intraday data contract"
```

### Task 2: 点时股票池

**Files:**
- Create: `skills/deep-analysis/scripts/lib/intraday/universe.py`
- Test: `skills/deep-analysis/scripts/tests/test_intraday_universe.py`

**Interfaces:**
- Consumes: 标准日线列 `ts_code, trade_date, amount`。
- Produces: `build_point_in_time_universe(daily, security_history, trading_status, *, top_n=500, lookback=20, min_listing_days=60) -> pd.DataFrame`，输出 `trade_date, ts_code, avg_amount_20d, liquidity_rank`。

- [ ] **Step 1: Write failing point-in-time tests**

```python
def test_universe_uses_only_completed_days_and_keeps_later_delisted_stock():
    result = build_point_in_time_universe(
        daily=daily_fixture_with_large_current_day_amount(),
        security_history=pd.DataFrame([
            {"ts_code": "OLD.SZ", "list_date": "20200101", "delist_date": "20260731"},
            {"ts_code": "NEW.SZ", "list_date": "20260701", "delist_date": None},
        ]),
        trading_status=status_fixture(active_codes=["OLD.SZ", "NEW.SZ"]),
        top_n=1, lookback=2, min_listing_days=60,
    )
    assert result.query("trade_date == '20260730'")["ts_code"].tolist() == ["OLD.SZ"]
```

增加两个测试：`T` 日 amount 不改变排名；ST/停牌按 `effective_from <= T <
effective_to` 排除，而当前名称或当前状态不影响历史日期。

- [ ] **Step 2: Run universe tests and confirm RED**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_universe.py -q
```

Expected: import fails for missing `build_point_in_time_universe`.

- [ ] **Step 3: Implement rolling liquidity ranking**

实现步骤必须是：

```text
1. daily 按 ts_code/trade_date 排序；
2. 对 amount 先 shift(1)，再 rolling(lookback, min_periods=lookback).mean()；
3. 将 list_date/delist_date 与点时状态按日期区间连接；
4. 过滤上市不足60自然日、ST、退市整理、停牌和无有效14:20成交的代码；
5. 每个 trade_date 按 avg_amount_20d 降序、ts_code 升序稳定排序；
6. 取前 top_n 并生成从1开始的 liquidity_rank。
```

- [ ] **Step 4: Run universe tests and confirm GREEN**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_universe.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit point-in-time universe**

```powershell
git add -- skills/deep-analysis/scripts/lib/intraday/universe.py skills/deep-analysis/scripts/tests/test_intraday_universe.py
git commit -m "feat: build point-in-time liquid universe"
```

### Task 3: 复权映射与信号

**Files:**
- Create: `skills/deep-analysis/scripts/lib/intraday/adjustments.py`
- Create: `skills/deep-analysis/scripts/lib/intraday/signals.py`
- Test: `skills/deep-analysis/scripts/tests/test_intraday_adjustments.py`
- Test: `skills/deep-analysis/scripts/tests/test_intraday_signals.py`

**Interfaces:**
- Produces: `apply_signal_adjustment(minutes, adj_factors) -> pd.DataFrame`，新增 `signal_open, signal_high, signal_low, signal_close`。
- Produces: `score_tail_relative_momentum(stock_minutes, benchmark_minutes, trade_date) -> float`.
- Produces: `select_daily_candidate(scores: pd.DataFrame) -> pd.Series | None`.

- [ ] **Step 1: Write failing adjustment and anti-lookahead tests**

```python
def test_adjustment_preserves_raw_execution_price_and_continuous_signal_price():
    result = apply_signal_adjustment(minutes_across_split(), adj_factor_across_split())
    assert result["close"].tolist() == [20.0, 10.0]
    assert result["signal_close"].tolist() == pytest.approx([20.0, 20.0])


def test_signal_ignores_1420_bar_and_subtracts_benchmark():
    score = score_tail_relative_momentum(
        stock_minutes=stock_with_1359_100_1419_102_1420_150(),
        benchmark_minutes=benchmark_with_1359_100_1419_101_1420_80(),
        trade_date="20260730",
    )
    assert score == pytest.approx(0.01)
```

增加测试：缺少 13:59 或 14:19 时返回 `NaN`；同分按 `ts_code` 选择较小代码；
输入包含 `bar_end >= 14:20:00` 不改变结果。

- [ ] **Step 2: Run adjustment/signal tests and confirm RED**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_adjustments.py skills/deep-analysis/scripts/tests/test_intraday_signals.py -q
```

Expected: modules are missing.

- [ ] **Step 3: Implement normalized factor and fixed signal**

```python
def apply_signal_adjustment(minutes, adj_factors):
    merged = minutes.merge(adj_factors[["ts_code", "trade_date", "adj_factor"]],
                           on=["ts_code", "trade_date"], how="left", validate="many_to_one")
    if merged["adj_factor"].isna().any():
        raise ValueError("missing adj_factor")
    for field in ("open", "high", "low", "close"):
        merged[f"signal_{field}"] = merged[field] * merged["adj_factor"]
    return merged
```

信号实现仅取 13:59 和 14:19 两根已完成分钟，按设计公式返回标量；不引入阈值、
量价附加因子或参数搜索。

- [ ] **Step 4: Run tests and confirm GREEN**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_adjustments.py skills/deep-analysis/scripts/tests/test_intraday_signals.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit adjustment and signal**

```powershell
git add -- skills/deep-analysis/scripts/lib/intraday/adjustments.py skills/deep-analysis/scripts/lib/intraday/signals.py skills/deep-analysis/scripts/tests/test_intraday_adjustments.py skills/deep-analysis/scripts/tests/test_intraday_signals.py
git commit -m "feat: add adjusted tail momentum signal"
```

### Task 4: 分笔成交与费用

**Files:**
- Create: `skills/deep-analysis/scripts/lib/intraday/execution.py`
- Test: `skills/deep-analysis/scripts/tests/test_intraday_execution.py`

**Interfaces:**
- Produces dataclasses:

```python
@dataclass(frozen=True)
class FeeSchedule:
    commission_rate: float = 0.00025
    minimum_commission: float = 5.0
    sell_stamp_tax: float = 0.0005
    transfer_fee_rate: float = 0.0

@dataclass(frozen=True)
class Fill:
    ts_code: str
    side: Literal["buy", "sell"]
    bar_start: pd.Timestamp
    shares: int
    price: float
    gross_value: float
    fees: float
```

- Produces: `simulate_window(minutes, *, side, requested_shares, slippage_bps, participation_rate, limit_price, fee_schedule) -> tuple[list[Fill], int]`，第二项为未成交股数。

- [ ] **Step 1: Write failing execution tests**

```python
def test_buy_adds_slippage_caps_participation_and_rounds_lots():
    fills, unfilled = simulate_window(
        minutes=five_bars(volume_shares=10_000, vwap=10.0),
        side="buy", requested_shares=1_000, slippage_bps=10,
        participation_rate=0.05, limit_price=11.0, fee_schedule=FeeSchedule(),
    )
    assert sum(fill.shares for fill in fills) == 1_000
    assert fills[0].price == pytest.approx(10.01)
    assert all(fill.shares <= 500 for fill in fills)
    assert unfilled == 0


def test_each_actual_order_pays_minimum_commission():
    fills, _ = simulate_window(
        minutes=five_bars(volume_shares=100_000, vwap=1.0),
        side="buy", requested_shares=500, slippage_bps=0,
        participation_rate=0.05, limit_price=1.1, fee_schedule=FeeSchedule(),
    )
    assert sum(fill.fees for fill in fills) == 25.0
```

增加测试：卖出减滑点并收印花税；收盘等于涨停价不买、等于跌停价不卖；
零成交量不成交；窗口结束返回未成交；每笔股数为 100 的整数倍。

- [ ] **Step 2: Run execution tests and confirm RED**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_execution.py -q
```

Expected: missing execution module.

- [ ] **Step 3: Implement deterministic five-slice execution**

每个窗口按时间顺序执行。初始目标平均分成五份并向下修正为 100 股；前一笔未成交
的数量滚入后续分钟。可成交股数为
`floor(min(remaining, volume_shares * participation_rate) / 100) * 100`。
价格使用分钟 `amount_yuan / volume_shares`，买入加滑点、卖出减滑点。

每个非零 Fill 单独计算：

```python
commission = max(gross_value * fee_schedule.commission_rate,
                 fee_schedule.minimum_commission)
stamp_tax = gross_value * fee_schedule.sell_stamp_tax if side == "sell" else 0.0
fees = commission + stamp_tax + gross_value * fee_schedule.transfer_fee_rate
```

- [ ] **Step 4: Run execution tests and confirm GREEN**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_execution.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit execution**

```powershell
git add -- skills/deep-analysis/scripts/lib/intraday/execution.py skills/deep-analysis/scripts/tests/test_intraday_execution.py
git commit -m "feat: simulate constrained intraday fills"
```

### Task 5: 账户状态机

**Files:**
- Create: `skills/deep-analysis/scripts/lib/intraday/portfolio.py`
- Test: `skills/deep-analysis/scripts/tests/test_intraday_portfolio.py`

**Interfaces:**
- Consumes: `Fill`, 每日候选和交易日历。
- Produces: `PortfolioConfig(initial_cash=10000.0, max_new_position=5000.0)`.
- Produces: `run_cash_account(signals, minute_loader, trading_days, config, fee_schedule, slippage_bps) -> BacktestLedger`.
- Produces: `run_notional_account(...) -> BacktestLedger`.
- `BacktestLedger` 包含 `orders, positions, daily_equity, rejected_signals` 四个 DataFrame。

- [ ] **Step 1: Write failing cash-account tests**

```python
def test_cash_account_rounds_down_and_never_goes_negative():
    ledger = run_cash_account(
        signals=one_signal(price=10.0),
        minute_loader=fixture_loader(),
        trading_days=["20260730", "20260731"],
        config=PortfolioConfig(initial_cash=10_000, max_new_position=5_000),
        fee_schedule=FeeSchedule(), slippage_bps=0,
    )
    assert ledger.orders.query("side == 'buy'")["shares"].sum() == 400
    assert ledger.daily_equity["cash"].min() >= 0


def test_failed_next_day_exit_keeps_position_and_blocks_used_cash():
    ledger = run_cash_account(
        signals=two_day_signals(),
        minute_loader=loader_with_next_day_limit_down_then_recovery(),
        trading_days=["20260730", "20260731", "20260803"],
        config=PortfolioConfig(), fee_schedule=FeeSchedule(), slippage_bps=0,
    )
    assert ledger.positions["holding_days"].max() == 2
    assert "insufficient_cash" in ledger.rejected_signals["reason"].tolist()
```

增加测试：停牌延期；部分成交；未成交买单不创建持仓；市值按当日最后可得真实价估值；
统一名义账户与现金账户使用同一执行器。

- [ ] **Step 2: Run portfolio tests and confirm RED**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_portfolio.py -q
```

Expected: missing portfolio module.

- [ ] **Step 3: Implement event-ordered state machine**

每日严格按以下顺序：

```text
1. 处理到期和延期持仓的 9:35–9:39 卖出；
2. 用卖出后的现金更新可用资金；
3. 14:20 读取当日候选；
4. 计算 floor(min(cash - estimated_fees, max_new_position) / price / 100) * 100；
5. 14:30–14:34 执行买入；
6. 记录未成交、拒绝原因、持仓和收盘权益。
```

所有状态变化只由 Fill 驱动；不得在无 Fill 时假设现金或持仓变化。

- [ ] **Step 4: Run portfolio tests and confirm GREEN**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_portfolio.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit portfolio**

```powershell
git add -- skills/deep-analysis/scripts/lib/intraday/portfolio.py skills/deep-analysis/scripts/tests/test_intraday_portfolio.py
git commit -m "feat: add realistic overnight portfolio ledger"
```

### Task 6: 样本切割、统计和市场状态

**Files:**
- Create: `skills/deep-analysis/scripts/lib/intraday/validation.py`
- Test: `skills/deep-analysis/scripts/tests/test_intraday_validation.py`

**Interfaces:**
- Produces: `split_trade_dates(dates, train=0.6, validation=0.2) -> DatasetSplit`.
- Produces: `block_bootstrap_mean(returns, *, block_size, samples, seed) -> ConfidenceInterval`.
- Produces: `compute_metrics(ledger) -> dict[str, float | int]`.
- Produces: `classify_market_states(index_daily) -> pd.DataFrame`.

- [ ] **Step 1: Write failing validation tests**

```python
def test_split_is_chronological_and_test_is_last_twenty_percent():
    split = split_trade_dates(pd.date_range("2026-01-01", periods=10, freq="B"))
    assert len(split.train) == 6
    assert len(split.validation) == 2
    assert len(split.test) == 2
    assert max(split.validation) < min(split.test)


def test_block_bootstrap_is_seeded_and_samples_contiguous_blocks():
    first = block_bootstrap_mean(pd.Series([1, -1, 1, -1]), block_size=2,
                                 samples=500, seed=42)
    second = block_bootstrap_mean(pd.Series([1, -1, 1, -1]), block_size=2,
                                  samples=500, seed=42)
    assert first == second
```

增加测试：Profit Factor 用总盈利/总亏损；最大回撤从连续权益曲线计算；
最差 5% 尾部损失；状态仅用 `T-1` 以前的指数数据和扩展历史波动分位；
非连续状态不拼接后计算回撤。

- [ ] **Step 2: Run validation tests and confirm RED**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_validation.py -q
```

Expected: missing validation module.

- [ ] **Step 3: Implement reproducible validation**

`block_bootstrap_mean` 使用 `numpy.random.default_rng(seed)`，每次随机选连续
`block_size` 日片段并循环拼接到原长度，以每日净收益为抽样单位。`compute_metrics`
输出规格中的毛/净收益、费用、滑点、净期望、Profit Factor、回撤、尾部损失、
胜率、盈亏均值、连续亏损、成交与延期统计。

- [ ] **Step 4: Run validation tests and confirm GREEN**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_validation.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit validation**

```powershell
git add -- skills/deep-analysis/scripts/lib/intraday/validation.py skills/deep-analysis/scripts/tests/test_intraday_validation.py
git commit -m "feat: add leakage-safe backtest validation"
```

### Task 7: 可恢复分钟归档与接口探测

**Files:**
- Create: `skills/deep-analysis/scripts/lib/intraday/archive.py`
- Create: `skills/deep-analysis/scripts/export_tushare_minutes.py`
- Test: `skills/deep-analysis/scripts/tests/test_tushare_minute_archive.py`

**Interfaces:**
- Consumes: `lib.tushare_bootstrap.ManifestStore` 和现有 Tushare provider。
- Produces: `MinuteProbeResult(api_name, status, time_label_semantics, volume_unit, amount_unit, row_limit, fields, reason)`.
- Produces: `probe_minute_api(pro, sample_code, trade_date) -> MinuteProbeResult`.
- Produces: `month_shards(codes, start_date, end_date) -> list[MinuteShard]`.
- Produces: `MinuteArchiveExporter.export(shards) -> dict[str, int]`.

- [ ] **Step 1: Write failing archive tests using fake provider**

```python
def test_probe_classifies_permission_denial_without_leaking_token(tmp_path):
    class Pro:
        def stk_mins(self, **kwargs):
            raise RuntimeError("permission denied for credential abc")
    result = probe_minute_api(Pro(), "000001.SZ", date(2026, 7, 30))
    assert result.status == "unsupported"
    assert "abc" not in json.dumps(asdict(result))


def test_full_row_limit_causes_shard_split_not_success(tmp_path):
    exporter = MinuteArchiveExporter(
        pro=provider_returning_exactly(8000),
        output_root=tmp_path, row_limit=8000, min_interval_seconds=0,
    )
    result = exporter.export([MinuteShard("000001.SZ", date(2026, 7, 1),
                                          date(2026, 7, 31))])
    assert result["split"] == 1
    assert not ManifestStore(tmp_path).is_complete(
        "stk_mins_1m", "000001_SZ__20260701_20260731")
```

增加测试：其他证券/越界日期拒绝；raw 与 Parquet 哈希写 manifest；成功恢复不请求；
全局限流器由多个 worker 共享；`unsupported` 和 `realtime_only` 写
`minute_probe_results.json`；任何落盘文本均不含环境 token。

- [ ] **Step 2: Run archive tests and confirm RED**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_tushare_minute_archive.py -q
```

Expected: missing archive module and CLI.

- [ ] **Step 3: Implement probe, shard splitting and persistence**

接口探测顺序固定为：

```text
1. stk_mins(ts_code, freq="1min", start_date, end_date)
2. 若方法不存在或明确不支持，再探测 rt_min_daily(ts_code)
3. stk_mins 成功才允许 historical；只有 rt_min_daily 成功记 realtime_only
4. 两者均拒绝记 unsupported
```

原始响应写 `raw/stk_mins_1m/<code>/<period>.jsonl.gz`，标准化后写
`normalized/stk_mins_1m/<code>/<period>.parquet`。先写临时文件、计算 SHA256，
再原子替换目标文件，最后 append success manifest。达到 `row_limit` 的分片先按
日期中点拆分，单日仍满行则记录失败，不标成功。

- [ ] **Step 4: Run archive tests and related manifest regressions**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_tushare_minute_archive.py skills/deep-analysis/scripts/tests/test_tushare_bootstrap.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit archive implementation**

```powershell
git add -- skills/deep-analysis/scripts/lib/intraday/archive.py skills/deep-analysis/scripts/export_tushare_minutes.py skills/deep-analysis/scripts/tests/test_tushare_minute_archive.py
git commit -m "feat: archive resumable minute shards"
```

### Task 8: 回测 CLI 与冻结实验

**Files:**
- Create: `skills/deep-analysis/scripts/backtest_overnight_intraday.py`
- Test: `skills/deep-analysis/scripts/tests/test_intraday_cli.py`

**Interfaces:**
- Consumes: 归档根目录、起止日期、滑点列表、实验目录。
- Produces: `experiment_config.json`, `data_inventory.json`, `signals.parquet`,
  `orders.parquet`, `daily_equity.parquet`, `metrics.json`, `report.md`。

- [ ] **Step 1: Write failing end-to-end fixture test**

```python
def test_cli_runs_fixture_experiment_and_freezes_test_result(tmp_path):
    archive = write_two_stock_three_day_fixture(tmp_path / "archive")
    experiment = tmp_path / "experiment"
    assert main([
        "--archive-root", str(archive),
        "--output", str(experiment),
        "--start-date", "20260727", "--end-date", "20260731",
        "--slippage-bps", "5,10,20", "--bootstrap-seed", "42",
    ]) == 0
    metrics = json.loads((experiment / "metrics.json").read_text("utf-8"))
    assert set(metrics["scenarios"]) == {"5", "10", "20"}
    assert metrics["test_run_count"] == 1
    assert (experiment / "report.md").exists()

    with pytest.raises(RuntimeError, match="frozen test already executed"):
        main(["--output", str(experiment), "--run-frozen-test"])
```

增加测试：缺分钟数据时退出码非零并生成 blocked inventory；输出配置含数据哈希；
报告区分统一名义与 1 万元账户；CLI 参数和日志不显示 token。

- [ ] **Step 2: Run CLI test and confirm RED**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_cli.py -q
```

Expected: missing CLI module.

- [ ] **Step 3: Implement experiment orchestration**

CLI 先验证归档覆盖和哈希，再构建点时股票池、复权分钟、固定信号，依次运行
5/10/20 bps 的统一名义与现金账户。训练/验证结果可重复运行；第一次运行冻结测试区时
在配置中写 `test_run_count=1` 和完成时间，后续拒绝覆盖。所有 JSON 使用排序键，
所有表按日期和代码稳定排序。

- [ ] **Step 4: Run CLI and complete intraday test suite**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_*.py skills/deep-analysis/scripts/tests/test_tushare_minute_archive.py -q
```

Expected: all intraday tests pass.

- [ ] **Step 5: Commit CLI**

```powershell
git add -- skills/deep-analysis/scripts/backtest_overnight_intraday.py skills/deep-analysis/scripts/tests/test_intraday_cli.py
git commit -m "feat: run frozen overnight experiments"
```

### Task 9: 在线探测、归档启动与最终验证

**Files:**
- Modify only if a test proves necessary: `skills/deep-analysis/scripts/lib/tushare_bootstrap.py`
- Create at runtime: `D:\work\gupiao\data\tushare_calendar\minute_probe_results.json`
- Create at runtime when supported: `D:\work\gupiao\data\tushare_calendar\raw\stk_mins_1m\...`
- Create at runtime when supported: `D:\work\gupiao\data\tushare_calendar\normalized\stk_mins_1m\...`

**Interfaces:**
- Consumes: completed/current week-card collector process state.
- Produces: audited probe result and either resumable archive progress or explicit blocked state.

- [ ] **Step 1: Verify no online collector is active**

Run:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'export_tushare_(bootstrap|mainbz|minutes)\.py' } |
  Select-Object ProcessId,CommandLine
```

Expected before probing: no active `export_tushare_bootstrap.py` or
`export_tushare_mainbz.py`. If one remains active, do not call the API and leave this task pending.

- [ ] **Step 2: Run one bounded permission/semantics probe**

Run:

```powershell
python skills/deep-analysis/scripts/export_tushare_minutes.py probe `
  --output-root D:\work\gupiao\data\tushare_calendar `
  --sample-code 000001.SZ `
  --trade-date 20260729 `
  --max-requests-per-minute 120
```

Expected: `minute_probe_results.json` has status `historical`, `realtime_only`, or
`unsupported`, plus fields, units, row limit and time-label semantics; console output contains no credential.

- [ ] **Step 3: Branch only on audited capability**

If status is `historical`, build the three-year point-in-time top-500 union from existing daily/status
archives and start:

```powershell
python skills/deep-analysis/scripts/export_tushare_minutes.py export `
  --output-root D:\work\gupiao\data\tushare_calendar `
  --start-date 20230801 --end-date 20260730 `
  --top-n 500 --workers 12 --max-requests-per-minute 120
```

If status is `realtime_only`, initialize only the daily simulation archive command and record historical
backtest as blocked. If status is `unsupported`, do not issue bulk requests and record the exact sanitized
provider reason.

- [ ] **Step 4: Run proportional verification**

Run:

```powershell
python -m pytest skills/deep-analysis/scripts/tests/test_intraday_*.py skills/deep-analysis/scripts/tests/test_tushare_minute_archive.py skills/deep-analysis/scripts/tests/test_tushare_bootstrap.py skills/deep-analysis/scripts/tests/test_kline_window_continuity.py skills/deep-analysis/scripts/tests/test_fetch_kline_contract.py -q
git diff --check
git status --short
```

Expected: all selected tests pass; no whitespace errors; status shows only known user changes plus the
task’s committed files and runtime data outside the repository.

- [ ] **Step 5: Generate inventory and handoff**

For historical support, report security count, requested/completed/failed shard counts, date coverage,
row counts, bytes and manifest location. For blocked states, report which capability failed and what can
still run locally. Do not claim a profitable strategy until frozen test results exist and pass the
predeclared statistical checks.
