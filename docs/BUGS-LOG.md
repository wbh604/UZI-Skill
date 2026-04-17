# BUGS-LOG · 防回归记录

每个 bug 修完都登记到这里。**未来改这些代码区域时，必须回看本文件确保不引入回归。**
对应单元测试在 `skills/deep-analysis/scripts/tests/test_no_regressions.py`。

---

## v2.7.1 (2026-04-17 hotfix)

### BUG#R5 · 19_contests xueqiu_cubes 全空（XueQiu 登录政策变化）
- **症状**：实盘比赛维度始终 0 个 cube，无任何雪球组合显示
- **根因**：`xueqiu.com/cubes/cubes_search.json` 2026 年起强制登录，HTTP 直访
  返 `400 + error_code: "400016"`（"遇到错误，请刷新页面或者重新登录"）
- **修法**：
  - 新 `lib/xueqiu_browser.py` Playwright + 持久化 cookie
  - `fetch_contests` HTTP fail → 检查 UZI_XQ_LOGIN → Playwright fallback
  - 未登录 → 透明标 `_login_required: True` + commentary 显示"⚠️ XueQiu 需登录"
  - run.py 加 `--enable-xueqiu-login` flag，README 说明登录步骤
- **回归测试**：`test_no_regressions.py::test_contests_login_required_marked`
- **若未来改 fetch_contests**：必须保留 `xueqiu_meta.login_required` 标记

### BUG#R6 · 18_trap signals 全 0（ddgs cache 残留）
- **症状**：杀猪盘 8 信号扫描永远命中 0/8（`signals_hit_count: 0`）
- **根因**：v2.6.1 之前 ddgs 未装时 `_ddg_search` 返 [] 被 cache 缓存了 12h；
  装 ddgs 后 cache 仍有效 → 永远返空
- **修法**：清 `.cache/_global/api_cache/ws__*.json` cache（一次性）
  + 改 `_auto_summarize_dim` 让 18_trap 显示 "已扫 ddgs 24 条搜索结果" 透明状态
- **若未来 lib/web_search 改依赖**：必须 bump cache_key_prefix 强制失效

---

## v2.7.0 (2026-04-17)

### BUG#R1 · `detect_style` 漏掉负 ROE 的困境股
- **症状**：ST 股（roe_5y_min < 0）被错判为 `small_speculative`（小盘投机），不是 `distressed`（困境反转）
- **位置**：`lib/stock_style.py:detect_style` 第 1 个判定分支
- **根因**：旧条件 `0 < roe_5y_min < 5` 排除了负值
- **修法**：改为 `roe_5y_min < 5`（去掉下界，允许负值）
- **回归测试**：`test_no_regressions.py::test_distressed_negative_roe`
- **若未来改 detect_style**：必须保留"负 ROE 也是困境"逻辑

### BUG#R2 · `fund_managers` 只显示 6 个（v2.4 修复后又出现的"假回归"）
- **症状**：报告里只显示 6 个基金经理，即便股票被几百家基金持有
- **位置**：`run_real_test.py:_fund_holders` 函数（wave3）
- **根因**：v2.4 把 `fetch_fund_holders.main()` 默认 limit 改成 None，但调用方
  `run_real_test.py:264` 一直写死 `limit=6` —— 修改 fetcher 默认值不会影响显式传参
- **修法**：把 `limit=6` 改为 `limit=None`
- **回归测试**：`test_no_regressions.py::test_fund_managers_no_cap`
- **若未来改 wave3 fetcher**：默认 limit 必须保持 None，render 端已支持 >6 紧凑展开

### BUG#R4 · fetch_fund_holders 并行调 akshare 触发 mini_racer V8 crash
- **症状**：Py3.13 macOS 跑 `fetch_fund_holders.main()` 默认 workers=3 → 致命 crash
  `Check failed: !pool->IsInitialized()`
- **根因**：v2.6 给 `_MINI_RACER_FETCHERS` 加了锁，但 fetch_fund_holders 不在
  wave2 列表里（它是 wave3 + 内部自己开 ThreadPoolExecutor）。其内部并行调
  `ak.fund_open_fund_info_em` 触发 mini_racer 同样问题。
- **修法**：fetch_fund_holders 默认 `UZI_FUND_WORKERS=1`（serial）；同样修
  `lib/quant_signal.py` 内部并发 → 默认 `UZI_QUANT_WORKERS=1`
- **若未来引入新模块调 akshare fund/portfolio 接口**：必须 default workers=1，
  或显式 import `_MINI_RACER_LOCK`

### BUG#R3 · 数据缺口 agent 没主动补齐就出报告
- **症状**：stage2 完成后直接发链接给用户，没检查 22 维定性 commentary 是否完整
- **位置**：原 SKILL.md 没有"输出前最后核查" 的 HARD-GATE
- **根因**：HARD-GATE-DATAGAPS 要求 agent 补数据，但没说"最后还要再核一遍"
- **修法**：新增 HARD-GATE-FINAL-CHECK，强制 agent 在发链接前打开 synthesis.json
  + raw_data.json 检查覆盖率 / commentary 完整性 / detected_style 合理性
- **若未来改 SKILL.md**：必须保留 FINAL-CHECK 这一节

---

## v2.6.1 (2026-04-17 hotfix)

### BUG · 直跑模式定性维度全空
- **症状**：浙江东方报告里宏观/政策/原材料/期货/事件 5 维 missing
- **根因 1**：`dim_commentary` 的 `dim_labels` 只覆盖 9/22 维
- **根因 2**：fallback 是 "[脚本占位]" 废话
- **根因 3**：`ddgs` 不在 requirements.txt（lib/web_search 静默返 0）
- **修法**：`_auto_summarize_dim` 全 22 维 + `_autofill_qualitative_via_mx` MX/ddgs 兜底 + 加 ddgs 到 requirements.txt
- **回归测试**：`test_no_regressions.py::test_22_dims_all_have_commentary`

