---
name: model-update
description: 增量更新财务模型 — 用新财报/新指引/修正假设重算 DCF 内在价值、Comps 隐含价、投资逻辑与目标价，输出 before→after delta
---

# /model-update <股票代码> [新假设]

财报发布 / 公司更新指引 / 修正假设后，用新数据增量更新已有财务模型，
而不是从头重算。输出关键假设 before→after 的 delta 表，并把改动传导到
DCF 内在价值、Comps 隐含价、投资逻辑各支柱，给出更新后的 verdict。

A 股 / 港股 / 美股通用；估值参数沿用 UZI（A 股 rf 2.5% / ERP 6% / 税 25%）。

触发词：「更新模型 / 改假设重算 / 新指引 / 财报更新数字 / 修正估计 / revise estimates」。

## 输入

| 来源 | 说明 |
|---|---|
| 新财报实绩 | 营收 / 毛利率 / 净利率 / capex 的最新实际值 |
| 新管理层指引 | 营收增速、利润率、资本开支前瞻 |
| 修正假设 | 分析师调高/调低 stage1 增速、终值 g、beta、目标 PE/目标价 |

支持的假设键（`updates` dict）：
`rev_growth` · `gross_margin` · `net_margin` · `capex_pct` ·
`stage1_growth` · `terminal_g` · `beta` · `target_pe` · `target_price`
（百分比传数字如 `26.0` 表示 26%；倍数 `beta=1.5`；价格 `target_price=24.0`）

## 工作流

1. 采集/复用最新 features（`extract_features`）。
2. 若要算估值影响，先有 DCF / Comps 结果（复用 `/dcf`、`/comps` 的输出）。
3. 调用：
   ```python
   from lib.tier1.model_update import build_model_update
   from lib.fin_models import compute_dcf, build_comps_table

   dcf = compute_dcf(features)                         # 可选
   comps = build_comps_table(target, peers)            # 可选

   result = build_model_update(
       features, raw,
       updates={"rev_growth": 26.0, "net_margin": 16.0, "capex_pct": 7.0},
       dcf_result=dcf, comps_result=comps,
   )
   ```
   - `updates=None` → 演示模式：从 features 推断「最新 vs 上期」自动出 delta。
   - 不传 `dcf_result` / `comps_result` → 对应影响段标记「未提供」，函数照常返回结构。

## 输出

- **① 假设 delta 表**：每条假设 before → after（↑/↓/→）+ 影响通道。
- **② DCF 内在价值影响**：每股内在价值 before→after、delta%、WACC 变化、安全边际变化。
- **③ Comps 隐含价影响**：中位 PE × EPS 隐含价 before→after、delta%。
- **④ 投资逻辑影响**：每条改动映射到对应支柱（成长性/盈利质量/现金流/估值锚），💪 强化 / ⚠️ 削弱。
- **⑤ 更新后 verdict**：综合分 → 上修 / 维持 / 下修 + 建议动作。

## 展示示例

```
📊 模型更新 · 测试科技 (000001.SZ) · 显式模式

① 关键假设 delta
  营收增速     15.0% → 26.0%  (↑)  [→DCF]
  净利率       14.0% → 16.0%  (↑)  [→DCF/Comps]
  Capex/营收    6.7% →  7.0%  (↑)  [→DCF]

② DCF 内在价值   ¥20.00 → ¥23.05  (+15.3%)  ↑
   WACC 8.50% → 8.50% · 安全边际 +8.1% → +24.6%

③ Comps 隐含价   ¥22.00 → ¥25.15  (+14.3%)  ↑（净利率放大 EPS）

④ 投资逻辑
  成长性（营收增速）   15.0%→26.0% (↑)   💪 强化
  盈利质量（净利率）   14.0%→16.0% (↑)   💪 强化
  现金流/资本纪律      6.7%→7.0%  (↑)   ⚠️ 削弱

⑤ 更新后评级：🟢 上修 (Upgrade)（综合分 +31.5）→ 上调目标价 / 加仓候选
```

## 方法论

详见 `skills/deep-analysis/references/fin-methods/model-update.md`
（改编自 anthropics/financial-services equity-research/model-update）。
