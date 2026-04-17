# Release Notes

## v2.7.1 — 2026-04-17 (hotfix)

> **修复 `19_contests` / `18_trap` 两维永远空的两个独立 bug**

### 用户报告
> "实盘比赛持仓，杀猪盘信号这些还是没数据"

### 根因 1（R5）· XueQiu 2026 加登录鉴权
- `xueqiu.com/cubes/cubes_search.json` 直访 → `400 + error_code: "400016"`
- 旧 fetch_contests 把任何 status≠200 当 0 cube → 19_contests 永空
- 修：新 `lib/xueqiu_browser.py` Playwright + 持久化 cookie；fetch_contests 透明
  标记 `login_required: True`；用户可 `--enable-xueqiu-login` opt-in
- README 加「需登录的数据源」章节，说明启用步骤

### 根因 2（R6）· ddgs 缓存空结果残留
- v2.6.1 之前 ddgs 没装 → `_ddg_search()` 返 [] → cache 缓存 12h
- 装 ddgs 后 cache 仍生效 → trap_signals 8 信号永远命中 0
- 修：清 `.cache/_global/api_cache/ws__*` cache（一次性）
- `_auto_summarize_dim` 改成显示 "8 信号扫描命中 0/8（已扫 ddgs 24 条搜索结果）"，
  让用户清楚是"扫了 0 命中"而不是"没扫"

### 新增
- `lib/xueqiu_browser.py` (~140 行) · Playwright + 持久化 cookie + opt-in 登录流程
- `run.py --enable-xueqiu-login` flag · `UZI_XQ_LOGIN=1` env var
- README "🔓 需登录的数据源" 章节
- BUGS-LOG · BUG#R5 + BUG#R6 记录
- 3 个新回归测试（共 18 个，全部通过）

### 浙江东方实测对比
| 维度 | 修前 | 修后 |
|---|---|---|
| 19_contests commentary | "暂未上榜实盘比赛"（误导：其实是接口 401） | "⚠️ XueQiu 需登录，启用方式：..." |
| 18_trap commentary | "🟢 安全；命中信号 0 条" | "🟢 安全 · 8 信号扫描命中 0/8（已扫 ddgs 24 条结果）" |

启用 XueQiu 登录后，可看到 50+ 个雪球组合持有 + 收益率分布。

---

## v2.7.0 — 2026-04-17

> **按股票风格动态加权评分 + 量化基金结构性识别 + 4 个 regression bug 修复 + 防回归测试 + bug 全量记录**

### 主线 · 风格动态加权（解决"分数都偏低、一片回避"的系统性问题）

旧公式 `consensus = bullish/active*100` 太严苛 → overall 普遍 < 40 → 一片回避。

新机制：
- **7 + 1 个 style** · 白马 / 高成长 / 周期 / 小盘投机 / 分红防御 / 困境反转 / 量化因子型 / 中性兜底
- `lib/stock_style.py` 自动识别 + 7×7 评委组矩阵 + 8 个个体 override
- 22 维 fundamental dim multiplier
- **neutral 半权计入 consensus**（修正旧公式 0% 权重核心 bug）

### 量化因子型 · 结构性识别（用户特别要求）

`lib/quant_signal.py` · 不维护白名单，用结构性特征：
> 第一大持仓 < 2% → 疑似量化基金；该股在多少家这种基金 top-10 → 触发 quant_factor

私募量化备查名单（10 个 · 幻方/九坤/灵均/明汯等）供 agent 走 LHB / web search 交叉验证。

### 修复 4 个 BUG（用户实测发现）

| ID | 症状 | 修法 |
|---|---|---|
| **R1** | ST 股错判 small_speculative | distressed 条件支持负 ROE |
| **R2** | fund_managers 还是 6 个 | wave3 调用 `limit=None`；浙江东方 6 → **332 个** |
| **R3** | agent 没主动核查就出报告 | 新 HARD-GATE-FINAL-CHECK |
| **R4** | mini_racer V8 crash on Py3.13 | wave3 默认 serial workers |

### 防回归基础设施
- `docs/BUGS-LOG.md` — 全量 bug 历史 + 10 条 don't 清单
- `scripts/tests/test_no_regressions.py` — 15 个回归测试，全部通过

### 浙江东方实测对比
| 项 | v2.6.1 | v2.7.0 |
|---|---|---|
| panel_consensus | 6.0 | **17.0** (+11.0) |
| **overall_score** | **39.8 (回避)** | **44.2 (谨慎)** |
| fund_managers 显示 | 6 个 | **332 个** |

---

