"""Read-only, pre-publication check for private rotation artifacts in the Git index."""
from __future__ import annotations

import csv
import fnmatch
import io
import json
import subprocess
from pathlib import Path, PurePosixPath


def private_path(path: str) -> bool:
    parts = PurePosixPath(path.lower()).parts
    name = parts[-1]
    patterns = (
        "citic_industry_fund_flow*", "sector_fund_flow*.csv*", "stock_fund_flow*.csv*",
        "today_proxy_*", "rotation.json", "rankings.csv", "*rotation*.html",
        "*rotation*.png", "*rotation*.jpg", "*rotation*.zip", "*rotation*.csv*",
    )
    return (
        ".private" in parts
        or any(part.startswith("industry_fund_flow_rotation") for part in parts)
        or any(a in {"data", "reports"} and b in {"rotation", "industry_rotation"}
               for a, b in zip(parts, parts[1:]))
        or any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)
    )


def _private_json(value) -> bool:
    if isinstance(value, list):
        return any(_private_json(item) for item in value)
    if not isinstance(value, dict):
        return False
    strategy, status = str(value.get("strategy", "")), str(value.get("status", ""))
    if strategy == "citic40-active-flow-rotation" or status.startswith("public_proxy_"):
        return True
    windows = value.get("windows")
    if isinstance(windows, dict) and any(
        isinstance(block, dict) and {"base", "composite"} <= block.keys()
        for block in windows.values()
    ):
        return True
    return any(_private_json(item) for item in value.values())


def private_content(path: str, content: bytes) -> bool:
    suffix = PurePosixPath(path).suffix.lower()
    text = content.decode("utf-8-sig", errors="replace")
    if suffix == ".csv":
        header = set(next(csv.reader(io.StringIO(text)), []))
        return ({"active_buy_amount", "active_sell_amount"} <= header
                or {"window", "variant", "rank", "score", "code"} <= header)
    if suffix == ".json":
        try:
            return _private_json(json.loads(text))
        except (ValueError, RecursionError):
            # A malformed candidate must not silently evade inspection.
            return True
    if suffix == ".html":
        return "行业资金流轮动" in text and "周频" in text
    return False


def inspect_index(repo: Path) -> list[str]:
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True,
        ).stdout

    entries = git("ls-files", "--stage", "-z").split(b"\0")
    violations = []
    for entry in entries:
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, sha, stage = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8", errors="replace")
        if stage != "0":
            raise ValueError("索引有未解决的合并冲突，先处理冲突再发布")
        if private_path(path):
            violations.append(path)
            continue
        if mode not in {"100644", "100755"} or Path(path).suffix.lower() not in {".csv", ".json", ".html"}:
            continue
        object_id = sha
        size = int(git("cat-file", "-s", object_id))
        if size > 16 * 1024 * 1024 or private_content(path, git("cat-file", "blob", object_id)):
            violations.append(path)
    return violations


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[5])
    args = parser.parse_args()
    try:
        violations = inspect_index(args.repo)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"无法完成轮动数据检查：{type(exc).__name__}\n")
    if violations:
        parser.exit(1, "拒绝发布：索引包含疑似私有轮动数据，请取消暂存并保留本地文件：\n"
                    + "\n".join(violations) + "\n")
    print("PASS: Git 索引未发现已知轮动数据或结果特征（不替代人工核查）")


if __name__ == "__main__":
    main()
