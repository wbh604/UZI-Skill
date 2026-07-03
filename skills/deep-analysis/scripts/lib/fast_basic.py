"""Fast best-effort basic info for fetchers that must not block on quote chains."""
from __future__ import annotations

import json
import os
import queue
import threading
from pathlib import Path
from typing import Any

from lib import data_sources as ds


KNOWN_A_SHARE_IDENTITY: dict[str, dict[str, str]] = {
    "600036": {"name": "招商银行", "industry": "银行"},
    "601398": {"name": "工商银行", "industry": "银行"},
    "601939": {"name": "建设银行", "industry": "银行"},
    "601288": {"name": "农业银行", "industry": "银行"},
    "601328": {"name": "交通银行", "industry": "银行"},
    "601166": {"name": "兴业银行", "industry": "银行"},
    "600016": {"name": "民生银行", "industry": "银行"},
    "600000": {"name": "浦发银行", "industry": "银行"},
    "601818": {"name": "光大银行", "industry": "银行"},
    "601998": {"name": "中信银行", "industry": "银行"},
    "600919": {"name": "江苏银行", "industry": "银行"},
    "601009": {"name": "南京银行", "industry": "银行"},
    "601229": {"name": "上海银行", "industry": "银行"},
    "600926": {"name": "杭州银行", "industry": "银行"},
    "300308": {"name": "中际旭创", "industry": "光模块"},
    "300502": {"name": "新易盛", "industry": "光模块"},
    "300394": {"name": "天孚通信", "industry": "光模块"},
    "688498": {"name": "源杰科技", "industry": "光模块"},
    "300548": {"name": "博创科技", "industry": "光模块"},
    "603083": {"name": "剑桥科技", "industry": "光模块"},
    "300750": {"name": "宁德时代", "industry": "电池"},
    "002812": {"name": "恩捷股份", "industry": "电池"},
    "300014": {"name": "亿纬锂能", "industry": "电池"},
    "002709": {"name": "天赐材料", "industry": "电池"},
    "002460": {"name": "赣锋锂业", "industry": "电池"},
    "002466": {"name": "天齐锂业", "industry": "电池"},
}


def fetch_basic_fast(ti, timeout: float | None = None) -> dict:
    """Call data_sources.fetch_basic with a hard daemon-thread timeout.

    Some wrappers only need name/industry/PE/PB. If the full basic chain stalls,
    return local identity and cache-derived valuation fields instead of blocking
    the dimension fetcher.
    """
    if timeout is None:
        timeout = float(os.environ.get("UZI_BASIC_FETCH_TIMEOUT", "6"))

    q: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

    def _worker() -> None:
        try:
            q.put(("ok", ds.fetch_basic(ti)))
        except Exception as e:
            q.put(("err", e))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(max(0.001, timeout))
    if not thread.is_alive():
        try:
            status, payload = q.get_nowait()
        except queue.Empty:
            return _local_basic(ti, "empty_result")
        if status == "ok" and isinstance(payload, dict):
            return payload
        return _local_basic(ti, f"error:{type(payload).__name__}")

    return _local_basic(ti, f"timeout:{timeout:g}s")


def _local_basic(ti, reason: str) -> dict:
    out: dict[str, Any] = {"code": ti.full, "_basic_fast_fallback": reason}
    if ti.market == "A":
        out.update(KNOWN_A_SHARE_IDENTITY.get(ti.code, {}))
        if not out.get("industry"):
            try:
                industry = ds._known_stock_industry(ti.code)  # type: ignore[attr-defined]
            except Exception:
                industry = None
            if industry:
                out["industry"] = industry
        _merge_history_snapshot(out, ti)
    if not out.get("name"):
        out["name"] = ti.code
    return out


def _merge_history_snapshot(out: dict, ti) -> None:
    payload = _latest_history_payload(ti)
    if not payload:
        return
    for key, value in payload.items():
        label = str(key)
        if out.get("price") is None and ("最新" in label or "鏈€鏂" in label):
            out["price"] = _num(value)
        elif out.get("pe_ttm") is None and ("市盈" in label or "甯傜泩" in label or label.upper() == "PE"):
            out["pe_ttm"] = _num(value)
        elif out.get("pb") is None and ("市净" in label or "甯傚噣" in label or label.upper() == "PB"):
            out["pb"] = _num(value)
        elif out.get("market_cap_raw") is None and ("总市" in label or "鎬诲競" in label):
            out["market_cap_raw"] = _num(value)
    if out.get("market_cap_raw") and not out.get("market_cap"):
        out["market_cap"] = f"{out['market_cap_raw'] / 1e8:.2f}亿"


def _latest_history_payload(ti) -> dict | None:
    root = _cache_root()
    if root is None:
        return None
    symbol = _a_share_symbol(ti)
    candidates = list(root.glob(f"history*{symbol}_*.json"))
    best = None
    best_ts = -1.0
    for path in candidates:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            ts = float(obj.get("_cached_at") or path.stat().st_mtime)
            payload = obj.get("payload")
            if ts > best_ts and isinstance(payload, dict):
                best_ts = ts
                best = payload
        except Exception:
            continue
    return best


def _cache_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        cache = parent / "data" / "cache"
        if cache.exists():
            return cache
    return None


def _a_share_symbol(ti) -> str:
    suffix = "sh" if ti.full.upper().endswith(".SH") or ti.code.startswith(("60", "68", "90")) else "sz"
    if ti.full.upper().endswith(".BJ"):
        suffix = "bj"
    return f"{suffix}.{ti.code}"


def _num(value: Any) -> float | None:
    if value in (None, "", "-", "—"):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").replace("+", ""))
    except (TypeError, ValueError):
        return None