## v2.6.1 — 2026-04-17 (hotfix)

> **追加论坛 bug · 直跑模式定性维度依然空** 修复

### 用户报告
跑完报告后发现 "宏观环境/政策/原材料/期货/事件" 5 维仍然空白。

### 根因（3 串）
1. `dim_commentary` 的 `dim_labels` 只覆盖 9/22 维，5 个定性维度直接 missing
2. fallback commentary 是 "[脚本占位] 待 Claude 补充"——哪怕 raw_data 已有数据
3. **`ddgs` 不在 requirements.txt** — 所有依赖 `lib/web_search` 的代码静默返回 0 结果（这是 v2.3 起的隐藏 bug）

### 修复
- `_auto_summarize_dim()` 覆盖全 22 维 · 把 raw_data 字段综合成 1-2 句中文摘要
- `_autofill_qualitative_via_mx()` MX → ddgs 二级兜底 · 失败显式标记
- `requirements.txt` 加 `ddgs>=9.0.0`

### 实测（浙江东方 600120.SH）
6/6 定性维度全有真实内容（5 维 ddgs 兜底 + 1 维原本有数据）。

---

## v2.6.0 — 2026-04-17

> **论坛 11 项 bug 综合修复 + Codex 测试发现的 5 个 PR#2 blocker**

### 论坛报告 bug（来自 [linux.do/t/topic/1981105](https://linux.do/t/topic/1981105)）

| # | bug | v2.6 修复 | 文件 |
|---|---|---|---|
| 2 | `KeyError: 'skip'` | preview_with_mock.py 加 'skip' key + .get() 兜底 | `preview_with_mock.py:322` |
| 11 | 失败卡死整条 pipeline | `as_completed(timeout=300)` + `result(timeout=90)` + 长尾 fetcher 180s 例外 | `run_real_test.py:113-220` |
| 9 | OpenCode 跑到 60% 停止不能续 | `collect_raw_data(resume=True)` + 增量保存 raw_data.json + `--no-resume` flag | `run_real_test.py` + `run.py` |
| 3 | python 直跑报错 | Py3.9 兼容（A） + 全部 import 测过 + render alias（E） | 多文件 |
| 10 | pypi 超时 | v2.4 已 4 级镜像 fallback；v2.6 加诊断输出 | `run.py:check_dependencies` |
| 8 | 反爬数据缺失 | 新增 `_fetch_price_tencent_qt(market, code)` A/H/U 通用价格兜底 | `lib/data_sources.py` |
| 5 | 排序异常（最看空 27 vs 0 不一致） | 排除 score=0 异常 + 按 score 排（不再按 signal 分组）+ 矛盾警示 | `run_real_test.py:712-746` |
| 6 | 编造事实（药明康德↔Apple） | 新 HARD-GATE-FACTCHECK 强制 cite raw_data | `SKILL.md` |
| 1 | 非 Claude 评委对齐错位 | 新 `lib/agent_analysis_validator.py` schema 校验 + `_agent_analysis_errors.json` 写盘 | 新文件 + stage2 |
| 4 | Codex 兼容差 | run.py Codex 检测增强 + SKILL.md 新增"Codex 自适配"小节 | `run.py` + `SKILL.md` |
| 7 | Claude plugin 不能执行 | hooks.json 直调 session-start（去掉 polyglot run-hook.cmd 中间层）+ chmod | `hooks/hooks.json` + `hooks/README.md` |

### Codex 在 PR#2 测试中发现的 5 个 BLOCKER

| Blocker | 修复 |
|---|---|
| A: `str \| None` Python 3.10+ 语法在 3.9 报错 | `from __future__ import annotations` 加到所有 v2.3+ 新文件 + run.py |
| B: `mini_racer` V8 thread crash on 600519 | 给 fetch_industry/capital_flow/valuation 加共享 `_MINI_RACER_LOCK` |
| C: 报告 banner 还显示 v2.2 | run.py + assemble_report.py 动态读 plugin.json，模板加 `{{PLUGIN_VERSION}}` |
| D: HK price 是 None | Tencent qt 兜底（同 bug 8）实测 00700 拿到 ¥510 |
| E: render_share_card / render_war_report 缺 main() | 加 `main = render` alias |

### 新增 lib

- `lib/agent_analysis_validator.py` — schema 校验 (~250 行)
  - 检查 dim_commentary/panel_insights/great_divide_override/narrative_override/buy_zones 类型
  - error 级 + warning 级
  - `format_issues()` 漂亮控制台输出

### 新增 flag

