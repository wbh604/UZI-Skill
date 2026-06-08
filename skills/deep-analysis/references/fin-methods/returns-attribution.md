# 收益归因 · Returns Attribution（二级市场组合）

> **改编自** `anthropics/financial-services` · `plugins/vertical-plugins/private-equity/skills/returns-analysis`，
> **适配为二级市场组合**。原文是 PE 基金的 IRR/MOIC 敏感性 + 收益桥（增长 / 多重 / 杠杆三因子归因），
> 这里替换成公开市场组合的「权重 × 个股收益」归因。

## 这是什么

把一个组合的**区间总收益**拆开，回答三个问题：

1. **谁赚的钱** —— 各持仓贡献 = 权重 × 个股区间收益（单位：百分点 pp）。
2. **哪类资产赚的** —— 按行业（可选按流派/风格）分组贡献。
3. **谁是英雄 / 谁是猪队友** —— Top3 贡献 / Top3 拖累排序，外加 vs 基准超额。

配合 UZI 已有的 `--portfolio holdings.csv` 组合功能：portfolio_runner 负责跑分 + 健康度，
本归因负责"这段时间组合涨跌从哪来"。

## 从 PE 原文到二级市场的映射

| 原文（PE returns-analysis） | 本适配（二级市场组合） |
|---|---|
| MOIC = 退出股权 / 投入股权 | 组合区间总收益率 `total_return` |
| IRR 敏感性表（entry×exit 多重） | —（二级市场用区间收益，不建多重表） |
| 收益桥：EBITDA 增长 / 多重扩张 / 债务偿还 三因子 | 收益桥：逐持仓贡献 + 行业/流派分组贡献 |
| Bull / Base / Bear 情景 | —（留给上层组合工具，本函数只做实绩归因） |
| 费用 / carry 拖累 | 不适用（公开市场无 carry） |

**核心恒等式**：`total_return = Σ(weight_i × return_pct_i)`，且
`Σ(行业分组贡献) == Σ(流派分组贡献) == total_return`（分组只是重排，不改总量）。

## 数据结构（吃 `--portfolio` 的 holdings）

参考 `lib/portfolio_runner.py` 的 holdings 行结构（ticker / weight / note），本函数再多吃两个字段：

```python
holdings = [
    {
        "ticker": "600519.SH",   # 必填
        "weight": 0.30,          # 0-1 或 0-100，自动 /100 + 归一化；缺失则等权
        "return_pct": 12.5,      # 个股区间收益率(%)；缺失 → 标注"需补价格区间"，按 0 计
        "industry": "白酒",       # 行业归因用；缺失归"未分类"
        "name": "贵州茅台",        # 展示用（缺失回退 note / ticker）
        "school": "价值",         # 可选 · 流派归因（至少一只带才触发该维度）
        "note": "白酒龙头",
    },
    ...
]
```

> **拿不到个股区间收益怎么办**：缺 `return_pct` 的持仓 `needs_price=True`、贡献按 0 计、
> 计入 `missing_return_tickers`，并在 verdict 里提示"⚠️ N 只缺区间收益需补价格"。
> 上层可先用 K 线维度（`2_kline`）补区间收益再回填。

## 调用

```python
from lib.tier1.returns_attrib import build_returns_attribution

result = build_returns_attribution(holdings, benchmark_return=6.0)  # 基准可选
```

### 返回结构

| 字段 | 说明 |
|---|---|
| `total_return` | 组合区间总收益（pp） |
| `contribution_table` | 逐持仓：weight / return_pct / contribution_pct / needs_price / note |
| `sector_attribution` | 行业归因（行业 → 权重 / 贡献 / 只数），按贡献降序 |
| `school_attribution` | 流派归因（仅当 holdings 带 school），否则空 list |
| `top_contributors` | Top3 正贡献 |
| `top_detractors` | Top3 负贡献（拖累） |
| `benchmark` | `{benchmark_return_pct, excess_return_pct, outperform}`，无基准则 `None` |
| `n_missing_return` / `missing_return_tickers` | 缺区间收益的持仓 |
| `verdict` | 一句话点评 |
| `methodology_log` | 分步骤推演日志（与其它 build_X 一致） |

## 输出范式（展示用）

```
组合区间总收益 +8.50%（vs 基准 +6.00% · 超额 +2.50pp · 跑赢）

加权贡献表：
  比亚迪    电动车  仓位30%  收益+20.0%  贡献 +6.00pp  ←
  贵州茅台   白酒   仓位40%  收益+10.0%  贡献 +4.00pp
  五粮液    白酒   仓位30%  收益 -5.0%  贡献 -1.50pp  ✕

行业归因：电动车 +6.00pp · 白酒 +2.50pp
Top 贡献：比亚迪 +6.00pp / 贵州茅台 +4.00pp
Top 拖累：五粮液 -1.50pp

一句话：组合区间总收益 +8.50%，主升由比亚迪贡献 +6.00pp，主要拖累五粮液 -1.50pp，跑赢基准 +2.50pp。
```

## 注意

- 贡献单位是**百分点 (pp)**，不是个股收益率本身（已乘权重）。
- 分组归因只是把逐持仓贡献按维度重排，加总必须等于 `total_return`（测试有断言）。
- 缺 `return_pct` 不报错，但会拉低可信度 —— verdict 明确提示需补价格区间。
- 本函数是**实绩归因**（已发生的区间收益），不做情景/敏感性预测——那是组合层面的事。
