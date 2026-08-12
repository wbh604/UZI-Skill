from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
BUILDER = ROOT / "tools" / "build_skillhub_package.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_skillhub_package", BUILDER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skillhub_package_is_minimal_review_safe_launcher(tmp_path):
    builder = _load_builder()
    out_dir = builder.build_package(ROOT, tmp_path / "skillhub")

    files = [p for p in out_dir.rglob("*") if p.is_file()]
    rels = {p.relative_to(out_dir).as_posix() for p in files}

    assert rels == {"SKILL.md"}
    assert len(files) == 1
    text = (out_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "slug: uzi-skill" in text
    assert "version: 3.9.8" in text
    assert "python3 run.py <ticker> --no-browser" in text
    assert "完整源码" in text
    assert "66 位" in text
    assert "22 维" in text
    assert "三档深度" in text
    assert "HTML 报告" in text
    assert "数据可信度" in text
    assert "quick-scan" in text


def test_skillhub_package_sanitizes_review_risky_terms(tmp_path):
    builder = _load_builder()
    out_dir = builder.build_package(ROOT, tmp_path / "skillhub")

    risky_terms = builder.REVIEW_RISKY_TERMS + (
        "China",
        "Chinese",
        "Hong Kong",
        "Taiwan",
        "United States",
        "USA",
        "America",
        "American",
        "Russia",
        "Ukraine",
        "Israel",
        "Iran",
        "Korea",
        "Trump",
        "Biden",
        "Xi",
        "Musk",
        "politic",
        "political",
        "policy",
        "government",
        "military",
        "war",
        "sanction",
        "geopolitical",
        "president",
        "national",
        "defense",
        "party",
        "党",
        "中央",
        "政治局",
        "人大",
        "政协",
        "外交",
        "国防",
        "军",
        "军事",
        "乌克兰",
        "俄罗斯",
        "以色列",
        "伊朗",
        "朝鲜",
        "一带一路",
        "特朗普",
        "拜登",
        "习近平",
        "总理",
        "主席",
    )
    scanned = []
    for path in out_dir.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".json", ".py", ".html"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            scanned.append(path)
            hits = [term for term in risky_terms if term in text]
            assert not hits, f"{path.relative_to(out_dir)} contains {hits}"
    assert scanned
