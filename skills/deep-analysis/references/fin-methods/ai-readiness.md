# AI 就绪度 / 卡位评估 · AI Readiness (single-stock)

> **改编自 [anthropics/financial-services](https://github.com/anthropics/financial-services)
> `plugins/vertical-plugins/private-equity/skills/ai-readiness`**，
> 把原版「在 PE 组合里扫描多家 portco、按美元杠杆排序、找可复用 playbook」
> 适配成**单只个股**的「AI 暴露度 / 就绪度 / 卡位评估」，
> 并**复用 Serenity 的派生特征 `ai_chokepoint_score`** 作为「AI 卡位强度」的量化锚。

一句话定位：**评估这一家公司在 AI 浪潮里到底卡没卡位、就不就绪——
是真有 AI 真实收入/订单/产能的卡位股，还是只蹭 AI 概念标签。**

与本目录其它方法的关系：
- 与 `serenity-bottleneck.md` 同源（都用 `ai_chokepoint_score`），但角色不同：
  Serenity 是**选股/重仓裁决**（卡住才买）；本法是**就绪度体检**——
  给出强/中/弱/无评级 + 三道 gate + 杠杆点，供报告里「AI 维度」单独成块。
- 与 DCF / Comps / IC memo 互补：本法判「AI 暴露强不强」，它们判「值不值」。

---

## 原版 → 单票的映射

| 原版（PE 组合） | 单票适配 |
|---|---|
| 扫描整个组合的 portco | 评估**这一只**个股 |
| Gate①：数据在不在（能否产出干净输入） | **Gate① 是否真在 AI 产业链上**（`ai_chain_hit`）|
| Gate②：有没有 owner（管理层是否有人推） | **Gate② 是否有可验证的 AI 真实收入/订单/产能**（5_chain / 15_events / 7_industry 推断）|
| Gate③：30 天能否试点 | **Gate③ 卡位是否不可替代且可持续**（`ai_irreplaceable` + moat）|
| Step 3 跨公司按美元排序 | **N/A**（单票无跨公司排序）|
| Step 4 找 replays / 可复用 playbook | **N/A**（单票无跨公司复用）|
| Step 5 组合级 aggregate EBITDA | **N/A**（单票无组合汇总）|

三道 gate 全 yes = **「强就绪 / Go」**；任一 no = **「观察 / Wait」**并注明缺口。
这沿用原版「All three yes → Go / Any no → Wait with a note on what unblocks it」。

---

## 三道 Gate（个股版）

### Gate ① 是否真在 AI 产业链上
- 判据：`features["ai_chain_hit"]`（命中 AI 算力/终端供应链关键词）。
- 不在链上 → 评级直接「无」，AI 维度对论点**无加分（N/A）**——
  呼应原版「rank by dollars, not excitement」，不为概念兴奋买单。

### Gate ② 是否有可验证的 AI 真实收入/订单/产能
- 判据：链上 **且**（5_chain/15_events 出现订单/中标/长协/在手/产能/扩产/量产/提价/缺货/认证等证据词
  **或** 行业增速 ≥ 20% 景气）。
- 对应原版「The binding constraint is almost always data, not models」的精神：
  没有可验证的真实需求证据 = 疑似纯概念标签，gate 不过。

### Gate ③ 卡位是否不可替代且可持续
- 判据：`features["ai_irreplaceable"]`（切换成本 + 规模壁垒 ≥ 12/20），辅以 `moat_total`。
- 对应原版「Ownership is the real gate」——这里的「real gate」换成**不可替代的卡位**：
  可替代环节即便短期蹭到 AI 需求，也会被填平/抢单，不可持续。

---

## AI 暴露评级（以 `ai_chokepoint_score` 为主锚）

| 评级 | 判据 | 含义 |
|---|---|---|
| **强** | `choke ≥ 75`，或三 gate 全过且 `choke ≥ 60` | 卡位硬 + 真实需求 + 不可替代 → 强就绪，AI 可作核心论点 |
| **中** | `choke ≥ 50` 或通过 ≥ 2 gate | 在链上、部分成立，卡位待验证 |
| **弱** | 在链上但 `choke < 50` 且通过 < 2 gate | 蹭概念为主，卡位证据不足 |
| **无** | `ai_chain_hit = False` | 不在 AI 链上，AI 维度 N/A |

> 评级以 `ai_chokepoint_score`（Serenity 四因子：AI 链命中 × 不可替代 × 小盘弹性 × 需求拐点）
> 为单变量主锚，gate 通过数作为校验——**不被便宜估值/高成长干扰**（沿用 Serenity 设计原则）。

---

## Top AI 杠杆点

从行业 + 供应链 + 事件文本推断 **top 2-3 个 AI 杠杆点**，分两类立场：
- **卡位型**（处于 AI 算力/终端供应链关键环节）：
  算力/AI 芯片 · 光互连/光模块 · 存储/HBM · 供电/散热 · 互连/连接器/PCB · AI 终端光学(AR/VR)
- **赋能型**（AI 提升自身业务效率/产品力）：
  AI 应用/软件 · AI 赋能传统业务

---

## 报告输出区块规范

供 deep-analysis 报告直接调用，按以下输出：

1. **AI 暴露评级**：强/中/弱/无 + `ai_chokepoint_score` + 评级说明
2. **三道 Gate**：逐条 pass/fail + 依据
3. **裁决**：Go · 强就绪 / Wait · 观察（含 `gaps` 缺口清单）
4. **Top AI 杠杆点**：类别 + 命中关键词 + 卡位/赋能立场
5. **一句话结论**
6. **组合维度**：跨公司排序 / replays / 组合 EBITDA → **N/A**（单票不适用，注明而非删空）

调用：

```python
from lib.tier1.ai_readiness import build_ai_readiness
result = build_ai_readiness(features, raw)   # features 来自 extract_features
```

返回 dict 含：`rating / rating_note / ai_chokepoint_score / gates / gates_passed /
verdict / gaps / leverage_points / conclusion / methodology_log`，
以及 `cross_portfolio_ranking / replays / aggregate_ebitda`（均 N/A）。

---

## 重要原则（继承自原版 Important Notes）

- **看证据，不看兴奋。** 评级以卡位强度量化锚为主，纯概念标签不给分。
- **约束几乎总是「真实需求/卡位」，而非「AI 故事」。** Gate② 没有订单/产能/景气证据 = 不过。
- **不可替代才是真 gate。** 可替代环节蹭到的 AI 需求不可持续，落「中/弱」而非「强」。
- **组合相关项一律 N/A 而非删空。** 单票语境下明确标注「不适用」，避免被误读为遗漏。
