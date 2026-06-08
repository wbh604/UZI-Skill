# 财报前预览 · Earnings Preview Method

> 改编自 **anthropics/financial-services** `equity-research/earnings-preview`，
> 移植进 UZI-Skill 并适配 A股 / 港股 / 美股多市场。
>
> 一句话定位：**在公司披露季报之前**，搭好"该盯什么、会怎么动"的前瞻框架——
> 一致预期对照、行业观察指标、Bull/Base/Bear 三情景、催化剂清单、预期波幅。

与本目录其它方法的关系：
- `research_workflow.build_earnings_analysis` 是**财报后** beat/miss 解读（"发生了什么"）。
- 本方法是它的**财报前镜像**（"接下来盯什么"）——同样 `build_X(features, raw_data) -> dict`
  + `methodology_log` 风格，纯函数、无外部 IO。
- DCF / Comps 是估值方法；本方法是**事件前定位**方法，输出可喂给交易/仓位决策。

实现：`skills/deep-analysis/scripts/lib/tier1/earnings_preview.py`
→ `build_earnings_preview(features, raw_data) -> dict`

---

## 设计原则（沿用本目录 CRITICAL CONSTRAINTS）

1. **可审计**：每步留 `methodology_log`，记录"凭什么给这个共识/情景/波幅"。
2. **来源透明**：一致预期能从 `6_research` 拿到的标来源；拿不到的**显式标注「需 web 补充」**，绝不静默编造。
3. **可证伪**：每个情景都配明确**触发条件**——什么发生才走这个情景。
4. **多市场自适应**：观察指标按行业、隐含波动按市场（A 股无个股期权）切换。

---

## 五步法

### ① 一致预期对照 Consensus Table
- EPS：优先 `features.consensus_eps_2026`（来自 `6_research` 一致预期）。
- 营收：`6_research` 有则用；无则用历史 3 年 CAGR 外推占位，并标「需 web 补充」。
- 卖方目标价 / 覆盖家数 / 买入率：从 `6_research` 派生。
- 输出：`consensus_table`（每行带 `source`）+ `consensus_notes`（缺口清单）。
- **A 股适配**：`6_research` 拿得到的就用，拿不到的标「需 web 补充」。

### ② 行业观察指标 Watch Metrics（按行业分类）
财报最该盯的运营指标随行业不同：

| 行业 | 关注指标 |
|---|---|
| 软件 / SaaS | ARR / 经常性收入、NRR 净留存、RPO、付费客户数 |
| 零售 / 消费 | 同店销售 SSSG、客流、客单价、线上占比 |
| 工业 / 制造 | 在手订单 backlog、book-to-bill、量 vs 价 |
| 金融 | 净息差 NIM、不良/拨备、信贷增速、AUM |
| 医药 | 核心品种放量、处方量、集采影响、管线 |
| **白酒（A 股）** | 动销、渠道库存、吨价/提价、合同负债（预收） |
| **光模块（A 股）** | 800G/1.6T 出货量、高端占比、毛利率、大客户能见度 |
| **新能源（A 股）** | 装机/出货 GW、单位盈利、产能利用率、原料传导 |
| 半导体 / 汽车 | 产能利用率/ASP/库存周期、销量/单车 ASP |

未命中行业 → 落到通用默认（营收 vs 共识 / 毛利率趋势 / 经营现金流 / 指引）。

### ③ Bull / Base / Bear 三情景
基于**历史营收增速 + 毛利率趋势**：
- Base 增速 = 历史 3yCAGR 与最近一期增速的均值；Bull = Base+8pt，Bear = Base−8pt。
- 营收区间 = 最新营收 × (1+增速)；EPS 用毛利杠杆放大（Bull ×1.12 / Base ×1.0 / Bear ×0.85）。
- 每个情景配：**触发条件** + **毛利率假设** + **历史财报后股价反应**（用年化波动 ÷ √252 近似单日，标注可 web 核对）。

### ④ 催化剂清单 Catalyst Checklist
3-5 个决定财报日股价反应的看点：
1. 营收/EPS vs 一致预期（及 buy-side whisper number，可 web 补充）。
2. 前瞻指引 vs 共识（买方更看指引而非当期数字）。
3. 行业头号运营指标（②的第一项，领先利润表）。
4. 毛利率方向 + 管理层归因。
5. 战略/叙事变化（并购、回购、新品、产能、诉讼）——事件流命中才加。

### ⑤ 预期波幅 Implied Move
- **A 股个股**：多数无期权 → 标注"A 股无个股期权，用历史财报日波动代替"，
  年化波动 ÷ √252 给单日 ±幅度。
- **美股 / 港股**：可用财报到期 ATM straddle 反推期权隐含波动（需 web 补充期权链），
  历史波动作下限参考。

---

## 返回结构

```python
{
  "method": "Earnings Preview (pre-earnings)",
  "company": {"name", "code", "industry", "market"},
  "report_quarter": "2026 Q2",
  "consensus_table": [{"metric", "consensus", "yoy_pct", "source"}, ...],
  "consensus_notes": ["...需 web 补充..."],
  "watch_metrics": {"sector": "光模块", "metrics": [...]},
  "scenarios": [  # bull / base / bear 三项齐全
    {"scenario", "label", "revenue_yi", "revenue_growth_pct",
     "eps", "gross_margin_assumption", "triggers", "expected_stock_reaction"},
  ],
  "catalyst_checklist": [{"item", "why", "importance"}, ...],
  "implied_move": {"method", "options_available", "implied_move_pct",
                   "historical_proxy_pct", "note"},
  "methodology_log": [...],
}
```

---

## 测试

`scripts/tests/test_tier1_earnings_preview.py`：断言三情景齐全 + 增速/EPS 单调、
行业指标映射、一致预期缺失标注、A 股 vs 美股隐含波动分支、空输入鲁棒性。
