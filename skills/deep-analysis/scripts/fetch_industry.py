"""Dimension 7 · 行业景气度 — 使用 cninfo 行业 PE 聚合数据（绕过 push2）."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta

import akshare as ak  # type: ignore
from lib.market_router import parse_ticker
from lib.industry_mapping import resolve_csrc_industry


# Industry → (growth %, TAM 亿, penetration %, lifecycle stage)
# Hardcoded domain knowledge for common industries (fallback when no API)
INDUSTRY_ESTIMATES: dict[str, dict] = {
    "光学光电子": {
        "growth": "+30%/年",
        "tam": "¥420 亿",
        "penetration": "12%",
        "lifecycle": "成长期",
        "note": "AR/VR + 车载光学 + iPhone 相机模组驱动",
    },
    "半导体": {
        "growth": "+18%/年",
        "tam": "¥7800 亿",
        "penetration": "国产化率 15%",
        "lifecycle": "成长期",
        "note": "国产替代 + AI 算力需求",
    },
    "医药生物": {
        "growth": "+10%/年",
        "tam": "¥3.2 万亿",
        "penetration": "—",
        "lifecycle": "成熟期",
        "note": "集采降价 + 创新药放量博弈",
    },
    "电池": {
        "growth": "+22%/年",
        "tam": "¥1.8 万亿",
        "penetration": "电车 38%",
        "lifecycle": "成长期",
        "note": "动力电池 + 储能双驱动",
    },
    "白酒": {
        "growth": "+6%/年",
        "tam": "¥7500 亿",
        "penetration": "—",
        "lifecycle": "成熟期",
        "note": "次高端分化 + 名酒企稳",
    },
    "银行": {
        "growth": "+4%/年",
        "tam": "—",
        "penetration": "—",
        "lifecycle": "成熟期",
        "note": "净息差收窄 + 红利防御属性",
    },
    "钢铁": {
        "growth": "-2%/年",
        "tam": "—",
        "penetration": "—",
        "lifecycle": "衰退期",
        "note": "供给侧 + 需求下行",
    },
}


def _best_industry_match(industry: str) -> dict:
    if not industry:
        return {}
    for key, val in INDUSTRY_ESTIMATES.items():
        if key in industry or industry in key or industry[:2] in key:
            return val
    return {}


def _cninfo_industry_metrics(industry_name: str) -> dict:
    """Pull industry aggregated PE from cninfo — works on this network."""
    if not industry_name:
        return {}
    today = datetime.now()
    for i in range(1, 8):
        d = (today - timedelta(days=i)).strftime("%Y%m%d")
        try:
            df = ak.stock_industry_pe_ratio_cninfo(
                symbol="证监会行业分类", date=d
            )
            if df is None or df.empty:
                continue
            # v2.8.3 · 用语义映射代替 str.contains(industry[:2]) —— 旧版对"工业金属"
            # 等前缀高碰撞的申万行业会误命中"农副食品加工业"
            row = resolve_csrc_industry(industry_name, df)
            if row is None:
                continue
            pe_col = next((c for c in df.columns if "市盈率" in c and "加权" in c), None)
            return {
                "industry_name_match": str(row.get("行业名称", "")),
                "company_count": int(row.get("公司数量", 0)) if "公司数量" in df.columns else None,
                "total_mcap_yi": float(row.get("总市值-静态", 0)) if "总市值-静态" in df.columns else None,
                "net_profit_yi": float(row.get("净利润-静态", 0)) if "净利润-静态" in df.columns else None,
                "industry_pe_weighted": float(row[pe_col]) if pe_col else None,
                "industry_pe_median": float(row.get("静态市盈率-中位数", 0)) if "静态市盈率-中位数" in df.columns else None,
                "data_date": d,
            }
        except Exception:
            continue
    return {}


def _dynamic_industry_overview(industry: str) -> dict:
    """v2.9 · 替代 INDUSTRY_ESTIMATES 硬编码 · 用 search_trusted 动态查景气度。

    对不在 INDUSTRY_ESTIMATES 的行业（236/243 个申万三级），走权威域 site:
    查询，从统计局/工信部/中证网/每经的真实文章里抽：
      - growth 同比增速关键词
      - TAM 市场规模
      - lifecycle 阶段性关键词
    把抽到的 snippets 返回给 agent，由 agent 在 dim_commentary 里综合。
    """
    try:
        from lib.web_search import search_trusted
    except Exception:
        return {}

    from datetime import datetime
    yr = datetime.now().year
    queries = {
        "景气度": f"{yr} {industry} 行业景气度 增速 市场规模",
        "TAM":    f"{industry} 行业规模 亿元 TAM 2026",
        "周期":   f"{industry} 生命周期 成长期 成熟期 下行",
    }
    snippets: dict[str, list] = {}
    for tag, q in queries.items():
        res = search_trusted(q, dim_key="7_industry", max_results=4)
        valid = [r for r in res if "error" not in r]
        snippets[tag] = [
            {"title": r.get("title", "")[:80], "body": r.get("body", "")[:200], "url": r.get("url", "")}
            for r in valid[:3]
        ]

    # 启发式提取（agent 可覆盖）
    # v2.12.1 · 同时读 title 和 body（很多热门新闻的关键数字在 title 里，如"净利齐涨超40%"）
    all_bodies = " ".join(
        f"{s.get('title', '')} {s.get('body', '')}"
        for items in snippets.values() for s in items
    )
    import re

    # v2.12.1 · growth 上下文感知：优先匹配"增长/增速/CAGR/同比/增幅/复合增长/涨超/涨幅/提升"附近的 %
    # 避免被 "失业率 5%" "PE 25%" 等不相关的 % 抢先
    # 关键词扩展到"涨超/涨幅/暴涨/翻倍/提升/上升/上涨"以覆盖中文财经新闻的常见表达
    growth_heuristic = "—"
    growth_context_pat = re.compile(
        r"(?:增长|增速|CAGR|复合增长|同比|增幅|年均增长|涨超|涨幅|暴涨|翻倍|提升|上升|上涨|净利齐涨)"
        r"[^%]{0,20}?([+\-]?\d{1,3}(?:\.\d+)?)\s*%"
    )
    m = growth_context_pat.search(all_bodies)
    if m:
        growth_heuristic = f"{m.group(1)}%/年"
    else:
        # 次级兜底：含"行业"/"市场" 前后的 %
        m2 = re.search(
            r"(?:行业|市场|产业)[^%]{0,30}?([+\-]?\d{1,3}(?:\.\d+)?)\s*%|"
            r"([+\-]?\d{1,3}(?:\.\d+)?)\s*%\s*(?:的?增长|的?增速)",
            all_bodies,
        )
        if m2:
            val = m2.group(1) or m2.group(2)
            growth_heuristic = f"{val}%/年"

    # TAM：匹配"市场规模/规模达/将达" 附近的"XX亿"
    tam_heuristic = "—"
    tam_context_pat = re.compile(
        r"(?:市场规模|规模达|规模约|将达|产业规模|TAM|行业规模)[^亿]{0,20}?(\d{1,5}(?:\.\d+)?)\s*亿"
    )
    m = tam_context_pat.search(all_bodies)
    if m:
        tam_heuristic = f"¥{m.group(1)}亿"
    else:
        m2 = re.search(r"(\d{1,5}(?:\.\d+)?)\s*亿\s*(?:元)?\s*(?:市场|规模)", all_bodies)
        if m2:
            tam_heuristic = f"¥{m2.group(1)}亿"

    # v2.12.1 · penetration 渗透率提取（原版完全缺失）
    penetration_heuristic = "—"
    pen_pat = re.compile(
        r"渗透率[^%]{0,10}?(\d{1,3}(?:\.\d+)?)\s*%|"
        r"(\d{1,3}(?:\.\d+)?)\s*%\s*的?渗透率"
    )
    m = pen_pat.search(all_bodies)
    if m:
        val = m.group(1) or m.group(2)
        penetration_heuristic = f"{val}%"

    # 生命周期关键词扫描
    lifecycle = "—"
    for keyword, label in [("成长期", "成长期"), ("成熟期", "成熟期"),
                           ("下行期", "下行期"), ("衰退", "衰退期"),
                           ("拐点", "拐点"), ("景气", "景气上行")]:
        if keyword in all_bodies:
            lifecycle = label
            break

    return {
        "growth_heuristic": growth_heuristic,
        "tam_heuristic": tam_heuristic,
        "penetration_heuristic": penetration_heuristic,  # v2.12.1
        "lifecycle_heuristic": lifecycle,
        "web_snippets": snippets,
        "snippet_count": sum(len(v) for v in snippets.values()),
    }


def main(industry: str) -> dict:
    # v2.9 · 优先级
    #   1. INDUSTRY_ESTIMATES 硬编码（手工策展的 7 个高频行业保留做 anchor）
    #   2. search_trusted 动态查权威域（236 个未覆盖行业的兜底）
    #   3. cninfo 行业 PE 加权 metrics（独立源，始终尝试）
    # v2.10.1 · lite mode 跳过 dynamic 查询（节省 3-9 次 ddgs 请求）
    import os
    est = _best_industry_match(industry)
    if os.environ.get("UZI_LITE") == "1":
        dynamic = {}
    else:
        dynamic = {} if est else _dynamic_industry_overview(industry)

    # Get cninfo aggregated metrics
    cninfo_metrics = _cninfo_industry_metrics(industry)

    # 合并：硬编码优先，没有则走动态启发 + 真实 snippets
    # v2.12.1 · penetration 补 dynamic 兜底（原版遗漏）
    growth      = est.get("growth")     or dynamic.get("growth_heuristic")       or "—"
    tam         = est.get("tam")        or dynamic.get("tam_heuristic")          or "—"
    penetration = est.get("penetration") or dynamic.get("penetration_heuristic") or "—"
    lifecycle   = est.get("lifecycle")  or dynamic.get("lifecycle_heuristic")    or "—"
    note        = est.get("note", "")

    source_parts = ["cninfo:stock_industry_pe_ratio"]
    if est: source_parts.append("INDUSTRY_ESTIMATES")
    if dynamic: source_parts.append(f"search_trusted:7_industry({dynamic.get('snippet_count',0)} snippets)")

    return {
        "data": {
            "industry": industry,
            "growth": growth,
            "tam": tam,
            "penetration": penetration,
            "lifecycle": lifecycle,
            "note": note,
            "cninfo_metrics": cninfo_metrics,
            "total_companies": cninfo_metrics.get("company_count"),
            "industry_pe_weighted": cninfo_metrics.get("industry_pe_weighted"),
            # v2.9 · agent 可基于这些真实 snippets 写更好的 dim_commentary
            "dynamic_snippets": dynamic.get("web_snippets") or {},
            "needs_web_search": not bool(est) and not dynamic,
            "web_search_queries": [
                f"{industry} 行业景气度 2026",
                f"{industry} 市场规模 TAM",
                f"{industry} 渗透率 提升空间",
            ] if (not est and not dynamic) else [],
        },
        "source": " + ".join(source_parts),
        "fallback": not bool(cninfo_metrics) and not dynamic,
    }


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "光学光电子"
    print(json.dumps(main(arg), ensure_ascii=False, indent=2, default=str))
