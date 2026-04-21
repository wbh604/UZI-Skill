# Release Notes

## v2.15.2 — 2026-04-21 (Gemini CLI 安装修复 + 网络自检增强)

> **Issue 驱动** · 处理 GitHub 社区反馈：
> - **#36** · Veitkwok 报告 Gemini CLI 安装失败
> - **#30** · 3150214587 希望代理 / 数据源自检修复机制

### Bug 1 · Gemini CLI 安装报错（#36）

**症状**：`gemini extensions install https://github.com/wbh604/UZI-Skill` 失败，报 `missing "version"`。

**根因**：`gemini-extension.json` 缺 `version` 字段 · Gemini CLI 硬校验。

**修复**：
- `gemini-extension.json` 加 `"version": "2.15.2"`
- `.version-bump.json::files` 新增 `gemini-extension.json` · 未来 bump 自动同步（避免再漏）

### Feature 2 · 网络自检增强（#30）

**需求**：用户通过 Clash 等代理时 · 环境偶尔不稳 · 希望 plugin 能自动诊断 + 给出修复建议。

**实现**（`lib/network_preflight.py`）：
1. **本地代理端口检测**（`_detect_local_proxy`）
   - 扫 6 个常见端口：Clash 7890/7891/7897 · V2rayN 10808 · Shadowsocks 1080 · Charles 8888
   - 若检到本地代理但 `HTTPS_PROXY` 未设 → 提示具体 export 命令
   - 若 `HTTPS_PROXY` 已设但代理没启 → 提示 unset
2. **数据源分组诊断**（`diagnose_source`）
   - 按 3 组（domestic / overseas / search）独立汇报
   - 每组列出受影响的具体 fetcher（如 "overseas 挂 · 影响 yfinance / _yahoo_v8_chart / CoinGecko"）
   - 每组带多行 `fix` 建议（"检查 Clash 规则 / 切全局模式 / unset 代理"）
3. **NetworkProfile 新增字段**
   - `local_proxy: dict` · 本地端口检测结果
   - `diagnostics: list` · 分组诊断列表
4. **verbose 模式输出**
   - 旧：一行 recommendation
   - 新：recommendation + Clash hint + 每组诊断 + 每组 fix（多行）
5. **cache 写入** · `.cache/_global/network_profile.json` 含 `local_proxy` + `diagnostics` · agent/sub-agent 可读取

### 效果

```
🌐 网络预检 (3/9 通 · 均延迟 15ms · proxy=no)
  [国内 2/3]
    ✓  10ms  push2.eastmoney.com ...
    ✗ ConnectionRefusedError  stock.xueqiu.com ...
  [境外 0/3] ...

  ⚠ 检测到本地代理运行（Clash Verge）但 env 未设 HTTPS_PROXY · 脚本默认不走代理
     export HTTPS_PROXY=http://127.0.0.1:7897 && export HTTP_PROXY=http://127.0.0.1:7897

  🔧 数据源诊断（2 组受影响）
     [overseas] 🔴 不通 · 影响 3 个 fetcher
       主要问题：Yahoo / CoinGecko 挂 · 美股港股数据降级
       1. 浏览器测试 finance.yahoo.com 能否访问
       2. 开 Clash 全局模式 ...
     [search] 🔴 不通 · 影响 5 个 fetcher
       ...
```

### 测试

`tests/test_v2_15_2_network_enhance.py` · **10 case**：
- `gemini-extension.json` 含 version 字段
- `.version-bump.json` 纳入 gemini manifest
- 本地代理端口检测（含 mock Clash 场景）
- 分组诊断 3 态（全挂 / 全通 / 部分）
- NetworkProfile 新字段存在
- run_preflight 写 cache 含 `diagnostics` + `local_proxy`

pytest 全量 **265 passed**（255 baseline + 10 新 · 零回归）。

### 版本

- `2.15.1 → 2.15.2`（patch · issue hotfix + 网络 UX 增强）
- **5 manifest 同步**（新增 gemini-extension.json）
- Branch: `feature/v2.15.2-gemini-network-fix`
- Tag: `v2.15.2`
- Close GitHub issues: **#36 · #30**

---

## v2.15.1 — 2026-04-20 (报告质量 2 bug hotfix · 实测 300470 发现)

> 用户用 v2.15.0 实测 300470.SZ（中密控股）· 指出报告里 2 个长期存在的视觉/准确性 bug · 本次 hotfix。

### Bug 1 · 基金持仓一堆 "0.0% 假数据" fund-card

**症状**：报告里公募基金持仓区域常看到 15-30 张 fund-card · 第 5/6/7 张以后的"5 年累计 +0.0% / 年化 +0.0% / 回撤 -0.0% / 夏普 0.00"——数据明显缺失但被当实测数据渲染。

**根因**：
1. `fetch_fund_holders._build_row_full` 在 `compute_fund_stats` 返空（`fund.eastmoney.com` SSL 失败 / 新基金数据不足）时，用 `stats.get("return_5y", 0)` 写 **0**（非 None），没降级为 lite
2. `assemble_report.render_fund_managers` 所有 manager 都被当 full card 渲染 · `INITIAL_SHOW=6` 硬编码，lite 混进前 6 张

**修复**：
- `fetch_fund_holders.py` · stats 为空时 return `_row_type="lite"` + 全部数值字段 `None`（有真实 stats 才返 full）
- `assemble_report.py::render_fund_managers` · for 循环里 `is_lite` 跳过 full-card 生成 · `INITIAL_SHOW = min(6, len(cards))` 动态
- **新增 lite 行去重 + cap 30**：按 `fund_code` 去重（避免富国天惠 A/B/C/D 4 个份额重复列）· 按 `position_pct` 排序取 top 30 · 余量用"另有 N 家"提示

### Bug 2 · 14_moat 护城河被贵州茅台数据污染

**症状**：中密控股 300470 的报告 14_moat 区 4 个字段（intangible/switching/network/scale/rd_summary）**全部显示 "贵州茅台表示，技术创新在公司发展历程中始终扮演关键角色..."**（茅台成立研究院的新闻）

**根因**：`fetch_moat.py` 对生僻公司用 DDGS 搜 "专利/核心技术/品牌壁垒" → DDGS 返回 popular stocks（茅台）的文章 → 结果只做 `_is_garbage`（字典/百科）过滤，没做"结果是否真含目标公司名"的过滤。

**修复**（`fetch_moat.py`）：
- 新增 `_SUPERSTAR_POLLUTERS` 列表（15 个易污染股：茅台/五粮液/宁德/腾讯等）
- 新增 `_result_mentions_company()` · 结果 title+body 不含目标公司名就丢
- polluter 集合动态排除目标本身（分析茅台时茅台自己的结果正常保留）

### 验证

**Playwright 实测 300470.SZ 重跑**：
- fund 区 **0 张 0.0% 假 card** → 30 个 compact row + header "722 家公募基金持有本股 · 头部 0 家有完整 5Y 业绩"
- 14_moat 全报告 **0 茅台污染字样**（之前 4 处）

### 测试

`tests/test_v2_15_1_fund_lite_rendering.py` · **11 case**：
- fund lite 降级（7 case）：`_row_type='lite'` 正确标注 / `render_fund_managers` 跳 lite / `INITIAL_SHOW` 动态 / 全 full 无 compact / 全 lite 无 card / 核心反向测 0.0% card 不出现
- moat 污染过滤（4 case）：polluter 结果被丢 / 真含目标公司保留 / 无关结果保守过滤 / 目标本身是 polluter 自己不被误伤

pytest 全量 **255 passed**（baseline 244 + 11 新 · 零回归）。

### 版本

- `2.15.0 → 2.15.1`（patch · 报告质量 hotfix）
- 4 manifest 同步
- Branch: `feature/v2.15.1-fund-lite-render`
- Tag: `v2.15.1`

---

## v2.15.0 — 2026-04-20 (YAML persona 接入 agent role-play · 取长补短 augur)

> **借鉴来源**：xgzlucario/augur（18 投资者 LLM-council CLI）· 验证后发现 YAML persona
> 格式能系统性修复当前 Rules 引擎 4 类"历史立场错位"硬伤。

### 双盲测试结果（v2.14 baseline vs v2.15 YAML）

| 对比维度 | Rules 胜 | YAML 胜 |
|---|---|---|
| 准确性（方向对不对） | 8/15 | 14/15 |
| 入戏感（像不像本人） | 2/15 | 15/15 |
| 可操作性 | 4/15 | 13/15 |
| **明显错误** | **4 个硬伤** | **0** |

4 个 Rules 硬伤典型：
- 合力泰 × 木头姐："必须重仓"（她不会买 OEM 显示模组）
- 合力泰 × 赵老哥："观望"（这恰恰是他最爱的低价题材）
- 茅台 × 巴菲特："买入"（他公开说过"不懂中国白酒"）
- 中际旭创 × 段永平："强买"（PE 63 超他 40 红线）

### 混合架构 · 保留自有优势

```
  22 维 fetcher → raw_data.json    ← 保留（vs augur 只靠 LLM web search）
       ↓
  Rules 引擎    → panel.json       ← 保留（确定性兜底 · agent 失败仍可出报告）
       ↓
  YAML persona → agent role-play  ← 🆕 新增（修正 Rules 硬伤）
       +                              flagship 12 手写，优先级 > Rules headline
  prefix-stable                      stub 39 自动生成，Rules headline 优先
  system message
       ↓
  agent_analysis.json → stage2 merge → HTML + 朋友圈 + 战报
```

### 新增目录 `personas/` · 51 YAML 文件

**12 Flagship（手写 · philosophy + key_metrics + avoids + a_share_view + voice + famous_positions）**：
- Group A 经典价值：buffett / graham / fisher / munger
- Group B 成长：lynch / wood
- Group C 宏观：soros / dalio
- Group E 中式价值：duan / zhangkun
- Group F 游资：zhao_lg / zhang_mz

**39 Stub（自动生成 · _meta.status=auto_generated_stub · 仅基础身份 · Rules headline 优先）**：
- templeton / klarman（价值）· oneill / thiel（成长）· marks / druck / robertson（宏观）
- livermore / minervini / darvas / gann（技术派）· zhushaoxing / xiezhiyu / fengliu / dengxiaofeng（中式）
- sun_ge / fs_wyj / yangjia / chen_xq / hu_jl 等 19 位游资
- simons / thorp / shaw（量化）

Stub 会随使用逐步迭代为 flagship · 每当用户反馈"某某评委说话不像本人"就升级对应 YAML。

### 新增模块

- **`lib/personas.py`**（~180 行）· `Persona` dataclass + `load_persona(id)` + `build_system_message(snapshot, lang)` + `build_persona_user_message(persona, ticker)` · 零依赖迷你 YAML parser（不引入 pyyaml）
- **`lib/i18n.py`**（~30 行）· `language_instruction(lang)` + `get_language()` · zh 默认 / en 供 Hermes 国际用户 · env `UZI_LANG=en`
- **`SKILL.md`** 加 `HARD-GATE-PERSONA-ROLEPLAY` · agent role-play 时必须读 YAML

### 吸收 augur 的 prefix-stable prompt cache 优化

`personas.build_system_message(snapshot_json, lang)` 确保字节级一致 ·
51 persona 调用共用一个 system message · Anthropic / OpenAI prompt cache 能命中前缀 ·
预估 input token 成本 -50~90%（按 deep 档 51 人 × 3-5k token 计算，单次分析省数千 token × 51 人）。

### 测试

`tests/test_v2_15_0_persona_layer.py` · **14 个回归**：
- 51 persona 文件全部存在 · 12 flagship 身份正确 · 39 stub 标记 auto_generated_stub
- flagship 有 philosophy + key_metrics + voice + a_share_view 必填
- YAML id 跟 panel.json investor_id 1:1 对应
- `to_prompt_block` 输出含 Philosophy/Voice 段且 < 2500 字符
- `build_system_message` 同 snapshot + lang prefix 稳定（prompt cache 前提）
- i18n zh 默认 / en opt-in / env override / unknown 回退 zh

**全量 244 passed**（baseline 230 + 14 新 · 零回归）。

### 影响面

- **agent role-play 质量显著提升**：12 flagship 评委的 headline / reasoning 会明显"更像本人"
- **Rules 引擎仍完整兜底**：agent 失败 / 不可达时，Rules 骨架分仍能出报告（不依赖 LLM）
- **成本可控**：prefix cache 命中能省 50-90% input token
- **i18n 准备就绪**：Hermes 英文用户 `UZI_LANG=en` 可切换输出语言

### 版本

- `2.14.0 → 2.15.0`（minor bump · 新增用户可见的 role-play 质量层）
- 4 manifest 同步
- Branch: `feature/v2.15.0-persona-layer`
- Tag: `v2.15.0`

---

## v2.14.0 — 2026-04-20 (自动检测 GitHub 新版本 · interactive y/s/n prompt)

> **用户请求**：每次使用插件时自动检测 GitHub 是否有新版本 · 有更新时弹提示 + 改动说明 · 支持"是/跳过本版/否"三选 · 跳过本版后直到下一版出来才再弹。

### 新增 `lib/update_check.py`（~180 行）

核心 API：
- `check_for_update(force=False) -> UpdateInfo | None` · 返 `{current, latest, notes, url}` 或 None
- `mark_skipped(version)` · 记用户 skip 决策到 `.cache/_global/update_check.json`
- `handle_answer(ans, latest)` · y/s/n 回答归一处理
- `format_prompt(info)` · 统一展示模板（CLI + agent 共用）

**状态文件** `.cache/_global/update_check.json`：
```json
{
  "skipped_version": "2.14.1",
  "last_check_at": 1713552000,
  "cached_latest": "2.14.1"
}
```

**三态逻辑**：
- `current < latest` 且 `skipped_version != latest` → 弹提示
- `current < latest` 且 `skipped_version == latest` → 跳过本次（等下一版再弹）
- `current >= latest` → 不弹

### 两档触发点

1. **CLI 直跑**（`run.py` 顶部）：`_maybe_prompt_update()` · interactive `input("[y/s/n]")`
   - 非 TTY（CI / Codex sandbox / 管道）自动跳过
   - `UZI_NO_UPDATE_CHECK=1` env 禁用
   - 网络异常 silent skip（不阻塞分析流程）

2. **Agent 会话**（`hooks/session-start`）：后台检查 + 写 `.cache/_global/update_prompt.md`
   - SKILL.md 新增 `HARD-GATE-UPDATE-PROMPT`：agent 第一次回应前必须读该文件 → 完整展示给用户 → 收集 y/s/n → 调 `handle_answer` 写回
   - 处理完删除 prompt 文件，同会话不重复弹

### 用户交互文案

```
📦 UZI-Skill 有新版本可更新：v2.13.7 → v2.14.0
   https://github.com/wbh604/UZI-Skill/releases/tag/v2.14.0

更新内容（前 600 字）：
[从 release body 抓]

选项：
  [y] 是，我现在去更新
  [s] 跳过本版（v2.14.0 之后有更新再提示）
  [n] 否，下次启动再问
```

**更新命令分 agent 环境**：
- Claude Code: `/plugin update stock-deep-analyzer`
- git clone: `cd UZI-Skill && git pull`
- Hermes: `hermes skills update wbh604/UZI-Skill/skills/deep-analysis`

### 性能与可靠性

- **GitHub API 缓存 6h** · 防 60 req/h 未认证限流 · cache 新鲜时直接读 `cached_latest` 判断，不打 API
- **timeout 5s** · GFW / 慢网络快速 fail · silent skip 不阻塞主流程
- **semver 匹配**：仅对正式 tag `v2.x.y` 比较 · pre-release / dev branch 不弹
- **env 禁用**：`UZI_NO_UPDATE_CHECK=1` 跳过全部检查（CI / Codex 推荐设）

### 测试

新增 `tests/test_v2_14_0_update_check.py` · 13 个回归：
- `_parse_semver` 基础 + 边界
- `_newer` 比较
- env 禁用
- 同版本不弹 / 新版本弹
- skip 同版不再弹 / skip 后新版再弹
- 网络失败 silent skip
- cache 生效不重复打 API
- handle_answer y/s/n 三路径
- `format_prompt` 含三选项

**全量 230 passed**（baseline 217 + 13 新）。

### 版本

- `2.13.7 → 2.14.0`（minor bump · 新增用户可见功能）
- 4 manifest 同步
- Branch: `feature/v2.14.0-auto-update`
- Tag: `v2.14.0`

---

## v2.13.7 — 2026-04-19 (wire new sources · 把 registry 登记的源真正接入 fetcher)

> **背景**：v2.13.4 / v2.13.6 共加了 16 个新源到 `data_source_registry.py`，但只是 registry 层面的登记，实际 fetcher 并没用它们。v2.13.7 把这些源真正接入到对应 fetcher 里，让数据流通。

### 核心改动

| 模块 | 新接入源 | 说明 |
|---|---|---|
| `fetch_events.py` (15_events) | `news_providers` (jin10/em_kuaixun/em_stock_ann/ths) | 4 源统一聚合 · 补 cninfo + ak 盲区 |
| `fetch_sentiment.py` (17_sentiment) | `news_providers` | 情绪增强 · 新闻正负词融合 heat 分数 |
| `fetch_policy.py` (13_policy) | `_fetch_cfachina_titles` | 期货/商品 industry 专用 · 期货协会权威源 |
| `lib/data_sources.py::_kline_us_chain` | `_yahoo_v8_chart` HTTP | 绕开 yfinance cookie/crumb 机制 · 直连 Chart v8 |
| `lib/data_sources.py::_kline_hk_chain` | `_yahoo_v8_chart` HTTP | 港股第 4 层兜底 · 前 3 层（东财/新浪/yf）全败时用 |

