"""网络预检 + NetworkProfile · v2.13.5.

v2.10.2 原版只测 5 个国内 TCP connect · 无法区分"国内通 + 境外不通"等常见大陆无代理场景.

v2.13.5 升级：
- 9 个目标分 3 组（国内 / 境外 / 搜索）
- 检测代理 env（HTTP_PROXY / HTTPS_PROXY / ALL_PROXY / NO_PROXY）
- 输出结构化 `NetworkProfile` 供 agent + DIM_STRATEGIES 自适应
- 写 `.cache/_global/network_profile.json` 让 agent 介入阶段可读

**使用**:
    from lib.network_preflight import get_network_profile
    prof = get_network_profile()  # 跑预检 · 返 NetworkProfile dataclass
    if prof.overseas_ok:
        url = "https://query1.finance.yahoo.com/..."  # 境外源 OK
    else:
        url = "https://xueqiu.com/..."  # 降级到国内
"""
from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path


@dataclass
class DomainCheck:
    domain: str
    group: str  # "domestic" | "overseas" | "search"
    reachable: bool
    latency_ms: int
    error: str = ""
    purpose: str = ""


# ───────────────────────────────────────────────────────────────
# 目标清单 · 3 组 × 3 域 = 9 目标
# ───────────────────────────────────────────────────────────────

_DOMESTIC_TARGETS = [
    ("push2.eastmoney.com", "东财 push2 · A 股行情主源"),
    ("www.cninfo.com.cn", "巨潮 cninfo · 公告/行业 PE"),
    ("stock.xueqiu.com", "雪球数据"),
]

_OVERSEAS_TARGETS = [
    ("query1.finance.yahoo.com", "Yahoo Finance · 美股数据"),
    ("api.coingecko.com", "CoinGecko · 加密市场流动性"),
    ("baike.baidu.com", "百度百科 · 公司词条（国内直连但海外代理可能反被拦）"),
]

_SEARCH_TARGETS = [
    ("duckduckgo.com", "DuckDuckGo · ddgs"),
    ("www.baidu.com", "百度搜索"),
    ("api.github.com", "GitHub API · 通用网络健康度"),
]

_ALL_TARGETS: list[tuple[str, str, str]] = (
    [(d, g, p) for (d, p) in _DOMESTIC_TARGETS for g in ["domestic"]]
    + [(d, g, p) for (d, p) in _OVERSEAS_TARGETS for g in ["overseas"]]
    + [(d, g, p) for (d, p) in _SEARCH_TARGETS for g in ["search"]]
)


# ───────────────────────────────────────────────────────────────
# NetworkProfile · 结构化输出
# ───────────────────────────────────────────────────────────────

@dataclass
class NetworkProfile:
    """v2.13.5 · 网络情况的结构化画像 · 供 agent 和 DIM_STRATEGIES 自适应."""
    domestic_ok: bool = False
    overseas_ok: bool = False
    search_ok: bool = False
    has_proxy: bool = False  # HTTP_PROXY / HTTPS_PROXY / ALL_PROXY 任一设置
    proxy_url: str = ""
    domestic_count: int = 0   # 通的数量（0-3）
    overseas_count: int = 0
    search_count: int = 0
    avg_latency_ms: int = 0
    recommendation: str = ""  # 给 agent 看的一句话建议
    severity: str = "ok"      # ok | warning | degraded | critical
    probed_at: float = 0.0    # unix timestamp
    checks: list = field(default_factory=list)  # List[dict] (asdict(DomainCheck))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "NetworkProfile":
        d = dict(d)
        d.pop("checks", None)  # 读回时不反序列化明细
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _probe(domain: str, port: int = 443, timeout: float = 3.0) -> DomainCheck:
    t0 = time.time()
    try:
        sock = socket.create_connection((domain, port), timeout=timeout)
        sock.close()
        return DomainCheck(
            domain=domain, group="", reachable=True,
            latency_ms=int((time.time() - t0) * 1000),
        )
    except socket.gaierror as e:
        return DomainCheck(domain=domain, group="", reachable=False,
                           latency_ms=int((time.time() - t0) * 1000),
                           error=f"DNS fail: {e}")
    except socket.timeout:
        return DomainCheck(domain=domain, group="", reachable=False,
                           latency_ms=int(timeout * 1000),
                           error=f"timeout > {timeout}s")
    except Exception as e:
        return DomainCheck(domain=domain, group="", reachable=False,
                           latency_ms=int((time.time() - t0) * 1000),
                           error=f"{type(e).__name__}: {str(e)[:80]}")


def _detect_proxy() -> tuple[bool, str]:
    """从 env 检测代理配置 · 返 (has_proxy, proxy_url)."""
    for var in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
                "https_proxy", "http_proxy", "all_proxy"):
        v = os.environ.get(var, "").strip()
        if v and v.lower() not in ("off", "no", "false"):
            return True, f"{var}={v}"
    return False, ""


