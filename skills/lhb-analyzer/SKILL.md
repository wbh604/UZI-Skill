---
name: lhb-analyzer
description: 龙虎榜深度分析器。识别游资席位、判断机构 vs 游资博弈、对照同板块龙虎榜找辨识度龙头。当用户问"谁在买这只票/最近龙虎榜怎么样/X游资有没有上榜/这是不是X的票"时使用。
version: 3.8.0
author: FloatFu-true
license: MIT
metadata:
  hermes:
    tags: [finance, a-share, lhb, hot-money, market-microstructure]
    related_skills: [deep-analysis]
---

# 龙虎榜深度分析

## 调用上下文

输入：股票代码或个股名
输出：龙虎榜分析 + 游资识别 + 同板块对比

## 数据流

1. 调用 `scripts/fetch_lhb.py {ticker}` 拿到原始龙虎榜数据
2. 调用 `lib/seat_db.py::match_seats_in_lhb()` 识别游资席位
3. 用 `lib/seat_db.py::is_in_range()` 判断该游资是否在射程内
4. 拉取同板块龙虎榜对比（找辨识度龙头）

## 输出 markdown 结构

```markdown
# {name} ({ticker}) 龙虎榜分析

## 📅 近 30 天上榜 X 次

(列表)

## 🐉 识别到的游资 (Y 位)

| 游资 | 风格 | 在不在射程 | 买入 / 卖出 |
|---|---|---|---|
| 章盟主 | 大资金趋势 | ✅ 在射程 | 买 1.2 亿 |
| 佛山无影脚 | 一日游 | ❌ 不在 | 卖 0.3 亿 (反向预警) |

## ⚖️ 机构 vs 游资

- 机构净买入: ¥X 亿
- 游资净买入: ¥Y 亿
- 主导方: {机构 / 游资}

## 🏆 同板块辨识度龙头

| 排名 | 代码 | 名称 | 上榜次数 | 累计涨幅 |
|---|---|---|---|---|
| 1 | ... | ... | ... | ... |

本股在板块中的位置: 第 N

## 💡 结论一句话

"这是一只机构主导 + 章盟主格局票，板块辨识度排第 2，可以跟。"
```

## 参考资料

详细的 22 位游资席位百科见 `references/seat-encyclopedia.md`。
