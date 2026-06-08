# Model Update · 增量更新财务模型

> 改编自 **anthropics/financial-services** `equity-research/model-update`，A 股 / 港股 / 美股适配。
> 实现：`scripts/lib/tier1/model_update.py` · 入口 `build_model_update`。

## 这是什么

原版是一份给卖方分析师手填的 markdown 工作流：财报发布后把实绩 plug 进 Excel
模型 → 修正前瞻估计 → 重算估值 → 给新目标价/评级。

UZI 版把它重写成**纯函数**：吃 `features` + `raw_data` + 一组新假设 (`updates`)，
不改任何已有模型，而是计算「关键假设 before→after 的 delta」，并把 delta 传导到
DCF 内在价值、Comps 隐含价、投资逻辑各支柱，最后给更新后的 verdict。核心理念是
**增量**（incremental），不是从头重算——所以它接收已有的 `dcf_result` / `comps_result`
并在其基础上算变化量。

## 函数签名

```python
build_model_update(
    features: dict,
    raw_data: dict,
    updates: dict | None = None,
    dcf_result: dict | None = None,
    comps_result: dict | None = None,
) -> dict
```

| 参数 | 说明 |
|---|---|
| `features` | `lib.stock_features.extract_features` 输出 |
| `raw_data` | 原始 22 维（仅用于取公司名/code） |
| `updates` | 新假设 dict（见下）。`None` → 演示模式，从 features 推断「最新 vs 上期」 |
| `dcf_result` | `lib.fin_models.compute_dcf` 输出 → 算内在价值 delta（不传则标「未提供」） |
| `comps_result` | `lib.fin_models.build_comps_table` 输出 → 算隐含价 delta |

## 支持的假设键

| key | 标签 | 单位 | 影响通道 | before 推断源（演示模式） |
|---|---|---|---|---|
| `rev_growth` | 营收增速 | % | DCF | 最新增速 vs 3Y CAGR |
| `gross_margin` | 毛利率 | % | DCF | features.gross_margin |
| `net_margin` | 净利率 | % | DCF + Comps | features.net_margin |
| `capex_pct` | Capex/营收 | % | DCF | — |
| `stage1_growth` | DCF Stage1 增速 | % | DCF | — |
| `terminal_g` | DCF 终值 g | % | DCF | — |
| `beta` | Beta | x | DCF | — |
| `target_pe` | 目标 PE | x | Comps | features.pe |
| `target_price` | 目标价 | 价格 | Comps | 卖方目标价 vs 现价 |

> 百分比传裸数字（`26.0` = 26%）；倍数 `beta=1.5`；价格 `target_price=24.0`。

## 输出结构（5 段）

1. `assumption_deltas` — 每条假设 `{before, after, before_fmt, after_fmt, delta, direction(↑/↓/→), channel}`。
2. `dcf_impact` — `{available, intrinsic_before, intrinsic_after, delta_pct, wacc_before/after_pct, safety_margin_before/after_pct, drivers}`。
3. `comps_impact` — `{available, implied_pe_before, implied_pe_after, delta_pct, drivers}`。
4. `thesis_impact` — list，每条改动映射到支柱（成长性/盈利质量/现金流/风险/估值锚）+ 💪 强化 / ⚠️ 削弱。
5. `verdict` — `{rating, action, composite_score, pillars_strengthened, pillars_weakened}`。

外加 `methodology_log`（沿用 UZI 范式，逐步可追溯）。

## 传导逻辑（一阶近似）

为保持纯函数 + 无副作用，本模块**不回灌** `compute_dcf`，而用一阶弹性近似重定价：

- **DCF**：
  - `stage1_growth` / `rev_growth`（半弹性映射）→ 显式期复利因子 `(1+g_a)^5 / (1+g_b)^5`。
  - `net_margin` / `gross_margin` → 按比例缩放基期 FCF。
  - `capex_pct` ↑ → 每 +1pp 约 −3% FCF。
  - `beta` ↑ → 通过 CAPM（沿用 rf/erp/equity_weight）抬高 WACC → 终值因子 `(wacc_b−g_b)/(wacc_a−g_a)`。
  - `terminal_g` → 同样进终值因子。
- **Comps**：
  - `net_margin` ↑ → 放大 EPS → 隐含价 = 中位 PE × EPS_after。
  - `target_pe` → 直接替换乘数。

> 这是「快速影响估算」。要精确数字时，把 `updates` 转成 `compute_dcf` 的
> `assumptions=` 重跑一遍 DCF，再把两个 DCF 结果对比（精度高于本模块的一阶近似）。

## verdict 评分

```
composite = dcf.delta_pct + comps.delta_pct + (强化支柱 − 削弱支柱) × 2
  ≥ +10 → 🟢 上修      [+3,+10) → 🟡 小幅上修
  (−3,+3) → ⚪ 维持     (−10,−3] → 🟠 小幅下修      ≤ −10 → 🔴 下修
```

`capex_pct` / `beta` 上升计为利空（削弱），其余假设上升计为利多（强化）。

## 与 UZI 其它模块的关系

- 上游：`/dcf`（`compute_dcf`）、`/comps`（`build_comps_table`）产出 `dcf_result` / `comps_result`。
- 平行：`/earnings`（`build_earnings_analysis`）做 beat/miss 定性，`model-update` 做定量重定价——
  财报后通常先 `/earnings` 看超预期与否，再 `/model-update` 把新数字灌进模型看目标价怎么动。
- 下游：`/thesis`（`build_thesis_tracker`）跟踪支柱状态；本模块的 `thesis_impact` 是「假设变动 → 支柱方向」的瞬时映射。

## 默认假设来源

A 股估值参数沿用 UZI institutional-modeling 默认（见
`references/task1.5-institutional-modeling.md`）：rf 2.5% / ERP 6% / 税 25% /
终值 g 2.5%。WACC 与 beta 改动从传入的 `dcf_result.wacc_breakdown.inputs` 取 rf/erp，
保证跟原 DCF 一致。
