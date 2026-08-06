"""Dimension 10 · 估值 (PE/PB/PEG/历史分位 + 简化 DCF + EV/EBITDA stub).

补全：原方案要求 PE/PB/PEG/PS/EV/EBITDA + DCF + 历史分位 + 行业中枢
"""
from __future__ import annotations

import json
import sys
from typing import Any

import akshare as ak  # type: ignore
from lib import data_sources as ds
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


def _mx_latest_pct(result: dict, label_substr: str) -> tuple[float, str] | tuple[None, None]:
    """Pull newest percentage + window label from MX SEARCH_DATA.

    Returns (value, window) where window is like "3 年" / "5 年" / "历史" inferred
    from the MX indicator name. Avoids hardcoding "5 年" when MX returns 3Y series.
    """
    if not isinstance(result, dict) or result.get("error"):
        return None, None
    data = result.get("data") or {}
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    sr = (inner or {}).get("searchDataResultDTO") or {}
    for dto in sr.get("dataTableDTOList") or []:
        if not isinstance(dto, dict):
            continue
        table = dto.get("table") or dto.get("rawTable") or {}
        name_map = dto.get("nameMap") or {}
        if isinstance(name_map, list):
            name_map = {str(i): v for i, v in enumerate(name_map)}
        for key, values in table.items():
            if key == "headName" or not isinstance(values, list) or not values:
                continue
            label = str(name_map.get(key) or name_map.get(str(key)) or key)
            if label_substr not in label:
                continue
            for raw in values:
                try:
                    v = float(str(raw).replace("%", "").replace("倍", "").replace(",", "").strip())
                except (TypeError, ValueError):
                    continue
                if v >= 0:
                    window = "历史"
                    if "5年" in label or "5 年" in label:
                        window = "5 年"
                    elif "3年" in label or "3 年" in label:
                        window = "3 年"
                    elif "上市以来" in label:
                        window = "上市以来"
                    return v, window
    return None, None


def _fetch_valuation_via_mx(code: str, name_hint: str = "", basic: dict | None = None) -> dict:
    """Safe valuation fill from basic + 东财妙想 · no mini_racer / baidu / cninfo.

    Used when UZI_DISABLE_MINI_RACER=1 or baidu SSL fails. Returns data dict
    compatible with main()'s data shape (may be partial).
    """
    basic = basic or {}
    try:
        from lib.mx_api import MXClient
    except Exception:
        return {}
    client = MXClient()
    if not client.available and not basic:
        return {}

    label = (name_hint or "").strip() or code
    pe = basic.get("pe_ttm")
    pb = basic.get("pb")
    used_basic = pe is not None or pb is not None
    used_mx = False
    pe_q = None
    pe_window = "5 年"
    pb_q = None

    if client.available:
        # current PE/PB if basic missing
        if pe is None or pb is None:
            snap = client.fetch_snapshot(label) or {}
            if pe is None:
                for k, v in snap.items():
                    if "市盈率" in str(k) or "PE" in str(k).upper():
                        try:
                            pe = float(str(v).replace("%", "").replace("倍", ""))
                            used_mx = True
                            break
                        except (TypeError, ValueError):
                            pass
            if pb is None:
                for k, v in snap.items():
                    if "市净率" in str(k) or str(k).upper() == "PB":
                        try:
                            pb = float(str(v).replace("%", "").replace("倍", ""))
                            used_mx = True
                            break
                        except (TypeError, ValueError):
                            pass

        pe_q, pe_window = _mx_latest_pct(
            client.query(f"{label} 市盈率近五年分位数"),
            "市盈率",
        )
        if pe_q is None:
            pe_q, pe_window = _mx_latest_pct(
                client.query(f"{code} 市盈率历史百分位"),
                "市盈率",
            )
        pb_q, _pb_window = _mx_latest_pct(
            client.query(f"{label} 市净率近五年分位数"),
            "市净率",
        )
        if pb_q is None:
            pb_q, _pb_window = _mx_latest_pct(
                client.query(f"{code} 市净率PB历史百分位"),
                "市净率",
            )
        if pe_q is not None or pb_q is not None:
            used_mx = True

    if used_basic and used_mx:
        source = "basic+mx_api"
    elif used_mx:
        source = "mx_api"
    else:
        source = "basic"

    out: dict[str, Any] = {"_valuation_source": source}
    if pe is not None:
        out["pe"] = str(pe)
    if pb is not None:
        out["pb"] = str(pb)
    if pe_q is not None:
        out["pe_quantile"] = f"{pe_window or '5 年'} {pe_q:.0f} 分位"
    if pb_q is not None:
        out["pb_quantile"] = f"{pb_q:.0f}%"
    return out