- `python run.py {ticker} --no-resume` — 强制重抓全部 22 fetcher
- 默认 resume：复用 `.cache/{ticker}/raw_data.json` 中已有有效维度（节省 80% 时间）

### 测试验证

- ✅ Python 3.9.6 (默认 macOS python3) 可 import 所有模块
- ✅ Python 3.13 (conda) 跑通完整流程
- ✅ Tencent qt 三市场实测：A 600519 / H 00700 / U AAPL 都返回有效 price
- ✅ Validator 自测 3 个 case 通过

---

## v2.5.0 — 2026-04-17

### 数据源注册表（v2.5 主题）
- **`lib/data_source_registry.py`** — 40+ 个数据源元数据集中管理（新文件，~330 行）
  - 3 个 Tier：HTTP 主源 (22) / Playwright 浏览器源 (7) / 官方披露源 (11)
  - 字段：id / name / url / markets / dims / tier / access / health / notes
  - 辅助函数：`by_dim()` / `by_market()` / `http_sources_for()` / `playwright_sources_for()`
- **`task2.5-qualitative-deep-dive.md` URL 模板扩充**
  - Dim 3 加 华尔街见闻 / 第一财经 / Investing 经济日历 + 商品
  - Dim 4 新加段（A/H 浏览器源）
  - Dim 7 加 问财 / 同花顺 F10
  - Dim 13 加 财联社 7x24 / 华尔街见闻
  - Dim 15 加 财联社 / 第一财经 / 金融界 / 网易财经；HK 段加 HKEXNews + AASTOCKS
  - Dim 16 新加段（云财经龙虎榜 + 东财）

### 港股 5 维实际增强
- **`lib/hk_data_sources.py`** — 包装之前未用到的 50+ akshare HK 函数（新文件，~200 行）
  - `fetch_hk_basic_combined`：XQ basic + EM company profile + EM valuation/scale/growth comparison
  - `fetch_hk_announcements`：HKEXNews 静态 HTML 抓取（基础版）
- **`_fetch_basic_hk` 重写**（data_sources.py）：从 1 个 push2 调用扩展到 4 源 fallback chain
  - 新拿到字段：industry / pe_ttm / pb / market_cap / 主营业务 / chairman / ranks / 港股通标记
  - 实测 00700：industry=软件服务、PE=18.95、PB=3.69、市值=4.13万亿、HK 排名第 1
- **`fetch_peers.py` HK 分支**：rank-in-HK-universe 替代具体同行表（agent 可走 AASTOCKS Playwright 补充）
- **`fetch_capital_flow.py` HK 分支**：港股通资格 (沪/深) + eniu 30日市值历史
- **`fetch_events.py` HK 分支**：HKEXNews 公告 + 中文 web search 兜底

### AGENTS.md
- 新增"数据源速查表"小节：按 dim × 市场列出推荐源优先级
- Python 调用示例（agent 怎么用 registry）

### 维持兼容
- `requirements.txt` 不变（无新 pip 依赖）
- AASTOCKS 仅作 Tier-2 Playwright 源在 registry 出现，不写 fetcher 代码（HTML 是 JS 渲染的）
- 1_financials / 6_research / 16_lhb 等其他 6 个 HK dim 仍 stub，标在 RELEASE-NOTES "已知缺口"

### 已知缺口（next）
- HK price/change_pct（push2 spot 不通；agent 可走 Tencent qt: `qt.gtimg.cn/q=hk{code5}`）
- HK 财报 / HK 研报 / HK 沪深港通持股变动 / HK 同行具体 list（全走 AASTOCKS Playwright）

---

## v2.4.0 — 2026-04-17

### 大佬抓作业完整性
- `fetch_fund_holders.py:limit` 默认从 50 → None，茅台实测 649 家主动权益基金全部收录
- `assemble_report.render_fund_managers` 第 7 位起切换到紧凑行（48px × 滚动）
- 并行计算 fund_stats（默认 3 workers，`UZI_FUND_WORKERS=1` 切串行）

### 6 维定性深度方法论
- 新增 `references/task2.5-qualitative-deep-dive.md`（~400 行）
  - 3 个并行 sub-agent 分工（Macro-Policy / Industry-Events / Cost-Transmission）
  - 每维 4-7 必答问题、6 条跨域因果链
- SKILL.md 新增 HARD-GATE-QUALITATIVE
- pip 国内镜像自动 fallback（清华 → 阿里云 → 中科大 → 豆瓣）
- AGENTS.md 新增"网络受限环境"场景 A/B/C

---

## v2.3.0 — 2026-04-17

