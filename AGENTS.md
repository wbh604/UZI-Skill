# UZI-Skill · Agent 指令

> 本文件供 Codex / Claude Code / Cursor / Devin / OpenCode / Gemini 等 AI agent 自动读取。

## 轮动数据发布边界

行业轮动工具仅发布算法、数据契约和合成测试。真实输入、资金流明细、排名、模型持仓、报告、截图及包含它们的压缩包只保存在本地，不得上传 GitHub、Issue/PR 附件、Release、公开页面或技能包，也不得复制进公开文档。不要绕过忽略规则。提交或发布前运行 `python3 skills/deep-analysis/scripts/lib/industry_rotation/privacy.py` 检查 Git 索引，并人工核对提交清单；CI 检查不是上传前防护。不要删除用户本地数据。

---

## 🗺️ Repository Layout & Entrypoints (v3.2.0)

**绝对路径约定 —— 不要自己瞎猜** · 避免 "scripts/run.py 缺失" 这类误解：

```
UZI-Skill/                                  # ← 你 cwd 应该是这里
├── run.py                                  # ✅ 用户入口 · CLI 直跑 (python run.py <ticker>)
├── AGENTS.md / CLAUDE.md / GEMINI.md       # agent 指令
├── .claude-plugin/plugin.json              # Claude Code manifest
├── .cursor-plugin/plugin.json              # Cursor manifest
├── gemini-extension.json                   # Gemini manifest
├── package.json                            # OpenClaw / npm
└── skills/deep-analysis/
    ├── SKILL.md                            # skill 描述
    ├── assets/                             # HTML 模板 / avatars / icons
    └── scripts/                            # ← 所有 Python 业务代码在这里
        ├── run_real_test.py                # legacy stage1/stage2 入口 (v3.1 瘦身后 735 行)
        ├── assemble_report.py              # HTML shell 组装 (v3.2 瘦身后 587 行)
        ├── fetch_*.py (22 个)              # 数据采集 · 也是独立 CLI (python fetch_basic.py <ticker>)
        ├── compute_*.py                    # 机构建模 (DCF / BCG / Porter)
        ├── tests/                          # 745 passed + 1 skipped
        ├── .cache/<ticker>/                # 跑过的股票缓存
        ├── reports/<ticker>_<date>/        # 生成的 HTML 报告
        └── lib/
            ├── pipeline/                   # 🆕 v3.0 管道式架构（默认路径）
            │   ├── run.py                  # run_pipeline 编排入口
            │   ├── collect.py              # 并发 collector (22 fetcher adapter)
            │   ├── score.py                # scoring 段 (调 rrt 纯函数)
            │   ├── synthesize.py           # stage2 薄 wrapper
            │   ├── score_fns.py            # 🆕 v3.1 · 1228 行纯函数
            │   ├── preflight_helpers.py    # 🆕 v3.1 · 网络/ticker preflight
            │   ├── fetchers/registry.py    # 22 adapter 工厂
            │   └── renderer/               # 21 个 renderer stub (未完全使用)
            ├── report/                     # 🆕 v3.2 · assemble_report 拆分
            │   ├── svg_primitives.py       # 19 个 svg_* + COLOR_*
            │   ├── dim_viz.py              # 19 个 _viz_xxx + DIM_VIZ_RENDERERS
            │   ├── institutional.py        # DCF/LBO/IC memo/catalyst/competitive
            │   ├── panel_cards.py          # 66 评委 panel 渲染
            │   └── special_cards.py        # fund/insights/school_scores/debate
            └── ...（其他 lib 模块 · investor_db / network_preflight / ...）
```

### 入口 Cheat Sheet

