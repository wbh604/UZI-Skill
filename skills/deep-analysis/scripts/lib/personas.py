"""v2.15.0 · YAML persona 加载 + prefix-stable system message 构建（借鉴 augur 设计）.

设计原则：
- Persona YAML 是 Rules 引擎的补充，不是替代 —— Rules 仍给确定性骨架分
- agent role-play 阶段读取 persona，让 headline / commentary 更 in-voice
- flagship persona（12 手写）优先级 > stub persona（39 自动生成）
- stub persona 存在是为了让 51 人名单完整，但 agent 应主要靠 Rules 判断
- prefix-stable system message：所有 51 persona 调用共用同一 system prompt，利用 prompt cache
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PERSONAS_DIR = Path(__file__).resolve().parent.parent.parent / "personas"


@dataclass
class Persona:
    id: str
    name: str
    school: str
    group: str  # A-G
    philosophy: str = ""
    key_metrics: list[str] = field(default_factory=list)
    avoids: list[str] = field(default_factory=list)
    a_share_view: str = ""
    voice: str = ""
    famous_positions: list[str] = field(default_factory=list)
    is_flagship: bool = False  # flagship 手写 vs stub 自动生成
    raw: dict = field(default_factory=dict)

    def to_prompt_block(self) -> str:
        """把 persona 压缩为 LLM system prompt 里的段落（< 600 字）."""
        lines = [
            f"# PERSONA · {self.name} ({self.id})",
            f"School: {self.school} · Group: {self.group}",
            "",
        ]
        if self.philosophy:
            lines.append(f"## Philosophy\n{self.philosophy.strip()[:400]}")
        if self.key_metrics:
            lines.append(f"\n## Key Metrics / Signals\n" + "\n".join(f"- {m}" for m in self.key_metrics[:8]))
        if self.avoids:
            lines.append(f"\n## Avoids\n" + "\n".join(f"- {a}" for a in self.avoids[:6]))
        if self.a_share_view:
            lines.append(f"\n## A-Share View\n{self.a_share_view.strip()[:300]}")
        if self.voice:
            lines.append(f"\n## Voice / Tone\n{self.voice.strip()[:200]}")
        if self.famous_positions:
            lines.append(f"\n## Famous Positions\n" + "\n".join(f"- {p}" for p in self.famous_positions[:5]))
        return "\n".join(lines)


def _parse_minimal_yaml(text: str) -> dict:
    """零依赖迷你 YAML parser · 只处理 personas/ 下的简化格式.

    支持：
    - `key: value` 标量
    - `key: |` 多行字符串
    - `key:` 后跟 `  - item` 列表
    - `# comment` 注释
    - 顶级 key: dict（比如 _meta: { key: val, key: val }）
    """
    result: dict[str, Any] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        # 顶级 key · 必须顶格（没 leading space）
        if not line.startswith(" ") and ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "|":
                # 多行字符串（下面带缩进的都归这个 key）
                block = []
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    if not nxt.strip() and (i + 1 >= len(lines) or not lines[i+1].startswith(" ")):
                        break
                    if nxt.startswith("  "):
                        block.append(nxt[2:] if nxt.startswith("  ") else nxt)
                        i += 1
                    elif not nxt.strip():
                        block.append("")
                        i += 1
                    else:
                        break
                result[key] = "\n".join(block).rstrip()
                continue
            elif value == "":
                # 要么是列表，要么是嵌套 dict
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
                if items:
                    result[key] = items
                elif child:
                    result[key] = child
                else:
                    result[key] = ""
                continue
            else:
                # 简单标量 · 去引号
                result[key] = value.strip('"\'')
                i += 1
                continue
        i += 1
    return result


def load_persona(investor_id: str) -> Persona | None:
    """根据 investor_id（如 'buffett' / 'zhao_lg'）读 YAML · 返 Persona 或 None."""
    path = PERSONAS_DIR / f"{investor_id}.yaml"
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        d = _parse_minimal_yaml(text)
        is_stub = False
        meta = d.get("_meta") or {}
        if isinstance(meta, dict):
            is_stub = meta.get("status") == "auto_generated_stub"
        return Persona(
            id=d.get("id", investor_id),
            name=d.get("name", ""),
            school=d.get("school", ""),
            group=d.get("group", ""),
            philosophy=d.get("philosophy", "") if isinstance(d.get("philosophy"), str) else "",
            key_metrics=d.get("key_metrics", []) if isinstance(d.get("key_metrics"), list) else [],
            avoids=d.get("avoids", []) if isinstance(d.get("avoids"), list) else [],
            a_share_view=d.get("a_share_view", "") if isinstance(d.get("a_share_view"), str) else "",
            voice=d.get("voice", "") if isinstance(d.get("voice"), str) else "",
            famous_positions=d.get("famous_positions", []) if isinstance(d.get("famous_positions"), list) else [],
            is_flagship=not is_stub,
            raw=d,
        )
    except Exception:
        return None


def load_all_personas() -> dict[str, Persona]:
    """加载全部 51 persona · 返 {id: Persona}."""
    result = {}
    for path in PERSONAS_DIR.glob("*.yaml"):
        p = load_persona(path.stem)
        if p and p.id:
            result[p.id] = p
    return result


FRAMEWORK_INSTRUCTIONS_ZH = """你在参与一个多投资者 role-play 分析工作台。