### 中文名纠错 + MX 妙想 API 接入
- 新 `lib/name_matcher.py` (Levenshtein + Jaccard fuzzy)
- 新 `lib/mx_api.py` (东财妙想 Skills Hub `mkapi2.dfcfs.com` 客户端)
- 三层解析：MX → akshare 精确 → 本地 fuzzy
- `.env` + `--force-name`

### 数据缺口 agent 接管
- `data_integrity.generate_recovery_tasks` 输出 agent 任务清单
- HTML 报告顶部橙色 banner 标注缺失字段
- HARD-GATE-NAME + HARD-GATE-DATAGAPS

---

## v2.2.0 (develop) — 2026-04-16

### Agent Closed-Loop (核心改动)
- **`agent_analysis.json`**: 新增闭环文件，agent 的定性分析独立存储
- **`generate_synthesis()` 合并机制**: 优先使用 agent 写入的字段，仅对缺失字段生成 stub
- **`stage2()` 自动读取**: 读取 `agent_analysis.json` 并传给 `generate_synthesis` 合并
- **`agent_reviewed` 标记**: synthesis 输出带标记，明确标识是否有 agent 介入
- **HARD-GATE 增强**: 必须写 `agent_analysis.json` + 设置 `agent_reviewed: true` 才能进 stage2
- **合并优先级**: agent dim_commentary > stub，agent punchline > 脚本金句，agent risks > 低分维度生成

### Agent 可覆盖字段
- `dim_commentary` — 每维度定性评语
- `panel_insights` — 评委整体观察
- `great_divide_override.punchline` — 冲突金句
- `great_divide_override.bull_say_rounds` / `bear_say_rounds` — 辩论 3 轮
- `narrative_override.core_conclusion` — 综合结论
- `narrative_override.risks` — 风险列表
- `narrative_override.buy_zones` — 四派买入区间

### Bug Fixes
- Fixed: `main()` 函数 `standalone_path` 不在作用域（NameError）

---

## v2.1.0 — 2026-04-16

### Architecture
- **Two-stage pipeline**: `stage1()` (data + skeleton) → agent analysis → `stage2()` (report)
- **HARD-GATE tags**: Claude cannot skip agent analysis step
- **Multi-platform support**: `.codex/`, `.opencode/`, `.cursor-plugin/`, `GEMINI.md`
- **Session hooks**: `hooks.json` auto-activates on session start
- **Agent template**: `agents/investor-panel.md` for sub-agent role-play

### Investor Intelligence
- **3-layer evaluation**: reality check (market/holdings/affinity) → rule engine → composite
- **Known holdings**: Buffett×Apple=100 bullish (actual holding), 游资×US=skip
- **Market scope**: Only 游资 restricted to A-share; all others evaluate globally

### Bug Fixes
- Fixed: KeyError 'skip' in sig_dist and vote_dist
- Fixed: investor_personas crash on skip signal
- Fixed: Hardcoded risks "苹果订单" appearing for all stocks
- Fixed: Great Divide bull/bear score mismatch with jury seats
- Fixed: build_unit_economics crash when industry is None
- Fixed: Capital flow empty (北向关停 → 主力资金替代)
- Fixed: LHB empty → show sector TOP 5
- Fixed: Governance pledge parsing (list[dict] not string)

---

## v2.0.0 — 2026-04-16

### New Features
- **17 institutional analysis methods** from anthropics/financial-services-plugins
  - DCF (WACC + 2-stage FCF + 5×5 sensitivity)
  - Comps (peer multiples + percentile)
  - 3-Statement projection (5Y IS/BS/CF)
  - Quick LBO (PE buyer IRR test)
  - Initiating Coverage (JPM/GS/MS format)
  - IC Memo (8 chapters + Bull/Base/Bear scenarios)
  - Porter 5 Forces + BCG Matrix
  - Catalyst Calendar, Thesis Tracker, Idea Screen, etc.
- **51 investor panel** with 180 quantified rules
- **Rule engine**: investor_criteria.py + investor_evaluator.py + stock_features.py (108 features)
- **Data integrity validator**: 100% coverage check after Task 1
- **Bloomberg-style HTML report** (~600KB self-contained)
- **14 slash commands**: /dcf, /comps, /lbo, /initiate, /ic-memo, /catalysts, /thesis, /screen, /dd, etc.

### Data Sources
- 22 dimensions, 8+ data sources, multi-layer fallback
- All free, zero API key (akshare/yfinance/ddgs/eastmoney/xueqiu/tencent/sina/baidu)

---

## v1.0.0 — 2026-04-14

- Initial release
- 19 dimensions + 50 investor panel + trap detection
- Basic HTML report
