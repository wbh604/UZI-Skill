"""Dimension 1 · 财报 — 产出 viz 需要的完整 shape.

Output shape (matches report viz expectations):
{
  "roe": "18.7%", "net_margin": "...", "revenue_growth": "...", "fcf": "...",
  "roe_history":        [12.4, 14.1, 15.8, 16.2, 17.5, 18.7],   # 5Y+
  "revenue_history":    [21.5, 25.8, 28.6, 32.1, 38.4, 49.2],   # 亿
  "net_profit_history": [4.2,  5.1,  5.9,  6.8,  8.3,  10.5],   # 亿
  "financial_years":    ["2020", "2021", "2022", "2023", "2024", "25Q1"],
  "dividend_years":     ["2020", ...],
  "dividend_amounts":   [...],   # 元/10 股
  "dividend_yields":    [...],   # %
  "financial_health": {
      "current_ratio": 2.4,
      "debt_ratio":    28.5,
      "fcf_margin":   118.0,
      "roic":          22.3,
  }
}
"""
from __future__ import annotations

import json
import sys
import traceback

import akshare as ak  # type: ignore
from lib import data_sources as ds
from lib.market_router import parse_ticker


def _to_float(v) -> float:
    try:
        if v in (None, "", "--", "-"):
            return 0.0
        return float(str(v).replace(",", "").replace("%", ""))
    except (ValueError, TypeError):
        return 0.0


def _to_yi(v) -> float:
    """Convert raw (often 元) to 亿."""
    n = _to_float(v)
    return round(n / 1e8, 2)


