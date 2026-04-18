"""Provider health CLI · v2.10.6.

用法：
    python -m lib.providers            # 所有 provider 健康度
    python -m lib.providers chain A    # 看 A 股某维度的优先级链
"""
from __future__ import annotations

import os
import sys

from . import health_check, get_provider_chain, list_providers


def _banner(title: str) -> None:
    print("\n" + "─" * 60)
    print(f"  {title}")
    print("─" * 60)


def cmd_health() -> None:
    _banner("Provider 健康度 (v2.10.6)")
    h = health_check()
    print(f"\n  {'name':12s} {'avail':8s} {'key req':8s} {'markets':10s}  status")
    print(f"  {'-'*12:12s} {'-'*8:8s} {'-'*8:8s} {'-'*10:10s}  {'-'*30}")
    for name, info in sorted(h.items()):
        mk = ",".join(info.get("markets", []))
        req = "yes" if info.get("requires_key") else "no"
        avail = "✓" if info.get("available") else "✗"
        status = info.get("status", "?")
        print(f"  {name:12s} {avail:8s} {req:8s} {mk:10s}  {status}")

    # 指南
    _banner("启用建议")
    if not any(h[n].get("available") for n in ("tushare",)):
        print("  · Tushare (A 股最稳官方源) 未启用：")
        print("    1. https://tushare.pro 注册 → 复制 token")
        print("    2. export TUSHARE_TOKEN=<your>")
    if not h.get("efinance", {}).get("available"):
        print("  · efinance 未装：pip install efinance  (0 key · A/H/U 都覆盖)")
    if not h.get("baostock", {}).get("available"):
        print("  · baostock 未装：pip install baostock  (0 key · A 股深度历史)")
    if not h.get("direct_http", {}).get("available"):
        print("  · direct_http 不可用（requests 缺失）")


def cmd_chain(args: list[str]) -> None:
    market = args[1] if len(args) > 1 else "A"
    dims = args[2:] if len(args) > 2 else ["kline", "financials", "basic", "lhb"]
    _banner(f"Provider 优先级链 · market={market}")
    for d in dims:
        chain = get_provider_chain(d, market)
        env_override = os.environ.get(f"UZI_PROVIDERS_{d.upper()}")
        hint = f"  [UZI_PROVIDERS_{d.upper()}={env_override}]" if env_override else ""
        names = " → ".join(p.name for p in chain) if chain else "(无可用 provider)"
        print(f"  {d:14s} {names}{hint}")


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("health", "-h"):
        cmd_health()
        return 0
    if argv[0] == "chain":
        cmd_chain(argv)
        return 0
    print(f"未知子命令: {argv[0]}")
    print("用法: python -m lib.providers [health|chain [market] [dim...]]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
