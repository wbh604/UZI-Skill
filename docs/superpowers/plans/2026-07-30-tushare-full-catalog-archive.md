# Tushare 官方目录全量归档 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在周卡到期前，将官方目录中的股票数据、ETF专题、指数专题、公募基金、宏观经济和大模型语料全部登记，并将每个非分钟子接口归档为完整数据、合法空数据、实时增量、停更或明确不支持之一。

**Architecture:** 以官方文档目录生成不可遗漏的 API 注册表，每个接口先做一次权限、字段、日期归属和截断探测，再选择按证券、交易日、报告期、自然月或递归日期区间的最省请求分片。所有采集复用 append-only manifest、共享限流器和 raw/normalized 双层文件；实时接口只积累到期前快照，停更接口只探测一次，分钟接口按用户要求排除。

**Tech Stack:** Python 3.11、pandas、requests、BeautifulSoup、Tushare兼容HTTPS API、gzip JSONL/CSV、pytest、PowerShell进程监督。

## Global Constraints

- 在线采集固定 120 次/分钟，最多 12 workers，所有 worker 共享请求启动限流器。
- 当前在线采集进程退出前不得启动第二个会叠加限流的进程。
- 股票、ETF、指数及基金的历史目标口径为严格滚动十年：2016-07-30 至采集日。
- 宏观经济数据体量小，保存接口可返回的全部历史。
- 大模型语料默认保存2017-01-01至采集日；若接口可用且容量允许，再向更早历史扩展。
- 不采集股票、ETF、指数和申万的历史或实时分钟K线。
- 实时日线、实时参考、当日竞价等不能回补历史的接口标记 `incremental_only`，从启用日至周卡到期每天留存快照。
- 标记“停”的接口只做一次探测；成功则保存可返回历史，失败则记录 `stopped` 或 `unsupported`，不循环请求。
- 周线、月线、复权行情和技术因子优先保存官方接口响应；接口不支持时才从已归档基础数据本地派生，并标记 `derived_local`。
- 每个接口显式请求官方文档列出的全部输出字段，不能只依赖默认字段。
- Token只从现有环境加载器读取，禁止写入命令行、日志、manifest、探测结果或数据文件。
- 成功分片不重复请求；失败分片只在当前轮结束后重试；不得删除成功文件。
- 不修改无关未提交工作。

## Official Catalog Scope

本计划以2026-07-30官方文档导航为冻结目录。总计登记：

- 股票数据：107个直接API，加2个`pro_bar`派生入口；其中3个分钟API排除，
  106个进入归档、派生或分类。
- ETF专题：13个API，其中3个分钟API排除，10个进入归档或分类。
- 指数专题：20个API，其中3个分钟API排除，17个进入归档或分类。
- 公募基金：9个API，全部进入归档或分类。
- 宏观经济：19个API，全部进入归档或分类。
- 大模型语料：9个API，全部进入归档或分类。

冻结后新增的官方子栏目不会静默加入本轮；先写入 `catalog_changes.json`，由人工确认后进入新版本。

## Execution Priority

1. 完成当前 `fina_mainbz` 产品分片，并完成财务十年覆盖门禁。
2. 修复严格滚动十年日频边界和非默认点时字段。
3. 股票公司行为、交易状态、历史可交易性和宽基/行业点时成分。
4. ETF与指数全部非分钟数据。
5. 公募基金全部数据。
6. 宏观经济全部历史。
7. 股票特色、两融、资金流、打板和概念专题。
8. 大模型语料，按日期从新到旧归档。
9. 实时增量接口每日快照、失败重试和最终库存。

阶段只在所有接口均为 `complete`、`legitimate_empty`、`incremental_only`、
`derived_local`、`stopped` 或 `unsupported` 时结束。

---