---

## v2.6.0 (2026-04-17)

### BUG · KeyError 'skip'（论坛 #2）
- **位置**：`preview_with_mock.py:322`
- **根因**：`sig_dist = {"bullish": 0, "neutral": 0, "bearish": 0}` 漏 'skip' key
- **修法**：加 'skip' + 用 `.get()` 防御
- **回归测试**：`test_no_regressions.py::test_sig_dist_has_skip_key`

### BUG · per-fetcher hang 导致 pipeline 卡死（论坛 #11）
- **位置**：`run_real_test.py:collect_raw_data` ThreadPoolExecutor
- **根因**：`as_completed()` 没 timeout，单 fetcher 网络 hang 卡死整个流水线
- **修法**：`as_completed(futures, timeout=300)` + `fut.result(timeout=90)` + 长尾 fetcher 例外
- **若未来改 collect_raw_data**：必须保持双层 timeout

### BUG · OpenCode 跑到 60% 停止不能续（论坛 #9）
- **修法**：`collect_raw_data(resume=True)` 默认 + 增量保存 + `--no-resume` flag
- **若未来改 stage1**：resume 默认必须 True

### BUG · Python 3.9 `str | None` 语法报错（Codex blocker A）
- **修法**：所有新 .py 文件加 `from __future__ import annotations`
- **回归测试**：`test_no_regressions.py::test_all_modules_import_on_py39`

### BUG · mini_racer V8 thread crash on A 股（Codex blocker B）
- **位置**：`run_real_test.py:run_fetcher`
- **根因**：akshare 的 stock_industry_pe / stock_individual_fund_flow / stock_a_pe_and_pb
  内部用 mini_racer 解 JS 反爬，V8 isolate 不是 thread-safe
- **修法**：`_MINI_RACER_LOCK` 串行化这 3 个 fetcher
- **若未来加新 fetcher**：若它调用 mini_racer 相关 akshare 函数，必须加进 `_MINI_RACER_FETCHERS`

### BUG · 报告 banner 显示 v2.2（Codex blocker C）
- **修法**：`run.py:_get_version()` + `assemble_report.py:_get_plugin_version()` 动态读 plugin.json
- **若未来 bump 版本号**：只改 plugin.json 即可，banner 自动同步

### BUG · render_share_card / render_war_report 缺 main()（Codex blocker E）
- **修法**：`main = render` alias
- **若未来重命名函数**：必须保留 main alias

---

## v2.5.0 (2026-04-17)

### BUG · 港股 11 个 dim 全是 A-only stub
- **修法**：`lib/hk_data_sources.py` 解锁 50+ akshare HK 函数；HK 5 维（basic / peers / capital_flow / events + 原 kline）真实数据
- **若未来改 fetch_*.py**：HK 分支必须独立 try/except，不能让 HK 错误污染 A 股链路

---

## v2.4.0 (2026-04-17)

### BUG · 大佬抓作业 limit=50 截断
- **修法**：`fetch_fund_holders.main(limit=None)` 默认改无上限
- **回归**：v2.7 又因 wave3 调用层写死 `limit=6` 部分回归 → BUG#R2

### BUG · 6 维定性维度无方法论指引
- **修法**：`task2.5-qualitative-deep-dive.md` (~400 行) + HARD-GATE-QUALITATIVE
- **若未来改 SKILL.md**：必须保留 HARD-GATE-QUALITATIVE

### BUG · pip 直接挂掉无国内镜像 fallback
- **修法**：`run.py:check_dependencies` 4 级镜像 fallback
- **若未来改 dependencies**：保持 4 级 fallback 链

---

## v2.3.0 (2026-04-17)

### BUG · 中文名输错（"北部港湾" vs "北部湾港"）解析挂掉、22 fetcher 全炸
- **修法**：`lib/name_matcher.py` Levenshtein + `lib/mx_api.py` MX NLP 三层 fallback
- **若未来改 fetch_basic.py**：name_resolver 必须返回结构化 error，不能 fallback 当 ticker 用

### BUG · 关键字段缺失时 pipeline 不 abort 也不警示
- **修法**：`data_integrity.generate_recovery_tasks` + `_data_gaps.json` + HTML 橙色 banner
- **回归测试**：`test_no_regressions.py::test_data_gaps_banner_renders`

---

## 通用 Don't 清单（任何改动都不能违反）

1. ❌ `sig_dist` 字典少 `skip` key
2. ❌ `as_completed()` 不带 timeout
3. ❌ ThreadPoolExecutor 跑 mini_racer-using fetcher 不加锁
4. ❌ 改 fetcher 默认参数后忘记同步调用层
5. ❌ 加 fund 持仓数据流时硬编码 limit
6. ❌ `dim_commentary` 用 "[脚本占位]" 字符串而不是 raw_data 综合
7. ❌ 写 .py 文件用 `str | None` syntax 但忘 `from __future__ import annotations`
8. ❌ `run.py` banner 硬编码版本号
9. ❌ `lib/web_search` 改用其他依赖但不更新 requirements.txt
10. ❌ 把第一次 stage2 输出当最终报告（必须 agent FINAL-CHECK）

## 流程要求

- 每改 `lib/stock_style.py` 必须跑 `test_no_regressions.py::test_*_style*`
- 每改 `run_real_test.py` 必须跑 `test_no_regressions.py` 全套
- 每改 `lib/data_sources.py` `_fetch_basic_*` 必须 smoke test 三市场
- bump 版本号时 4 个 manifest（`.claude-plugin/`、`.cursor-plugin/`、`package.json`、`.version-bump.json`）必须同步
