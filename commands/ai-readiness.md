---
name: ai-readiness
description: AI 就绪度评估 — 单票 AI 暴露/卡位评级 + 三道 gate + Top 杠杆点
---

# /ai-readiness <股票代码>

评估这一家公司在 AI 浪潮里的**暴露度 / 就绪度 / 卡位强度**。
改编自 anthropics/financial-services 的 PE「ai-readiness」组合扫描法，
适配成**单只个股**，并复用 Serenity 的 `ai_chokepoint_score` 作为卡位强度锚。

## 工作流

1. 采集数据 → `extract_features(raw, dims)`（已自带 AI 卡位派生特征）
2. 调用：
   ```python
   from lib.tier1.ai_readiness import build_ai_readiness
   result = build_ai_readiness(features, raw)
   ```

## 三道 Gate（个股版）

| Gate | 判据 | 数据源 |
|---|---|---|
| ① 是否真在 AI 产业链上 | `ai_chain_hit` | 关键词命中 |
| ② 是否有可验证的 AI 真实收入/订单/产能 | 订单/长协/产能/景气证据 | 5_chain · 15_events · 7_industry |
| ③ 卡位是否不可替代且可持续 | `ai_irreplaceable` + moat | 14_moat |

三 yes = 「强就绪 / Go」；否则「观察 / Wait」并注明缺口。

## 输出

- **AI 暴露评级**：强 / 中 / 弱 / 无（以 `ai_chokepoint_score` 为主锚）
- **三道 Gate**：逐条 pass/fail + 依据
- **Top 2-3 AI 杠杆点**：算力 / 光互连 / 存储 / 供电散热 / AI 应用 / AI 赋能传统业务
- **裁决**：Go · 强就绪 / Wait · 观察（含缺口）
- **一句话结论**
- 组合相关项（跨公司排序 / replays / 组合 EBITDA）→ 单票 **N/A**

## 展示示例

```
AI 就绪度 · AXT科技 (AXTI.US)

评级「强」(卡位强度 88/100) · 通过 3/3 Gate → Go · 强就绪
  ① 真在 AI 链上    ✅ 命中 ['inp','磷化铟','光模块','cpo']
  ② 真实收入/订单    ✅ 证据词 ['订单','长协','缺货','扩产']
  ③ 不可替代可持续   ✅ 切换+规模壁垒达标 (moat 26/40)

Top AI 杠杆点：光互连 / 光模块 · 存储 / HBM
结论：AXT 在 AI 光互连上游卡位硬，AI 暴露可作为核心论点之一。
```
