"""Regression for v3.6.1 · Hermes 安装脚本（绕过 Skills Guard）.

背景：Hermes Skills Guard 扫描器假阳性 168 条 · DANGEROUS · --force 也绕不过.
解法：提供 install-hermes.sh · clone + symlink · 跳过 Hub 扫描.

测试覆盖：
1. install-hermes.sh 存在 + 可执行
2. 脚本 bash 语法合法
3. 脚本含 set -euo pipefail 安全 flag
4. 脚本含 4 个 skill 名 (deep-analysis / investor-panel / lhb-analyzer / trap-detector)
5. 脚本含 fallback · 不假设 venv pip 永远存在
6. README + INSTALL-HERMES.md 已指向新脚本
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "install-hermes.sh"

# install-hermes.sh 是 POSIX shell 脚本 · 其「可执行位」和「bash 语法」只在
# Linux/macOS 上有意义 · Windows 文件系统没有 S_IXUSR · 且 WSL bash 常损坏。
# 这两个检查在 Windows 上必然 false-negative · skip 而非 fail。
_IS_WINDOWS = sys.platform == "win32" or platform.system() == "Windows"


# ─── #1 · 脚本存在性 ─────────────────────────────────────

def test_install_script_exists():
    assert SCRIPT.exists(), "install-hermes.sh 必须在 repo root"
    if _IS_WINDOWS:
        pytest.skip("Unix 可执行位 (S_IXUSR) 在 Windows 文件系统无意义")
    # 可执行权限
    import stat
    mode = SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, "install-hermes.sh 必须可执行 (chmod +x)"


def test_install_script_bash_syntax_valid():
    """bash -n 不实际执行 · 只检查语法."""
    if _IS_WINDOWS:
        pytest.skip("bash 语法检查依赖 POSIX shell · Windows 上 WSL bash 常损坏")
    bash = shutil.which("bash")
    if not bash:
        return  # CI 没 bash · skip
    r = subprocess.run([bash, "-n", str(SCRIPT)], capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, f"bash 语法错: {r.stderr}"


# ─── #2 · 安全 flag ──────────────────────────────────────

def test_install_script_uses_strict_mode():
    """set -euo pipefail · 任何 error 立即退出 · 防止半装."""
    body = SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in body, "脚本必须开严格模式 · 防止安装中途 silent fail"


# ─── #3 · 安装 4 个 skill ─────────────────────────────────

def test_install_script_covers_all_four_skills():
    body = SCRIPT.read_text(encoding="utf-8")
    for s in ("deep-analysis", "investor-panel", "lhb-analyzer", "trap-detector"):
        assert s in body, f"安装脚本缺 {s}"


def test_install_script_creates_symlinks_not_copies():
    """symlink 让 git pull 立刻生效 · 不要 cp (会变陈旧)."""
    body = SCRIPT.read_text(encoding="utf-8")
    assert "ln -sfn" in body


def test_install_script_handles_existing_clone():
    """clone 存在时 pull 更新 · 不重复 clone 报错."""
    body = SCRIPT.read_text(encoding="utf-8")
    assert "git -C" in body and "pull" in body


def test_install_script_cleans_old_hub_install():
    """user 之前 hermes skills install 装过 · 必须先清理 · 否则 symlink 会失败."""
    body = SCRIPT.read_text(encoding="utf-8")
    assert "rm -rf" in body
    # 清理目标必须是 hermes skills dir 下的 4 个 skill · 不能 rm 错地方
    assert "HERMES_SKILLS_DIR" in body


# ─── #4 · venv pip fallback ──────────────────────────────

def test_install_script_pip_fallback_when_venv_missing():
    """Hermes venv 可能在 ~/.hermes/venv 或 ~/.hermes/.venv · 两种都试 · 都没用系统 pip."""
    body = SCRIPT.read_text(encoding="utf-8")
    assert "venv/bin/pip" in body
    assert ".venv/bin/pip" in body
    # 兜底
    assert "pip install" in body


# ─── #5 · 文档链接 ───────────────────────────────────────

def test_install_hermes_md_promotes_script():
    """INSTALL-HERMES.md 顶部必须显眼指向新脚本 · 不能继续推 hermes skills install."""
    doc = (REPO_ROOT / "INSTALL-HERMES.md").read_text(encoding="utf-8")
    assert "install-hermes.sh" in doc
    # 必须说明 Skills Guard 问题
    assert "Skills Guard" in doc
    assert "DANGEROUS" in doc
    # 指向 Hermes 上游 issue
    assert "1006" in doc  # NousResearch/hermes-agent#1006


def test_readme_links_to_install_script():
    """README 安装表必须更新 · 不能继续说 hermes skills install 就行."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "install-hermes.sh" in readme


# ─── #6 · 不要绕过用户意图 ──────────────────────────────

def test_install_script_does_not_skip_security_scan_silently():
    """脚本必须打印明确 banner 说明它在做什么 · 不能静默运行."""
    body = SCRIPT.read_text(encoding="utf-8")
    assert "UZI-Skill" in body
    assert "Hermes" in body
    # 完成后必须打印验证信息
    assert "验证" in body or "verify" in body.lower()