### Task 1: 冻结官方目录和接口注册表

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tushare_catalog.py`
- Create: `skills/deep-analysis/scripts/tests/test_tushare_catalog.py`
- Create: `docs/data/tushare-catalog-2026-07-30.json`

**Interfaces:**
- Produces immutable `CatalogDataset`.
- Produces `CATALOG_DATASETS: tuple[CatalogDataset, ...]`.
- Produces `load_official_catalog_snapshot(path: Path) -> tuple[CatalogDataset, ...]`.

```python
@dataclass(frozen=True)
class CatalogDataset:
    category: str
    section: str
    title: str
    api_name: str
    doc_id: int
    mode: Literal["historical", "realtime", "stopped", "derived", "excluded_minute"]
    priority: int
    candidate_strategies: tuple[str, ...]
```

- [ ] **Step 1: Write the failing coverage test**

```python
def test_catalog_freezes_all_requested_subcolumns():
    from lib.tushare_catalog import CATALOG_DATASETS

    counts = Counter(item.category for item in CATALOG_DATASETS)
    assert counts == {
        "stock": 109,
        "etf": 13,
        "index": 20,
        "fund": 9,
        "macro": 19,
        "llm_corpus": 9,
    }
    excluded = {item.api_name for item in CATALOG_DATASETS
                if item.mode == "excluded_minute"}
    assert excluded == {
        "stk_mins", "rt_min", "rt_min_daily",
        "rt_etf_min", "rt_etf_min_daily", "etf_mins",
        "rt_idx_min", "idx_mins", "sw_mins",
    }
```

- [ ] **Step 2: Run the test and verify RED**

```powershell
D:\work\gupiao\.venv\Scripts\python.exe -m pytest skills/deep-analysis/scripts/tests/test_tushare_catalog.py -q
```

Expected: import fails because `lib.tushare_catalog` does not exist.

- [ ] **Step 3: Implement the frozen registry**

The registry must include every API listed in the appendices below, preserve document order, reject
duplicate `(category, api_name)`, and assign one of the five modes. Category/section header pages are
not datasets and do not count.

- [ ] **Step 4: Run the catalog test and save the snapshot**

```powershell
D:\work\gupiao\.venv\Scripts\python.exe -m pytest skills/deep-analysis/scripts/tests/test_tushare_catalog.py -q
```

Expected: PASS and the JSON snapshot contains 179 registered entries, including nine excluded minute APIs
and two locally materialized `pro_bar` entries.

### Task 2: Parse all official output fields and detect documentation changes

**Files:**
- Create: `skills/deep-analysis/scripts/snapshot_tushare_catalog.py`
- Modify: `skills/deep-analysis/scripts/lib/tushare_catalog.py`
- Test: `skills/deep-analysis/scripts/tests/test_tushare_catalog.py`

**Interfaces:**
- Produces `snapshot_catalog(session, datasets) -> CatalogSnapshot`.
- Writes `docs/data/tushare-catalog-2026-07-30.json`.
- Writes runtime `run_state/catalog_changes.json`.

- [ ] **Step 1: Write the failing field-extraction test**

```python
def test_document_parser_keeps_non_default_output_fields():
    html = fixture_document(
        api_name="disclosure_date",
        output_fields=[
            ("ts_code", "Y"), ("ann_date", "Y"), ("end_date", "Y"),
            ("modify_date", "N"),
        ],
    )
    parsed = parse_interface_document(html, doc_id=162)
    assert parsed.api_name == "disclosure_date"
    assert parsed.output_fields == (
        "ts_code", "ann_date", "end_date", "modify_date",
    )
