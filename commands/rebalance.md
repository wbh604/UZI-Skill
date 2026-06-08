---
name: rebalance
description: 组合再平衡 — 漂移检测 + 交易清单 + 换手成本（A股/港股/美股，无 TLH）
---

# /rebalance <持仓> [targets=等权] [threshold=5]

对一个组合做**再平衡分析**：当前权重偏离目标多少、要不要动、动的话买卖什么、换手要花多少钱。

A 股个人无资本利得税 → **不做税损收割 (TLH)**，聚焦 **漂移 + 风险 + 换手成本**。
（持仓含美股时，会一句话提示"美股部分可另议税损"。）

## 输入

持仓列表 `[{ticker, weight, market, industry?, value?, price?}]`，与 `--portfolio` 的 CSV 结构同源（ticker / weight / note）：

| 字段 | 必填 | 说明 |
|---|---|---|
| `ticker` | ✅ | `600519.SH` / `00700.HK` / `AAPL` |
| `weight` | ✅ | 当前权重，0-1 小数或 0-100 百分数（自动归一化） |
| `market` | 选 | `A` / `HK` / `US`，缺省按 ticker 后缀推断 |
| `industry` | 选 | 行业，用于行业分散度 |
| `value` | 选 | 该持仓市值（给了才能算金额/成本） |
| `price` | 选 | 现价（给了才能估股数，A 股按手取整） |

- **targets**：`None` → 等权 (1/N)；或 `{ticker: 目标权重}` 显式目标。
- **threshold**：漂移阈值，单位「百分点」，默认 **5**（偏离 >5pp 才动）。

## 工作流

```python
from lib.tier1.rebalance import build_rebalance

out = build_rebalance(holdings, targets=None, drift_threshold=5.0)
# out = {drift_table, trades, turnover_cost, concentration, summary, methodology_log}
```

配合已有 `--portfolio`：先 `python run.py --portfolio holdings.csv` 跑组合体检，
再把同一份 holdings 喂给 `build_rebalance` 做调仓建议。

## 输出

1. **漂移表** `drift_table` — 每只 当前 vs 目标 vs 漂移(pp) + 是否超阈值 + 方向（超配→卖/低配→买）
2. **阈值判断** `summary.any_breach` / `n_breached` / `max_drift_pp` — 默认 >5pp 才触发
3. **交易清单** `trades` — 仅对超阈值持仓：BUY/SELL + 金额 + 估算股数（A 股按手）
4. **换手成本** `turnover_cost` — 分市场拆解：
   - A 股：卖出印花税 0.05%（2023-08 下调）+ 双边佣金 ~0.025%
   - 港股：印花税 0.1%（双边）+ 佣金
   - 美股：印花税 ≈ 0
5. **集中度变化** `concentration` — 前 3 大集中度 / 最大单只 / HHI / 行业分散 的 前→后 对比

## 注意

- 小幅漂移在阈值内不动，别为再平衡而再平衡。
- 没给 `value/price` 时只出漂移方向，不估金额与成本。
- 不做 TLH（A/港股个人无资本利得税）；美股持仓的税损另议。

> 改编自 `anthropics/financial-services` wealth-management/portfolio-rebalance，A 股适配。
> 方法论详见 `skills/deep-analysis/references/fin-methods/rebalance.md`。