def _fetch_a_share(ti) -> dict:
    out: dict = {}
    code = ti.code

    # ─── 1. 历年关键指标 (stock_financial_abstract_ths 或 stock_financial_abstract)
    try:
        df_abs = ak.stock_financial_abstract(symbol=code)
        if df_abs is not None and not df_abs.empty:
            # 该接口一列是 "指标", 后面几列是报告期
            period_cols = [c for c in df_abs.columns if c not in ("选项", "指标")]
            # 最近 6 个年报 (按季度倒序)
            period_cols_annual = [c for c in period_cols if str(c).endswith("1231")][:6]
            period_cols_annual = sorted(period_cols_annual)  # 旧 -> 新

            def _row(keyword: str) -> list:
                row = df_abs[df_abs["指标"].astype(str).str.contains(keyword, na=False, regex=False)]
                if row.empty:
                    return []
                return [_to_yi(row[c].iloc[0]) for c in period_cols_annual]

            out["revenue_history"] = _row("营业总收入")
            out["net_profit_history"] = _row("归属于母公司所有者的净利润") or _row("净利润")
            out["financial_years"] = [str(c)[:4] for c in period_cols_annual]
    except Exception as e:
        out["_abstract_error"] = str(e)

    # ─── 2. 加权 ROE 序列 (stock_financial_analysis_indicator)
    try:
        df_ind = ak.stock_financial_analysis_indicator(symbol=code, start_year="2018")
        if df_ind is not None and not df_ind.empty:
            date_col = "日期" if "日期" in df_ind.columns else df_ind.columns[0]
            df_ind = df_ind.sort_values(date_col)
            # filter to year-end rows (12-31)
            df_annual = df_ind[df_ind[date_col].astype(str).str.endswith("12-31")]
            if len(df_annual) < 3:  # fallback to all rows
                df_annual = df_ind

            for col_key, target in [
                ("加权净资产收益率(%)", "roe_history"),
                ("净资产收益率加权(%)", "roe_history"),
                ("ROE", "roe_history"),
            ]:
                if col_key in df_ind.columns:
                    out[target] = [_to_float(v) for v in df_annual[col_key].tail(6).tolist()]
                    break

            last = df_ind.iloc[-1]
            # Financial health
            health = {}
            for src_key, dst_key, unit_div in [
                ("流动比率", "current_ratio", 1),
                ("资产负债率(%)", "debt_ratio", 1),
                ("总资产净利率(%)", "roic", 1),
                ("销售净利率(%)", "net_margin_pct", 1),
            ]:
                if src_key in df_ind.columns:
                    v = _to_float(last.get(src_key))
                    if v:
                        health[dst_key] = v / unit_div
            if health:
                out["financial_health"] = health

            # Net margin / ROE 汇总 summary strings
            if "加权净资产收益率(%)" in df_ind.columns:
                out["roe"] = f"{_to_float(last['加权净资产收益率(%)']):.1f}%"
            if "销售净利率(%)" in df_ind.columns:
                out["net_margin"] = f"{_to_float(last['销售净利率(%)']):.1f}%"

            # v3.8.0 · DuPont 杜邦分解 · ROE = 净利率 × 总资产周转率 × 权益乘数
            # 价值派(巴菲特/张磊)看 ROE 的"质量来源"：margin 驱动=高质量 · 纯杠杆驱动=风险
            try:
                _dp_nm = _to_float(last.get("销售净利率(%)")) if "销售净利率(%)" in df_ind.columns else None
                _dp_to = _to_float(last.get("总资产周转率(次)")) if "总资产周转率(次)" in df_ind.columns else None
                _dp_dr = _to_float(last.get("资产负债率(%)")) if "资产负债率(%)" in df_ind.columns else None
                _dp_em = (100.0 / (100.0 - _dp_dr)) if (_dp_dr not in (None, 0) and _dp_dr < 100) else None
                if _dp_nm is not None and _dp_to is not None and _dp_em is not None:
                    _dp_roe = _dp_nm * _dp_to * _dp_em  # net_margin% × turnover × em → ROE%
                    # 质量判定：净利率贡献占比 = 看 ROE 多大程度靠"赚钱能力"而非"借钱放大"
                    _margin_lever_ratio = _dp_nm / (_dp_em * 10) if _dp_em else 0  # 经验比例
                    out["dupont"] = {
                        "net_margin_pct": round(_dp_nm, 2),
                        "asset_turnover": round(_dp_to, 3),
                        "equity_multiplier": round(_dp_em, 2),
                        "roe_reconstructed_pct": round(_dp_roe, 2),
                        # 质量标签：权益乘数 >2.5(高杠杆) 且净利率偏低 → leverage-driven(风险)
                        "roe_quality": (
                            "leverage_driven" if (_dp_em >= 2.5 and _dp_nm < 10)
                            else "margin_driven" if _dp_nm >= 15
                            else "balanced"
                        ),
                    }
            except Exception:
                pass
    except Exception as e:
        out["_indicator_error"] = str(e)

    # ─── 3. 营收增速 summary
    try:
        rh = out.get("revenue_history") or []
        if len(rh) >= 2 and rh[-2]:
            growth = (rh[-1] - rh[-2]) / rh[-2] * 100
            out["revenue_growth"] = f"{growth:+.1f}%"
    except Exception:
        pass

    # ─── 4. 现金流 (FCF 占净利比)
    try:
        df_cf = ak.stock_cash_flow_sheet_by_report_em(symbol=f"{'SZ' if ti.full.endswith('SZ') else 'SH'}{code}")
        if df_cf is not None and not df_cf.empty:
            # 最近一期 经营性现金流
            if "经营活动产生的现金流量净额" in df_cf.columns:
                ocf = _to_float(df_cf["经营活动产生的现金流量净额"].iloc[0])
                out["fcf"] = f"{ocf / 1e8:.1f}亿"
                # ocf/np
                np_latest = (out.get("net_profit_history") or [0])[-1]
                if np_latest:
                    out.setdefault("financial_health", {})["fcf_margin"] = round(ocf / 1e8 / np_latest * 100, 1)
    except Exception:
        pass

    # ─── 5. 分红历史
    try:
        df_div = ak.stock_history_dividend_detail(symbol=code, indicator="分红")
        if df_div is not None and not df_div.empty:
            # 取近 5 年，按年份聚合（同一年可能多次分红）
            from collections import defaultdict
            by_year: dict[str, float] = defaultdict(float)
            for _, row in df_div.head(30).iterrows():
                date_str = str(row.get("公告日期", row.get("除权除息日", "")))
                year = date_str[:4] if date_str and len(date_str) >= 4 else ""
                amount = _to_float(row.get("派息", row.get("现金分红-派息(税前)(元/10股)", 0)))
                if year and amount:
                    by_year[year] += amount
            if by_year:
                years_sorted = sorted(by_year.keys())[-5:]
                out["dividend_years"] = years_sorted
                out["dividend_amounts"] = [round(by_year[y], 2) for y in years_sorted]
                # dividend yield ~ 自算，暂取占比近似，真实算法需要当年年末价格
                out["dividend_yields"] = [round(by_year[y] / 20, 2) for y in years_sorted]  # 非常粗略，生产环境应该用年末价
    except Exception as e:
        out["_dividend_error"] = str(e)

    # v3.4.2 · BaoStock 兜底（Schannel TLS / 网络受限场景）
    # 当 akshare 链路全挂时（roe/net_margin/revenue_history 都空）· 用 baostock 季报数据补齐.
    # 触发条件：核心字段缺失 + baostock 可用.
    needs_fallback = (
        not out.get("roe") and not out.get("revenue_history") and not out.get("net_margin")
    )
    if needs_fallback:
        try:
            import baostock as _bs
            from datetime import datetime as _dt
            lg = _bs.login()
            if lg.error_code == "0":
                bs_code = ("sh." if code.startswith(("60", "68", "5", "9")) else "sz.") + code
                cur_year = _dt.now().year
                rows = []
                for y in range(cur_year - 5, cur_year + 1):
                    for q in (1, 2, 3, 4):
                        rs = _bs.query_profit_data(code=bs_code, year=y, quarter=q)
                        while rs.error_code == "0" and rs.next():
                            rows.append(rs.get_row_data())
                _bs.logout()
                if rows:
                    fields = ["code", "pubDate", "statDate", "roeAvg", "npMargin",
                              "gpMargin", "netProfit", "epsTTM", "MBRevenue", "totalShare"]
                    # 按报告期排序 · 拿最新
                    rec = [dict(zip(fields, r)) for r in rows]
                    rec.sort(key=lambda r: r.get("statDate", ""))
                    # ROE 历史（年报 · 季报每年取最后一个）
                    annual = {}
                    for r in rec:
                        sd = r.get("statDate", "")
                        if sd.endswith("-12-31"):
                            try:
                                annual[sd[:4]] = round(float(r["roeAvg"]) * 100, 2)
                            except (TypeError, ValueError):
                                pass
                    if annual:
                        out["roe_history"] = [annual[y] for y in sorted(annual.keys())[-6:]]
                    # 营收历史（同样取年报 · MBRevenue 转亿）
                    rev_annual = {}
                    for r in rec:
                        sd = r.get("statDate", "")
                        if sd.endswith("-12-31"):
                            try:
                                rev_annual[sd[:4]] = round(float(r["MBRevenue"]) / 1e8, 2)
                            except (TypeError, ValueError):
                                pass
                    if rev_annual:
                        out["revenue_history"] = [rev_annual[y] for y in sorted(rev_annual.keys())[-6:]]
                    # 最新一期 · 综合 ROE / 净利率 / 毛利率
                    last = rec[-1]
                    if last.get("roeAvg") and not out.get("roe"):
                        try:
                            out["roe"] = f"{float(last['roeAvg']) * 100:.1f}%"
                        except (TypeError, ValueError):
                            pass
                    if last.get("npMargin") and not out.get("net_margin"):
                        try:
                            out["net_margin"] = f"{float(last['npMargin']) * 100:.1f}%"
                        except (TypeError, ValueError):
                            pass
                    if last.get("gpMargin") and not out.get("gross_margin"):
                        try:
                            out["gross_margin"] = f"{float(last['gpMargin']) * 100:.1f}%"
                        except (TypeError, ValueError):
                            pass
                    # 营收增长（最近 2 年）
                    rh = out.get("revenue_history") or []
                    if len(rh) >= 2 and rh[-2] and not out.get("revenue_growth"):
                        growth = (rh[-1] - rh[-2]) / rh[-2] * 100
                        out["revenue_growth"] = f"{growth:+.1f}%"
                    out["_baostock_fallback"] = "fetch_financials 通过 baostock 补齐 · Schannel TLS 受限场景"
        except Exception as _e:
            out["_baostock_err"] = f"{type(_e).__name__}: {str(_e)[:80]}"

    return out


