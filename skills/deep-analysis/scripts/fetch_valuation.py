"""Dimension 10 · 估值 (PE/PB/PEG/历史分位 + 简化 DCF + EV/EBITDA stub).

补全：原方案要求 PE/PB/PEG/PS/EV/EBITDA + DCF + 历史分位 + 行业中枢
"""
from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any

import akshare as ak  # type: ignore
from lib import data_sources as ds
from lib.data_quality import DataQuality, build_quality_report, mark_field
from lib.data_source_registry import source_health_snapshot
from lib.market_router import parse_ticker


def _find_weighted_pe_col(df) -> str | None:
    return next((c for c in df.columns if "市盈率" in c and "加权" in c), None)


def _market_weighted_pe(df) -> float | None:
    pe_col = _find_weighted_pe_col(df)
    if not pe_col:
        return None
    vals = []
    for v in df[pe_col].tolist():
        try:
            pe = float(v)
        except (TypeError, ValueError):
            continue
        if 0 < pe < 500:
            vals.append(pe)
    return round(sum(vals) / len(vals), 2) if vals else None


def _safe_float(v: Any, default: float | None = None) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if 0 < abs(f) < 1e15 else default


def _http_get_json(url: str, headers: dict | None = None, timeout: int = 8) -> dict:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _downsample(values: list[float], max_points: int = 60) -> list[float]:
    if len(values) <= max_points:
        return values
    step = max(1, len(values) // max_points)
    return values[::step]


def _percentile(current: Any, history: list[float]) -> float | None:
    cur = _safe_float(current)
    if cur is None or not history:
        return None
    valid = [v for v in history if v and v > 0]
    if not valid:
        return None
    return sum(1 for v in sorted(valid) if v < cur) / len(valid) * 100


def _fetch_eastmoney_valuation_history(code: str, history_len: int = 250) -> dict:
    url = (
        "https://datacenter-web.eastmoney.com/api/data/v1/get"
        "?reportName=RPT_VALUEANALYSIS_DET&columns=ALL"
        f"&filter=(SECURITY_CODE%3D%22{code}%22)"
        f"&pageSize={history_len}&sortColumns=TRADE_DATE&sortTypes=-1"
    )
    data = _http_get_json(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"})
    rows = sorted(((data.get("result") or {}).get("data") or []), key=lambda r: str(r.get("TRADE_DATE", "")))
    pe_history = [v for v in (_safe_float(r.get("PE_TTM")) for r in rows) if v is not None]
    pb_history = [v for v in (_safe_float(r.get("PB_MRQ")) for r in rows) if v is not None]
    return {
        "pe_history": pe_history,
        "pb_history": pb_history,
        "history_dates": [str(r.get("TRADE_DATE", ""))[:10] for r in rows],
        "source": "eastmoney:RPT_VALUEANALYSIS_DET",
    }


def simple_dcf(
    fcf_latest: float,
    growth_5y: float = 0.10,
    growth_terminal: float = 0.03,
    wacc: float = 0.10,
    years: int = 10,
) -> dict:
    """5+5 阶段简易 DCF，永续增长。"""
    if fcf_latest <= 0:
        return {"intrinsic_value": None, "_note": "negative FCF, DCF not applicable"}
    fcfs = []
    fcf = fcf_latest
    for y in range(1, years + 1):
        g = growth_5y if y <= 5 else (growth_5y + growth_terminal) / 2
        fcf *= 1 + g
        fcfs.append(fcf)
    pv_fcfs = sum(f / (1 + wacc) ** (i + 1) for i, f in enumerate(fcfs))
    terminal_value = fcfs[-1] * (1 + growth_terminal) / (wacc - growth_terminal)
    pv_terminal = terminal_value / (1 + wacc) ** years
    return {
        "intrinsic_value_total": pv_fcfs + pv_terminal,
        "pv_fcfs": pv_fcfs,
        "pv_terminal": pv_terminal,
        "assumptions": {
            "fcf_latest": fcf_latest, "growth_5y": growth_5y,
            "growth_terminal": growth_terminal, "wacc": wacc,
        },
    }


def dcf_sensitivity_matrix(
    fcf_latest: float,
    waccs: list[float],
    growths: list[float],
    current_price: float,
    shares_out: float = 1e9,  # 默认 10 亿股，生产环境应该从 basic 拉
    years: int = 10,
) -> dict:
    """Compute sensitivity matrix of intrinsic price across WACC x growth."""
    values = []
    for w in waccs:
        row = []
        for g in growths:
            result = simple_dcf(fcf_latest=fcf_latest, growth_5y=g / 100, wacc=w / 100, years=years)
            iv = result.get("intrinsic_value_total") or 0
            per_share = iv / shares_out if shares_out else 0
            row.append(round(per_share, 2))
        values.append(row)
    return {
        "waccs": waccs,
        "growths": growths,
        "values": values,
        "current_price": current_price,
    }


def main(ticker: str) -> dict:
    ti = parse_ticker(ticker)
    basic = ds.fetch_basic(ti)
    pe_history: list = []
    pb_history: list = []
    history_source = ""
    pe_quantile_val = None
    pb_quantile_val = None
    industry_pe_avg = None
    industry_pe_fallback_reason = ""

    if ti.market == "A":
        # 1. PE 5 年历史序列 via 百度股市通 (stock_zh_valuation_baidu)
        try:
            df_pe = ak.stock_zh_valuation_baidu(symbol=ti.code, indicator="市盈率(TTM)", period="近五年")
            if df_pe is not None and not df_pe.empty and "value" in df_pe.columns:
                pes_full = [round(float(v), 2) for v in df_pe["value"] if v and float(v) > 0]
                pe_history = pes_full[:]
                if len(pe_history) > 60:
                    step = len(pe_history) // 60
                    pe_history = pe_history[::step]

                cur_pe = basic.get("pe_ttm") or (pes_full[-1] if pes_full else 0)
                if cur_pe and pes_full:
                    sorted_pe = sorted(pes_full)
                    pe_quantile_val = sum(1 for x in sorted_pe if x < cur_pe) / len(sorted_pe) * 100
        except Exception as e:
            pe_history = []

        # PB history similar
        try:
            df_pb = ak.stock_zh_valuation_baidu(symbol=ti.code, indicator="市净率", period="近五年")
            if df_pb is not None and not df_pb.empty and "value" in df_pb.columns:
                pbs = [float(v) for v in df_pb["value"] if v and float(v) > 0]
                cur_pb = basic.get("pb")
                if cur_pb and pbs:
                    sorted_pb = sorted(pbs)
                    pb_quantile_val = sum(1 for x in sorted_pb if x < cur_pb) / len(sorted_pb) * 100
        except Exception:
            pass

        if not pe_history or pb_quantile_val is None:
            try:
                em_hist = _fetch_eastmoney_valuation_history(ti.code)
                if not pe_history and em_hist.get("pe_history"):
                    pe_history = _downsample(em_hist["pe_history"])
                    pe_quantile_val = _percentile(basic.get("pe_ttm") or (em_hist["pe_history"][-1] if em_hist["pe_history"] else None), em_hist["pe_history"])
                    history_source = em_hist.get("source", "")
                if em_hist.get("pb_history"):
                    pb_history = _downsample(em_hist["pb_history"])
                    if pb_quantile_val is None:
                        pb_quantile_val = _percentile(basic.get("pb") or (em_hist["pb_history"][-1] if em_hist["pb_history"] else None), em_hist["pb_history"])
                    history_source = history_source or em_hist.get("source", "")
            except Exception:
                pass

        # 2. 行业 PE 均值 - use cninfo (bypass push2)
        try:
            from datetime import datetime as _dt, timedelta as _td
            today = _dt.now()
            # Try yesterday (data publishes daily with lag)
            for d in [today - _td(days=i) for i in range(1, 8)]:
                try:
                    df = ak.stock_industry_pe_ratio_cninfo(
                        symbol="证监会行业分类", date=d.strftime("%Y%m%d")
                    )
                    if df is not None and not df.empty:
                        # v2.8.3 · 用语义映射替代 str.contains(industry[:2])
                        ind_name = basic.get("industry") or ""
                        from lib.industry_mapping import resolve_csrc_industry as _resolve
                        row = _resolve(ind_name, df) if ind_name else None
                        if row is not None:
                            pe_col = _find_weighted_pe_col(df)
                            if pe_col:
                                industry_pe_avg = round(float(row[pe_col]), 2)
                                break
                        elif not ind_name:
                            market_pe = _market_weighted_pe(df)
                            if market_pe is not None:
                                industry_pe_avg = market_pe
                                industry_pe_fallback_reason = "basic.industry 缺失 · 使用 cninfo 市场加权均值"
                                break
                        else:
                            market_pe = _market_weighted_pe(df)
                            if market_pe is not None:
                                industry_pe_avg = market_pe
                                industry_pe_fallback_reason = f"行业 {ind_name} 未匹配 · 使用 cninfo 市场加权均值"
                                break
                except Exception:
                    continue
        except Exception:
            pass

    # v2.9 · 港股 industry_pe fallback（cninfo 只支持 A 股）
    # HK 走 akshare hk_valuation_comparison_em（peer 平均 PE）或启发式同行 PE
    if ti.market == "H" and industry_pe_avg is None:
        try:
            df_hk = ak.hk_valuation_comparison_em(symbol=ti.code.zfill(5))
            if df_hk is not None and not df_hk.empty and "PE(TTM)" in df_hk.columns:
                pes = [float(v) for v in df_hk["PE(TTM)"] if v and not (isinstance(v, str) and v in ("-", "—"))]
                pes = [p for p in pes if p > 0 and p < 500]
                if pes:
                    industry_pe_avg = round(sum(pes) / len(pes), 2)
        except Exception:
            pass

    # 3. DCF 敏感度矩阵 - use fetch_financials output from our upgraded fetcher
    dcf_result: dict = {}
    dcf_sensitivity: dict = {}
    try:
        # Import our upgraded fetch_financials instead of the raw ds
        from fetch_financials import main as _fin_main
        fin_result = _fin_main(ti.full)
        fin_data = fin_result.get("data", {}) if isinstance(fin_result, dict) else {}
        net_profit_hist = fin_data.get("net_profit_history", [])
        net_profit_latest_yi = net_profit_hist[-1] if net_profit_hist else 0  # 亿元

        if net_profit_latest_yi > 0:
            # Convert 亿 → 元 for DCF calc
            net_profit_yuan = net_profit_latest_yi * 1e8
            dcf_result = simple_dcf(fcf_latest=net_profit_yuan * 0.8)
            current_price = basic.get("price") or 0
            total_shares = basic.get("total_shares") or 0
            if not total_shares:
                # derive from market_cap_raw / price
                mcap_raw = basic.get("market_cap_raw") or 0
                if current_price and mcap_raw:
                    total_shares = mcap_raw / current_price
            # v3.9.4 · 不再硬编码 1e9 股本 —— 推导失败时标记数据不足，
            # 否则每股内在价值会基于"10 亿股"算错（对市值偏离 10 亿的公司尤其荒谬）
            if total_shares:
                dcf_sensitivity = dcf_sensitivity_matrix(
                    fcf_latest=net_profit_yuan * 0.8,
                    waccs=[8, 9, 10, 11, 12],
                    growths=[6, 8, 10, 12],
                    current_price=current_price,
                    shares_out=total_shares,
                )
            else:
                dcf_sensitivity = {"_note": "股本数据缺失 · 无法计算每股敏感性", "values": []}
    except Exception as e:
        dcf_result = {"error": str(e)[:80]}

    cur_pe = basic.get("pe_ttm")
    iv_total = dcf_result.get("intrinsic_value_total") if isinstance(dcf_result, dict) else None
    dcf_display = f"¥{iv_total / 1e8:.1f}亿" if iv_total else "—"
    quality_fields = {
        "pe": mark_field(cur_pe, DataQuality.ACTUAL if cur_pe is not None else DataQuality.UNAVAILABLE, str(basic.get("source") or "basic")),
        "pb": mark_field(basic.get("pb"), DataQuality.ACTUAL if basic.get("pb") is not None else DataQuality.UNAVAILABLE, str(basic.get("source") or "basic")),
        "pe_quantile": mark_field(pe_quantile_val, DataQuality.DERIVED if pe_quantile_val is not None else DataQuality.UNAVAILABLE, history_source or "baidu:valuation"),
        "pb_quantile": mark_field(pb_quantile_val, DataQuality.DERIVED if pb_quantile_val is not None else DataQuality.UNAVAILABLE, history_source or "baidu:valuation"),
        "industry_pe": mark_field(industry_pe_avg, DataQuality.ACTUAL if industry_pe_avg else DataQuality.UNAVAILABLE, "cninfo/hk_valuation"),
        "dcf": mark_field(iv_total, DataQuality.ESTIMATED if iv_total else DataQuality.UNAVAILABLE, "simple_dcf", "FCF proxy + fixed assumptions"),
    }

    return {
        "ticker": ti.full,
        "data": {
            "pe": str(cur_pe) if cur_pe is not None else "—",
            "pb": str(basic.get("pb")) if basic.get("pb") is not None else "—",
            "pe_quantile": f"5 年 {pe_quantile_val:.0f} 分位" if pe_quantile_val is not None else "—",
            "pb_quantile": f"{pb_quantile_val:.0f}%" if pb_quantile_val is not None else "—",
            "industry_pe": str(industry_pe_avg) if industry_pe_avg else "—",
            "industry_pe_fallback_reason": industry_pe_fallback_reason,
            "dcf": dcf_display,
            "pe_history": pe_history,
            "pb_history": pb_history,
            "valuation_history_source": history_source or ("baidu:valuation" if pe_history else ""),
            "dcf_simple": dcf_result,
            "dcf_sensitivity": dcf_sensitivity,
            "quality_fields": quality_fields,
            "data_quality": build_quality_report(quality_fields),
            "source_health": source_health_snapshot("10_valuation", ti.market),
        },
        "source": "baidu:valuation + cninfo:industry_pe_ratio + simple_dcf",
        "fallback": False,
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"), ensure_ascii=False, indent=2, default=str))