```

- [ ] **Step 2: Run the test and verify RED**

```powershell
D:\work\gupiao\.venv\Scripts\python.exe -m pytest skills/deep-analysis/scripts/tests/test_tushare_catalog.py::test_document_parser_keeps_non_default_output_fields -q
```

Expected: missing parser.

- [ ] **Step 3: Implement document parsing and comparison**

For every frozen `doc_id`, parse API name, input fields, all output fields, stated limit, update
frequency and stopped status. Compare current official navigation with the frozen snapshot. New,
removed or renamed entries go to `catalog_changes.json`; they do not alter the active queue.

- [ ] **Step 4: Verify field completeness**

The test must assert `fina_indicator.update_flag` and `disclosure_date.modify_date` are present,
and that every historical dataset has at least one identity/date/output field.

### Task 3: Build one-request capability and shard-strategy probing

**Files:**
- Create: `skills/deep-analysis/scripts/lib/tushare_catalog_probe.py`
- Create: `skills/deep-analysis/scripts/tests/test_tushare_catalog_probe.py`

**Interfaces:**
- Produces `probe_catalog_dataset(pro, spec, context) -> ProbeResult`.
- Writes `run_state/catalog_probe_results.json`.

- [ ] **Step 1: Write failing probe tests**

```python
def test_probe_rejects_saturated_range_and_selects_smaller_shards():
    result = probe_catalog_dataset(
        provider_returning_exact_limit(100),
        fina_mainbz_spec(),
        sample_context(),
    )
    assert result.supported is True
    assert result.strategy == "security_report_period"
    assert result.rejected["security_year"] == "row_limit_saturated"


def test_realtime_api_is_not_treated_as_historical():
    result = probe_catalog_dataset(
        realtime_provider(),
        rt_etf_k_spec(),
        sample_context(),
    )
    assert result.status == "incremental_only"