def _fetch_hk(ti) -> dict:
    """v2.7.2 · 港股财报 — 之前 HK 分支直接返回 {}，导致 1_financials 完全空。

    数据源: akshare.stock_financial_hk_analysis_indicator_em
      返回 9 年年度指标，含 ROE_AVG / ROE_YEARLY / ROIC_YEARLY / DEBT_ASSET_RATIO
      / CURRENT_RATIO / GROSS_PROFIT_RATIO / OPERATE_INCOME / HOLDER_PROFIT /
      OPERATE_INCOME_YOY / HOLDER_PROFIT_YOY / NET_PROFIT_RATIO / BASIC_EPS
      / PER_NETCASH_OPERATE.
    """
    code5 = ti.code.zfill(5)
    out: dict = {}
    try:
        df = ak.stock_financial_hk_analysis_indicator_em(symbol=code5, indicator="年度")
        if df is None or df.empty:
            return {}
        # 按年份升序，取最近 6 年
        df = df.sort_values("REPORT_DATE").tail(6).reset_index(drop=True)

        years = [str(d)[:4] for d in df["REPORT_DATE"].tolist()]
        out["financial_years"] = years

        def _col(name, div=1.0, ndigits=2):
            if name not in df.columns:
                return []
            vals = []
            for v in df[name].tolist():
                try:
                    vals.append(round(float(v) / div, ndigits))
                except (TypeError, ValueError):
                    vals.append(None)
            return vals

        # OPERATE_INCOME 和 HOLDER_PROFIT 以 元 为单位，折算亿
        out["revenue_history"] = _col("OPERATE_INCOME", div=1e8, ndigits=2)
        out["net_profit_history"] = _col("HOLDER_PROFIT", div=1e8, ndigits=2)
        out["roe_history"] = _col("ROE_AVG", ndigits=2)
        out["gross_margin_history"] = _col("GROSS_PROFIT_RATIO", ndigits=2)
        out["net_margin_history"] = _col("NET_PROFIT_RATIO", ndigits=2)

        last = df.iloc[-1].to_dict()

        def _last_pct(key, default="—"):
            v = last.get(key)
            try:
                return f"{float(v):.1f}%"
            except (TypeError, ValueError):
                return default

        out["roe"] = _last_pct("ROE_AVG")
        out["roic"] = _last_pct("ROIC_YEARLY")
        out["net_margin"] = _last_pct("NET_PROFIT_RATIO")
        out["gross_margin"] = _last_pct("GROSS_PROFIT_RATIO")

        # 营收增速（最后一年 YoY）
        try:
            out["revenue_growth"] = f"{float(last.get('OPERATE_INCOME_YOY', 0)):.1f}%"
        except (TypeError, ValueError):
            out["revenue_growth"] = "—"
        try:
            out["profit_growth"] = f"{float(last.get('HOLDER_PROFIT_YOY', 0)):.1f}%"
        except (TypeError, ValueError):
            out["profit_growth"] = "—"

        # financial_health 子结构与 A 股保持一致
        try:
            out["financial_health"] = {
                "debt_ratio": round(float(last.get("DEBT_ASSET_RATIO") or 0), 1),
                "current_ratio": round(float(last.get("CURRENT_RATIO") or 0), 2),
                "roic": round(float(last.get("ROIC_YEARLY") or 0), 2),
                "fcf_margin": None,  # HK 年报未直接给 FCF margin
            }
        except Exception:
            pass

        # EPS / BPS
        try:
            out["eps"] = round(float(last.get("BASIC_EPS") or 0), 3)
        except Exception:
            pass
        try:
            out["bps"] = round(float(last.get("BPS") or 0), 2)
        except Exception:
            pass

        out["currency"] = str(last.get("CURRENCY") or "HKD")
    except Exception as e:
        out["_hk_indicator_error"] = f"{type(e).__name__}: {e}"

    # 港股派息（派息记录需要另一个 API；akshare 覆盖有限，暂不强制）
    return out


