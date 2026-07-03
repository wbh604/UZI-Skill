"""Local cache enrichment for UZI raw data.

The project-level ``data/cache`` directory already contains daily A-share
history and financial snapshots. This module imports those snapshots into UZI's
``raw_data.json`` shape when network fetchers leave holes.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from lib.market_router import parse_ticker


KNOWN_A_SHARE_IDENTITY: dict[str, dict[str, str]] = {
    "300750": {"name": "宁德时代", "industry": "电池"},
    "300502": {"name": "新易盛", "industry": "光模块"},
    "300394": {"name": "天孚通信", "industry": "光模块"},
    "300308": {"name": "中际旭创", "industry": "光模块"},
    "601138": {"name": "工业富联", "industry": "AI服务器/算力硬件"},
    "002415": {"name": "海康威视", "industry": "安防设备/AIoT"},
    "600406": {"name": "国电南瑞", "industry": "电网自动化"},
    "300124": {"name": "汇川技术", "industry": "工业自动化"},
    "300274": {"name": "阳光电源", "industry": "光伏逆变器/储能"},
    "600285": {"name": "羚锐制药", "industry": "中药"},
    "600988": {"name": "赤峰黄金", "industry": "黄金"},
    "600989": {"name": "宝丰能源", "industry": "煤化工"},
}

_MOJIBAKE_MARKERS = (
    "瀹", "鐢", "鏃", "鍏", "睜", "绠", "涓", "鍧", "浜", "鈥", "�",
)


def enrich_raw_data_from_local_cache(raw: dict, cache_root: str | Path | None = None) -> dict:
    """Patch UZI raw data with trusted local snapshots.

    Existing valid fields win. Local snapshots are used for missing values and
    visibly broken mojibake strings.
    """
    if not isinstance(raw, dict):
        return raw

    ticker = raw.get("full") or raw.get("ticker") or raw.get("code") or ""
    try:
        ti = parse_ticker(str(ticker))
    except Exception:
        return raw

    changes: list[str] = []
    _apply_known_identity(raw, ti.code, changes)

    if ti.market != "A":
        _record_changes(raw, changes, None)
        return raw

    root = Path(cache_root) if cache_root else _find_workspace_cache_root()
    symbol = _a_share_symbol(ti.code, ti.full)

    history = _latest_payload(root, "history", symbol)
    financial = _latest_payload(root, "financial", symbol)

    if history:
        _merge_history(raw, history, changes)
    if financial:
        _merge_financial(raw, financial, changes)

    _record_changes(raw, changes, root)
    return raw


def repair_mojibake_text(value: Any) -> Any:
    """Repair common UTF-8-as-GBK mojibake in short Chinese strings."""
    if not isinstance(value, str) or not _looks_bad_text(value):
        return value
    try:
        repaired = value.encode("gbk", errors="strict").decode("utf-8", errors="strict")
    except Exception:
        repaired = value
    if repaired != value and _looks_better(value, repaired):
        return repaired
    if "浜" in value:
        return value.replace("浜?", "亿").replace("浜", "亿")
    return value


def _apply_known_identity(raw: dict, code: str, changes: list[str]) -> None:
    identity = KNOWN_A_SHARE_IDENTITY.get(code)
    if not identity:
        return
    basic = _dim_data(raw, "0_basic")
    for key in ("name", "industry"):
        if _set_if_missing_or_bad(basic, key, identity[key]):
            changes.append(f"0_basic.{key}:known_identity")


def _merge_history(raw: dict, payload: dict, changes: list[str]) -> None:
    basic = _dim_data(raw, "0_basic")
    kline = _dim_data(raw, "2_kline")
    valuation = _dim_data(raw, "10_valuation")

    price = _num(payload.get("最新价"))
    pe = _num(payload.get("市盈率-动态"))
    pb = _num(payload.get("市净率"))
    market_cap_raw = _num(payload.get("总市值"))
    change_pct = _num(payload.get("涨跌幅"))
    turnover_rate = _num(payload.get("换手率"))

    if _set_if_missing_or_bad(basic, "price", price):
        changes.append("0_basic.price:history")
    if _set_if_missing_or_bad(basic, "change_pct", change_pct):
        changes.append("0_basic.change_pct:history")
    if _set_if_missing_or_bad(basic, "turnover_rate", turnover_rate):
        changes.append("0_basic.turnover_rate:history")
    if _set_if_missing_or_bad(basic, "pe_ttm", _round(pe, 2)):
        changes.append("0_basic.pe_ttm:history")
    if _set_if_missing_or_bad(basic, "pb", _round(pb, 2)):
        changes.append("0_basic.pb:history")
    if market_cap_raw and _set_if_missing_or_bad(basic, "market_cap_raw", market_cap_raw):
        changes.append("0_basic.market_cap_raw:history")
    if market_cap_raw:
        market_cap_yi = market_cap_raw / 1e8
        if _set_if_missing_or_bad(basic, "market_cap_yi", _round(market_cap_yi, 2)):
            changes.append("0_basic.market_cap_yi:history")
        if _set_if_missing_or_bad(basic, "market_cap", f"{market_cap_yi:.2f}亿"):
            changes.append("0_basic.market_cap:history")

    if _set_if_missing_or_bad(valuation, "pe", _round(pe, 2)):
        changes.append("10_valuation.pe:history")
    if _set_if_missing_or_bad(valuation, "pb", _round(pb, 2)):
        changes.append("10_valuation.pb:history")

    position = _num(payload.get("position_250"))
    close_vs_ma60 = _num(payload.get("close_vs_ma60"))
    close_vs_ma200 = _num(payload.get("close_vs_ma200"))
    ret20 = _num(payload.get("return_20d"))
    ret60 = _num(payload.get("return_60d"))
    drawdown = _num(payload.get("drawdown_250"))

    stats = kline.setdefault("kline_stats", {})
    if isinstance(stats, dict):
        if _set_if_missing_or_bad(stats, "position_250", _round(position, 4)):
            changes.append("2_kline.kline_stats.position_250:history")
        if _set_if_missing_or_bad(stats, "return_20d", _format_pct(ret20)):
            changes.append("2_kline.kline_stats.return_20d:history")
        if _set_if_missing_or_bad(stats, "return_60d", _format_pct(ret60)):
            changes.append("2_kline.kline_stats.return_60d:history")
        if _set_if_missing_or_bad(stats, "max_drawdown", _format_pct(drawdown)):
            changes.append("2_kline.kline_stats.max_drawdown:history")

    for key, value in (
        ("position_250", _round(position, 4)),
        ("close_vs_ma60", _round(close_vs_ma60, 4)),
        ("close_vs_ma200", _round(close_vs_ma200, 4)),
    ):
        if _set_if_missing_or_bad(kline, key, value):
            changes.append(f"2_kline.{key}:history")


def _merge_financial(raw: dict, payload: dict, changes: list[str]) -> None:
    fin = _dim_data(raw, "1_financials")

    for key in ("roe", "gross_margin", "net_margin", "profit_growth", "revenue_growth",
                "deduct_profit_growth", "cash_profit_ratio"):
        value = _round(_num(payload.get(key)), 4)
        if _set_if_missing_or_bad(fin, key, value):
            changes.append(f"1_financials.{key}:financial")

    health = fin.setdefault("financial_health", {})
    if isinstance(health, dict):
        debt = _round(_num(payload.get("debt_ratio")), 4)
        if _set_if_missing_or_bad(health, "debt_ratio", debt):
            changes.append("1_financials.financial_health.debt_ratio:financial")
        cash_profit = _round(_num(payload.get("cash_profit_ratio")), 4)
        if _set_if_missing_or_bad(health, "cash_profit_ratio", cash_profit):
            changes.append("1_financials.financial_health.cash_profit_ratio:financial")

    if _set_if_missing_or_bad(fin, "_data_period", payload.get("_data_period")):
        changes.append("1_financials._data_period:financial")


def _dim_data(raw: dict, dim_key: str) -> dict:
    dims = raw.setdefault("dimensions", {})
    dim = dims.setdefault(dim_key, {"data": {}, "source": "local_data_repair", "fallback": False})
    if not isinstance(dim, dict):
        dim = {"data": {}, "source": "local_data_repair", "fallback": False}
        dims[dim_key] = dim
    data = dim.setdefault("data", {})
    if not isinstance(data, dict):
        data = {}
        dim["data"] = data
    return data


def _set_if_missing_or_bad(target: dict, key: str, value: Any) -> bool:
    if value in (None, "", "-", "—"):
        return False
    current = target.get(key)
    if _is_missing(current) or _looks_bad_text(current):
        target[key] = value
        return True
    repaired = repair_mojibake_text(current)
    if repaired != current:
        target[key] = repaired
        return True
    return False


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == "-" or value == "—"


def _looks_bad_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return any(marker in value for marker in _MOJIBAKE_MARKERS)


def _looks_better(old: str, new: str) -> bool:
    old_bad = sum(old.count(marker) for marker in _MOJIBAKE_MARKERS)
    new_bad = sum(new.count(marker) for marker in _MOJIBAKE_MARKERS)
    return new and new_bad < old_bad


def _latest_payload(root: Path | None, category: str, symbol: str) -> dict | None:
    if root is None or not root.exists():
        return None
    candidates = list(root.glob(f"{category}*{symbol}_*.json"))
    best_payload = None
    best_ts = -1.0
    for path in candidates:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            ts = float(obj.get("_cached_at") or path.stat().st_mtime)
            if ts > best_ts and isinstance(obj.get("payload"), dict):
                best_ts = ts
                best_payload = obj["payload"]
        except Exception:
            continue
    return best_payload


def _find_workspace_cache_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        cache = parent / "data" / "cache"
        if cache.exists():
            return cache
    return None


def _a_share_symbol(code: str, full: str) -> str:
    suffix = "sh" if full.upper().endswith(".SH") or code.startswith(("60", "68", "90")) else "sz"
    if full.upper().endswith(".BJ"):
        suffix = "bj"
    return f"{suffix}.{code}"


def _num(value: Any) -> float | None:
    if value in (None, "", "-", "—"):
        return None
    try:
        out = float(str(value).replace(",", "").replace("%", "").replace("+", ""))
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _round(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None


def _format_pct(value: float | None) -> str | None:
    return f"{value:+.1f}%" if value is not None else None


def _record_changes(raw: dict, changes: list[str], root: Path | None) -> None:
    if not changes:
        return
    raw["_local_data_repair"] = {
        "applied": True,
        "cache_root": str(root) if root else None,
        "changes": sorted(set(changes)),
    }
