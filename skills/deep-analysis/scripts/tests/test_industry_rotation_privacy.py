"""Publication checks use synthetic temporary data only."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.industry_rotation.privacy import inspect_index, private_content, private_path


@pytest.mark.parametrize("path", [
    "rotation.json", "data/rotation/input.csv", ".private/rotation/input.csv",
    "output/playwright/rotation-desktop.png", "reports/rotation/x/report.html",
    "arbitrary/today_proxy_2000-01-01.json", "rankings.csv", "citic_industry_fund_flow.csv.gz",
])
def test_private_paths(path):
    assert private_path(path)


def test_source_paths_are_allowed():
    assert not private_path("docs/industry-rotation.md")
    assert not private_path("lib/industry_rotation/privacy.py")
    assert not private_path("tests/test_industry_rotation.py")


@pytest.mark.parametrize("path,content", [
    ("renamed.csv", b"date,active_buy_amount,active_sell_amount\n2000-01-01,10,9\n"),
    ("renamed.csv", b"window,variant,rank,score,code\n20,base,1,1,synthetic\n"),
    ("renamed.json", json.dumps({"strategy": "citic40-active-flow-rotation"}).encode()),
    ("renamed.json", json.dumps({"windows": {"20": {"base": [], "composite": []}}}).encode()),
    ("renamed.html", "<title>行业资金流轮动</title><p>周频合成示例</p>".encode()),
])
def test_renaming_does_not_hide_known_contents(path, content):
    assert private_content(path, content)


def test_non_rotation_json_allowed():
    assert not private_content("package.json", b'{"name":"uzi","version":"1"}')


def test_scanner_checks_index_not_worktree_and_never_deletes(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init")
    path = tmp_path / "renamed.csv"
    path.write_text("active_buy_amount,active_sell_amount\n10,9\n", encoding="utf-8")
    git("add", "renamed.csv")
    path.write_text("public_header\npublic_value\n", encoding="utf-8")
    assert inspect_index(tmp_path) == ["renamed.csv"]
    assert path.read_text() == "public_header\npublic_value\n"
    git("add", "renamed.csv")
    assert inspect_index(tmp_path) == []


def test_repository_ignores_rotation_results():
    repo = Path(__file__).resolve().parents[4]
    paths = [".private/rotation/input.csv", "output/playwright/rotation-desktop.png",
             "skills/deep-analysis/scripts/reports/rotation/2000-01-01/report.html",
             "data/rotation/private.csv", "today_proxy_2000-01-01.json"]
    result = subprocess.run(["git", "-C", str(repo), "check-ignore", "--no-index", "--stdin"],
                            input="\n".join(paths) + "\n", text=True, capture_output=True, check=True)
    assert set(result.stdout.splitlines()) == set(paths)
