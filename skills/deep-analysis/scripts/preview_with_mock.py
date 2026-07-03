"""Generate a fully-populated mock report to preview the HTML template.

Usage: python scripts/preview_with_mock.py
Output: reports/MOCK_{date}/full-report.html
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from lib.cache import write_task_output  # noqa: E402
from lib.investor_db import INVESTORS  # noqa: E402

TICKER = "MOCK.SZ"

# ── Mock raw_data with FULL 19-dimension KPIs ──────────────────
raw_data = {
    "ticker": TICKER,
    "name": "水晶光电",
    "market": "A",
    "fetched_at": datetime.now().isoformat(),
    "dimensions": {
        "0_basic": {"data": {"code": TICKER, "name": "水晶光电", "industry": "光学光电",
                             "market_cap": "258.6亿", "price": 18.56, "change_pct": 2.32,
                             "pe_ttm": 42.3, "pb": 4.12,
                             "one_liner": "国内精密光学薄膜龙头，AR/AI 眼镜核心供应商，苹果产业链二供身份加持。"},
                    "source": "akshare:em", "fallback": False},
        "1_financials": {"data": {
            "roe": "18.7%", "net_margin": "21.4%", "revenue_growth": "+28%", "ocf": "12.3亿",
            "roe_history": [12.4, 14.1, 15.8, 16.2, 17.5, 18.7],
            "revenue_history": [21.5, 25.8, 28.6, 32.1, 38.4, 49.2],
            "net_profit_history": [4.2, 5.1, 5.9, 6.8, 8.3, 10.5],
            "financial_years": ["2020", "2021", "2022", "2023", "2024", "25Q1"],
            "dividend_years": ["2020", "2021", "2022", "2023", "2024"],
            "dividend_amounts": [1.2, 1.5, 2.0, 2.5, 3.0],
            "dividend_yields": [0.8, 1.0, 1.4, 1.8, 2.1],
            "financial_health": {
                "current_ratio": 2.4, "debt_ratio": 28.5, "ocf_to_ni": 118, "roic": 22.3,
            },
        }, "source": "akshare:financial_abstract", "fallback": False},
        "2_kline": {"data": (lambda: {
            "stage": "Stage 2 初期", "ma_align": "多头排列", "macd": "金叉水上", "rsi": "62",
            "close_60d": (lambda cs: cs)([15.2, 15.4, 15.1, 15.0, 14.8, 14.9, 15.2, 15.5, 15.7, 16.0, 16.2, 15.9, 15.7, 16.0, 16.3, 16.5, 16.8, 17.0, 16.8, 16.5, 16.7, 17.0, 17.2, 17.5, 17.3, 17.0, 17.2, 17.5, 17.8, 17.5, 17.2, 17.4, 17.6, 17.8, 17.9, 18.0, 17.8, 17.5, 17.6, 17.8, 18.0, 18.2, 18.0, 17.8, 18.1, 18.3, 18.5, 18.3, 18.1, 18.4, 18.2, 18.0, 18.2, 18.4, 18.6, 18.4, 18.2, 18.5, 18.7, 18.56]),
            "candles_60d": [
                {"date": f"2026-02-{str((i%28)+1).zfill(2)}" if i < 28 else f"2026-03-{str((i-28+1)).zfill(2)}" if i < 58 else f"2026-04-{str(i-58+1).zfill(2)}",
                 "open": round(15 + i*0.06 + (0.3 if i%3==0 else -0.2),2),
                 "close": round(15 + i*0.06 + (0.4 if i%2==0 else -0.25),2),
                 "high": round(15 + i*0.06 + 0.5,2),
                 "low": round(15 + i*0.06 - 0.35,2)} for i in range(60)
            ],
            "ma20_60d": [None]*19 + [round(15.5 + i*0.05, 2) for i in range(41)],
            "ma60_60d": [None]*59 + [17.2],
            "kline_stats": {"beta": "0.92", "volatility": "28.4%", "max_drawdown": "-18.6%", "ytd_return": "+14.2%"},
        })(), "source": "akshare:zh_a_hist", "fallback": False},
        "3_macro": {"data": {"rate_cycle": "降息周期", "fx_trend": "人民币偏弱", "geo_risk": "中性", "commodity": "周期底部"},
                    "source": "web_search", "fallback": True},
        "4_peers": {"data": {
            "rank": "行业第 2", "gross_margin_vs": "+4pp", "roe_vs": "+6pp", "growth_vs": "+12pp",
            "peer_comparison": [
                {"name": "毛利率 %", "self": 38.5, "peer": 34.2},
                {"name": "ROE %", "self": 18.7, "peer": 12.3},
                {"name": "营收增速 %", "self": 28, "peer": 16},
                {"name": "净利率 %", "self": 21.4, "peer": 15.8},
            ],
            "peer_table": [
                {"name": "水晶光电", "pe": "42.3", "pb": "4.12", "roe": "18.7%", "revenue_growth": "+28%", "is_self": True},
                {"name": "蓝特光学", "pe": "38.5", "pb": "3.80", "roe": "15.2%", "revenue_growth": "+22%"},
                {"name": "舜宇光学", "pe": "36.2", "pb": "3.45", "roe": "16.8%", "revenue_growth": "+19%"},
                {"name": "欧菲光",   "pe": "28.4", "pb": "2.10", "roe": "8.5%",  "revenue_growth": "+12%"},
                {"name": "联创电子", "pe": "32.1", "pb": "2.85", "roe": "10.3%", "revenue_growth": "+15%"},
                {"name": "永新光学", "pe": "40.5", "pb": "3.95", "roe": "14.2%", "revenue_growth": "+18%"},
            ],
        }, "source": "akshare:board_industry", "fallback": False},
        "5_chain": {"data": {
            "upstream": "光学薄膜原片 (台厂主导)",
            "downstream": "苹果 / Meta / 字节",
            "client_concentration": "前五 65%",
            "supplier_concentration": "前五 42%",
            "main_business_breakdown": [
                {"name": "薄膜光学", "value": 42},
                {"name": "红外截止", "value": 28},
                {"name": "棱镜",     "value": 15},
                {"name": "AR 光波导", "value": 10},
                {"name": "其他",     "value": 5},
            ],
        }, "source": "akshare:zygc + 年报", "fallback": False},
        "6_research": {"data": {"coverage": "26 家", "rating": "买入 18 / 增持 6 / 中性 2",
                                "target_avg": "¥22.50", "upside": "+21%"},
                       "source": "akshare:research_report_em", "fallback": False},
        "7_industry": {"data": {"growth": "+35%/年", "tam": "¥420 亿", "penetration": "12%",
                                "lifecycle": "成长期"},
                       "source": "web + akshare", "fallback": False},
        "8_materials": {"data": {
            "core_material": "光学玻璃 / 镀膜化学品",
            "price_trend": "12个月 -8%",
            "cost_share": "原材料占 35%",
            "import_dep": "进口依赖 22%",
            "price_history_12m": [108, 112, 115, 113, 110, 106, 104, 102, 100, 98, 96, 92],
        }, "source": "web_search", "fallback": True},
        "9_futures": {"data": {"linked_contract": "—", "contract_trend": "无强关联"},
                      "source": "web_search", "fallback": True},
        "10_valuation": {"data": {
            "pe": "42.3", "pe_quantile": "5年75分位",
            "industry_pe": "38.5", "dcf": "¥17.20",
            "pe_history": [25.2, 28.5, 30.1, 32.4, 35.8, 33.2, 30.5, 28.8, 31.5, 34.2, 38.5, 42.3],
            "dcf_sensitivity": {
                "waccs": [8, 9, 10, 11, 12],
                "growths": [6, 8, 10, 12],
                "values": [
                    [22.4, 25.8, 30.2, 36.5],
                    [19.5, 22.1, 25.6, 30.3],
                    [17.2, 19.2, 21.8, 25.4],
                    [15.2, 16.8, 18.8, 21.5],
                    [13.5, 14.8, 16.3, 18.4],
                ],
                "current_price": 18.56,
            },
        }, "source": "akshare:indicator_lg + DCF", "fallback": False},
        "11_governance": {"data": {"pledge": "实控人 8%",
                                    "insider": "+1.2亿",
                                    "related_tx": "占比 3.4%",
                                    "violations": "无"},
                          "source": "akshare:gpzy + ggcg", "fallback": False},
        "12_capital_flow": {"data": {
            "northbound_20d": "+8.4亿",
            "margin_trend": "上升 12%",
            "holders_trend": "3季连降",
            "main_5d": "+3.2亿",
            "northbound_history": [0.2, 0.5, 0.3, 0.8, 1.2, 0.9, 1.5, 2.1, 2.8, 2.5, 3.2, 3.8, 4.5, 5.2, 5.8, 6.4, 7.1, 7.8, 8.2, 8.4],
            "margin_history": [2.1, 2.15, 2.2, 2.18, 2.22, 2.25, 2.28, 2.3, 2.35, 2.38, 2.42, 2.45],
            "holders_history": [82500, 80100, 77200, 74800],
            "main_history": [0.5, 0.8, 1.2, 2.1, 3.2],
            "institutional_history": {
                "quarters": ["23Q2", "23Q3", "23Q4", "24Q1", "24Q2", "24Q3", "24Q4", "25Q1"],
                "fund":    [2.1, 2.4, 3.2, 4.1, 4.5, 5.2, 6.1, 7.3],
                "qfii":    [0.8, 0.9, 1.1, 1.3, 1.5, 1.8, 2.0, 2.4],
                "shehui":  [1.2, 1.5, 1.8, 2.1, 2.3, 2.5, 2.8, 3.0],
            },
            "unlock_schedule": [
                {"date": "26-06", "amount": 2.4},
                {"date": "26-08", "amount": 0.8},
                {"date": "26-11", "amount": 5.6},
                {"date": "27-02", "amount": 1.2},
            ],
        }, "source": "akshare:hsgt + margin + gdhs", "fallback": False},
        "13_policy": {"data": {"policy_dir": "支持 AI 硬件",
                                "subsidy": "高新企业减免",
                                "monitoring": "无负面",
                                "anti_trust": "不适用"},
                      "source": "web_search", "fallback": True},
        "14_moat": {"data": {"intangible": "150+ 专利",
                              "switching": "苹果绑定高",
                              "network": "弱",
                              "scale": "国内最大"},
                    "source": "web + akshare", "fallback": False},
        "15_events": {"data": {
            "recent_news": "iPhone 17 备货 + 苹果秋季发布会",
            "catalyst": "Q2 业绩预告 6/15",
            "earnings_preview": "预增 25-35%",
            "warnings": "无",
            "event_timeline": [
                "2026-04-12 · 公司公告 Q2 业绩预告 预增 25-35%",
                "2026-04-08 · 获苹果 M7 新订单 (产业链消息)",
                "2026-04-05 · AR 眼镜新品合作项目曝光",
                "2026-03-28 · 机构调研 接待券商 17 家",
                "2026-03-15 · 限售股解禁 1.2 亿股 (已消化)",
                "2026-03-10 · 北向资金连续 8 日净买入",
            ],
        }, "source": "akshare:news_em + cls", "fallback": False},
        "16_lhb": {"data": {"lhb_30d": "5 次",
                             "youzi_matched": "章盟主 / 交易猿",
                             "inst_net": "+2.4亿",
                             "youzi_net": "+1.8亿"},
                   "source": "akshare:stock_lhb_detail_em + seat_db", "fallback": False},
        "17_sentiment": {"data": {"xueqiu_heat": "热度 87 (↑)",
                                   "guba_volume": "+45% 环比",
                                   "big_v_mentions": "S 级 2 / A 级 6",
                                   "positive_pct": "62%"},
                         "source": "akshare:hot_rank + scrape", "fallback": False},
        "18_trap": {"data": {"signals_hit": "0/8",
                              "trap_level": "🟢 安全",
                              "high_risk_kw": "未发现",
                              "evidence_count": "0",
                              "recommendation": "数据正常，未发现异常推广痕迹。讨论热度与基本面匹配。"},
                    "source": "8-signal scan", "fallback": False},
        "19_contests": {"data": {
            "xq_cubes": "32", "high_return_cubes": "8",
            "tgb_mentions": "12 篇讨论", "ths_simu": "查询失败 (需登录)",
            "xq_cubes_list": [
                {"name": "科技成长先锋", "owner": "老王看科技", "total_gain": "+182.4%", "url": "https://xueqiu.com/P/ZH123456"},
                {"name": "苹果产业链精选", "owner": "苹果链猎人", "total_gain": "+156.7%", "url": "https://xueqiu.com/P/ZH123457"},
                {"name": "光学十年", "owner": "光电观察家", "total_gain": "+143.2%", "url": "https://xueqiu.com/P/ZH123458"},
                {"name": "高增长白马", "owner": "长期主义者", "total_gain": "+98.5%", "url": "https://xueqiu.com/P/ZH123459"},
                {"name": "AR+AI 硬件", "owner": "XR玩家007", "total_gain": "+87.3%", "url": "https://xueqiu.com/P/ZH123460"},
                {"name": "稳健成长 2026", "owner": "价值老张", "total_gain": "+72.1%", "url": "https://xueqiu.com/P/ZH123461"},
                {"name": "中小盘黑马", "owner": "赛道选手", "total_gain": "+65.8%", "url": "https://xueqiu.com/P/ZH123462"},
                {"name": "长线持有组合", "owner": "慢就是快", "total_gain": "+58.4%", "url": "https://xueqiu.com/P/ZH123463"},
                {"name": "消费电子链", "owner": "果链研究员", "total_gain": "+45.2%", "url": "https://xueqiu.com/P/ZH123464"},
                {"name": "创业板精选", "owner": "创业板老司机", "total_gain": "+38.6%", "url": "https://xueqiu.com/P/ZH123465"},
                {"name": "价值投资实盘", "owner": "段粉俱乐部", "total_gain": "+31.2%", "url": "https://xueqiu.com/P/ZH123466"},
                {"name": "科技龙头组合", "owner": "龙头战士", "total_gain": "+28.7%", "url": "https://xueqiu.com/P/ZH123467"},
                {"name": "稳健配置", "owner": "慢牛先生", "total_gain": "+22.4%", "url": "https://xueqiu.com/P/ZH123468"},
                {"name": "AI 算力 2.0", "owner": "AI 专注", "total_gain": "+18.9%", "url": "https://xueqiu.com/P/ZH123469"},
                {"name": "成长股猎手", "owner": "成长猎手", "total_gain": "+12.3%", "url": "https://xueqiu.com/P/ZH123470"},
            ],
            "tgb_list": [
                {"title": "水晶光电近期龙虎榜解读，章盟主再次加仓", "url": "https://www.taoguba.com.cn/Article/1234567"},
                {"title": "002273 技术形态分析 - 突破平台整理中", "url": "https://www.taoguba.com.cn/Article/1234568"},
                {"title": "苹果产业链二供逻辑是否成立？", "url": "https://www.taoguba.com.cn/Article/1234569"},
                {"title": "水晶光电 Q2 业绩预告解读", "url": "https://www.taoguba.com.cn/Article/1234570"},
                {"title": "【实盘分享】002273 持仓 30%", "url": "https://www.taoguba.com.cn/Article/1234571"},
                {"title": "AR 眼镜渗透率测算 - 水晶光电受益几何", "url": "https://www.taoguba.com.cn/Article/1234572"},
                {"title": "北向资金连续买入，这个信号要重视", "url": "https://www.taoguba.com.cn/Article/1234573"},
                {"title": "水晶光电 vs 蓝特光学 对比研究", "url": "https://www.taoguba.com.cn/Article/1234574"},
            ],
            "ths_list": [
                {"nickname": "短线王者2025", "return_pct": 89.3},
                {"nickname": "稳健先生", "return_pct": 67.5},
                {"nickname": "趋势跟随者", "return_pct": 54.2},
                {"nickname": "科技猎手", "return_pct": 48.7},
                {"nickname": "光电专业户", "return_pct": 42.1},
                {"nickname": "长期持有党", "return_pct": 36.8},
            ],
        }, "source": "xueqiu cubes API + tgb scrape + 10jqka", "fallback": False},
    },
}
write_task_output(TICKER, "raw_data", raw_data)

# ── Mock dimensions.json · 全 19 维评分 ─────────────────────────
dimensions = {
    "ticker": TICKER,
    "fundamental_score": 76.0,
    "dimensions": {
        "1_financials": {"score": 8, "weight": 5, "label": "财报扎实，ROE 三年 >18%",
                         "reasons_pass": ["ROE 18.7%", "净利率 21%", "营收增速 28%"], "reasons_fail": ["商誉占净资产 28%"]},
        "2_kline": {"score": 7, "weight": 4, "label": "Stage 2 初期，均线多头",
                    "reasons_pass": ["MA 多头排列", "MACD 金叉"], "reasons_fail": ["RSI 62 接近超买"]},
        "3_macro": {"score": 6, "weight": 3, "label": "降息周期支持成长股",
                    "reasons_pass": ["货币宽松"], "reasons_fail": ["人民币偏弱压制利润率"]},
        "4_peers": {"score": 8, "weight": 4, "label": "行业第 2，关键指标全部高于均值",
                    "reasons_pass": ["毛利率 +4pp", "ROE +6pp", "增速 +12pp"], "reasons_fail": []},
        "5_chain": {"score": 6, "weight": 4, "label": "下游集中度过高，对苹果依赖深",
                    "reasons_pass": ["上游分散", "议价能力强"], "reasons_fail": ["前五客户 65%"]},
        "6_research": {"score": 8, "weight": 3, "label": "26 家覆盖，买入比例 69%",
                       "reasons_pass": ["上涨空间 21%", "评级以买入为主"], "reasons_fail": []},
        "7_industry": {"score": 9, "weight": 4, "label": "行业 +35%/年，渗透率仅 12%",
                       "reasons_pass": ["TAM 420亿", "渗透率提升空间大"], "reasons_fail": []},
        "8_materials": {"score": 7, "weight": 3, "label": "原材料 12 个月降价 8%",
                        "reasons_pass": ["成本下降"], "reasons_fail": ["进口依赖 22%"]},
        "9_futures": {"score": 5, "weight": 2, "label": "无强关联期货品种"},
        "10_valuation": {"score": 5, "weight": 5, "label": "PE 已到 5 年 75 分位",
                         "reasons_pass": [], "reasons_fail": ["PE 高于行业均值", "DCF 内在值低于现价"]},
        "11_governance": {"score": 8, "weight": 4, "label": "治理良好，管理层增持",
                          "reasons_pass": ["质押低", "近 12 月增持 1.2 亿", "无违规"], "reasons_fail": []},
        "12_capital_flow": {"score": 8, "weight": 4, "label": "北向 +8.4 亿 + 筹码集中",
                            "reasons_pass": ["北向流入", "股东户数 3 季降"], "reasons_fail": []},
        "13_policy": {"score": 7, "weight": 3, "label": "AI 硬件产业政策利好",
                      "reasons_pass": ["高新减免", "AI 政策"], "reasons_fail": []},
        "14_moat": {"score": 7, "weight": 3, "label": "150+ 专利 + 苹果绑定",
                    "reasons_pass": ["无形资产", "转换成本"], "reasons_fail": ["网络效应弱"]},
        "15_events": {"score": 8, "weight": 4, "label": "Q2 业绩预增 25-35%",
                      "reasons_pass": ["业绩预告", "iPhone 17 备货"], "reasons_fail": []},
        "16_lhb": {"score": 8, "weight": 4, "label": "章盟主 / 交易猿格局加仓",
                   "reasons_pass": ["机构净买 2.4 亿", "顶级游资进场"], "reasons_fail": []},
        "17_sentiment": {"score": 7, "weight": 3, "label": "雪球热度上升，正面 62%",
                         "reasons_pass": ["S 级大V 2 位提及"], "reasons_fail": ["环比 +45% 注意泡沫"]},
        "18_trap": {"score": 9, "weight": 5, "label": "🟢 安全，0/8 信号命中",
                    "reasons_pass": ["未发现推广", "热度与基本面匹配"], "reasons_fail": []},
        "19_contests": {"score": 7, "weight": 4, "label": "雪球 32 组合 / 8 个高收益持有",
                        "reasons_pass": ["雪球高收益持有 8 个", "淘股吧 12 篇讨论"], "reasons_fail": []},
    },
}
write_task_output(TICKER, "dimensions", dimensions)

# ── Mock panel.json · 50 人 Signal ────────────────────────────
import random
random.seed(42)

SAMPLE_COMMENTS = {
    "bullish": {
        "A": ["ROE 五年都在 18% 以上，护城河清晰，哪怕贵一点也值。", "资产负债表干净，现金流充沛，这种生意 10 年后还在赚钱。"],
        "B": ["PEG 只有 1.2，成长确定性在提升，机构刚开始加仓。", "CANSLIM 打 6 分，N 和 M 都在线，可以进攻。"],
        "C": ["市场还没意识到这个行业的反身性拐点，现在加仓是正确时机。", "宏观流动性在转向，这种标的最受益。"],
        "D": ["刚走出 VCP，量能配合，Stage 2 确认。", "突破关键压力位，止损位清晰。"],
        "E": ["生意看得懂、人靠谱、价格还能接受，三问都过。", "ROE 持续性强，消费属性明显，可以重仓。"],
        "F": ["板块格局打开，趋势向上，大资金进场节奏。", "二板定龙头，板块辨识度第一。", "题材到了干就完了。"],
        "G": ["多因子评分 82 分，质量因子和动量因子都强。", "凯利公式给出 0.12 最优仓位，可买。"],
    },
    "bearish": {
        "A": ["PE 已到历史 75 分位，安全边际不足。", "增长是建立在高资本开支上的，一旦周期反转会很惨。"],
        "B": ["PEG 1.5 已经不便宜，新产品线还没验证。", "机构持股比例已经过高，不符合 CANSLIM 的 S 项。"],
        "C": ["反身性正反馈进入晚期，离崩溃只差一份财报。", "市场温度计已经 75 分，贪婪区。"],
        "D": ["均线有走弱迹象，VCP 没有完全成形。", "距 52 周高点只剩 5%，不是入场点。"],
        "E": ["短期涨得太快，冯柳式赔率不足。", "产能周期已经过了最佳时点。"],
        "F": ["市值太大，不在射程里。", "情绪周期接近顶部，该减仓了。"],
        "G": ["统计上已经超卖区反面，均值回归风险。"],
    },
    "neutral": {
        "all": ["看不太懂，先放观察池。", "数据不够，再等一份季报。", "不在能力圈内。", "等待明确信号再说。"],
    },
}


def pick_comment(sig: str, group: str) -> str:
    if sig == "neutral":
        return random.choice(SAMPLE_COMMENTS["neutral"]["all"])
    return random.choice(SAMPLE_COMMENTS[sig].get(group, SAMPLE_COMMENTS[sig].get("A", ["—"])))


VERDICTS = {
    "bullish": ["强烈买入", "买入", "关注"],
    "bearish": ["观望", "回避", "等待"],
    "neutral": ["观望", "不适合", "不达标"],
}

panel_investors = []
# v2.6 · 与 run_real_test.py:454 对齐，加 'skip' key 防御 KeyError
vote_dist = {"strongly_buy": 0, "buy": 0, "watch": 0, "wait": 0, "avoid": 0, "n_a": 0, "skip": 0}
sig_dist = {"bullish": 0, "neutral": 0, "bearish": 0, "skip": 0}

for inv in INVESTORS:
    r = random.random()
    if r < 0.42:
        sig = "bullish"
    elif r < 0.78:
        sig = "neutral"
    else:
        sig = "bearish"
    conf = random.randint(55, 95) if sig != "neutral" else random.randint(30, 60)
    score = conf - random.randint(-8, 5)
    score = max(10, min(98, score))
    verdict = random.choice(VERDICTS[sig])
    v_key = {"强烈买入": "strongly_buy", "买入": "buy", "关注": "watch", "观望": "wait", "回避": "avoid"}.get(verdict, "n_a")
    vote_dist[v_key] = vote_dist.get(v_key, 0) + 1
    # v2.6 · 用 .get() 防御未来新 signal type 引发 KeyError
    sig_dist[sig] = sig_dist.get(sig, 0) + 1
    reason = pick_comment(sig, inv["group"])
    panel_investors.append({
        "investor_id": inv["id"],
        "name": inv["name"],
        "group": inv["group"],
        "avatar": f"avatars/{inv['id']}.svg",
        "signal": sig,
        "confidence": conf,
        "score": score,
        "verdict": verdict,
        "reasoning": reason,
        "comment": reason,
        "pass": [],
        "fail": [],
        "ideal_price": round(16 + random.random() * 4, 2),
        "period": random.choice(["3-5 年", "1-3 年", "半年", "1-3 月"]),
    })

panel = {
    "ticker": TICKER,
    "panel_consensus": round(sig_dist["bullish"] / 50 * 100, 1),
    "vote_distribution": vote_dist,
    "signal_distribution": sig_dist,
    "investors": panel_investors,
}
write_task_output(TICKER, "panel", panel)

# ── Mock synthesis.json ───────────────────────────────────────
# Pick strongest bull and bear
sorted_bulls = sorted([i for i in panel_investors if i["signal"] == "bullish"], key=lambda x: -x["confidence"])
sorted_bears = sorted([i for i in panel_investors if i["signal"] == "bearish"], key=lambda x: -x["confidence"])
bull = sorted_bulls[0] if sorted_bulls else panel_investors[0]
bear = sorted_bears[0] if sorted_bears else panel_investors[-1]

synthesis = {
    "ticker": TICKER,
    "name": "水晶光电",
    "overall_score": 76.8,
    "verdict_label": "可以蹲一蹲",
    "fundamental_score": 76.0,
    "panel_consensus": panel["panel_consensus"],
    "debate": {
        "bull": {"investor_id": bull["investor_id"], "name": bull["name"], "group": bull["group"]},
        "bear": {"investor_id": bear["investor_id"], "name": bear["name"], "group": bear["group"]},
        "rounds": [
            {
                "round": 1,
                "bull_say": f"ROE 五年都在 18% 以上，AR 眼镜渗透率才刚起步，现在 PE 42 看着贵，两年后业绩接上就是便宜。",
                "bear_say": f"ROE 是过去式。PE 已经到历史 75 分位，下一份季报只要稍微不及预期就要杀估值，现在介入是在刀尖上跳舞。",
            },
            {
                "round": 2,
                "bull_say": f"苹果产业链二供身份已经落地，M7 开始放量，这种可见度的定价权本来就该给溢价。",
                "bear_say": f"代价是公司把自己绑在苹果身上了。苹果今年资本开支砍 15%，你确定订单能持续？",
            },
            {
                "round": 3,
                "bull_say": f"短期波动不影响长逻辑，Stage 2 初期 + 章盟主刚进场，技术面和资金面都对。",
                "bear_say": f"章盟主进场的那个时点就是你应该警惕的时点——他不是做右侧，他是做趋势中后段的。",
            },
        ],
        "punchline": "ROE 五年 > 15%，但苹果今年资本开支砍 15%——这就是问题所在。",
    },
    "great_divide": {
        "bull_avatar": bull["investor_id"],
        "bear_avatar": bear["investor_id"],
        "bull_score": bull["confidence"],
        "bear_score": bear["confidence"],
        "punchline": "ROE 五年 > 15%，但苹果今年资本开支砍 15%——这就是问题所在。",
    },
    "risks": [
        "PE 已经到历史 75 分位，安全边际收窄",
        "苹果 2026 年资本开支砍 15%，订单可持续性存疑",
        "商誉占净资产 28%，减值风险",
        "AR 眼镜渗透率不达预期，行业景气度可能高估",
    ],
    "buy_zones": {
        "value": {"price": 16.20, "rationale": "DCF + 历史 PE 25 分位"},
        "growth": {"price": 17.50, "rationale": "PEG=1.2 对应价"},
        "technical": {"price": 18.00, "rationale": "20 日均线 + 颈线支撑"},
        "youzi": {"price": 18.56, "rationale": "板块情绪未破前可追"},
    },
    "friendly": {
        "scenarios": {
            "entry_price": 18.56,
            "cases": [
                {"name": "最坏情况", "probability": "15%", "return": -35},
                {"name": "偏差情况", "probability": "25%", "return": -15},
                {"name": "合理情况", "probability": "35%", "return": 12},
                {"name": "乐观情况", "probability": "20%", "return": 38},
                {"name": "极致乐观", "probability": "5%", "return": 75},
            ],
        },
        "similar_stocks": [
            {"name": "蓝特光学", "code": "SH688127", "similarity": "92%", "reason": "同为苹果产业链光学薄膜供应商，业务几乎重合",
             "url": "https://xueqiu.com/S/SH688127"},
            {"name": "舜宇光学", "code": "HK02382", "similarity": "85%", "reason": "全球光学龙头，业务范围更广但估值有参考性",
             "url": "https://xueqiu.com/S/HK02382"},
            {"name": "永新光学", "code": "SH603297", "similarity": "76%", "reason": "光学元器件精密加工，客户结构有部分重合",
             "url": "https://xueqiu.com/S/SH603297"},
            {"name": "联创电子", "code": "SZ002036", "similarity": "68%", "reason": "光学镜头同行，车载与 VR 方向有交集",
             "url": "https://xueqiu.com/S/SZ002036"},
        ],
        "exit_triggers": [
            "股价跌破 ¥15.50（60 日均线支撑位）→ 无条件止损",
            "苹果季度资本开支指引下修 > 10% → 业绩逻辑动摇",
            "Q2 业绩预告低于 +25% → 预期管理失守",
            "章盟主席位大额卖出 > 2 亿 → 顶级游资撤离信号",
            "PE 站上 5 年 90 分位（≈ 48）→ 泡沫区，获利了结",
        ],
    },
    "fund_managers": [
        {
            "name": "张坤", "fund_name": "易方达蓝筹精选混合", "fund_code": "005827", "avatar": "zhangkun",
            "position_pct": 3.2, "rank_in_fund": 8, "holding_quarters": 4, "position_trend": "加仓",
            "return_5y": 156.7, "annualized_5y": 20.5, "max_drawdown": -28.3, "sharpe": 1.42, "peer_rank_pct": 5,
            "nav_history": [1.0, 1.08, 1.12, 1.25, 1.42, 1.65, 1.58, 1.72, 1.88, 2.05, 2.18, 2.35, 2.52, 2.41, 2.57],
            "fund_url": "https://fund.eastmoney.com/005827.html",
        },
        {
            "name": "谢治宇", "fund_name": "兴全合润混合 LOF", "fund_code": "163406", "avatar": "xiezhiyu",
            "position_pct": 2.8, "rank_in_fund": 10, "holding_quarters": 6, "position_trend": "加仓",
            "return_5y": 124.3, "annualized_5y": 17.5, "max_drawdown": -22.1, "sharpe": 1.31, "peer_rank_pct": 8,
            "nav_history": [1.0, 1.05, 1.12, 1.20, 1.32, 1.48, 1.55, 1.68, 1.78, 1.92, 2.05, 2.15, 2.24, 2.18, 2.24],
            "fund_url": "https://fund.eastmoney.com/163406.html",
        },
        {
            "name": "朱少醒", "fund_name": "富国天惠成长混合", "fund_code": "161005", "avatar": "zhushaoxing",
            "position_pct": 2.1, "rank_in_fund": 14, "holding_quarters": 8, "position_trend": "持平",
            "return_5y": 98.6, "annualized_5y": 14.7, "max_drawdown": -25.8, "sharpe": 1.12, "peer_rank_pct": 15,
            "nav_history": [1.0, 1.04, 1.10, 1.18, 1.26, 1.34, 1.42, 1.52, 1.61, 1.68, 1.76, 1.84, 1.92, 1.96, 1.99],
            "fund_url": "https://fund.eastmoney.com/161005.html",
        },
        {
            "name": "傅鹏博", "fund_name": "睿远成长价值混合", "fund_code": "007119", "avatar": "",
            "position_pct": 3.8, "rank_in_fund": 5, "holding_quarters": 3, "position_trend": "加仓",
            "return_5y": 142.8, "annualized_5y": 19.4, "max_drawdown": -30.5, "sharpe": 1.28, "peer_rank_pct": 7,
            "nav_history": [1.0, 1.06, 1.14, 1.22, 1.34, 1.48, 1.58, 1.72, 1.85, 2.02, 2.15, 2.28, 2.38, 2.32, 2.43],
            "fund_url": "https://fund.eastmoney.com/007119.html",
        },
        {
            "name": "刘彦春", "fund_name": "景顺长城新兴成长", "fund_code": "260108", "avatar": "",
            "position_pct": 2.5, "rank_in_fund": 11, "holding_quarters": 5, "position_trend": "减仓",
            "return_5y": 88.4, "annualized_5y": 13.6, "max_drawdown": -35.2, "sharpe": 0.98, "peer_rank_pct": 22,
            "nav_history": [1.0, 1.08, 1.18, 1.15, 1.22, 1.32, 1.48, 1.55, 1.65, 1.72, 1.68, 1.75, 1.82, 1.88, 1.88],
            "fund_url": "https://fund.eastmoney.com/260108.html",
        },
        {
            "name": "冯波", "fund_name": "易方达研究精选股票", "fund_code": "000979", "avatar": "",
            "position_pct": 3.0, "rank_in_fund": 7, "holding_quarters": 2, "position_trend": "新进",
            "return_5y": 112.5, "annualized_5y": 16.3, "max_drawdown": -24.8, "sharpe": 1.18, "peer_rank_pct": 12,
            "nav_history": [1.0, 1.04, 1.12, 1.22, 1.32, 1.45, 1.52, 1.63, 1.72, 1.82, 1.92, 2.00, 2.05, 2.08, 2.12],
            "fund_url": "https://fund.eastmoney.com/000979.html",
        },
    ],
    "dashboard": {
        "core_conclusion": "77 分，可以蹲一蹲但别上头。50 位大佬里 21 人看多，最看好的是段永平(92)，但 PE 已经到历史 75 分位，苹果订单能不能接住是下半年最大的变量。",
        "data_perspective": {
            "trend": "Stage 2 初期，20 日均线刚翻多",
            "price": "现价 18.56，距压力位 20.10 还有 8%",
            "volume": "近 5 日温和放量，换手率 4.2%",
            "chips": "股东户数连续 3 季下降，筹码集中中",
        },
        "intelligence": {
            "news": "iPhone 17 备货传闻 + AR 眼镜 BOM 渗透率提升 + Q2 业绩预告",
            "risks": ["商誉 28%", "PE 历史 75 分位"],
            "catalysts": ["6 月新品发布", "Q2 业绩预告", "苹果秋季发布会"],
        },
        "battle_plan": {
            "entry": "16.20-17.00 分批",
            "position": "标准仓 50% 起步",
            "stop": "破 15.50 离场",
            "target": "短线 22, 中线 28",
        },
    },
}
write_task_output(TICKER, "synthesis", synthesis)

# ── Assemble ───────────────────────────────────────────────────
from assemble_report import assemble  # noqa: E402
result = assemble(TICKER)
print(f"\n[ok] Mock report ready. Open: {result}")
