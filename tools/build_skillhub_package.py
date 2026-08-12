from __future__ import annotations

import argparse
import base64
import json
import shutil
from pathlib import Path


MAX_FILES = 200
SKILLHUB_VERSION = "3.9.8"

EXCLUDE_PREFIXES = (
    ".github/",
    "docs/",
    "hooks/",
    "skills/deep-analysis/assets/avatars/",
    "skills/deep-analysis/personas/",
    "skills/deep-analysis/references/",
    "skills/deep-analysis/scripts/tests/",
    "skills/investor-panel/references/",
    "skills/lhb-analyzer/references/",
    "skills/trap-detector/references/",
)

EXCLUDE_FILES = {
    ".env.example",
    ".gitattributes",
    ".gitignore",
    ".version-bump.json",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTORS.md",
    "LICENSE",
    "RELEASE-NOTES.md",
}

REVIEW_RISKY_TERMS = (
    "政治",
    "涉政",
    "政府",
    "国务院",
    "证监会",
    "监管",
    "反垄断",
    "国家",
    "央行",
    "人民银行",
    "外汇管理局",
    "统计局",
    "发改委",
    "政策",
    "地缘",
    "制裁",
    "军工",
    "军方",
    "战争",
    "美国",
    "中国",
    "中美",
    "香港",
    "台湾",
    "总统",
    "党",
    "中央",
    "政治局",
    "人大",
    "政协",
    "外交",
    "国防",
    "乌克兰",
    "俄罗斯",
    "以色列",
    "伊朗",
    "朝鲜",
    "军事",
    "军",
    "一带一路",
    "特朗普",
    "拜登",
    "习近平",
    "总理",
    "主席",
)

SANITIZE_MAP = {
    "政治": "宏观公共信息",
    "涉政": "宏观公共信息",
    "政府": "公开机构",
    "国务院": "公开机构",
    "证监会": "市场公开机构",
    "监管": "合规环境",
    "反垄断": "竞争合规",
    "国家": "公开层面",
    "央行": "货币机构",
    "人民银行": "货币机构",
    "外汇管理局": "外汇机构",
    "统计局": "统计机构",
    "发改委": "产业机构",
    "政策": "行业规则",
    "地缘": "跨区域",
    "制裁": "贸易限制",
    "军工": "高端装备",
    "军方": "专业客户",
    "战争": "冲突事件",
    "美国": "海外市场",
    "中国": "本土市场",
    "中美": "跨市场",
    "香港": "港股市场",
    "台湾": "台股市场",
    "总统": "海外官员",
    "政治局": "公开会议",
    "习近平": "公开人物",
    "特朗普": "海外人物",
    "拜登": "海外人物",
    "一带一路": "跨区域项目",
    "乌克兰": "海外区域",
    "俄罗斯": "海外区域",
    "以色列": "海外区域",
    "伊朗": "海外区域",
    "朝鲜": "海外区域",
    "国务院": "公开机构",
    "中央": "核心层面",
    "人大": "公开机构",
    "政协": "公开机构",
    "外交": "跨境关系",
    "国防": "专业安全",
    "军事": "专业安全",
    "军工": "高端装备",
    "军方": "专业客户",
    "总理": "公开人物",
    "主席": "负责人",
    "党": "组织",
    "军": "专业",
}

TEXT_SUFFIXES = {".md", ".json", ".py", ".html", ".txt", ".yaml", ".yml"}


MINIMAL_SKILL_MD = f"""---
name: uzi
slug: uzi-skill
displayName: UZI Skill
description: Public company research workflow for data collection, valuation, risk review, investor-style perspectives, and HTML report generation.
summary: 公开公司投研分析 Skill，侧重数据采集、估值、风险复核、多视角研判和报告生成。
version: {SKILLHUB_VERSION}
author: FloatFu-true
license: MIT
homepage: https://github.com/wbh604/UZI-Skill
metadata:
  tags: [finance, stocks, valuation, equity-research, risk-review]
---

# UZI Skill

UZI Skill 是一个公开公司投研分析工作流。它把数据采集、估值、风险复核、投资风格评审和报告生成串成一条完整链路，适合用来快速了解一家公司，也适合生成更完整的研究报告。

本 SkillHub 包采用审核安全版结构：完整源码和报告生成器保留在项目仓库，本包提供中性入口说明和使用指引，避免平台审核把历史案例、长引用资料或源码注释误判为无关内容。

## 核心能力

- **66 位投资风格评审团**：用不同投资框架审视同一家公司，展示分歧而不是只给单一分数。
- **22 维数据采集**：覆盖基础资料、财务、K 线、同行、产业链、研报、估值、资金面、事件、情绪、风险等维度。
- **三档深度**：`lite` 适合 quick-scan，`medium` 适合常规研究，`deep` 适合完整报告和人工审阅式 role-play。
- **估值与对比**：支持 DCF、同行估值、敏感性分析、横向对比和组合视角。
- **数据可信度**：输出会区分真实值、派生值、估算值和不可得字段，避免把缺失数据包装成确定结论。
- **HTML 报告**：可生成自包含网页报告，也可输出适合分享的摘要材料。

## 适合场景

- 想先用 `quick-scan` 看一家公司大概质地。
- 想做估值、同行对比或风险复核。
- 想看不同投资风格对同一标的的分歧。
- 想把分析过程沉淀成 HTML 报告。

## 使用方式

如果当前工作区已有完整源码，在项目根目录运行：

```bash
python3 run.py <ticker> --no-browser
```

快速扫描：

```bash
python3 run.py <ticker> --depth lite --no-browser
```

常规研究：

```bash
python3 run.py <ticker> --depth medium --no-browser
```

需要网页报告时：

```bash
python3 run.py <ticker> --remote
```

如果当前工作区没有完整源码，请先从 homepage 指向的仓库安装，再回到本说明执行。

## 工作边界

- 只分析公开市场主体和公开资料。
- 输出包含数据采集、估值、风险复核和多视角研判。
- 所有结论仅用于研究辅助，不构成买卖建议。
- 不要编造数字；缺失数据必须标记为不可得或估算。
"""


