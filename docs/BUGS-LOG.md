# BUGS-LOG · 防回归记录

每个 bug 修完都登记到这里。**未来改这些代码区域时，必须回看本文件确保不引入回归。**
对应单元测试在 `skills/deep-analysis/scripts/tests/test_no_regressions.py` + `tests/test_v2_10_4_fixes.py`。

**登记规范**：每个条目必须含 症状 / 位置 / 根因 / 影响 / 修法 / 验证 / 回归测试 / "未来改该区域注意事项"

---

## v2.10.7 (2026-04-18 · Codex 整体审查发现执行链路 3 处)

### BUG · `raw["market"]` 硬编 "A" 污染 HK/US 路径
- **症状**：`python run.py 00700.HK --depth lite` Self-Review 显示 `(A)`，应为 `(H)`；后续市场分支判断全错
- **位置**：`skills/deep-analysis/scripts/run_real_test.py::collect_raw_data` 入口 + post-fetch_basic 回填逻辑
- **根因**：
  1. 初始化时硬编码 `raw["market"] = "A"`
  2. post-fetch_basic 回填只在 `resolved_ticker != ticker` 分支里触发（用户直接输入 `00700.HK` 时 resolved == input，不触发）
  3. 回填读的是 `dims["0_basic"].get("data", {}).get("market", "A")`，但 fetch_basic 实际把 market 放在**顶层**（见 fetch_basic.py:80 `"market": ti.market`），不在 `.data` 里
- **影响**：所有 HK/US 直输 + 所有 resume cache 走 raw 的场景，`raw.market` 都被污染为 A
- **修法**：
  1. 入口用 `parse_ticker(ticker).market` 预填（非中文名即可拿到 H/U）
  2. post-fetch_basic 改为**无条件**从 `dims["0_basic"].get("market")` 顶层回填
  3. resume 从 cache 复用时也回填 `raw["market"]`
- **验证**：`python run.py 00700.HK --depth lite` Self-Review 显示 `(H)` ✅
- **回归测试**：`test_v2_10_4_fixes.py::test_raw_market_initialized_from_parse_ticker`
- **若未来改 collect_raw_data**：不能把 market 硬编码回 "A"；不能把顶层 market 改回读 `.data.market`；新增 resume 路径必须同步回填 market

### BUG · `resume` cache 对别名输入失效
- **症状**：用户用中文名 "贵州茅台" 或三位港股 "700" 输入时，`.cache/600519.SH/raw_data.json` 已存在也不命中缓存，重跑 Stage 1 耗时 + token 双爆
- **位置**：`run_real_test.py::collect_raw_data` 的 resume cache 加载块（line ~107-114）
- **根因**：注释写"尝试用原始 ticker 和 resolved ticker 都查"，实际只 `_read_cache(ticker, "raw_data")` 调了一次，发生在 fetch_basic 解析之前
- **影响**：别名输入下 resume 形同虚设；Codex 等 agent 环境反复耗 token 重跑
- **修法**：双重查询——先 `_read_cache(ticker)` 原样查；未命中 + 非中文名则 `_read_cache(parse_ticker(ticker).full)` 兜底
- **验证**：`python run.py 00700.HK`（cache 存在）→ 命中 15/15 维
- **回归测试**：`test_v2_10_4_fixes.py::test_resume_cache_tries_resolved_ticker`
- **若未来改 resume 路径**：不能移除 `parse_ticker.full` 兜底查询；中文名输入走 fetch_basic resolver 不在 resume 范畴内

### BUG · AGENTS.md 强制全量 agent 流程 · 抵消 CLI/lite 降载设计
- **症状**：v2.10.4/5 已把 `agent_analysis.json` 缺失降 warning 允许 CLI 直跑出报告，但 AGENTS.md 仍让 agent 看到"分析 XXX"就无条件 role-play 51 评委 + 写 agent_analysis.json，token 浪费
- **位置**：`AGENTS.md` Step 1-5 + `CLAUDE.md` "工作流" 段落
- **根因**：v2.10.4/5 是代码侧改，文档没同步更新
- **修法**：加"深浅两路径"决策树：
  - 快速路径（默认）：`python3 run.py <ticker> --depth lite/medium --no-browser` → 30s-4min 出完整报告，**不需要** role-play
  - 深度路径：仅当用户明确要 DCF / IC memo / 首次覆盖等深度产物时走两段式
