"""Regression tests for v2.15.2 · issue #30 网络自检增强 (Clash + 分组诊断) + #36 gemini manifest."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
ROOT = SCRIPTS.parent.parent.parent


# ─── #36 · Gemini CLI ──────────────────────────────────────────

def test_gemini_extension_has_version():
    """Gemini CLI 需要 version 字段 · 没这个字段 install 会挂."""
    path = ROOT / "gemini-extension.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "version" in data, "gemini-extension.json 必须有 version 字段（否则 Gemini CLI 安装失败）"
    # 应该跟主 manifest 一致
    main_manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    # 至少同大版本
    assert data["version"].split(".")[0] == main_manifest["version"].split(".")[0]


def test_version_bump_config_includes_gemini():
    """version-bump.json 必须含 gemini-extension.json · 否则下次 bump 会遗漏."""
    config = json.loads((ROOT / ".version-bump.json").read_text(encoding="utf-8"))
    assert "gemini-extension.json" in config.get("files", [])
    assert "gemini-extension.json" in config.get("patterns", {})


# ─── #30 · 本地代理端口检测 ───────────────────────────────────

def test_detect_local_proxy_returns_expected_shape():
    from lib.network_preflight import _detect_local_proxy
    info = _detect_local_proxy()
    assert "has_local_proxy" in info
    assert "detected" in info
    assert "hint" in info
    assert isinstance(info["detected"], list)


def test_detect_local_proxy_with_mocked_clash_port():
    """mock Clash 7890 打开 + env 未设 · 应给出 export 建议."""
    from lib import network_preflight as np
    import socket

    def fake_create_connection(addr, timeout=0.3):
        host, port = addr
        if host == "127.0.0.1" and port == 7890:
            # fake 一个 socket
            class _FakeSocket:
                def close(self): pass
            return _FakeSocket()
        raise ConnectionRefusedError()

    with patch.object(socket, "create_connection", side_effect=fake_create_connection):
        # 清 env
        import os
        saved = {}
        for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
                  "https_proxy", "http_proxy", "all_proxy"):
            saved[k] = os.environ.pop(k, None)
        try:
            info = np._detect_local_proxy()
            assert info["has_local_proxy"] is True
            assert any(d["port"] == 7890 for d in info["detected"])
            assert "export HTTPS_PROXY" in info["hint"]
            assert "7890" in info["hint"]
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


# ─── #30 · 分组诊断 ──────────────────────────────────────────

def test_diagnose_source_all_broken_gives_3_groups():
    from lib.network_preflight import diagnose_source, NetworkProfile
    p = NetworkProfile(
        domestic_ok=False, overseas_ok=False, search_ok=False,
        domestic_count=0, overseas_count=0, search_count=0,
    )
    diags = diagnose_source(p)
    assert len(diags) == 3
    groups = {d["group"] for d in diags}
    assert groups == {"domestic", "overseas", "search"}
    # 每组必须有 affected_fetchers + fix
    for d in diags:
        assert d.get("affected_fetchers")
        assert d.get("fix")
        assert d.get("status")


def test_diagnose_source_all_ok_no_diagnostics():
    from lib.network_preflight import diagnose_source, NetworkProfile
    p = NetworkProfile(
        domestic_ok=True, overseas_ok=True, search_ok=True,
        domestic_count=3, overseas_count=3, search_count=3,
    )
    diags = diagnose_source(p)
    assert diags == [], "全通时不应有诊断"


def test_diagnose_partial_domestic_only_one_warning():
    from lib.network_preflight import diagnose_source, NetworkProfile
    p = NetworkProfile(
        domestic_ok=True, overseas_ok=False, search_ok=True,
        domestic_count=2, overseas_count=0, search_count=3,  # 1 个国内挂但不影响 ok
    )
    diags = diagnose_source(p)
    # 国内 2/3 但还算 ok · 只应看到 overseas 问题
    groups = {d["group"] for d in diags}
    assert "overseas" in groups
    assert "search" not in groups  # 搜索通


def test_network_profile_has_new_fields():
    """v2.15.2 · NetworkProfile 新增 local_proxy + diagnostics."""
    from lib.network_preflight import NetworkProfile
    p = NetworkProfile()
    assert hasattr(p, "local_proxy")
    assert hasattr(p, "diagnostics")


def test_run_preflight_populates_diagnostics(monkeypatch):
    """run_preflight 完成时 · diagnostics 应被填入."""
    from lib import network_preflight as np

    def fake_probe(domain, port=443, timeout=3.0):
        # 模拟全不通 · 会触发 3 组诊断
        return np.DomainCheck(domain=domain, group="", reachable=False,
                              latency_ms=0, error="blocked")

    with patch.object(np, "_probe", side_effect=fake_probe), \
         patch.object(np, "_detect_local_proxy",
                      return_value={"has_local_proxy": False, "detected": [], "hint": ""}):
        prof = np.run_preflight(verbose=False)

    assert prof.domestic_ok is False
    assert prof.overseas_ok is False
    assert prof.search_ok is False
    assert len(prof.diagnostics) == 3  # 全挂 · 3 组都有诊断
    assert prof.local_proxy == {"has_local_proxy": False, "detected": [], "hint": ""}


def test_run_preflight_writes_enhanced_cache(monkeypatch):
    """run_preflight 写的 cache 必须含 local_proxy + diagnostics."""
    from lib import network_preflight as np

    def fake_probe(domain, port=443, timeout=3.0):
        return np.DomainCheck(domain=domain, group="", reachable=True, latency_ms=5)

    with patch.object(np, "_probe", side_effect=fake_probe):
        prof = np.run_preflight(verbose=False)

    cache = SCRIPTS / ".cache" / "_global" / "network_profile.json"
    assert cache.exists()
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert "local_proxy" in data
    assert "diagnostics" in data
