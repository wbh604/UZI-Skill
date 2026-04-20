"""Dimension 14 · 专利与护城河 — web search + 财报 R&D ratio."""
from __future__ import annotations

import json
import sys

from lib import data_sources as ds
from lib.market_router import parse_ticker
from lib.web_search import search, search_trusted


def _evaluate(text: str, pos_kws: list[str], neg_kws: list[str]) -> int:
    """Return 1-10 score based on keyword matches."""
    if not text:
        return 5
    text = text.lower()
    pos = sum(1 for kw in pos_kws if kw.lower() in text)
    neg = sum(1 for kw in neg_kws if kw.lower() in text)
    raw = 5 + pos - neg
    return max(1, min(10, raw))


# Garbage patterns — dictionary/wikipedia pages about Chinese characters
_GARBAGE_PATTERNS = [
    "拼音", "汉语", "通用规范汉字", "常用字", "甲骨文", "部首",
    "笔画", "Unicode", "字形", "读音", "偏旁",
    "百科词条", "词条概述", "释义",
]


def _is_garbage(text: str) -> bool:
    """Detect dictionary/wikipedia noise in search results."""
    if not text:
        return False
    return sum(1 for p in _GARBAGE_PATTERNS if p in text) >= 2


# v2.15.1 · 已知的"超级股票名"· DDGS 对生僻公司查询经常混入这些头部股票的结果
# 所以对这些词做严格过滤：结果里出现就 drop（除非目标公司本身就是这些）
_SUPERSTAR_POLLUTERS = [
    "贵州茅台", "五粮液", "泸州老窖", "洋河股份",  # 白酒
    "宁德时代", "比亚迪",                           # 电池
    "中际旭创", "新易盛",                            # 光模块
    "腾讯", "阿里巴巴", "美团", "京东",              # 互联网
    "招商银行", "工商银行", "建设银行",              # 银行
]


def _result_mentions_company(result: dict, company_name: str, superstar_names: set[str]) -> bool:
    """v2.15.1 · 判断一条 search result 是否真的跟目标公司相关.

    判断标准：
    1. title / body 里包含公司名 → ✅
    2. 不包含公司名，但包含 superstar polluter 名（贵州茅台/五粮液等）→ ❌ 污染
    3. 都不包含 → 视为"弱相关"，保守过滤
    """
    if not company_name:
        return True  # 无法验证 · 不过滤
    text = ((result.get("title") or "") + " " + (result.get("body") or "")).lower()
    if not text.strip():
        return False
    name_lc = company_name.lower()
    # 2 字名字过短可能误命中，取后缀 2-3 字更稳
    name_key = name_lc[-2:] if len(name_lc) >= 2 else name_lc
    if name_lc in text or (len(name_lc) > 2 and name_key in text):
        return True
    # 不含公司名但含 polluter → 污染
    for polluter in superstar_names:
        if polluter in text:
            return False  # 明显污染
    # 都不含 · 弱相关 · 保守过滤
    return False


def main(ticker: str) -> dict:
    ti = parse_ticker(ticker)
    basic = ds.fetch_basic(ti)
    name = basic.get("name", ti.code)

    # Search queries — use full name + stock context to avoid dictionary hits
    # Add "股票" or "上市公司" to anchor the query in finance domain
    full_name = basic.get("full_name") or name
    stock_anchor = f"{name} 上市公司"
    queries = {
        "intangible": f"{stock_anchor} 专利 核心技术 品牌壁垒 竞争优势",
        "switching": f"{stock_anchor} 客户粘性 转换成本 认证壁垒 大客户",
        "network": f"{stock_anchor} 平台效应 网络效应 用户生态",
        "scale": f"{stock_anchor} 市场份额 行业地位 规模优势 龙头",
        "rd": f"{stock_anchor} 研发投入 研发占比 技术实力",
    }

    # v2.15.1 · 计算 superstar polluters（排除目标本身）· 防止 DDGS 对生僻公司返超级股票的结果
    superstar_set = {p for p in _SUPERSTAR_POLLUTERS if p not in (name or "") and p not in (full_name or "")}

    results: dict[str, dict] = {}
    for key, q in queries.items():
        # v2.7.3 · 护城河查询用 14_moat 权威域（每经/一财/中证网/华尔街见闻）
        # 权威域未命中时用普通 search 补位
        res_t = search_trusted(q, dim_key="14_moat", max_results=6)
        res = res_t if len(res_t) >= 3 else list(res_t) + list(search(q, max_results=6))
        # Filter: remove errors + dictionary garbage + 公司名不匹配的污染结果（v2.15.1）
        valid = [r for r in res
                 if "error" not in r
                 and not _is_garbage(r.get("body", "") + r.get("title", ""))
                 and _result_mentions_company(r, name, superstar_set)]
        combined_text = " ".join(r.get("body", "") for r in valid)
        results[key] = {
            "text": combined_text,
            "snippets": [
                {"title": r.get("title", "")[:80], "body": r.get("body", "")[:200], "url": r.get("url", "")}
                for r in valid[:2]
            ],
        }

    # Score each moat dimension (1-10)
    intangible_score = _evaluate(
        results["intangible"]["text"],
        pos_kws=["专利", "核心技术", "自主", "垄断", "独家", "行业领先", "国产替代"],
        neg_kws=["模仿", "同质", "无差异"],
    )
    switching_score = _evaluate(
        results["switching"]["text"],
        pos_kws=["绑定", "独家", "长期合作", "认证", "唯一", "二供", "一供"],
        neg_kws=["易替换", "议价弱"],
    )
    network_score = _evaluate(
        results["network"]["text"],
        pos_kws=["平台", "生态", "网络", "用户基数"],
        neg_kws=["单点", "无网络"],
    )
    scale_score = _evaluate(
        results["scale"]["text"],
        pos_kws=["龙头", "第一", "领先", "最大", "份额", "国产替代"],
        neg_kws=["追赶", "落后", "份额低"],
    )

    # Build qualitative descriptions
    def _top_body(key: str, n: int = 1) -> str:
        snips = results[key]["snippets"]
        return " ".join(s.get("body", "")[:100] for s in snips[:n])

    return {
        "ticker": ti.full,
        "data": {
            "intangible": _top_body("intangible") or "—",
            "switching": _top_body("switching") or "—",
            "network": _top_body("network") or "—",
            "scale": _top_body("scale") or "—",
            "scores": {
                "intangible": intangible_score,
                "switching": switching_score,
                "network": network_score,
                "scale": scale_score,
            },
            "rd_summary": _top_body("rd", n=2) or "—",
            "web_search_snippets": {k: v["snippets"] for k, v in results.items()},
            "moat_framework": ["intangible", "switching", "network", "scale", "efficient_scale"],
        },
        "source": "web_search:ddgs + keyword scoring",
        "fallback": False,
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"), ensure_ascii=False, indent=2, default=str))