- **若未来改 agent 流程**：run.py 的 CLI 直跑路径必须保持"缺 agent_analysis.json 降 warning 继续出 HTML"；文档里必须保留深浅两路径说明

---

## v2.10.5 (2026-04-18 · v2.10.4 遗漏补丁)

### BUG · `check_coverage_threshold` 非 profile-aware 阻塞 lite 出报告
- **症状**：`python run.py 600519.SH --depth lite --no-browser` 跑出 `coverage=17% (3/18)` → critical → `RuntimeError: BLOCKED by self-review`，HTML 生成失败
- **位置**：`skills/deep-analysis/scripts/lib/self_review.py::check_coverage_threshold:254`
- **根因**：分母用全 18 项 `CRITICAL_CHECKS`，lite 只启用 7 维，结构性偏低；CLI 直跑模式又没 agent 可补数据，critical 把流程卡死
- **影响**：任何 lite 模式 + 网络稍差的组合 → 报告 block
- **修法**：
  1. Profile-aware 分母：只算 `profile.fetchers_enabled` 里的 CRITICAL_CHECKS 项
  2. CLI-only/lite 模式下 `< 40%` 的 critical 降为 warning（允许继续出 HTML 供参考）
- **验证**：600519.SH lite → `critical=0 warning=2`，HTML 生成 ✅
- **回归测试**：
  - `test_v2_10_4_fixes.py::test_coverage_critical_downgrades_in_lite`
  - `test_v2_10_4_fixes.py::test_coverage_critical_preserved_in_medium`（回归护栏 · medium 仍 critical）
  - `test_v2_10_4_fixes.py::test_coverage_profile_aware_denominator`
- **若未来改 self_review**：分母必须读 profile，不能退回硬编码 18；CLI 模式下 critical 降级逻辑不能删

### BUG · `run.py` 直跑模式未自动标记 UZI_CLI_ONLY
- **症状**：`python run.py 002273.SZ --depth medium` → `agent_analysis` 缺失仍 critical → block HTML
- **位置**：`run.py::main()` 环境变量设置区
- **根因**：CLI 降级逻辑依赖 `UZI_DEPTH=lite / UZI_LITE=1 / UZI_CLI_ONLY=1 / CI=true` 四个信号；medium 模式都不命中
- **修法**：run.py main() 开头加 `os.environ.setdefault("UZI_CLI_ONLY", "1")` — run.py 是 CLI 直跑入口（agent 流程走 stage1/stage2 直接调用，不经 run.py）
- **验证**：002273.SZ medium → HTML 生成 ✅
- **回归测试**：`test_v2_10_4_fixes.py::test_run_py_sets_cli_only_env`
- **若未来改 run.py**：不能删 UZI_CLI_ONLY=1 setdefault；若新增 agent 专用入口必须另设标志区分

### BUG · `render_fund_managers` None 字段 TypeError
- **症状**：`TypeError: '>' not supported between instances of 'NoneType' and 'int'` in `assemble_report.py:1844`
- **位置**：`skills/deep-analysis/scripts/assemble_report.py::render_fund_managers`（5 处字段）
- **根因**：v2.10.2 fund_holders 双层策略（Top N full + rest lite）下，rest lite 基金的 `return_5y/annualized_5y/max_drawdown/sharpe/peer_rank_pct` 为 **显式 None**，但 `m.get("return_5y", 0)` 只处理 key 缺失、不处理值为 None
- **影响**：所有 lite + fund holders ≥ N+1 的场景 → 报告组装崩溃
- **修法**：`m.get("return_5y") or 0` 统一兜底（既处理缺失又处理 None）
- **验证**：`run.py 002273.SZ --depth medium` 正常生成 HTML
- **若未来改 fund_holders schema**：数值字段保持"None = 未计算"语义；新增数值字段 render 时必须用 `or 0` 不能用 `.get(k, 0)`

---

## v2.10.4 (2026-04-17 · Codex 测试反馈 3 bug)