| 操作 | 命令 |
|---|---|
| 用户一句话分析 | `python run.py <ticker>` (repo root · 走 v3.0 pipeline) |
| 强制老路径 (保险) | `UZI_LEGACY=1 python run.py <ticker>` |
| 只跑单个 fetcher | `cd skills/deep-analysis/scripts && python fetch_basic.py <ticker>` |
| 跑全量 pytest | `cd skills/deep-analysis/scripts && pytest tests/ -q` |
| Python 环境 | 任意装了 akshare/pytest 的 Python 3.10+（macOS 系统 `/usr/bin/python3` 通常缺这些 · 用 `pip install -r requirements.txt` 装；conda / venv / pyenv 都行） |

### 内部模块调用约定

- Python 模块路径起点 = `skills/deep-analysis/scripts/` · `run_real_test.py` 顶部 `sys.path.insert(0, str(HERE))` 注入
- `from lib.pipeline.score import score_from_cache` · 不是 `from skills.deep_analysis.scripts.lib...`
- `run_real_test` 对外简称 `rrt` · pipeline 调它的纯函数 (`rrt.score_dimensions` → 实际来自 `lib.pipeline.score_fns`)

### 版本分水岭

| 版本 | 变化 | 影响 agent 的部分 |
|---|---|---|
| v3.0.0 | pipeline 默认启用 · `UZI_LEGACY=1` 回老路径 | `python run.py` 默认进 pipeline |
| v3.1.0 | rrt 瘦身 65% · 纯函数搬到 score_fns | 所有 `rrt.XXX` 仍向后兼容 (re-export) |
| v3.2.0 | assemble_report 瘦身 80% · 拆 5 个 lib/report/* | 所有 `assemble_report.XXX` 仍向后兼容 |

**黄金规则**：外部 test / lib 仍可以 `import run_real_test; rrt.score_dimensions(...)` · 不用改。拆分对上层透明.

---

## 你是谁

你是一个股票深度分析 agent。用户给你一只股票，你要**采集数据 → 亲自分析每个投资者的判断 → 生成报告**。

## 核心原则

**你不是脚本运行器——你是首席分析师。** 脚本只是你的工具。

66 个投资大佬的评审必须由你 role-play，不是纯跑规则引擎：
- 巴菲特看 ROE 和护城河，但他实际持有苹果 → 这比规则更重要
- 游资只做 A 股 → 分析美股时直接跳过
- 木头姐看颠覆创新 → 给她白酒股她会说"不在平台里"

## 深浅两套路径 · 按用户意图选一条（v3.2.0）

用户一句话只说"分析 XXX"**不一定**等于要跑全量 agent 流程。先做判断：

| 用户信号 | 推荐路径 | 耗时 | 为什么 |
|---|---|---|---|
| "快速看看"、"先扫一眼"、`/quick-scan`、`/thesis` | **CLI 直跑 lite** | 30-60s | 7 维核心数据 + 10 投资者，脚本直接出报告 |
| `--depth deep` / 明确要求"深度分析"、"估值"、"DCF"、"首次覆盖"、`/ic-memo`、`/initiate` | **全量 agent 流程** | 5-10min | 22 维 + 66 评委 role-play + agent_analysis.json |
| 未明确 | **默认 medium + CLI 直跑**（仍出完整报告） | 2-4min | v2.10.5 起 CLI 直跑 medium 也能完整出 HTML |

**关键（v3.9.4 起强化）**：`--depth deep` 必须是**全量 agent 流程**——你要介入 role-play 66 评委并写 `agent_analysis.json`，不能只跑 `run.py --depth deep` 就交差。判断规则：

1. 用户明确要"深度 / 全面 / DCF / 首次覆盖 / IC memo" → **走路径 B**
2. 你看到 `--depth deep`（无论谁加的）→ **走路径 B**
3. lite / medium / 未指定 → 走路径 A（CLI 直跑，agent 不介入）

从 v2.10.4 起，`run.py` 直跑模式下 `agent_analysis.json` 缺失会降级为 warning 不阻塞 HTML。但**这只适用于 lite/medium**。deep 档缺 agent_analysis 意味着你没尽到 agent 职责——报告会缺 role-play 判断。

### 路径 A · CLI 直跑（快速 · 仅 lite/medium）

```bash
python3 run.py <ticker> --depth lite --no-browser    # 最快
python3 run.py <ticker> --depth medium --no-browser  # 默认完整度
python3 run.py <ticker> --school F --no-browser      # v3.5.0 · 只看 F 派（游资）视角
```

**注意**：路径 A 只适用于 lite/medium。**`--depth deep` 不在此列**——deep 必须走路径 B（agent 介入 role-play）。看到 deep 档时不要直接 `run.py --no-browser` 一把梭，先跑 stage1 采集，然后介入 role-play。

**v3.5.0 `--school` 参数**：用户可锁定单一流派 (A价值/B成长/C宏观/D技术/E中国价投/F游资/G量化/H科技领袖派/I Serenity 卡位猎手)，
其他派评委自动 skip · 报告顶部渲染 SCHOOL LOCK banner · 你 role-play 时**只 role-play 该派 5-8 人** ·
panel_insights / debate_rounds 都限于该派内部分歧。详见 SKILL.md `HARD-GATE-SCHOOL-LOCK`。

脚本会：
1. 跑 stage1 采集数据
2. 自检 self-review（CLI 模式下 agent_analysis 缺失是 warning）
3. 调 stage2 组装 HTML 报告

**你只需**：读最终 HTML / synthesis.json，向用户汇报核心结论。**不需要** role-play 66 评委。（这是 lite/medium 档的行为。deep 档除外——见下方路径 B。）

### 路径 B · 全量 agent 流程（深度）

用户明确要深度分析（estimation/DCF/IC memo），按下面 Step 1-5 走：

### Step 1 · 安装依赖（首次）

克隆仓库并安装依赖。仓库在 `skills/deep-analysis/scripts/` 下有所有脚本。

### Step 2 · 数据采集（脚本完成）

进入 `skills/deep-analysis/scripts/` 目录，调用 `stage1()` 采集 22 维数据 + 机构建模 + 规则引擎骨架分：

```bash
cd <repo_root>/skills/deep-analysis/scripts
python -c "from run_real_test import stage1; stage1('<ticker>')"
```

> 💡 deep 档**不要**用 `python run.py <ticker> --depth deep` 一把跑完（那是纯规则输出）。正确的做法是先 `stage1()` 采集 → 你介入 role-play → 再 `stage2()` 出报告。

### Step 3 · 你来分析（全量路径必走，不能跳过）

<HARD-GATE>
Do NOT proceed to report generation until you have:
1. READ the panel.json skeleton scores
2. ANALYZED each investor group from their perspective
3. UPDATED panel.json with your judgments
4. WRITTEN agent_analysis.json with dim_commentary + panel_insights + overrides
5. SET agent_reviewed: true in agent_analysis.json
</HARD-GATE>

### ⛔ Step 3.0 · Playwright 兜底前置检查（v2.13.5 必走）

Stage 1 跑完后 · 开始 role-play **之前**：

```python
import json, os
from pathlib import Path

# 1. 读网络 profile · 了解能抓哪些源
net_path = Path(".cache/_global/network_profile.json")
if net_path.exists():
    net = json.loads(net_path.read_text(encoding="utf-8"))
    print(f"网络: {net['recommendation']}")  # 比如"国内通 · 境外受限"

# 2. 读自查 issues 找数据不足的维度
issues_path = Path(f".cache/{ticker}/_review_issues.json")
if issues_path.exists():
    issues = json.loads(issues_path.read_text(encoding="utf-8"))
    low_q = [
        i["dim"] for i in issues.get("issues", [])
        if i.get("category") == "data" and i.get("severity") in ("critical", "warning")
    ]

# 3. 如果 low_q 非空 · 主动强制跑一次 Playwright 兜底
if low_q:
    os.environ["UZI_PLAYWRIGHT_FORCE"] = "1"
    from lib.playwright_fallback import autofill_via_playwright
    summary = autofill_via_playwright(raw, ticker)
    # summary.succeeded > 0 → 某些维度已被 Playwright 补齐 · 继续 role-play 时这些维度有真实数据了
```

**为什么这个 HARD-GATE**：v2.13.5 之前 agent 经常看到 `data.growth = "—"` 就在
commentary 里写 "增速待补充"，但脚本其实可以用 Playwright 从百度/东财 F10/雪球
抓到数据 · agent 没主动调就浪费了。

Playwright 也抓不到的维度 · 再用 WebSearch / mx_api / 常识补（并标注"基于公开信息推断"）。

### Step 3.1 你来做评委 role-play

**3a. 读取 `.cache/{ticker}/panel.json`**

看 66 人各自打了多少分，特别关注 Top 5 Bull 和 Top 5 Bear。

**3b. 逐组分析 66 评委**

对每组投资者，站在他们的角度思考这只票：

| 组 | 关注点 |
|---|---|
| 价值派（巴菲特/格雷厄姆/芒格） | ROE 够不够？护城河深不深？有安全边际吗？ |
| 成长派（林奇/木头姐/欧奈尔） | 增速够不够？赛道有颠覆性吗？PEG 合理吗？ |
| 宏观派（索罗斯/达里奥） | 利率环境？行业在周期什么位置？ |
| 技术派（利弗莫尔/米内尔维尼） | Stage 几？均线排列？成交量？ |
| 中国价投（段永平/张坤/冯柳） | 好生意吗？管理层本分吗？有认知差吗？ |
| 游资（赵老哥/章盟主） | 龙虎榜？板块热度？适合短线吗？ |
| 量化（西蒙斯） | 动量/价值/质量因子打分 |

**每个人给出**：signal（bullish/bearish/neutral/skip）、score（0-100）、headline（引用具体数字）、reasoning（2-3 句话）

你可以覆盖规则引擎的机械得分——你是在模拟这个人的判断。

**3c. 把分析结果更新到 panel.json**

**3d. 写 `agent_analysis.json`（闭环关键！）**

写入 `.cache/{ticker}/agent_analysis.json`，包含：
```json
{
  "agent_reviewed": true,
  "analysis_input_hash": "从 _agent_review_context.json 原样复制",
  "dim_commentary": { "0_basic": "你的定性评语", ... },
  "panel_insights": "整体评委观察",
  "great_divide_override": {
    "punchline": "一句能传播的冲突金句",
    "bull_say_rounds": ["第1轮多方说", "第2轮", "第3轮"],
    "bear_say_rounds": ["第1轮空方说", "第2轮", "第3轮"]
  },
  "narrative_override": {
    "core_conclusion": "综合结论",
    "risks": ["风险1", "风险2", ...],
    "buy_zones": { "value": {...}, "growth": {...}, "technical": {...}, "youzi": {...} }
  }
}
```

**stage2() 会自动读取并合并。** 你写的字段优先级高于脚本生成的 stub。

### Step 4 · 生成报告（脚本完成）

调用 `stage2()` 读取你更新后的 panel.json + agent_analysis.json，生成综合研判 + HTML 报告。

### Step 5 · 向用户汇报

告诉用户：
1. 综合评分 + 定调（值得重仓 / 可以蹲 / 观望 / 谨慎 / 回避）
2. 66 评委投票分布
3. **你自己分析的** Top 3 看多理由 + Top 3 看空理由
4. DCF 内在价值 vs 当前价
5. 杀猪盘等级
6. 报告路径（或 `--remote` 公网链接）

## 快速模式

用户说"快速分析"或"不用详细"→ 直接用 `run.py` 一把跑完，不做 agent 分析。快但粗糙。

## 远程模式

用户不在电脑前 → 用 `--remote` 参数，自动生成 Cloudflare 公网链接。

## 平台专属安装指南

| 平台 | 文档 |
|---|---|
| Codex | `.codex/INSTALL.md` |
| OpenCode | `.opencode/INSTALL.md` |
| Cursor | `.cursor-plugin/plugin.json` |
| Gemini | `GEMINI.md` |
| Claude Code | `.claude-plugin/plugin.json` |

## 🌐 网络受限环境（重要 · v2.4 新增）

UZI-Skill 既可能在**中国大陆**运行，也可能在 **Codex / 海外云容器**里运行，
两类环境的网络瓶颈不同，agent 遇到错误时要按情况切换。

### 场景 A · 大陆网络 / 校园 / 公司代理

**症状**：`pip install` 超时、SSL handshake 失败、`pypi.org` 连不上。

**处理**：按顺序尝试国内 pip 镜像（`run.py` 和 `setup.sh` 已经会自动 fallback，
但在 agent 环境你可能要手动指定）：

```bash
# 清华（推荐）
pip install -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn

# 阿里云（兜底）
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 中科大
pip install -r requirements.txt -i https://pypi.mirrors.ustc.edu.cn/simple/
```

数据源通常都通（akshare / xueqiu / eastmoney），个别被反爬的子域（如
`push2.eastmoney.com`）可能 Empty reply — **设置 `MX_APIKEY` 启用东财
妙想官方 API** 作为主数据源，见 `.env.example`。

### 场景 B · Codex / 海外 agent 容器

**症状**：`pip install` 很快，但跑分析时 `akshare` 报 timeout、
`push2.eastmoney.com` 不通、`cninfo.com.cn` DNS 失败。

**处理**：国内数据源从海外访问有时反被 GFW 限制。按以下顺序尝试：

1. **启用 MX_APIKEY**（最稳）— 妙想 API 走境内外都可达的 `mkapi2.dfcfs.com`
2. `yfinance` 兜底美股/港股
3. `WebSearch` + `Chrome/Playwright MCP` 打开以下备用入口抓 HTML：
   - 雪球：`https://xueqiu.com/S/{code}`（走 CDN，境外可访问）
   - 腾讯财经：`https://stockapp.finance.qq.com/mstats/`
   - 同花顺（F10 页）：`https://stockpage.10jqka.com.cn/{code}/`

### 场景 C · pip 和数据源都不通（双失败）

agent 应该：
1. 明确告诉用户："当前网络环境无法访问 pypi 和东财，建议切换到中国大陆 IP 或配置 MX_APIKEY"
2. 不要尝试用未验证的 VPN / 代理，不要绕过用户网络策略
3. 保留 `_data_gaps.json` + `_resolve_error.json`，下次网络恢复后可以直接 `stage2()` 生成报告

### 环境侦测快速命令

agent 在不确定环境时，可先跑这几条探测：

```bash
# pypi 连通性
curl -sS --max-time 5 -o /dev/null -w "pypi: %{http_code}\n" https://pypi.org/simple/
# 国内镜像连通性
curl -sS --max-time 5 -o /dev/null -w "tuna: %{http_code}\n" https://pypi.tuna.tsinghua.edu.cn/simple/
# 东财 push2（最常被挡）
curl -sS --max-time 5 -o /dev/null -w "push2: %{http_code}\n" https://push2.eastmoney.com/api/qt/stock/get
# 东财其他域
curl -sS --max-time 5 -o /dev/null -w "quote-em: %{http_code}\n" https://quote.eastmoney.com/
curl -sS --max-time 5 -o /dev/null -w "xueqiu: %{http_code}\n" https://xueqiu.com/
# 妙想 API
curl -sS --max-time 5 -o /dev/null -w "mx: %{http_code}\n" https://mkapi2.dfcfs.com/
```

根据哪些通/哪些不通，决定走哪个数据链。

## 📚 数据源速查表（v2.5 新增）

完整源清单在 `lib/data_source_registry.py`（40+ 源 · 3 tier）。常见 dim 推荐路径如下，
agent 选择源时按"主源 → 备源 → 浏览器源"顺序，failed 自动 fallthrough：

| Dim | A 股 主源 | A 股 备源 | A 股 浏览器源 | H 股主源 |
|---|---|---|---|---|
| 0_basic | xq_api (akshare) | mx_api / em_quote | xueqiu_f10 | hk_data_sources combined (XQ + EM profile + EM valuation) |
| 2_kline | em_data + akshare | baostock / tencent_qt | — | akshare hk_hist |
| 4_peers | akshare board_industry | em_data | iwencai / ths_f10 | hk_valuation_comparison_em (rank-only) + AASTOCKS (Playwright) |
| 6_research | em_data + cninfo | hexun / stockstar | xueqiu_f10 | (HK 限) yicai / cls |
| 12_capital_flow | em_data 北向 + akshare | — | yuncaijing | hk_security_profile (港股通标记) + AASTOCKS Playwright |
| 13_policy | gov_cn + cninfo | csrc / miit / ndrc | — | (同 A) + cls 7x24 + wallstreetcn |
| 15_events | cninfo + em_data | xq_api / cls / yicai | xueqiu_f10 | hkexnews + AASTOCKS Playwright |
| 16_lhb | akshare lhb + em_data | — | yuncaijing | (HK 无 LHB 概念，看南北向替代) |
| 17_sentiment | xq_api / ddgs | wallstreetcn | xueqiu_f10 | futu (Playwright) / xq_api |

**用法（在 sub-agent prompt 里）**：
```python
from lib.data_source_registry import http_sources_for, playwright_sources_for, by_dim

# Tier-1 HTTP 源，按 health 排序
sources = http_sources_for("4_peers", "A")
for s in sources:
    print(s.id, s.base_url, s.health, s.notes)

# 当 HTTP 全失败时，agent 启动 Playwright 用 tier-2 源：
browser_sources = playwright_sources_for("4_peers", "A")
```

**港股增强（v2.5 新加）**：
- `lib/hk_data_sources.py` 包装了之前未用到的 50+ akshare HK 函数
- `_fetch_basic_hk` 现在能拿到 industry / PE / PB / 市值 / 排名 / 公司介绍
- `fetch_peers.py` HK 分支返回 rank-in-HK-universe（具体同行 list 走 AASTOCKS Playwright）
- `fetch_capital_flow.py` HK 分支返回港股通资格 + 30 日市值变化
- `fetch_events.py` HK 分支抓 HKEXNews + 中文 web search 兜底

## ⚙️ v2.6 论坛 bug 修复速查（重要 · 影响 agent 行为）

| 论坛 bug | 修了什么 | agent 仍要做什么 |
|---|---|---|
| 失败卡死 | per-fetcher 90s timeout | 不要重试 timeout 维度，让 _data_gaps.json 触发恢复 |
| 中断不能续 | `--resume` 默认开 | 第二次跑同股 agent 应直接调 stage2 (raw_data 已有) |
| 非 Claude 评委对齐错位 | schema validator 写 `_agent_analysis_errors.json` | 跑完 stage2 看 console 是否有 🔴 错误，按 `_agent_analysis_errors.json` suggestion 改 |
| 编造事实（药明康德↔Apple） | HARD-GATE-FACTCHECK | 每条 commentary cite raw_data 出处，不确定的不要肯定语气 |
| Codex 兼容差 | run.py 自动 Codex 检测 + mini_racer 锁 | Codex 环境必设 `MX_APIKEY`，不要 `--no-resume` |
| Claude plugin 不能执行 | hooks.json 直调 session-start | 装完跑 `chmod +x hooks/session-start` |

## 注意

- A 股：`600519.SH` / `002273.SZ` / `贵州茅台`
- 港股：`00700.HK`
- 美股：`AAPL`
- 不需要 API key（但**建议设置 `MX_APIKEY`** 提高稳定性，特别是 Codex/海外环境）
- v2.6 默认 `--resume` · 强制重抓加 `--no-resume`
