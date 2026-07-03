"""Regression for issue #73 (SKILL.md version sync) + #74 (JSON date serialization).

#73 (@jxpeng98)：install-hermes.sh 装完显示 v3.3.1（非最新）。根因：4 个 SKILL.md
的 `version:` frontmatter 从未随 manifest 一起 bump，且 .version-bump.json 漏了它们。
脚本验证步骤读 SKILL.md version → 显示陈旧的 3.3.1。

#74 (@constansino)：pipeline cache 写 json.dumps 未带 default=str，遇到
datetime/Decimal/numpy/pandas 对象会序列化崩溃。PR #75 修了 run.py，但 score.py /
preflight_helpers.py 还有遗漏。

测试覆盖：
1. 4 个 SKILL.md version 与 manifest 一致（不再停在 3.3.1）
2. .version-bump.json 包含全部 4 个 SKILL.md（防再次漏 bump）
3. score.py / preflight_helpers.py 的 json.dumps 都带 default=str
4. default=str 行为：datetime/Decimal 不再崩溃
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parents[2]
sys.path.insert(0, str(SCRIPTS))


# ─── #73 · SKILL.md 版本同步 ─────────────────────────────

SKILLS = ["deep-analysis", "investor-panel", "lhb-analyzer", "trap-detector"]


def _manifest_version() -> str:
    return json.loads((REPO / "package.json").read_text(encoding="utf-8"))["version"]


def _skill_version(skill: str) -> str:
    for line in (REPO / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip()
    return ""


def test_all_skill_md_match_manifest_version():
    """4 个 SKILL.md version 必须 == manifest · 不再停在 3.3.1 (issue #73)."""
    mv = _manifest_version()
    for s in SKILLS:
        sv = _skill_version(s)
        assert sv == mv, f"{s}/SKILL.md version={sv} != manifest {mv} (issue #73)"


def test_skill_md_not_stuck_at_331():
    for s in SKILLS:
        assert _skill_version(s) != "3.3.1", f"{s} 仍停在 3.3.1"


def test_version_bump_includes_all_skill_md():
    """.version-bump.json 必须含 4 个 SKILL.md · 否则未来又会漏 bump."""
    vb = json.loads((REPO / ".version-bump.json").read_text(encoding="utf-8"))
    for s in SKILLS:
        path = f"skills/{s}/SKILL.md"
        assert path in vb["files"], f".version-bump.json files 缺 {path}"
        assert path in vb["patterns"], f".version-bump.json patterns 缺 {path}"
        assert "VERSION" in vb["patterns"][path]


# ─── #74 · JSON date serialization (default=str) ──────────

def test_pipeline_json_writers_use_default_str():
    """score.py / preflight_helpers.py 的 json.dumps 都要带 default=str (issue #74)."""
    for rel in ("lib/pipeline/score.py", "lib/pipeline/preflight_helpers.py", "lib/pipeline/run.py"):
        src = (SCRIPTS / rel).read_text(encoding="utf-8")
        # 找所有写 cache 的 json.dumps · 必须都带 default=str
        import re
        dumps_calls = re.findall(r"json\.dumps\([^)]*\)", src)
        unguarded = [c for c in dumps_calls
                     if ("ensure_ascii" in c and "default=" not in c)]
        assert not unguarded, f"{rel} 有未带 default=str 的 cache 写: {unguarded}"


def test_default_str_handles_date_decimal():
    """default=str 确实能序列化 date / datetime / Decimal · 不崩."""
    payload = {"d": date(2026, 6, 6), "dt": datetime(2026, 6, 6, 9, 30),
               "dec": Decimal("1.5"), "normal": "ok"}
    # 不带 default 会崩
    try:
        json.dumps(payload)
        raise AssertionError("预期不带 default 会 TypeError")
    except TypeError:
        pass
    # 带 default=str 正常
    out = json.dumps(payload, ensure_ascii=False, default=str)
    assert "2026-06-06" in out
    assert "1.5" in out