### BUG · lite 模式与 self-review 冲突（9 critical 误报）
- **症状**：`UZI_DEPTH=lite` 跑完 gate 报 9 个 critical（维度缺失、data 为空）
- **位置**：`lib/self_review.py::check_all_dims_exist` + `::check_empty_dims`
- **根因**：硬编码检查全 20 维，不看 profile；lite 只启用 7 维，其余 13 维被误报 critical
- **修法**：两函数都读 `analysis_profile.get_profile().fetchers_enabled`，只检查启用的维度
- **回归测试**：
  - `test_check_all_dims_lite_respects_profile`
  - `test_check_empty_dims_lite_respects_profile`
  - `test_check_all_dims_medium_still_reports_missing`（护栏）
- **若未来加 self-review check**：新 check 涉及维度遍历必须 profile-aware

### BUG · agent_analysis.json 缺失在 CLI 直跑误报 critical
- **症状**：`python run.py` 直跑（无 agent 介入）必定 critical 阻止 HTML
- **位置**：`lib/self_review.py::check_agent_analysis_exists`
- **修法**：`UZI_DEPTH=lite / UZI_LITE=1 / UZI_CLI_ONLY=1 / CI=true` 任一命中 → 降 warning
- **回归测试**：`test_agent_analysis_missing_downgrades_in_lite` + `test_agent_analysis_missing_critical_in_medium`（护栏）
- **若未来改：** 正常两段式流程 agent_analysis 缺失仍是 critical，不能一刀切降级

### BUG · ETF 早退 RuntimeError（stage1 已识别非股，stage2 仍被调用）
- **症状**：`python run.py 512400.SH` → stage1 写 `_resolve_error.json` 识别为 ETF，但 `run_real_test.main()` 仍调 stage2 → `RuntimeError: Stage 2 缺少数据`
- **位置**：`run_real_test.py::main()` + `run.py::main()` 两处
- **修法**：
  1. `run_real_test.main()` 加 `status == "non_stock_security"` 分支，跳过 stage2 并 return
  2. `run.py::main()` 捕获 `run_analysis()` 返回的 `non_stock_security` dict，打印成分股提示后 `sys.exit(0)`
  3. 中文名输入路径同样捕获
- **回归测试**：`test_main_returns_early_on_non_stock_security` + `test_main_returns_early_on_name_not_resolved`
- **若未来加新的"非个股"类别**：早退 status 加到 `main()` 的分支列表里，不要让 stage2 被白白调用

---

## v2.8.3 (2026-04-17 critical · 行业分类碰撞错误)

### BUG#R10 · 申万行业被误映射到证监会"农副食品加工业"（严重）
- **症状**：用户分析云铝股份（000807.SZ），属于工业金属铝行业，但报告里 `7_industry` / `10_valuation` 两维都把它归类为**农副食品加工**
- **位置**：`fetch_industry.py::_cninfo_industry_metrics:90` + `fetch_valuation.py:122`
- **根因**：两处都用 `df["行业名称"].str.contains(industry_name[:2])` 做 fuzzy 匹配。证监会行业分类里含"工业"子串的有 4 个行业，其中农副食品加工业排第一，`iloc[0]` 盲选它
- **影响面**：所有带"工业 / 加工 / 制造"字样的申万行业（工业金属/工业母机/工业机械/工业气体 etc）全受影响；报告的 industry_pe、公司数量、行业景气度文本全是错的
- **修法**：新 `lib/industry_mapping.py`：
  1. `SW_TO_CSRC_INDUSTRY` 134 条申万 → 证监会硬映射
  2. `HIGH_COLLISION_TOKENS` 黑名单 12 个通用前缀
  3. `resolve_csrc_industry()` 4 策略解析：硬映射 → 整名子串 → 去前缀 fuzzy → 返 None
  4. **绝不再盲选 `iloc[0]`**，匹配不到明确返 None
- **验证**：云铝股份 → 工业金属 → 有色金属冶炼和压延加工业 PE 32.97 ✓
- **回归测试**：
  - `test_industry_mapping_blocks_high_collision_substring`
  - `test_resolve_csrc_industry_on_mock_df`（mock 6 个证监会行业，用工业金属查询必须选到有色金属加工业不能选到农副食品）
  - `test_fetch_industry_and_fetch_valuation_use_mapping`