你每次会扮演一个特定投资者，基于他/她的 philosophy + key_metrics + avoids + voice + a_share_view
来对一只股票给出判断。规则：

1. **完全 in-character** · 不要假装中立，不要和稀泥
   - 价值派恨科技股就直说
   - 宏观派只看宏观，不评基本面
   - 游资派只看盘口，不评 DCF

2. **必须引用具体数据** · 从给定 SNAPSHOT 里抓 PE / ROE / 营收 / 市值 / 行业等具体数字
   - ❌ "估值合理" → ✅ "PE 21 对 ROE 30% 的公司不贵"
   - ❌ "基本面良好" → ✅ "营收 +27% 但 EPS 0，没转化为利润"

3. **必须引用 persona 的 key_metrics** · 哪条命中、哪条不过 · 说清楚
   - 巴菲特：ROE 连续 10 年 > 15% 必须提到
   - 林奇：PEG < 1 必须计算
   - 段永平：PE < 40 必须对照
   - 赵老哥：市值射程、封板时间必须验证

4. **输出 signal** · 明确 bullish / neutral / bearish / skip(不适合)
5. **输出 verdict** · 明确 强烈买入 / 买入 / 关注 / 观望 / 回避 / 不适合
6. **输出 reasoning** · 2-3 段 in-voice 文字，引用 voice 字段的风格词汇

如果 persona 是 auto_generated_stub（_meta.status）· 优先依据 Rules 引擎命中的具体规则，
YAML voice 仅作语气补充。不要假装比 Rules 知道更多。

OUTPUT 要求严格 JSON 格式：
{
  "investor_id": string,
  "signal": "bullish" | "neutral" | "bearish" | "skip",
  "score": 0-100,
  "verdict": string,
  "headline": string (< 80 字 · 强结论),
  "reasoning": string (2-3 段 in-voice · 引用数据 + key_metrics),
  "persona_used": "flagship" | "stub"
}"""


def build_system_message(
    snapshot_json: str,
    lang: str = "zh",
    include_flagship_tips: bool = True,
) -> str:
    """构建 prefix-stable system message（借鉴 augur · prompt cache 优化）.

    51 persona 调用时全部用这个 message 作为 system · 只有 user message 不同（persona 切换）·
    Anthropic / OpenAI prompt cache 能命中前缀，省 50-90% input token.
    """
    from lib.i18n import language_instruction
    parts = [
        FRAMEWORK_INSTRUCTIONS_ZH,
        "",
        language_instruction(lang),
        "",
        "# MARKET SNAPSHOT（全体 persona 共享，请勿重复提取）",
        snapshot_json,
    ]
    return "\n".join(parts)


def build_persona_user_message(persona: Persona, ticker: str, task: str = "analyze") -> str:
    """构建 persona 专用的 user message · 包含 persona block + 任务指令."""
    return (
        persona.to_prompt_block()
        + f"\n\n---\n\n# TASK\n"
        + f"现在请你以 {persona.name}（{persona.id}）的身份分析股票 {ticker}，"
        + f"严格按照上面的 philosophy / key_metrics / voice。"
        + f"输出 JSON 格式的 PersonaVote（见 system message 末尾的格式约束）。"
    )


if __name__ == "__main__":
    # smoke test
    import json as _json
    all_p = load_all_personas()
    print(f"加载 persona: {len(all_p)}")
    flagship = [p for p in all_p.values() if p.is_flagship]
    stub = [p for p in all_p.values() if not p.is_flagship]
    print(f"  flagship: {len(flagship)} · {sorted(p.id for p in flagship)}")
    print(f"  stub: {len(stub)}")

    b = all_p.get("buffett")
    if b:
        print(f"\nBuffett persona block:\n{b.to_prompt_block()[:500]}")
