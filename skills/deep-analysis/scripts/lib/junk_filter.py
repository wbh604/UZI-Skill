"""Autofill 噪音过滤 · v2.13.0

v2.12.1 在 run_real_test.py 里写了私有 _is_junk_autofill · 现在 Playwright 兜底
也需要同样的过滤 · 抽出来共用。

run_real_test.py::_is_junk_autofill 保留以免破现有 import · 内部改为 delegate.
"""
from __future__ import annotations

# 常见 prompt 残留 / 模板占位 / LLM 道歉 · 模块级便于扩展
JUNK_PATTERNS = (
    "类型；类型",           # MX prompt 残留（v2.12.1 bug 发现）
    "XXX", "TODO", "null", "undefined", "None",
    "抱歉，", "无法回答", "我不知道", "不清楚", "暂无数据",
    "（示例）", "（待补）",
)


def is_junk_autofill_text(text: str) -> bool:
    """检测 MX / ddgs / Playwright 兜底返的噪音数据（不写进 data 字段）.

    触发条件：
    1. 长度 < 5 → 太短无意义
    2. 命中黑名单短语（prompt 残留 / 模板占位符 / LLM 道歉）
    3. 分号分隔全同（"类型；类型；类型"）
    """
    if not text:
        return True
    t = str(text).strip()
    if len(t) < 5:
        return True
    if any(j in t for j in JUNK_PATTERNS):
        return True
    parts = [p.strip() for p in t.split("；") if p.strip()]
    if len(parts) >= 2 and len(set(parts)) == 1:
        return True
    return False