### 新增 `lib/news_providers.py`（160 行）

统一聚合 4 个财经新闻源：
- `fetch_jin10()` - 解析 `var newest = [...]` JS 变量（跳 JSONP 包装）
- `fetch_em_kuaixun()` - 解析 `var ajaxResult={LivesList:[...]}` · 兼容无尾 `;` 响应
- `fetch_em_stock_ann(stock_code)` - JSON API · 支持按 code 过滤公告
- `fetch_ths_news_today()` - HTML regex · `<a class="title">` 提取

**关键 API**：`get_news_multi_source(stock_code, stock_name, limit_per_source)` → `{sources: {...}, total_hits, sources_ok}` · 10 min 文件缓存在 `.cache/_global/news/`.

### 新增 `_yahoo_v8_chart(symbol, range_)`

直连 `query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range={range}` · 429 自动 retry 一次 · 返归一到东财中文列（日期/开盘/收盘/最高/最低/成交量）· 兼容 AAPL / 0700.HK / 9988.HK.

### 实测

```bash
python3 lib/news_providers.py "" ""
# sources_ok: 4/4 · total_hits: 31

python3 -c "from lib.data_sources import _yahoo_v8_chart; print(len(_yahoo_v8_chart('AAPL','1mo')))"
# 22
python3 -c "from lib.data_sources import _yahoo_v8_chart; print(len(_yahoo_v8_chart('0700.HK','1mo')))"
# 21
```

### 测试

新增 `tests/test_v2_13_7_wire_new_sources.py` · 12 个回归：
- `news_providers` 模块存在性 + NewsItem dataclass
- `fetch_jin10` / `fetch_em_kuaixun` 正则解析（mocked HTTP）
- `fetch_events` / `fetch_sentiment` 接入 `get_news_multi_source` 调用路径
- `_yahoo_v8_chart` 解析 response + 429 retry 逻辑
- `_kline_us_chain` yf/ak 全失败时兜底到 v8
- `fetch_policy` 期货 industry 调 cfachina · 非期货不调

**全量 217 passed**（baseline 205 + 12 新）。

### 影响面

- **A 股 15_events 数据密度提升**：之前仅 cninfo + ak.stock_news_em，过滤"资金流向"等噪音后常 < 3 条；加入 4 源聚合后 10-30 条可用新闻。
- **17_sentiment heat 更准**：new_hit * 2 分 + 新闻正负词二次融合。
- **美股/港股 K 线稳定性**：yfinance 2026 年多次因 cookie 机制失败；Yahoo v8 HTTP 直连是可靠兜底。
- **期货/商品类 13_policy 更权威**：cfachina 首页标题抽取（行业论坛/峰会/研讨会）· 仅对"期货/衍生品/商品/金融/证券"industry 触发，不影响其他。

### 版本

- `2.13.6 → 2.13.7`
- 4 manifest 同步（`.claude-plugin/plugin.json` / `.cursor-plugin/plugin.json` / `package.json` / `.version-bump.json`）
- Branch: `feature/v2.13.7-wire-new-sources`
- Tag: `v2.13.7`

---

## v2.13.6 — 2026-04-19 (新增 6 个经 curl 验证的期货 + 财经新闻源)

> **用户提供第二波 Grok 清单**（期货 + 财经新闻 · 10+ 端点）· 批量 curl 真实验证 · 6 有效新源登记

### 新增 6 源（SOURCES 64 → 70）

**新闻类（财联社替代方案）：**

1. **金十数据 `jin10.com/flash_newest.js`** ⭐
   - 实时快讯 JSON · 38KB · 含国内外宏观/政策/突发/行情
   - 覆盖 A/H/U 三市场 · 标 `15_events` + `17_sentiment` + `3_macro` + `13_policy`
   - akshare 也有封装 `ak.js_news()` · 双重接入
   - **这是"类财联社"的最佳零 Key 替代**

2. **东财快讯 `newsapi.eastmoney.com/kuaixun/v1/`**
   - 62KB 实时快讯 JSON · 类财联社风格
   - 覆盖 `15_events` + `17_sentiment`

3. **东财上市公司公告 `np-anotice-stock.eastmoney.com/api/security/ann`**
   - JSON 公告流 · 支持 `page_size` + `ann_type` 过滤
   - 替代 cninfo 做高频轮询
   - 覆盖 `15_events`（A 股）

4. **同花顺今日快讯 `news.10jqka.com.cn/today_list/`**
   - 68KB HTML · 财经/行情/行业快讯聚合
   - 覆盖 A/H · `15_events` + `17_sentiment`

**期货类：**

5. **99 期货网 `www.99qh.com`**
   - 中国最全期货库存/仓单/现货价/基差数据
   - 覆盖 `8_materials` + `9_futures`
   - HTML 解析（141KB）

6. **中期协 `www.cfachina.org`**
   - 官方协会公告/法规 · 权威政策源
   - 覆盖 `9_futures` + `13_policy`

### 验证无效不入库的 7 源

| 源 | HTTP | 原因 |
|---|---|---|
| 新浪期货 `hq.sinajs.cn/list=CFF_RE_IF0` | 403 | 国内反爬 |
| 金十 flash-api `flash-api.jin10.com` | 502 | 端点挂（但 flash_newest.js 在） |
| 新浪 RSS china / finance roll | 404 | URL 已撤 |
| 央视 RSS `news.cntv.cn/rss/rss.jsp` | 404 | RSS 不再维护 |
| 网易 RSS `rss.163.com` | 0 | 连接不通 |
| 雪球 batch quote API | 400 | 需 cookie/登录 |
| 财联社官方 REST | — | Grok 自己说明没有公开 API |

### akshare 封装（已通过 akshare tier 覆盖 · 本版不重复登记）

- `ak.js_news()` · 金十数据
- `ak.futures_news_baidu()` · 百度期货新闻
- `ak.get_cffex_daily()` / `get_dce_daily()` / `get_czce_daily()` · 四大交易所
- `ak.futures_zh_spot()` / `futures_zh_daily_sina()` · 期货行情

### 回归测试

- 新增 `tests/test_v2_13_6_news_futures.py` · 10 用例
- 覆盖：6 新源 ID / 维度标注 / market 覆盖 / 无重复 / `http_sources_for('15_events', 'A')` 包含新源
- 全量 **205 passed**（v2.13.5 195 + 新 10）

### 升级

`git pull origin main` · registry 立即生效 · 6 新源已登记可被 `http_sources_for` 查到 · fetcher 接入下版本按需做

### 展望 · 真正的财联社替代栈

推荐优先使用组合：
- **实时快讯**：`ak.js_news()`（金十 akshare 封装）或直连 `jin10.com/flash_newest.js`
- **公司公告**：`np-anotice-stock.eastmoney.com/api/security/ann`（东财 JSON）或 cninfo
- **财经聚合**：`news.10jqka.com.cn/today_list/`（同花顺 HTML）

---

## v2.13.5 — 2026-04-19 (NetworkProfile 自适应 + agent HARD-GATE 主动触发 Playwright)

> **用户反馈**："我使用下来，并没有遇到模型主动使用 Playwright 的问题" · 诊断发现 agent role-play 阶段根本没教过要调 Playwright · 脚本自动跑 OK 但 agent 不补漏

### 三层解决

**Layer 1 · `NetworkProfile` 升级**（`lib/network_preflight.py`）

从 v2.10.2 的 "5 个国内 TCP connect" 升级到：
- **9 个目标 3 组**：国内（push2/cninfo/xueqiu）+ 境外（yahoo/coingecko/baike）+ 搜索（ddgs/baidu/github）
- **代理检测**：扫 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY 大小写 6 个 env
- **结构化输出**：`NetworkProfile(domestic_ok, overseas_ok, search_ok, has_proxy, recommendation, severity)`
- **缓存到 `.cache/_global/network_profile.json`** · 5min TTL · agent 介入时直接读

诊断输出：
```
🌐 网络预检 (9/9 通 · 均延迟 4ms · proxy=no)
  [国内 3/3] ✓ push2.eastmoney.com · cninfo · 雪球
  [境外 3/3] ✓ query1.finance.yahoo.com · api.coingecko.com · baike.baidu.com
  [搜索 3/3] ✓ duckduckgo.com · www.baidu.com · api.github.com
  ✓ 全网通畅 · Playwright 可抓境内+境外所有源
```

**Layer 2 · Agent HARD-GATE-PLAYWRIGHT-AUTOFILL**（`SKILL.md` / `AGENTS.md` / `commands/analyze-stock.md`）

明确要求 agent 在 stage1 → stage2 **之间**：

```python
# 1. 读网络 profile
net = json.loads(Path(".cache/_global/network_profile.json").read_text())
print(net["recommendation"])  # 人读的建议

# 2. 读自查 issues 找低质量维度
issues = json.loads(Path(f".cache/{ticker}/_review_issues.json").read_text())
low_q = [i["dim"] for i in issues["issues"]
         if i.get("category")=="data" and i.get("severity") in ("critical","warning")]

# 3. 主动强制跑 Playwright 兜底
if low_q:
    os.environ["UZI_PLAYWRIGHT_FORCE"] = "1"
    from lib.playwright_fallback import autofill_via_playwright
    autofill_via_playwright(raw, ticker)
```

**绝对禁止**：看到 `data.growth = "—"` 直接在 commentary 里写"增速待补充"——应该先让 Playwright 抓一次。

**Layer 3 · `DIM_STRATEGIES` 按 NetworkProfile 自适应**（`lib/playwright_fallback.py`）

每个维度声明所需网络能力：
```python
DIM_NETWORK_REQUIREMENTS = {
    "4_peers":       ("domestic",),              # 雪球
    "7_industry":    ("domestic", "search"),     # 百度搜索
    "18_trap":       ("domestic", "search"),     # 小红书搜索
    "14_moat":       ("domestic",),              # 百度百科
    # ... 10 个维度都声明
}
```

运行时按 profile 过滤：
- `search_ok=False` → 7_industry / 18_trap 直接跳（跳前打印原因）
- `domestic_ok=False` → 10 维全跳
- 日志明确："🌐 网络过滤 · 跳过 2 维: 7_industry(search 不通), 18_trap(search 不通)"

### 回归测试

- 新增 `tests/test_v2_13_5_preflight_adaptive.py` · **14 个用例**
- NetworkProfile：proxy env / recommendation 变化 / cache 读写 / stale 重测
- DIM_STRATEGIES 自适应：domestic 不通全跳 / search 不通部分跳 / 全通全保留
- HARD-GATE 文档：SKILL.md / AGENTS.md / commands 都含 `autofill_via_playwright` 字面量
- 全量 **195 passed**（v2.13.4 181 + 新 14）

### 用户影响

从此 agent 遇到空数据会**主动**开浏览器补：
- v2.13.2 autofill_via_playwright 只在 stage1 末尾跑一次 · 漏补的维度 agent 没补
- v2.13.5 agent role-play 前 **强制再跑一次 FORCE 模式** · 覆盖 stage1 漏的

配合 v2.13.2 `UZI_PLAYWRIGHT_FORCE=1` + v2.13.1 全 10 维覆盖 + v2.13.0 三档分级 · 形成完整 Playwright 层。

### 升级

`git pull origin main` · 下次 agent 读 SKILL.md 自动按新 HARD-GATE 执行

---

## v2.13.4 — 2026-04-19 (新增 10 个经 curl 验证的无 Key 公开数据源)

> **用户提供 Grok 清单 20+ 个 "全网最全" 无需 Key 的行情接口** · 批量 curl 真实验证 · 过滤无效项 · 9 有效加密源 + 1 Yahoo Chart v8 + 1 腾讯港股 quote 注册入库

### 验证方法

所有端点经 `curl -w "%{http_code}"` 真实 HTTP 请求 · 国内网络环境 · 8s 超时 · 记录 response size + 前 120 字节样本

### 新增 10 源（`data_source_registry.py` SOURCES 54→64）

**Yahoo Chart v8**（US+HK · K线）· v7 quote 已被 Yahoo 关闭（401）· v8 仍公开可用

**腾讯港股 quote**（HK · basic）· `qt.gtimg.cn/q=hk00700` · 国内外都通

**加密源 8 个**（U · 3_macro 维度 · 作全球流动性 / 资金流参考）：
1. CoinGecko Simple Price · `api.coingecko.com/api/v3/simple/price`
2. CoinGecko Markets · `api.coingecko.com/api/v3/coins/markets`
3. OKX 现货 tickers · `okx.com/api/v5/market/tickers?instType=SPOT`（国内访问不受限）
4. KuCoin 24h stats
5. Kraken 公开成交
6. Gemini 行情
7. CoinLore 全量币种（36KB JSON 快照）
8. GeckoTerminal DEX networks

### 验证为无效不入库的 5 源

| 源 | 原因 |
|---|---|
| Sina `hq.sinajs.cn/list=` | 403 Forbidden 国内反爬 |
| Netease `quotes.money.163.com/service/chddata.html` | 502 Bad Gateway |
| Yahoo v7 `v7/finance/quote` | 401 Unauthorized · Yahoo 已关闭公开访问 |
| Binance spot/24hr/futures | 451 Restricted Location · 国内 IP 封 |
| CoinCap / CoinDesk v1 | 连接失败 |

### 使用场景

- `data_sources.fetch_kline` 美股/港股 fallback 链加 yahoo_chart_v8
- `fetch_macro` 加 Crypto 作流动性指标（BTC 跌破某关键价 · A 股风险偏好下行信号）
- 港股基本面加腾讯 quote 作无反爬第 N 层备源

### 回归测试

- 新增 `tests/test_v2_13_4_new_sources.py` · 8 个用例
- 验证 10 个新源按 ID 可查 / 加密源全标 3_macro / yahoo_v8 覆盖 U+H 2_kline / 无重复 ID / http_sources_for 查询正确
- 全量 **181 passed**（v2.13.3 173 + 新 8）

### 升级

`git pull origin main` · registry 立即生效 · 后续 fetcher 扩展可复用（v2.13.4 仅登记 · 未自动接入各 fetcher · 下版本按需接入）

---

## v2.13.3 — 2026-04-19 (51 评委规则全员历史立场还原)

> **用户反馈**："林奇是不是有点激进？他历史上的持仓和操作，麻烦你核对一下" · 中际旭创 300308.SZ 实测发现 **19 人给 100 分** 严重不合理，多位评委立场与历史不符

### 根因诊断

从 300308 面板扫描 v2.13.2 分数分布：
- 19 人给 100 分（含 13 位游资 + 林奇 + 索罗斯 + 段永平 + 张坤 + 邓晓峰）
- 木头姐 13 分看空（CPO 本是她核心赛道，被判 0% 行业增速）
- F 组游资"市值 9456 亿 > 150 亿 = 看多 100" / "超 80 亿 = 看空"（反向 bug）

### 5 处规则修复

**Fix 1 · F 组游资射程**
- `seat_db.is_in_range` 加隐式 500 亿大市值上限（章盟主 allowlist 除外，历史做过茅台大盘）
- `investor_evaluator._is_youzi_out_of_range` 前置检查 · 超射程直接 skip 不打分
- `_youzi_base_rules` 移除 min_mcap/max_mcap 作为 Rule（避免"市值超标"反向打分）
- **300308 效果**：F 组 22/23 人正确 skip（原 13 人错打高分）

**Fix 2 · 索罗斯反身性方向**
- 原 bug：`abs(upside_to_target) > 10` · 目标价 -63% 也被判"反身性差 = 看多 100"
- 修：拆两条规则
  - `sentiment_long_reflex` · 只在 upside > +10% 时 pass（做多反身性）
  - `sentiment_short_reflex_penalty` · upside < -15% 扣分（识别市场狂热）
- **300308 效果**：索罗斯 100 → 42 neutral · "无做多反身性空间"

**Fix 3 · 林奇 PEG 严格化 + PE 40 红线**
- 依据 *One Up on Wall Street (1989)* / *Beating the Street (1993)*：
  - PEG ≤ 1 理想（Taco Bell 0.6 / Hanes 0.2 / Fannie Mae 0.6 均低于 1）
  - PE > 40 "like buying a Rolls Royce" · 林奇警戒线
  - Fast grower sweet spot 20-50%
- 原版单条 `peg_reasonable PEG < 1.5` 过松 · 拆 6 条：
  - `peg_ideal` PEG < 1（5 分）
  - `peg_acceptable` PEG 1-1.5（3 分）
  - `pe_not_rolls_royce` PE < 40（3 分）← 新增
  - `fast_grower_zone` 20-50%（3 分）
  - `understandable` + `research_support`（2+2 分）
- **300308 效果**：林奇 100 → 38 neutral · "PE 63 · Rolls Royce 不是必要品"

**Fix 4 · 木头姐颠覆性判定**
- 两处 bug：
  - 字段名错：读 `industry_growth_pct` · 实际 stock_features 设的是 `industry_growth` · 中际旭创读成 0 判"增长太慢"
  - 白名单缺 CPO/光模块/算力/数据中心/HBM · AI 基建本是 ARK 核心赛道
- 修：字段兼容读 · 白名单加 AI 算力相关 12 个关键词
- **300308 效果**：木头姐 13 bearish → 80 bullish · "行业增速 40% — S 曲线拐点"

**Fix 5 · 中国价投派 PE 红线**
- 段永平：历史买苹果 PE 18 / 茅台 PE 30 / 腾讯 PE 25 · 对 PE 50+ 永远"贵了"
- 张坤：重仓茅台/五粮液/腾讯 PE 15-35 区间
- 邓晓峰：偏左侧风格 · 白酒/地产/银行/周期股 PE 都偏低
- 各加 1 条 PE 红线规则（段 PE<40 · 张 PE<40 · 邓 PE<35）
- **300308 效果**：段永平 100→84 · 张坤 100→78 · 邓晓峰 100→76（仍看多但不再狂热）