def _fetch_us(ti) -> dict:
    try:
        import yfinance as yf
    except ImportError:
        return {}
    try:
        t = yf.Ticker(ti.code)
        fin = t.financials  # 最近 4 年
        bs = t.balance_sheet
        cf = t.cashflow
        info = t.info or {}
        out: dict = {}
        if fin is not None and not fin.empty:
            rev_row = next((r for r in ["Total Revenue", "TotalRevenue"] if r in fin.index), None)
            np_row = next((r for r in ["Net Income", "NetIncome", "Net Income Common Stockholders"] if r in fin.index), None)
            if rev_row:
                out["revenue_history"] = [round(float(v) / 1e8, 2) for v in fin.loc[rev_row].tolist()[::-1]]
            if np_row:
                out["net_profit_history"] = [round(float(v) / 1e8, 2) for v in fin.loc[np_row].tolist()[::-1]]
            out["financial_years"] = [str(c)[:4] for c in fin.columns[::-1]]
        out["roe"] = f"{info.get('returnOnEquity', 0) * 100:.1f}%" if info.get("returnOnEquity") else "—"
        out["net_margin"] = f"{info.get('profitMargins', 0) * 100:.1f}%" if info.get("profitMargins") else "—"
        return out
    except Exception:
        return {}


def main(ticker: str) -> dict:
    ti = parse_ticker(ticker)
    try:
        if ti.market == "A":
            data = _fetch_a_share(ti)
        elif ti.market == "U":
            data = _fetch_us(ti)
        elif ti.market == "H":
            data = _fetch_hk(ti)
        else:
            data = {}
        error = None
    except Exception as e:
        data = {}
        error = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)

    return {
        "ticker": ti.full,
        "data": data,
        "source": "akshare:stock_financial_abstract + indicator + cash_flow + dividend_detail",
        "fallback": not bool(data),
        "error": error,
    }


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"
    print(json.dumps(main(arg), ensure_ascii=False, indent=2, default=str))
