# 组合再平衡 (Portfolio Rebalance)

> **改编自 `anthropics/financial-services` wealth-management/portfolio-rebalance。**
> **A 股适配：去 TLH（税损收割）+ 换手成本本地化。**

| 项 | 值 |
|---|---|
| Python 模块 | `lib/tier1/rebalance.py :: build_rebalance` |
| 命令 | `/rebalance` |
| 源 SKILL | wealth-management/portfolio-rebalance |
| 配合 | UZI 已有 `--portfolio`（组合体检）→ 本方法（调仓建议） |

## 函数签名

```python
build_rebalance(
    holdings: list[dict],          # [{ticker, weight, market, industry?, value?, price?}]
    targets: dict | None = None,   # {ticker: 目标权重}；None → 等权 1/N
    drift_threshold: float = 5.0,  # 漂移阈值，单位「百分点」
) -> dict
# → {drift_table, trades, turnover_cost, concentration, summary, methodology_log}
```

## 方法论（6 步，逐步可审计）

源 skill 是面向美国财富管理（taxable / IRA / Roth / 401k 多账户 + 资产分置 + wash-sale + TLH）。
A 股散户场景下，这些税优账户体系与资本利得税都不存在，因此**裁掉税务子系统**，保留再平衡的计算内核：

| 源 skill 步骤 | A 股适配 |
|---|---|
| Step 1 Current State（含 cost basis / 未实现盈亏） | **去掉 cost basis / 盈亏** — A 股个人无资本利得税，盈亏不影响调仓决策 |
| Step 2 Drift Analysis（±3-5% band） | **保留** — 当前 vs 目标权重，默认 >5pp 触发 |
| Step 3 Trade Recommendations（Tax-Aware：优先税优账户/避短期收益/TLH/wash-sale） | **裁成纯调仓** — 超阈值即买卖，无税务排序、无 wash-sale |
| Step 4 Asset Location（IRA 放债券 / Roth 放高成长） | **整段删除** — A 股无多类型账户 |
| Step 5 Implementation（交易数 + 成本 + 已实现盈亏） | **换手成本本地化** — 见下表；去掉"已实现盈亏" |
| Step 6 Output | drift_table / trades / turnover_cost / concentration |

实际实现里合并为 6 个 `methodology_log` 步骤：归一化 → 漂移 → 交易清单 → 换手成本 → 集中度 → TLH 说明。

## 漂移与阈值

- 当前权重、目标权重都**自动归一化**到 1.0（支持 0-1 小数或 0-100 百分数）。
- 漂移 = (当前 − 目标) × 100，单位**百分点 (pp)**。
- `|漂移| > drift_threshold` → `breached=True`，进入交易清单。
- 默认阈值 **5pp**（对应源 skill 的 ±3-5% rebalancing band）。
- 三种目标模式：
  - `targets=None` → **等权** 1/N
  - `targets={ticker: w}` → **显式目标**（按评分/按风险的规则可在外层算好权重后传入）

## 换手成本（本地化，双边）

源 skill 只说 "estimated transaction costs"，未给具体率。这里按**当前实际费率**建模并**分市场标注**：

| 市场 | 印花税 | 佣金 | 备注 |
|---|---|---|---|
| A 股 | **0.05%**（仅卖出） | ~0.025%（双边） | 印花税 2023-08-28 从 0.1% 下调至 0.05% |
| 港股 | **0.1%**（买卖双边） | ~0.025%（双边） | 印花税买卖各收一次 |
| 美股 | **≈ 0** | 0（多为零佣金） | 无印花税，SEC 费极小忽略 |

实现细节（`STAMP_DUTY` / `COMMISSION` 常量）：
- A/US：**买入不收印花税**，仅 A 股**卖出**收。
- HK：买卖**双边均收**印花税。
- 成本按**每笔交易额**累加，输出 `total_cost` + `cost_pct_of_turnover` + `by_market` 拆解。
- 未提供 `value/price` → 跳过金额与成本估算，只给漂移方向。

## 风险 / 集中度变化

`concentration.before / after` 各含：
- `top_n_weight` — 前 3 大集中度
- `max_single_weight` — 最大单只仓位
- `hhi` — 赫芬达尔指数（Σ w²，越高越集中）
- `n_industries` / `top_industry_weight` / `industry_breakdown` — 行业分散

并给出 `top_n_change_pp` / `max_single_change_pp` / `hhi_change` 的前→后变化。

## 为什么不做 TLH

**A 股 / 港股个人投资者无资本利得税**，卖出不产生应税收益，也就没有"用浮亏抵税"的动机 → **TLH 不适用**。
`summary.tlh_note` 显式注明这一点。

**美股例外**：若 holdings 含美股（market=US），`tlh_note` 会追加一句提示——
美股有资本利得税与短期/长期持有期区分，卖出端**可另议税损收割**，但本工具不自动执行。

## 与 `--portfolio` 的衔接

`portfolio_runner.py` 的 holdings 结构是 `{ticker, weight, note}`。本模块在其上**扩展可选字段** `market / industry / value / price`，
完全向后兼容：只给 `ticker + weight` 也能跑（只是没有金额/成本/行业分散）。

典型流程：
1. `python run.py --portfolio holdings.csv` — 组合体检（加权评分 + 集中度）
2. `build_rebalance(holdings, targets, threshold)` — 看漂移、出调仓清单、算换手成本
