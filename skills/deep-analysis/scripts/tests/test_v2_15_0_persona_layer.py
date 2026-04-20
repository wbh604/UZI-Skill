"""Regression tests for v2.15.0 · YAML persona 层（从 augur 吸收 + 保留自有优势）."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

PERSONAS_DIR = SCRIPTS.parent / "personas"


# ─── persona 目录完整性 ──────────────────────────────────────────

def test_personas_dir_exists():
    assert PERSONAS_DIR.exists(), "personas/ 目录必须存在"


def test_51_persona_files_present():
    yamls = list(PERSONAS_DIR.glob("*.yaml"))
    assert len(yamls) == 51, f"应有 51 个 persona YAML，实际 {len(yamls)}"


def test_12_flagship_personas():
    """flagship 必须是手写（无 _meta.status=auto_generated_stub）· 12 个."""
    from lib.personas import load_all_personas
    all_p = load_all_personas()
    flagship_ids = {p.id for p in all_p.values() if p.is_flagship}
    expected = {
        "buffett", "graham", "fisher", "munger",
        "lynch", "wood",
        "soros", "dalio",
        "duan", "zhangkun",
        "zhao_lg", "zhang_mz",
    }
    assert flagship_ids == expected, f"flagship 应恰好是 {expected}，实际 {flagship_ids}"


def test_flagship_has_all_required_fields():
    """flagship 必须有 philosophy + key_metrics + voice + a_share_view."""
    from lib.personas import load_persona
    for iid in ("buffett", "lynch", "zhao_lg", "wood", "duan"):
        p = load_persona(iid)
        assert p is not None, f"{iid} 加载失败"
        assert p.name, f"{iid} 缺 name"
        assert p.philosophy, f"{iid} 缺 philosophy"
        assert len(p.key_metrics) >= 3, f"{iid} key_metrics 过少"
        assert p.voice, f"{iid} 缺 voice"
        assert p.a_share_view, f"{iid} 缺 a_share_view"


def test_stub_persona_marked_correctly():
    """stub persona 必须标记 is_flagship=False."""
    from lib.personas import load_persona
    # 抽样 stub
    for iid in ("templeton", "simons", "liu_sh"):
        p = load_persona(iid)
        assert p is not None
        assert not p.is_flagship, f"{iid} 应标记为 stub"


def test_persona_ids_match_panel_investors():
    """personas/ 里的 id 必须和 panel.json 里的 investor_id 一一对应."""
    import json
    panel_path = SCRIPTS / ".cache" / "002217.SZ" / "panel.json"
    if not panel_path.exists():
        # 如果没有 cache · 跳过（CI 环境）
        return
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    panel_ids = {i["investor_id"] for i in panel["investors"]}
    yaml_ids = {p.stem for p in PERSONAS_DIR.glob("*.yaml")}
    missing = panel_ids - yaml_ids
    extra = yaml_ids - panel_ids
    assert not missing, f"panel.json 有但 personas/ 缺：{missing}"
    assert not extra, f"personas/ 有但 panel.json 缺：{extra}"


# ─── Persona dataclass + prompt block ───────────────────────────

def test_persona_to_prompt_block():
    from lib.personas import load_persona
    p = load_persona("buffett")
    block = p.to_prompt_block()
    assert "沃伦·巴菲特" in block or "Buffett" in block
    assert "Philosophy" in block
    assert "Key Metrics" in block
    assert "Voice" in block
    assert len(block) < 2500, "persona block 不宜过长（prefix cache 考量）"


def test_build_system_message_is_prefix_stable():
    """相同 snapshot + lang 必须产出字节级一致的 system message（prompt cache 关键）."""
    from lib.personas import build_system_message
    snap = '{"ticker":"002217.SZ","pe":882}'
    a = build_system_message(snap, lang="zh")
    b = build_system_message(snap, lang="zh")
    assert a == b, "prefix-stable 断言失败"


def test_build_persona_user_message_contains_persona_block():
    from lib.personas import load_persona, build_persona_user_message
    p = load_persona("lynch")
    msg = build_persona_user_message(p, "600519.SH")
    assert "彼得·林奇" in msg
    assert "600519.SH" in msg
    assert "PEG" in msg  # lynch flagship 里必定有 PEG key_metric


# ─── i18n ───────────────────────────────────────────────────────

def test_language_instruction_default_zh():
    import os
    from lib.i18n import language_instruction
    os.environ.pop("UZI_LANG", None)
    txt = language_instruction()
    assert "中文" in txt or "zh" in txt.lower()


def test_language_instruction_en():
    from lib.i18n import language_instruction
    txt = language_instruction("en")
    assert "English" in txt


def test_language_env_override():
    import os
    from lib.i18n import get_language
    os.environ["UZI_LANG"] = "en"
    try:
        assert get_language() == "en"
    finally:
        os.environ.pop("UZI_LANG", None)


def test_language_falls_back_to_zh_on_unknown():
    import os
    from lib.i18n import get_language
    os.environ["UZI_LANG"] = "jp"  # unsupported
    try:
        assert get_language() == "zh"
    finally:
        os.environ.pop("UZI_LANG", None)


# ─── SKILL.md HARD-GATE 文档 ────────────────────────────────────

def test_skill_md_has_persona_hard_gate():
    skill = SCRIPTS.parent / "SKILL.md"
    txt = skill.read_text(encoding="utf-8")
    assert "HARD-GATE-PERSONA-ROLEPLAY" in txt
    assert "personas/" in txt
    assert "flagship" in txt.lower()
