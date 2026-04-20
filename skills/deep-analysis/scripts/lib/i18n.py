"""v2.15.0 · 多语言开关（借鉴 augur::language_instruction 设计）.

用法：
- zh（默认）· 中文 agent / 大陆用户
- en · 英文 agent · 供 Hermes / 国际用户

集成点：
- `personas.build_system_message(lang=...)` 读 language_instruction()
- 未来可扩展到 stage2 报告文案、fetcher 错误信息等
"""
from __future__ import annotations

import os

SUPPORTED_LANGS = ("zh", "en")


def get_language() -> str:
    """按优先级返当前语言 · env > default."""
    lang = (os.environ.get("UZI_LANG") or "zh").lower()
    return lang if lang in SUPPORTED_LANGS else "zh"


def language_instruction(lang: str = "") -> str:
    """返回 system prompt 里追加的语言指令.

    agent role-play 时这段文字加入 system · 强制输出语言一致.
    """
    if not lang:
        lang = get_language()

    if lang == "en":
        return (
            "OUTPUT LANGUAGE: All reasoning, headline, verdict and commentary must be "
            "written in English. Keep persona-specific terms (e.g., '赵老哥', '段永平') "
            "in their original Chinese as they are proper nouns."
        )
    # zh default
    return (
        "输出语言：所有 reasoning / headline / verdict / commentary 必须用中文。"
        "外国投资者名（Buffett / Lynch / Wood）可混用中英文，以上下文自然为准。"
        "金融术语首选中文（净利率 / 毛利率 / 市盈率 / 护城河），技术/量化术语可保留英文（DCF / PEG / EPS）。"
    )
