"""本地浏览器探测 · 复用系统 Chrome/Edge，避免重复下载 Playwright Chromium.

设计目标：
- **跨平台**：Windows / macOS / Linux 都按各自约定路径探测
- **零副作用**：只读文件系统与 PATH，不安装、不下载、不改配置
- **可覆盖**：``UZI_BROWSER_PATH`` 环境变量优先级最高
- **可回退**：探测不到时返回 ``None``，调用方继续走 Playwright 自带 Chromium

为什么需要它：
``playwright install chromium`` 会额外下载约 150 MB 的浏览器，而多数开发机/办公机
已经装了 Chrome 或 Edge。复用系统浏览器可以省掉这次下载，也让无外网环境可用。

用法::

    from lib.browser_locator import find_local_browser

    exe = find_local_browser()          # str | None
    if exe:
        browser = p.chromium.launch(executable_path=exe)
    else:
        browser = p.chromium.launch()   # 回退到 Playwright 管理的 Chromium
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

__all__ = [
    "BROWSER_PATH_ENV",
    "find_local_browser",
    "find_local_browser_with_source",
    "browser_launch_kwargs",
]

#: 显式指定浏览器可执行文件的环境变量名
BROWSER_PATH_ENV = "UZI_BROWSER_PATH"

#: Chromium 内核浏览器名（按偏好排序：Chrome 优先，Edge 次之）
_CHROMIUM_NAMES = ("chrome", "google-chrome", "chromium", "chromium-browser", "msedge", "microsoft-edge")


def _windows_candidates() -> list[str]:
    """Windows 常见安装位置."""
    out: list[str] = []
    program_files = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]
    local_appdata = os.environ.get("LOCALAPPDATA")

    for base in program_files:
        if not base:
            continue
        out.append(str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"))
        out.append(str(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"))

    if local_appdata:
        out.append(str(Path(local_appdata) / "Google" / "Chrome" / "Application" / "chrome.exe"))
        out.append(str(Path(local_appdata) / "Microsoft" / "Edge" / "Application" / "msedge.exe"))
    return out


def _macos_candidates() -> list[str]:
    """macOS 应用包内的可执行文件."""
    out: list[str] = []
    for app in ("Google Chrome", "Microsoft Edge", "Chromium"):
        for root in ("/Applications", str(Path.home() / "Applications")):
            out.append(f"{root}/{app}.app/Contents/MacOS/{app.replace(' ', '')}")
    # Chromium 的包内名就是 Chromium
    out.append("/Applications/Chromium.app/Contents/MacOS/Chromium")
    return out


def _posix_path_candidates() -> list[str]:
    """Linux / 其它 POSIX：走 PATH 查找."""
    out: list[str] = []
    for name in _CHROMIUM_NAMES:
        found = shutil.which(name)
        if found:
            out.append(found)
    return out


def _known_candidates() -> list[str]:
    """按当前平台给出候选路径列表（未做存在性过滤）."""
    if sys.platform.startswith("win"):
        return _windows_candidates()
    if sys.platform == "darwin":
        return _macos_candidates() + _posix_path_candidates()
    return _posix_path_candidates()


def find_local_browser_with_source() -> tuple[str | None, str]:
    """探测本地浏览器，并返回来源标记（便于日志与测试断言）.

    Returns:
        (path, source) —— 探测失败时返回 ``(None, "none")``。
        source 取值：``env`` / ``known-path`` / ``path-lookup`` / ``none``
    """
    explicit = os.environ.get(BROWSER_PATH_ENV)
    if explicit:
        # 用户显式指定：尊重用户，即使文件不存在也返回，由 Playwright 报错更直观
        if Path(explicit).exists():
            return explicit, "env"
        return None, "none"

    for cand in _known_candidates():
        if cand and Path(cand).exists():
            return cand, "known-path"

    # Windows 也允许通过 PATH 兜底（例如 scoop / winget 安装到自定义目录）
    for name in _CHROMIUM_NAMES:
        found = shutil.which(name)
        if found:
            return found, "path-lookup"

    return None, "none"


def find_local_browser() -> str | None:
    """返回本地 Chrome/Edge/Chromium 可执行文件路径，找不到返回 ``None``."""
    return find_local_browser_with_source()[0]


def browser_launch_kwargs() -> dict[str, str]:
    """构造传给 ``p.chromium.launch`` / ``launch_persistent_context`` 的参数.

    探测不到本地浏览器时返回空 dict，让 Playwright 使用自带 Chromium，
    保持与旧版本完全一致的行为。
    """
    exe = find_local_browser()
    return {"executable_path": exe} if exe else {}
