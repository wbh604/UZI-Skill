"""全局网络超时护栏 · v2.10.2.

**问题**: akshare 内部大量 `requests.get()` 不带 timeout，走代理/GFW 不通时
会卡到 TCP 默认 120s。单次看着还好，20 个 fetcher 叠加就是卡死。

**修法**: module import 时 monkey-patch `requests.Session.request` / 顶层
`requests.get/post`，注入默认 timeout。用户已显式设 timeout 的调用不受影响。

**使用**:
    # 在 run_real_test.py / 任何入口的最早期 import:
    from lib.net_timeout_guard import install_default_timeout
    install_default_timeout()

    # 或直接 import 这个 module 会自动装（侧效应）
    import lib.net_timeout_guard  # noqa

**环境变量**:
    UZI_HTTP_TIMEOUT  · 默认 20（秒）· 单次 HTTP 最长耗时
"""
from __future__ import annotations

import os


_INSTALLED = False


def install_default_timeout() -> None:
    """Monkey-patch requests 库，给所有不带 timeout 的调用注入默认超时."""
    global _INSTALLED
    if _INSTALLED:
        return

    try:
        from lib.net_proxy_router import configure_proxy_routing
        configure_proxy_routing()
    except Exception:
        pass

    try:
        import requests
        from requests.sessions import Session
    except ImportError:
        return

    default_timeout = int(os.environ.get("UZI_HTTP_TIMEOUT", "20"))

    _original_request = Session.request

    def _patched_request(self, method, url, **kwargs):
        # 只在调用方没显式传 timeout 时注入
        if "timeout" not in kwargs or kwargs.get("timeout") is None:
            kwargs["timeout"] = default_timeout
        return _original_request(self, method, url, **kwargs)

    Session.request = _patched_request

    # 顶层 requests.get/post/... 也走相同逻辑（它们底层都是 Session）
    _INSTALLED = True


# Module-import 时自动装（简化集成）
install_default_timeout()