```

- [ ] **Step 2: Run probe tests and verify RED**

```powershell
D:\work\gupiao\.venv\Scripts\python.exe -m pytest skills/deep-analysis/scripts/tests/test_tushare_catalog_probe.py -q
```

- [ ] **Step 3: Implement bounded probing**

Each active API gets at most one request per candidate strategy. Validate requested date/code ownership,
identity uniqueness, explicit output fields, empty policy and row-limit saturation. Candidate strategies
are attempted in this order when supported:

```text
static_snapshot
full_range
calendar_year
calendar_month
report_period
trade_date
security
security_year
security_report_period
recursive_date_range
```

Permission denial, invalid parameters and stopped endpoints are deterministic classifications; 429,
502 and timeout remain retryable and cannot classify an API as unsupported.

- [ ] **Step 4: Run tests and persist sanitized decisions**

Probe results may contain field names and non-secret parameters, but no token, authorization header or
environment value.

### Task 4: Generalize the resumable exporter

**Files:**
- Modify: `skills/deep-analysis/scripts/lib/tushare_bootstrap.py`
- Create: `skills/deep-analysis/scripts/export_tushare_catalog.py`
- Test: `skills/deep-analysis/scripts/tests/test_tushare_catalog_export.py`

**Interfaces:**
- Produces `export_catalog_dataset(spec, probe, context) -> ExportSummary`.
- CLI supports `--category`, `--section`, `--dataset`, `--probe-only`, `--retry-failed`.

- [ ] **Step 1: Write failing generic exporter tests**

Tests must prove:

- successful shards resume without provider calls;
- all explicit fields are passed;
- capped shards recursively split and are not marked complete;
- allowed empty shards are successful with `data_status=no_data`;
- other-date/code responses are rejected;
- raw and normalized hashes are recorded;
- all workers share a 0.5-second request-start interval;
- credentials are redacted from every failure string.

- [ ] **Step 2: Run tests and verify RED**

```powershell
D:\work\gupiao\.venv\Scripts\python.exe -m pytest skills/deep-analysis/scripts/tests/test_tushare_catalog_export.py -q
```

- [ ] **Step 3: Implement generic export**

Persist:

```text
raw/<api_name>/<shard_id>.jsonl.gz
normalized/<api_name>/<shard_id>.csv.gz
manifest.jsonl
```

Every success record includes API name, document ID, category, shard parameters without secrets,
row count, date boundaries, fetched time, source URL, raw hash and normalized hash.

- [ ] **Step 4: Run catalog and existing bootstrap regressions**

```powershell
D:\work\gupiao\.venv\Scripts\python.exe -m pytest skills/deep-analysis/scripts/tests/test_tushare_catalog_export.py skills/deep-analysis/scripts/tests/test_tushare_bootstrap.py -q
```

### Task 5: Complete core stock point-in-time data first

**Files:**
- Runtime only under `D:\work\gupiao\data\tushare_calendar`

- [ ] **Step 1: Finish current `fina_mainbz` product queue**

Keep yearly shards and split saturated years by report period. Do not launch a duplicate process.

- [ ] **Step 2: Repair the strict rolling-ten-year day boundary**

Backfill `daily`, `daily_basic`, `adj_factor`, `moneyflow_hsgt` from 2016-07-30 through 2016-12-31,
and append every newly closed trading day after the existing archive boundary.

- [ ] **Step 3: Repair non-default point-in-time fields**

Fetch `disclosure_date` by quarter with:

```text
fields=ts_code,ann_date,end_date,pre_date,actual_date,modify_date
```

Audit `fina_indicator` by report-year and preserve `update_flag`; re-request only shards whose current
projection or period coverage is incomplete.

- [ ] **Step 4: Pull corporate actions and tradability**

Archive `dividend`, `repurchase`, `share_float`, `stock_st`, `st`, `namechange`, `suspend_d`,
`stk_limit`, `stock_hsgt`, `stk_premarket`, `new_share`, `bak_basic`, `stk_shock`,
`stk_high_shock`, and `stk_alert`.

### Task 6: Archive ETF and index categories

**Files:**
- Runtime only under the archive root.

- [ ] **Step 1: ETF historical/static data**

Archive `etf_basic`, `etf_index`, `fund_daily`, `fund_adj`, `etf_share_size`, `etf_sh_cons`,
`etf_sz_cons`, and `idx_anns`.

- [ ] **Step 2: ETF realtime-only data**

Snapshot `rt_etf_k` and `rt_etf_sz_iopv` once per open trading day until expiry. Record all three ETF
minute APIs as `excluded_minute`.

- [ ] **Step 3: Index historical/static data**

Archive `index_basic`, `index_daily`, `index_weekly`, `index_monthly`, `index_weight`,
`index_dailybasic`, `index_classify`, `index_member_all`, `sw_daily`, `ci_index_member`,
`ci_daily`, `index_global`, `idx_factor_pro`, `daily_info`, and `sz_daily_info`.

- [ ] **Step 4: Index realtime-only data**

Snapshot `rt_idx_k` and `rt_sw_k` once per open trading day. Record `rt_idx_min`, `idx_mins`,
and `sw_mins` as `excluded_minute`.

### Task 7: Archive all public-fund and macroeconomic data

- [ ] **Step 1: Public funds**

Archive `fund_basic`, `fund_company`, `fund_manager`, `mkt_idx_bmk`, `fund_share`, `fund_nav`,
`fund_div`, `fund_portfolio`, and `fund_factor_pro`. Static masters are full snapshots; NAV and
factor data use fund/month shards; holdings use fund/report-period shards.

- [ ] **Step 2: Domestic macro**

Archive full available history for `cn_schedule`, `shibor`, `shibor_quote`, `shibor_lpr`, `hibor`,
`wz_index`, `gz_index`, `cn_gdp`, `cn_cpi`, `cn_ppi`, `cn_m`, `sf_month`, and `cn_pmi`.

- [ ] **Step 3: International macro**

Archive full available history for `libor`, `us_tycr`, `us_trycr`, `us_tbr`, `us_tltr`, and
`us_trltr`.

### Task 8: Archive remaining stock specialty sections

- [ ] **Step 1: Shareholders and reference data**

Archive `top10_holders`, `top10_floatholders`, `pledge_stat`, `pledge_detail`, `block_trade`,
`stk_account`, `stk_account_old`, `stk_holdernumber`, and `stk_holdertrade`. Stopped account APIs
receive one probe only.

- [ ] **Step 2: Specialty and institutional data**

Archive `report_rc`, `cyq_perf`, `cyq_chips`, `stk_factor`, `stk_factor_pro`, `ccass_hold`,
`ccass_hold_detail`, `hk_hold`, `stk_auction_o`, `stk_auction_c`, `stk_nineturn`,
`stk_ah_comparison`, `stk_surv`, and `broker_recommend`.

- [ ] **Step 3: Margin and securities lending**

Archive `margin`, `margin_detail`, `margin_secs`, `slb_len`; probe stopped `slb_sec`,
`slb_sec_detail`, and `slb_len_mm` once.

- [ ] **Step 4: Money flow**

Archive `moneyflow`, `moneyflow_ths`, `moneyflow_dc`, `moneyflow_cnt_ths`, `moneyflow_ind_ths`,
`moneyflow_ind_dc`, `moneyflow_mkt_dc`, and existing `moneyflow_hsgt`.

- [ ] **Step 5: Limit-board and concepts**

Archive `top_list`, `top_inst`, `limit_list_ths`, `limit_list_d`, `limit_step`,
`limit_cpt_list`, `ths_index`, `ths_daily`, `ths_member`, `dc_index`, `dc_member`,
`dc_daily`, `hm_list`, `hm_detail`, `ths_hot`, `dc_hot`, `tdx_index`, `tdx_member`,
`tdx_daily`, `kpl_list`, `kpl_concept_cons`, `dc_concept`, and `dc_concept_cons`.

- [ ] **Step 6: Realtime stock snapshots and locally derived helpers**

Snapshot `rt_k` and `stk_auction` until expiry. Store official outputs for `weekly`, `monthly`,
`stk_weekly_monthly`, `stk_week_month_adj`, and `bak_daily` when supported. Materialize the
non-direct `pro_bar`/复权行情 helper locally from `daily + adj_factor` with source metadata.

### Task 9: Archive all large-model corpora

- [ ] **Step 1: Structured policy and research corpora**

Archive `npr`, `research_report`, and `monetary_policy` using publication-month shards and all
returned metadata/content fields.

- [ ] **Step 2: News corpora**

Archive `news`, `major_news`, and `cctv_news` from newest to oldest using day shards. A full day at
the documented/provider row cap recursively splits by source or smaller time interval.

- [ ] **Step 3: Company announcements and Q&A**

Archive `anns_d`, `irm_qa_sh`, and `irm_qa_sz` using trade-date/month shards. Persist the exact API
response content and returned document URLs; do not crawl unrelated external websites.

- [ ] **Step 4: Corpus quality gate**

Reject duplicate stable IDs, dates outside the shard, empty bodies where the interface promises
content, and silently truncated cap-sized shards. Record text bytes, metadata rows and date coverage.

### Task 10: Final inventory and completion gate

**Files:**
- Create: `skills/deep-analysis/scripts/validate_tushare_catalog.py`
- Test: `skills/deep-analysis/scripts/tests/test_tushare_catalog_validation.py`
- Create: `docs/data/tushare-full-catalog-inventory.md`

- [ ] **Step 1: Validate latest status per dataset/shard**

The validator uses the latest manifest row for each key, verifies artifacts and hashes, and reports
expected/success/failed/pending/zero-row counts.

- [ ] **Step 2: Enforce category completion**

Every one of the 179 registered entries must appear exactly once in final classification. The nine
minute APIs must be `excluded_minute`; no other API may silently disappear.

- [ ] **Step 3: Retry only unresolved supported shards**

Run one exporter at 120 requests/minute and 12 workers. Deterministic permission/parameter failures
become `unsupported`; transient failures remain retryable.

- [ ] **Step 4: Produce final inventory**

For each API report title, doc ID, selected strategy, requested/actual boundaries, files, rows, bytes,
hash status, source, fetch times and final classification.

## Appendix A: Frozen Stock APIs

```text
stock_basic, stk_premarket, trade_cal, stock_st, st, stock_hsgt, namechange,
stock_company, stk_managers, stk_rewards, bse_mapping, new_share, bak_basic,
daily, rt_k, stk_mins, rt_min, rt_min_daily, weekly, monthly, pro_bar,
pro_bar_adj,
stk_weekly_monthly, stk_week_month_adj, adj_factor, daily_basic, stk_limit,
suspend_d, hsgt_top10, ggt_top10, ggt_daily, bak_daily,
income, balancesheet, cashflow, forecast, express, dividend, fina_indicator,
fina_audit, fina_mainbz, disclosure_date,
stk_shock, stk_high_shock, stk_alert, top10_holders, top10_floatholders,
pledge_stat, pledge_detail, repurchase, share_float, block_trade, stk_account,
stk_account_old, stk_holdernumber, stk_holdertrade,
report_rc, cyq_perf, cyq_chips, stk_factor, stk_factor_pro, ccass_hold,
ccass_hold_detail, hk_hold, stk_auction_o, stk_auction_c, stk_nineturn,
stk_ah_comparison, stk_surv, broker_recommend,
margin, margin_detail, margin_secs, slb_sec, slb_len, slb_sec_detail, slb_len_mm,
moneyflow, moneyflow_ths, moneyflow_dc, moneyflow_cnt_ths, moneyflow_ind_ths,
moneyflow_ind_dc, moneyflow_mkt_dc, moneyflow_hsgt,
top_list, top_inst, limit_list_ths, limit_list_d, limit_step, limit_cpt_list,
ths_index, ths_daily, ths_member, dc_index, dc_member, dc_daily, stk_auction,
hm_list, hm_detail, ths_hot, dc_hot, tdx_index, tdx_member, tdx_daily,
kpl_list, kpl_concept_cons, dc_concept, dc_concept_cons
```

## Appendix B: Frozen ETF, Index, Fund, Macro and Corpus APIs

```text
ETF:
etf_basic, etf_index, rt_etf_min, rt_etf_min_daily, etf_mins, rt_etf_k,
fund_daily, fund_adj, etf_share_size, etf_sh_cons, etf_sz_cons,
rt_etf_sz_iopv, idx_anns

