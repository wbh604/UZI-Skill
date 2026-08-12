"""Data source registry · v2.5.

Catalogs every data source UZI-Skill knows about with metadata: URL, which
markets/dims it covers, access method, and current health status. Used by:

1. Fetchers (to pick primary vs fallback sources)
2. Agent sub-tasks in HARD-GATE-QUALITATIVE (to pick browser URLs per dim)
3. AGENTS.md data source cheat-sheet generation

Design principles:
- Pure config, no I/O. Keeps the module cheap to import.
- Pattern mirrors `lib/investor_db.py` (list of dataclass + filter helpers).
- Registry is a hint, not truth — each fetcher still reports actual `source`
  in its return dict. If reality diverges from registry, trust the fetcher.

Tiers:
- 1 = HTTP primary — cheap, stable, belongs in fetcher fallback chains
- 2 = Playwright / browser — reliable but slow/heavy, use when tier-1 fails or
      when only JS-rendered pages work (雪球 / 问财 / 富途)
- 3 = Auxiliary — official disclosure portals, legal-source-of-truth but
      schema-heavy (SSE/SZSE/CNINFO/HKEXNews)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DataSource:
    id: str                         # stable short id, e.g. "aastocks_quote"
    name_cn: str                    # Chinese display name
    base_url: str                   # root or example endpoint
    markets: tuple[str, ...]        # "A", "H", "U"
    dims: tuple[str, ...]           # dimension keys this source can help fill
    tier: int                       # 1 HTTP primary, 2 Playwright, 3 official disclosure
    access: str                     # "http" | "akshare" | "mx_api" | "playwright" | "ddgs"
    health: str                     # "known_good" | "flaky" | "blocked_often" | "needs_browser"
    notes: str = ""


GLOBAL_MARKETS = (
    "A", "H", "U", "JP", "KR", "TW", "SG", "IN", "CA", "AU", "GB",
    "DE", "FR", "NL", "CH", "ES", "IT", "SE", "NO", "DK", "FI",
    "BE", "PT", "BR", "MX", "TH", "ID", "MY", "NZ", "ZA", "IL", "G",
)


# ═══════════════════════════════════════════════════════════════
# Tier 1 · HTTP-accessible primary sources (safe for fetcher code)
# ═══════════════════════════════════════════════════════════════
_TIER1: list[DataSource] = [
    DataSource(
        "em_push2", "东方财富 push2",
        "https://push2.eastmoney.com/api/qt/stock/get",
        ("A", "H", "U"),
        ("0_basic", "2_kline", "10_valuation", "12_capital_flow"),
        1, "http", "blocked_often",
        "2026 常被反爬拦截（大陆 / 境外均可能 Empty reply）；建议走 MX API 或 XueQiu akshare 代抓"
    ),
    DataSource(
        "em_quote", "东方财富 quote 页",
        "https://quote.eastmoney.com/",
        ("A", "H", "U"),
        ("0_basic", "2_kline"),
        1, "http", "known_good",
        "push2 挂掉时 quote 子域通常仍可用（2026 验证：200 OK）"
    ),
    DataSource(
        "em_data", "东方财富 data 子域",
        "https://data.eastmoney.com/",
        ("A",),
        ("4_peers", "7_industry", "11_governance", "12_capital_flow", "16_lhb", "15_events", "6_research"),
        1, "http", "known_good",
        "龙虎榜 / 北向 / 融资融券 / 股东户数 / 研报 / 行业板块成分（akshare board_industry_cons_em 走这里）"
    ),
    DataSource(
        "em_valuation_history", "东方财富估值历史",
        "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_VALUEANALYSIS_DET",
        ("A",),
        ("10_valuation",),
        1, "http", "known_good",
        "PE_TTM / PB_MRQ 历史序列；百度估值接口失败时用于真实历史分位 fallback"
    ),
    DataSource(
        "xq_api", "雪球 akshare backend",
        "https://stock.xueqiu.com/",
        ("A", "H"),
        ("0_basic", "1_financials", "2_kline", "15_events", "17_sentiment"),
        1, "akshare", "known_good",
        "akshare.stock_individual_basic_info_xq / stock_individual_spot_xq"
    ),
    DataSource(
        "tencent_qt", "腾讯行情 qt",
        "https://qt.gtimg.cn/",
        ("A", "H", "U"),
        ("0_basic", "2_kline"),
        1, "http", "known_good",
        "realtime quote 兜底源；格式 ~-delimited 字符串"
    ),
    DataSource(
        "sina_quote", "新浪财经行情",
        "https://finance.sina.com.cn/",
        ("A", "H", "U"),
        ("0_basic", "2_kline", "15_events"),
        1, "http", "flaky",
        "hq.sinajs.cn 老接口 2026 返 403；主页 HTML 解析仍可用"
    ),
    DataSource(
        "cninfo", "巨潮资讯",
        "http://www.cninfo.com.cn/",
        ("A",),
        ("15_events", "7_industry", "1_financials"),
        1, "http", "known_good",
        "A 股公告原文的法定披露源；akshare.stock_industry_pe_ratio 也走这里"
    ),
    DataSource(
        "hkexnews", "HKEXNews 港交所披露易",
        "https://www1.hkexnews.hk/",
        ("H",),
        ("15_events", "11_governance"),
        1, "http", "known_good",
        "港股公告的法定披露源"
    ),
    DataSource(
        "aastocks", "AASTOCKS 港股",
        "https://www.aastocks.com/",
        ("H",),
        ("0_basic", "4_peers", "12_capital_flow", "15_events"),
        1, "http", "flaky",
        "港股 PE/PB/industry/南北向核心数据源；HTML regex 抓取 + Playwright 兜底"
    ),
    DataSource(
        "cls", "财联社 7x24 电报",
        "https://www.cls.cn/",
        ("A", "H", "U"),
        ("15_events", "3_macro"),
        1, "http", "known_good",
        "事件驱动首选；催化剂与突发新闻密度最高"
    ),
    DataSource(
        "yicai", "第一财经",
        "https://www.yicai.com/",
        ("A", "H"),
        ("15_events", "3_macro", "7_industry"),
        1, "http", "known_good",
        "行业与公司新闻、宏观产业专题；适合 agent 抽取定性评语"
    ),
    DataSource(
        "wallstreetcn", "华尔街见闻",
        "https://wallstreetcn.com/",
        ("A", "H", "U"),
        ("3_macro", "17_sentiment"),
        1, "http", "flaky",
        "快讯 + 海外联动；/live 端点 2026 返 404，走主页抓最新"
    ),
    DataSource(
        "cfi", "中财网",
        "https://quote.cfi.cn/",
        ("A",),
        ("0_basic", "1_financials", "15_events"),
        1, "http", "known_good",
        "个股资料 / 公告 / 研报 HTML 兜底"
    ),
    DataSource(
        "hexun", "和讯网",
        "https://stock.hexun.com/",
        ("A",),
        ("6_research", "15_events"),
        1, "http", "known_good",
        "研报转载 + 行业点评兜底"
    ),
    DataSource(
        "163money", "网易财经",
        "https://money.163.com/",
        ("A", "U"),
        ("0_basic", "15_events"),
        1, "http", "known_good",
        "新闻聚合 + 公告转载"
    ),
    DataSource(
        "jrj", "金融界",
        "https://stock.jrj.com.cn/",
        ("A",),
        ("15_events", "7_industry"),
        1, "http", "known_good",
        "题材联动 / 盘面复盘"
    ),
    DataSource(
        "investing", "Investing.com",
        "https://www.investing.com/",
        ("U",),
        ("3_macro", "9_futures"),
        1, "http", "known_good",
        "商品 / 外汇 / 海外指数 / 宏观日历"
    ),
    DataSource(
        "mx_api", "东方财富妙想 Skills Hub",
        "https://mkapi2.dfcfs.com/finskillshub/",
        ("A", "H", "U"),
        ("0_basic", "1_financials", "15_events"),
        1, "mx_api", "known_good",
        "v2.3 新增 · 需 MX_APIKEY；官方 NLP API，自动纠错中文名"
    ),
    DataSource(
        "akshare_lhb", "akshare 龙虎榜",
        "https://akshare.akfamily.xyz/",
        ("A",),
        ("16_lhb",),
        1, "akshare", "known_good",
        "ak.stock_lhb_detail_em 等；主 LHB 数据源"
    ),
    DataSource(
        "baostock", "BaoStock",
        "http://baostock.com/",
        ("A",),
        ("2_kline",),
        1, "akshare", "known_good",
        "K 线 fallback，官方接口无 key"
    ),
    DataSource(
        "yfinance", "Yahoo Finance",
        "https://finance.yahoo.com/",
        ("U", "H"),
        ("0_basic", "1_financials", "2_kline"),
        1, "akshare", "known_good",
        "美股主源、港股兜底"
    ),
    DataSource(
        "ddgs", "DuckDuckGo 搜索",
        "https://duckduckgo.com/",
        ("A", "H", "U"),
        ("3_macro", "13_policy", "14_moat", "15_events", "17_sentiment"),
        1, "ddgs", "flaky",
        "中文搜索质量不稳定；agent 建议二次过滤 garbage patterns"
    ),
    # ── v2.13.4 新增 · 公开无 Key 源（经 curl 真实验证 2026-04-19）──
    DataSource(
        "yahoo_chart_v8", "Yahoo Finance Chart v8 (HTTP)",
        "https://query1.finance.yahoo.com/v8/finance/chart/",
        ("U", "H"),
        ("2_kline",),
        1, "http", "known_good",
        "美股/港股 K 线直接 HTTP · 格式 ?symbol=AAPL&interval=1d&range=1mo · v7/quote 已被 Yahoo 关闭需 401 · v8 仍公开"
    ),
    DataSource(
        "yahoo_equity_screener", "Yahoo Finance 全球股票筛选",
        "https://query2.finance.yahoo.com/v1/finance/screener",
        GLOBAL_MARKETS,
        ("4_peers",),
        1, "yfinance", "known_good",
        "按 Yahoo 细分行业发现全球候选；结果仍需发行人去重、币种和数据完整度校验"
    ),
    DataSource(
        "yahoo_fundamentals_timeseries", "Yahoo Finance 全球年度财务时序",
        "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/",
        GLOBAL_MARKETS,
        ("1_financials", "4_peers", "10_valuation"),
        1, "http", "known_good",
        "全球同行年度营收/利润/权益/现金流；固定 host + symbol allowlist + 12s timeout"
    ),
    DataSource(
        "yahoo_fx_chart", "Yahoo Finance 外汇 Chart",
        "https://query1.finance.yahoo.com/v8/finance/chart/JPYUSD=X",
        GLOBAL_MARKETS,
        ("4_peers",),
        1, "http", "known_good",
        "按年份计算汇率均值；原币报表值保留，换算值写入独立 *_base 字段"
    ),
    DataSource(
        "tencent_hk_quote", "腾讯港股实时 qt.gtimg.cn",
        "http://qt.gtimg.cn/q=hk00700",
        ("H",),
        ("0_basic",),
        1, "http", "known_good",
        "港股实时行情 HK00700 类格式 · 腾讯自家接口无反爬 · 国内外都通"
    ),
    DataSource(
        "coingecko_simple_price", "CoinGecko Simple Price",
        "https://api.coingecko.com/api/v3/simple/price",
        ("U",),
        ("3_macro",),
        1, "http", "known_good",
        "加密货币实时价格 · 宏观风险偏好参考 · 参数 ?ids=bitcoin,ethereum&vs_currencies=usd"
    ),
    DataSource(
        "coingecko_markets", "CoinGecko Markets",
        "https://api.coingecko.com/api/v3/coins/markets",
        ("U",),
        ("3_macro",),
        1, "http", "known_good",
        "Top 100 加密货币行情 + 市值 · 可作宏观资金流参考"
    ),
    DataSource(
        "okx_spot_tickers", "OKX 现货 tickers (API v5)",
        "https://www.okx.com/api/v5/market/tickers?instType=SPOT",
        ("U",),
        ("3_macro",),
        1, "http", "known_good",
        "OKX 国内访问不受限 · BTC/ETH/altcoin 全量现货快照 · 加密市场情绪代理"
    ),
    DataSource(
        "kucoin_stats", "KuCoin 24h 统计",
        "https://api.kucoin.com/api/v1/market/stats",
        ("U",),
        ("3_macro",),
        1, "http", "known_good",
        "参数 ?symbol=BTC-USDT · 24h 涨跌 + 成交量 · 备用加密源"
    ),
    DataSource(
        "kraken_trades", "Kraken 公开成交",
        "https://api.kraken.com/0/public/Trades",
        ("U",),
        ("3_macro",),
        1, "http", "known_good",
        "参数 ?pair=xbtusd · 近期成交流水 · 合规美金加密交易所"
    ),
    DataSource(
        "gemini_ticker", "Gemini 行情",
        "https://api.gemini.com/v2/ticker/btcusd",
        ("U",),
        ("3_macro",),
        1, "http", "known_good",
        "合规美金加密交易所 · 美国用户主场 · 数据相对干净"
    ),
    DataSource(
        "coinlore_tickers", "CoinLore 全量币种",
        "https://api.coinlore.net/api/tickers/",
        ("U",),
        ("3_macro",),
        1, "http", "known_good",
        "无分页限制 · 一次 36KB JSON · 适合加密市场全景快照"
    ),
    DataSource(
        "geckoterminal_networks", "GeckoTerminal DEX Networks",
        "https://api.geckoterminal.com/api/v2/networks",
        ("U",),
        ("3_macro",),
        1, "http", "known_good",
        "DEX 数据 · Uniswap/PancakeSwap 等 · 链上资金流参考"
    ),
    # ── v2.13.6 新增 · 期货/新闻源（curl 真实验证 2026-04-19）──
    DataSource(
        "jin10_flash", "金十数据实时快讯",
        "https://www.jin10.com/flash_newest.js",
        ("A", "H", "U"),
        ("3_macro", "13_policy", "15_events", "17_sentiment"),
        1, "http", "known_good",
        "财联社替代品 · 实时快讯 JSON · 38KB · 含国内外宏观/政策/突发/行情 · akshare 也封装为 ak.js_news()"
    ),
    DataSource(
        "em_kuaixun", "东财快讯 (kuaixun) · 类财联社",
        "https://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_50_1_.html",
        ("A", "H", "U"),
        ("15_events", "17_sentiment"),
        1, "http", "known_good",
        "东财快讯流 · 62KB · 含股票/宏观/政策/突发新闻 · 跟财联社风格相近"
    ),
    DataSource(
        "em_stock_ann", "东财上市公司公告",
        "https://np-anotice-stock.eastmoney.com/api/security/ann",
        ("A",),
        ("15_events",),
        1, "http", "known_good",
        "公告 JSON 流 · 支持 page_size + ann_type 过滤 · 替代 cninfo 做高频轮询"
    ),
    DataSource(
        "qh99_inventory", "99 期货网 · 库存/现货/基差",
        "https://www.99qh.com/",
        ("A",),
        ("8_materials", "9_futures"),
        1, "http", "known_good",
        "中国最全期货库存/仓单/现货价/基差数据 · 需 HTML 解析 · 国内期货行业核心源"
    ),
    DataSource(
        "cfachina", "中国期货业协会",
        "http://www.cfachina.org/",
        ("A",),
        ("9_futures", "13_policy"),
        1, "http", "known_good",
        "期货业政策/法规/协会公告 · 权威官方 · 国内期货政策参考"
    ),
    DataSource(
        "ths_news_today", "同花顺今日财经快讯",
        "http://news.10jqka.com.cn/today_list/",
        ("A", "H"),
        ("15_events", "17_sentiment"),
        1, "http", "known_good",
        "同花顺实时快讯列表 · 68KB HTML 解析 · 财经/行情/行业快讯聚合"
    ),
    # 腾讯期货（已有 tencent_qt tencent_hk_quote · 期货用相同 endpoint 不同参数）· 不重复登记
]

# ═══════════════════════════════════════════════════════════════
# Tier 2 · Playwright / browser-only sources
# ═══════════════════════════════════════════════════════════════
_TIER2: list[DataSource] = [
    DataSource(
        "iwencai", "问财（同花顺 NLP 筛选）",
        "https://www.iwencai.com/",
        ("A",),
        ("4_peers", "5_chain", "7_industry"),
        2, "playwright", "needs_browser",
        "NLP 条件查询：'市值>100亿 行业=半导体'；需 cookie 流程"
    ),
    DataSource(
        "ths_f10", "同花顺 F10",
        "https://stockpage.10jqka.com.cn/",
        ("A", "H"),
        ("0_basic", "4_peers", "5_chain", "11_governance", "14_moat"),
        2, "playwright", "needs_browser",
        "主营 / 股东 / 同行 / 概念板块映射，A 股信息最齐全"
    ),
    DataSource(
        "xueqiu_f10", "雪球 F10 / 讨论",
        "https://xueqiu.com/",
        ("A", "H", "U"),
        ("11_governance", "15_events", "17_sentiment"),
        2, "playwright", "needs_browser",
        "HTTP 直抓常返 403；用 Playwright 可稳定抓社区观点与公告"
    ),
    DataSource(
        "legulegu", "乐咕乐股估值历史",
        "https://legulegu.com/",
        ("A",),
        ("10_valuation", "7_industry"),
        2, "playwright", "needs_browser",
        "PE/PB 5Y 分位、行业估值；HTTP 直访返 403"
    ),
    DataSource(
        "stockstar", "证券之星",
        "https://stock.stockstar.com/",
        ("A",),
        ("6_research", "15_events"),
        2, "playwright", "needs_browser",
        "数据中心 + 研报评级；HTTP 直访返 567"
    ),
    DataSource(
        "futu", "富途牛牛",
        "https://www.futunn.com/",
        ("H", "U"),
        ("0_basic", "1_financials", "17_sentiment"),
        2, "playwright", "needs_browser",
        "港美股页面 + 社区；HTTP 直访跳 403"
    ),
    DataSource(
        "yuncaijing", "云财经龙虎榜",
        "https://www.yuncaijing.com/",
        ("A",),
        ("16_lhb",),
        2, "playwright", "flaky",
        "游资席位 / 题材热度 / 龙虎榜补源"
    ),
]

# ═══════════════════════════════════════════════════════════════
# Tier 3 · Official disclosure portals (法定源，供 agent 交叉验证)
# ═══════════════════════════════════════════════════════════════
_TIER3: list[DataSource] = [
    DataSource(
        "sse", "上海证券交易所",
        "https://www.sse.com.cn/",
        ("A",),
        ("15_events", "11_governance"),
        3, "http", "known_good",
        "上交所披露 + 上证 e 互动"
    ),
    DataSource(
        "szse", "深圳证券交易所",
        "https://www.szse.cn/",
        ("A",),
        ("15_events", "11_governance"),
        3, "http", "known_good",
        "深交所披露 + 互动易"
    ),
    DataSource(
        "csrc", "中国证监会",
        "http://www.csrc.gov.cn/",
        ("A",),
        ("13_policy",),
        3, "http", "known_good",
        "监管政策原文"
    ),
    DataSource(
        "gov_cn", "国务院政策",
        "https://www.gov.cn/zhengce/",
        ("A", "H"),
        ("13_policy", "3_macro"),
        3, "http", "known_good",
        "顶层政策文件"
    ),
    DataSource(
        "miit", "工信部",
        "https://www.miit.gov.cn/",
        ("A",),
        ("13_policy", "7_industry"),
        3, "http", "known_good",
        "制造业行业政策"
    ),
    DataSource(
        "ndrc", "发改委",
        "https://www.ndrc.gov.cn/",
        ("A",),
        ("13_policy", "3_macro"),
        3, "http", "known_good",
        "发改委政策解读"
    ),
    DataSource(
        "samr", "市场监管总局",
        "https://www.samr.gov.cn/",
        ("A",),
        ("13_policy",),
        3, "http", "known_good",
        "反垄断 / 市场监管"
    ),
    DataSource(
        "shfe", "上海期货交易所",
        "https://www.shfe.com.cn/",
        ("A",),
        ("8_materials", "9_futures"),
        3, "http", "known_good",
        "黑色 / 有色 / 贵金属 / 原油期货日报"
    ),
    DataSource(
        "dce", "大连商品交易所",
        "https://www.dce.com.cn/",
        ("A",),
        ("8_materials", "9_futures"),
        3, "http", "known_good",
        "农产品 / 化工期货"
    ),
    DataSource(
        "czce", "郑州商品交易所",
        "https://www.czce.com.cn/",
        ("A",),
        ("8_materials", "9_futures"),
        3, "http", "known_good",
        "农产品 / 能源期货"
    ),
    DataSource(
        "100ppi", "生意社现货",
        "https://www.100ppi.com/",
        ("A",),
        ("8_materials",),
        3, "http", "known_good",
        "现货价格数据库"
    ),

    # ── v2.7.3 · 权威媒体（用 ddgs site: 查询抓标题/正文片段） ──
    DataSource(
        "cnstock", "中国证券网",
        "https://www.cnstock.com/",
        ("A", "H"),
        ("15_events", "6_research", "17_sentiment", "13_policy"),
        3, "ddgs", "known_good",
        "v2.7.3 新增 · 上证 e 互动 / 新股报告 / 公司公告交叉验证。ddgs site:cnstock.com 验证返真实新闻标题"
    ),
    DataSource(
        "cs_cn", "中证网",
        "https://www.cs.com.cn/",
        ("A", "H"),
        ("15_events", "13_policy", "17_sentiment"),
        3, "ddgs", "known_good",
        "v2.7.3 新增 · 中证报权威；ddgs site:cs.com.cn 返公司/政策真实新闻"
    ),
    DataSource(
        "stcn", "证券时报",
        "https://www.stcn.com/",
        ("A", "H"),
        ("15_events", "17_sentiment", "13_policy"),
        3, "ddgs", "known_good",
        "v2.7.3 新增 · 证券时报网；ddgs site:stcn.com 返真实文章（如：腾讯控股回购）"
    ),
    DataSource(
        "nbd", "每日经济新闻",
        "https://www.nbd.com.cn/",
        ("A", "H", "U"),
        ("15_events", "17_sentiment", "18_trap", "14_moat"),
        3, "ddgs", "known_good",
        "v2.7.3 新增 · 每经网产业/公司新闻；ddgs site:nbd.com.cn 返真实新闻"
    ),

    # ── v2.7.3 · 官方宏观 + 利率环境 ──
    DataSource(
        "pbc", "中国人民银行",
        "http://www.pbc.gov.cn/",
        ("A", "H"),
        ("3_macro", "13_policy"),
        3, "ddgs", "known_good",
        "v2.7.3 新增 · 央行利率 / 货币政策原文；ddgs site:pbc.gov.cn"
    ),
    DataSource(
        "safe", "国家外汇管理局",
        "https://www.safe.gov.cn/",
        ("A", "H", "U"),
        ("3_macro", "13_policy"),
        3, "ddgs", "known_good",
        "v2.7.3 新增 · 外汇 / 跨境资金政策"
    ),
    DataSource(
        "stats_gov", "国家统计局",
        "http://www.stats.gov.cn/",
        ("A", "H"),
        ("3_macro", "7_industry"),
        3, "ddgs", "known_good",
        "v2.7.3 新增 · GDP / PMI / CPI / 工业增加值原始数据；ddgs site:stats.gov.cn"
    ),
    DataSource(
        "chinamoney", "中国货币网",
        "https://www.chinamoney.com.cn/",
        ("A",),
        ("3_macro", "12_capital_flow"),
        3, "ddgs", "known_good",
        "v2.7.3 新增 · 银行间市场 / Shibor / CFETS"
    ),
    DataSource(
        "chinabond", "中国债券信息网",
        "https://yield.chinabond.com.cn/",
        ("A",),
        ("3_macro", "10_valuation"),
        3, "http", "known_good",
        "v2.7.3 新增 · 国债收益率曲线（WACC 无风险利率锚）；首页 yield.chinabond.com.cn/ 200 OK"
    ),

    # ── v2.7.3 · 期货 / 能源 ──
    DataSource(
        "ine", "上海国际能源交易中心",
        "https://www.ine.cn/",
        ("A",),
        ("8_materials", "9_futures"),
        3, "http", "known_good",
        "v2.7.3 新增 · 原油/燃油/天然橡胶期货日报"
    ),
]


# ═══════════════════════════════════════════════════════════════
# v2.7.3 · Tier-2 社区/股吧增量（与权威媒体分层）
# ═══════════════════════════════════════════════════════════════
_TIER2_EXTRA_V273: list[DataSource] = [
    DataSource(
        "guba_em_list", "东财股吧 list 页（按股票代码）",
        "https://guba.eastmoney.com/list,{code}.html",
        ("A", "H"),
        ("17_sentiment", "18_trap", "19_contests"),
        2, "http", "known_good",
        "v2.7.3 新增 · list,{code}.html 200 OK 含真实帖子标题；600519/00700 验证可抓"
    ),
    DataSource(
        "jisilu", "集思录",
        "https://www.jisilu.cn/",
        ("A",),
        ("17_sentiment", "19_contests"),
        2, "ddgs", "flaky",
        "v2.7.3 新增 · 社区观点 / 可转债/套利；站内搜索要会员，走 ddgs site:jisilu.cn"
    ),
    DataSource(
        "fx678", "汇通财经",
        "https://www.fx678.com/",
        ("A", "U"),
        ("3_macro", "8_materials", "9_futures"),
        2, "ddgs", "flaky",
        "v2.7.3 新增 · 大宗商品 / 外汇 / 宏观快讯（列表路径要找，用 ddgs site: 查）"
    ),
    DataSource(
        "cmc", "CompaniesMarketCap",
        "https://companiesmarketcap.com/",
        ("H", "U"),
        ("0_basic", "10_valuation"),
        2, "http", "known_good",
        "v2.7.3 新增 · 英文站，港美股市值/估值 fallback；/tencent/marketcap/ 200 OK"
    ),
]


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════

SOURCES: list[DataSource] = _TIER1 + _TIER2 + _TIER2_EXTRA_V273 + _TIER3


def by_id(source_id: str) -> DataSource | None:
    return next((s for s in SOURCES if s.id == source_id), None)


def by_dim(dim_key: str) -> list[DataSource]:
    return [s for s in SOURCES if dim_key in s.dims]


def by_market(market: str) -> list[DataSource]:
    return [s for s in SOURCES if market in s.markets]


def by_tier(tier: int) -> list[DataSource]:
    return [s for s in SOURCES if s.tier == tier]


def http_sources_for(dim_key: str, market: str) -> list[DataSource]:
    """Tier-1 HTTP sources matching a dim + market. Ordered by health (known_good first)."""
    health_rank = {"known_good": 0, "flaky": 1, "blocked_often": 2, "needs_browser": 3}
    hits = [s for s in SOURCES if s.tier == 1 and market in s.markets and dim_key in s.dims]
    return sorted(hits, key=lambda s: health_rank.get(s.health, 99))


def source_health_snapshot(dim_key: str, market: str) -> dict:
    """Return a compact health snapshot for agent/report diagnostics."""
    health_rank = {"known_good": 0, "flaky": 1, "blocked_often": 2, "needs_browser": 3}
    hits = [s for s in SOURCES if market in s.markets and dim_key in s.dims]
    ordered = sorted(hits, key=lambda s: (health_rank.get(s.health, 99), s.tier, s.id))
    counts: dict[str, int] = {}
    sources = []
    for source in ordered:
        counts[source.health] = counts.get(source.health, 0) + 1
        sources.append({
            "id": source.id,
            "name_cn": source.name_cn,
            "tier": source.tier,
            "access": source.access,
            "health": source.health,
            "base_url": source.base_url,
            "notes": source.notes,
        })
    counts["total"] = len(sources)
    return {"dim": dim_key, "market": market, "counts": counts, "sources": sources}


def playwright_sources_for(dim_key: str, market: str) -> list[DataSource]:
    """Tier-2 sources requiring browser. Use when HTTP sources all fail or only JS-rendered."""
    return [s for s in SOURCES if s.tier == 2 and market in s.markets and dim_key in s.dims]


def official_sources_for(dim_key: str) -> list[DataSource]:
    """Tier-3 official disclosure sources (market-agnostic mostly)."""
    return [s for s in SOURCES if s.tier == 3 and dim_key in s.dims]


def assert_registry_sane() -> None:
    """Smoke test — called once from __main__ block. Ensures no duplicate IDs."""
    ids = [s.id for s in SOURCES]
    assert len(ids) == len(set(ids)), f"Duplicate source IDs: {set(x for x in ids if ids.count(x) > 1)}"


if __name__ == "__main__":
    assert_registry_sane()
    print(f"Registry OK · {len(SOURCES)} sources ({len(_TIER1)} tier-1, {len(_TIER2)} tier-2, {len(_TIER3)} tier-3)")
    print()
    print("Example lookups:")
    print(f"  by_dim('4_peers')          → {[s.id for s in by_dim('4_peers')]}")
    print(f"  by_market('H')             → {[s.id for s in by_market('H')]}")
    print(f"  http_sources_for('0_basic', 'H')   → {[s.id for s in http_sources_for('0_basic', 'H')]}")
    print(f"  playwright_sources_for('4_peers', 'A') → {[s.id for s in playwright_sources_for('4_peers', 'A')]}")