- **若未来改 fetcher**：`resolve_csrc_industry` 是 single source of truth，不许退回裸 `str.contains(ind[:2])` pattern
- **若未来加新申万行业**：优先加到 SW_TO_CSRC_INDUSTRY 硬映射；不行再靠 fallback，不要用 iloc[0] 盲选

---

## v2.8.1 (2026-04-17 quotes expansion · 海外人物真实原话)

### 增强 · quotes-knowledge-base.md 补齐 22 位海外代表人物
- **动机**：v2.8.0 做完 investor_profile 后发现 quotes-knowledge-base（agent 必读语料）只覆盖中国投资者，海外 20+ 人物原话空白。用户："还有很多你要去找他们的言论，去找一下，收集一下"
- **方法**：4 个并行 research agent 按流派取证；严格要求真实可验证、不 fabricate
- **产出**：KB 306 → 639 行；人物 23 → 45；每人 3-5 条带 URL 原话
- **溯源标准**：优先原版书（Principles / Margin of Safety / One Up on Wall Street / Zero to One / Reminiscences）、官方年报（berkshirehathaway.com / oaktreecapital.com / ARK）、经过验证的 Goodreads / Farnam Street / 雪球 / WSJ / CNBC
- **发现的副作用**：`chengdu` 被写进 PROFILES 但 KB 把它归类为"席位集合体·无个人原话" → 移出 PROFILES 走 group F fallback（席位集合体不应冒充个人人物）
- **回归测试**：
  - `test_quotes_knowledge_base_covers_authored_personas`（每个 authored 必须在 KB 有段落）
  - `test_quotes_knowledge_base_has_source_urls`（抽查必须带 URL）
- **若未来改 investor_profile**：新增 authored 人物必须同步加 KB 段落，否则测试 fail
- **若未来改 KB**：不能删海外人物 URL（下游 agent 依赖可点击溯源）

---

## v2.8.0 (2026-04-17 persona profile · 因地制宜)

### 增强 · 每个评委用自己方法论回答 3 个问题
- **动机**：Codex 建议把评审升级成"流派 + 人物 + agent 写回"。实地审计发现这些 80% 已有；真正缺的是每个评委的 `time_horizon` / `position_sizing` / `what_would_change_my_mind`
- **关键原则**：**不是给所有人加 3 个同样的字段**，而是每人按自己方法论填 authentic 内容（Buffett 10 年 vs 赵老哥 T+2 vs Simons <2 天）
- **已落地**：`lib/investor_profile.py` 22 人手写 + 7 群 fallback
- **接入**：evaluator.evaluate / _skip_result / _unknown_result 三处返回 · generate_panel 写入 panel.json · assemble_report 新增「🧭 我的方法论」UI 区块
- **回归测试**：
  - `test_investor_profile_authentic_per_persona`（buffett/zhao_lg/simons 必须体现差异）
  - `test_investor_profile_group_fallback`（未注册投资者走 group fallback）
  - `test_evaluator_carries_profile_fields`
  - `test_panel_carries_profile_fields`
- **若未来加/改投资者**：不能把 authentic 人物换成 group fallback（退化）；新增投资者优先加到 PROFILES 而不是只塞进 investor_db
- **若改 panel 输出 schema**：不能删 3 个字段，报告 UI 已依赖

---

## v2.7.3 (2026-04-17 data-source expansion)

### 增强 · 权威域 site: 搜索 + 14 个 Codex 建议源
- **动机**：Codex 建议补"权威媒体 + 官方宏观 + 银行间利率 + 社区舆情"四块源
- **已落地**：14 个 DataSource（cnstock/cs_cn/stcn/nbd/pbc/safe/stats_gov/
  chinamoney/chinabond/ine/guba_em_list/jisilu/fx678/cmc）
- **核心机制**：`lib/web_search.py::search_trusted(query, dim_key=...)` 自动
  prepend `(site:d1 OR site:d2 ...)` 把 ddgs 限定在 dim 对应权威域白名单
- **接入 fetcher**：fetch_policy（全切）/ fetch_macro（部分）/
  fetch_events（权威+通用兜底）/ fetch_moat（权威+通用兜底）
- **不接入**：fetch_trap_signals（需要命中小红书/抖音风险信号，强制权威域
  反而漏；设计上保留现状）· fetch_sentiment（已有按平台 site: 设计）
