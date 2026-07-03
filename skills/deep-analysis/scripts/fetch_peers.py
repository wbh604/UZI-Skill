"""Dimension 4 - peer comparison: output peer_table + peer_comparison."""
from __future__ import annotations

import json
import os
import sys
import time

import akshare as ak  # type: ignore
from lib import data_sources as ds
from lib.fast_basic import fetch_basic_fast
from lib.market_router import parse_ticker

DASH = "—"


def _float(v, default=0.0):
    try:
        s = str(v).replace(",", "").replace("%", "")
        if s in ("", "nan", "-", "--", "None"):
            return default
        return float(s)
    except (ValueError, TypeError):
        return default


def _format_pe(v) -> str:
    x = _float(v)
    return f"{x:.1f}" if x > 0 else DASH


def _format_pb(v) -> str:
    x = _float(v)
    return f"{x:.2f}" if x > 0 else DASH


def _build_self_only_table(ti, basic: dict) -> tuple[list, list]:
    """Tier 4 fallback: return at least the company itself."""
    self_row = {
        "name": basic.get("name") or ti.full,
        "code": ti.full,
        "pe": _format_pe(basic.get("pe_ttm")),
        "pb": _format_pb(basic.get("pb")),
        "roe": DASH,
        "revenue_growth": DASH,
        "is_self": True,
    }
    return [self_row], []


STATIC_A_SHARE_PEERS: dict[str, list[tuple[str, str]]] = {
    "银行": [
        ("600036.SH", "招商银行"),
        ("601398.SH", "工商银行"),
        ("601939.SH", "建设银行"),
        ("601288.SH", "农业银行"),
        ("601328.SH", "交通银行"),
        ("601166.SH", "兴业银行"),
        ("600016.SH", "民生银行"),
        ("600000.SH", "浦发银行"),
        ("601818.SH", "光大银行"),
        ("601998.SH", "中信银行"),
        ("600919.SH", "江苏银行"),
        ("601009.SH", "南京银行"),
        ("601229.SH", "上海银行"),
        ("600926.SH", "杭州银行"),
    ],
    "光模块": [
        ("300308.SZ", "中际旭创"),
        ("300502.SZ", "新易盛"),
        ("300394.SZ", "天孚通信"),
        ("688498.SH", "源杰科技"),
        ("300548.SZ", "博创科技"),
        ("603083.SH", "剑桥科技"),
    ],
    "电池": [
        ("300750.SZ", "宁德时代"),
        ("002812.SZ", "恩捷股份"),
        ("300014.SZ", "亿纬锂能"),
        ("002709.SZ", "天赐材料"),
        ("002460.SZ", "赣锋锂业"),
        ("002466.SZ", "天齐锂业"),
    ],
}


def _static_peer_seed(industry: str) -> list[tuple[str, str]]:
    if not industry:
        return []
    for key, rows in STATIC_A_SHARE_PEERS.items():
        if key in industry:
            return rows
    return []


def _build_static_peer_table(ti, basic: dict, industry: str) -> tuple[list, list, list]:
    rows = list(_static_peer_seed(industry))
    if not rows:
        return [], [], []

    code_to_name = {code: name for code, name in rows}
    code_to_name[ti.full] = basic.get("name") or code_to_name.get(ti.full) or ti.full

    ordered_codes = [ti.full] + [code for code, _ in rows if code != ti.full]
    table = []
    raw = []
    for code in ordered_codes[:6]:
        is_self = code == ti.full
        name = code_to_name.get(code, code)
        row = {
            "name": name,
            "code": code,
            "pe": _format_pe(basic.get("pe_ttm")) if is_self else DASH,
            "pb": _format_pb(basic.get("pb")) if is_self else DASH,
            "roe": DASH,
            "revenue_growth": DASH,
        }
        if is_self:
            row["is_self"] = True
        table.append(row)
        raw.append({"tier": 0, "source": "local_static_peers", **row})

    comparison = [
        {"name": "PE (越低越好)", "self": _float(basic.get("pe_ttm")), "peer": DASH},
        {"name": "PB (越低越好)", "self": _float(basic.get("pb")), "peer": DASH},
    ]
    return raw, table, comparison


