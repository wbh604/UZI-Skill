"""Data Provider Framework · v2.10.3.

统一接入多个数据源做 **自动 failover**。目的：

  · 主源 akshare 挂了不至于整个 fetcher 返空
  · 用户有 Tushare/FMP 等可选 key 时自动启用更稳定源
  · 下游 fetcher 不关心具体从哪拉，只要拿到数据

## 架构

```
fetcher (e.g. fetch_financials)
    ↓
get_provider_chain("financials", market="A")   ← 按偏好+可用性排序的 providers
    ↓
for p in chain:
    try:
        return p.fetch_financials(ti)
    except ProviderError:
        continue
```

## 内置 providers（v2.10.3）

  · akshare    (主 · 0 key · 默认)
  · efinance   (冗余 · 0 key · 需 pip install efinance)
  · tushare    (opt-in · 需 TUSHARE_TOKEN)
  · baostock   (低层 · 0 key · 已装)

## 环境变量

  TUSHARE_TOKEN     · Tushare Pro token
  UZI_PROVIDERS_<DIM>  · 单维度覆盖偏好，如 UZI_PROVIDERS_FINANCIALS=tushare,akshare
"""
from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable


class ProviderError(Exception):
    """统一错误类型，让 fetch chain 能优雅 failover."""


@runtime_checkable
class Provider(Protocol):
    """所有 provider 必须实现的协议."""
    name: str
    requires_key: bool
    markets: tuple[str, ...]  # ("A",) / ("A", "H") / ("U",)

    def is_available(self) -> bool:
        """能否用（环境变量/依赖/网络都检查）."""
        ...


# ═══════════════════════════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════════════════════════

_REGISTRY: dict[str, Provider] = {}


def register(provider: Provider) -> None:
    """Provider 类模块内自动调用注册."""
    _REGISTRY[provider.name] = provider


def get(name: str) -> Provider | None:
    return _REGISTRY.get(name)


def list_providers(market: str | None = None, available_only: bool = False) -> list[Provider]:
    """列出 provider · 可按 market 过滤 · 可只返回当前可用的."""
    out = list(_REGISTRY.values())
    if market:
        out = [p for p in out if market in p.markets]
    if available_only:
        out = [p for p in out if p.is_available()]
    return out


def get_provider_chain(dim: str, market: str = "A") -> list[Provider]:
    """返回一个给定维度+市场的 provider 优先级链.

    优先级 = UZI_PROVIDERS_<DIM> env （逗号分隔 id）> 内置默认顺序
    默认顺序：akshare → efinance → tushare → baostock
    """
    default_order = ["akshare", "efinance", "tushare", "baostock"]
    env_key = f"UZI_PROVIDERS_{dim.upper()}"
    env_val = os.environ.get(env_key)
    if env_val:
        order = [x.strip() for x in env_val.split(",") if x.strip()]
    else:
        order = default_order

    chain: list[Provider] = []
    for name in order:
        p = _REGISTRY.get(name)
        if p and market in p.markets and p.is_available():
            chain.append(p)
    return chain


def try_chain(
    method: str,
    dim: str,
    market: str = "A",
    *args,
    **kwargs,
) -> tuple[Any, str]:
    """按 provider 优先级链依次调用 `method`，返回 (data, provider_name).

    v2.10.6 · 让 fetcher 一行调用就能享受多源 failover：

        from lib.providers import try_chain
        try:
            rows, src = try_chain("fetch_kline_a", dim="kline", market="A", code="600519")
            print(f"拿到 {len(rows)} 根 K 线，来源 {src}")
        except ProviderError:
            # 所有 provider 都失败，再走老的硬编码链

    Args:
      method: provider 上的方法名（如 "fetch_financials_a"）
      dim:    维度关键字，用于读 UZI_PROVIDERS_<DIM> env 覆盖顺序
      market: "A" / "H" / "U"
      *args, **kwargs: 转发给 provider.method(...)

    Raises:
      ProviderError: 所有可用 provider 都失败（附最后一个错误）
    """
    chain = get_provider_chain(dim, market)
    if not chain:
        raise ProviderError(f"[{dim}/{market}] 无可用 provider（检查 TUSHARE_TOKEN / pip install）")
    errors: list[str] = []
    for p in chain:
        fn = getattr(p, method, None)
        if fn is None:
            errors.append(f"{p.name}: 未实现 {method}")
            continue
        try:
            data = fn(*args, **kwargs)
            return data, p.name
        except ProviderError as e:
            errors.append(f"{p.name}: {e}")
            continue
        except Exception as e:
            # provider 实现里漏抛 ProviderError 的兜底
            errors.append(f"{p.name}: {type(e).__name__}: {e}")
            continue
    raise ProviderError(
        f"[{dim}/{market}] 所有 provider 都失败: " + " | ".join(errors[:3])
    )


def health_check() -> dict[str, dict]:
    """返回每个 provider 的健康度 + 诊断信息."""
    out = {}
    for name, p in _REGISTRY.items():
        try:
            avail = p.is_available()
            out[name] = {
                "available": avail,
                "markets": list(p.markets),
                "requires_key": p.requires_key,
                "status": "ok" if avail else "unavailable",
            }
        except Exception as e:
            out[name] = {"available": False, "status": f"error: {type(e).__name__}"}
    return out


# Auto-register built-in providers on import
def _auto_register():
    """import 时自动装所有内置 providers（失败的静默跳过）."""
    try:
        from . import akshare_provider  # noqa
    except Exception:
        pass
    try:
        from . import efinance_provider  # noqa
    except Exception:
        pass
    try:
        from . import tushare_provider  # noqa
    except Exception:
        pass
    try:
        from . import baostock_provider  # noqa
    except Exception:
        pass
    try:
        from . import direct_http_provider  # noqa
    except Exception:
        pass


_auto_register()
