"""Dimension 4 · 同行对比 — 产出 peer_table + peer_comparison."""
from __future__ import annotations

import json
import os
import sys
import time

import akshare as ak  # type: ignore
from lib import data_sources as ds
from lib.market_router import parse_ticker


def _float(v, default=0.0):
    try:
        s = str(v).replace(",", "").replace("%", "")
        if s in ("", "nan", "-", "--", "None"):
            return default
        return float(s)
    except (ValueError, TypeError):
        return default


def _build_self_only_table(ti, basic: dict) -> tuple[list, list]:
    """v2.12.1 · Tier 4 兜底：只返回公司自己一行，agent 可识别需外部补同行数据."""
    self_row = {
        "name": basic.get("name") or ti.full,
        "code": ti.full,
        "pe": f"{_float(basic.get('pe_ttm')):.1f}" if _float(basic.get("pe_ttm")) > 0 else "—",
        "pb": f"{_float(basic.get('pb')):.2f}" if _float(basic.get("pb")) > 0 else "—",
        "roe": "—",
        "revenue_growth": "—",
        "is_self": True,
    }
    return [self_row], []


def main(ticker: str) -> dict:
    ti = parse_ticker(ticker)
    basic = ds.fetch_basic(ti)
    industry = basic.get("industry") or ""
    peers_raw: list = []
    peer_table: list = []
    peer_comparison: list = []

    # v2.5 · HK 分支：用 akshare HK valuation/scale comparison 给出 rank-in-HK-universe，
    # 没有具体同行名单（akshare 港股没有按行业列表函数；agent 可走 AASTOCKS Playwright 兜底）
    if ti.market == "H":
        # v2.12.1 · HK 分支独立 try/except 隔离（HK 数据路径与 A 股独立，失败不应污染）
        try:
            ranks = (basic.get("_ranks") or {})
            val = ranks.get("valuation") or {}
            scale = ranks.get("scale") or {}
            growth = ranks.get("growth") or {}
        except Exception:
            ranks, val, scale, growth = {}, {}, {}, {}
        # 用 PE/PB/Mcap 排名构造一行 self
        self_row = {
            "name": basic.get("name") or ti.full,
            "code": ti.full,
            "pe": f"{val.get('pe_ttm', 0):.1f}" if val.get("pe_ttm") else "—",
            "pb": f"{val.get('pb_mrq', 0):.2f}" if val.get("pb_mrq") else "—",
            "roe": "—",
            "revenue_growth": f"{growth.get('revenue_yoy', 0):.1f}%" if growth.get("revenue_yoy") else "—",
            "is_self": True,
        }
        peer_table = [self_row]
        peer_comparison = [
            {"name": "PE-TTM 排名 (HK 全市场)", "self": val.get("pe_ttm_rank"), "peer": "—"},
            {"name": "PB-MRQ 排名 (HK 全市场)", "self": val.get("pb_mrq_rank"), "peer": "—"},
            {"name": "总市值排名 (HK 全市场)", "self": scale.get("market_cap_rank"), "peer": "—"},
            {"name": "营收 YoY 排名", "self": growth.get("revenue_yoy_rank"), "peer": "—"},
        ]
        # rank string for the report
        mcap_rank = scale.get("market_cap_rank")
        rank_str = f"HK 第 {mcap_rank} 位（按总市值）" if mcap_rank else "—"
        return {
            "ticker": ti.full,
            "data": {
                "industry": industry or "未分类（akshare HK 无行业聚合）",
                "self": basic,
                "peer_table": peer_table,
                "peer_comparison": peer_comparison,
                "rank": rank_str,
                "peers_top20_raw": [],
                "_note": "HK peer LIST 需走 AASTOCKS Playwright 或问财；本字段提供 rank-in-universe 作替代",
            },
            "source": "akshare:hk_valuation_comparison_em + scale_comparison_em + growth_comparison_em",
            "fallback": False,
        }

    # v2.12.1 · A 股分支 · 三层 fallback 链防止 push2 挂了报告空板块
    fallback_used = False
    fallback_reason = ""
    source_used = "akshare:stock_board_industry_cons_em"

    def _parse_peer_df(df, self_ticker_code: str):
        """共用解析逻辑：df → (peers_raw, peer_table, peer_comparison)."""
        df = df.copy()
        df["_mcap"] = df["总市值"].apply(_float) if "总市值" in df.columns else 0
        df = df.sort_values("_mcap", ascending=False)
        raw = df.head(20).to_dict("records")

        self_row = None
        peers_top5 = []
        for r in raw:
            code = str(r.get("代码", ""))
            name = r.get("名称", "")
            entry = {
                "name": name, "code": code,
                "pe": f"{_float(r.get('市盈率-动态')):.1f}" if _float(r.get("市盈率-动态")) > 0 else "—",
                "pb": f"{_float(r.get('市净率')):.2f}" if _float(r.get("市净率")) > 0 else "—",
                "roe": "—", "revenue_growth": "—",
            }
            if code == self_ticker_code:
                entry["is_self"] = True
                self_row = entry
            elif len(peers_top5) < 5:
                peers_top5.append(entry)

        tbl = ([self_row] if self_row else []) + peers_top5

        def _avg(col):
            if col not in df.columns: return 0.0
            vals = [_float(v) for v in df[col] if _float(v) > 0]
            return round(sum(vals) / len(vals), 2) if vals else 0.0

        cmp = [
            {"name": "PE (越低越好)", "self": _float(basic.get("pe_ttm")), "peer": _avg("市盈率-动态")},
            {"name": "PB (越低越好)", "self": _float(basic.get("pb")),     "peer": _avg("市净率")},
        ]
        return raw, tbl, cmp

    if ti.market == "A" and industry:
        # ─── Tier 1: 主链（push2） ───
        try:
            df = ak.stock_board_industry_cons_em(symbol=industry)
            if df is not None and not df.empty:
                peers_raw, peer_table, peer_comparison = _parse_peer_df(df, ti.code)
        except Exception as e:
            peers_raw = [{"tier": 1, "error": f"{type(e).__name__}: {str(e)[:200]}"}]

        # ─── Tier 2: 重试一次（网络抖动） ───
        if not peer_table:
            try:
                time.sleep(2.5)
                df = ak.stock_board_industry_cons_em(symbol=industry)
                if df is not None and not df.empty:
                    peers_raw, peer_table, peer_comparison = _parse_peer_df(df, ti.code)
                    fallback_used = True
                    fallback_reason = "Tier 1 网络失败 · Tier 2 retry 成功"
                    source_used += " (retry)"
            except Exception as e:
                peers_raw.append({"tier": 2, "error": f"{type(e).__name__}: {str(e)[:200]}"})

        # ─── Tier 3: 雪球 Playwright 登录兜底（用户 opt-in） ───
        if not peer_table:
            try:
                from lib.xueqiu_browser import is_login_enabled, fetch_peers_via_browser
                if is_login_enabled():
                    xq_peers = fetch_peers_via_browser(ti.code)  # 返 list[dict]
                    if xq_peers:
                        # 构造兼容的 df-like 结构
                        import pandas as pd
                        xq_df = pd.DataFrame([
                            {"代码": p.get("code", ""), "名称": p.get("name", ""),
                             "总市值": p.get("mcap_yi", 0),
                             "市盈率-动态": p.get("pe", 0), "市净率": p.get("pb", 0)}
                            for p in xq_peers
                        ])
                        if not xq_df.empty:
                            peers_raw, peer_table, peer_comparison = _parse_peer_df(xq_df, ti.code)
                            fallback_used = True
                            fallback_reason = "Tier 1/2 akshare 失败 · Tier 3 雪球浏览器兜底"
                            source_used = "xueqiu.com/S/{code} (playwright)"
            except Exception as e:
                peers_raw.append({"tier": 3, "error": f"{type(e).__name__}: {str(e)[:200]}"})

        # ─── Tier 4 保底：仅公司自己一行 + fallback 标记 ───
        if not peer_table:
            peer_table, peer_comparison = _build_self_only_table(ti, basic)
            fallback_used = True
            if not fallback_reason:
                fallback_reason = "所有同行数据源失败 · 仅返回公司自身"
            source_used += " (self-only fallback)"

    return {
        "ticker": ti.full,
        "data": {
            "industry": industry,
            "self": basic,
            "peer_table": peer_table,
            "peer_comparison": peer_comparison,
            "rank": "—",  # 真实排名需要 聚合查询
            "peers_top20_raw": peers_raw[:20],
            "fallback_reason": fallback_reason,  # v2.12.1
        },
        "source": source_used,
        "fallback": fallback_used,
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"), ensure_ascii=False, indent=2, default=str))
