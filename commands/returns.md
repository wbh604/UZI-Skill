---
name: returns
description: 组合收益归因 — 拆解总收益为各持仓贡献 + 行业/流派归因 + Top 贡献/拖累 + vs 基准
---

# /returns <holdings.csv | 组合> [benchmark=6.0]

把一个组合的**区间总收益**拆开：谁赚的钱、哪类资产赚的、谁是英雄谁是猪队友。
配合 UZI 的 `--portfolio` 组合功能 —— portfolio_runner 负责打分/健康度，本命令负责"涨跌从哪来"。

> 改编自 anthropics/financial-services · private-equity/returns-analysis，适配二级市场组合。
> 方法详见 `skills/deep-analysis/references/fin-methods/returns-attribution.md`。

## 输入

吃 `--portfolio` 同款 holdings 结构，每行再带 `return_pct` / `industry`：

```
ticker,weight,return_pct,industry,name
600519.SH,0.40,10.0,白酒,贵州茅台
000858.SZ,0.30,-5.0,白酒,五粮液
002594.SZ,0.30,20.0,电动车,比亚迪
```

- `weight` 0-1 或 0-100 都行，自动归一化；缺失则等权。
- `return_pct` 个股区间收益率(%)。**拿不到**则留空 → 标注"需补价格区间"，按 0 计（可先从 K 线维度补区间收益再回填）。
- `school` 可选 · 带上就多出一维流派归因。

## 工作流

```python
from lib.tier1.returns_attrib import build_returns_attribution

result = build_returns_attribution(holdings, benchmark_return=6.0)  # 基准可选
```

## 输出

| 模块 | 内容 |
|---|---|
| **总收益** | `total_return` = Σ(权重×个股收益)，单位 pp |
| **加权贡献表** | 逐持仓：仓位 / 收益 / 贡献(pp) / 是否需补价 |
| **行业归因** | 各行业贡献（降序），加总 == 总收益 |
| **流派归因** | 仅当 holdings 带 `school` |
| **Top3 贡献 / Top3 拖累** | 正/负贡献排序 |
| **vs 基准** | 超额 = 总收益 − 基准，跑赢/跑输 |
| **一句话点评** | `verdict` |

## 展示示例

```
组合区间总收益 +8.50%（vs 基准 +6.00% · 超额 +2.50pp · 🟢 跑赢）

加权贡献表：
  比亚迪    电动车  30%  +20.0%  贡献 +6.00pp  ←主升
  贵州茅台   白酒   40%  +10.0%  贡献 +4.00pp
  五粮液    白酒   30%   -5.0%  贡献 -1.50pp  ✕拖累

行业归因：电动车 +6.00pp · 白酒 +2.50pp
Top 贡献：比亚迪 +6.00 / 贵州茅台 +4.00
Top 拖累：五粮液 -1.50

一句话：组合总收益 +8.50%，主升由比亚迪贡献 +6.00pp，主要拖累五粮液 -1.50pp，跑赢基准 +2.50pp。
```

## 注意

- 贡献单位是**百分点 (pp)**（已乘权重），不是个股收益率本身。
- 分组归因只是重排，加总必须等于总收益。
- 缺 `return_pct` 不报错，但 verdict 会提示"⚠️ N 只缺区间收益需补价格"。
- 实绩归因（已发生区间收益），不做情景/敏感性预测。
