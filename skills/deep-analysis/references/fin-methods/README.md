# 机构级财务分析方法库

> 改编自 `anthropics/financial-services-plugins`，适配 A 股 / 港股 / 美股散户深度分析场景。

本目录记录 22 种机构级分析方法的**方法论**与**A 股落地参数**（18 种核心 + 5 个 Tier-1 续引入，见文末）。每种方法都有对应的 Python 计算模块：

| 方法 | Python 模块 | 源 SKILL |
|---|---|---|
| DCF 估值 | `lib/fin_models.py :: compute_dcf` | financial-analysis/dcf-model |
| Comps 相对估值 | `lib/fin_models.py :: build_comps_table` | financial-analysis/comps-analysis |
| 三表预测 | `lib/fin_models.py :: project_three_stmt` | financial-analysis/3-statement-model |
| LBO 快速测试 | `lib/fin_models.py :: quick_lbo` | financial-analysis/lbo-model |
| 并购增厚/摊薄 | `lib/fin_models.py :: accretion_dilution` | investment-banking/merger-model |
| Porter 5 Forces + BCG | `lib/deep_analysis_methods.py :: build_competitive_analysis` | financial-analysis/competitive-analysis |
| 首次覆盖报告 | `lib/research_workflow.py :: build_initiating_coverage` | equity-research/initiating-coverage |
| 财报业绩解读 | `lib/research_workflow.py :: build_earnings_analysis` | equity-research/earnings-analysis |
| 催化剂日历 | `lib/research_workflow.py :: build_catalyst_calendar` | equity-research/catalyst-calendar |
| 投资逻辑追踪 | `lib/research_workflow.py :: build_thesis_tracker` | equity-research/thesis-tracker |
| 晨报 | `lib/research_workflow.py :: build_morning_note` | equity-research/morning-note |
| 量化选股筛选 | `lib/research_workflow.py :: run_idea_screen` | equity-research/idea-generation |
| 行业综述 | `lib/research_workflow.py :: build_sector_overview` | equity-research/sector-overview |
| 投委会备忘录 | `lib/deep_analysis_methods.py :: build_ic_memo` | private-equity/ic-memo |
| 单位经济 | `lib/deep_analysis_methods.py :: build_unit_economics` | private-equity/unit-economics |
| 价值创造计划 | `lib/deep_analysis_methods.py :: build_value_creation_plan` | private-equity/value-creation-plan |
| 尽调清单 | `lib/deep_analysis_methods.py :: build_dd_checklist` | private-equity/dd-checklist |
| 组合再平衡（大类配置） | `lib/deep_analysis_methods.py :: build_portfolio_rebalance` | wealth-management/portfolio-rebalance |

## Tier-1 续引入（v3.8.0 · `lib/tier1/` 包）

> 2026-06-04 第二批从 `anthropics/financial-services` 续引入的 5 个与个股研究强相关的方法，
> 各自有 slash 命令（`commands/`）+ 方法论文档（本目录）+ 纯函数模块（`lib/tier1/`）+ pytest。

| 方法 | Python 模块 | 命令 | 源 SKILL |
|---|---|---|---|
| AI 就绪度/卡位评估 | `lib/tier1/ai_readiness.py :: build_ai_readiness` | `/ai-readiness` | private-equity/ai-readiness（适配单票 + 复用 `ai_chokepoint_score`） |
| 财报前预览 | `lib/tier1/earnings_preview.py :: build_earnings_preview` | `/earnings-preview` | equity-research/earnings-preview |
| 模型增量更新 | `lib/tier1/model_update.py :: build_model_update` | `/model-update` | equity-research/model-update |
| 组合收益归因 | `lib/tier1/returns_attrib.py :: build_returns_attribution` | `/returns` | private-equity/returns-analysis（适配二级市场组合） |
| 组合再平衡（逐持仓+换手成本） | `lib/tier1/rebalance.py :: build_rebalance` | `/rebalance` | wealth-management/portfolio-rebalance（A 股适配：去 TLH + 印花税/佣金本地化） |

说明：`/rebalance`（逐持仓 + A 股印花税/佣金换手成本）与既有 `build_portfolio_rebalance`（资产大类配置漂移）分工互补，前者出**调仓交易清单**、后者看**大类配置偏离**。

## 设计原则（全部来自原 SKILL.md 的 CRITICAL CONSTRAINTS）

1. **公式 over 硬编码**：所有派生值都是"函数调用"，不是预计算的数字。改变假设，全链条联动更新。
2. **Step-by-step 可审计**：每个模块返回的 dict 里都带 `methodology_log`，完整记录"每一步在算什么"。
3. **敏感性内置**：DCF 强制 5×5 敏感性表，中心格必须等于基础案例的每股内在价值（自检机制）。
4. **数据源优先级**：真数据 > 代理估算 > 默认值。所有默认值都显式标记为 DEFAULT_*。
5. **情景分析**：IC memo 强制 Bull / Base / Bear 三情景 + 概率 + 假设。

## A 股落地参数

| 参数 | 默认值 | 来源 |
|---|---|---|
| 无风险利率 (rf) | 2.5% | 10Y 中国国债 |
| 股权风险溢价 (ERP) | 6.0% | A 股历史 |
| 标准税率 | 25% | 企业所得税 |
| 高新税率 | 15% | 高新技术企业 |
| 终值永续增长 | 2.5% | 长期 GDP 名义 |
| Beta 默认 | 1.0 | 中性 |
| 债务比例 | 30% | A 股中位数 |
| 税前债务成本 | 4.5% | LPR + 0.5-1pp |

## 报告集成

- 新增 dim **`20_valuation_models`** — DCF / Comps / 3-stmt / LBO 打包
- 新增 dim **`21_research_workflow`** — Initiating / Earnings / Catalyst / Thesis / Morning / Screen / Sector
- 新增 dim **`22_deep_methods`** — IC Memo / Unit Economics / VCP / DD / Competitive / Rebalance

每个新 dim 都通过 `compute_deep_methods.py` 生成，不走 web 请求（纯计算），所以 Task 1 之后 Task 2 里就能直接跑出来。

## 已有 / 新增对照

**之前我们有**：19 维数据采集 + 51 评委量化规则
**这次新增**：机构级财务建模层 (DCF/Comps/LBO/3-stmt) + 研究工作流产物 (首次覆盖/财报解读/催化剂/逻辑追踪) + 深度决策方法 (IC memo/DD/Porter/单位经济/VCP/再平衡)

改动后：**19 维 + 3 新 dim + 51 评委（规则引擎引用新特征） + 18 种分析方法**
