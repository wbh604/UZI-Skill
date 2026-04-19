"""Dimension 13 · 政策与监管 — 真实 web search 拉取行业政策."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime

from lib.web_search import search, search_trusted


def _fetch_cfachina_titles(limit: int = 15) -> list[dict]:
    """v2.13.7 · 中国期货业协会静态 HTML 抓标题 · Grok 验证源 · 零 Key.

    cfachina 大部分列表 JS 渲染，但首页 / 关于协会页静态 HTML 含标题链接.
    抓回来做 13_policy 的监管信号（期货 / 衍生品 industry 尤其相关）.
    """
    try:
        import requests
        r = requests.get(
            "http://www.cfachina.org/",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"},
            timeout=12,
        )
        if r.status_code != 200:
            return []
        r.encoding = r.apparent_encoding or "utf-8"
        # 抽"关键词 + 链接" · 过滤导航/页脚/资格类杂项
        pairs = re.findall(r'<a[^>]*href="([^"]+)"[^>]*>([^<]{8,60})</a>', r.text)
        titles = []
        seen = set()
        for href, text in pairs:
            t = text.strip()
            # 过滤导航/框架类
            if any(noise in t for noise in [
                "首页", "协会", "联系", "办理", "业务", "资格",
                "会员", "管理", "委员会", "内容", "简介", "章程",
                "廉洁", "脱贫", "招聘", "采购", "信息公示",
                "基本情况", "历史情况", "人员信息", "分支机构",
                "股东信息", "诚信记录", "次级债", "诚信信息",
                "月度成交", "月度经营", "服务实体", "移动应用",
            ]):
                continue
            if t in seen:
                continue
            seen.add(t)
            if href.startswith("/"):
                url = "http://www.cfachina.org" + href
            elif href.startswith("http"):
                url = href
            else:
                url = "http://www.cfachina.org/" + href.lstrip("./")
            titles.append({"title": t[:80], "body": "", "url": url})
            if len(titles) >= limit:
                break
        return titles
    except Exception:
        return []


def main(industry: str = "综合") -> dict:
    year = datetime.now().year
    queries = {
        "policy_dir": f"{year} {industry} 国家政策 扶持 利好",
        "subsidy": f"{year} {industry} 政府补贴 税收优惠",
        "monitoring": f"{year} {industry} 监管 合规 风险",
        "anti_trust": f"{year} {industry} 反垄断 调查",
    }
    snippets: dict[str, list] = {}
    sentiment_map: dict[str, str] = {}

    # v2.13.7 · cfachina 直连（期货监管信号 · 补 ddgs 盲区）
    cfa_titles = _fetch_cfachina_titles(limit=10) if any(
        kw in industry for kw in ["期货", "衍生品", "商品", "金融", "证券"]
    ) else []

    # v2.7.3 · 政策 dim 全部用 13_policy 权威域（gov.cn / csrc / 中证网 / 证券时报 ...）
    for key, q in queries.items():
        res = search_trusted(q, dim_key="13_policy", max_results=4)
        valid = [r for r in res if "error" not in r]
        snippets[key] = [
            {"title": r.get("title", "")[:80], "body": r.get("body", "")[:200], "url": r.get("url", "")}
            for r in valid[:3]
        ]

        # Heuristic sentiment per category
        text = " ".join(r.get("body", "") for r in valid)
        pos_kws = ["扶持", "支持", "鼓励", "补贴", "优惠", "免税", "专项", "利好"]
        neg_kws = ["处罚", "罚款", "违规", "禁止", "限制", "收紧", "调查", "约谈"]
        pos = sum(1 for kw in pos_kws if kw in text)
        neg = sum(1 for kw in neg_kws if kw in text)

        if pos > neg + 1:
            sentiment_map[key] = "积极"
        elif neg > pos + 1:
            sentiment_map[key] = "收紧"
        elif pos == 0 and neg == 0:
            sentiment_map[key] = "—"
        else:
            sentiment_map[key] = "中性"

    # 追加 cfachina 到 monitoring snippets（期货相关 industry 才抓）
    if cfa_titles:
        snippets.setdefault("monitoring", [])
        snippets["monitoring"].extend(cfa_titles[:5])

    return {
        "data": {
            "policy_dir": sentiment_map.get("policy_dir", "—"),
            "subsidy": sentiment_map.get("subsidy", "—"),
            "monitoring": sentiment_map.get("monitoring", "—"),
            "anti_trust": sentiment_map.get("anti_trust", "—"),
            "snippets": snippets,
            "year": year,
            "industry": industry,
            "cfachina_titles_count": len(cfa_titles),
        },
        "source": "web_search:ddgs + keyword sentiment + cfachina (v2.13.7 · 期货监管)",
        "fallback": False,
    }


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "光学光电子"
    print(json.dumps(main(arg), ensure_ascii=False, indent=2, default=str))
