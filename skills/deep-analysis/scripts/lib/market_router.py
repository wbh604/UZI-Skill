"""Identify market (A / H / U) from a ticker or stock name and normalize the code.

v2.9.2 · 扩展 `_a_share_suffix` 覆盖 ETF / LOF / 可转债 等非个股 6 位码
        + 增加 `classify_security_type` 识别标的类型（stock/etf/lof/cb）
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Market = Literal["A", "H", "U"]
SecurityType = Literal["stock", "etf", "lof", "convertible_bond", "mutual_fund", "index", "unknown"]


@dataclass
class TickerInfo:
    raw: str            # original user input
    code: str           # numeric/letter code without exchange suffix
    full: str           # canonical: 002273.SZ / 00700.HK / AAPL
    market: Market      # A / H / U


_RE_A_NUMERIC = re.compile(r"^\d{6}$")
_RE_A_FULL = re.compile(r"^(\d{6})\.(SZ|SH|BJ)$", re.I)
_RE_HK = re.compile(r"^(\d{4,5})(?:\.HK)?$", re.I)
_RE_US = re.compile(r"^[A-Z][A-Z\.\-]{0,5}$")
_RE_CSINDEX = re.compile(r"^H\d{5}$")


# ═══════════════════════════════════════════════════════════════
# v2.9.2 · 完整的 6 位码分类（之前只看前 2 位，漏了一大片）
# ═══════════════════════════════════════════════════════════════
# 沪市 (SH)：
#   600xxx / 601xxx / 603xxx / 605xxx · 主板股票
#   688xxx · 科创板股票
#   900xxx · B 股
#   50xxxx / 51xxxx / 52xxxx / 56xxxx / 58xxxx · ETF
#   501xxx / 502xxx / 506xxx · LOF（部分重叠 ETF 范围，逻辑上同属 SH 基金）
#   10xxxx / 11xxxx · 可转债
#
# 深市 (SZ)：
#   000xxx / 001xxx / 002xxx / 003xxx · 主板 / 中小板股票
#   300xxx · 创业板股票
#   159xxx · ETF
#   160xxx / 161xxx / 162xxx / 163xxx / 164xxx / 165xxx / 166xxx / 167xxx / 168xxx · LOF
#   12xxxx / 127xxx / 128xxx · 可转债
#
# 北交所 (BJ)：
#   83xxxx / 87xxxx / 88xxxx / 92xxxx

_SH_PREFIXES_2 = ("60", "68", "90")       # 688 涉及在 _SH_3 里单独覆盖
_SH_STOCK_PREFIXES_3 = ("688",)
_SH_B_SHARE = ("900",)
_SH_FUND_PREFIXES_2 = ("50", "51", "52", "56", "58")
_SH_BOND_PREFIXES_2 = ("10", "11")

_SZ_STOCK_PREFIXES_3 = ("000", "001", "002", "003", "300", "301")
_SZ_FUND_PREFIXES_3 = ("159",)
_SZ_LOF_PREFIXES_2 = ("16",)  # 160xxx-168xxx
_SZ_BOND_PREFIXES_2 = ("12",)

_BJ_PREFIXES_2 = ("83", "87", "88", "92")


def _a_share_suffix(code6: str) -> str:
    """Decide SZ/SH/BJ for a 6-digit A-share code.

    v2.9.2 修复：之前只看前 2 位 (60/688/900 → SH, 其他 → SZ)，导致：
      - 512400 (SH ETF) 被错判 SZ
      - 10xxxx / 11xxxx (SH 可转债) 被错判 SZ
      - 159xxx (SZ ETF) 虽然默认 SZ 对了但巧合
    现在按完整规则走，任何 6 位码都能归对交易所。
    """
    # 北交所
    if code6.startswith(_BJ_PREFIXES_2):
        return "BJ"
    # 沪市（按优先级：股票 → ETF/LOF/可转债）
    if code6.startswith(_SH_STOCK_PREFIXES_3):    # 688xxx 科创板
        return "SH"
    if code6.startswith(_SH_B_SHARE):              # 900xxx B 股
        return "SH"
    if code6.startswith(("60",)):                  # 600/601/603/605/606...
        return "SH"
    if code6.startswith(_SH_FUND_PREFIXES_2):      # 50/51/52/56/58 · SH ETF/LOF
        return "SH"
    if code6.startswith(_SH_BOND_PREFIXES_2):      # 10/11 · SH 可转债
        return "SH"
    # 深市（包含其他所有剩余 6 位码）
    return "SZ"


def classify_security_type(code6: str) -> SecurityType:
    """v2.9.2 新增：识别标的类型（stock / etf / lof / convertible_bond / mutual_fund）.

    v3.4.3 · 修复开放式基金误判：
    - 110011 易方达优质（开放式基金）以前被判为 convertible_bond → early-exit 用户无法分析
    - 现在通过 akshare.fund_name_em 二次校验 · 基金代码优先识别为 mutual_fund
    - mutual_fund 走 fund_holdings_runner 跟 ETF/LOF 一样循环分析持仓

    用于 fetch_basic 早期分流：
    - stock → 走 22 维 + 51 评委
    - etf / lof / mutual_fund → 走 fund_holdings_runner (循环持仓)
    - convertible_bond → early-exit（不适合）
    """
    # 中证指数代码（例如 H30269）不是 A 股股票代码，但历史上会被
    # parse_ticker 的最后兜底分支误当成 A 股。单独识别后由指数数据源处理。
    if _RE_CSINDEX.fullmatch(str(code6).upper()):
        return "index"
    if not code6 or not code6.isdigit() or len(code6) != 6:
        return "unknown"
    # ETF (SH 50/51/52/56/58, SZ 159)
    if code6.startswith(_SZ_FUND_PREFIXES_3) or \
       code6.startswith(_SH_FUND_PREFIXES_2):
        if code6.startswith(("501", "502", "506")):
            return "lof"
        return "etf"
    # SZ LOF (160xxx-168xxx)
    if code6.startswith(_SZ_LOF_PREFIXES_2):
        return "lof"

    # v3.4.3 · 在判 convertible_bond 之前先查是否为开放式基金
    # 110xxx / 12xxx 等码段同时是老转债 + 开放式基金 · 用 fund_name_em 二次确认
    if code6.startswith(_SH_BOND_PREFIXES_2) or \
       code6.startswith(_SZ_BOND_PREFIXES_2):
        if _is_mutual_fund_code(code6):
            return "mutual_fund"
        return "convertible_bond"

    # v3.4.3 · 其他不符合 stock 前缀的码段 · 也查一下是否开放式基金
    # 005827 易方达蓝筹精选 · 005xxx 不是股票前缀但是基金
    if not (code6.startswith(_SH_STOCK_PREFIXES_3) or
            code6.startswith(_SH_B_SHARE) or
            code6.startswith(("60",)) or
            code6.startswith(_SZ_STOCK_PREFIXES_3) or
            code6.startswith(_BJ_PREFIXES_2)):
        if _is_mutual_fund_code(code6):
            return "mutual_fund"

    # 股票
    if code6.startswith(_SH_STOCK_PREFIXES_3) or \
       code6.startswith(_SH_B_SHARE) or \
       code6.startswith(("60",)) or \
       code6.startswith(_SZ_STOCK_PREFIXES_3) or \
       code6.startswith(_BJ_PREFIXES_2):
        return "stock"
    return "unknown"


_MUTUAL_FUND_CODE_CACHE: set[str] | None = None


def _is_mutual_fund_code(code6: str) -> bool:
    """v3.4.3 · 用 akshare.fund_name_em 校验 6 位码是否开放式基金.

    懒加载 + 缓存：第一次调时下载全市场基金清单（~5000 条）· 后续 O(1) 查表.
    任何 akshare 异常都返 False · 不影响主流程.
    """
    global _MUTUAL_FUND_CODE_CACHE
    if _MUTUAL_FUND_CODE_CACHE is None:
        try:
            import akshare as ak  # type: ignore
            df = ak.fund_name_em()
            if df is None or df.empty:
                _MUTUAL_FUND_CODE_CACHE = set()
            else:
                # akshare fund_name_em 列：基金代码 / 基金简称 / 基金类型
                code_col = next((c for c in df.columns if "代码" in str(c)), df.columns[0])
                _MUTUAL_FUND_CODE_CACHE = {
                    str(x).zfill(6) for x in df[code_col].dropna().tolist()
                }
        except Exception:
            _MUTUAL_FUND_CODE_CACHE = set()
    return code6 in _MUTUAL_FUND_CODE_CACHE


def parse_ticker(raw: str) -> TickerInfo:
    """Best-effort parse. For Chinese names (e.g. '水晶光电'), caller must resolve via fetch_basic first."""
    s = raw.strip().upper().replace(" ", "")

    # 中证指数使用 H + 5 位数字编码（如 H30269）。保留 market=A 以兼容
    # 现有数据管道的 A/H/U 三市场 schema，security_type=index 负责分流。
    if _RE_CSINDEX.fullmatch(s):
        return TickerInfo(raw=raw, code=s, full=s, market="A")

    m = _RE_A_FULL.match(s)
    if m:
        return TickerInfo(raw=raw, code=m.group(1), full=f"{m.group(1)}.{m.group(2).upper()}", market="A")

    if _RE_A_NUMERIC.match(s):
        suffix = _a_share_suffix(s)
        return TickerInfo(raw=raw, code=s, full=f"{s}.{suffix}", market="A")

    if s.endswith(".HK"):
        code = s.removesuffix(".HK").lstrip("0") or "0"
        return TickerInfo(raw=raw, code=code, full=f"{code.zfill(5)}.HK", market="H")

    # v2.10.2 · 3-位数纯数字（如 "700"/"981"）A 股不存在，走 HK
    # 原逻辑：_RE_A_NUMERIC 要求 6 位，_RE_HK 匹配 4-5 位 → "700" 3 位都不匹配
    # 落到最后 A 股兜底 → 错判为 A 股 code=700
    if s.isdigit() and 3 <= len(s) <= 5:
        padded = s.zfill(5)
        return TickerInfo(raw=raw, code=s.lstrip("0") or "0", full=f"{padded}.HK", market="H")

    if _RE_HK.match(s) and not _RE_US.match(s):
        return TickerInfo(raw=raw, code=s.lstrip("0") or "0", full=f"{s.zfill(5)}.HK", market="H")

    if _RE_US.match(s):
        return TickerInfo(raw=raw, code=s, full=s, market="U")

    # Unrecognized — likely a Chinese name. Caller must resolve.
    return TickerInfo(raw=raw, code=raw, full=raw, market="A")


def is_chinese_name(raw: str) -> bool:
    """True if input contains CJK chars (needs name→code resolution)."""
    return any("\u4e00" <= ch <= "\u9fff" for ch in raw)


if __name__ == "__main__":
    for t in ["002273", "002273.SZ", "600519", "00700.HK", "00700", "AAPL", "BRK.B", "水晶光电"]:
        print(t, "->", parse_ticker(t))