def _first(row: dict, keys: tuple[str, ...], default=""):
    for key in keys:
        if key in row:
            return row.get(key)
    return default


def _parse_peer_df(df, basic: dict, self_code: str, self_full: str):
    """Shared parser: DataFrame -> (peers_raw, peer_table, peer_comparison)."""
    df = df.copy()
    mcap_col = next((c for c in ("总市值", "总市值 ", "市值", "鎬诲競鍊?") if c in df.columns), None)
    if mcap_col:
        df["_mcap"] = df[mcap_col].apply(_float)
        df = df.sort_values("_mcap", ascending=False)
    raw = df.head(20).to_dict("records")

    self_row = None
    peers_top5 = []
    for r in raw:
        code = str(_first(r, ("代码", "证券代码", "浠ｇ爜"), ""))
        name = _first(r, ("名称", "证券简称", "鍚嶇О"), "")
        pe = _first(r, ("市盈率-动态", "市盈率", "PE", "甯傜泩鐜?鍔ㄦ€?"), "")
        pb = _first(r, ("市净率", "PB", "甯傚噣鐜?"), "")
        entry = {
            "name": name,
            "code": code,
            "pe": _format_pe(pe),
            "pb": _format_pb(pb),
            "roe": DASH,
            "revenue_growth": DASH,
        }
        if code in (self_code, self_full):
            entry["is_self"] = True
            self_row = entry
        elif len(peers_top5) < 5:
            peers_top5.append(entry)

    table = ([self_row] if self_row else []) + peers_top5

    def _avg(keys: tuple[str, ...]) -> float:
        col = next((c for c in keys if c in df.columns), "")
        if not col:
            return 0.0
        vals = [_float(v) for v in df[col] if _float(v) > 0]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    comparison = [
        {"name": "PE (越低越好)", "self": _float(basic.get("pe_ttm")), "peer": _avg(("市盈率-动态", "市盈率", "PE", "甯傜泩鐜?鍔ㄦ€?"))},
        {"name": "PB (越低越好)", "self": _float(basic.get("pb")), "peer": _avg(("市净率", "PB", "甯傚噣鐜?"))},
    ]
    return raw, table, comparison