- **回归测试**：`test_trusted_domains_covers_qualitative_dims` /
  `test_qualitative_fetchers_use_search_trusted` /
  `test_registry_contains_codex_authority_sources`
- **若未来改 web_search**：保持 TRUSTED_DOMAINS_BY_DIM 覆盖至少 5 个核心
  定性维度（3_macro/13_policy/15_events/14_moat/17_sentiment）
- **若未来改 registry**：cnstock/cs_cn/stcn/nbd/pbc/safe/stats_gov/chinabond/
  ine/guba_em_list 10 个权威源不得删除

---

## v2.7.2 (2026-04-17 hotfix)

### BUG#R7 · HK `1_financials` 永远空（stub 从未实现）
- **症状**：所有港股 `1_financials` 返回 `data={}`；ROE / 营收 / 净利 /
  毛利率 / 负债率 / ROIC 全缺；agent 盲评 → 报告完整性掉到 56%
- **位置**：`scripts/fetch_financials.py::main` HK 分支
- **根因**：旧代码 `else: data = {}`（HK 走这里），注释承认 "akshare has
  stock_financial_hk_abstract but field names differ" 但 stub 从未补上
- **修法**：新 `_fetch_hk(ti)` 调用 `ak.stock_financial_hk_analysis_indicator_em`，
  把 ROE_AVG / ROE_YEARLY / ROIC_YEARLY / OPERATE_INCOME / HOLDER_PROFIT /
  DEBT_ASSET_RATIO / CURRENT_RATIO / GROSS_PROFIT_RATIO + YoY 映射到 A 股
  一致的字段；额外保留 HK 特有 `eps` / `bps` / `currency`
- **验证**：`00700.HK` → `roe=21.1%` · `roe_history=[28.1, 29.8, 24.6, 15.1, 21.8, 21.1]` ·
  `revenue_history` 6 年亿元 · `financial_health` 完整
- **若未来改 fetch_financials**：HK 分支必须返回 ROE + 6 年历史，否则
  港股技术面/基本面评委全部盲评

### BUG#R8 · HK 2_kline 只有 1 条路径，GFW 一丢包就 0 根
- **症状**：港股 `kline_count=0`、`stage='—'`、所有技术指标 None；
  `ds.fetch_kline` 在东财 push2his 被代理丢包时直接失败无兜底
- **位置**：`scripts/lib/data_sources.py::_fetch_kline_impl` HK 分支
- **根因**：HK 只有 `ak.stock_hk_hist` 一条路径；A 股已有 6 路 fallback 链，
  但 HK 从未对齐
- **修法**：新 `_kline_hk_chain()` 三层 fallback：
  1. `ak.stock_hk_hist`（东财 push2）
  2. `ak.stock_hk_daily`（新浪, 返 5366 rows IPO-至今）
  3. `yfinance 0700.HK`（海外兜底；自动 `00700` → `700.HK`）
  所有路径返回结果归一到东财中文列（日期/开盘/收盘/最高/最低/成交量）
- **验证**：mock 东财失败后 Sina fallback 正常返 561 rows, stage='Stage 1 底部'
- **若未来改 HK kline**：必须保留至少 2 路以上 fallback；返回前归一到中文列

### BUG#R9 · Wave2 结束未 flush，timeout 标记会丢
- **症状**：跑完 465s 后 `raw_data.json` 里某维度**完全消失**（不是 OK 也不是
  timeout），agent 无法辨别"没跑过"还是"跑挂了"
- **位置**：`scripts/run_real_test.py::collect_raw_data` wave2 末尾
- **根因**：`_persist_progress()` 每 3 个 fetcher 落盘一次；wave2 整体 300s
  超时后把未完成 fetcher 标记 `_timeout=True` 写入 `dims` **仅在内存**；
  wave3 再跑 160s 期间若 Ctrl+C / crash，wave2 的 timeout 标记全丢
- **修法**：wave2 结束立即 `_persist_progress()` + stage1 收尾再 flush 一次。
  raw_data 始终反映最新完整状态。
- **若未来改 wave2/wave3**：任何新 wave 结束必须强制 flush，不要指望增量
  持久化覆盖 wave 结束的关键状态

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
