---
name: earnings-preview
description: 财报前预览 — 一致预期对照 + 行业观察指标 + Bull/Base/Bear 三情景 + 催化剂清单 + 预期波幅
---

# /earnings-preview <股票代码>

公司**披露季报之前**的前瞻预览（earnings preview）。与 `/earnings`（财报后 beat/miss 解读）互为镜像：
`/earnings` 看"已经发生了什么"，`/earnings-preview` 看"接下来该盯什么、会怎么动"。

适配 A股 / 港股 / 美股个股，行业观察指标与隐含波动按市场自适应。

## 工作流

1. 采集数据（22 维），一致预期优先取 `6_research`。
2. 调用：
   ```python
   from lib.tier1.earnings_preview import build_earnings_preview
   result = build_earnings_preview(features, raw_data)
   ```
3. 一致预期 / 历史财报日股价反应 / 期权隐含波动若标注「需 web 补充」，用 web 搜索补全后再成稿。

## 输出

- **一致预期对照表**：EPS / 营收 / 卖方目标价 vs 现状（来源标注；`6_research` 拿不到的标「需 web 补充」）
- **行业观察指标**：按行业分类（SaaS→ARR/NRR、零售→同店、工业→在手订单、金融→NIM、医药→放量；A 股本土：白酒→动销、光模块→出货、新能源→装机）
- **Bull / Base / Bear 三情景**：营收/EPS 区间 + 触发条件 + 历史财报后股价反应（基于历史营收增速 + 毛利率趋势）
- **催化剂清单**：3-5 个决定股价反应的看点（含 whisper number 提示）
- **预期波幅 implied move**：
  - A 股个股多数无期权 → **用历史财报日波动代替**（年化波动 ÷ √252 近似单日）
  - 美股 / 港股 → 可用财报到期 ATM straddle 反推期权隐含波动（需 web 补充期权链）

## 展示示例

```
中际旭创 (300308.SZ) · A股 · 光模块 · 预览季度≈2026 Q2

一致预期：
  EPS 6.2 (YoY +37.8%) · 来源 6_research
  营收 348 亿 (YoY +45%) · ⚠️ 无一致预期 → 3yCAGR 外推，需 web 补充
  卖方目标价 ¥150（覆盖 28 家 / 买入率 90%）

行业观察指标（光模块）：800G/1.6T 出货量 · 高端占比 · 毛利率 · 大客户能见度

三情景（营收增速 / EPS）：
  🟢 Bull  +60.5% / 6.94   触发：量价齐升 + 上修指引
  ⚪ Base  +52.5% / 6.20   触发：基本符合，指引维持
  🔴 Bear  +44.5% / 5.27   触发：不及共识 / 毛利受压

预期波幅：A 股无个股期权 → 历史财报日 ±3.4%（年化波动 55% 近似）
```