def _build_recommendation(p: NetworkProfile) -> tuple[str, str]:
    """根据 profile 生成 agent-facing 建议文本 + severity."""
    # severity
    if p.domestic_count >= 2 and p.overseas_count >= 2 and p.search_count >= 2:
        sev = "ok"
    elif p.domestic_count >= 2 and p.search_count >= 1:
        sev = "warning"
    elif p.domestic_count >= 1:
        sev = "degraded"
    else:
        sev = "critical"

    # recommendation
    if p.domestic_ok and p.overseas_ok and p.search_ok:
        rec = "✓ 全网通畅 · Playwright 可抓境内+境外所有源"
    elif p.domestic_ok and not p.overseas_ok and p.search_ok:
        rec = (
            "✓ 国内网络正常 · ✗ 境外受限 · "
            "Playwright 只抓国内源（东财 F10 / cninfo / 雪球 public / 百度搜索）· "
            "跳过 Yahoo / CoinGecko / 英文 Wikipedia"
        )
    elif p.domestic_ok and not p.overseas_ok and not p.search_ok:
        rec = (
            "⚠ 国内通 · 搜索受限 · 境外不通 · "
            "Playwright 只抓国内无搜索依赖的源（东财 F10 / cninfo / 雪球 page）· "
            "跳 baidu/百度搜索/Yahoo/CoinGecko"
        )
    elif not p.domestic_ok and p.overseas_ok:
        rec = (
            "⚠ 境外 VPN 环境 · 国内源受限 · "
            "Playwright 可抓 Yahoo/CoinGecko · 但不抓东财 push2（国内限外 IP）· "
            "建议 akshare 配合用 xueqiu fallback"
        )
    elif p.domestic_count >= 1:
        rec = "⚠ 网络不稳 · 建议 --depth lite + 跳过 Playwright 省时间"
    else:
        rec = "🔴 网络严重不通 · 建议退出修网络 · lite 模式也会失败"

    return rec, sev


def run_preflight(verbose: bool = True, timeout: float = 3.0) -> NetworkProfile:
    """跑预检 · 返 NetworkProfile（不同于 v2.10.2 dict）· 自动写 cache.

    写入 `.cache/_global/network_profile.json` 供 agent/subagent 读。
    """
    has_proxy, proxy_url = _detect_proxy()

    results: list[DomainCheck] = []
    for domain, group, purpose in _ALL_TARGETS:
        r = _probe(domain, timeout=timeout)
        r.group = group
        r.purpose = purpose
        results.append(r)

    dom_ok = sum(1 for r in results if r.group == "domestic" and r.reachable)
    ovs_ok = sum(1 for r in results if r.group == "overseas" and r.reachable)
    sch_ok = sum(1 for r in results if r.group == "search" and r.reachable)

    avg_lat = 0
    reachable_latencies = [r.latency_ms for r in results if r.reachable]
    if reachable_latencies:
        avg_lat = int(sum(reachable_latencies) / len(reachable_latencies))

    prof = NetworkProfile(
        domestic_ok=dom_ok >= 2,        # 3 个有 2 个通算 ok
        overseas_ok=ovs_ok >= 2,
        search_ok=sch_ok >= 2,
        has_proxy=has_proxy,
        proxy_url=proxy_url,
        domestic_count=dom_ok,
        overseas_count=ovs_ok,
        search_count=sch_ok,
        avg_latency_ms=avg_lat,
        probed_at=time.time(),
        checks=[asdict(r) for r in results],
    )
    prof.recommendation, prof.severity = _build_recommendation(prof)

    if verbose:
        total = len(results)
        reachable_count = sum(1 for r in results if r.reachable)
        print(f"\n🌐 网络预检 ({reachable_count}/{total} 通 · 均延迟 {avg_lat}ms · "
              f"proxy={'yes' if has_proxy else 'no'})")
        groups = [("国内", "domestic"), ("境外", "overseas"), ("搜索", "search")]
        for label, g in groups:
            grp = [r for r in results if r.group == g]
            grp_ok = sum(1 for r in grp if r.reachable)
            print(f"  [{label} {grp_ok}/{len(grp)}]")
            for r in grp:
                mark = f"✓ {r.latency_ms:4d}ms" if r.reachable else f"✗ {r.error[:35]}"
                print(f"    {mark}  {r.domain:32} · {r.purpose}")
        print(f"\n  {prof.recommendation}\n")

    # 写 cache 供 agent 介入时读
    try:
        cache_dir = Path(__file__).resolve().parent.parent / ".cache" / "_global"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "network_profile.json").write_text(
            json.dumps(prof.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass  # 写失败不阻塞主流程

    return prof


def get_network_profile(max_age_sec: int = 300) -> NetworkProfile:
    """读 cache · 若过期（>5min）重跑预检.

    agent 介入时调用此函数快速拿 profile · 不重跑网络测试。
    """
    try:
        cache_dir = Path(__file__).resolve().parent.parent / ".cache" / "_global"
        cache_file = cache_dir / "network_profile.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            probed_at = data.get("probed_at", 0)
            if time.time() - probed_at < max_age_sec:
                return NetworkProfile.from_dict(data)
    except Exception:
        pass
    # 过期或不存在 · 重跑
    return run_preflight(verbose=False)


# v2.10.2 向后兼容 · 保留 run_preflight 返 dict 的调用者
def run_preflight_legacy_dict(verbose: bool = True, timeout: float = 3.0) -> dict:
    """兼容 v2.10.2 的 dict 返回格式."""
    prof = run_preflight(verbose=verbose, timeout=timeout)
    return {
        "reachable": prof.domestic_count + prof.overseas_count + prof.search_count,
        "failures": 9 - (prof.domestic_count + prof.overseas_count + prof.search_count),
        "critical_failures": 9 - (prof.domestic_count + prof.overseas_count + prof.search_count),
        "avg_latency_ms": prof.avg_latency_ms,
        "advisory": prof.recommendation,
        "severity": prof.severity,
        "results": prof.checks,
    }


if __name__ == "__main__":
    prof = run_preflight(verbose=True)
    print(f"\n[JSON summary]\n{json.dumps(prof.to_dict(), ensure_ascii=False, indent=2)[:800]}")
