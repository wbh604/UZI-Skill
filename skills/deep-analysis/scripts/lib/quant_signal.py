"""量化基金 / 量化重仓信号检测 · v2.7

不维护具体基金白名单（基金名字未必含"量化"）。改用结构性特征：
**第一大持仓占净值 < 2% → 疑似量化基金**
理由：量化基金持 100-300 只股票分散持仓；主动价值/集中型基金第一大常 8-10%。

判定流程：
1. 对每只持有目标股票的基金（来自 `raw["fund_managers"]`）
2. 抓它的前 10 大持仓（akshare `fund_portfolio_hold_em`，24h cache）
3. 若 top-1 < 2% → 疑似量化
4. 若该量化基金的 top-10 含目标股票 → 计入 quant_holders
5. count >= QUANT_FACTOR_MIN_COUNT (3) → quant_factor style 触发

使用：
    from lib.quant_signal import detect_quant_signal
    sig = detect_quant_signal("600120.SH", raw["fund_managers"])
    if sig["is_quant_factor_style"]:
        # mark stock as quant_factor type
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .cache import cached, TTL_QUARTERLY

try:
    import akshare as ak  # type: ignore
except ImportError:
    ak = None


QUANT_TOP1_THRESHOLD = 2.0       # 第一大持仓占净值 < 2% → 疑似量化
QUANT_FACTOR_MIN_COUNT = 3       # 至少 3 家量化基金 top-10 持有 → 触发 style
HOLDINGS_QUARTER = "2025"        # akshare 接受年份；后期可按当前季度自动算


# ─── 私募量化备查名单 ──
# 私募不公开持仓，本模块无法直接抓取；agent 走 web search / LHB / 大股东交叉验证
KNOWN_PRIVATE_QUANTS: tuple[str, ...] = (
    "幻方", "九坤", "灵均", "鸣石", "因诺", "明汯", "玄信", "衍复", "宽德", "念空",
    "锐天", "九章", "信弘", "汐泰", "黑翼", "白鹭", "诚奇", "盛冠达", "千象",
)


def _fetch_top_holdings(fund_code: str, top_n: int = 10) -> list[dict]:
    """带 24h cache 的前 N 大持仓抓取。失败/空 → []。NEVER raises."""
    if not fund_code or ak is None:
        return []

    def _do() -> list[dict]:
        try:
            df = ak.fund_portfolio_hold_em(symbol=str(fund_code), date=HOLDINGS_QUARTER)
            if df is None or df.empty:
                return []
            return df.head(top_n).to_dict("records")
        except Exception:
            return []

    return cached(f"_quant/{fund_code}", "top10_holdings", _do, ttl=TTL_QUARTERLY)


def _is_quant_like(top_holdings: list[dict]) -> tuple[bool, float]:
    """结构性判定：top-1 占净值 < QUANT_TOP1_THRESHOLD → True
    返回 (is_quant_like, top1_pct)"""
    if not top_holdings:
        return False, 0.0
    try:
        top1_pct = float(top_holdings[0].get("占净值比例", 0))
    except (ValueError, TypeError):
        return False, 0.0
    return top1_pct < QUANT_TOP1_THRESHOLD, top1_pct


def _fetch_all_holding_funds(ticker_code: str, max_funds: int = 80) -> list[dict]:
    """直接调 fetch_fund_holders.fetch_holding_funds 拿全部持有本股的基金（不受
    run_real_test 默认 limit=6 限制）。

    raw["fund_managers"] 默认只有 6 个（按 5Y 收益率 top 6）；做量化信号判定需要
    更大样本（至少 50-80）才靠谱。
    """
    if ak is None:
        return []
    try:
        # Avoid circular import — fetch_fund_holders is in scripts/, lib/ is its peer
        import sys
        from pathlib import Path
        scripts_dir = Path(__file__).resolve().parent.parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from fetch_fund_holders import fetch_holding_funds
        all_funds = fetch_holding_funds(ticker_code)
        # Normalize: each entry must have at least 基金代码 + 基金名称
        out = []
        for h in all_funds[:max_funds]:
            code = str(h.get("基金代码") or h.get("fund_code") or "").strip()
            name = str(h.get("基金名称") or h.get("fund_name") or "").strip()
            if code:
                out.append({"fund_code": code, "fund_name": name})
        return out
    except Exception:
        return []


def detect_quant_signal(stock_code: str, fund_managers: list[dict] | None = None,
                        max_funds: int = 80) -> dict:
    """对所有持有本股的基金，识别量化属性 + 是否 top-10 持有。

    Args:
        stock_code: full ticker like "600120.SH" or "600120"
        fund_managers: list from raw["fund_managers"]; if empty/None, will auto-fetch
                       up to max_funds via fetch_holding_funds (不受 wave3 limit=6 制约)
        max_funds: cap on auto-fetched funds (only used when fund_managers is None/empty)

    Returns:
        {
            "count": 5,                       # quant funds with target in top-10
            "quant_funds": [                  # sorted by weight_pct desc
                {"name": "国金量化多因子A", "fund_code": "006195",
                 "rank": 4, "weight_pct": 2.3, "top1_pct": 1.8,
                 "manager": "马芳"},
                ...
            ],
            "active_funds_total": 50,         # how many funds checked
            "quant_funds_total": 12,          # how many were detected as quant-like
            "is_quant_factor_style": True,    # count >= MIN_COUNT
        }
    """
    code5 = (stock_code or "").split(".")[0].strip()

    # 样本太小时（如 wave3 默认 6 个）自动拉更大样本
    if not fund_managers or len(fund_managers) < 20:
        bigger = _fetch_all_holding_funds(code5, max_funds=max_funds)
        if bigger:
            fund_managers = bigger

    if not fund_managers:
        return {
            "count": 0, "quant_funds": [],
            "active_funds_total": 0, "quant_funds_total": 0,
            "is_quant_factor_style": False,
        }

    def _check_one(m: dict) -> dict | None:
        fund_code = m.get("fund_code")
        if not fund_code:
            return None
        top10 = _fetch_top_holdings(str(fund_code), top_n=10)
        is_q, top1_pct = _is_quant_like(top10)
        if not is_q:
            return None
        # ✓ 量化基金 — 检查目标股票是否在 top-10
        for rank, h in enumerate(top10, start=1):
            holding_code = str(h.get("股票代码", "")).strip()
            if holding_code == code5:
                try:
                    weight_pct = float(h.get("占净值比例", 0))
                except (ValueError, TypeError):
                    weight_pct = 0.0
                return {
                    "name": str(m.get("fund_name", "") or ""),
                    "fund_code": str(fund_code),
                    "rank": rank,
                    "weight_pct": weight_pct,
                    "top1_pct": top1_pct,
                    "manager": str(m.get("name", "") or ""),
                }
        # 量化但不持目标股票
        return {"_quant_no_hold": True}

    quant_holders: list[dict] = []
    quant_total = 0

    # workers 默认 1 — 防 mini_racer V8 isolate crash（Py3.13）；
    # akshare.fund_portfolio_hold_em 内部用 JS 解码，多线程不安全。
    import os as _os
    _w = max(1, int(_os.environ.get("UZI_QUANT_WORKERS", "1")))
    with ThreadPoolExecutor(max_workers=_w) as pool:
        for r in pool.map(_check_one, fund_managers):
            if r is None:
                continue
            quant_total += 1
            if r.get("_quant_no_hold"):
                continue
            quant_holders.append(r)

    quant_holders.sort(key=lambda x: -x.get("weight_pct", 0))

    return {
        "count": len(quant_holders),
        "quant_funds": quant_holders[:10],
        "active_funds_total": len(fund_managers),
        "quant_funds_total": quant_total,
        "is_quant_factor_style": len(quant_holders) >= QUANT_FACTOR_MIN_COUNT,
    }


if __name__ == "__main__":
    import json
    import sys

    code = sys.argv[1] if len(sys.argv) > 1 else "600120.SH"

    # Read existing raw_data cache for testing
    from pathlib import Path
    cache = Path(".cache") / code / "raw_data.json"
    if not cache.exists():
        print(f"No cached raw_data for {code}; run stage1 first.")
        sys.exit(1)

    raw = json.loads(cache.read_text(encoding="utf-8"))
    fund_managers = raw.get("fund_managers", [])
    print(f"Testing {code} · {len(fund_managers)} fund_managers from cache")

    sig = detect_quant_signal(code, fund_managers)
    print(json.dumps(sig, ensure_ascii=False, indent=2, default=str))