def main(ticker: str) -> dict:
    ti = parse_ticker(ticker)
    basic = fetch_basic_fast(ti)
    industry = basic.get("industry") or ""
    peers_raw: list = []
    peer_table: list = []
    peer_comparison: list = []

    if ti.market == "H":
        try:
            ranks = basic.get("_ranks") or {}
            val = ranks.get("valuation") or {}
            scale = ranks.get("scale") or {}
            growth = ranks.get("growth") or {}
        except Exception:
            val, scale, growth = {}, {}, {}
        self_row = {
            "name": basic.get("name") or ti.full,
            "code": ti.full,
            "pe": _format_pe(val.get("pe_ttm")),
            "pb": _format_pb(val.get("pb_mrq")),
            "roe": DASH,
            "revenue_growth": f"{growth.get('revenue_yoy', 0):.1f}%" if growth.get("revenue_yoy") else DASH,
            "is_self": True,
        }
        return {
            "ticker": ti.full,
            "data": {
                "industry": industry or "未分类（akshare HK 无行业聚合）",
                "self": basic,
                "peer_table": [self_row],
                "peer_comparison": [
                    {"name": "PE-TTM 排名 (HK 全市场)", "self": val.get("pe_ttm_rank"), "peer": DASH},
                    {"name": "PB-MRQ 排名 (HK 全市场)", "self": val.get("pb_mrq_rank"), "peer": DASH},
                    {"name": "总市值排名 (HK 全市场)", "self": scale.get("market_cap_rank"), "peer": DASH},
                    {"name": "营收 YoY 排名", "self": growth.get("revenue_yoy_rank"), "peer": DASH},
                ],
                "rank": f"HK 第 {scale.get('market_cap_rank')} 位（按总市值）" if scale.get("market_cap_rank") else DASH,
                "peers_top20_raw": [],
                "_note": "HK peer LIST 需要 AASTOCKS Playwright 或问财；本字段提供 rank-in-universe 替代。",
            },
            "source": "akshare:hk_valuation_comparison_em + scale_comparison_em + growth_comparison_em",
            "fallback": False,
        }

    fallback_used = False
    fallback_reason = ""
    source_used = "akshare:stock_board_industry_cons_em"

    if ti.market == "A" and industry:
        # Tier 0: local static fallback. This is the default path because Eastmoney push2
        # can hang behind some proxies; set UZI_PEERS_TRY_AK=1 to use the network source.
        peers_raw, peer_table, peer_comparison = _build_static_peer_table(ti, basic, industry)
        if peer_table:
            fallback_used = True
            fallback_reason = "akshare push2 默认关闭；使用本地静态同行兜底"
            source_used = "local_static_peers"

        # Tier 1: primary push2 source, explicit opt-in only.
        if not peer_table and os.environ.get("UZI_PEERS_TRY_AK") == "1":
            try:
                df = ak.stock_board_industry_cons_em(symbol=industry)
                if df is not None and not df.empty:
                    peers_raw, peer_table, peer_comparison = _parse_peer_df(df, basic, ti.code, ti.full)
                    fallback_used = False
                    source_used = "akshare:stock_board_industry_cons_em"
            except Exception as e:
                peers_raw = [{"tier": 1, "error": f"{type(e).__name__}: {str(e)[:200]}"}]

            # Tier 2: retry once for transient network failures.
            if not peer_table:
                try:
                    time.sleep(2.5)
                    df = ak.stock_board_industry_cons_em(symbol=industry)
                    if df is not None and not df.empty:
                        peers_raw, peer_table, peer_comparison = _parse_peer_df(df, basic, ti.code, ti.full)
                        fallback_used = True
                        fallback_reason = "Tier 1 网络失败；Tier 2 retry 成功"
                        source_used = "akshare:stock_board_industry_cons_em (retry)"
                except Exception as e:
                    peers_raw.append({"tier": 2, "error": f"{type(e).__name__}: {str(e)[:200]}"})
        elif not peer_table:
            peers_raw.append({"tier": 1, "skipped": "set UZI_PEERS_TRY_AK=1 to enable Eastmoney push2"})

        # Tier 3: Xueqiu Playwright login fallback, still opt-in via UZI_XQ_LOGIN=1.
        if not peer_table:
            try:
                from lib.xueqiu_browser import fetch_peers_via_browser, is_login_enabled
                if is_login_enabled():
                    xq_peers = fetch_peers_via_browser(ti.code)
                    if xq_peers:
                        import pandas as pd

                        xq_df = pd.DataFrame([
                            {
                                "代码": p.get("code", ""),
                                "名称": p.get("name", ""),
                                "总市值": p.get("mcap_yi", 0),
                                "市盈率-动态": p.get("pe", 0),
                                "市净率": p.get("pb", 0),
                            }
                            for p in xq_peers
                        ])
                        if not xq_df.empty:
                            peers_raw, peer_table, peer_comparison = _parse_peer_df(xq_df, basic, ti.code, ti.full)
                            fallback_used = True
                            fallback_reason = "akshare 不可用；Tier 3 雪球浏览器兜底成功"
                            source_used = f"xueqiu.com/S/{ti.code} (playwright)"
            except Exception as e:
                peers_raw.append({"tier": 3, "error": f"{type(e).__name__}: {str(e)[:200]}"})

        # Tier 4: self-only final fallback.
        if not peer_table:
            peer_table, peer_comparison = _build_self_only_table(ti, basic)
            fallback_used = True
            if not fallback_reason:
                fallback_reason = "所有同行数据源失败；仅返回公司自身"
            source_used += " (self-only fallback)"

    if ti.market == "A" and not peer_table:
        peer_table, peer_comparison = _build_self_only_table(ti, basic)
        fallback_used = True
        if not fallback_reason:
            fallback_reason = "行业缺失或同行数据源失败；仅返回公司自身"
        if "self-only fallback" not in source_used:
            source_used += " (self-only fallback)"

    return {
        "ticker": ti.full,
        "data": {
            "industry": industry,
            "self": basic,
            "peer_table": peer_table,
            "peer_comparison": peer_comparison,
            "rank": DASH,
            "peers_top20_raw": peers_raw[:20],
            "fallback_reason": fallback_reason,
        },
        "source": source_used,
        "fallback": fallback_used,
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"), ensure_ascii=False, indent=2, default=str))
