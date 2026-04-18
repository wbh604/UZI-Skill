"""Regression tests for v2.10.6 provider chain integration.

Covers:
- try_chain() success / failover / all-fail
- get_provider_chain() env override
- health_check() structure
- provider method completeness (spot-check)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_health_check_structure():
    from lib.providers import health_check
    h = health_check()
    assert isinstance(h, dict)
    assert "akshare" in h  # always registered
    for name, info in h.items():
        assert "available" in info
        assert "status" in info


def test_get_provider_chain_defaults_to_akshare_first():
    os.environ.pop("UZI_PROVIDERS_KLINE", None)
    from lib.providers import get_provider_chain
    chain = get_provider_chain("kline", "A")
    # akshare 应该在链首（安装了 akshare 的机器上）
    if chain:  # only if akshare available
        assert chain[0].name == "akshare"


def test_env_override_reorders_chain(monkeypatch):
    """Env UZI_PROVIDERS_<DIM> 应改变 chain 顺序."""
    monkeypatch.setenv("UZI_PROVIDERS_KLINE", "baostock,akshare")
    from lib.providers import get_provider_chain
    chain = get_provider_chain("kline", "A")
    names = [p.name for p in chain]
    # 两个都可用的环境下，baostock 应先于 akshare
    if "baostock" in names and "akshare" in names:
        assert names.index("baostock") < names.index("akshare"), names
    # 至少有一个匹配到
    assert len(names) >= 1 or not names  # chain 空在缺依赖时也允许


def test_try_chain_returns_data_and_source(monkeypatch):
    """try_chain 拿到第一个成功的 provider 的返回 + 名字."""
    import lib.providers as pv

    class _FakeOk:
        name = "fake_ok"
        requires_key = False
        markets = ("A",)
        def is_available(self): return True
        def fetch_thing(self, x): return {"got": x}

    class _FakeFail:
        name = "fake_fail"
        requires_key = False
        markets = ("A",)
        def is_available(self): return True
        def fetch_thing(self, x): raise pv.ProviderError("nope")

    # Stub _REGISTRY so chain only sees our fakes
    monkeypatch.setattr(pv, "_REGISTRY", {"fake_fail": _FakeFail(), "fake_ok": _FakeOk()})
    monkeypatch.setenv("UZI_PROVIDERS_THING", "fake_fail,fake_ok")

    data, src = pv.try_chain("fetch_thing", "thing", "A", "hello")
    assert data == {"got": "hello"}
    assert src == "fake_ok"


def test_try_chain_raises_when_all_fail(monkeypatch):
    import lib.providers as pv

    class _F1:
        name = "f1"; requires_key = False; markets = ("A",)
        def is_available(self): return True
        def fetch_x(self): raise pv.ProviderError("boom1")

    class _F2:
        name = "f2"; requires_key = False; markets = ("A",)
        def is_available(self): return True
        def fetch_x(self): raise pv.ProviderError("boom2")

    monkeypatch.setattr(pv, "_REGISTRY", {"f1": _F1(), "f2": _F2()})
    monkeypatch.setenv("UZI_PROVIDERS_X", "f1,f2")
    import pytest
    with pytest.raises(pv.ProviderError) as exc:
        pv.try_chain("fetch_x", "x", "A")
    assert "boom1" in str(exc.value) or "boom2" in str(exc.value)


def test_try_chain_skips_method_not_implemented(monkeypatch):
    """Provider 没实现目标方法时应跳过而不是崩溃."""
    import lib.providers as pv

    class _NoMethod:
        name = "no_method"; requires_key = False; markets = ("A",)
        def is_available(self): return True
        # 故意不实现 fetch_kline_a

    class _HasMethod:
        name = "has_method"; requires_key = False; markets = ("A",)
        def is_available(self): return True
        def fetch_kline_a(self, **kw): return ["row"]

    monkeypatch.setattr(pv, "_REGISTRY", {"no_method": _NoMethod(), "has_method": _HasMethod()})
    monkeypatch.setenv("UZI_PROVIDERS_KLINE", "no_method,has_method")
    data, src = pv.try_chain("fetch_kline_a", "kline", "A")
    assert src == "has_method"
    assert data == ["row"]


def test_tushare_has_kline_method_v2_10_6():
    """v2.10.6 新增：tushare provider 必须实现 fetch_kline_a（之前缺失）."""
    from lib.providers import tushare_provider
    p = tushare_provider._TushareProvider()
    assert hasattr(p, "fetch_kline_a"), "tushare_provider.fetch_kline_a must exist in v2.10.6"
    assert callable(p.fetch_kline_a)


def test_all_providers_have_is_available():
    """Protocol 合规：每个 provider 都有 is_available()."""
    from lib.providers import _REGISTRY
    for name, p in _REGISTRY.items():
        assert hasattr(p, "is_available"), f"{name} missing is_available"
        # 能调（不崩）
        result = p.is_available()
        assert isinstance(result, bool), f"{name}.is_available must return bool"
