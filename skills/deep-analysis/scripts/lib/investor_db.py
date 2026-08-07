"""50 贤评审团元数据 · 每位投资者的 ID / 流派 / 关注字段白名单 / DiceBear seed.

详细方法论和评分逻辑在 skills/investor-panel/references/group-{a..g}.md 里。
"""
from __future__ import annotations

# Field whitelist convention — these are dimension keys from dimensions.json.
ALL_DIMS = [f"{i}_" for i in range(20)]

INVESTORS = [
    # ──────────── A: 经典价值派 ────────────
    {"id": "buffett",   "name": "巴菲特",     "en": "Warren Buffett",     "group": "A", "fields": ["1_financials", "10_valuation", "11_governance", "14_moat"], "source": "Berkshire Hathaway Letters", "avatar_seed": "Buffett-Owl-Glasses"},
    {"id": "graham",    "name": "格雷厄姆",   "en": "Benjamin Graham",    "group": "A", "fields": ["1_financials", "10_valuation"], "source": "The Intelligent Investor (1949)", "avatar_seed": "Graham-Bowtie"},
    {"id": "fisher",    "name": "费雪",       "en": "Philip Fisher",      "group": "A", "fields": ["1_financials", "4_peers", "11_governance", "14_moat"], "source": "Common Stocks and Uncommon Profits (1958)", "avatar_seed": "Fisher-Pipe"},
    {"id": "munger",    "name": "芒格",       "en": "Charlie Munger",     "group": "A", "fields": ["1_financials", "10_valuation", "11_governance", "14_moat"], "source": "Poor Charlie's Almanack", "avatar_seed": "Munger-Books"},
    {"id": "templeton", "name": "邓普顿",     "en": "John Templeton",     "group": "A", "fields": ["10_valuation", "3_macro"], "source": "Investing the Templeton Way", "avatar_seed": "Templeton-Globe"},
    {"id": "klarman",   "name": "卡拉曼",     "en": "Seth Klarman",       "group": "A", "fields": ["10_valuation", "11_governance", "15_events"], "source": "Margin of Safety (1991)", "avatar_seed": "Klarman-Vault"},

    # ──────────── B: 成长投资派 (4 经典 + 5 新晋 VC = 9 人) ────────────
    {"id": "lynch",     "name": "彼得·林奇",   "en": "Peter Lynch",        "group": "B", "fields": ["1_financials", "7_industry", "10_valuation"], "source": "One Up on Wall Street (1989)", "avatar_seed": "Lynch-Tie"},
    {"id": "oneill",    "name": "欧奈尔",     "en": "William O'Neil",     "group": "B", "fields": ["1_financials", "2_kline", "12_capital_flow", "15_events"], "source": "How to Make Money in Stocks (CANSLIM)", "avatar_seed": "Oneill-Chart"},
    {"id": "thiel",     "name": "彼得·蒂尔",   "en": "Peter Thiel",        "group": "B", "fields": ["4_peers", "7_industry", "14_moat"], "source": "Zero to One (2014)", "avatar_seed": "Thiel-Suit"},
    {"id": "wood",      "name": "木头姐",     "en": "Cathie Wood",        "group": "B", "fields": ["7_industry", "13_policy", "14_moat"], "source": "ARK Big Ideas Annual", "avatar_seed": "CathieWood-Curls"},
    # v3.7.0 · 5 位新晋科技/创新派 VC/投资人
    {"id": "andreessen","name": "马克·安德森", "en": "Marc Andreessen",   "group": "B", "tier": "new_gen", "fields": ["7_industry", "14_moat", "13_policy"], "source": "a16z Blog · Techno-Optimist Manifesto (2023)", "avatar_seed": "Andreessen-Bald"},
    {"id": "gurley",    "name": "比尔·格利",  "en": "Bill Gurley",        "group": "B", "tier": "new_gen", "fields": ["7_industry", "14_moat", "1_financials"], "source": "Above the Crowd · Benchmark", "avatar_seed": "Gurley-Tall"},
    {"id": "naval",     "name": "纳瓦尔",     "en": "Naval Ravikant",     "group": "B", "tier": "new_gen", "fields": ["14_moat", "11_governance", "7_industry"], "source": "The Almanack of Naval Ravikant", "avatar_seed": "Naval-Beard"},
    {"id": "gerstner",  "name": "布拉德·格斯特纳","en": "Brad Gerstner",   "group": "B", "tier": "new_gen", "fields": ["7_industry", "1_financials", "10_valuation"], "source": "Altimeter Quarterly Letters", "avatar_seed": "Gerstner-Glasses"},
    {"id": "chamath",   "name": "查马斯",     "en": "Chamath Palihapitiya","group": "B", "tier": "new_gen", "fields": ["7_industry", "12_capital_flow", "17_sentiment"], "source": "Social Capital Letters / All-In Podcast", "avatar_seed": "Chamath-Vest"},

    # ──────────── C: 宏观对冲派 ────────────
    {"id": "soros",     "name": "索罗斯",     "en": "George Soros",       "group": "C", "fields": ["3_macro", "12_capital_flow", "17_sentiment"], "source": "The Alchemy of Finance (1987)", "avatar_seed": "Soros-Mustache"},
    {"id": "dalio",     "name": "达里奥",     "en": "Ray Dalio",          "group": "C", "fields": ["3_macro", "13_policy"], "source": "Principles (2017)", "avatar_seed": "Dalio-Suit"},
    {"id": "marks",     "name": "霍华德·马克斯", "en": "Howard Marks",       "group": "C", "fields": ["10_valuation", "17_sentiment", "3_macro"], "source": "The Most Important Thing", "avatar_seed": "Marks-Memos"},
    {"id": "druck",     "name": "德鲁肯米勒", "en": "Stanley Druckenmiller","group": "C", "fields": ["3_macro", "12_capital_flow"], "source": "Lost Tree Club Speech 2015", "avatar_seed": "Druckenmiller-Bald"},
    {"id": "robertson", "name": "罗伯逊",     "en": "Julian Robertson",   "group": "C", "fields": ["4_peers", "1_financials"], "source": "Tiger Management Letters", "avatar_seed": "Robertson-Tiger"},
    # v3.7.0 · 2 位做空猎手 (做空也是宏观判断 · 不另建派)
    {"id": "burry",     "name": "迈克尔·伯利", "en": "Michael Burry",     "group": "C", "mandate": "short", "tier": "new_gen", "fields": ["3_macro", "10_valuation", "17_sentiment", "18_trap"], "source": "Scion Asset Management 13F + X @michaeljburry", "avatar_seed": "Burry-Plaid"},
    {"id": "chanos",    "name": "吉姆·查诺斯", "en": "Jim Chanos",        "group": "C", "mandate": "short", "tier": "new_gen", "fields": ["11_governance", "1_financials", "18_trap"], "source": "Kynikos · 30 Years of Short Selling", "avatar_seed": "Chanos-Suit"},

    # ──────────── D: 技术趋势派 ────────────
    {"id": "livermore", "name": "利弗莫尔",   "en": "Jesse Livermore",    "group": "D", "fields": ["2_kline", "15_events"], "source": "Reminiscences of a Stock Operator (1923)", "avatar_seed": "Livermore-Hat"},
    {"id": "minervini", "name": "米内尔维尼", "en": "Mark Minervini",     "group": "D", "fields": ["2_kline", "1_financials"], "source": "Trade Like a Stock Market Wizard", "avatar_seed": "Minervini-Trophy"},
    {"id": "darvas",    "name": "达瓦斯",     "en": "Nicolas Darvas",     "group": "D", "fields": ["2_kline"], "source": "How I Made $2,000,000 (1960)", "avatar_seed": "Darvas-Box"},
    {"id": "gann",      "name": "江恩",       "en": "William Gann",       "group": "D", "fields": ["2_kline"], "source": "Truth of the Stock Tape (1923)", "avatar_seed": "Gann-Square"},

    # ──────────── E: 中国价投/公募派 ────────────
    {"id": "duan",      "name": "段永平",     "en": "Duan Yongping",      "group": "E", "fields": ["1_financials", "10_valuation", "11_governance", "14_moat"], "source": "段永平投资问答录", "avatar_seed": "Duan-Apple"},
    {"id": "zhangkun",  "name": "张坤",       "en": "Zhang Kun",          "group": "E", "fields": ["1_financials", "14_moat"], "source": "易方达蓝筹精选季报", "avatar_seed": "ZhangKun-Glasses"},
    {"id": "zhushaoxing","name": "朱少醒",    "en": "Zhu Shaoxing",       "group": "E", "fields": ["1_financials", "7_industry"], "source": "富国天惠成长年报", "avatar_seed": "Zhu-Notebook"},
    {"id": "xiezhiyu",  "name": "谢治宇",     "en": "Xie Zhiyu",          "group": "E", "fields": ["1_financials", "10_valuation"], "source": "兴全合润季报", "avatar_seed": "Xie-Calc"},
    {"id": "fengliu",   "name": "冯柳",       "en": "Feng Liu",           "group": "E", "fields": ["10_valuation", "17_sentiment", "15_events"], "source": "雪球《弱者体系》", "avatar_seed": "Feng-Yin"},
    {"id": "dengxiaofeng","name":"邓晓峰",    "en": "Deng Xiaofeng",      "group": "E", "fields": ["1_financials", "5_chain", "7_industry"], "source": "高毅晓峰系列季报", "avatar_seed": "Deng-Cycle"},
    # v3.7.0 · 高瓴张磊 · "做时间的朋友" · 长期主义代表
    {"id": "zhang_lei", "name": "张磊",       "en": "Zhang Lei (Hillhouse)","group": "E", "tier": "new_gen", "fields": ["14_moat", "7_industry", "1_financials", "11_governance"], "source": "《价值》 · 高瓴资本", "avatar_seed": "ZhangLei-Hillhouse"},

    # ──────────── F: A 股游资派 (22 人 = 17 经典 + 5 新晋) ────────────
    {"id": "zhang_mz",   "name": "章盟主",     "group": "F", "tier": "legend", "fields": ["2_kline", "12_capital_flow", "16_lhb"], "avatar_seed": "ZhangMZ-Cigar"},
    {"id": "sun_ge",     "name": "孙哥",       "group": "F", "tier": "legend", "fields": ["2_kline", "16_lhb"], "avatar_seed": "SunGe-Shades"},
    {"id": "zhao_lg",    "name": "赵老哥",     "group": "F", "tier": "legend", "fields": ["2_kline", "15_events", "16_lhb"], "avatar_seed": "ZhaoLG-Hoodie"},
    {"id": "fs_wyj",     "name": "佛山无影脚", "group": "F", "tier": "legend", "fields": ["2_kline", "16_lhb"], "avatar_seed": "FSWYJ-Mask"},
    {"id": "yangjia",    "name": "炒股养家",   "group": "F", "tier": "legend", "fields": ["2_kline", "17_sentiment"], "avatar_seed": "YangJia-Beanie"},
    {"id": "chen_xq",    "name": "陈小群",     "group": "F", "tier": "new_gen","fields": ["2_kline", "15_events", "16_lhb"], "avatar_seed": "ChenXQ-Cap"},
    {"id": "hu_jl",      "name": "呼家楼",     "group": "F", "tier": "new_gen","fields": ["16_lhb", "12_capital_flow"], "avatar_seed": "HuJL-Suit"},
    {"id": "fang_xx",    "name": "方新侠",     "group": "F", "tier": "new_gen","fields": ["2_kline", "12_capital_flow"], "avatar_seed": "FangXX-Glasses"},
    {"id": "zuoshou",    "name": "作手新一",   "group": "F", "tier": "new_gen","fields": ["2_kline", "16_lhb"], "avatar_seed": "ZuoShou-Wand"},
    {"id": "xiao_ey",    "name": "小鳄鱼",     "group": "F", "tier": "new_gen","fields": ["1_financials", "2_kline", "16_lhb"], "avatar_seed": "XiaoEY-Croc"},
    {"id": "jiao_yy",    "name": "交易猿",     "group": "F", "tier": "new_gen","fields": ["2_kline", "12_capital_flow", "16_lhb"], "avatar_seed": "JiaoYY-Monkey"},
    {"id": "mao_lb",     "name": "毛老板",     "group": "F", "tier": "new_gen","fields": ["2_kline", "7_industry", "16_lhb"], "avatar_seed": "MaoLB-Tie"},
    {"id": "xiao_xian",  "name": "消闲派",     "group": "F", "tier": "new_gen","fields": ["2_kline", "16_lhb"], "avatar_seed": "XiaoXian-Tea"},
    {"id": "lasa",       "name": "拉萨天团",   "group": "F", "tier": "regional","fields": ["16_lhb", "17_sentiment"], "avatar_seed": "Lasa-Yak"},
    {"id": "chengdu",    "name": "成都帮",     "group": "F", "tier": "regional","fields": ["2_kline", "16_lhb"], "avatar_seed": "Chengdu-Panda"},
    {"id": "sunan",      "name": "苏南帮",     "group": "F", "tier": "regional","fields": ["16_lhb"], "avatar_seed": "Sunan-Group"},
    {"id": "ningbo_st",  "name": "宁波桑田路", "group": "F", "tier": "regional","fields": ["2_kline", "16_lhb"], "avatar_seed": "Ningbo-Wave"},
    # 2025 新晋
    {"id": "liuyi_zl",   "name": "六一中路",   "group": "F", "tier": "new_2025","fields": ["2_kline", "15_events", "16_lhb"], "avatar_seed": "LiuYi-Drone"},
    {"id": "liu_sh",     "name": "流沙河",     "group": "F", "tier": "new_2025","fields": ["2_kline", "16_lhb"], "avatar_seed": "LiuSH-River"},
    {"id": "gu_bl",      "name": "古北路",     "group": "F", "tier": "new_2025","fields": ["16_lhb", "12_capital_flow"], "avatar_seed": "GuBL-Coat"},
    {"id": "bj_cj",      "name": "北京炒家",   "group": "F", "tier": "new_2025","fields": ["2_kline", "15_events", "16_lhb"], "avatar_seed": "BJCJ-Boss"},
    {"id": "wang_zr",    "name": "瑞鹤仙",     "group": "F", "tier": "new_2025","fields": ["2_kline", "16_lhb"], "avatar_seed": "RuiHe-Crane"},
    {"id": "xin_dd",     "name": "鑫多多",     "group": "F", "tier": "new_2025","fields": ["2_kline", "15_events", "16_lhb"], "avatar_seed": "XinDD-Star"},
    # v3.9.0 · 股海贼王 · 淘股吧十年实盘 (2016-02 起 · 33 万→3000 万+) · 从其 8951 笔
    # 真实交易流水 + 5069 条发言蒸馏 (docs/ghzw-dossier.md) · 超短接力 + 题材主线 + 格局票
    {"id": "ghzw",       "name": "股海贼王",   "group": "F", "tier": "flagship","fields": ["2_kline", "15_events", "16_lhb", "7_industry", "17_sentiment"], "source": "淘股吧十年实盘帖 · 8951 笔交割单蒸馏", "avatar_seed": "GHZW-Pirate"},

    # ──────────── G: 量化系统派 ────────────
    {"id": "simons",    "name": "西蒙斯",     "en": "Jim Simons",         "group": "G", "fields": ["2_kline", "9_futures"], "source": "The Man Who Solved the Market", "avatar_seed": "Simons-Beard"},
    {"id": "thorp",     "name": "索普",       "en": "Ed Thorp",           "group": "G", "fields": ["10_valuation", "1_financials"], "source": "A Man for All Markets", "avatar_seed": "Thorp-Cards"},
    {"id": "shaw",      "name": "大卫·肖",    "en": "David Shaw",         "group": "G", "fields": ["1_financials", "2_kline", "10_valuation"], "source": "More Money Than God (Mallaby)", "avatar_seed": "Shaw-Code"},
    # v3.7.0 · Cliff Asness · 因子量化 / 价值因子代表
    {"id": "asness",    "name": "克利夫·阿斯尼斯","en": "Cliff Asness",     "group": "G", "tier": "new_gen", "fields": ["10_valuation", "1_financials", "2_kline"], "source": "AQR Capital · Quality Minus Junk / Value-Momentum-Profitability", "avatar_seed": "Asness-Tweet"},

    # ──────────── H: 科技领袖派 / AI CEO (4 人 · v3.7.0) ────────────
    # v3.7.0 · 4 位 AI 时代的 CEO/投资人 · 自带行业 thesis + 持仓视角
    {"id": "jensen_huang", "name": "黄仁勋",     "en": "Jensen Huang",            "group": "H", "tier": "new_gen", "fields": ["7_industry", "5_chain", "14_moat", "4_peers"], "source": "GTC Keynotes / NVDA Earnings Calls", "avatar_seed": "Jensen-Leather"},
    {"id": "musk",         "name": "马斯克",     "en": "Elon Musk",               "group": "H", "tier": "new_gen", "fields": ["7_industry", "14_moat", "13_policy", "15_events"], "source": "TSLA Master Plan / X @elonmusk", "avatar_seed": "Musk-Rocket"},
    {"id": "altman",       "name": "山姆·奥特曼", "en": "Sam Altman",             "group": "H", "tier": "new_gen", "fields": ["7_industry", "14_moat", "5_chain", "11_governance"], "source": "OpenAI Blog / Y Combinator Posts", "avatar_seed": "Altman-Glasses"},
    {"id": "saylor",       "name": "迈克尔·塞勒", "en": "Michael Saylor",         "group": "H", "tier": "new_gen", "fields": ["3_macro", "10_valuation", "13_policy", "17_sentiment"], "source": "MSTR Earnings + X @saylor · BTC Treasury Strategy", "avatar_seed": "Saylor-Bitcoin"},

    # ──────────── I: AI 卡位/瓶颈猎手 (重磅角色 · 独立成组) ────────────
    # Serenity (@aleabitoreddit) · 前 AI 研究科学家 / 前 RISC-V 基金会成员 / 光通信工程师
    # 方法论：AI 产业链「卡脖子/瓶颈点」—— 不买龙头，专挑最难替代的二三线上游小盘
    {"id": "serenity",     "name": "Serenity",   "en": "Serenity (@aleabitoreddit)", "group": "I", "tier": "flagship", "fields": ["5_chain", "7_industry", "14_moat", "13_policy", "15_events"], "source": "serenity-alpha skill / X @aleabitoreddit", "avatar_seed": "Serenity-Chip"},
]


def by_id(investor_id: str) -> dict | None:
    return next((i for i in INVESTORS if i["id"] == investor_id), None)


def by_group(group: str) -> list[dict]:
    return [i for i in INVESTORS if i["group"] == group]


def all_ids() -> list[str]:
    return [i["id"] for i in INVESTORS]


def assert_count() -> None:
    expected = 66  # v3.9.0 · 65 + 股海贼王 (F 组第 24 人 · 淘股吧十年实盘蒸馏)
    assert len(INVESTORS) == expected, f"Expected {expected} investors, got {len(INVESTORS)}"


# Backwards-compat alias
assert_50 = assert_count


if __name__ == "__main__":
    assert_50()
    from collections import Counter
    print("Total:", len(INVESTORS))
    print("By group:", Counter(i["group"] for i in INVESTORS))
