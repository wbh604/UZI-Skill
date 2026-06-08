<div align="center">

# 游资（UZI）Skills

*"51 个投资大佬帮你看盘，巴菲特和赵老哥终于坐在了同一张桌子上。"*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://python.org)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.com/product/claude-code)
[![Dimensions](https://img.shields.io/badge/Dimensions-22-brightgreen)]()
[![Investors](https://img.shields.io/badge/Investors-51-orange)]()
[![Methods](https://img.shields.io/badge/Institutional%20Methods-17-red)]()
[![Self-Review](https://img.shields.io/badge/Self--Review-13%20checks-blueviolet)](skills/deep-analysis/scripts/lib/self_review.py)

A 股 / 港股 / 美股 · 个股深度分析引擎 · **v3.8.0 Tier-1 五方法 + Serenity 严谨化（8 罚分 + 证据阶梯 + 供应链分层）+ DuPont/KDJ/OBV/Williams · v3.7.1 首页补 Serenity 介绍 + `--school H/I` · v3.7.0 13 位新晋科技大佬入团 (52→65 评委)**

[安装](#安装) · [用法](#用法) · [三档深度](#-三档思考深度v2103-新增) · [Hermes 🆕](INSTALL-HERMES.md) · [评审团](#-65-位评审团) · [Serenity 🆕](#-i-组--serenity--ai-卡位瓶颈猎手) · [机构方法](#-17-种机构级方法) · [自查 gate](#-机械级自查-gatev29-起) · [报告截图](#-报告长什么样) · [FAQ](#-faq) · [入群交流测试](#-测试交流群) · [Contributors](CONTRIBUTORS.md)

**中文** | [English](README_EN.md)

</div>

---

## 🚀 30 秒上手

**任何 agent 里丢一句话 · 装好就能用**。详细装法见 [安装](#安装)。

| 你用的 agent | 直接丢这句 |
|---|---|
| **Claude Code** | `/plugin marketplace add wbh604/UZI-Skill` 然后 `/plugin install stock-deep-analyzer@uzi-skill` |
| **Codex / OpenAI CLI** | "按 https://raw.githubusercontent.com/wbh604/UZI-Skill/main/.codex/INSTALL.md 装 UZI-Skill，分析 600519" |
| **Cursor** | `/add-plugin stock-deep-analyzer` |
| **Gemini CLI** | `gemini extensions install https://github.com/wbh604/UZI-Skill` |
| **Hermes** | ⚠️ `hermes skills install` 当前被 [Skills Guard 误判](https://github.com/NousResearch/hermes-agent/issues/1006) · 用一键脚本绕过：`curl -fsSL https://raw.githubusercontent.com/wbh604/UZI-Skill/main/install-hermes.sh \| bash` · 详见 [INSTALL-HERMES.md](INSTALL-HERMES.md) |
| **OpenClaw / 龙虾** | "装 https://github.com/wbh604/UZI-Skill 这个股票分析技能" |
| **CLI 直用** | `git clone https://github.com/wbh604/UZI-Skill.git && cd UZI-Skill && pip install -r requirements.txt && python run.py 贵州茅台` |

装好后最常用 4 条命令（任何 agent 里直接说）：

```
/stock-deep-analyzer:analyze-stock 贵州茅台    ← 完整 22 维 × 65 评委分析（5-8min）
/stock-deep-analyzer:quick-scan 002217         ← 30 秒速判
/stock-deep-analyzer:scan-trap 002217          ← 杀猪盘排查
/stock-deep-analyzer:dcf 600519                ← DCF 估值专项
```

> 💡 **当前最新稳定版 v3.3.2**：
> - **v3.3.2** · 🆕 **GitHub issue #50 + #51 hotfix**（社区报告驱动）· #50 institutional 漏 import svg_sparkline 致 Stage 2 NameError · #51 XueQiu cubes_search.json endpoint 下线 → 改 query/v1/search/cube/stock.json (致谢 @chenxiang-bj / @bilieebiliee1-design / @Kylin824)
> - **v3.3.1** · Hermes 兼容回归修复（v3.x 重构期 main 缺 hermes 适配 · 群友报错根因）· main 分支现在直接支持 `hermes skills install`
> - **v3.3.0** · 分支整合 · segmental 渲染层 cherry-pick 到 v3.2 架构 · 22 个 stale 分支清理（仅保留 main + hermes-compat）
> - **v3.2.0** · `assemble_report.py` 2964 → 587 行（-80%）· 拆 5 个 `lib/report/*.py` 子模块
> - **v3.1.0** · `run_real_test.py` 2105 → 735 行（-65%）· 1228 行纯函数迁到 `lib/pipeline/score_fns.py`
> - **v3.0.0** · pipeline 架构默认启用（`python run.py <ticker>` 默认走新路径 · `UZI_LEGACY=1` 回老路径）
>
> 两个巨文件合计 **5069 → 1322 行 (-74%)** · 332 tests 全过 · 真机 e2e 002217 resume 10s 出报告 · v2.x 所有 API 100% 向后兼容.
>
> v2.15 系列继续保留：capital_flow universe cache（100x 加速）· school_scores 按流派打分 · 混合公式 + 极化拉伸.
>
> **Hermes 用户旧版残留可能报错** · 重装一次即解决（`hermes skills uninstall` 然后 install 4 个 skill）· 详见 [INSTALL-HERMES.md](INSTALL-HERMES.md).

---


## 💬 没有群！虽然我也不知道为什么交流群也没涉及什么东西会被封号。。。

拉群会被封，有想法的直接加我吧，只针对插件本身或者其他有趣的项目和量化，不聊个股

<p align="center">
  <img src="docs/screenshots/8501bb4280cc56c809c0a19619e49c82.jpg" width="300" alt="拉群会被封，有想法的直接加我吧，只针对插件本身或者其他有趣的项目和量化，不聊个股" />
</p>

> 添加人过多，请备注好事宜，我才知道出什么问题了。。

---

---
## 鸣谢
学AI，上L站！
感谢 [Linux.do](https://linux.do/) 社区支持。

## 这是啥

一句话：输入一只股票，Claude 变成你的私人分析师，跑完 22 个维度的数据、调 17 种华尔街分析模型、让 51 个投资风格完全不同的大佬各自打分，最后吐出一份 600KB 的 Bloomberg 风格报告。

```
/stock-deep-analyzer:analyze-stock 国盾量子
```

5-8 分钟后你会得到：
- **一份 HTML 报告** — 可以直接用浏览器打开，自包含，离线也能看
- **一张朋友圈竖图** — 1080×1920，直接发
- **一张微信群战报** — 1920×1080
- **一段话摘要** — 复制粘贴就能发群里

## 为什么做这个

之前看一只票的流程：东方财富翻基本面 → 同花顺看 K 线 → 雪球刷大 V 说了啥 → 研报系统找卖方观点 → Excel 算个 DCF → 结果买进去还是亏。

这些活儿本质上就是"搜集信息 → 多角度分析 → 给个结论"，让 AI 全干了不行吗？

市面上看了一圈，要么是输出三段废话的 GPT wrapper，要么是用不起的机构终端。Anthropic 出了个 [financial-services-plugins](https://github.com/anthropics/financial-services-plugins)，方法论很好（DCF / Comps / LBO 那套），但完全是美股视角 + 全要付费数据源。

所以自己搓了一个。**全免费数据源，零 API key，A 股直接能跑。**

---

## 安装

不管你用什么 agent，**都是丢一句话过去就行**：

### Claude Code

```
/plugin marketplace add wbh604/UZI-Skill
/plugin install stock-deep-analyzer@uzi-skill
```

装好后说 `/stock-deep-analyzer:analyze-stock 贵州茅台`。

> ⚠️ **必须带 `stock-deep-analyzer:` 命名空间前缀**
>
> Claude Code 装 plugin 后，所有 skill/command 都以 `stock-deep-analyzer:` 开头。
> 部分环境下短名（`/analyze-stock`）不会被自动解析——稳妥起见请一律用全名：
>
> - `/stock-deep-analyzer:analyze-stock <ticker>`
> - `/stock-deep-analyzer:quick-scan <ticker>`
> - `/stock-deep-analyzer:scan-trap <ticker>`
> - `/stock-deep-analyzer:dcf <ticker>`
> - `/stock-deep-analyzer:ic-memo <ticker>`
> - `/stock-deep-analyzer:investor-panel <ticker>`
> - `/stock-deep-analyzer:trap-detector <ticker>`
> - `/stock-deep-analyzer:deep-analysis <ticker>`
> - 等全部 14 条
>
> Cursor / Gemini CLI / Codex 同理：**一律用 `/stock-deep-analyzer:<cmd>` 全名**，
> 避免短名解析失败。

### Codex

直接对 Codex 说：

> 请按照 https://raw.githubusercontent.com/wbh604/UZI-Skill/main/.codex/INSTALL.md 的指引安装 UZI-Skill，然后帮我深度分析 贵州茅台。

### OpenClaw / 龙虾

对龙虾说：

> 帮我安装 https://github.com/wbh604/UZI-Skill 这个股票分析技能，装好后分析 贵州茅台。

### Cursor

```
/add-plugin stock-deep-analyzer
```

然后说"分析 贵州茅台"。

### Gemini CLI

```bash
gemini extensions install https://github.com/wbh604/UZI-Skill
```

### OpenCode

对 OpenCode 说：

> 请按照 https://raw.githubusercontent.com/wbh604/UZI-Skill/main/.opencode/INSTALL.md 安装并分析 贵州茅台。

### Windsurf / Devin / 其他 Agent

丢这句话进去：

> 克隆 https://github.com/wbh604/UZI-Skill ，读 AGENTS.md 了解怎么用，帮我深度分析 贵州茅台。

### 📱 不在电脑前？

对任何 agent 说：

> 分析 贵州茅台，用远程模式，生成一个公网链接让我手机能看。

agent 会自动用 `--remote` 启动 Cloudflare Tunnel，给你一个 `https://xxx.trycloudflare.com` 链接。

---

## 用法

### 完整深度分析（5-8 分钟）

```
/stock-deep-analyzer:analyze-stock 水晶光电
/stock-deep-analyzer:analyze-stock 002273
/stock-deep-analyzer:analyze-stock 00700.HK
/stock-deep-analyzer:analyze-stock AAPL
```

### 专项命令

> 都要加 `/stock-deep-analyzer:` 前缀才保证执行得通。

| 命令 | 干嘛的 |
|---|---|
| `/stock-deep-analyzer:dcf 600519` | DCF 估值 · WACC + 5×5 敏感性表 |
| `/stock-deep-analyzer:comps 002273` | 同行对标 · PE/PB 分位分析 |
| `/stock-deep-analyzer:lbo 600519` | LBO 测试 · PE 买方能赚多少 IRR |
| `/stock-deep-analyzer:initiate 002273` | 机构首次覆盖报告 · JPM/GS 格式 |
| `/stock-deep-analyzer:ic-memo 002273` | 投委会备忘录 · 三情景回报 |
| `/stock-deep-analyzer:earnings 002273` | 财报解读 · beat/miss 检测 |
| `/stock-deep-analyzer:catalysts 002273` | 催化剂日历 · 未来 60 天 |
| `/stock-deep-analyzer:thesis 002273` | 投资逻辑追踪 · 5 支柱监控 |
| `/stock-deep-analyzer:screen 002273` | 5 套量化筛选 · value/growth/quality |
| `/stock-deep-analyzer:dd 002273` | 尽调清单 · 5 工作流 21 项 |
| `/stock-deep-analyzer:quick-scan 002273` | 30 秒速判 |
| `/stock-deep-analyzer:panel-only 600519` | 只看 65 评委投票 |
| `/stock-deep-analyzer:scan-trap 002273` | 杀猪盘排查 |
| `/stock-deep-analyzer:segmental-model 300308` | 🆕 分业务收入 bottom-up 建模 · 3 情景 × 3 年 projection · 对 DCF 反向校验 |

---

## 🎯 评分校准（v2.11）

用户反馈"茅台 47 分"、"没超过 65 分"—— 诊断发现两处公式偏严苛，v2.11 校准：

| 改动 | 旧 (v2.9.1) | 新 (v2.11) | 影响 |
|---|---|---|---|
| **verdict 阈值** | 85/70/55/40 | **80/65/50/35** | 从未有股能 ≥85（"值得重仓"档空设），下调 5 分让白马/真强股进"可以蹲一蹲"档 |
| **consensus neutral 权重** | 0.5（半权） | **0.6** | 51 评委里价值派+游资 35 人偏保守，neutral 权重 0.5 让白马 consensus 仅 37，0.6 更贴近"不坑但不是心头好"的真实语义 |

公式（未变）：`overall = fund_score × 0.6 + consensus × 0.4`

典型白马（如茅台）预期：
- v2.9.1：`fund=62 consensus=45 → overall 55 → 观望优先`
- v2.11：`fund=62 consensus=50 → overall 57 → 观望优先`（但更接近"可以蹲一蹲"边界，白马行情启动时容易进 65）

两档合计影响 ~5-8 分。**真正的坑仍会 < 35 → 回避**，分数辨识度不降反升。

诊断字段 `panel.json::consensus_formula.version = "v2.11 · (bullish + 0.6*neutral) / active"` 可审计。

回归测试：`tests/test_v2_11_scoring_calibration.py` 8 个用例。

完整校准记录见 [BUGS-LOG.md v2.11.0 章节](docs/BUGS-LOG.md#v2110-2026-04-18--评分校准--用户反馈驱动)。

---

## 🎚️ 三档思考深度（v2.10.3 新增）

给用户自己选择分析力度——快想 / 正常 / 深挖：

```bash
python run.py 600519 --depth lite     # ⚡ 速判模式（1-2 分钟）
python run.py 600519                   # 📊 标准分析（5-8 分钟）· 默认
python run.py 600519 --depth deep      # 🔬 深度研究（15-20 分钟）
```

或通过环境变量：

```bash
export UZI_DEPTH=lite       # 或 medium / deep
python run.py 600519
```

### 三档差异一览

| 维度 | ⚡ **lite** 速判 | 📊 **medium** 标准 | 🔬 **deep** 机构级 |
|---|---|---|---|
| **预计耗时** | 1-2 分钟 | 5-8 分钟 | 15-20 分钟 |
| **fetcher 维度** | 核心 7 维 | 全 22 维 | 全 22 维 + 强化 fallback |
| **评委数量** | 10 位代表 | 65 位完整 | 65 位 + **Bull-Bear 结构化辩论** |
| **机构方法** | 只 DCF | 全 17 种 | 全 17 种 + **Segmental Build-Up** |
| **ddgs 定性查询** | **全 skip**（省 token）| 按需 · 预算 30 次 | 跑满 · 预算 60 次 |
| **fund_holders** | Top 5 完整业绩 | Top 20 完整 + 其余清单 | Top 100 完整 |
| **自查 gate** | critical block | critical block · warning 可 ack | 两级都 block |
| **Playwright 兜底**（v2.13.1） | ❌ 完全禁用 | opt-in · `UZI_PLAYWRIGHT_ENABLE=1` · **6 维**（4_peers/8_materials/15_events/17_sentiment/7_industry/14_moat） | ✅ 默认启用 · **10 维**（medium 6 + 3_macro/13_policy/18_trap/19_contests）· 首次 y/n 交互装 Chromium |
| **Token 消耗（Codex）** | 最省 | 中等 | 最大 |
| **适用场景** | 随手看 / 老板临时问 / 预判 ETF 成分股 | 日常深度分析 · 写研报 | 投委会备忘录 · 建仓前深挖 |

### 自动降级策略

- **第一次安装** / `.cache/_global` 空时 → 自动切 lite（省首次冷启动时间）
- **网络预检 3+ 域不通** → 自动切 lite（避免卡死）
- 手动 `--depth` 始终覆盖自动判定

### 实战选择

| 问题 | 推荐档位 |
|---|---|
| "帮我看看这只票能不能买" | `medium`（默认） |
| "15 分钟内给我个结论" | `lite` |
| "老板明天投委会要看" | `deep`（含 Bull-Bear 辩论 + bottom-up segmental） |
| "ETF 代码输进去了（系统会提示选成分股）" | `lite`（成分股快速预判）|
| "Codex 环境 / 首次安装" | 不用管 · 自动 lite |

### 命令映射（隐式档位）

| 命令 | 隐式档位 |
|---|---|
| `/stock-deep-analyzer:quick-scan 600519` | lite |
| `/stock-deep-analyzer:panel-only 600519` | lite |
| `/stock-deep-analyzer:analyze-stock 600519` | medium（默认）|
| `/stock-deep-analyzer:ic-memo 600519` | deep |
| `/stock-deep-analyzer:initiate 600519` | deep |

---

## 🎭 65 位评审团

不是模板话术。每个人有自己的**量化规则集**（共 236 条），给出的建议必须引用具体命中了哪条。
v3.7.0 起新增 **13 位新晋科技大佬** + 独立的 **I 组 Serenity（AI 卡位/瓶颈猎手）**，覆盖 9 大流派：

| 组 | 风格 | 人数 | 代表人物 |
|---|---|---|---|
| A | 经典价值 | 6 | 巴菲特 · 格雷厄姆 · 芒格 · 费雪 · 邓普顿 · 卡拉曼 |
| B | 成长投资 | 9 | 林奇 · 木头姐 · 蒂尔 · **Andreessen (a16z)** · **Gurley (Benchmark)** · **Naval** · **Gerstner (Altimeter)** · **Chamath** |
| C | 宏观对冲 | 7 | 索罗斯 · 达里奥 · 霍华德马克斯 · 德鲁肯米勒 · 罗伯逊 · **Burry（大空头）** · **Chanos（做空猎手）** |
| D | 技术趋势 | 4 | 利弗莫尔 · 米内尔维尼 · 达瓦斯 · 江恩 |
| E | 中国价投 | 7 | 段永平 · 张坤 · 朱少醒 · 谢治宇 · 冯柳 · 邓晓峰 · **张磊（高瓴）** |
| F | A 股游资 | 23 | 章盟主 · 赵老哥 · 炒股养家 · 佛山无影脚 · 北京炒家 · 鑫多多 … |
| G | 量化系统 | 4 | 西蒙斯 · 索普 · 大卫·肖 · **Asness (AQR)** |
| H | 科技领袖派 🆕 | 4 | **黄仁勋 (NVIDIA)** · **马斯克 (Tesla)** · **Sam Altman (OpenAI)** · **Saylor (MSTR)** |
| I | AI 卡位/瓶颈猎手 🆕 | 1 | **Serenity（@aleabitoreddit）** |

> v3.7.0（2026-06）新晋 13 人加粗。**H 组**是带着自家产业链视角的科技 CEO；**I 组 Serenity** 是单人特殊评委（见下）。

**举个例子**：

> **巴菲特** 给水晶光电打 62 分 · 中性
> "观望：护城河 27/40 可见；但 ROE 5 年最低 6.7%，达标率仅 0/5"
> ✅ 资产负债率 30% 保守 · ❌ ROE 5 年最低 6.7%

> **黄仁勋** 给某 CPO 光模块股打 100 分 · 看多
> "在 AI 算力链上 · 数据中心 Capex 直接受益 · 毛利率 ≥50% 定价权强——这是光速摩尔定律的受益方。"
> ✅ AI 算力需求强相关 · ✅ CUDA/生态绑定深

> **卡拉曼** 给水晶光电打 0 分 · 看空
> "看空核心：无 30% 安全边际"

---

## 🧠 I 组 · Serenity · AI 卡位/瓶颈猎手

> **重磅角色**：2026 年 X（推特）爆火的海外散户研究员 [@aleabitoreddit](https://x.com/aleabitoreddit)。
> 单独成组、单独评分——因为她的打法极度集中、极度逆共识，跟任何机构大佬都不一样。

### 她是谁

- 自述背景：**前 AI 研究科学家 · Nature 论文作者 · 前 RISC-V 基金会成员 · 半导体/光通信工程师**
- 二次元头像、匿名、不露脸、不卖课、不跟单，研究**全部免费公开**，X 粉丝 30 万+
- 成名战：提前约一年押中 InP 磷化铟衬底瓶颈股 **$AXTI（$12 → $70+，最高 $115–140）**，2026 Q1 被 IntelliEPI CEO 公开印证"InP 短缺是整个 AI 基建的瓶颈"

> ⚠️ 身份与收益均为**自述/媒体转述、未经第三方审计**，各来源数字互相矛盾。本项目仅蒸馏其**方法论**作为一个分析视角，不代表认可其真实战绩。详见 [`docs/serenity-research-dossier.md`](docs/serenity-research-dossier.md)（全网 20+ 来源逐条档案）。

### 她在 UZI-Skill 里的作用

把她的「**AI 产业链卡脖子/瓶颈点理论（Chokepoint Theory）**」做成一个可量化的评委——
**不买 AI 龙头**（英伟达这种已被充分定价的票），而是沿供应链往上游拆，找那个"全世界都绕不过去、又最容易供给见底"的二三线上游小盘，抢在市场定价前埋伏。

```
龙头被买爆 → 沿供应链往上拆 → 找最难替代的环节 → 找该环节里供给最紧的小盘 → 提前埋伏
```

**核心打分逻辑「卡位决定态度」**——不看估值便宜、不看成长快，只看一个变量：**这家公司的产品在当前 AI 浪潮里有没有卡住别人的脖子**。

| 判定 | 态度 |
|---|---|
| 卡住了（不可替代 + 供给瓶颈 + 没被定价） | 🟢 **看多 / 可能重仓** |
| 在 AI 链上但卡位不硬（能被替代 / 产能充足） | ⚖️ 中性 · 待验证 |
| 没卡到位 / 只是蹭概念 / 不在 AI 链 | 🔴 **直接 skip**（白酒、银行护城河满分也给 0 分） |

判一个环节是不是"卡位点"看三件事：① **难替代**（换供应商/材料/工艺要多久，越久越好 → `14_moat` 切换成本）② **供给紧**（产能跟不跟得上 AI 需求曲线，越跟不上越好 → `7_industry`）③ **没被定价**（市场还在用"周期股/老半导体/小众材料"旧叙事看它 → `5_chain` + `15_events`）。

### 怎么单独跑 Serenity 视角

```bash
python run.py 300394.SZ --school I       # 只看 Serenity 的"卡没卡位"判断
python run.py NVDA --school H             # 只看 H 组科技领袖派（黄仁勋/Musk/Altman/Saylor）
```

> 方法论六步法 + alpha 5 维详见 [`skills/deep-analysis/references/fin-methods/serenity-bottleneck.md`](skills/deep-analysis/references/fin-methods/serenity-bottleneck.md)；
> 语气库 + 评分规则见 [`skills/investor-panel/references/group-i-serenity.md`](skills/investor-panel/references/group-i-serenity.md)。

---

## 📐 17 种机构级方法

从 [anthropics/financial-services-plugins](https://github.com/anthropics/financial-services-plugins) 移植方法论，适配了 A 股参数（rf=2.5% / ERP=6% / 税率 25% / 终值 g=2.5%）：

**估值建模**
- DCF（WACC 拆解 + 两段 FCF + Gordon Growth 终值 + 5×5 敏感性热力图）
- Comps 同行对标（PE / PB / EV-EBITDA 分位 + 隐含目标价）
- 三表预测（5 年 IS / BS / CF 联动）
- Quick LBO（PE 基金视角 IRR 交叉校验）
- 并购增厚/摊薄模型

**研究工作流**
- 首次覆盖报告（JPM/GS/MS 格式 · 评级 + 目标价 + 论点 + 风险）
- 财报 beat/miss 解读
- 催化剂日历（真实事件提取 + 未来预排 + 影响分级）
- 投资逻辑追踪（5 支柱健康度）
- 晨报 · 量化筛选 · 行业综述

**深度决策**
- IC 投委会备忘录（8 章节 · Bull/Base/Bear 三情景）
- Porter 五力 + BCG 矩阵
- DD 尽调清单（5 工作流 21 项 · 自动标注完成状态）
- 单位经济学 · 价值创造计划 · 组合再平衡

---

## 📸 报告长什么样

> 以下截图全部来自水晶光电（002273.SZ）的真实分析结果。

### 综合评分 + 核心结论

<img src="docs/screenshots/hero-score.png" width="700" />

### 多空大分歧 · The Great Divide

费雪 100 分 vs 卡拉曼 96 分，三轮互喷，每轮引用具体数字。

<img src="docs/screenshots/great-divide.png" width="700" />

### 65 位评审团 · 审判席

每个人一盏灯——绿色看多、红色看空、灰色中性。

<img src="docs/screenshots/jury-seats.png" width="700" />

### 聊天室模式

评委们用自己的语言风格发言，引用命中的具体规则。

<img src="docs/screenshots/chat-room.png" width="700" />

### DCF 估值 · 5×5 敏感性热力图

WACC 6.96% · 内在价值 ¥20.73 · 安全边际 -28.6%，颜色从深绿（低估）到深红（高估）。

<img src="docs/screenshots/dcf-model.png" width="700" />

### IC 投委会备忘录 · 三情景回报

Bull ¥26.95 / Base ¥20.73 / Bear ¥14.51，每个情景有概率和假设。

<img src="docs/screenshots/ic-memo.png" width="700" />

### 22 维深度卡

每个维度有独立可视化——K 线蜡烛图 / PE Band / 雷达图 / 供应链流程图 / 温度计 / 环形图。

<img src="docs/screenshots/deep-scan.png" width="700" />

### 朋友圈竖图 · 一键分享

<img src="docs/screenshots/share-card.png" width="300" />

---

## 🔧 数据源

全部免费，零 API key：

| 数据 | 主源 | 备用 |
|---|---|---|
| 实时行情 / PE / 市值 | 东方财富 push2 | 雪球 → 腾讯 → 新浪 → 百度 |
| 财报历史 | akshare | 雪球 f10 |
| K 线 / 技术指标 | akshare | yfinance |
| 龙虎榜 / 北向 / 两融 | akshare | 东财 |
| 研报 / 公告 | 巨潮 cninfo + akshare | 同花顺 |
| 港股 | akshare hk | yfinance |
| 美股 | yfinance | akshare us |
| 宏观 / 政策 / 舆情 / 杀猪盘 | DuckDuckGo web search | — |
| **社交热榜**（v2.12 新增） | **微博 / 知乎 / 百度 / 抖音 / 头条 / B 站 · 各平台官方 JSON API** | 5min 文件缓存 · 单平台失败不影响其他 |

多层 fallback 链 — 一个源挂了自动切下一个。

### 📱 6 平台社交热榜（v2.12 新增）

散户情绪和杀猪盘题材经常先在抖音/小红书/微博发酵，DuckDuckGo 扫不到。v2.12 起 `17_sentiment` 维度自动查：

- **微博热搜** · 抓 `weibo.com/ajax/side/hotSearch` · 50 条实时热搜
- **知乎热榜** · 抓 `zhihu.com/api/v3/feed/topstory/hot-list-web` · 50 条
- **百度热搜** · 抓 `top.baidu.com/api/board` · 实时榜单
- **抖音热点** · 抓 `douyin.com/aweme/v1/web/hot/search/list/` · 搜索热点
- **头条热榜** · 抓 `toutiao.com/hot-event/hot-board/` · 热点事件
- **B 站热搜** · 抓 `s.search.bilibili.com/main/hotword` · 全站热搜

股票名（含简称，如"贵州茅台"→"贵州"/"茅台"）在热榜标题里命中 → 计入情绪热度 + 记录具体条目。

数据结构：synthesis 的 `17_sentiment.data.hot_trend_mentions`：
```json
{
  "stock_name": "贵州茅台",
  "platforms_ok": 6,
  "total_hits": 3,
  "by_platform_count": {"weibo": 2, "zhihu": 1, ...},
  "mentions": { "weibo": [{"rank":3, "title":"茅台 1499 回归", ...}], ... }
}
```

> 致谢：本模块设计参考了 [run-bigpig/jcp](https://github.com/run-bigpig/jcp) (韭菜盘 AI) 的 `hottrend` 服务实现。

### 🔑 可选：东方财富妙想 Skills API（v2.3 新增）

2026 年 `push2.eastmoney.com` 在大陆网络经常被反爬拦截。若设置
`MX_APIKEY`，UZI-Skill 会优先走官方 NLP API：

- **中文名纠错**："北部港湾" → 自动识别为 "北部湾港(000582.SZ)"
- **行情快照**：绕过 push2 直接拿到最新价/市值/PE/PB/行业

配置：
```bash
cp .env.example .env
# 编辑 .env 填入 MX_APIKEY（免费申领：https://dl.dfcfs.com/m/itc4）
```

无 key 时全部回退到 XueQiu/akshare 链，现有用户零感知。

### 🔓 需登录的数据源（v2.7.1 新增）

部分数据源 2026 年起加了登录鉴权，UZI-Skill 默认**不主动弹登录窗**（保持无人值守）。
用户可按需启用：

| 数据源 | 维度 | 启用方式 | 影响 |
|---|---|---|---|
| **XueQiu cubes_search.json** | `19_contests` 实盘比赛持仓 | `export UZI_XQ_LOGIN=1` 然后 `python -m lib.xueqiu_browser login`（一次性弹浏览器登录） | 不启用：报告 19_contests 显示"⚠️ XueQiu 需登录，0 cube"；启用后能看到雪球 50+ 个实盘组合持有本股 |

#### XueQiu 登录步骤

```bash
# 1. 启用环境变量（一次性，可加进 .zshrc）
export UZI_XQ_LOGIN=1

# 2. 一次性登录（首次跑会弹有头浏览器，登录后回到终端按回车）
python -m lib.xueqiu_browser login
# → 浏览器弹出，手动账密 / 微信扫码 / 短信登录
# → 登录成功后回终端按回车，cookie 持久化到 ~/.uzi-skill/playwright-xueqiu/

# 3. 后续跑分析自动复用登录态（cookie 通常有效 ≥ 30 天）
python run.py 贵州茅台 --no-browser
# 19_contests 维度会显示真实雪球组合数 + 收益率分布

# 4. 如果直接跑 run.py 想启用，加 flag
python run.py 贵州茅台 --enable-xueqiu-login
```

#### 跳过登录（默认行为）

不想登录？什么都不用做。XueQiu 维度会清晰标注 `⚠️ 需登录，0 cube`，
其他 21 个维度照常工作。

#### 状态查询
```bash
python -m lib.xueqiu_browser status
# 显示：profile dir / cookie 是否存在 / 是否启用
```

### 🚨 数据缺口怎么处理（v2.3）

若某些字段脚本拿不到（网络限制 / 新股 / 停牌），pipeline **不会塞默认值糊弄**：

1. 生成 `_data_gaps.json` 列出每个缺口的建议恢复动作（浏览器 / MX / WebSearch / 推导）
2. Agent 按 [HARD-GATE-DATAGAPS](skills/deep-analysis/SKILL.md) 逐条尝试补齐
3. 真的补不到 → 在 `agent_analysis.json` 里 `data_gap_acknowledged` 显式承认
4. HTML 报告顶部显示橙色 banner + 相关字段显示 "—" 并划线

这样你永远能分辨"这只股真的不适合买" vs "只是数据没拿到"。

### 🌐 网络受限环境（v2.4 新增）

UZI-Skill 在大陆和海外都能跑，但瓶颈不同，建议对号入座：

**大陆网络 · `pip install` 失败怎么办？**

`run.py` 和 `setup.sh` 会自动尝试国内镜像（清华 → 阿里云 → 中科大），
所以常见情况你什么都不用做。若要手动指定：

```bash
pip install -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn
```

**Codex / 海外 agent · 数据源访问慢怎么办？**

国内数据源（尤其 `push2.eastmoney.com`）从海外访问经常超时。**强烈建议
设置 `MX_APIKEY`**（免费申领 → https://dl.dfcfs.com/m/itc4），它走
`mkapi2.dfcfs.com` 境内外都通，同时天然具备中文名纠错能力。

```bash
cp .env.example .env
# 编辑 .env 填入 MX_APIKEY
python run.py 贵州茅台
```

**双端都不通**：agent 应保留 `_data_gaps.json` / `_resolve_error.json`，
等网络恢复后直接跑 `stage2()` 可以复用已采集数据，不用从头来过。

详见 [AGENTS.md · 网络受限环境](AGENTS.md) 的场景 A/B/C 速查。

---

## 📁 项目结构（v3.2.0 架构）

```
UZI-Skill/
├── run.py                              # ✅ 用户入口 (python run.py <ticker>)
├── AGENTS.md / CLAUDE.md / CODEX.md    # agent 指令 (v3.2 新增 CODEX.md)
├── GEMINI.md                           # Gemini CLI 指引
├── RELEASE-NOTES.md                    # 完整版本日志
├── docs/BUGS-LOG.md                    # bug 登记 + 防回归清单
├── .claude-plugin/plugin.json          # Claude Code manifest
├── .cursor-plugin/plugin.json          # Cursor manifest
├── gemini-extension.json               # Gemini manifest
├── commands/                           # 14 个 slash commands
├── personas/                           # 51 个 YAML persona (v2.15.0)
├── skills/
│   ├── deep-analysis/                  # ★ 主 skill (股票分析)
│   │   ├── SKILL.md
│   │   ├── references/                 # 方法论文档
│   │   ├── assets/                     # HTML 模板 + 51 头像 svg
│   │   └── scripts/                    # ← 所有 Python 业务代码
│   │       ├── run_real_test.py        # legacy stage1/stage2 (v3.1 瘦身 735 行)
│   │       ├── assemble_report.py      # HTML shell (v3.2 瘦身 587 行)
│   │       ├── fetch_*.py              # 22 fetcher · 也是独立 CLI
│   │       ├── compute_deep_methods.py # 机构建模
│   │       ├── tests/                  # 332 pytest
│   │       └── lib/
│   │           ├── pipeline/           # 🆕 v3.0 管道式架构（默认路径）
│   │           │   ├── run.py          # run_pipeline 编排入口
│   │           │   ├── collect.py      # 并发 collector (22 adapter)
│   │           │   ├── score.py        # scoring 段（调 rrt 纯函数）
│   │           │   ├── synthesize.py   # stage2 薄 wrapper
│   │           │   ├── score_fns.py    # 🆕 v3.1 · 1228 行纯函数
│   │           │   ├── preflight_helpers.py  # 🆕 v3.1 · 网络/ticker preflight
│   │           │   ├── fetchers/registry.py  # 22 adapter 工厂
│   │           │   └── renderer/       # 21 个 renderer stub
│   │           ├── report/             # 🆕 v3.2 · assemble_report 拆分
│   │           │   ├── svg_primitives.py     # 19 svg_* + COLOR_*
│   │           │   ├── dim_viz.py            # 19 _viz_xxx + DIM_VIZ_RENDERERS
│   │           │   ├── institutional.py      # DCF/LBO/IC/catalyst/competitive
│   │           │   ├── panel_cards.py        # 65 评委 panel
│   │           │   └── special_cards.py      # fund/insights/school_scores
│   │           ├── investor_criteria.py      # 51 人 × 180 规则
│   │           ├── investor_evaluator.py     # 规则引擎
│   │           ├── stock_features.py         # 108 标准化特征
│   │           ├── playwright_fallback.py    # v2.13 兜底
│   │           ├── self_review.py            # 机械自查 13 check
│   │           └── ...                       # 其他 lib 模块
│   ├── investor-panel/                 # 评审团 skill
│   ├── lhb-analyzer/                   # 龙虎榜 skill
│   └── trap-detector/                  # 杀猪盘 skill
├── requirements.txt
└── LICENSE
```

**v3.2 重构分层亮点**：

| 层 | 文件 | 职责 |
|---|---|---|
| 入口 | `run.py` | CLI 主入口 · `UZI_LEGACY=1` 回退老路径 |
| 管道 | `lib/pipeline/*` | v3.0 主干 · collect / score / synthesize |
| 纯函数 | `lib/pipeline/score_fns.py` | v3.1 · score_dimensions / generate_panel / generate_synthesis |
| 渲染 | `lib/report/*` | v3.2 · 5 个子模块 · svg / viz / inst / panel / special |
| Legacy | `run_real_test.py` + `assemble_report.py` | v2.x 向后兼容层 · re-export 所有迁移函数 |

---

## 🧠 设计理念

**Agent 驱动分析，脚本只是工具。**

整个流程分两段——中间 agent 必须介入，**最后必须自查**（v2.9 起机械强制）：

```
Stage 1 (脚本)          → 数据采集 + 模型计算 + 规则引擎骨架分
        ⏸️ Agent 介入   → 读数据 → role-play 65 评委 → 写判断 → 审查假设
Stage 2 (脚本)          → 综合研判 + 自动跑 13 条自查 → 报告生成
                         ↑ v2.9 核心：critical 不过 → 拒绝出 HTML
```

**51 个评委不是跑公式出分数**——agent 要真正站在每个人的角度思考：

- 巴菲特分析苹果 → agent 知道这是伯克希尔第一大持仓 → override 看多
- 赵老哥分析美股 → agent 知道游资不做美股 → skip
- 木头姐分析白酒 → agent 知道她只看颠覆创新 → "不在平台里"
- 格雷厄姆看到 PE 33 → 不需要复杂推理 → 看空

每个判断都可以覆盖规则引擎的机械得分，但必须给出理由。

**三层评估**：真实持仓 → 行业亲和度 → 量化规则。真金白银比任何公式都有说服力。

### 🛡 机械级自查 gate（v2.9 起）

过往 `HARD-GATE-FINAL-CHECK` 是"软要求"——agent 可能跳过、可能忘、可能做半截。BUG#R10（云铝被归为"农副食品加工"）就是全流程跑完报告发出去，才被用户发现行业分类错了。**软 gate 不够，v2.9 起机械强制。**

**`lib/self_review.py`** 13 条自动检查覆盖所有历史 BUG 经验：

| severity | 抓什么 | 背后 BUG |
|---|---|---|
| 🔴 critical | 行业碰撞（工业金属→农副食品加工） | BUG#R10 |
| 🔴 critical | 维度缺失 / 空 data / 占位符 | wave2 timeout、fetcher 崩溃 |
| 🔴 critical | HK kline 0 根 / HK 财报空 | BUG#R7 / R8 |
| 🔴 critical | panel 全 skip / coverage < 60% | 数据灾难 |
| 🔴 critical | agent_analysis 缺 / 未 review | agent 偷懒 |
| 🟡 warning | DCF 全 0 / 金属股 materials 空 | v2.8.x coverage gap |
| 🟡 warning | 编造"苹果产业链"无 raw_data 证据 | 联想编造 |

**`assemble_report::assemble()` 入口自动跑 review**，critical > 0 → `raise RuntimeError("⛔ BLOCKED by self-review")`，**物理上无法出报告**，直到 agent 修完。

```bash
# agent 迭代流程
loop:
  python review_stage_output.py <ticker>
  读 .cache/<ticker>/_review_issues.json
  对每条 critical 执行 suggested_fix
  直到 critical == 0 才出 HTML
```

每次新 BUG 修完，对应的 `check_*` 规则都会加到 self_review，**下次同类问题跑完就自动抓到，不再靠用户反馈**。

---

## ❓ FAQ

**Q: 跑一次要多久？**
A: 5-8 分钟，主要是数据采集慢（22 个维度要调十几个 API）。纯计算的机构建模部分 < 1 秒。

**Q: 需要付费数据源吗？**
A: 不需要。全部免费源（akshare / yfinance / DuckDuckGo / 巨潮 / 东方财富 / 雪球），零 API key。

**Q: 港股美股能用吗？**
A: 能。`/stock-deep-analyzer:analyze-stock 00700.HK` 或 `/stock-deep-analyzer:analyze-stock AAPL`。

**Q: 数据准不准？**
A: 实时数据走东方财富 / 雪球，财报走巨潮 / akshare，和你在东方财富 App 上看到的一样。但 web search 质量不稳定（DuckDuckGo 中文搜索有时会返回无关结果），所以 Claude 会做二次审查。

**Q: 能当投资建议吗？**
A: 不能。这是工具不是神仙，51 个大佬的意见都是规则引擎模拟的，不代表真人观点。买不买你自己决定。

**Q: 怎么知道这次报告数据是否可信？**
A: v2.9 起**强制**机械自查。报告生成前跑 13 条检查，critical 不过物理上发不出报告。`.cache/<ticker>/_review_issues.json` 里能看到本次跑有没有 warning，每条都带 `suggested_fix`。每次新 BUG 修完都加对应检查 → 下次同类问题自动抓到，不靠用户反馈。

**Q: 怎么升级到新版本？自动提示吗？**
A: 会。v2.14.0 起每次启动 CLI 或 agent 会话都会后台检测 GitHub 最新 release：
- 有新版本 → 弹三选一提示（是 / 跳过本版 / 否）+ 改动摘要
- 选"是"→ 按你装的方式执行对应命令：
  - Claude Code: `/plugin update stock-deep-analyzer`
  - git clone: `cd UZI-Skill && git pull`
  - Hermes: `hermes skills update wbh604/UZI-Skill/skills/deep-analysis`
- 选"跳过本版"→ 该版本不再提示，下一个新版本出来时才再弹
- 选"否"→ 下次启动再问
- 网络慢 / 关掉检查：`export UZI_NO_UPDATE_CHECK=1`（CI / Codex 环境推荐）
- 缓存 6 小时 · 不会每次都打 GitHub API

**Q: 之前报告里有 BUG 怎么办？**
A: 2026-04-17 前跑过"工业金属 / 工业母机 / 工业机械"相关股票的用户，cache 里的 `7_industry` 维度是错的（云铝被归为农副食品加工的那个 bug）。清 cache 重跑即可：
```bash
rm -rf skills/deep-analysis/scripts/.cache/<ticker>/raw_data.json
python run.py <ticker> --no-resume
```

---

## 📋 更新日志

| 版本 | 日期 | 主要变化 |
|---|---|---|
| **v3.8.0** | 2026-06-08 | **Tier-1 五方法 + Serenity 严谨化 + 技术指标/杜邦扩展**（参考 `anthropics/financial-services` + `lolifamily/ashare-mcp` + `muxuuu/serenity-skill`）. **① Tier-1 5 方法**（新包 `lib/tier1/`）：`/ai-readiness`（AI 就绪度/卡位 · 复用 `ai_chokepoint_score`）· `/earnings-preview`（财报前预览 · Bull/Base/Bear + 隐含波动）· `/model-update`（增量更新模型 · 假设 delta + 对 DCF/Comps/thesis 影响）· `/returns`（组合收益归因）· `/rebalance`（逐持仓再平衡 + 本地化换手成本，A股无资本利得税故不做 TLH）. **② Serenity 严谨化**（不再只会看多）：8 罚分因子（炒作无订单/微盘流动性/杀猪盘/治理/周期/替代设计/地缘/稀释 · 封顶 60% 折扣）+ 3 级证据阶梯（强公告财报×1.0 > 中媒体卖方×0.85 > 弱叙事×0.70 · 同卡位"有定点量产"≈90 vs"仅题材"≈60）+ 供应链 8 层分层（材料→...→下游 · 越上游瓶颈分越高）. **③ 指标扩展**：DuPont 杜邦分解（ROE 质量来源 margin_driven/leverage_driven · 价值派用）+ KDJ/OBV/Williams%R（K 线卡片新增副指标徽章 · 技术派用）. 61 个新回归测试 · 总 622 passed |
| **v3.7.1** | 2026-06-04 | **首页补 Serenity 介绍 + `--school H/I` 放开** · 用户反馈"README 没把 Serenity 写清楚". 修复：(1) 评审团章节重写 52→65 人 · 7→9 组完整表 (A–I)· 规则 180→236; (2) 新增专门 `## 🧠 I 组 · Serenity · AI 卡位/瓶颈猎手` 介绍块（她是谁 + 未审计免责 + Chokepoint Theory 作用 + "卡位决定态度"打分表 + `--school I/H` 用法）; (3) **bug fix** · v3.7.0 起 evaluator `SCHOOL_LABELS` 已含 H/I 但 `run.py` argparse `choices` 还停在 A-G · 文档说能用实跑报错 · 现 choices 扩到 A-I + `_SCHOOL_NAMES` 补中文名; (4) README/CLAUDE/AGENTS/GEMINI 当前状态计数 52→65 评委同步（历史 changelog 不动）. 533 passed |
| **v3.7.0** | 2026-06-03 | **13 位新晋科技大佬集体入团 · 52→65 评委** · 用户反馈"评委库新晋科技 / AI / VC 视角覆盖不足". 新增分布：**B 成长派 +5** (Marc Andreessen a16z / Bill Gurley Benchmark / Naval Ravikant AngelList / Brad Gerstner Altimeter / Chamath Palihapitiya Social Capital) · **C 宏观派 +2** 做空猎手 (Michael Burry Big Short / Jim Chanos Kynikos) · **E 中国价投 +1** (张磊 高瓴 · "做时间的朋友") · **G 量化派 +1** (Cliff Asness AQR 价值×质量×动量三因子) · **H AI 卡位/瓶颈猎手 +4** (黄仁勋 NVIDIA / Musk TSLA / Sam Altman OpenAI / Saylor MSTR). 每位评委 ≥4 条规则 (测试守护) · `_render_school_lock_banner` THEMES 全派代表评委更新为真实在册成员 · H 派配色紫色 🔗. NVDA 跑分实测 Andreessen/Gerstner/Huang/Altman 全 100 · 茅台跑分 Andreessen 38 (industry filter ✓ 白酒不在 software/AI) · 张磊 80 (✓ 长跑道龙头). 18 个新回归测试 · 总 532 passed |
| **v3.6.3** | 2026-06-03 | **重磅角色 Serenity · AI 卡位/瓶颈猎手（新增第 52 位评委 · 独立 I 组）** · 把 X 爆火的 AI 供应链「卡脖子/瓶颈点」投资人 Serenity ([@aleabitoreddit](https://x.com/aleabitoreddit)) 接入评审团 · 参考 [serenity-alpha skill](https://github.com/haskaomni/serenity-skill/tree/main/serenity-alpha) 方法论 + 爬 X 真实言论建语气库. **核心打分逻辑「卡位决定态度」**：新增派生特征 `ai_chokepoint_score`（AI 链命中 × 不可替代性 × 中小市值弹性 × 需求拐点）· `SERENITY_RULES` 全 weight 5 · 产品卡在 AI 瓶颈（光模块/CPO/HBM/CoWoS/InP 衬底…）+ 上游不可替代 + 小市值 → **bullish 重仓**；没卡到位/不在 AI 链上 → **bearish 不碰**（白酒/银行护城河满分也 score=0）；在链但卡位不硬 → neutral 待验证. 改动 `investor_db`(独立 I 组)/`investor_criteria`/`investor_evaluator`(`--school I`)/`investor_personas`/`investor_profile`/`stock_features`/`agents/investor-panel.md`/`investor-cards.json`(置顶高亮). 新增 `group-i-serenity.md` + `fin-methods/serenity-bottleneck.md`（六步法 + alpha 5 维 + $AXTI 范例）+ `serenity-voice.md` 语气库 + `docs/serenity-research-dossier.md`（全网 20 条评价档案）. 8 个新回归 + 实测水晶光电(neutral 59) · 总 533 passed |
| **v3.6.2** | 2026-06-03 | **cninfo 翻页长尾修复 + Hermes 脚本 pip 探测** · 两个社群 issue 同发. **#68** ([@xy2yp](https://github.com/wbh604/UZI-Skill/issues/68))：`--versus 000958 600406 --depth lite` 卡在 15_events cninfo 公告 · `0/854 [01:53<6:11:58]` · 根因 `akshare.stock_zh_a_disclosure_report_cninfo` 内部翻完全部 854 页才返回 · 我们 `.head(30)` 是事后截取没用. 修法：新增 `_cninfo_direct_api` 直连 cninfo `/new/hisAnnouncement/query` HTTP · `pageSize=30 + pageNum=1 + 15s 硬超时` · akshare 慢路径默认禁用（`UZI_AK_CNINFO_FALLBACK=1` opt-in）· 几小时 → ≤15s. **#69** ([@FrankHuy](https://github.com/wbh604/UZI-Skill/issues/69))：Linux + Py3.11 跑安装脚本 `pip: command not found` · akshare 装不上. 修法：脚本启动加 Python 版本预检（≥3.10）· pip 五层级联探测（venv/.venv/pip/pip3/python -m pip）· 完全失败时给 apt/yum/ensurepip 三套指令 · install 失败给镜像源 + 升级 pip 建议. 12 个新回归 · 总 507 passed |
| **v3.6.1** | 2026-05-29 | **Hermes Skills Guard 假阳性绕过** · [issue #66](https://github.com/wbh604/UZI-Skill/issues/66) (@zodiacg) 反馈：`hermes skills install` 报 `Verdict: DANGEROUS · 168 findings` · `--force` 也覆盖不了. 诊断：Hermes Skills Guard 模式匹配假阳性 · 把我们读 `os.environ.get("UZI_DEPTH")` 当 "exfiltration" · `subprocess.run(["brew", "install", "cloudflared"])` 当 "privilege_escalation" · HTML 注释当 "injection". Hermes 团队已知问题 ([#1006](https://github.com/NousResearch/hermes-agent/issues/1006)/[#7072](https://github.com/NousResearch/hermes-agent/issues/7072))· 官方 builtin skills 也被自家扫描器拦. 修法：新增 `install-hermes.sh` (96 行 · `set -euo pipefail`) · `curl ... \| bash` 一键 clone + symlink + venv pip · 完全等价 Hub 安装但跳过扫描. `INSTALL-HERMES.md` 头部重写解释假阳性原因. 11 个新回归测试守护 (script 存在/bash 语法/严格模式/4 skill 覆盖/venv fallback/文档链接) · 总 495 passed |
| **v3.6.0** | 2026-05-29 | **视觉/交互大升级 + 多股横向对比 + 组合分析** · 三 Phase 拼合发布. **Phase A 视觉**：(1) 暗色模式 toggle（右上角 🌙 · `localStorage` 持久化 + `prefers-color-scheme` 自动初始化）· (2) 左侧 sticky TOC + IntersectionObserver scroll-spy · (3) 大评分 count-up 动画 · (4) PE/PB/ROE/DCF/IRR/WACC/EV-EBITDA/LBO/YTD/TTM/PEG/LHB 自动包 `.jargon` + 悬浮 tooltip · (5) 报告底部 QR 码（扫码直达完整报告）· 🔒 全部用 `createElement + textContent` 安全 DOM · 不用 innerHTML (XSS 防御). **Phase B `--versus`**：2-4 只票横向对比 · `lib/versus_runner.py` (380 行)· ★ WIN 高亮 12 个核心指标 · 单 HTML 自包含 · 复用 cache. **Phase C `--portfolio`**：用户上传 CSV (ticker/weight/note) · 容错解析（header/无 header/中英文列名/0-1 vs 0-100 权重）· 权重自动归一 · 输出排名 + KPI（加权评分 + 集中度 + 行业分散）+ metadata.json · `lib/portfolio_runner.py` (370 行). Phase D（`--sector` / `--as-of`）需 fetcher date-aware · 留到 v3.7. 39 个新回归测试 · 总 484 passed |
| **v3.5.0** | 2026-05-29 | **单一流派视角锁定 (`--school A-G`) + SaaS 集成 (`--output-dir`)** · 社群反馈"我只想看 F 派游资视角 · 不想 51 评委一起 vote". (1) `run.py` 加 `--school A/B/C/D/E/F/G` · 价值/成长/宏观/技术/中国价投/游资/量化 七选一 · `investor_evaluator.evaluate` 入口检查 `UZI_SCHOOL` env · 非该派评委直接 `_skip_result(reason="用户锁定 X 派视角")` 不进规则引擎. (2) `synthesis.school_lock={group,label}` 编码进 syn · `_render_school_lock_banner` 7 派各自配色（A=深绿/F=深红/G=青）渲染在报告顶部 · 让分享者一眼看出本次仅看了该派 · 避免被误读为 51 评委结论. (3) `SKILL.md` 加 HARD-GATE · agent role-play 时严格只 role-play 该派 · `panel_insights` 不写跨派对比. (4) 同时合入早先准备的 `--output-dir DIR` SaaS 集成参数 · 把 `reports/{ticker}_{date}/` 拷到外部路径 + 写 `index.html` / `report.meta.json` 供 Celery worker 落库. 11 个新回归测试 · 总 445 passed |
| **v3.4.5** | 2026-05-12 | **F 派游资 LHB 反查 + low-confidence banner** · 社群 codex agent 跑京东方 (000725) 实测发现两点：① F 派 23 人全 skip（市值 2000 亿超射程）· 但 LHB 实际有 3-5 个游资席位参与涨停博弈 · 评委逻辑与数据脱节. ② 规则引擎 fund_score 37.6 但 agent 重评 65/100 · 报告无任何"score 不可信"警告 · 用户误判. 修法：(1) `_is_youzi_out_of_range` 加 LHB 反查 · features.matched_youzi 含该游资昵称时强制不 skip. (2) `_render_data_gap_banner` 新增 syn 参数 · stock + fund_score<50 + cov<60% → 渲染 low-confidence 红色 banner · 文案明确引导看 agent 重评估. 10 个新回归测试 · 总 407 passed |
| **v3.4.4** | 2026-05-12 | **data quality banner UX 优化** · 社群反馈两点：① ETF 报告 "覆盖率 17%" 让用户误判可信度（实际 ETF 本就无 ROE/PE 个股字段）· ② 橙色 banner 上橙色字（`#f59e0b/#fbbf24`）看不清. 修法：(1) banner 检测 ETF/LOF/mutual_fund · 切换 `fund-type` 蓝色调 banner · 文案明确"基金类型预期缺字段·不影响可信度"+ 引导看持仓股报告. (2) CSS 对比度大改 · title→#92400e 深棕 · subtitle strong→#7c2d12 + 加粗 800 · chip 文字→#7c2d12 · subtitle 正文→#1f2937 深灰. 11 个新 CSS + 行为回归测试 · 总 397 passed |
| **v3.4.3** | 2026-05-12 | **开放式基金分类修复 + 字段级 fallback gate** · (1) [#60 复议](https://github.com/wbh604/UZI-Skill/issues/60) (@SchrodingerBarbatos) · 用户输 110011 易方达优质 → 被错判 convertible_bond early-exit. 修法：`classify_security_type` 在判 cb 前用 `akshare.fund_name_em` 二次校验 · 加 `mutual_fund` 类型 · run.py + preflight 路由到 fund_holdings_runner · 005xxx 等股票前缀外的基金也识别. (2) [PR #63](https://github.com/wbh604/UZI-Skill/pull/63) (@Wood Letitia · 313+137 行) · 字段级 fallback gate · 修 source-level 整块切换导致 name 永远缺的问题 · 主源拿到 price/PE/PB 但 name 空时 · 自动调 tencent_qt → baostock → ak_code_name 补全 · 仅填空不覆盖. 386 tests passed |
| **v3.4.2** | 2026-05-11 | **Windows + Clash + Schannel TLS 兼容** · 社群反馈"Clash 国内规则 DIRECT 还是 Schannel · 东方财富彻底不可用 · 只有 baostock 能用". 修法：(1) `lib/data_sources.fetch_basic` 在所有 eastmoney 链路（xueqiu / push2 / baidu / tencent_qt）后追加 baostock fallback · `query_history_k_data_plus` 拿 peTTM/pbMRQ/close · `query_stock_basic` 拿 name/listed_date; (2) `fetch_financials._fetch_a_share` 当 ROE/营收/净利率全空时调 baostock `query_profit_data` 拉 5 年季报 · 解析 ROE history / 营收 history / 净利率 / 毛利率. 实测茅台 baostock 拿到 ROE=19.25% / 净利率 52.6% / 营收 893.5 亿. 6 个新回归 test (含真机烟雾) · 总 374 passed |
| **v3.4.1** | 2026-05-11 | **verdict 粒度细化** · 社群反馈"神剑股份(58分) / 博云新材(60分) verdict 都是观望优先 看不出差异". 修法：(1) verdict 50-65 拆三档（观望偏空 50-55 / 观望中性 55-60 / 观望偏多 60-65）· 65-70 加"可以蹲（偏弱）"; (2) verdict label 追加"X 派看多 / Y 派看空"; (3) synthesis 加 `verdict_detail = "基本面 X · 共识 Y"` · assemble_report 渲染时拼到 verdict 后. 改后两只票 verdict 仍同段（55-60）但 detail 让基本面 +2 分差异显式可见. 5 个新回归 test · 总 368 passed |
| **v3.4.0** | 2026-05-10 | **基金/ETF 持仓循环分析 + baostock ≥0.9.1** · ETF/LOF 不再 early-exit · 改为列出前 10 持仓 + 估算耗时 + **二次确认**（y / 数字 / N） · 确认后循环跑 stock-analyze + 生成 fund-holdings-summary.html. partial failure 容忍 · `UZI_FUND_AUTO_YES=1` 跳过 prompt（CI/agent）. 可转债/指数仍 early-exit. 同时 `requirements.txt` 锁 `baostock>=0.9.1` (社群通知 2026-04-22 起服务端要求). 新建 `lib/fund_holdings_runner.py` (240 行) · 7 个回归测试 · 总 362 passed. 真机：510300 持仓正确拉到（茅台 5.89% top1） |
| **v3.3.4** | 2026-05-10 | **mini_racer V8 crash escape hatch** ([#61](https://github.com/wbh604/UZI-Skill/issues/61)) · 用户 @dragonforai 报 `python run.py SEHK.03690 --depth deep` → `[FATAL:address_pool_manager.cc(67)] Check failed`. 根因：macOS Py 3.12/3.13 下 mini_racer V8 isolate pool 即使串行化仍可能双重初始化 SIGTRAP（进程级崩 · Python `try/except` 抓不到）. 多重修法：① `UZI_DISABLE_MINI_RACER=1` 显式禁用. ② **Sentinel 文件机制（核心创新）**：调 mini_racer fetcher 前 arm `~/.uzi-skill/_minirackercrash.sentinel` · 成功后 disarm · 进程崩则 sentinel 留下 · 下次启动自动 disable + 提示用户. ③ `UZI_FORCE_MINI_RACER=1` 强制启用. legacy + pipeline 双路径都加保护. 新增 7 个回归 test · 总 355 passed |
| **v3.3.3** | 2026-05-06 | **社区 PR 4 合 1**（[#52](https://github.com/wbh604/UZI-Skill/pull/52) / [#54](https://github.com/wbh604/UZI-Skill/pull/54) / [#55](https://github.com/wbh604/UZI-Skill/pull/55) / [#59](https://github.com/wbh604/UZI-Skill/pull/59)） · #52 [LHB akshare 1.18+ "近一月" 失效](https://github.com/wbh604/UZI-Skill/pull/52) (@qdby26) · 改 YYYYMMDD 日期循环 + 6 mock test。#55 [agent_analysis schema docs](https://github.com/wbh604/UZI-Skill/pull/55) (@DragonQuix) · SKILL.md + analyze-stock.md 文档化 12 条 validator 校验规则。#54 (@DragonQuix) cherry-pick svg_radar import · #59 (@Charlson852) cherry-pick Python 3.11 嵌套 f-string SyntaxError 修复（**避开了 #59 原版的 items.append 缩进 bug**）· 新增 5 个回归 test 守护 · 总 348 passed |
| **v3.3.2** | 2026-04-28 | **GitHub issue #50 + #51 hotfix**（社区驱动）· #50 [Stage 2 总是超时](https://github.com/wbh604/UZI-Skill/issues/50)：v3.2 拆分时 `lib/report/institutional.py` 漏 import `svg_sparkline` · `_render_lbo_block` 触发 NameError → stage2 崩 · 加进 import 块即修复（致谢 @chenxiang-bj 报告 + agent 诊断）。#51 [XueQiu 登录验证失败](https://github.com/wbh604/UZI-Skill/issues/51)：`/cubes/cubes_search.json` endpoint 已下线 · 改用 `/query/v1/search/cube/stock.json?q={code}` (致谢 @bilieebiliee1-design 报告 + @Kylin824 提供 fix)。3 处文件同步换 endpoint。新增 5 个回归 test · 总 337 passed |
| **v3.3.1** | 2026-04-28 | **Hermes 兼容回归修复 (hotfix)** · 群友反馈"更新后不支持 hermes 报错"。根因：v3.0/v3.1/v3.2 重构期 main 上从未包含 hermes 兼容代码（`INSTALL-HERMES.md` / `skills/deep-analysis/run.py` / `requirements.txt` / 4 个 SKILL.md hermes metadata 全缺）· 但 README 仍叫 hermes 用户装 main · 装下来缺文件就崩。修复：从 `hermes-compat` 分支 cherry-pick 5 项核心适配到 main + `run.py` 加双 layout 探测。**hermes 用户重装一次 skill 即恢复**（`hermes skills uninstall` + install 4 个）|
| **v3.3.0** | 2026-04-23 | **分支大整合**：唯一未合 feature（v2.10 segmental 渲染层 · 228 行 + 222 CSS）cherry-pick 到 v3.2 架构 · 新建 `lib/report/segmental.py` (555 行)。同时清理 22 个 stale 分支（refactor/* / docs/* / feature/v2.14-v2.15.3 都已 superseded）· 仅保留 main + hermes-compat · 单一开发主干. |
| **v3.2.0** | 2026-04-23 | **assemble_report.py 深度拆分 (-80%)**：2964 → 587 行 · 拆 5 个子模块 `lib/report/svg_primitives` (602) / `dim_viz` (742) / `institutional` (532) / `panel_cards` (183) / `special_cards` (544)。v2.x 所有 API 保持 re-export · 332 tests 全过 · e2e 零差异 · 加 `CODEX.md` + `AGENTS.md::Repository Layout` 给 codex 准确入口指引 |
| **v3.1.0** | 2026-04-23 | **run_real_test.py 瘦身 65%**：2105 → 735 行。1228 行纯函数 (`_f/score_dimensions/generate_panel/generate_synthesis/_autofill_qualitative_via_mx`) → `lib/pipeline/score_fns.py`；166 行 preflight/resolve/ETF guard → `lib/pipeline/preflight_helpers.py::prepare_target()`。rrt 做 re-export 保持完整向后兼容 · 332 tests 全过 · 002217 resume 10s 出报告 |
| **v3.0.0** | 2026-04-23 | **pipeline 架构默认启用**：`python run.py <ticker>` 默认走 `pipeline.run_pipeline` · `UZI_LEGACY=1` 强制回老路径 · pipeline 异常自动 fallback。Phase 6c 解耦：`pipeline.score` 直接调 rrt 纯函数（不再走 stage1 重复 collect）· 002217 score_from_cache 从 180s → 10.6s。Pipeline 预检 guards (中文名 / ETF / LOF / 可转债 → fallback legacy) |
| **v2.15.5** | 2026-04-23 | **评分公式重校准**：`panel_consensus` 从单一 vote 公式升级为混合公式 `0.65*score_mean + 0.35*vote_weighted` + 极化拉伸 (k=1.3) · 解决"大多数分在一个区间徘徊"问题 · 7 流派 consensus 分歧更清晰 · 002217 F 游资 51→43.7（vote 高估修正）· G 量化 50→59.3（实分低估修正） |
| **v2.15.4** | 2026-04-22 | **按流派打分 school_scores**：7 大流派 (A 价值 / B 成长 / C 宏观 / D 技术 / E 中式 / F 游资 / G 量化) 各自产出 consensus/avg_score/verdict · 报告新增"SCHOOL SCORES"卡片 · 同一只票可见不同哲学的分歧（宏观派买入 vs 成长派回避） |
| **v2.15.3** | 2026-04-21 | **性能 hotfix** · fetch_capital_flow 每股重抓全 A 大宗/解禁/融资数据集 → 每股 3+ min · 新增 `_universe_*()` 4 个 helper + `cached("_universe", ...)` 24h TTL · 全股共享 · 二次跑 universe 部分 0.01s（**100+ 倍加速**）· 6 专项测试 |
| **v2.15.2** | 2026-04-21 | **GitHub issue hotfix**：#36 Gemini CLI 安装报错（gemini-extension.json 加 version + 纳入 version-bump）· #30 网络自检增强（Clash 本地代理端口侦测 + 数据源分组诊断 + 多行修复建议 · 写进 `.cache/_global/network_profile.json` 供 agent 读）· 10 专项测试 |
| **v2.15.1** | 2026-04-20 | **报告质量 2 bug hotfix**（实测 300470 发现）· Bug 1: fund-card 一堆 "5Y +0.0%" 假数据 · 修 `_build_row_full` + `render_fund_managers` 让 lite 行降级 · Bug 2: 14_moat 护城河被贵州茅台数据污染（DDGS 对生僻公司返超级股票结果）· 加 `_SUPERSTAR_POLLUTERS` 过滤 · 11 专项测试 |
| **v2.15.0** | 2026-04-20 | **YAML persona 接入 agent role-play**（借鉴 augur · 取长补短）：新增 `personas/` 目录 51 个 YAML 文件（12 flagship 手写 + 39 stub 自动生成）· `lib/personas.py` 加载 + prefix-stable system message（prompt cache 省 50-90%）· `lib/i18n.py` zh/en 语言开关 · `HARD-GATE-PERSONA-ROLEPLAY` 强制 agent 读 YAML · 双盲测试（3 股 × 5 投资者）显示 YAML 14/15 vs Rules 8/15 方向准确率 · 修复 Rules 4 类"历史立场错位"硬伤 · 14 专项测试 |
| **v2.14.0** | 2026-04-20 | **自动检测 GitHub 新版本**：每次启动 CLI 或 agent 会话，插件会检测 GitHub latest release · 有更新则弹 `y / s / n` 三选一（是 / 跳过本版 / 否）· 跳过本版后直到下一版才再弹 · 6h 缓存防 API 限流 · 非 TTY / `UZI_NO_UPDATE_CHECK=1` / 网络异常 silent skip 不阻塞 · `HARD-GATE-UPDATE-PROMPT` 让 agent 主动展示 · 13 专项测试 |
| **main** | 2026-04-20 | **Segmental Revenue Build-Up 落地**（`lib/segmental_model.py` 408 行 + `compute_segmental.py` CLI + `/segmental-model` slash command）· deep 档 `enable_segmental_model` flag 之前只在 profile 声明，实现缺失——本次从老分支 cherry-pick 3 个新文件，零冲突接入 · 同步新增 `CONTRIBUTORS.md` · 清理 14 个已合入幽灵分支 |
| **v2.13.7** | 2026-04-19 | **16 新源真正接入 fetcher**：v2.13.4/6 登记但未用的 16 源全部接通——新建 `lib/news_providers.py`（jin10/em 快讯/em 公告/同花顺 4 源聚合）接入 `fetch_events` + `fetch_sentiment`；`_yahoo_v8_chart` 直连 HTTP 接入 US/HK K 线链（绕 yfinance cookie）；cfachina 期货协会源接入 `fetch_policy`（期货/商品 industry 专用）。实测 4/4 新闻源通 · A 股 15_events 密度 3-5 → 10-30 条 · pytest 217 passed |
| **v2.13.6** | 2026-04-19 | **新增 6 个经 curl 验证的期货 + 财经新闻源**（SOURCES 64 → 70）：jin10_flash（类财联社零 Key 替代）/ em_kuaixun / em_stock_ann / ths_news_today / 99qh / cfachina · 8 专项测试 |
| **v2.13.5** | 2026-04-19 | **NetworkProfile 自适应 + agent HARD-GATE 主动触发 Playwright**：9 目标 3 组网络预检（domestic/overseas/search）+ 代理检测 + 5min cache · SKILL.md / AGENTS.md 加 `HARD-GATE-PLAYWRIGHT-AUTOFILL` 让 agent 主动 FORCE · 15 专项测试 |
| **v2.13.4** | 2026-04-19 | **新增 10 个经 curl 验证的无 Key 公开数据源**（SOURCES 54 → 64）：Yahoo Chart v8 / 腾讯 qt HK / 加密货币（CoinGecko/Binance/CoinCap）/ ECB / World Bank 等 · 11 专项测试 |
| **v2.13.3** | 2026-04-19 | **51 评委规则全员历史立场还原**：林奇 PE<40 Rolls Royce 红线、索罗斯 long/short 拆分、木头姐 CPO/光模块 whitelist、段永平/张坤/邓晓峰 PE 硬红线、游资 range 校验 · 10 专项测试 |
| **v2.13.2** | 2026-04-19 | **Playwright 触发逻辑升级 · 数据质量感知 + FORCE flag**：`_dim_quality_score` 公开字段真空检测 · `UZI_PLAYWRIGHT_FORCE=1` 强制全维兜底 · 8 专项测试 |
| **v2.13.1** | 2026-04-18 | **Playwright 全 10 维覆盖**（开源研究场景扩展）：v2.13.0 Codex 保守排除的 5 维（7_industry 百度搜索 / 14_moat 百度百科 / 13_policy 证监会 / 18_trap 小红书 / 19_contests 雪球组合）全部加回 · medium 4→6 维 · deep 5→10 维 · 22 专项测试 |
| **v2.13.0** | 2026-04-18 | **Playwright 通用兜底 · 按三档 profile 分级**：lite `off` / medium `opt-in` (4 维) / deep `default` (5 维 · 首次 y/n 自动装 Chromium)。新增 `lib/playwright_fallback.py` · 抽离 `lib/junk_filter.py` |
| **v2.12.1** | 2026-04-18 | **4 个报告板块空数据/错数据修复**（中际旭创实测驱动）：4_peers 三层 fallback + 雪球 Playwright opt-in · 7_industry regex 上下文感知 · core_material 垃圾过滤 · BCG 真实算 market_share + 阈值调整 · 16 专项测试 |
| **v2.12.0** | 2026-04-18 | **6 平台社交热榜聚合**：微博/知乎/百度/抖音/头条/B站 官方 API + 5min 文件缓存 + 单平台失败不影响其他 · `17_sentiment` 维度新增 `hot_trend_mentions` 字段补 DuckDuckGo 盲区 · 抄 jcp/hottrend 设计 · 17 个专项测试 |
| **v2.11.0** | 2026-04-18 | **评分校准（用户反馈驱动）**：论坛+微信反馈"茅台 47 分"、"没超过 65 分" → verdict 阈值 `85/70/55/40 → 80/65/50/35`；consensus neutral 权重 `0.5 → 0.6`（A 股白马结构性偏低问题）；`stock_style` 同步对齐 |
| **v2.10.7** | 2026-04-18 | **Codex 审查 3 处修复**：`raw.market` 硬编"A"污染 HK/US · `resume` 对别名输入失效（中文名/三位港股 cache 不命中）· AGENTS.md 强制全量流程与 CLI/lite 降载设计冲突 → 深浅两路径决策树 |
| **v2.10.6** | 2026-04-18 | **Providers 框架实际落地**：v2.10.3 建的 5 provider 链（akshare/efinance/tushare/baostock/direct_http）实际接入 `data_sources.py` K 线链 · Tushare kline 补齐 · `hermes skills install` 风格 health CLI |
| **v2.10.5** | 2026-04-18 | **v2.10.4 遗漏补丁**：`check_coverage_threshold` profile-aware（lite 不再结构性偏低）· `run.py` 自动 `UZI_CLI_ONLY=1`（medium/deep CLI 直跑也出报告）· `render_fund_managers` None 字段兜底 |
| **v2.10.4** | 2026-04-17 | **Codex 测试反馈 3 bug**：lite 模式 self-review 9 critical 误报 · `agent_analysis.json` 缺失 CLI 直跑误报 critical · ETF 早退 `RuntimeError: Stage 2 缺少数据` |
| **v2.10.3** | 2026-04-18 | **三档思考深度**：`lite` (30s-2min · 7 维 + 10 投资者) / `medium` (2-4min · 默认 · 22 维 + 51 投资者) / `deep` (15-20min · 含 Bull-Bear 辩论 + Segmental) · `--depth` CLI arg · direct_http provider（腾讯/新浪/etnet 直连脱离 akshare） |
| **v2.10.0-2** | 2026-04-18 | 首次安装 + Codex 机器耗时/token 优化 · `lib/net_timeout_guard` 4 层网络超时保护（代理/GFW 不通快速 fail） · Fund holders 双层策略（Top N full + rest lite） · 首次运行 10-15min → 2-4min |
| **v2.9.x** | 2026-04-17 | **机械级 agent 自查 gate**：13 条自动检查 + `assemble_report` 入口强制 block critical → 修完再出 HTML · fetch_industry 动态 `search_trusted`（236 个行业不再是"—"）· HK industry_pe fallback · consensus 半权公式 |
| **v2.8.x** | 2026-04-17 | **BUG#R10 修复** 行业分类碰撞（工业金属→农副食品加工）· 134 条申万→证监会硬映射 · 22 位海外人物真实原话 + URL 溯源 · 每评委自己方法论回答 3 字段 · English README · Munger/Alibaba hook |
| **v2.7.x** | 2026-04-17 | HK financials 实现（BUG#R7）· HK kline fallback 链（BUG#R8）· wave2 flush（BUG#R9）· 风格动态加权 7+1 · 量化结构性识别（top-1<2%）· XueQiu 登录 opt-in · 14 权威数据源 + search_trusted |
| **v2.6.x** | 2026-04-17 | agent 闭环写回 · `agent_analysis.json` 合并 · dim_commentary · 22 维覆盖 |
| **v2.5** | 2026-04-16 | 数据源注册表 54 条 · HK AASTOCKS 支持 · 3 层 tier 分类 |
| **v2.0–v2.3** | 2026-04-16 | 17 种机构分析方法 · 51 评委 180 规则 · 两段式 pipeline · MX 妙想 API · 多平台支持 |
| **v1.0** | 2026-04-14 | 初版 · 19 维 + 50 评委 + 杀猪盘检测 |

完整更新日志见 [RELEASE-NOTES.md](RELEASE-NOTES.md)

---

## 🤝 致谢

- [anthropics/financial-services-plugins](https://github.com/anthropics/financial-services-plugins) — 机构级分析方法论
- [obra/superpowers](https://github.com/obra/superpowers) — 多平台架构 / HARD-GATE / hooks / sub-agent 设计
- [akshare](https://github.com/akfamily/akshare) — A 股数据引擎
- [titanwings/colleague-skill](https://github.com/titanwings/colleague-skill) — Skill 架构参考
- [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) — Pydantic Signal 模式
- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) — 多空辩论循环

---


## ⚠️ 免责声明

本工具由 AI 模型基于公开数据生成分析报告。所有评分、建议、模拟评语均为算法输出，不代表任何真实投资者的实际观点。**不构成投资建议**，投资有风险，入市需谨慎。

---

## ⭐ Star History

实时 stars：![GitHub Repo stars](https://img.shields.io/github/stars/wbh604/UZI-Skill?style=social)

<a href="https://star-history.com/#wbh604/uzi-skill&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=wbh604/uzi-skill&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=wbh604/uzi-skill&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=wbh604/uzi-skill&type=Date" />
 </picture>
</a>

> 注：star-history.com 服务端有 24h 缓存，增长很猛的前几天图可能滞后（想看当前真实数字看上面的 shields.io badge，或点图进 star-history 官网会触发刷新）。

---

<div align="center">

MIT License · Made by FloatFu-true · O.o

</div>