def main_safe(ticker: str) -> dict:
    """Valuation without mini_racer-prone akshare calls (baidu/cninfo/lg)."""
    ti = parse_ticker(ticker)
    basic = {}
    try:
        basic = ds.fetch_basic(ti) or {}
    except Exception:
        basic = {}
    data = _fetch_valuation_via_mx(ti.code, getattr(ti, "raw", "") or basic.get("name") or "", basic)
    # ensure coverage fields aren't left as em-dash placeholders
    if "pe" not in data:
        data["pe"] = "—"
    if "pb" not in data:
        data["pb"] = "—"
    if "pe_quantile" not in data:
        data["pe_quantile"] = "—"
    if "pb_quantile" not in data:
        data["pb_quantile"] = "—"
    filled = any(
        data.get(k) not in (None, "", "—")
        for k in ("pe", "pb", "pe_quantile", "pb_quantile")
    )
    src = data.get("_valuation_source") or "basic"
    return {
        "ticker": ti.full,
        "data": data,
        "source": f"{src} (mini_racer-safe)",
        "fallback": not filled,
    }


def main(ticker: str) -> dict:
    ti = parse_ticker(ticker)
    basic = ds.fetch_basic(ti)
    pe_history: list = []
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
            total_shares = total_shares or 1e9
            dcf_sensitivity = dcf_sensitivity_matrix(
                fcf_latest=net_profit_yuan * 0.8,
                waccs=[8, 9, 10, 11, 12],
                growths=[6, 8, 10, 12],
                current_price=current_price,
                shares_out=total_shares,
            )
    except Exception as e:
        dcf_result = {"error": str(e)[:80]}

    cur_pe = basic.get("pe_ttm")
    iv_total = dcf_result.get("intrinsic_value_total") if isinstance(dcf_result, dict) else None
    dcf_display = f"¥{iv_total / 1e8:.1f}亿" if iv_total else "—"

    data = {
        "pe": str(cur_pe) if cur_pe is not None else "—",
        "pb": str(basic.get("pb")) if basic.get("pb") is not None else "—",
        "pe_quantile": f"5 年 {pe_quantile_val:.0f} 分位" if pe_quantile_val is not None else "—",
        "pb_quantile": f"{pb_quantile_val:.0f}%" if pb_quantile_val is not None else "—",
        "industry_pe": str(industry_pe_avg) if industry_pe_avg else "—",
        "industry_pe_fallback_reason": industry_pe_fallback_reason,
        "dcf": dcf_display,
        "pe_history": pe_history,
        "dcf_simple": dcf_result,
        "dcf_sensitivity": dcf_sensitivity,
    }

    # baidu/cninfo SSL 常见失败 · 用 MX/basic 补 pe + 分位（coverage 硬字段）
    needs_mx = any(data.get(k) in (None, "", "—") for k in ("pe", "pe_quantile", "pb_quantile"))
    if needs_mx:
        mx_data = _fetch_valuation_via_mx(ti.code, getattr(ti, "raw", "") or basic.get("name") or "", basic)
        for k in ("pe", "pb", "pe_quantile", "pb_quantile"):
            if data.get(k) in (None, "", "—") and mx_data.get(k) not in (None, "", "—"):
                data[k] = mx_data[k]
        if mx_data.get("_valuation_source"):
            data["_valuation_source"] = mx_data["_valuation_source"]

    return {
        "ticker": ti.full,
        "data": data,
        "source": "baidu:valuation + cninfo:industry_pe_ratio + simple_dcf"
        + ("+mx_api" if "mx_api" in str(data.get("_valuation_source") or "") else ""),
        "fallback": False,
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"), ensure_ascii=False, indent=2, default=str))
