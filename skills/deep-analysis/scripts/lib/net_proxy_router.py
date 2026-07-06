"""Proxy routing for mixed China/overseas data sources.

Python requests can pick up Windows system proxy settings even when
HTTP_PROXY/HTTPS_PROXY are not set. For UZI this is harmful: many domestic data
domains should bypass VPN, while DuckDuckGo/Yahoo/GitHub can use the local VPN.
"""
from __future__ import annotations

import os
import socket


LOCAL_PROXY_PORTS = (7897, 7890, 7891, 10809, 10808, 1080, 20170, 2080, 8080)
DOMESTIC_NO_PROXY = (
    "localhost",
    "127.0.0.1",
    "::1",
    "eastmoney.com",
    ".eastmoney.com",
    "cninfo.com.cn",
    ".cninfo.com.cn",
    "xueqiu.com",
    ".xueqiu.com",
    "10jqka.com.cn",
    ".10jqka.com.cn",
    "sina.com.cn",
    ".sina.com.cn",
    "sinaimg.cn",
    ".sinaimg.cn",
    "baidu.com",
    ".baidu.com",
    "jin10.com",
    ".jin10.com",
    "cs.com.cn",
    ".cs.com.cn",
    "stcn.com",
    ".stcn.com",
    "nbd.com.cn",
    ".nbd.com.cn",
    "sse.com.cn",
    ".sse.com.cn",
    "szse.cn",
    ".szse.cn",
)


def configure_proxy_routing() -> dict:
    """Configure env proxy routing once per process.

    Modes:
    - UZI_PROXY_MODE=off/direct: do nothing.
    - UZI_PROXY_MODE=proxy: require UZI_PROXY_URL or an existing/local proxy.
    - UZI_PROXY_MODE=auto/default: use existing env proxy, or detected local proxy.
    """
    mode = os.environ.get("UZI_PROXY_MODE", "auto").strip().lower() or "auto"
    if mode in {"off", "direct", "none", "0"}:
        return {
            "mode": "off",
            "proxy_url": "",
            "configured_proxy": False,
            "configured_no_proxy": False,
        }

    proxy_url = _configured_proxy_url() or os.environ.get("UZI_PROXY_URL", "").strip()
    if not proxy_url and mode in {"auto", "proxy", "on", "1"}:
        proxy_url = _detect_local_http_proxy()

    configured_proxy = False
    if proxy_url and not _configured_proxy_url():
        os.environ.setdefault("HTTP_PROXY", proxy_url)
        os.environ.setdefault("HTTPS_PROXY", proxy_url)
        configured_proxy = True

    configured_no_proxy = _merge_no_proxy(DOMESTIC_NO_PROXY)
    return {
        "mode": mode,
        "proxy_url": proxy_url or _configured_proxy_url(),
        "configured_proxy": configured_proxy,
        "configured_no_proxy": configured_no_proxy,
    }


def _configured_proxy_url() -> str:
    for key in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        value = os.environ.get(key, "").strip()
        if value and value.lower() not in {"off", "no", "false", "0"}:
            return value
    return ""


def _detect_local_http_proxy() -> str:
    for port in LOCAL_PROXY_PORTS:
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=0.2)
            sock.close()
            return f"http://127.0.0.1:{port}"
        except OSError:
            continue
    return ""


def _merge_no_proxy(entries: tuple[str, ...]) -> bool:
    existing = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    parts = [p.strip() for p in existing.split(",") if p.strip()]
    seen = {p.lower() for p in parts}
    changed = False
    for entry in entries:
        if entry.lower() not in seen:
            parts.append(entry)
            seen.add(entry.lower())
            changed = True
    value = ",".join(parts)
    if value:
        os.environ["NO_PROXY"] = value
        os.environ["no_proxy"] = value
    return changed