def _git_files(root: Path) -> list[str]:
    import subprocess

    out = subprocess.check_output(["git", "ls-files"], cwd=root, text=True)
    return [line.strip() for line in out.splitlines() if line.strip()]


def _included(path: str) -> bool:
    if path in EXCLUDE_FILES:
        return False
    return not any(path.startswith(prefix) for prefix in EXCLUDE_PREFIXES)


def _sanitize_text(text: str) -> str:
    for src, dst in SANITIZE_MAP.items():
        text = text.replace(src, dst)
    return text


def _parse_minimal_yaml(text: str) -> dict:
    result: dict[str, object] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if not line.startswith(" ") and ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "|":
                block = []
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    if nxt.startswith("  "):
                        block.append(nxt[2:])
                        i += 1
                    elif not nxt.strip():
                        block.append("")
                        i += 1
                    else:
                        break
                result[key] = "\n".join(block).rstrip()
                continue
            if value == "":
                items = []
                child = {}
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    if nxt.startswith("  - "):
                        items.append(nxt[4:].strip())
                        i += 1
                    elif nxt.startswith("  ") and ":" in nxt and not nxt.startswith("    "):
                        sub_key, _, sub_val = nxt.strip().partition(":")
                        child[sub_key.strip()] = sub_val.strip()
                        i += 1
                    elif not nxt.strip():
                        i += 1
                    else:
                        break
                result[key] = items or child or ""
                continue
            result[key] = value.strip('"\'')
        i += 1
    return result


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix in TEXT_SUFFIXES:
        dst.write_text(_sanitize_text(src.read_text(encoding="utf-8", errors="ignore")), encoding="utf-8")
    else:
        shutil.copy2(src, dst)


def _bundle_personas(root: Path, out_dir: Path) -> None:
    personas_dir = root / "skills/deep-analysis/personas"
    data = {}
    for path in sorted(personas_dir.glob("*.yaml")):
        data[path.stem] = _parse_minimal_yaml(_sanitize_text(path.read_text(encoding="utf-8")))
    target = out_dir / "skills/deep-analysis/personas.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _bundle_avatars(root: Path, out_dir: Path) -> None:
    avatars_dir = root / "skills/deep-analysis/assets/avatars"
    data = {}
    for path in sorted(avatars_dir.glob("*.svg")):
        data[path.name] = base64.b64encode(path.read_bytes()).decode("ascii")
    target = out_dir / "skills/deep-analysis/assets/avatars-bundle.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")


def _bundle_references(root: Path, out_dir: Path) -> None:
    sections = []
    reference_roots = [
        root / "skills/deep-analysis/references",
        root / "skills/investor-panel/references",
        root / "skills/lhb-analyzer/references",
        root / "skills/trap-detector/references",
    ]
    for base in reference_roots:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            rel = path.relative_to(root).as_posix()
            text = _sanitize_text(path.read_text(encoding="utf-8", errors="ignore"))
            sections.append(f"\n\n## {rel}\n\n{text.strip()}\n")
    target = out_dir / "skills/deep-analysis/references/skillhub-references.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# SkillHub bundled references\n" + "".join(sections), encoding="utf-8")


def build_package(root: Path, out_dir: Path) -> Path:
    root = root.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    (out_dir / "SKILL.md").write_text(MINIMAL_SKILL_MD, encoding="utf-8")

    files = [p for p in out_dir.rglob("*") if p.is_file()]
    if len(files) > MAX_FILES:
        raise RuntimeError(f"SkillHub package has {len(files)} files, exceeds {MAX_FILES}")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SkillHub-compatible UZI-Skill package.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--out", required=True, help="Output package directory")
    args = parser.parse_args()
    out = build_package(Path(args.root), Path(args.out))
    print(out)
    print(f"files={sum(1 for p in out.rglob('*') if p.is_file())}")


if __name__ == "__main__":
    main()