Index:
index_basic, index_daily, rt_idx_k, rt_idx_min, index_weekly, idx_mins,
index_monthly, index_weight, index_dailybasic, index_classify,
index_member_all, sw_daily, rt_sw_k, sw_mins, ci_index_member, ci_daily,
index_global, idx_factor_pro, daily_info, sz_daily_info

Public fund:
fund_basic, fund_company, fund_manager, mkt_idx_bmk, fund_share, fund_nav,
fund_div, fund_portfolio, fund_factor_pro

Macro:
cn_schedule, shibor, shibor_quote, shibor_lpr, libor, hibor, wz_index,
gz_index, cn_gdp, cn_cpi, cn_ppi, cn_m, sf_month, cn_pmi, us_tycr,
us_trycr, us_tbr, us_tltr, us_trltr

Large-model corpus:
npr, research_report, monetary_policy, news, major_news, cctv_news, anns_d,
irm_qa_sh, irm_qa_sz
```

## Success Criteria

- 179 official entries are registered and none are omitted，包含107个股票直接API以及
  `pro_bar`、`pro_bar_adj`两个派生入口。
- Nine minute APIs are explicitly excluded and no minute requests are sent.
- Every other API ends in a documented final classification.
- All supported historical interfaces satisfy the requested date coverage without capped shards.
- All explicit non-default output fields are retained.
- Realtime-only interfaces have daily snapshots from activation through subscription expiry.
- No completed shard is requested twice.
- No credential appears in commands, logs, manifests, probe results or data.
- Final inventory distinguishes complete, legitimate empty, incremental-only, derived-local, stopped,
  unsupported, failed and pending states.