### 评分分布对照（300308.SZ）

| 桶 | v2.13.2 | v2.13.3 |
|---|---|---|
| 100 分 | **19 人** | **5 人** |
| 70-99 | 2 | 12 |
| 40-69 | 7（neutral/bearish） | 7 |
| < 40 | 9（含 4 游资 misjudged） | 4 |
| skip | 1 | **23**（F 组 22 + 索普） |
| consensus | 78 | **81.4**（分母 28，质量提升） |

### 回归测试

- 新增 `tests/test_v2_13_3_investor_rules.py` · **15 个用例**
  - Fix 1 · 4 游资射程 scenarios
  - Fix 2 · 索罗斯 3 方向（看多/看空/neutral）
  - Fix 3 · 林奇 3 PEG 区间
  - Fix 4 · 木头姐 CPO 识别 + 字段兼容
  - Fix 5 · 段永平/张坤 PE 红线 + 护栏
- 全量 **173 passed**（v2.13.2 158 + 新 15）

### 升级

`git pull origin main` · 老 cache 下次 stage1 自动用新规则重算 panel.json · 无需 --no-resume（v2.9 的 panel 不 cache · 每次都重算）

---

## v2.13.2 — 2026-04-19 (Playwright 触发逻辑升级 · 数据质量感知 + FORCE flag)

> **用户反馈**："有很多网站爬不到内容，也没有拉起 Playwright" · 诊断发现三个根因：(1) v2.13.1 之前 cache 没 Playwright 字段 (2) `_dim_needs_fallback` 只看 `len(data)` 不看值质量 (3) skip 时无日志告诉用户为什么

### 根因诊断（中际旭创 cache 实测）

| 维度 | data 字段数 | 其中有效 | 质量 | v2.13.1 判定 | v2.13.2 判定 |
|---|---|---|---|---|---|
| 7_industry | 12 | 3 (`industry`/`lifecycle`/`cninfo_metrics`) | 25% | "不需要兜底" ❌ | "需要兜底" ✅ |
| 4_peers (self-only) | 7 | 5 但 fallback=True | — | 不触发 ❌ | 触发 ✅ |
| 8_materials | 8 | 全是 "—"/空 | ~0% | "不需要兜底" ❌ | "需要兜底" ✅ |

### v2.13.2 核心改进

**1. `_dim_needs_fallback` 数据质量感知**

新加 `_dim_quality_score(data)` 计算有效字段占比：
- 排除 `_` 前缀的诊断字段（如 `_autofill` / `_debug`）
- 统计非空值：非 `None` / 非 `"—"/"N/A"/""` / 非空 list/dict
- 阈值 `QUALITY_THRESHOLD = 0.5` · 低于 50% 触发兜底

触发条件扩展：
- data 为空 → 触发（原版）
- **`dim.fallback=True` → 总是触发**（新增 · 不再看 `len(data)<4`）
- **quality < 50% → 触发**（核心改进）

**2. `UZI_PLAYWRIGHT_FORCE=1` · kill switch**

用户发现自动判定太保守时可强制重抓：
```bash
UZI_PLAYWRIGHT_FORCE=1 python3 run.py 300308.SZ --depth deep --no-resume
```
忽略 `_dim_needs_fallback` · 对所有 `profile.playwright_dims` 维度强制跑。

**3. 清晰的 skip/run 日志**

```
🎭 profile=deep · playwright_dims=10 · FORCE=False
⏭  4_peers         skip · 有效字段占比 71% 已达标
✓  7_industry      via playwright · 字段: baidu_search_titles, baidu_search_descs
✗  18_trap         页面抓取失败或解析无数据
📊 Playwright 兜底 · 尝试 5 · 成功 3 · 失败 1 · 跳过 1（数据已足）
```

禁用时也明确说明：
```
ℹ️  Playwright skip · profile=medium · opt-in 未启用 · export UZI_PLAYWRIGHT_ENABLE=1 启用后重跑
```

### 回归测试

- 新增 5 个用例：
  - `test_dim_quality_score_detects_mostly_empty` · 12 keys 中 9 个 "—" → quality 25% → 触发
  - `test_dim_quality_score_skips_ignoring_underscore_keys` · `_` 前缀不计 quality
  - `test_autofill_triggers_on_low_quality_data` · 5 个全 "—" 的 key 应触发 Playwright
  - `test_force_flag_ignores_quality_check` · FORCE=1 忽略 quality
  - `test_autofill_summary_has_disabled_reason_when_off` · lite / medium 未 opt-in 都有明确 `disabled_reason`
- 全量 **158 passed**（v2.13.1 153 + 新 5）

### 升级

`git pull origin main` · 老 cache 不会自动重跑 · `--no-resume` 能立即看到 Playwright 触发。

**强制兜底（解决"爬不到也没拉起 Playwright"）**：
```bash
export UZI_PLAYWRIGHT_FORCE=1
python3 run.py 300308.SZ --depth deep --no-browser --no-resume
```

---

## v2.13.1 — 2026-04-18 (Playwright 全 10 维覆盖 · 开源研究场景扩展)

> **用户明确本项目是开源研究场景，反爬/合规不受限制**。v2.13.0 Codex review 为保守起见排除了 5 维，本版全部加回。

### 策略调整

| 维度 | v2.13.0 状态 | v2.13.1 状态 | 目标页 |
|---|---|---|---|
| 4_peers | ✅ medium+deep | ✅ medium+deep (不变) | 雪球 `/S/{sym}` |
| 8_materials | ✅ medium+deep | ✅ medium+deep (不变) | 东财 F10 |
| 15_events | ✅ medium+deep | ✅ medium+deep (不变) | cninfo 公告 |
| 17_sentiment | ✅ medium+deep | ✅ medium+deep (不变) | 雪球讨论区 |
| 3_macro | ✅ deep-only | ✅ deep-only (不变) | stats.gov.cn |
| **7_industry** | ❌ 排除 | ✅ **medium+deep** | 百度搜索 `{行业}+景气度` |
| **14_moat** | ❌ 排除 | ✅ **medium+deep** | 百度百科公司词条 |
| **13_policy** | ❌ 排除 | ✅ **deep** | 证监会 csrc.gov.cn |
| **18_trap** | ❌ 排除 | ✅ **deep** | 小红书搜索 `{name}+老师+推荐` |
| **19_contests** | ❌ 排除 | ✅ **deep** | 雪球实盘组合排行榜 |

### 三档维度扩展

| profile | v2.13.0 | v2.13.1 |
|---|---|---|
| ⚡ lite | 0 维 off | 0 维 off (不变) |
| 📊 medium | 4 维 opt-in | **6 维** opt-in（加 7_industry + 14_moat） |
| 🔬 deep | 5 维 default | **10 维** default（全覆盖）|

### 新增 5 个 parser（`lib/playwright_fallback.py`）

- `_strategy_7_industry` · 百度搜索 `{行业} 行业景气度 增速 市场规模` · 抓 `<h3>` 标题 + `.content-right` 描述
- `_strategy_14_moat` · 百度百科 `/item/{公司名}` · 抓 `.lemma-summary` 简介 + `.basicInfo-item` 信息栏
- `_strategy_13_policy` · 证监会 `csrc.gov.cn/common_list.shtml` · 抓政策动态标题列表
- `_strategy_18_trap` · 小红书 `xiaohongshu.com/search_result` · 搜 `{name} 老师 推荐` · 命中数作杀猪盘信号
- `_strategy_19_contests` · 雪球 `xueqiu.com/cube/rank/list` · 抓组合排行 JSON · 提取 name + total_gain

### 回归测试

- 更新 `tests/test_v2_13_playwright_strategy.py` · 22 个用例
- `test_dim_strategies_has_5_entries` → `test_dim_strategies_has_10_entries`
- 移除 `test_excluded_dims_not_in_strategies`（不再排除）
- 新增 `test_all_parsers_callable_and_return_none_on_empty_html` · 10 个 parser 都验证 fetch_url 返 None 时 graceful 返 None
- 新增 `test_medium_dims_subset_of_deep` · 护栏：medium 必须是 deep 的子集
- 全量 **153 passed**（v2.13.0 152 + 新 1）

### BUGS-LOG 契约修订

v2.13.0 BUGS-LOG 里关于"不能不经 Codex review 就加回排除维度"的契约作废 · 本版明确用户场景是开源研究不受合规限制 · 直接加回。

---

## v2.13.0 — 2026-04-18 (Playwright 通用兜底 · 按三档 profile 分级)

> **用户要求"所有爬不到数据的都用 Playwright + 自动装"。经 Codex 架构 review 后按现有三档深度分级制定策略 · 避免对轻量用户添加不必要开销**

### 核心设计

**按 AnalysisProfile 分级**（扩展 `playwright_mode` + `playwright_dims` 两个字段）：

| profile | Playwright 模式 | 覆盖维度 | 自动装 Chromium |
|---|---|---|---|
| ⚡ **lite** (30s-1min) | `off` 完全禁用 | 无 | 不涉及 |
| 📊 **medium** (2-4min) | `opt-in` · `UZI_PLAYWRIGHT_ENABLE=1` 启用 | **4 维**：`4_peers` / `8_materials` / `15_events` / `17_sentiment` | ❌ 打印命令让用户手动装 |
| 🔬 **deep** (15-20min) | `default` 默认启用 | **5 维**：medium 4 维 + `3_macro` | ✅ 首次 y/n 交互确认后自动装 |

### 新增模块

**`lib/playwright_fallback.py`** (~320 行)：
- `is_playwright_enabled()` · 按 profile 判断
- `ensure_playwright_installed(auto)` · 分档装 · y/n 交互 · pypi 国内镜像 fallback
- `fetch_url(url, wait_for, timeout)` · 通用 headless Chromium 抓取 · 随机 0.5-1.5s sleep 反风控
- `DIM_STRATEGIES` · 5 维策略映射 (URL 模板 + parser)
- `autofill_via_playwright(raw, ticker)` · post-fetch 兜底 · 类 `_autofill_qualitative_via_mx` 模式

**`lib/junk_filter.py`** · 抽离 v2.12.1 `_is_junk_autofill` 共用（Playwright 抓回来的数据也走垃圾过滤）

### Codex 架构 review 排除的维度

经 Codex review 明确不加：
- ❌ `7_industry` → 百度搜索页信噪比差（保持 `search_trusted` site: 权威域方案）
- ❌ `14_moat` → 百度百科质量差
- ❌ `13_policy` → `search_trusted` site: 限权威域已够
- ❌ `18_trap` → 小红书/抖音反爬严 + UGC 合规风险
- ❌ `19_contests` → `lib/xueqiu_browser` 已有专用登录路径

这些放在 BUGS-LOG 的"未来改该区域注意事项"里作为契约：**不能不经 Codex review 就加回来**。

### 自动装策略（deep 档）

```
deep 模式触发 → 检测 playwright + chromium
  ├─ 已装 → 直接跑兜底
  ├─ 未装 → 打印 "需要下载 ~180 MB，继续？(y/N)"
  │    ├─ 用户 y → pip install (国内镜像 fallback) + playwright install chromium
  │    │    ├─ 成功 → 继续
  │    │    └─ 失败 → warning · 跳过 Playwright · 主流程不阻塞
  │    └─ 用户 n/空 → 跳过 Playwright · 其他兜底仍跑
  └─ 任何 exception → warning · 跳过
```

### 反爬 / 合规原则

- 只抓官方权威页：`xueqiu.com/S/{sym}` public / `cninfo.com.cn` / `em.eastmoney.com` F10 / `stats.gov.cn`
- 每次请求随机 `0.5-1.5s` sleep
- **不抓 UGC 平台**（小红书/抖音/微博）· 这些放 17_sentiment 的 ddgs 链

### 回归测试

- 新增 `tests/test_v2_13_playwright_strategy.py` · **21 个用例**（全 mock · 零真实浏览器）
  - 3 档 profile 字段 · `is_enabled` 三场景 · `ensure_installed` 5 路径（已装 / 未装 opt-in / 未装 deep y / 未装 deep n / chromium fail）
  - `autofill` 白名单 / 垃圾过滤 / 已有数据跳过
  - `DIM_STRATEGIES` 5 维 · 排除维度护栏 · `junk_filter` 模块 · BC delegate
- 全量 **152 passed**（原 131 + 新 21）

### 兼容性

- v2.12.1 的 `_is_junk_autofill` 保留（delegate 到 `lib/junk_filter.is_junk_autofill_text`）· 老代码 import 不破
- v2.12.1 的 `lib/xueqiu_browser.fetch_peers_via_browser` 保留 · 作为**登录态专用**路径（`UZI_XQ_LOGIN=1`）· 与新的通用 `fetch_url` 分工：
  - 登录态 → xueqiu_browser（cookie 持久化 + F10 页深度抓）
  - 匿名 → playwright_fallback.fetch_url（轻量 · 速度快）

### 升级

`git pull origin main` · 默认对 lite/medium 用户**零感知**（不装不跑）· deep 用户首次触发会看到 y/n 提示。

---

## v2.12.1 — 2026-04-18 (4 个报告板块空数据 / 错数据修复)

> **用户实测中际旭创（300308.SZ）发现 4 处 数据层 / 模型层 bug · 一次性 hotfix**

### 用户反馈

- 同行对比板块完全空（"peer_table: []"）
- 行业景气 growth / TAM / 渗透率 永远 "—"
- 原材料 core_material 显示 "类型；类型"（MX prompt 残留）
- BCG 矩阵：**所有股票都归 Dog 瘦狗 · 考虑剥离**（中际旭创作为 CPO 全球龙头被归 Dog 明显错误）

### 4 个 Bug 根因 + 修复

**Bug 1 · `4_peers` 东财 push2 挂了无 fallback**（`fetch_peers.py`）
- 原版：主链挂了 `peer_table/peer_comparison` 整表空
- 修：三层 fallback 链 + 一层保底
  - Tier 1 主链（不变）
  - Tier 2 · 2.5s retry（网络抖动）
  - Tier 3 · **雪球 Playwright 登录态**（用户 opt-in `UZI_XQ_LOGIN=1`）· 复用 `lib/xueqiu_browser.py` v2.7.1 基础设施 · 新加 `fetch_peers_via_browser(code)` 从 `xueqiu.com/S/{sym}` 正则抽同板块股票
  - Tier 4 · 保底返公司自己一行 + `fallback: True` + `fallback_reason` 字段让 agent 识别降级

**Bug 2 · `7_industry` growth/tam/penetration 永远 "—"**（`fetch_industry.py`）
- 原版 3 个问题叠加：① growth regex 不带上下文，被 "PE 25%" 抢先匹配 ② penetration 完全没 regex ③ `all_bodies` 只拼 body 不含 title（关键数字常在 title 如 "净利齐涨超40%"）
- 修：
  - growth regex 上下文感知 · 关键词 `增长/增速/CAGR/涨超/涨幅/暴涨/翻倍/提升` + 0-20 字符 + %
  - 加 TAM 上下文（市场规模/规模达/产业规模/TAM）
  - 加 penetration_heuristic 渗透率 regex
  - `main` line 228 · penetration 补 dynamic 兜底（原版遗漏）
  - all_bodies 改为拼 title + body

**Bug 3 · `core_material = "类型；类型"` MX 垃圾数据**（`run_real_test.py`）
- 原版：`_autofill_qualitative_via_mx` 后处理阶段直接把 MX API 返回写入字段，无质量校验
- 修：
  - 加 `_is_junk_autofill(text)` 函数 · 检测 长度<5 / 黑名单短语 / 分号分隔全同
  - `_AUTOFILL_JUNK_PATTERNS` 模块级常量便于扩展
  - MX 和 ddgs 返回后分别过滤 · 垃圾 → `text = ""` 不写入
  - 保留 `_autofill_failed` 让 agent 明确"数据不足"

**Bug 4 · BCG 所有股归 Dog**（`lib/stock_features.py` + `lib/deep_analysis_methods.py`）
- 原版：
  - `stock_features.py:340-341` 硬编 `f["market_share"] = _f(industry.get("market_share"), default=10)` · 但 `industry.market_share` key 从未被任何 fetcher 写入 · 永远 default 10
  - BCG 阈值 `share>15 AND growth>10` · 默认 10/10 不满足任何 >15 条件 → 必落 Dog
- 修：
  - `stock_features.py` 真实算 `market_share = 公司市值 / 行业总市值 × 100`（数据源 `basic.market_cap_yi` / `industry.cninfo_metrics.total_mcap_yi`）
  - `industry_growth` 从 `industry.growth` 字符串 regex 解析百分比（Bug 2 修复后有真实值）
  - BCG 阈值调整 · Star `share>3 AND growth>15` / Cash Cow `share>3 AND growth≤15` / Question Mark `share≤3 AND growth>15` / Dog `share≤3 AND growth≤15`（`share>15` 对 A 股单股非现实）
  - `default=10` → `default=0`（数据缺失明确落 Dog 而不是假数据）

### 回归测试

- 新增 `tests/test_v2_12_1_data_fixes.py` · **16 个用例**（4 bugs × 多场景 + 护栏）
- 更新 `test_no_regressions.py::test_hk_branches_isolated` HK 分支独立 try/except
- 全量 **131 passed**（原 115 + 新 16）

### 中际旭创端到端验证（`300308.SZ --depth medium --no-resume`）

