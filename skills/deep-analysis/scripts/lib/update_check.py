"""v2.14.0 · GitHub update-check 检测插件新版本.

设计：
- 读本地 `.claude-plugin/plugin.json::version`
- 查 `api.github.com/repos/wbh604/UZI-Skill/releases/latest`
- semver 比较 · 缓存 6h 防 GH API 60/h 限流
- 支持 "skip this version"：用户跳某版后直到下一个新版前不再弹
- 非 TTY / `UZI_NO_UPDATE_CHECK=1` / 网络异常 → silent skip
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

GITHUB_REPO = "wbh604/UZI-Skill"
CACHE_TTL_SEC = 6 * 3600  # 6h · 避免 GH API 限流
HTTP_TIMEOUT = 5  # 失败快速放行

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent


def _cache_path() -> Path:
    root = Path(__file__).resolve().parent.parent / ".cache" / "_global"
    root.mkdir(parents=True, exist_ok=True)
    return root / "update_check.json"


def _read_local_version() -> str | None:
    manifest = _PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    if not manifest.exists():
        return None
    try:
        return json.loads(manifest.read_text(encoding="utf-8")).get("version")
    except Exception:
        return None


def _parse_semver(v: str) -> tuple[int, int, int] | None:
    """'2.13.7' or 'v2.13.7' → (2, 13, 7); pre-release / non-matching → None."""
    if not v:
        return None
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)$", v.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _newer(latest: str, current: str) -> bool:
    lp = _parse_semver(latest)
    cp = _parse_semver(current)
    if lp is None or cp is None:
        return False
    return lp > cp


@dataclass
class UpdateInfo:
    current: str
    latest: str
    notes: str  # release body · truncated
    url: str


def _load_state() -> dict:
    f = _cache_path()
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        _cache_path().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def mark_skipped(version: str) -> None:
    """用户选择 'skip this version' · 直到 latest 变了才再弹."""
    state = _load_state()
    state["skipped_version"] = version
    _save_state(state)


def _fetch_latest_release() -> dict | None:
    """GET /releases/latest · 失败返 None."""
    try:
        import requests
    except ImportError:
        return None
    try:
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "UZI-Skill-update-check",
            },
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def check_for_update(force: bool = False) -> UpdateInfo | None:
    """主入口 · 返 UpdateInfo(新版) 或 None（无需提示）.

    force=True 跳 cache + skip 标记，供用户手动 /uzi:update-check 用.
    """
    if os.environ.get("UZI_NO_UPDATE_CHECK") == "1":
        return None

    current = _read_local_version()
    if not current:
        return None

    state = _load_state()
    now = time.time()

    # cache 6h（force 时绕过）
    if not force:
        last = state.get("last_check_at", 0)
        cached_latest = state.get("cached_latest", "")
        if now - last < CACHE_TTL_SEC and cached_latest:
            # cache 未过期 · 直接判
            if not _newer(cached_latest, current):
                return None
            if state.get("skipped_version") == cached_latest:
                return None
            # 需要弹但缓存里没 notes · 仍要去拿一次新 release body
            # 下面 fallthrough 重新 fetch

    # 触发 GH API
    rel = _fetch_latest_release()
    state["last_check_at"] = now
    if not rel:
        _save_state(state)
        return None

    latest = (rel.get("tag_name") or "").lstrip("v")
    if not latest:
        _save_state(state)
        return None

    state["cached_latest"] = latest
    _save_state(state)

    if not _newer(latest, current):
        return None
    # 跳过本版
    if not force and state.get("skipped_version") == latest:
        return None

    notes = (rel.get("body") or "").strip()
    if len(notes) > 600:
        notes = notes[:600] + "…"

    return UpdateInfo(
        current=current,
        latest=latest,
        notes=notes,
        url=rel.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases/tag/v{latest}",
    )


def format_prompt(info: UpdateInfo) -> str:
    """标准化展示模板 · run.py 和 session-start hook 共用."""
    return (
        f"\n📦 UZI-Skill 有新版本可更新：v{info.current} → v{info.latest}\n"
        f"   {info.url}\n\n"
        f"更新内容（前 600 字）：\n{info.notes}\n\n"
        f"选项：\n"
        f"  [y] 是，我现在去更新（查看 README 安装章节的更新命令）\n"
        f"  [s] 跳过本版（v{info.latest} 之后有更新再提示）\n"
        f"  [n] 否，下次启动再问\n"
    )


def handle_answer(answer: str, latest: str) -> str:
    """user 回答归一化 · 返一句反馈文案."""
    a = (answer or "").strip().lower()
    if a in ("s", "skip", "跳过"):
        mark_skipped(latest)
        return f"✓ 已跳过 v{latest}，后续有更新版本再提示"
    if a in ("y", "yes", "是"):
        return (
            f"→ 请按 README 里你当前 agent 的更新命令操作：\n"
            f"  Claude Code: /plugin update stock-deep-analyzer\n"
            f"  git clone: cd UZI-Skill && git pull\n"
            f"  Hermes: hermes skills update wbh604/UZI-Skill/skills/deep-analysis"
        )
    return "→ 好的，下次启动再问"


if __name__ == "__main__":
    force = "--force" in sys.argv
    info = check_for_update(force=force)
    if info is None:
        print("✓ 已是最新版（或无需提示）")
        sys.exit(0)
    print(format_prompt(info))
