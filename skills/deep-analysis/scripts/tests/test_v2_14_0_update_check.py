"""Regression tests for v2.14.0 · 自动检测 GitHub 新版本 · skip/cache 逻辑."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def _clear_cache():
    f = SCRIPTS / ".cache" / "_global" / "update_check.json"
    if f.exists():
        f.unlink()


def test_parse_semver_basic():
    from lib.update_check import _parse_semver
    assert _parse_semver("2.13.7") == (2, 13, 7)
    assert _parse_semver("v2.14.0") == (2, 14, 0)
    assert _parse_semver("  v1.0.0  ") == (1, 0, 0)
    assert _parse_semver("") is None
    assert _parse_semver("2.13.7-rc1") is None
    assert _parse_semver("latest") is None


def test_newer_comparison():
    from lib.update_check import _newer
    assert _newer("2.14.0", "2.13.7") is True
    assert _newer("2.13.8", "2.13.7") is True
    assert _newer("3.0.0", "2.99.99") is True
    assert _newer("2.13.7", "2.13.7") is False
    assert _newer("2.13.6", "2.13.7") is False
    # 非 semver → 保守 False
    assert _newer("bad", "2.13.7") is False


def test_env_disable_check():
    from lib import update_check as uc
    _clear_cache()
    os.environ["UZI_NO_UPDATE_CHECK"] = "1"
    try:
        result = uc.check_for_update()
        assert result is None, "env 禁用时必须返 None"
    finally:
        os.environ.pop("UZI_NO_UPDATE_CHECK", None)


def test_no_update_when_same_version():
    from lib import update_check as uc
    _clear_cache()
    fake_release = {"tag_name": "v2.13.7", "body": "same version", "html_url": "x"}
    with patch.object(uc, "_read_local_version", return_value="2.13.7"), \
         patch.object(uc, "_fetch_latest_release", return_value=fake_release):
        assert uc.check_for_update(force=True) is None


def test_update_available_returns_info():
    from lib import update_check as uc
    _clear_cache()
    fake_release = {
        "tag_name": "v2.14.0",
        "body": "## v2.14.0\nauto update check" + "x" * 1000,
        "html_url": "https://example/release",
    }
    with patch.object(uc, "_read_local_version", return_value="2.13.7"), \
         patch.object(uc, "_fetch_latest_release", return_value=fake_release):
        info = uc.check_for_update(force=True)
    assert info is not None
    assert info.current == "2.13.7"
    assert info.latest == "2.14.0"
    assert len(info.notes) <= 601  # 600 + ellipsis
    assert "v2.14.0" in info.notes or "auto update check" in info.notes


def test_skip_marker_suppresses_prompt_same_version():
    from lib import update_check as uc
    _clear_cache()
    fake_release = {"tag_name": "v2.14.0", "body": "notes", "html_url": "x"}
    with patch.object(uc, "_read_local_version", return_value="2.13.7"), \
         patch.object(uc, "_fetch_latest_release", return_value=fake_release):
        # 第一次问 · 返 info
        info = uc.check_for_update(force=True)
        assert info is not None
        # 用户选 skip
        uc.mark_skipped(info.latest)
        # 再查同版本（非 force · 用 cache · cache 新鲜 → 走 cache 分支）
        info2 = uc.check_for_update(force=False)
        assert info2 is None, "skip 后同版本不再弹"


def test_skip_marker_does_not_suppress_newer_version():
    from lib import update_check as uc
    _clear_cache()
    uc.mark_skipped("2.14.0")
    # 现在出了 2.14.1
    fake_release = {"tag_name": "v2.14.1", "body": "newer", "html_url": "x"}
    with patch.object(uc, "_read_local_version", return_value="2.13.7"), \
         patch.object(uc, "_fetch_latest_release", return_value=fake_release):
        info = uc.check_for_update(force=True)
    assert info is not None, "更新的版本必须再弹 · skip 仅针对某个具体 tag"
    assert info.latest == "2.14.1"


def test_network_failure_silent_skip():
    from lib import update_check as uc
    _clear_cache()
    with patch.object(uc, "_read_local_version", return_value="2.13.7"), \
         patch.object(uc, "_fetch_latest_release", return_value=None):
        # GH API 挂 · 不能 raise · 不能弹
        assert uc.check_for_update(force=True) is None


def test_cache_suppresses_repeat_api_call():
    from lib import update_check as uc
    _clear_cache()
    fake_release = {"tag_name": "v2.14.0", "body": "notes", "html_url": "x"}
    calls = {"n": 0}

    def fake_fetch():
        calls["n"] += 1
        return fake_release

    with patch.object(uc, "_read_local_version", return_value="2.13.7"), \
         patch.object(uc, "_fetch_latest_release", side_effect=fake_fetch):
        # 第一次 force=False · cache 空 · 触发 fetch
        uc.check_for_update(force=False)
        # mark skip so cache 分支 hit
        uc.mark_skipped("2.14.0")
        # 第二次立刻再查（cache 新鲜 + skip · 应直接返 None 不打 API）
        assert uc.check_for_update(force=False) is None
    # 只打了 1 次 API
    assert calls["n"] == 1


def test_handle_answer_skip_writes_state():
    from lib import update_check as uc
    _clear_cache()
    msg = uc.handle_answer("s", "2.14.0")
    assert "跳过" in msg or "skip" in msg.lower()
    state = json.loads((SCRIPTS / ".cache" / "_global" / "update_check.json").read_text())
    assert state.get("skipped_version") == "2.14.0"


def test_handle_answer_yes_shows_update_commands():
    from lib.update_check import handle_answer
    msg = handle_answer("y", "2.14.0")
    assert "/plugin update" in msg
    assert "git pull" in msg


def test_handle_answer_no_is_noop():
    from lib.update_check import handle_answer
    _clear_cache()
    msg = handle_answer("n", "2.14.0")
    # 不能写 skip
    f = SCRIPTS / ".cache" / "_global" / "update_check.json"
    if f.exists():
        state = json.loads(f.read_text())
        assert state.get("skipped_version") != "2.14.0", "选 n 不应写 skip"


def test_format_prompt_contains_all_options():
    from lib.update_check import UpdateInfo, format_prompt
    info = UpdateInfo(current="2.13.7", latest="2.14.0", notes="blah", url="http://x")
    txt = format_prompt(info)
    assert "v2.13.7" in txt
    assert "v2.14.0" in txt
    assert "[y]" in txt and "[s]" in txt and "[n]" in txt
    assert "跳过本版" in txt