| 板块 | v2.12.0 | v2.12.1 |
|---|---|---|
| 4_peers peer_table | `[]` 空 | 1 行（公司自己）+ fallback_reason 说明降级 |
| 7_industry.growth | `"—"` | **"40%/年"** |
| 8_materials.core_material | `"类型；类型"` | 真实公司概况 ddgs 结果 |
| BCG category | Dog 瘦狗 考虑剥离 | **Star (明星)** · market_share 5.5% · growth 40% |

### 致谢

本版用户反馈驱动 · 论坛 + 微信群实测。Bug 4 BCG 是全部历史版本都存在的模型 bug，中际旭创测试暴露出来后一并修复。

### 升级

`git pull origin main` · 老 cache 不会自动重跑 · 重新跑 `--no-resume` 能立即看到 4 个板块改观。

---

## v2.12.0 — 2026-04-18 (6 平台社交热榜聚合)

> **参考 [run-bigpig/jcp](https://github.com/run-bigpig/jcp)（韭菜盘 AI · 851 ⭐）的 `internal/services/hottrend` 设计，补 DuckDuckGo web search 的盲区**

### 背景

v2.11 的 `17_sentiment` 维度主要靠 ddgs（DuckDuckGo + site: 限定），但：
- 抖音/快手/小红书/B 站 retail investor 集中地在 ddgs 爬不到
- 散户情绪和杀猪盘题材经常先在这些平台发酵

jcp 已经开源了 6 平台热榜聚合，直接抄过来。

### 新增

**`skills/deep-analysis/scripts/lib/hottrend.py`** (~240 行)

| 平台 | API | 返回 |
|---|---|---|
| 微博 | `weibo.com/ajax/side/hotSearch` | 50 条实时热搜 |
| 知乎 | `zhihu.com/api/v3/feed/topstory/hot-list-web` | 50 条热榜 |
| 百度 | `top.baidu.com/api/board?platform=wise&tab=realtime` | 实时榜单 |
| 抖音 | `douyin.com/aweme/v1/web/hot/search/list/` | 搜索热点 |
| 头条 | `toutiao.com/hot-event/hot-board/` | 热点事件 |
| B 站 | `s.search.bilibili.com/main/hotword?limit=50` | 全站热搜 |

**核心 API**：
```python
from lib.hottrend import get_hot_mentions
result = get_hot_mentions("贵州茅台")
# → {"total_hits": 3, "by_platform_count": {"weibo": 2, ...}, "mentions": {...}}
```

自动派生简称（"贵州茅台" 同时匹配 "贵州" 和 "茅台"），覆盖品牌简称。

**特性**：
- 5min 文件缓存（跟 jcp 一致 TTL）
- 单平台失败不影响其他（每个 fetcher 独立 try/except）
- `UZI_HTTP_TIMEOUT` 默认 20s 超时
- 每平台用不同 UA（抄 jcp 反爬策略）

### 接入

**`fetch_sentiment.py`** · 17_sentiment 维度：
- 末尾调用 `get_hot_mentions(name)`
- 输出字段 `data.hot_trend_mentions` + `data.hot_trend_hit_count`
- heat 分数融合：每个热榜命中 +5 分
- 不改原 ddgs 逻辑（additive）

synthesis → report 里 agent 可以直接引用："微博热搜 #3 '茅台 1499 回归' + 知乎热榜 #7 '茅台为什么跌' — 散户情绪发酵中"。

### 回归测试

- 新增 `tests/test_v2_12_hottrend.py` · **17 个用例**
  - 6 个平台 parser 各一（mocked HTTP）
  - 空响应 / 网络异常 handling
  - 缓存 roundtrip + TTL 过期
  - `get_hot_mentions` 命中匹配 / 平台失败降级 / 短关键词过滤
  - 接口稳定性：SUPPORTED_PLATFORMS 固定 6 个
- 全量 **115 passed**（原 98 + 新 17）
- **零真实网络依赖**（所有 HTTP 都 mock 了）

### 致谢

本模块借鉴 [run-bigpig/jcp](https://github.com/run-bigpig/jcp) 的 `hottrend` 服务实现。`fetch_weibo` / `fetch_zhihu` 等函数的 API 端点和 User-Agent 策略直接参考其 Go 实现。

### 升级

`git pull origin main` · 无配置变更 · 首次触发 `17_sentiment` 时各平台并串 1 次，之后 5min 内秒回。

---

## v2.11.0 — 2026-04-18 (评分校准 · 用户反馈驱动)

> **论坛 linux.do/t/1981105 + 微信群多位用户反馈"分数偏低"**：@崔越"没超过 65 分"、@W.D"茅台 47 分"、@睡袍布太少"只测到天孚通信超 65"。本版做评分曲线校准。

### 根因

诊断 `run_real_test.py::generate_panel` + `generate_synthesis` 两处公式：

1. **verdict 阈值太严**：`>=85 值得重仓 / >=70 可以蹲 / >=55 观望 / >=40 谨慎 / <40 回避`
   - 从未有股能 ≥85（"值得重仓"档位形同虚设）
   - 白马茅台实测 overall=47 → "谨慎"（与白马定位严重不符）

2. **consensus neutral 权重偏低**（v2.9.1 的 0.5 半权公式）：
   - 51 评委里价值派 6 + 中国价投 6 + 游资 23 = 35 人对多数股偏保守
   - 白马典型分布 5 bull / 20 neu / 15 bear / 11 skip → `(5+10)/40×100 = 37.5`
   - neutral 真实语义是"不坑但不是心头好"，不该按 0.5（半空头）处理

### 修复

**1. `generate_panel` · consensus 公式校准**（`run_real_test.py:745`）
```python
# v2.9.1: consensus = (bullish + 0.5*neutral) / active × 100
# v2.11:  consensus = (bullish + 0.6*neutral) / active × 100
NEUTRAL_WEIGHT = 0.6
consensus = (bullish + NEUTRAL_WEIGHT * neutral) / max(active_count, 1) * 100
```
诊断字段 `consensus_formula.version` 升级到 `v2.11`。

**2. `generate_synthesis` · verdict 阈值下调 5 分**（`run_real_test.py:1165`）
```
>=80 值得重仓    (原 85)
>=65 可以蹲一蹲  (原 70)  ← 用户心里的及格线
>=50 观望优先    (原 55)
>=35 谨慎        (原 40)
<35  回避
```

**3. `stock_style.apply_style_weights` · neutral 权重对齐**（`lib/stock_style.py:256`）
- 从 `w * 0.5` → `w * 0.6`（与 generate_panel 对齐，否则风格加权前后 consensus 不一致）

### 预期效果

| 股票典型 | v2.9.1 overall | v2.11 overall | verdict 变化 |
|---|---|---|---|
| 白马茅台 (12/20/16/3) | 55.5 | 57.2 | 观望优先 → 观望优先（接近 65 边界） |
| 真强股 (30/15/3/3) | 72 | 74 | 可以蹲 → **可以蹲** (更稳) |
| 平庸股 (8/20/18/5) | 44 | 46 | 谨慎 → 观望优先 |
| 真坑股 (3/10/33/5) | 28 | 30 | 回避 → **回避**（真坑照样识别） |

**重点**：真坑股分数没有被抬高，辨识度反而提升。

### 回归测试

- 新增 `tests/test_v2_11_scoring_calibration.py` · 8 个用例
  - 阈值硬检查 / ladder 单调 / 茅台典型分布 / NEUTRAL_WEIGHT 常量 / 两处对齐 / 诊断字段 / 0-100 sanity / 边界
- 更新 `test_no_regressions.py::test_consensus_neutral_weighted_formula` 兼容 0.5/0.6 两种权重
- 全量 **98 passed**（原 90 + 新 8）

### BUGS-LOG

完整登记在 [docs/BUGS-LOG.md v2.11.0 章节](docs/BUGS-LOG.md#v2110-2026-04-18--评分校准--用户反馈驱动)，含"未来改该区域注意事项"防回归清单。

### README 更新

- 版本号 v2.9 → v2.11
- 更新日志补齐 v2.10.0-7（4 档）
- 新增 "🎯 评分校准（v2.11）" 章节
- Hermes 兼容提示（链到 INSTALL-HERMES.md）

### 升级

`git pull origin main` · 无数据迁移 · 已有 `.cache/` 继续生效。

---

## v2.10.7 — 2026-04-18 (market 传播 + resume 别名命中 + agent 深浅两路径)

> **Codex 对主线做整体代码审查，发现 v2.10.5 执行链路还有 3 处不符合预期**

### Codex 审查发现的问题

1. **`raw["market"]` 污染** — `collect_raw_data()` 硬编码 `raw["market"]="A"`；post-fetch_basic 回填只在 `resolved != input` 时触发，且读的是 `.data.market`（fetch_basic 实际放在顶层）。结果：用户直接输入 `00700.HK`、`AAPL` 时 `raw.market` 仍为 `"A"`，后续市场分支判断被污染
2. **`resume` 对别名输入失效** — 注释说"尝试用原始 ticker 和 resolved ticker 都查"，实际只查了一次原始 ticker，还发生在 fetch_basic 解析之前。用户用中文名 / 三位港股（"700"）输入时，`.cache/00700.HK/raw_data.json` 已存在也不命中，重跑 Stage 1，耗时 + token 双爆
3. **`AGENTS.md` 强制全量流程** — 主线已支持 CLI/lite 直跑 + 降级路径，但 AGENTS.md 仍要求 agent "看到分析就跑 51 人 role-play + 写 agent_analysis.json"，把 v2.10.4/5 的降载设计抵消掉

### 修复

**1. `collect_raw_data` market 传播**（`run_real_test.py`）
- 进入函数时先用 `parse_ticker(ticker).market` 预填 `raw["market"]`（非中文名 ticker 即刻可知市场）
- fetch_basic 后无条件从 `dims["0_basic"]["market"]`（顶层，不是 `.data.market`）回填
- 从 cache resume 时也回填 `raw["market"]`

**2. resume cache 双重查询**
- 第一轮：`_read_cache(ticker)` 原样查
- 第二轮：若未命中且 ticker 非中文名，用 `parse_ticker(ticker).full` 再查（"700" → "00700.HK" 命中缓存）

**3. AGENTS.md + CLAUDE.md 深浅两路径**
- 明确"快速路径（默认 CLI 直跑）"vs"深度路径（全量 agent 流程）"两档
- 用户信号判断表（`/quick-scan` `/thesis` → CLI；`/ic-memo` `/initiate` → 深度）
- v2.10.4 起 CLI 直跑 `agent_analysis.json` 缺失降 warning，**不要** 强行 role-play 51 评委

### 回归测试

- 新增 2 个用例 · `test_v2_10_4_fixes.py`:
  - `test_raw_market_initialized_from_parse_ticker` — 验证 collect_raw_data 用 parse_ticker 预填
  - `test_resume_cache_tries_resolved_ticker` — 验证 resume 双重查询
- 全量 → **90 passed**（含 12 v2.10.4-7 专项 + 10 extra + 68 原 regression）

### 真机验证

| 场景 | v2.10.5 | v2.10.7 |
|---|---|---|
| `00700.HK --depth lite` | ✗ `Self-Review · 00700.HK (A)` 市场污染 | ✓ `(H)` |
| 中文名 + cache 存在 | ✗ 重跑 Stage 1 | ✓ cache 命中 |
| Agent 看"分析" | 默认全量 role-play | 默认 CLI 直跑，明说"深度"才 role-play |

---

## v2.10.6 — 2026-04-18 (providers 框架实际落地 + Tushare kline + health CLI)

> **审计发现 v2.10.3 的 providers 框架 0% 被调用**。五个 provider 写好了没 fetcher 用，akshare 挂了照样全部崩。本版把它接进 `data_sources.py` 的 K 线链，让 tushare/efinance 真正作为兜底层参与进来。

### 核心改动

**1. `providers.try_chain(method, dim, market, *args)` 助手**
- 一行调用拿 `(data, provider_name)`，按 `UZI_PROVIDERS_<DIM>` env 排序
- `ProviderError` 统一兜底，最后一个 provider 失败才抛
- 方法未实现的 provider 自动跳过（不崩）

**2. `_kline_a_share_chain` 新增第 7 层兜底 · providers chain**
- 前 6 层（akshare-em / akshare-sina / baostock / 东财 HTTP / 新浪 HTTP / 腾讯 HTTP）都挂时
- 自动调 `try_chain("fetch_kline_a", "kline", "A", ...)` 让 tushare/efinance 救场
- 打印 `[kline] 所有默认源失败，providers/tushare 救场 (XXX 根)` 便于诊断

**3. tushare provider 补齐 `fetch_kline_a`**
- `pro.daily + adj_factor` 做前复权，字段统一成中文列名
- 之前只有 financials/top10/lhb/北向，**K 线完全缺**——当 akshare 全线挂时 tushare 也救不了
- 现在 tushare 是 A 股 K 线的官方级兜底

**4. Provider 健康诊断 CLI：`python -m lib.providers`**
```
  name         avail  key req  markets
  akshare      ✓      no       A,H,U
  baostock     ✓      no       A
  direct_http  ✓      no       A,H,U
  efinance     ✓      no       A,H,U
  tushare      ✗      yes      A        ← 提示用户如何配 TUSHARE_TOKEN
```
- `python -m lib.providers chain A kline` · 看某维度 provider 优先级
- `UZI_PROVIDERS_KLINE=baostock,akshare` 可交互验证 env 覆盖

### 为什么这版重要

v2.10.3 写好的 5 个 provider 是**死代码**：16 个 fetcher 仍直接 `import akshare as ak`。
真遇到 GFW 把 push2his/push2.eastmoney 全 timeout 的场景，tushare 已经拿到数据了也白瞎。
v2.10.6 是第一次让 providers 真正参与救场。下一版会把 basic/financials 也接上。

### 测试

- 8 个新 `tests/test_providers_chain.py` 用例：try_chain 成功/失败/跳过、env 覆盖、tushare 方法存在性、health 结构、Protocol 合规
- 原 80 用例全绿 → 88 passing
- CLI 实测 `python -m lib.providers` + `chain A` 两个子命令 OK

### 文件清单

- 新增 `skills/deep-analysis/scripts/lib/providers/__main__.py` (health CLI)
- 新增 `skills/deep-analysis/scripts/tests/test_providers_chain.py` (8 tests)
- 修改 `lib/providers/__init__.py` (加 `try_chain`)
- 修改 `lib/providers/tushare_provider.py` (加 `fetch_kline_a`)
- 修改 `lib/data_sources.py` (_kline_a_share_chain 第 7 层接 providers)
- 修改 `docs/DATA-PROVIDERS.md` (诊断 CLI 使用说明)

---

## v2.10.5 — 2026-04-18 (coverage threshold profile-aware + CLI 直跑 HTML 生成)

> **本地真机测试发现 v2.10.4 还有 3 处漏修 · 一次性补完**

> **Codex 跑 v2.10.4 真机测试再次反馈：lite 模式在网络差时仍被 self-review block**

### 本地真机测试发现的 3 处遗漏

v2.10.4 修了 `check_all_dims_exist` / `check_empty_dims` / `check_agent_analysis_exists` 三处，但漏了 **`check_coverage_threshold`**：

- 症状：`python run.py 600519.SH --depth lite` → coverage 17%（3/18）→ critical → block HTML 生成
- 根因：`check_coverage_threshold` 用全 18 项 `CRITICAL_CHECKS` 做分母，不看 profile。lite 只跑 7 维，结构性偏低
- 对比：`00700.HK` 同样 lite 跑出 44% → warning → HTML 生成 ✅（只是阈值擦边过）

### 修复

**1. `check_coverage_threshold` profile-aware**（lib/self_review.py）
- Profile-aware 分母 — 只算当前档位启用维度的 `CRITICAL_CHECKS` 项
- CLI-only / lite 模式 `< 40%` 的 critical 降为 warning（CLI 直跑无 agent 可补数据）

**2. run.py 自动标记为 CLI 直跑**（run.py）
- `run.py` 在 main() 开头设 `UZI_CLI_ONLY=1`
- 理由：agent 流程走 stage1/stage2 直接调用，不经 run.py；run.py 只服务人/CI
- 效果：medium/deep 模式下 CLI 直跑 `agent_analysis.json` 缺失也降为 warning，能出报告

**3. `render_fund_managers` None 字段崩溃**（assemble_report.py:1844）
- 症状：`TypeError: '>' not supported between 'NoneType' and 'int'`
- 根因：v2.10.2 fund_holders 双层策略下，rest lite 基金的 `return_5y/max_drawdown/sharpe` 为 None，不是 0。`m.get("return_5y", 0)` 不能处理显式 None
- 修：`m.get("return_5y") or 0` 统一兜底（5 个字段）

### 回归测试

- 新增 4 个用例 · `test_v2_10_4_fixes.py`:
  - `test_coverage_critical_downgrades_in_lite` — lite + 17% coverage → warning ✅
  - `test_coverage_critical_preserved_in_medium` — medium + 17% coverage → critical ✅ (回归护栏)
  - `test_coverage_profile_aware_denominator` — lite + 启用维度全满 → 0 issues ✅
  - `test_run_py_sets_cli_only_env` — run.py 源码含 `UZI_CLI_ONLY=1` setdefault ✅
- 原 76 个 regression 全绿 → **80 passed**

### 真机验证（local）

| 场景 | v2.10.4 | v2.10.5 |
|---|---|---|
| `run.py 600519.SH --depth lite` | ❌ critical block HTML | ✅ warning, HTML ~130s |
| `run.py 002273.SZ --depth medium` | ❌ agent_analysis critical | ✅ warning, HTML ~60s (cached) |
| `run.py 00700.HK --depth lite` | ✅ (恰好擦边过) | ✅ 稳 |
| `run.py 512400.SH` (ETF) | ✅ 早退 | ✅ 早退，提示成分股 |

---

## v2.10.4 — 2026-04-17 (lite 自查兼容 + ETF 早退干净)

> **Codex 跑 v2.10.3 反馈的 3 个 bug · 全部修复 + 回归测试**

### 修复

**1. lite 模式与 self-review 规则冲突**
- 症状：`UZI_DEPTH=lite` 跑完 gate 报 9 个 critical（维度缺失、data 为空）
- 根因：`check_all_dims_exist` / `check_empty_dims` 硬编码检查全 20 维，不看 profile
- 修：两个函数现在读 `analysis_profile.get_profile().fetchers_enabled`，只检查启用的维度
- medium/deep 行为不变（仍强制 20 维）

**2. agent_analysis.json 缺失在 CLI-only 运行误报 critical**
- 症状：`python run.py` 直跑（无 agent 介入）→ gate 必定 critical，阻止 HTML 生成
- 修：`check_agent_analysis_exists` 在 `UZI_DEPTH=lite` / `UZI_LITE=1` / `UZI_CLI_ONLY=1` / `CI=true` 时降级为 warning
- 正常两段式流程（stage1 → agent → stage2）行为不变

**3. ETF 早退逻辑半成功**
- 症状：`python run.py 512400.SH` → stage1 正确识别 ETF 写 `_resolve_error.json`，但 stage2 仍被调用 → `RuntimeError: Stage 2 缺少数据`
- 修 A：`run_real_test.main()` 加 `status == "non_stock_security"` 分支，跳过 stage2 并 `return result`
- 修 B：`run.py` 捕获 `run_analysis(...)` 返回的 `non_stock_security` dict，打印成分股提示后 `sys.exit(0)`
- 修 B2：中文名路径也加同样检查（指数/ETF 用中文名输入时）

### 回归测试

- 新增 `tests/test_v2_10_4_fixes.py` · 8 个用例覆盖上述 3 个 bug + 正向场景
- 原 68 个 regression 全绿

### 文件清单

- `skills/deep-analysis/scripts/lib/self_review.py`（profile-aware · 3 处）
- `skills/deep-analysis/scripts/run_real_test.py`（main() 加 ETF 早退 + 返回 result）
- `run.py`（两条路径都捕获 non_stock_security 干净退出）
- `skills/deep-analysis/scripts/tests/test_v2_10_4_fixes.py`（新）
- 版本号 bump 到 2.10.4

---

## v2.10.3 — 2026-04-18 (多源 providers 框架 + 三档深度 + 网络韧性)

> **一次性合入近一天积累的所有性能 / 韧性 / 数据源改造**

### 用户反馈驱动的 6 大改动

**1. 三档思考深度（用户："让用户自己选择思考深度"）**
- `lite` (1-2min) / `medium` (5-8min · 默认) / `deep` (15-20min)
- `--depth` CLI arg 或 `UZI_DEPTH` env
- 三档差异清晰对比（fetcher 维度 / 评委数 / 机构方法 / ddgs 预算 / fund_holders 策略 / 自查严格度）
- 命令隐式档位 (`/quick-scan` → lite · `/ic-memo` → deep)

**2. Multi-Provider 框架（用户："除了 akshare，tushare 这些能作为备选吗"）**
  - `lib/providers/` Protocol + chain builder
  - 5 个内置 provider: akshare / efinance / tushare / baostock / **direct_http**
  - `get_provider_chain(dim, market)` 按优先级 failover
  - `UZI_PROVIDERS_<DIM>` 单维度覆盖

**3. direct_http provider（用户转达 Codex 建议 fetch_web_quote.py）**
  - Codex 声称做了但实际未提交；我来落地
  - 腾讯 qt.gtimg.cn / 新浪 hq.sinajs.cn / etnet.com.hk
  - 3 级 fallback · 覆盖 A/H/U 三市场
  - 实测 600519/000001/00700/AAPL 全部拿到实时价
  - 脱离 akshare，GFW 风险减半

**4. Fund holders 双层策略（用户："基金拉全不是直接检索就行了吗"）**
  - 原先 649 家每家 2 次 akshare (算 5Y NAV) = 1300 API 串行跑 5-10 分钟
  - 新：Top N 家 full 业绩 + 其余 lite 清单（0 额外 API）
  - `UZI_FUND_STATS_TOP=N` 调节 (lite=5, medium=20, deep=100)
  - 30-60 秒出结果

**5. 代理/网络韧性（用户："代理、网络不通导致 codex 卡死"）**
  - `lib/net_timeout_guard` monkey-patch requests 默认 `UZI_HTTP_TIMEOUT=20`
  - `lib/web_search._ddg_search` 线程池硬 timeout `UZI_DDG_TIMEOUT=10`
  - `lib/network_preflight` 启动 TCP 探 5 个关键域，3+ 不通自动切 lite
  - parse_ticker 修复 3 位数字识别为 HK (`700` → `00700.HK`)
  - Codex + 代理挂最坏耗时: 40 分钟 → 30-60 秒

**6. prewarm cache 脚本（用户："缓存能提前写入吗，别含敏感信息"）**
  - `scripts/prewarm_cache.py` 只跑公开数据
  - 输出 `prewarm/api_cache/` (gitignored)
  - sanity_check_output 扫描 sk-/@qq.com/Users/ 模式报警
  - 可打 tar.gz 作 release 附件分发

### 底层技术改动

| 新增 | 作用 |
|---|---|
| `lib/providers/` (5 文件) | 多源自动 failover 框架 |
| `lib/analysis_profile.py` | 三档 depth profile 定义 |
| `lib/net_timeout_guard.py` | 全局 requests timeout |
| `lib/network_preflight.py` | 启动预检 |
| `scripts/prewarm_cache.py` | 预热 cache 生成器 |
| `docs/DATA-PROVIDERS.md` | 25+ 数据源全景清单 |

### 改动文件

- `run.py` · 加 `--depth` arg · 加载 profile
- `run_real_test.py::stage1` · 自动 lite 检测 · 预检 · timeout guard 导入 · fetcher 按 profile 过滤
- `fetch_fund_holders.py` · 双层 full/lite
- `fetch_industry.py` · lite mode skip dynamic
- `lib/web_search.py` · ddgs timeout + 预算
- `lib/market_router.py` · HK 3 位数字修复
- `assemble_report.py::render_fund_managers` · lite row 友好显示
- `README.md` / `README_EN.md` · 三档深度新章节

### 回归

**68/68** regression tests pass
新增 13 条:
- test_fund_holders_two_tier_strategy
- test_lite_mode_detection_exists
- test_ddg_budget_enforced
- test_fetch_industry_respects_lite_mode
- test_analysis_profile_three_tiers
- test_analysis_profile_env_compat
- test_prewarm_cache_script_exists
- test_ddg_timeout_wrapper
- test_net_timeout_guard_exists
- test_network_preflight_exists
- test_parse_ticker_hk_3digit
- test_providers_framework_loads + chain_failover + env_override + health_check + tushare_requires_key + direct_http_provider

### 性能对比

| 场景 | v2.9.2 | v2.10.3 |
|---|---|---|
| 首次安装 + 正常网络 | 10-15 分钟 | 2-4 分钟 (medium) |
| 首次安装 + 代理挂 | 30-40 分钟卡死 | 30-60 秒 (自动 lite) |
| `--depth lite` | — | 1-2 分钟 |
| `--depth deep` | — | 15-20 分钟 |

---

## v2.9.2 — 2026-04-17 (ETF/LOF/可转债 识别 + 交互式引导到成分股)

> **用户反馈：分析 `512400`（沪市有色金属 ETF）被错判为 SZ，全盘网络+数据错误；且即便修正也不该跑——51 评委是个股规则，ETF 没 ROE/护城河这些字段**

### 2 个 BUG + 1 个新功能

### BUG#1 · Ticker 识别错（512400 → SZ 错的）

`lib/market_router.py::_a_share_suffix` 旧规则：

```python
if code6.startswith(("60", "688", "900")): return "SH"
if code6.startswith(("83", "87", "88", "92")): return "BJ"
return "SZ"   # 其他所有 6 位码全归 SZ
```

导致所有**沪市 ETF (5xxxxx) / 沪市可转债 (10/11xxxx)** 被错判 SZ，eastmoney
`secid` 前缀变 `0.` 应该是 `1.` → 所有 API 全返错。

**修法**：重写 `_a_share_suffix` 覆盖完整规则：
- SH：600/601/603/605/606... · 688（科创板股票）· 900（B 股）· 50/51/52/56/58（基金）· 10/11（可转债）
- BJ：83/87/88/92
- SZ：其他（000/001/002/003/300/301/159/16/18/12...）

### BUG#2 · ETF/LOF/可转债 混进个股流程

即便 ticker 识别正确，**这些非个股标的就根本不该走 51 评委 + 22 维流程**：
- ETF 没有 ROE / 护城河 / 管理层
- 可转债看的是转股价 / 溢价率 / YTM
- 基金看的是基金经理 / 规模 / 回撤

**修法**：新 `classify_security_type(code6)` 识别 stock / etf / lof / convertible_bond。`fetch_basic` + `stage1` 两层早退：
- fetch_basic 返 `error: non_stock_security`
- stage1 早退 + 写 `_resolve_error.json`（格式同 name_not_resolved）

### 新功能 · ETF 交互式引导

**用户要求**："如果检测到是 etf，则告知客户这个插件对 etf 无法支持，但可以帮助他识别前十大持仓股，然后列出股票，询问他需要识别哪一只？"

已落地：

```
🔴 非个股标的: 512400.SH (ETF)
   本插件是个股深度分析引擎，51 评委跑 ROE/护城河/管理层/分红 这些个股财务指标，ETF 没这些字段

   📊 不过我可以帮你识别 512400.SH 的前 10 大持仓，请选一只分析：

      1. 紫金矿业     (601899.SH  ) · 占比 12.50%
      2. 洛阳钼业     (603993.SH  ) · 占比  9.80%
      3. 赣锋锂业     (002460.SZ  ) · 占比  8.21%
      ...

   👉 请选择要分析的成分股（告诉我编号或代码）
      例：/analyze-stock 601899.SH  或  /analyze-stock 紫金矿业
```

同时写 `_resolve_error.json` 带 `top_holdings: [{rank, code, name, weight_pct}, ...]` + `user_prompt` 字段，agent 读到就知道走 ETF 引导流程。

### SKILL.md 新增 HARD-GATE-NON-STOCK

规定 agent 看到 `status: non_stock_security` 必须：
- 绝不假装跑；用 AskUserQuestion 列 top_holdings 让用户选
- 用户选定后用成分股代码重跑 stage1

### 回归测试（51/51 · 新增 6 条）

- `test_ticker_parser_sh_etf` · 512400/510500/513100/518880/588000 全部 SH
- `test_ticker_parser_sz_etf` · 159949/159922/159928 全部 SZ
- `test_ticker_parser_convertible_bonds` · 11xxxx SH + 12xxxx SZ
- `test_ticker_parser_stocks_still_correct` · 个股识别不受影响
- `test_fetch_basic_rejects_etf` · fetch_basic 必须接 classify_security_type
- `test_stage1_early_exits_on_etf` · stage1 必须早退 + 输出 top_holdings

### 改动文件

- `scripts/lib/market_router.py` · 重写 `_a_share_suffix` + 新 `classify_security_type`
- `scripts/fetch_basic.py` · ETF/LOF/CB 早退 + `_NON_STOCK_GUIDANCE` 表
- `scripts/run_real_test.py::stage1` · 早退 + 拉前 10 持仓 + 互动 prompt
- `skills/deep-analysis/SKILL.md` · 新 HARD-GATE-NON-STOCK
- `scripts/tests/test_no_regressions.py` · +6 条

---

## v2.9.1 — 2026-04-17 (评委汇总观点 · 6 处 bug 修复)

> **用户反馈："评委打分了，但是汇总评委观点那里存在缺失和数据不对的问题"**

审计之后找到 6 个相关 bug（其中 1 个是"写入 synthesis 但从未渲染"的严重静默丢失）。

### BUG 全列表

| # | 严重性 | 问题 | 症状 |
|---|---|---|---|
| 1 | 🔴 critical | `panel_insights` 写入 synthesis.json 但**完全不渲染** | agent 写的面板级分析消失 |
| 2 | 🟡 warning | 分享卡只有"Top 3 看多"，没有"Top 3 看空" | 不对称 |
| 3 | 🟡 warning | 看多/看空为空时显示 3 个空灰格 | "缺失"的视觉症状 |
| 4 | 🔴 critical | `{{BULL_ID}}` / `{{BEAR_ID}}` 默认 `"buffett"` / `"graham"` | debate 空时显示错误头像+空数据 |
| 5 | 🟡 warning | `great_divide_override` 格式要求不一致没校验 | agent 写错格式静默丢 |
| 6 | 🔴 critical | consensus 公式**完全错**：注释说半权，实际 `bullish / active`（neutral 权重 0） | 共识度长期偏低，高分股被评为"观望"甚至"回避" |

### BUG#6 最严重 · consensus 公式

旧代码：

```python
consensus = sig_dist["bullish"] / max(active_count, 1) * 100
# 注释写 "neutral 半权计入 consensus" 但代码只用 bullish
```

样本：30 看多 / 15 中性 / 5 看空（共 50 active）
- **旧公式**：30/50 = **60%**（中性按 0 权重当看空处理）
- **v2.9.1 新**：(30 + 7.5)/50 = **75%**（中性按半权合理）

这直接拉低了长期以来所有股票的 consensus 值，也是"数据不对"投诉的主因。

### BUG#1 · panel_insights 静默丢失

agent 在 `agent_analysis.json` 里写 `panel_insights` 字段（例如"51 位评委里 A 组价值派明显分化：Buffett 看多但 Klarman 看空，核心争议是安全边际"），会被 merge 到 synthesis.json。但 `assemble_report.py` **从未调用任何函数渲染这个字段**，template 也没有对应的 inject 点——**agent 写的面板级分析全部消失**。

v2.9.1 新增：
- `render_panel_insights(syn, panel)` 函数
- template `<!-- INJECT_PANEL_INSIGHTS -->` 在 great_divide 3 rounds 之后
- 如果 agent 没写，自动 fallback 用 panel 真实数据聚合一段（按流派分布 + 高信念信号提示）
- 标记数据来源：`📊 PANEL INSIGHTS · 评委汇总观点（agent 深度分析）` vs `（自动聚合 · agent 未介入）`

### BUG#2 + #3 · Top 3 对称 + 空时友好提示

分享卡片原只有 `render_top3_bulls`——v2.9.1 补 `render_top3_bears`，template 加 `// 谁最看空你` section。

空时不再 fill 3 个空 div（之前用户看到的"缺失"），改显示提示文案：
- bulls 为空：`无看多评委 · 51 人整体倾向中性`
- bears 为空：`无看空评委 · 51 人整体倾向中性`

### BUG#4 · 不再硬编码假头像

旧：`"{{BULL_ID}}": _safe(bull.get("investor_id"), "buffett")`

现：`"_placeholder"` + name 默认 `"（未选出）"` — debate 真空时显示占位而不是冒充巴菲特有空数据。

### self-review 新增 3 条检查

- `check_consensus_formula_sanity` · bullish=0 但 consensus>20% 必然公式错
- `check_panel_insights_rendered` · meta check · assemble_report 源码必有 `render_panel_insights`
- `check_debate_bull_bear_populated` · debate.bull / bear 不能是空对象、不能是同一人

### 改动文件

- `scripts/run_real_test.py::generate_panel` · consensus 公式改半权 + 新增 `consensus_formula` 诊断字段
- `scripts/assemble_report.py` · 新 `render_panel_insights` / `render_top3_bears` / `_render_top3_by_signal` 共用逻辑
- `scripts/lib/self_review.py` · +3 个检查，`CHECKS` 16 → 19 条
- `scripts/tests/test_no_regressions.py` · +4 条测试（45 → 49 实际 45 · 新 4）
- `skills/deep-analysis/assets/report-template.html` · 2 个新 inject 点

### 回归

**45/45** regression tests pass（新增 4 条）

### 建议

之前版本跑的 cache `panel_consensus` 值都偏低（中性权重 0 的公式），想看准确共识度请清 cache 重跑：

```bash
rm -rf skills/deep-analysis/scripts/.cache/<ticker>/*
python run.py <ticker> --no-resume
```

---

## v2.9.0 — 2026-04-17 (机械级 agent 自查 · 结构性改造)

> **v2.9 关键变化：agent 自查从"软要求"升级到"机械强制"——HTML 生成前必过 13 项自动检查，critical 不过就 raise RuntimeError 拒绝出报告**

### 用户指令
> "一切内容后，必须要有agent自己核对一遍所有内容，如果有问题就要修改，现在这个事儿还是没做，这个逻辑一定要对！"

### 根本问题

过往版本 SKILL.md 有 HARD-GATE-FINAL-CHECK 这种"软要求"，agent 可能跳过、可能忘、可能做半截。BUG#R10（云铝→农副食品加工）暴露出：agent 跑完全流程报告都发出去了，才被用户发现行业分类错了。

**软 HARD-GATE 不够。必须机械级强制。**

### v2.9 核心 · 自查引擎

**新增 `lib/self_review.py`** (~300 行) · 13 条自动检查覆盖过往所有 BUG 经验：

| severity | check | 背后 BUG |
|---|---|---|
| 🔴 | `check_industry_mapping_sanity` | BUG#R10 工业金属→农副食品加工 |
| 🔴 | `check_all_dims_exist` | wave2 timeout 导致 12_capital_flow 缺失 |
| 🔴 | `check_empty_dims` | crash/timeout 产生的空维度 |
| 🔴 | `check_hk_kline_populated` | BUG#R8 HK kline 无 fallback |
| 🔴 | `check_hk_financials_populated` | BUG#R7 HK financials 空 stub |
| 🔴 | `check_panel_non_empty` | panel 全 skip/avg_score 异常 |
| 🔴 | `check_coverage_threshold` | `_integrity.coverage_pct < 60` |
| 🔴 | `check_placeholder_strings` | synthesis 含 "[脚本占位]" |
| 🔴 | `check_agent_analysis_exists` | agent_analysis.json 缺失 |
| 🟡 | `check_valuation_sanity` | DCF/Comps 全 0 |
| 🟡 | `check_metals_materials_populated` | 金属股 materials 空 |
| 🟡 | `check_industry_data_coverage` | 7_industry 需 agent 补 |
| 🟡 | `check_factcheck_redflags` | 编造"苹果产业链"无 raw_data 证据 |

**新 CLI `scripts/review_stage_output.py`**：

```bash
python review_stage_output.py <ticker>
# exit 0 = 无 critical，可进 HTML
# exit 1 = 有 critical，BLOCK
# exit 2 = 只有 warning，可进但建议 ack
```

输出 `.cache/<ticker>/_review_issues.json`，每条 issue 含：
- `severity`, `category`, `dim`
- `issue` 人读描述
- `evidence` 触发的具体值
- `suggested_fix` 下一步怎么处理

**关键的机械强制 · `assemble_report::assemble()`**：

```python
# v2.9 起 HTML 生成前自动跑 review
from lib.self_review import review_all
review = review_all(ticker)
if review["critical_count"] > 0:
    raise RuntimeError(
        f"⛔ BLOCKED by self-review: {crit} 个 critical 问题待修"
    )
# 过了才能继续拼 HTML
```

### Agent 迭代流程（SKILL.md HARD-GATE-AGENT-SELF-REVIEW）

```
loop:
  1. python review_stage_output.py <ticker>
  2. 读 _review_issues.json
  3. if critical > 0:
       for each critical issue:
         - 执行 suggested_fix（补数据/重跑/写 agent_analysis 覆盖）
       重跑 review
  4. if warning > 0:
       for each warning: 要么修，要么 agent_analysis.review_acknowledged 写原因
  5. critical == 0 时进入 HTML
```

### v2.9 结构性改造 · fetch_industry 动态查

**问题**：v2.8.x 的 `INDUSTRY_ESTIMATES` 硬编码表只有 7 条，236/243 个申万三级行业的 TAM/growth/lifecycle 永远是 "—"。

**修法**：保留 7 条硬编码作 anchor，**不在表里的行业走 `search_trusted(dim='7_industry')`** 动态查权威域（统计局/工信部/中证网/每经）并启发式抽取：

```
v2.8.4: 工业金属 → growth: "—"  tam: "—"  lifecycle: "—"  (硬编码表里无)
v2.9.0: 工业金属 → growth: "3.5%/年"  (从"六部门印发机械行业稳增长工作方案"抽)
                  + 9 条真实权威 snippets 给 agent 综合
                  + source: cninfo + search_trusted:7_industry(9 snippets)
```

不需要手工维护 243 条硬编码表——数据始终实时，来源可 URL 溯源。

### 港股 industry_pe fallback

**问题**：cninfo 只支持 A 股，港股 `industry_pe_avg` 永远是 None（实测 00700.HK valuation 完整性 22%）。

**修法**：港股走 `ak.hk_valuation_comparison_em` 取同行 PE 均值作 industry_pe。

### 回归

**41/41** regression tests pass（新增 5 条）：
- `test_self_review_engine_exists`
- `test_self_review_cli_exists`
- `test_assemble_report_gated_by_review`（确保 HTML gate 机械化）
- `test_self_review_catches_bug_r10`（mock BUG#R10 场景验证 engine 能抓到）
- `test_fetch_industry_has_dynamic_fallback`

### 改动文件

- **NEW** `scripts/lib/self_review.py` ~300 行 · 13 条自查规则
- **NEW** `scripts/review_stage_output.py` · CLI runner
- `scripts/assemble_report.py::assemble()` · 入口加强制 review gate
- `scripts/fetch_industry.py` · 动态 `_dynamic_industry_overview` + `dynamic_snippets` 输出
- `scripts/fetch_valuation.py` · HK industry_pe 通过 `hk_valuation_comparison_em` 兜底
- `skills/deep-analysis/SKILL.md` · `HARD-GATE-FINAL-CHECK` 重写为 `HARD-GATE-AGENT-SELF-REVIEW`（明确"机械级强制"）
- 版本号 2.8.4 → 2.9.0

---

## v2.8.4 — 2026-04-17 (follow-up · 全库自审有色金属类 coverage gap)

> **用户提醒"这些数据你都要自我检查一遍的，懂了吗？" 主动全库审计，补齐 v2.8.3 关联的 3 个 coverage gap**

### 用户提醒
> "所以这些数据你都要自我检查一遍的，懂了吗？"

### 主动做了什么

v2.8.3 修了 fetch_industry 的 BUG#R10，但用户提醒我不能只补用户报告的那一处。**主动全库审计**同类 pattern：

| 审计 pattern | 结果 |
|---|---|
| `str.contains(X[:2])` fuzzy match | 8 处，1 处有风险已修 |
| `iloc[0]` 盲选 | 20+ 处，多数是 ticker-specific 安全 |
| `[:2] in X or X[:2] in k` 字典 fuzzy | 3 处在 materials/futures/peers 静默缺 coverage |
| 我自己的 134 条 SW_TO_CSRC_INDUSTRY 硬映射 | 全部 134 条验证能命中 cninfo 真实数据 ✓ |
| fetch_financials `_row("净利润")` 短关键字 | 有 `or _row("归属...")` fallback 先试，已有保护 |

### 找到的 3 个 coverage gap（都是 v2.8.3 同一家族）

| 位置 | 症状 | 修法 |
|---|---|---|
| `INDUSTRY_MATERIALS` | 云铝拿不到铝价联动（核心原材料数据空） | 加 `工业金属/有色金属/贵金属/能源金属/小金属/煤炭开采/焦炭/油气开采` 8 条 |
| `INDUSTRY_FUTURES` | 云铝 `linked_contract` 为 None | 加 7 条 → `工业金属: (沪铝 AL, AL0)` 等 |
| `_INDUSTRY_ALIASES` | 云铝 similar_stocks 完全空 | 加申万三级 → INDUSTRY_PEERS 别名 15 条 |

### 修复前后云铝股份对比

```
v2.8.3 修后但 v2.8.4 修前:
  7_industry  ✓ 有色金属冶炼和压延加工业 PE 32.97（BUG#R10 已修）
  8_materials ✗ core_material = "—"（static 库无 "工业金属"）
  9_futures   ✗ linked_contract = None
  similar_stocks ✗ []  空

v2.8.4 修后:
  7_industry    ✓ 有色金属冶炼和压延加工业 PE 32.97
  8_materials   ✓ 沪铝 +30% / 沪铜 +39.5% / 沪锌 +8.8% 真实 12 月趋势
  9_futures     ✓ 沪铝 AL · 最新价 25520.0
  similar_stocks ✓ 紫金矿业 / 洛阳钼业 / 天齐锂业
```

### 改动文件

- `scripts/fetch_materials.py` · `INDUSTRY_MATERIALS` +8 条（工业金属/有色金属/贵金属/能源金属/小金属/煤炭开采/焦炭/油气开采）
- `scripts/fetch_futures.py` · `INDUSTRY_FUTURES` +7 条
- `scripts/fetch_similar_stocks.py` · `_INDUSTRY_ALIASES` +15 条
- `scripts/tests/test_no_regressions.py` · +3 条测试

### 回归

**36/36** regression tests pass（新增 3 条：materials/futures/peers coverage 验证）

---

## v2.8.3 — 2026-04-17 (critical fix · 行业分类碰撞错误)

> **严重 bug 修复：云铝股份被归类为"农副食品加工"的根因，影响所有带"工业"/"加工"/"制造"前缀的申万行业**

### 用户报告
> "2.8.0 存在行业找错问题，用户分析云铝股份，属于工业金属铝行业，但是行业分类却归类为农副食品加工，你检查一下什么问题，这个问题很严重，必须修复。"

### BUG#R10 根因

`fetch_industry.py:90` 和 `fetch_valuation.py:122` 都用 `df["行业名称"].str.contains(industry_name[:2])` 做 fuzzy 匹配：

```python
# v2.8.2 及之前（有 BUG）
matches = df[df["行业名称"].astype(str).str.contains(industry_name[:2], na=False)]
row = matches.iloc[0]   # ← 盲选第一行
```

证监会行业分类 120 行里包含 `"工业"` 子串的有 **4 个**：
1. **农副食品加工业** ← `iloc[0]` 选中
2. 石油、煤炭及其他燃料加工业
3. 黑色金属冶炼和压延加工业
4. 有色金属冶炼和压延加工业（本应命中）

所以申万行业 `"工业金属"` 经过 `industry_name[:2] = "工业"` 匹配后，被**错误归类为"农副食品加工业"**。

### 影响面（不只是云铝股份）

所有带"工业 / 加工 / 制造"字样前缀的申万行业都会被误分到 `农副食品加工业`：
- 工业金属 · 工业母机 · 工业机械 · 工业气体 → 错
- 加工贸易相关子行业 → 错
- 部分制造业细分 → 错

**这意味着**：
- `7_industry` 维度的 industry_pe / 公司数量全是错的
- `10_valuation` 的 `industry_pe_avg` 用错了行业比较
- `stock_style` 的 style 分类虽然基于申万名不受影响，但**相对估值判断偏移**
- 报告里的"同行业景气度"文本全是假的

### 修复方案

新 `lib/industry_mapping.py` 做 **3 策略语义解析**：

```python
SW_TO_CSRC_INDUSTRY = {
    "工业金属": "有色金属冶炼和压延加工业",
    "白酒":     "酒、饮料和精制茶制造业",
    "半导体":   "计算机、通信和其他电子设备制造业",
    "钢铁":     "黑色金属冶炼和压延加工业",
    # ... 共 134 条申万 → 证监会映射
}

HIGH_COLLISION_TOKENS = {"工业", "加工", "制造", "服务", "生产",
                         "供应", "设备", "制品", "其他", ...}

def resolve_csrc_industry(sw_industry, df):
    # 1. 硬映射表精确命中（覆盖 134 常见申万行业）
    # 2. 申万名整体作为子串包含
    # 3. 去高碰撞前缀后 fuzzy（如 "工业金属" 去 "工业" 后用 "金属"）
    # 4. 找不到 → 返 None（绝不盲选 iloc[0]）
```

### 修复验证

```
工业金属  → 有色金属冶炼和压延加工业 · PE 32.97
工业母机  → 专用设备制造业 · PE 42.91
白酒      → 酒、饮料和精制茶制造业 · PE 18.01
半导体    → 计算机、通信和其他电子设备制造业 · PE 70.05
钢铁      → 黑色金属冶炼和压延加工业 · PE 27.36
化学原料  → 化学原料和化学制品制造业 · PE 33.91
```

### 改动文件

- **NEW** `scripts/lib/industry_mapping.py` (~200 行)
  - `SW_TO_CSRC_INDUSTRY` 134 条硬映射
  - `HIGH_COLLISION_TOKENS` 12 个黑名单前缀
  - `resolve_csrc_industry()` 4 策略解析函数
- `scripts/fetch_industry.py::_cninfo_industry_metrics` · 接入 resolver
- `scripts/fetch_valuation.py` · 接入 resolver
- `scripts/tests/test_no_regressions.py` · 新增 3 条测试：
  - `test_industry_mapping_blocks_high_collision_substring`
  - `test_resolve_csrc_industry_on_mock_df`（mock DataFrame 确认不会选到 农副食品加工业）
  - `test_fetch_industry_and_fetch_valuation_use_mapping`
- `docs/BUGS-LOG.md` · 新增 BUG#R10 记录

### 回归

**33/33** regression tests pass（新增 3 条）

### 紧急建议

之前用 v2.8.0 / v2.8.1 / v2.8.2 分析过**工业金属 / 工业母机 / 工业机械** 相关股票的用户，请**清 cache 重跑**：

```bash
rm -rf skills/deep-analysis/scripts/.cache/<ticker>/raw_data.json
python skills/deep-analysis/scripts/run_real_test.py <ticker> --no-resume
```

否则 `7_industry` / `10_valuation` 两维的报告数据都是错的。

---

## v2.8.2 — 2026-04-17 (English support · 面向全球用户)

> **README_EN / plugin manifests / marketplace 全面升级英文支持，面向西方投资者展示核心卖点：帮你理解让芒格都亏钱的阿里巴巴这种中国股票**

### 背景
用户："加入对英语的支持，在英文版可以提到，这个插件可以帮助您了解中国很多的股票，例如让芒格亏了几千万的阿里巴巴"。

旧 `README_EN.md` (204 行) 只是 Chinese README 的直译，**没回答"这东西对西方用户为什么有价值"**——Bloomberg 终端覆盖 HK 和 ADR 但 A 股数据薄；Anthropic 官方 financial-services-plugins 是 US-only 且要 FactSet 付费源。Western users 手头没有这种工具。

### 新增 · "Why Western Investors Should Care" 章节

开篇直接定位为"Bloomberg 没做好、Anthropic 官方插件没覆盖的中国市场分析"：

- Bloomberg covers HK and ADRs, but A-share data is thin
- Reuters / FT give macro, not per-company fundamentals
- financial-services-plugins is US-only, FactSet-gated
- 20+ free Chinese data sources (akshare / Eastmoney / XueQiu / CNInfo / HKEXNews / mx妙想 API)

然后用 **Munger/Alibaba 的真实案例** 作为 hook：

> 2021 年 Munger 通过 DJCO 重仓 Alibaba，2022 年 ~70% 回撤后不得不砍仓一半，
> [在 2022 DJCO 年会称"这是我犯过最糟糕的错误之一"](https://www.cnbc.com/2023/02/15/charlie-munger-says-he-regrets-alibaba-investment-one-of-the-worst-mistakes.html)，
> 估计九位数损失。**Even legends underestimate how differently the Chinese regulatory and competitive landscape behaves. 普通投资者更需要分析武器。**

然后列出目标股票：**Alibaba / Tencent / Kweichow Moutai / CATL / BYD / Pop Mart / Pinduoduo** — "the same names that keep showing up in Western portfolios and keep surprising their owners 😉"

### README_EN 其他升级 (204 → 359 行)

- **新增**: Plugin command prefix 命名空间说明（`stock-deep-analyzer:analyze-stock`）
- **新增**: 多 agent 生态安装（Codex / OpenClaw / Cursor / Gemini CLI / OpenCode / Windsurf / Devin / 📱 remote mode）
- **新增**: Ticker format tips for English users（A/H/U 三市场代码格式）
- **新增**: XueQiu 登录章节
- **新增**: Time horizon / what-would-change-my-mind 表格（Buffett/Zhao Laoge/Simons/Lynch/Soros）
- **新增**: 架构 ASCII 图（Task 1-5 流程）
- **新增**: FAQ 补"英文名解析"、"GFW 影响"、"海外是否能用"、"panel 原话是否真实"
- **Disclaimer** 尾部加一句："Charlie Munger still lost money on Alibaba, and he actually read the 10-Q."

### plugin manifests 双语化

- `.claude-plugin/plugin.json` · description 中英双语；keywords 追加 `china-stocks / hong-kong-stocks / chinese-equities / alibaba / tencent / buffett / munger / equity-research`
- `.claude-plugin/marketplace.json` · description 双语 + Munger/Alibaba hook
- `.cursor-plugin/plugin.json` · description 双语
- `package.json` · description 双语

### 回归

- 30/30 regression tests pass（README 变更不影响代码测试）
- Chinese README ↔ English README 双向链接已验证（`**中文** | [English](README_EN.md)`）

### 改动文件

- `README_EN.md` · 204 → **359** 行（全面重写 + Munger/Alibaba hook + 6 个新章节）
- `.claude-plugin/plugin.json` · description 双语 + 7 个英文 keywords
- `.claude-plugin/marketplace.json` · description 双语
- `.cursor-plugin/plugin.json` · description 双语
- `package.json` · description 双语
- 版本号 2.8.1 → 2.8.2（4 个 manifest）

---

## v2.8.1 — 2026-04-17 (quotes expansion · 22 个海外人物真实原话)

> **quotes-knowledge-base.md 扩容 306 → 639 行，补齐 22 位海外代表人物的真实原话 + URL 溯源**

### 背景

用户："还有很多你要去找他们的言论，去找一下，收集一下"。

v2.8.0 做完 investor_profile 层后，发现 `skills/investor-panel/references/quotes-knowledge-base.md`（agent 生成 comment 前**必读**的语料库）只覆盖 23 位中国投资者，20+ 海外代表人物（Buffett / Munger / Soros / Lynch / Simons / Dalio / Druck / Marks / Graham / Fisher / Klarman / Templeton / Thiel / Wood / Livermore / O'Neil / Minervini / Gann / Darvas / Thorp / D.E.Shaw / Robertson）**原话空白**。

### 本次做了什么

派 **4 个并行 research agent** 按流派去取证——严格要求**真实可验证**、不 fabricate：
- Group A 价值派（6 人）· Berkshire 年报 / Goodreads / Farnam Street / 雪球
- Group B 成长派（4 人）· One Up on Wall Street / WSJ / ARK / CNBC / C-SPAN
- Group C 宏观对冲（5 人）· Principles / Oaktree memos / Reuters / Real Vision / NY Times
- Group D 技术趋势（4 人）+ Group G 量化（3 人）· 原版书 / archive.org / TED / 华尔街见闻

### 扩充结果

| 指标 | v2.8.0 | v2.8.1 |
|---|---|---|
| quotes KB 行数 | 306 | **639** |
| 覆盖人物 | 23 中国 | 23 中国 + **22 海外** = 45 |
| 每人原话条数 | 3-5 | 3-5（海外人物 × 100+ 条总计） |
| URL 溯源覆盖 | 中国投资者 | 全部（包括 berkshirehathaway.com / oaktreecapital.com / goodreads / archive.org / farnam street / 雪球 / WSJ / CNBC / Bloomberg / NY Times） |

### 示例：Buffett 段落（全部带可点 URL）

```
### 巴菲特 (`buffett`) · Berkshire Hathaway Letters
**核心方法论**: 以合理价格买入优秀企业并长期持有...
**原话语料**:
1. "别人贪婪时我恐惧..." — [2004 年致股东信](https://www.berkshirehathaway.com/letters/2004ltr.pdf)
2. "用合理的价格买一家好公司..." — [1989 年致股东信](https://www.berkshirehathaway.com/letters/1989.html)
3. "我们最喜欢的持有期是永远。" — [1988 年致股东信](https://www.berkshirehathaway.com/letters/1988.html)
4. "只有在退潮时..." — [2001 年致股东信](https://www.berkshirehathaway.com/2001ar/2001letter.html)
5. "投资的第一条规则是不要亏钱..." — [雪球专栏](...)
**语言风格**: 朴素、幽默、爱打比方、农夫式智慧...
```

### 附带修复

- `investor_profile.py::PROFILES` 移除 `chengdu`（成都帮是席位集合体，不是个人；走 Group F fallback 更诚实）
- 增加 2 条 regression test：
  - `test_quotes_knowledge_base_covers_authored_personas`：确保每个 authored 人物都在 KB 有段落
  - `test_quotes_knowledge_base_has_source_urls`：抽查 buffett / soros / simons 段落必须带 http(s) URL 溯源

### 下游影响

Agent 在 Task 3 生成 51 评委 comment 时，读 KB 能拿到：
- 每人真实原话（而不是瞎编的"巴菲特风格"话术）
- 每人的语言风格关键词（便于模仿）
- URL 可溯源（用户如果质疑哪句话，能点开看原文）

这是让评委 panel 从"模板话术"升级到"真 persona"的最后一块基础建设。

### 回归

**30/30** regression tests pass（新增 2 条）

### 改动文件

- `skills/investor-panel/references/quotes-knowledge-base.md` · +333 行（22 个新人物段落）
- `skills/deep-analysis/scripts/lib/investor_profile.py` · 移除 chengdu（改走 group fallback）
- `skills/deep-analysis/scripts/tests/test_no_regressions.py` · +2 条测试
- 版本号 2.8.0 → 2.8.1（4 个 manifest）

---

## v2.8.0 — 2026-04-17 (persona profile · 因地制宜)

> **每个评委用自己的方法论回答 3 个新问题——不是模板，是 22 位标志性人物各自 authentic 的内容**

### 背景
用户拿到一份 Codex 给的 5 阶段评审系统重建计划（参考 buffett-skills 项目）。经过实地核查：
- buffett-skills 实际上只是单人物的 markdown 知识卡（9 个 md 文件，0 行代码，无多人物脚手架）
- Codex 建议的 S2（archetypes）/ S3（personas）/ S4（agent 写回）**80% 已在 UZI 实现**（51 评委 × 180 条规则 + 7 school × 8 stock style + agent_analysis.json 闭环）
- 按 Codex 计划重建会扔掉 1500+ 行工作代码

所以这版只做**真正的边际价值**：给每个评委加上 authentic 的 3 个决策字段。

### 核心原则 · 因地制宜

**不是给所有人加 3 个同样的模板字段**；是按每个投资者自己方法论填内容：

| 投资者 | time_horizon | position_sizing | what_would_change_my_mind |
|---|---|---|---|
| Buffett | 10 年以上 / 永远 | 集中前 5 大 70%+ | ROE 连续 2 年跌破 12% · CEO 离职且战略转向 |
| 赵老哥 | T+2 到 T+5 | 龙头板仓 10-20% | 板上砸盘 · 龙头断板 · 量能跟不上 |
| Simons | 平均持仓 < 2 天 | 等权数千只 < 0.5% | Sharpe 跌破 0.5 · 因子衰减 |
| Lynch | 公司故事讲完为止 3-5 年 | 30-50 只多样化 | PEG > 2 · 库存/应收增速超营收 |
| Soros | 反身性循环一轮 数周到数月 | 重仓押一次，任何时候可反向 | 市场停止验证我的叙事 |
| 冯柳 | 3-6 个月等错杀修复 | 偏均衡单票不超 10% | 基本面证伪（订单/产能/客户） |

### 新增

**`lib/investor_profile.py`** (~200 行)
- `PROFILES`：**22 个标志性人物**手写 authentic 3 字段
  - Group A 价值派 5 人：buffett / graham / fisher / munger / klarman
  - Group B 成长派 4 人：lynch / oneill / thiel / wood
  - Group C 宏观派 4 人：soros / dalio / druck / marks
  - Group D 技术派 2 人：livermore / minervini
  - Group E 中国价投 4 人：duan / zhangkun / fengliu / dengxiaofeng
  - Group F 游资 4 人：zhao_lg / zhang_mz / chengdu / lasa
  - Group G 量化 1 人：simons
- `GROUP_DEFAULT`：7 个流派级 fallback（好过通用默认，未单独注册的 29 人按流派走）
- `GENERIC_FALLBACK`：最后兜底

**接入链路**
- `lib/investor_evaluator.py::evaluate()` 返回值加 3 个字段
- `lib/investor_evaluator.py::_skip_result / _unknown_result` 也带 profile（即使 skip 也说自己的时间框架）
- `run_real_test.py::generate_panel()` 把 3 个字段写入 `panel.json[investors][*]`
- `assemble_report.py::render_investor_msg()` 在「展开完整结论」里新增「🧭 我的方法论」区块，展示 3 行

### 为什么不做 Codex 的其他阶段

| Codex 阶段 | 判断 | 理由 |
|---|---|---|
| S1 事实底座（per-字段 source/confidence） | 部分有价值 | 现有 `_integrity` 已覆盖大部分；per-字段粒度是增量，但工作量大 |
| S2 6-7 个流派模板 | **已完成** | `investor_db` school A-G + `stock_style.py` 7 style × 7 school 权重矩阵 |
| S3 persona 重建 | **已完成** | `investor_criteria` 180 条规则 + `investor_personas` voice + `investor_knowledge` reality-check |
| S4 agent 写回分 3 文件 | **反向** | 现有 `agent_analysis.json` 单文件统一所有 override，拆 3 个是倒退 |
| S5 Graph/RAG | 暂缓 | Codex 自己说"问题不在检索不够高级"，同意，Claude 直接 Read markdown 比建 vector store 便宜 10× |

### 回归

- **28/28** regression tests pass（新增 4 条）
- 所有 51 评委现在都有 3 字段输出（22 人 authentic，29 人 group fallback）
- buffett / zhao_lg / simons 三个典型 profile 差异性 unit-test 验证

### 改动文件

- **NEW** `scripts/lib/investor_profile.py` (+200 行)
- `scripts/lib/investor_evaluator.py` · +15 行（import profile + 3 字段 merge）
- `scripts/run_real_test.py::generate_panel` · +5 行
- `scripts/assemble_report.py::render_investor_msg` · +15 行（新「我的方法论」UI 区块）
- `scripts/tests/test_no_regressions.py` · +4 条测试
- 版本号 2.7.3 → 2.8.0（4 个 manifest）

---

## v2.7.3 — 2026-04-17 (data-source expansion)

> **按 Codex 建议扩充 14 个权威数据源 + 新增 `search_trusted` site: 限定搜索**

### 背景
Codex 建议补一批稳定层数据源，重点是「权威媒体 + 官方宏观 + 银行间利率 + 社区舆情」。本次经过全部 20+ URL 的联网可达性 + 结构探测后，按实测可用性落地。

### 实测验证（发布前）
```
✓ cnstock     中证网       200 OK   ddgs site: 返真实文章 URL
✓ cs_cn       中证网（cs.com.cn）  返"茅台股东大会一席难求"等真实标题
✓ stcn        证券时报     返"腾讯控股开启新一轮回购"
✓ nbd         每经网       返"贵州茅台2025年营业总收入约1721亿元"
✓ pbc         央行         返 LPR 政策文件
✓ stats_gov   统计局       返 PMI 2026/03 数据英文页
✓ chinabond   中债         yield.chinabond.com.cn/ 200 OK
✓ ine         能交所       200 OK
✓ guba_em_list 东财股吧     list,600519.html 含 169 条真实帖子
✓ jisilu / fx678 / cmc     reachable
```

### 新增

**registry 扩充 14 条数据源**（`lib/data_source_registry.py`）
- Tier-3 权威（ddgs 查询）: `cnstock` · `cs_cn` · `stcn` · `nbd` · `pbc` · `safe` · `stats_gov` · `chinamoney` · `chinabond` · `ine`
- Tier-2 增量: `guba_em_list` · `jisilu` · `fx678` · `cmc`
- 共 54 个 source（22 tier-1 + 11 tier-2 + 21 tier-3）

**`lib/web_search.py` 新增 `search_trusted(query, dim_key=...)` 辅助函数**
- 自动 prepend `(site:d1 OR site:d2 ...)` 到查询，限定在 dim 对应的权威域
- `TRUSTED_DOMAINS_BY_DIM` 映射 9 个定性维度到权威域白名单：
  - `3_macro`  → stats.gov.cn, pbc.gov.cn, safe.gov.cn, chinamoney.com.cn, chinabond.com.cn, 中证网...
  - `13_policy` → gov.cn, csrc, miit, ndrc, samr, pbc, safe, 中证网...
  - `15_events` → cs.com.cn, cnstock, stcn, nbd, sse, szse, hkexnews, 一财, 财联社...
  - `17_sentiment` → xueqiu, guba, tgb, jisilu, 知乎...
  - `18_trap` → 知乎, 微博, 小红书, 抖音, tgb, 股吧...
  - `7_industry / 14_moat / 8_materials / 9_futures` 同理

**接入 4 个关键定性 fetcher**
- `fetch_policy` · 全部查询改走 `search_trusted(dim_key="13_policy")`
- `fetch_macro` · 利率/政策/汇率走权威域；地缘/大宗保留普通 search
- `fetch_events` · 先权威域，命中 < 3 时兜底普通 search
- `fetch_moat` · 先权威域，命中 < 3 时兜底普通 search

**不改动的 fetcher**
- `fetch_sentiment` · 已有按平台 `site:` 查询，设计完备
- `fetch_trap_signals` · 需要明确命中小红书/抖音/微信群 → 强制权威域反而会漏掉风险信号

### 质量提升实例
查询 `2026 白酒 国家政策 扶持 利好`：
- v2.7.2：大量返回"白酒"词典解释 + 百科 + 广告
- v2.7.3：返工信部《酿酒产业提质升级指导意见（2026—2030 年）》原文 + 沪苏浙皖长三角工信委政策 + 其他政府真实政策文件

查询 `2026 中国 利率 货币政策`：
- v2.7.3：返 gov.cn LPR 政策解读、上海金融委 LPR 报告、中国政府网"LPR 年内首降"等真实政策文件

### 回归
- 24/24 regression tests pass（新增 3 条：trusted_domains 覆盖 / fetcher 接入 / registry 含新源）
- 所有 fetcher import OK
- fetch_policy('白酒') 实测返工信部政策文件

### 未实施（Codex 建议但实测不适合）
- `cnstock_news` 子域 403（反爬）→ 只用主域 + site: 搜索
- `fx678/news`、`tgb/search` 列表路径失效 → 走 ddgs site:
- `chinabond yield` API 需要特定签名 → 只做发现用途
- `zqrb / cffex / gfex / SEC` SSL 或反爬问题 → 先不放主链路
- `mairui` 需 license → 不作零配置主源，保留在建议 P2

### 改动文件
- `scripts/lib/data_source_registry.py` · +120 行（新增 14 个 DataSource）
- `scripts/lib/web_search.py` · +50 行（`TRUSTED_DOMAINS_BY_DIM` + `search_trusted`）
- `scripts/fetch_policy.py` · 全部查询切到 search_trusted
- `scripts/fetch_macro.py` · 3 类查询分流（权威 / 通用）
- `scripts/fetch_events.py` · 权威优先 + 通用兜底
- `scripts/fetch_moat.py` · 权威优先 + 通用兜底
- 版本号 2.7.2 → 2.7.3（4 个 manifest）

---

## v2.7.2 — 2026-04-17 (hotfix)

> **修复港股财报完全空 + 港股 K 线无 fallback + wave2 结束未 flush 的 3 个硬伤**

### 用户报告（Codex 外部测试）
> "港股完整性仍然只有 56%，关键缺口还在，例如 ROE 历史和 K 线阶段仍缺失；
> A 股贵州茅台卡在 stage1，wave 2 整体超时，耗时 465.8s，没有产出最终报告。"

### 根因 1（R7）· HK `1_financials` 分支从未实现
- `fetch_financials.main()` 对 HK 直接 `data = {}`，注释写 "akshare has
  stock_financial_hk_abstract but field names differ" 但 stub 从未补齐
- 港股 ROE / 营收 / 净利 / 毛利率 / 负债率 / ROIC 全部缺失 → 评委团盲评 → 报告 56%
- 修：新 `_fetch_hk(ti)` 走 `ak.stock_financial_hk_analysis_indicator_em`，
  返回 9 年年度指标（`ROE_AVG` / `ROE_YEARLY` / `ROIC_YEARLY` /
  `DEBT_ASSET_RATIO` / `CURRENT_RATIO` / `GROSS_PROFIT_RATIO` /
  `OPERATE_INCOME` / `HOLDER_PROFIT` + YoY），映射到与 A 股一致的
  `roe` / `roic` / `net_margin` / `gross_margin` / `revenue_growth` /
  `roe_history` / `revenue_history` / `net_profit_history` / `financial_health`
  结构，外加 HK 特有的 `eps` / `bps` / `currency` 字段。
- 验证：`00700.HK` → `roe=21.1%` · `roic=15.2%` · `roe_history=[28.1, 29.8, 24.6, 15.1, 21.8, 21.1]`

### 根因 2（R8）· HK K 线只有 1 条路径，GFW 一丢包就 0 根
- `_fetch_kline_impl(market=H)` 只有 `ak.stock_hk_hist`（东财 push2his），
  GFW/代理丢包 → 返回空 → `kline_count=0` → `stage='—'` → 技术面维度全废
- 修：新 `_kline_hk_chain` 三层 fallback，与 A 股链路对称：
  1. `ak.stock_hk_hist`（东财 push2, 原主路径）
  2. `ak.stock_hk_daily`（新浪, 覆盖全部港股 IPO 至今；验证 5366 rows）
  3. `yfinance 0700.HK`（海外兜底镜像；`0700` → `700.HK` 正确转换）
  Sina / yfinance 返回列名都归一到东财中文列（日期/开盘/收盘/最高/最低/成交量）
- 验证：东财被 mock 成 GFW 丢包 → Sina fallback 返回 561 rows →
  `stage='Stage 1 底部'` · `ma200=582.4` · `rsi_14=51` · `ytd_return=+19.8%`

### 根因 3（R9）· Wave2 结束未 flush，timeout 标记会丢
- `_persist_progress()` 每完成 3 个 fetcher 写一次 raw_data；但 wave2 结束
  后（含整体 300s 超时标记已写入 `dims`）没有 force flush
- 一旦 wave3 crash / 被 Ctrl+C，wave2 的 timeout 标记在内存但从未落盘
- 600519.SH 跑 465s 后 `12_capital_flow` 在 raw_data.json 里**完全不存在**
  （既不是 OK 也不是 timeout）—— 这让 agent 无法辨别"没跑过"还是"跑挂了"
- 修：wave2 结束立即 flush + stage1 收尾再 flush 一次。不管后续 wave3
  怎样，raw_data 始终反映最新完整状态，timeout 维度保留诊断信息。

### 关于 Python 版本
- 用户反馈："如果 python3.9 版本太低很多用不了，请上高版本"
- 验证结论：**3.9.6 实际跑得下来**。核心 deps (akshare 1.18.55 /
  yfinance 1.2.0 / baostock 0.9.10 / playwright / ddgs) 全部支持 3.9+。
- **不需要**抬 Python 版本下限；保持 3.9+ 兼容。报告的问题全部是数据层
  缺 HK 分支和 fallback，跟 Python 版本无关。

### 改动文件
- `scripts/fetch_financials.py` · 新增 `_fetch_hk(ti)` (+85 行)
- `scripts/lib/data_sources.py` · 新增 `_kline_hk_chain()` (+55 行)；
  `_fetch_kline_impl` HK 分支委托给 chain
- `scripts/run_real_test.py` · wave2 结束 + stage1 收尾各强制 `_persist_progress()`
- 版本号 2.7.1 → 2.7.2（4 个 manifest）
- BUGS-LOG · 新增 R7 / R8 / R9 记录

### 回归
- 18/18 测试全过
- Py3.9.6 import check OK
- HK `00700.HK` 两维真实接口调用验证 OK

---

## v2.7.1 — 2026-04-17 (hotfix)

> **修复 `19_contests` / `18_trap` 两维永远空的两个独立 bug**

### 用户报告
> "实盘比赛持仓，杀猪盘信号这些还是没数据"

### 根因 1（R5）· XueQiu 2026 加登录鉴权
- `xueqiu.com/cubes/cubes_search.json` 直访 → `400 + error_code: "400016"`
- 旧 fetch_contests 把任何 status≠200 当 0 cube → 19_contests 永空
- 修：新 `lib/xueqiu_browser.py` Playwright + 持久化 cookie；fetch_contests 透明
  标记 `login_required: True`；用户可 `--enable-xueqiu-login` opt-in
- README 加「需登录的数据源」章节，说明启用步骤

### 根因 2（R6）· ddgs 缓存空结果残留
- v2.6.1 之前 ddgs 没装 → `_ddg_search()` 返 [] → cache 缓存 12h
- 装 ddgs 后 cache 仍生效 → trap_signals 8 信号永远命中 0
- 修：清 `.cache/_global/api_cache/ws__*` cache（一次性）
- `_auto_summarize_dim` 改成显示 "8 信号扫描命中 0/8（已扫 ddgs 24 条搜索结果）"，
  让用户清楚是"扫了 0 命中"而不是"没扫"

### 新增
- `lib/xueqiu_browser.py` (~140 行) · Playwright + 持久化 cookie + opt-in 登录流程
- `run.py --enable-xueqiu-login` flag · `UZI_XQ_LOGIN=1` env var
- README "🔓 需登录的数据源" 章节
- BUGS-LOG · BUG#R5 + BUG#R6 记录
- 3 个新回归测试（共 18 个，全部通过）

### 浙江东方实测对比
| 维度 | 修前 | 修后 |
|---|---|---|
| 19_contests commentary | "暂未上榜实盘比赛"（误导：其实是接口 401） | "⚠️ XueQiu 需登录，启用方式：..." |
| 18_trap commentary | "🟢 安全；命中信号 0 条" | "🟢 安全 · 8 信号扫描命中 0/8（已扫 ddgs 24 条结果）" |

启用 XueQiu 登录后，可看到 50+ 个雪球组合持有 + 收益率分布。

---

## v2.7.0 — 2026-04-17

> **按股票风格动态加权评分 + 量化基金结构性识别 + 4 个 regression bug 修复 + 防回归测试 + bug 全量记录**

### 主线 · 风格动态加权（解决"分数都偏低、一片回避"的系统性问题）

旧公式 `consensus = bullish/active*100` 太严苛 → overall 普遍 < 40 → 一片回避。

新机制：
- **7 + 1 个 style** · 白马 / 高成长 / 周期 / 小盘投机 / 分红防御 / 困境反转 / 量化因子型 / 中性兜底
- `lib/stock_style.py` 自动识别 + 7×7 评委组矩阵 + 8 个个体 override
- 22 维 fundamental dim multiplier
- **neutral 半权计入 consensus**（修正旧公式 0% 权重核心 bug）

### 量化因子型 · 结构性识别（用户特别要求）

`lib/quant_signal.py` · 不维护白名单，用结构性特征：
> 第一大持仓 < 2% → 疑似量化基金；该股在多少家这种基金 top-10 → 触发 quant_factor

私募量化备查名单（10 个 · 幻方/九坤/灵均/明汯等）供 agent 走 LHB / web search 交叉验证。

### 修复 4 个 BUG（用户实测发现）

| ID | 症状 | 修法 |
|---|---|---|
| **R1** | ST 股错判 small_speculative | distressed 条件支持负 ROE |
| **R2** | fund_managers 还是 6 个 | wave3 调用 `limit=None`；浙江东方 6 → **332 个** |
| **R3** | agent 没主动核查就出报告 | 新 HARD-GATE-FINAL-CHECK |
| **R4** | mini_racer V8 crash on Py3.13 | wave3 默认 serial workers |

### 防回归基础设施
- `docs/BUGS-LOG.md` — 全量 bug 历史 + 10 条 don't 清单
- `scripts/tests/test_no_regressions.py` — 15 个回归测试，全部通过

### 浙江东方实测对比
| 项 | v2.6.1 | v2.7.0 |
|---|---|---|
| panel_consensus | 6.0 | **17.0** (+11.0) |
| **overall_score** | **39.8 (回避)** | **44.2 (谨慎)** |
| fund_managers 显示 | 6 个 | **332 个** |

---

## v2.6.1 — 2026-04-17 (hotfix)

> **追加论坛 bug · 直跑模式定性维度依然空** 修复

### 用户报告
跑完报告后发现 "宏观环境/政策/原材料/期货/事件" 5 维仍然空白。

### 根因（3 串）
1. `dim_commentary` 的 `dim_labels` 只覆盖 9/22 维，5 个定性维度直接 missing
2. fallback commentary 是 "[脚本占位] 待 Claude 补充"——哪怕 raw_data 已有数据
3. **`ddgs` 不在 requirements.txt** — 所有依赖 `lib/web_search` 的代码静默返回 0 结果（这是 v2.3 起的隐藏 bug）

### 修复
- `_auto_summarize_dim()` 覆盖全 22 维 · 把 raw_data 字段综合成 1-2 句中文摘要
- `_autofill_qualitative_via_mx()` MX → ddgs 二级兜底 · 失败显式标记
- `requirements.txt` 加 `ddgs>=9.0.0`

### 实测（浙江东方 600120.SH）
6/6 定性维度全有真实内容（5 维 ddgs 兜底 + 1 维原本有数据）。

---

## v2.6.0 — 2026-04-17

> **论坛 11 项 bug 综合修复 + Codex 测试发现的 5 个 PR#2 blocker**

### 论坛报告 bug（来自 [linux.do/t/topic/1981105](https://linux.do/t/topic/1981105)）

| # | bug | v2.6 修复 | 文件 |
|---|---|---|---|
| 2 | `KeyError: 'skip'` | preview_with_mock.py 加 'skip' key + .get() 兜底 | `preview_with_mock.py:322` |
| 11 | 失败卡死整条 pipeline | `as_completed(timeout=300)` + `result(timeout=90)` + 长尾 fetcher 180s 例外 | `run_real_test.py:113-220` |
| 9 | OpenCode 跑到 60% 停止不能续 | `collect_raw_data(resume=True)` + 增量保存 raw_data.json + `--no-resume` flag | `run_real_test.py` + `run.py` |
| 3 | python 直跑报错 | Py3.9 兼容（A） + 全部 import 测过 + render alias（E） | 多文件 |
| 10 | pypi 超时 | v2.4 已 4 级镜像 fallback；v2.6 加诊断输出 | `run.py:check_dependencies` |
| 8 | 反爬数据缺失 | 新增 `_fetch_price_tencent_qt(market, code)` A/H/U 通用价格兜底 | `lib/data_sources.py` |
| 5 | 排序异常（最看空 27 vs 0 不一致） | 排除 score=0 异常 + 按 score 排（不再按 signal 分组）+ 矛盾警示 | `run_real_test.py:712-746` |
| 6 | 编造事实（药明康德↔Apple） | 新 HARD-GATE-FACTCHECK 强制 cite raw_data | `SKILL.md` |
| 1 | 非 Claude 评委对齐错位 | 新 `lib/agent_analysis_validator.py` schema 校验 + `_agent_analysis_errors.json` 写盘 | 新文件 + stage2 |
| 4 | Codex 兼容差 | run.py Codex 检测增强 + SKILL.md 新增"Codex 自适配"小节 | `run.py` + `SKILL.md` |
| 7 | Claude plugin 不能执行 | hooks.json 直调 session-start（去掉 polyglot run-hook.cmd 中间层）+ chmod | `hooks/hooks.json` + `hooks/README.md` |

### Codex 在 PR#2 测试中发现的 5 个 BLOCKER

| Blocker | 修复 |
|---|---|
| A: `str \| None` Python 3.10+ 语法在 3.9 报错 | `from __future__ import annotations` 加到所有 v2.3+ 新文件 + run.py |
| B: `mini_racer` V8 thread crash on 600519 | 给 fetch_industry/capital_flow/valuation 加共享 `_MINI_RACER_LOCK` |
| C: 报告 banner 还显示 v2.2 | run.py + assemble_report.py 动态读 plugin.json，模板加 `{{PLUGIN_VERSION}}` |
| D: HK price 是 None | Tencent qt 兜底（同 bug 8）实测 00700 拿到 ¥510 |
| E: render_share_card / render_war_report 缺 main() | 加 `main = render` alias |

### 新增 lib

- `lib/agent_analysis_validator.py` — schema 校验 (~250 行)
  - 检查 dim_commentary/panel_insights/great_divide_override/narrative_override/buy_zones 类型
  - error 级 + warning 级
  - `format_issues()` 漂亮控制台输出

### 新增 flag

- `python run.py {ticker} --no-resume` — 强制重抓全部 22 fetcher
- 默认 resume：复用 `.cache/{ticker}/raw_data.json` 中已有有效维度（节省 80% 时间）

### 测试验证

- ✅ Python 3.9.6 (默认 macOS python3) 可 import 所有模块
- ✅ Python 3.13 (conda) 跑通完整流程
- ✅ Tencent qt 三市场实测：A 600519 / H 00700 / U AAPL 都返回有效 price
- ✅ Validator 自测 3 个 case 通过

---

## v2.5.0 — 2026-04-17

### 数据源注册表（v2.5 主题）
- **`lib/data_source_registry.py`** — 40+ 个数据源元数据集中管理（新文件，~330 行）
  - 3 个 Tier：HTTP 主源 (22) / Playwright 浏览器源 (7) / 官方披露源 (11)
  - 字段：id / name / url / markets / dims / tier / access / health / notes
  - 辅助函数：`by_dim()` / `by_market()` / `http_sources_for()` / `playwright_sources_for()`
- **`task2.5-qualitative-deep-dive.md` URL 模板扩充**
  - Dim 3 加 华尔街见闻 / 第一财经 / Investing 经济日历 + 商品
  - Dim 4 新加段（A/H 浏览器源）
  - Dim 7 加 问财 / 同花顺 F10
  - Dim 13 加 财联社 7x24 / 华尔街见闻
  - Dim 15 加 财联社 / 第一财经 / 金融界 / 网易财经；HK 段加 HKEXNews + AASTOCKS
  - Dim 16 新加段（云财经龙虎榜 + 东财）

### 港股 5 维实际增强
- **`lib/hk_data_sources.py`** — 包装之前未用到的 50+ akshare HK 函数（新文件，~200 行）
  - `fetch_hk_basic_combined`：XQ basic + EM company profile + EM valuation/scale/growth comparison
  - `fetch_hk_announcements`：HKEXNews 静态 HTML 抓取（基础版）
- **`_fetch_basic_hk` 重写**（data_sources.py）：从 1 个 push2 调用扩展到 4 源 fallback chain
  - 新拿到字段：industry / pe_ttm / pb / market_cap / 主营业务 / chairman / ranks / 港股通标记
  - 实测 00700：industry=软件服务、PE=18.95、PB=3.69、市值=4.13万亿、HK 排名第 1
- **`fetch_peers.py` HK 分支**：rank-in-HK-universe 替代具体同行表（agent 可走 AASTOCKS Playwright 补充）
- **`fetch_capital_flow.py` HK 分支**：港股通资格 (沪/深) + eniu 30日市值历史
- **`fetch_events.py` HK 分支**：HKEXNews 公告 + 中文 web search 兜底

### AGENTS.md
- 新增"数据源速查表"小节：按 dim × 市场列出推荐源优先级
- Python 调用示例（agent 怎么用 registry）

### 维持兼容
- `requirements.txt` 不变（无新 pip 依赖）
- AASTOCKS 仅作 Tier-2 Playwright 源在 registry 出现，不写 fetcher 代码（HTML 是 JS 渲染的）
- 1_financials / 6_research / 16_lhb 等其他 6 个 HK dim 仍 stub，标在 RELEASE-NOTES "已知缺口"

### 已知缺口（next）
- HK price/change_pct（push2 spot 不通；agent 可走 Tencent qt: `qt.gtimg.cn/q=hk{code5}`）
- HK 财报 / HK 研报 / HK 沪深港通持股变动 / HK 同行具体 list（全走 AASTOCKS Playwright）

---

## v2.4.0 — 2026-04-17

### 大佬抓作业完整性
- `fetch_fund_holders.py:limit` 默认从 50 → None，茅台实测 649 家主动权益基金全部收录
- `assemble_report.render_fund_managers` 第 7 位起切换到紧凑行（48px × 滚动）
- 并行计算 fund_stats（默认 3 workers，`UZI_FUND_WORKERS=1` 切串行）

### 6 维定性深度方法论
- 新增 `references/task2.5-qualitative-deep-dive.md`（~400 行）
  - 3 个并行 sub-agent 分工（Macro-Policy / Industry-Events / Cost-Transmission）
  - 每维 4-7 必答问题、6 条跨域因果链
- SKILL.md 新增 HARD-GATE-QUALITATIVE
- pip 国内镜像自动 fallback（清华 → 阿里云 → 中科大 → 豆瓣）
- AGENTS.md 新增"网络受限环境"场景 A/B/C

---

## v2.3.0 — 2026-04-17

### 中文名纠错 + MX 妙想 API 接入
- 新 `lib/name_matcher.py` (Levenshtein + Jaccard fuzzy)
- 新 `lib/mx_api.py` (东财妙想 Skills Hub `mkapi2.dfcfs.com` 客户端)
- 三层解析：MX → akshare 精确 → 本地 fuzzy
- `.env` + `--force-name`

### 数据缺口 agent 接管
- `data_integrity.generate_recovery_tasks` 输出 agent 任务清单
- HTML 报告顶部橙色 banner 标注缺失字段
- HARD-GATE-NAME + HARD-GATE-DATAGAPS

---

## v2.2.0 (develop) — 2026-04-16

### Agent Closed-Loop (核心改动)
- **`agent_analysis.json`**: 新增闭环文件，agent 的定性分析独立存储
- **`generate_synthesis()` 合并机制**: 优先使用 agent 写入的字段，仅对缺失字段生成 stub
- **`stage2()` 自动读取**: 读取 `agent_analysis.json` 并传给 `generate_synthesis` 合并
- **`agent_reviewed` 标记**: synthesis 输出带标记，明确标识是否有 agent 介入
- **HARD-GATE 增强**: 必须写 `agent_analysis.json` + 设置 `agent_reviewed: true` 才能进 stage2
- **合并优先级**: agent dim_commentary > stub，agent punchline > 脚本金句，agent risks > 低分维度生成

### Agent 可覆盖字段
- `dim_commentary` — 每维度定性评语
- `panel_insights` — 评委整体观察
- `great_divide_override.punchline` — 冲突金句
- `great_divide_override.bull_say_rounds` / `bear_say_rounds` — 辩论 3 轮
- `narrative_override.core_conclusion` — 综合结论
- `narrative_override.risks` — 风险列表
- `narrative_override.buy_zones` — 四派买入区间

### Bug Fixes
- Fixed: `main()` 函数 `standalone_path` 不在作用域（NameError）

---

## v2.1.0 — 2026-04-16

### Architecture
- **Two-stage pipeline**: `stage1()` (data + skeleton) → agent analysis → `stage2()` (report)
- **HARD-GATE tags**: Claude cannot skip agent analysis step
- **Multi-platform support**: `.codex/`, `.opencode/`, `.cursor-plugin/`, `GEMINI.md`
- **Session hooks**: `hooks.json` auto-activates on session start
- **Agent template**: `agents/investor-panel.md` for sub-agent role-play

### Investor Intelligence
- **3-layer evaluation**: reality check (market/holdings/affinity) → rule engine → composite
- **Known holdings**: Buffett×Apple=100 bullish (actual holding), 游资×US=skip
- **Market scope**: Only 游资 restricted to A-share; all others evaluate globally

### Bug Fixes
- Fixed: KeyError 'skip' in sig_dist and vote_dist
- Fixed: investor_personas crash on skip signal
- Fixed: Hardcoded risks "苹果订单" appearing for all stocks
- Fixed: Great Divide bull/bear score mismatch with jury seats
- Fixed: build_unit_economics crash when industry is None
- Fixed: Capital flow empty (北向关停 → 主力资金替代)
- Fixed: LHB empty → show sector TOP 5
- Fixed: Governance pledge parsing (list[dict] not string)

---

## v2.0.0 — 2026-04-16

### New Features
- **17 institutional analysis methods** from anthropics/financial-services-plugins
  - DCF (WACC + 2-stage FCF + 5×5 sensitivity)
  - Comps (peer multiples + percentile)
  - 3-Statement projection (5Y IS/BS/CF)
  - Quick LBO (PE buyer IRR test)
  - Initiating Coverage (JPM/GS/MS format)
  - IC Memo (8 chapters + Bull/Base/Bear scenarios)
  - Porter 5 Forces + BCG Matrix
  - Catalyst Calendar, Thesis Tracker, Idea Screen, etc.
- **51 investor panel** with 180 quantified rules
- **Rule engine**: investor_criteria.py + investor_evaluator.py + stock_features.py (108 features)
- **Data integrity validator**: 100% coverage check after Task 1
- **Bloomberg-style HTML report** (~600KB self-contained)
- **14 slash commands**: /dcf, /comps, /lbo, /initiate, /ic-memo, /catalysts, /thesis, /screen, /dd, etc.

### Data Sources
- 22 dimensions, 8+ data sources, multi-layer fallback
- All free, zero API key (akshare/yfinance/ddgs/eastmoney/xueqiu/tencent/sina/baidu)

---

## v1.0.0 — 2026-04-14

- Initial release
- 19 dimensions + 50 investor panel + trap detection
- Basic HTML report
