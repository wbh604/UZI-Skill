"""Regression tests for lib/browser_locator · 跨平台本地浏览器探测.

全部 mock 文件系统与 PATH，零真实浏览器依赖，可在 CI 的
Windows / macOS / Linux 三种 runner 上稳定通过。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from lib import browser_locator as bl  # noqa: E402


# ─── 环境变量优先 ────────────────────────────────────────────────

def test_env_var_wins_when_path_exists(monkeypatch, tmp_path):
    """UZI_BROWSER_PATH 指向真实存在的文件时，优先采用它."""
    fake = tmp_path / "my-chrome"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setenv(bl.BROWSER_PATH_ENV, str(fake))
    path, source = bl.find_local_browser_with_source()
    assert path == str(fake)
    assert source == "env"


def test_env_var_ignored_when_path_missing(monkeypatch):
    """显式指定但文件不存在 → 返回 None（不静默猜测别的浏览器）."""
    monkeypatch.setenv(bl.BROWSER_PATH_ENV, r"C:\definitely\not\here\chrome.exe")
    path, source = bl.find_local_browser_with_source()
    assert path is None
    assert source == "none"


def test_env_var_absent_does_not_raise(monkeypatch):
    monkeypatch.delenv(bl.BROWSER_PATH_ENV, raising=False)
    # 不崩溃即可（结果取决于跑测试的机器上是否装了浏览器）
    assert bl.find_local_browser() is None or isinstance(bl.find_local_browser(), str)


# ─── 平台候选路径 ────────────────────────────────────────────────

def test_windows_candidates_cover_chrome_and_edge(monkeypatch):
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    monkeypatch.setenv("ProgramFiles(x86)", r"C:\Program Files (x86)")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\tester\AppData\Local")
    cands = bl._windows_candidates()
    joined = " ".join(cands).lower()
    assert "chrome.exe" in joined
    assert "msedge.exe" in joined
    # 必须覆盖 Program Files 与 LOCALAPPDATA 两种安装位置
    assert any("program files" in c.lower() for c in cands)
    assert any("localappdata" in c.lower() or "appdata\\local" in c.lower() for c in cands)


def test_macos_candidates_include_app_bundle_paths():
    cands = bl._macos_candidates()
    joined = " ".join(cands)
    assert "Google Chrome.app/Contents/MacOS" in joined
    assert "Microsoft Edge.app/Contents/MacOS" in joined


def test_known_candidates_dispatch_by_platform(monkeypatch):
    monkeypatch.setattr(bl.sys, "platform", "win32")
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    win = bl._known_candidates()
    assert any("chrome.exe" in c.lower() for c in win)

    monkeypatch.setattr(bl.sys, "platform", "darwin")
    mac = bl._known_candidates()
    assert any(".app/Contents/MacOS" in c for c in mac)

    monkeypatch.setattr(bl.sys, "platform", "linux")
    with patch.object(bl.shutil, "which", return_value="/usr/bin/google-chrome"):
        linux = bl._known_candidates()
    assert "/usr/bin/google-chrome" in linux


# ─── 探测链：known-path → PATH 查找 → none ──────────────────────

def test_known_path_hit_reports_source(monkeypatch):
    monkeypatch.delenv(bl.BROWSER_PATH_ENV, raising=False)
    monkeypatch.setattr(bl, "_known_candidates", lambda: [r"C:\Program Files\Google\Chrome\Application\chrome.exe"])
    monkeypatch.setattr(bl.Path, "exists", lambda self: str(self).endswith("chrome.exe"))
    path, source = bl.find_local_browser_with_source()
    assert path is not None and path.endswith("chrome.exe")
    assert source == "known-path"


def test_path_lookup_used_as_fallback(monkeypatch):
    """Windows 常见路径都没命中时，仍允许通过 PATH 找到（scoop/winget 等）."""
    monkeypatch.delenv(bl.BROWSER_PATH_ENV, raising=False)
    monkeypatch.setattr(bl, "_known_candidates", lambda: [])
    monkeypatch.setattr(bl.shutil, "which", lambda name: "/opt/chrome" if name == "chrome" else None)
    path, source = bl.find_local_browser_with_source()
    assert path == "/opt/chrome"
    assert source == "path-lookup"


def test_returns_none_when_nothing_found(monkeypatch):
    monkeypatch.delenv(bl.BROWSER_PATH_ENV, raising=False)
    monkeypatch.setattr(bl, "_known_candidates", lambda: [])
    monkeypatch.setattr(bl.shutil, "which", lambda name: None)
    assert bl.find_local_browser() is None
    assert bl.find_local_browser_with_source() == (None, "none")


# ─── launch kwargs 契约 ─────────────────────────────────────────

def test_launch_kwargs_empty_when_no_browser(monkeypatch):
    """探测不到时必须返回空 dict → 调用方回退 Playwright 自带 Chromium."""
    monkeypatch.setattr(bl, "find_local_browser", lambda: None)
    assert bl.browser_launch_kwargs() == {}


def test_launch_kwargs_passes_executable_path(monkeypatch):
    monkeypatch.setattr(bl, "find_local_browser", lambda: "/usr/bin/google-chrome")
    assert bl.browser_launch_kwargs() == {"executable_path": "/usr/bin/google-chrome"}


def test_launch_kwargs_is_safe_to_splat(monkeypatch):
    """空 dict 展开不应破坏原有参数（`launch(headless=True, **{})` 等价旧行为）."""
    monkeypatch.setattr(bl, "find_local_browser", lambda: None)
    kwargs = bl.browser_launch_kwargs()
    merged = {"headless": True, **kwargs}
    assert merged == {"headless": True}


# ─── 与 playwright_fallback 的集成契约 ──────────────────────────

def test_playwright_fallback_uses_locator(monkeypatch):
    """playwright_fallback 必须复用 browser_locator，而非自己再写一份探测."""
    import lib.playwright_fallback as pf  # noqa: F401

    assert hasattr(pf, "find_local_browser")
    assert hasattr(pf, "browser_launch_kwargs")
    assert pf.find_local_browser is bl.find_local_browser


def test_xueqiu_browser_uses_locator():
    import lib.xueqiu_browser as xb  # noqa: F401

    assert hasattr(xb, "browser_launch_kwargs")


def test_render_share_card_uses_locator():
    """分享卡脚本必须走同一探测入口（源文件级别校验，避免 import 触发 playwright）."""
    src = (SCRIPTS / "render_share_card.py").read_text(encoding="utf-8")
    assert "browser_launch_kwargs" in src
    assert "p.chromium.launch(**browser_launch_kwargs())" in src
