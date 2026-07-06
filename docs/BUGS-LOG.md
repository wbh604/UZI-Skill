# BUGS-LOG · 防回归记录

每个 bug 修完都登记到这里。**未来改这些代码区域时，必须回看本文件确保不引入回归。**
对应单元测试在 `skills/deep-analysis/scripts/tests/test_no_regressions.py` + `tests/test_v2_10_4_fixes.py` + `tests/test_v2_11_scoring_calibration.py` + `tests/test_v2_12_1_data_fixes.py` + `tests/test_v2_13_playwright_strategy.py` + `tests/test_v3_9_2_flow_bugfixes.py`。

**登记规范**：每条必含 症状 / 位置 / 根因 / 影响 / 修法 / 验证 / 回归测试 / "未来改该区域注意事项"

---

## v3.9.2 (2026-07-07 · 流程与数据契约 hotfix · issue #82/#83)

### BUG · OCF 缺失、industry=None、CLI report 后处理早退、agent_analysis 坏结构继续合并

- **症状**：
  1. [#82](https://github.com/wbh604/UZI-Skill/issues/82) · `fetch_financials` 只把经营现金流写成 `fcf`，没有显式 `ocf` / `ocf_history` / `ocf_to_net_income_ratio`，A 股 trap-detector 的现金利润匹配规则会读不到真实 OCF。
  2. [#83](https://github.com/wbh604/UZI-Skill/issues/83) · `basic.industry=None` 时 `fetch_peers` 整个 A 股分支跳过，返回空同行表且 `fallback=False`；`fetch_valuation` 也直接丢行业/市场 PE。
  3. fund/ETF/LOF 持仓汇总、`--versus`、`--portfolio` 生成 HTML 后直接 `sys.exit(0)`，绕过 `--output-dir` / `--remote` / 浏览器打开。
  4. `agent_analysis.json` schema error 只打印 `_agent_analysis_errors.json`，但仍传给 `generate_synthesis`，坏结构可能污染报告或触发 `.get()` 异常。
- **位置**：
  - `fetch_financials.py` 现金流段
  - `fetch_peers.py` A 股 `industry` 分支
  - `fetch_valuation.py` cninfo 行业 PE 段
  - `run.py` CLI 分支和 remote 后处理
  - `run_real_test.py::stage2`
  - `lib/pipeline/fetchers/registry.py`
- **根因**：
  - 数据契约漂移：legacy fetcher 输出 `financial_health` / `pe_quantile`，registry 却期待顶层 `debt_ratio/current_ratio` / `pe_ttm/pe_percentile`。
  - 控制流分散：多报告模式各自早退，没有共享 report post-process。
  - schema validator 只写错误清单，没有把 error 级问题转成 fallback。
- **影响**：
  - 现金流质量被默认值掩盖，可能把 OCF/净利大幅背离的股票误判为通过。
  - 行业缺失时报告同行/估值区块空白但不标 fallback。
  - SaaS/远程查看模式在 fund/versus/portfolio 下失效。
  - 非 Claude/Codex 生成的坏 `agent_analysis.json` 可能导致 stage2 崩溃或错用用户覆盖字段。
- **修法**：
  1. `fetch_financials._apply_operating_cash_flow` 显式输出 OCF 字段；`stock_features` 读取 `ocf_to_net_income_ratio`。
  2. `fetch_peers` 在 industry 缺失时 self-only fallback，并写 `fallback_reason`。
  3. `fetch_valuation` 在 industry 缺失/未匹配时用 cninfo 市场加权 PE 兜底，并写 `industry_pe_fallback_reason`。
  4. pipeline registry 对齐 legacy 输出字段。
  5. `run.py` 抽出 direct report path + shared post-process，fund summary / versus / portfolio 均复用 `--output-dir` / `--remote`；`cloudflared` 缺失时默认只提示，显式 `--install-cloudflared` 才自动安装。
  6. `run_real_test._validate_agent_analysis_or_fallback` 对 error 级 schema issue 直接丢弃 payload，回退脚本骨架。
- **验证**：新增 `tests/test_v3_9_2_flow_bugfixes.py`，覆盖 8 个回归。
- **未来改该区域注意事项**：
  - 新增/改名 fetcher 字段时，同步更新 `lib/pipeline/fetchers/registry.py`，并加行为测试，不只 grep 源码。
  - 所有“生成 HTML 的 CLI 模式”都必须返回 report path 并进入统一 post-process；不要再在 runner 分支里直接 `sys.exit(0)`。
  - `cloudflared` / `brew` / `sudo` 属于系统变更，默认只提示，必须显式 opt-in。

## v3.8.1 (2026-06-09 · 全面体检 · H/I 两组配套层 6 处补齐)

### BUG · 加评委没加配套 · 6 个静默降级缺陷

- **症状**：v3.6.3 (Serenity I 组) / v3.7.0 (13 位科技大佬 H 等组) 上线后 · 报告中
  ① 14 位新评委头像破图 ② 流派评分卡永远只显示 7 派（H/I 静默消失）③ H/I 组标签
  显示裸字母 ④ H/I 评委的 time_horizon/position_sizing 全 "—" ⑤ 风格动态加权对
  H/I 失效 ⑥ 新评委群聊台词全是 generic 套话
- **根因**：加评委只改了 investor_db + investor_criteria · 但仓库里有 **6 处按组
  遍历/查表的硬编码 A-G 配套层** · 全部用 `.get(g, default)` 优雅降级 → 不崩 ·
  所以 CI 全绿 · 视觉缺陷一直没暴露
- **修法**：
  1. `gen_pixel_avatars.py` 重跑 → 补 14 头像（脚本本身就支持增量 · 之前没人跑）
  2. `special_cards.render_school_scores` order A-G → A-I
  3. `panel_cards.GROUP_LABELS` + `special_cards` 内联副本 → 补 H/I
  4. `investor_profile.GROUP_DEFAULT` → 补 H/I 流派档案
  5. `stock_style.STYLE_GROUP_WEIGHTS` 8 风格 × 补 H/I 列
  6. `MARKET_SCOPE` 13 人显式登记 + `PERSONAS` 13 人 voice 台词
- **验证**：10 个体检回归测试 (`test_v3_8_1_audit_fixes.py`) · 632 passed
- **未来改该区域注意事项**（防再犯 · 关键）：
  - **加新评委的 checklist**（缺一不可）：investor_db → investor_criteria →
    `gen_pixel_avatars.py` 重跑 → MARKET_SCOPE → PERSONAS 台词 → 若新增组：
    GROUP_LABELS ×2 / render_school_scores order / GROUP_DEFAULT /
    STYLE_GROUP_WEIGHTS / SCHOOL_LABELS / run.py --school choices /
    _render_school_lock_banner THEMES / score_fns GROUP_META
  - 体检测试 `test_v3_8_1_audit_fixes.py` 已把以上大部分变成硬断言 ·
    新加组时这些测试会先红 · 跟着修就不会漏
  - 不要依赖 `.get(g, 1.0)` 这类优雅降级当"没问题"的证据 —— 它恰恰是
    本次 6 个缺陷能潜伏两个版本的原因

---

## v3.6.3 (2026-06-03 · 重磅角色 Serenity · AI 卡位/瓶颈猎手 I 组)

### BUG · Serenity 卡位关键词库漏掉 AR/消费光学，把光学股误判成「不在 AI 链」

- **症状**：实测 `python run.py 002273 --depth lite`（水晶光电，真实行业「光学光电子」· AR/VR + 车载光学 + iPhone 相机模组 · 市值 404 亿）· Serenity 给出 `bearish / 0`，headline「不在 AI 产业链上 —— 对我没有意义」。但水晶光电明显踩在 AR/AI 光学链上，应识别为「在链但卡位不够硬 → neutral」，而非一票否决。
- **位置**：`skills/deep-analysis/scripts/lib/stock_features.py` · 派生特征 `ai_chokepoint_score` 的 `_AI_CHOKEPOINT_KW` 关键词库
- **根因**：关键词库只覆盖了**数据中心光**（光模块/CPO/光通信/光器件/激光器）+ 先进封装 + 化合物半导体 + 互连 + 算力，**漏了 AR/消费/车载光学族**（光学/光电子/光学元件/光波导/滤光片/镀膜/棱镜/镜头/相机模组/AR-VR/近眼显示/车载光学）。`光学光电子` 行业整段命中 0 词 → `ai_chain_hit=False` → 直接腰斩到 score≈0。
- **影响**：所有 AR/VR/消费光学/车载光学方向的真实卡位候选（水晶光电、蓝特光学、舜宇、长光华芯等）会被 Serenity 误判为「不在 AI 链」而错杀，丧失「在链→再按不可替代性/市值判断」的分级能力。
- **修法**：`_AI_CHOKEPOINT_KW` 扩充一组 AR/光学终端侧词条。**注意刻意不加裸词 `ar`/`vr`/`mr`**（会在 lowercase 的 JSON blob 里匹配到 market/margin/warrant 等英文子串造成全局误命中）· 改用中文词（增强现实/虚拟现实/混合现实/头显/近眼显示）+ 带斜杠的 `ar/vr` + `ar眼镜`。
- **验证**：
  - 水晶光电真实数据重评 → `ai_chain_hit=True`（命中 光学/光电子/相机模组/ar-vr/车载光学）· 卡位分 70.1 · 但不可替代=False(切换5+规模6=11<12) + 市值404亿>300 → **neutral / 59**「命中 AI 链但可替代性偏高、市值偏大，不是真瓶颈」（地道的 Serenity 视角）
  - `test_serenity_rules.py` 7 项不破：白酒(高粱酿造)/银行(存款贷款) 仍 `ai_chain_hit=False` → bearish（无 AR/光学词误命中）
  - 全量 532 passed
- **未来改该区域注意事项**：
  - **永远不要在 `_AI_CHOKEPOINT_KW` 加 2 字母以内的裸英文词**（ar/vr/mr/ic/ai 单独）· blob 是 lowercase 拼接的中英文 + JSON · 短英文子串必然误命中。要加英文必须够长够特异（waveguide / micro-led / cowos）。
  - 扩词只影响 `ai_chain_hit` 这道**门槛**；是否 bullish 仍由 `chokepoint≥70 + 不可替代 + 中小市值` 三条 weight-5 规则把关。所以扩词宁可**宽进严出**，不会让普通光学股变成 Serenity 重仓。
  - 改词库后必跑 `test_serenity_rules.py::test_bearish_on_non_ai_regardless_of_moat`（确保非 AI 股仍被否）。

---

## v3.6.2 (2026-06-03 · cninfo 翻页长尾 #68 + install-hermes.sh pip 探测 #69)

### BUG #68 · cninfo 公告分页 854 页拖几小时

- **症状**：用户 [@xy2yp](https://github.com/wbh604/UZI-Skill/issues/68) 反馈 `python run.py --versus 000958 600406 --depth lite` 卡在 15_events 维度 · 进度条 `0/854 [01:53<6:11:58, 26.44s/it]` · 单股 4-6 小时
- **位置**：`skills/deep-analysis/scripts/fetch_events.py::_cninfo_disclosures`
- **根因**：调 `akshare.stock_zh_a_disclosure_report_cninfo` · 该 akshare 函数内部用循环翻完全部分页（cninfo 一只票常有 800+ 页公告）才把 DataFrame 返给我们 · 后续 `.head(30)` 截取已无用 · 翻页时间已经花掉了
- **修法**：
  1. 新增 `_cninfo_direct_api(code, page_size=30, timeout=15)` · 直接 `requests.post` 到 `http://www.cninfo.com.cn/new/hisAnnouncement/query` · `pageNum=1 + pageSize=30` · 一次 HTTP ≤15s · 永远不翻全部页
  2. 板块路由：`000/001/002/3xx → szse` · `6xx/688 → sse` · `8xx → bse`
  3. 响应解析：`announcements[*].announcementTime` (毫秒) / `announcementTitle` / `adjunctUrl` (拼 `http://static.cninfo.com.cn/` 前缀)
  4. `_cninfo_disclosures` 优先调直连 API · 直连失败时**默认不调 akshare**（防长尾）· 仅 `UZI_AK_CNINFO_FALLBACK=1` 显式启用时才走 akshare 慢路径
- **验证**：
  - mock `requests.post` ConnectionError → 返 [] · 不抛
  - mock 200 + 合法 JSON → 解析正确 / 路由正确
  - 网络失败 + 未设 fallback env → 不调 akshare（关键 · 防止再次踩坑）
- **未来改该区域注意事项**：
  - **永远不要回去用 `ak.stock_zh_a_disclosure_report_cninfo`** · 这是 akshare 实现的死结 · 它会翻完所有页
  - 直连 API 的 pageSize 上限 cninfo 文档说 30 · 别贪心设大数字（会被服务端拒）
  - cninfo 的时间戳是 **毫秒** · 不要忘了 `/ 1000` 再 `fromtimestamp`
  - 板块路由 prefix 列表要保持齐：未来 cninfo 加新板块要更新（如果 北交所 8xx 后还有新代码段）

### BUG #69 · install-hermes.sh 在 Linux 找不到 pip

- **症状**：用户 [@FrankHuy](https://github.com/wbh604/UZI-Skill/issues/69) 在 CentOS-like + Python 3.11 跑一键脚本：`line 95: pip: command not found` + akshare 装不上
- **位置**：`install-hermes.sh` line ~94（装依赖段）
- **根因**：很多 Linux 发行版（Debian/Ubuntu/CentOS/RHEL）**默认不提供 plain `pip` 命令** · 用户必须用 `pip3` / `python3 -m pip` · 我们脚本只试 `pip` 直接报错 · 后续 akshare 报"找不到 wheel"其实是因为底层 pip 不存在 · 不是真的 wheel 不兼容
- **修法**：
  1. 启动加 Python 版本预检（`python3` → `python` 探测 + 版本 ≥3.10 检查）· 警告而非阻断 · 给三种系统的安装命令
  2. pip 探测改为 5 层级联：`$HERMES/venv/bin/pip` → `$HERMES/.venv/bin/pip` → `pip` → `pip3` → `$PY_BIN -m pip`
  3. 全部探测失败 → exit 4 + 给 apt / yum / ensurepip / get-pip 四种安装路径
  4. `pip install` 失败 → exit 5 + 提示版本/镜像源/升级 pip
- **验证**：
  - `bash -n install-hermes.sh` 语法过
  - 测试 grep 验证脚本含 pip3 / -m pip / tuna.tsinghua / upgrade pip 等关键字
- **未来改该区域注意事项**：
  - 不要在主体代码里假设 `pip` 命令存在 · 用 `command -v` 探测
  - `set -euo pipefail` 严格模式下任何 fail 立即退出 · 必须 *先* 探测再 *用*
  - 镜像源 fallback 只在文案里建议 · 不要默认走清华源（部分海外用户访问慢）· 让用户主动加 `-i`

---

## v3.6.1 (2026-05-29 · Hermes Skills Guard 假阳性绕过 · issue #66)

### BUG · `hermes skills install` 报 DANGEROUS · `--force` 覆盖不了

- **症状**：用户 @zodiacg ([#66](https://github.com/wbh604/UZI-Skill/issues/66)) 反馈 `hermes skills install wbh604/UZI-Skill/skills/deep-analysis` 失败 · scanner 168 findings · DANGEROUS verdict
- **位置**：Hermes Skills Guard 模式匹配扫描器（NousResearch/hermes-agent · 上游 bug · 不是 UZI-Skill 的问题）
- **根因**：Skills Guard 是 v0.x 纯模式匹配 (`r'os\.environ\b'`) · 不区分"读自己配置"vs"窃取用户敏感 env" · 也不识别 docstring / HTML 注释 / opt-in 用户功能
- **影响**：community 源任何 finding 都会 BLOCK · `--force` 设计上不能覆盖 DANGEROUS · 用户 Hub 装不下来
- **修法**：提供 `install-hermes.sh` 一键脚本 · `git clone + ln -sfn` 到 `~/.hermes/skills/` · 跳过 Hub quarantine 扫描 · Hermes 跑时只看目录 layout · 完全等价
- **绝不能做的事**：
  - ❌ 用 dynamic import + 字符串拼接绕 Skills Guard 检测（这是上游 issue #7072 提到的恶意绕过 · 我们绝不走这条路 · 那是窃取信任模型）
  - ❌ 删除合法的 `os.environ.get` 代码来降 findings · 那是把功能砍了
  - ✅ 只提供 clone+symlink 路径 · 用户主动决定信任我们 · 而不是欺骗 Hub 让它判 "safe"
- **验证**：
  - `bash install-hermes.sh` 在干净环境跑通 · 4 个 skill symlink + venv pip 装包 + SKILL.md 版本验证
  - 11 个回归测试 (`test_v3_6_1_install_hermes.py`)
- **未来改该区域注意事项**：
  - 若 Hermes Skills Guard 升级到 allowlist 模型 · `hermes skills install` 重新可用时 · 在 INSTALL-HERMES.md 顶部加 "Skills Guard 已修 · 直接 hub 装" 提示
  - 但 install-hermes.sh 应该保留作为 dev 路径（clone + symlink 让 git pull 立刻生效 · Hub 装是 snapshot）
  - 改 skill 目录结构时 · 必须同步更新脚本里的 `SKILLS=(deep-analysis ...)` 数组
  - 永远不要"为了 Skills Guard 评分好看"砍合法功能 · `--remote` cloudflared 是用户主动 opt-in · 默认不跑

---

## v3.6.0 (2026-05-29 · 视觉升级 + 多股对比 + 组合分析)

### FEATURE A1 · 暗色模式 toggle

- **位置**：`assets/report-template.html`（CSS `:root` + `[data-theme="dark"]` 块 · 末尾 `<script>` toggle 段）
- **改动**：
  1. 新增 `[data-theme="dark"]` 块 · 30+ 个 CSS 变量重定义（slate-900 风 + 提亮 neon）
  2. topbar 加 `<button id="theme-toggle">` · 默认 🌙 / 切换后 ☀️
  3. JS 初始化优先级：`localStorage.getItem('uzi-theme')` > `prefers-color-scheme: dark` > light
  4. 持久化：每次 toggle 都写 `localStorage` · 跨刷新生效
- **未来改该区域注意事项**：
  - 加新 CSS 变量时 · 必须同时在 `:root` 和 `[data-theme="dark"]` 都定义 · 否则暗色模式回退到 light 默认值
  - 不要硬编码 `#000000 / #ffffff` · 必须用 `var(--text-bright)` 等抽象

### FEATURE A2-3 · sticky TOC + count-up

- **位置**：`assets/report-template.html`（CSS `.toc-rail`/`.toc-item` · HTML `<nav class="toc-rail">` · 8 个 `id="section-X"` 锚点 · JS 末尾段）
- **改动**：
  1. 给 8 个 section-head div 加 `id="section-{core/clash/jury/chat/scan/modeling/risks/zones}"`
  2. 左侧 `.toc-rail` fixed 50% · `@media (max-width:1280px)` 隐藏
  3. JS 用 IntersectionObserver `rootMargin: '-30% 0px -50% 0px'` 命中段加 `.active` class
  4. count-up：找 `.score-giant, .sc-score-giant, .hero-score-num, .confidence` · 进入视口动画
- **未来改该区域注意事项**：
  - 增减章节时必须同步：HTML section id + TOC `<a href="#X">` + 顺序 · 不一致会出现 active 跳到错位置
  - count-up selector 用类名匹配 · 改样式时不要把 `.score-giant` 重命名 · 否则动画失效

### FEATURE A4 · 金融术语悬浮 tooltip · 🔒 XSS 安全加固

- **位置**：`assets/report-template.html`（JS 末尾 `TERMS` dict + `tooltipify` 函数）
- **改动**：
  1. `TERMS` dict 含 12 个核心术语（PE/PB/ROE/DCF/IRR/WACC/EV-EBITDA/LBO/YTD/TTM/PEG/LHB）
  2. 扫描 `.panel-insights / .dim-card .body / .friendly-layer / .risk-box / .punchline / .dim-row / .school-scores .desc / .round-bull / .round-bear / .qr-desc` 内 text node
  3. 用 `createDocumentFragment + createElement('span') + textContent + setAttribute('data-tip', ...)` 安全构造 · 不用 `innerHTML`
  4. 词条按长度降序匹配 · `\\b` 边界 + RegExp 防止 PE 误匹配 PEG
- **安全要点**：
  - **永远不要用 `node.innerHTML = ...` 处理动态术语 / 用户数据**（XSS 风险）
  - `textContent` 自动转义 · `setAttribute` 也安全 · 是首选
  - 测试 `test_tooltipify_uses_safe_dom_no_innerhtml` 守护这一点
- **未来改该区域注意事项**：
  - 加新术语只需扩 `TERMS` dict
  - 不要为了"省事"用 innerHTML 拼接 — 这是 security hook 检查项
  - 长术语在前（`EV/EBITDA` 在 `PE` 前）· 防止短词先匹配吞掉长词

### FEATURE A5 · 报告 QR 码

- **位置**：`assets/report-template.html`（CSS `.share-qr-card` · HTML 在 buy-zones 之后 share button 之前 · JS `drawQR` 函数）
- **改动**：
  1. `<canvas id="report-qr-canvas">` 200×200 · 用 Google Chart API (`api.qrserver.com`) 远程生成
  2. file:// 协议下不调 API · 用 `canvas.getContext('2d').fillText` 提示用 `--remote`
  3. 网络失败 fallback · 显示 "QR offline"
- **未来改该区域注意事项**：
  - QR 服务商可换 · 但接口签名 `data=<url>` 通用 · 不要硬编码尺寸到 URL
  - 不要 innerHTML 注入 URL · 用 canvas 2D 绘图安全

### FEATURE B · 多股横向对比 `--versus`

- **位置**：`lib/versus_runner.py` (新文件 380 行) · `run.py` argparse + 早返回段
- **核心函数**：
  - `_load_cache(ticker)` → bundle{syn, raw, panel}
  - `_extract_metrics(bundle)` → 12 个核心字段 dict
  - `_winner(values, higher_is_better)` → winner index · 全空返 -1 · 跳过 0
  - `_render_comparison_grid(stocks)` → table HTML · ★ WIN 标注
  - `_render_html(stocks, depth)` → 完整 HTML（复用主模板 CSS）
  - `run_versus(tickers, depth, auto_open)` → dispatch
- **不破坏现有行为**：
  - `--versus` 早返回 · 不影响单股分析路径
  - 输入校验 2-4 只 · 其他长度 invalid_input
- **未来改该区域注意事项**：
  - 改 `ROWS` 加新对比维度时 · winner 高低需明确（`higher_is_better` 字段）· None=不比
  - 模板 CSS 路径用 `ASSETS_DIR` 常量 · `.parents[1]` 推算 scripts dir · 不要硬编码
  - `_render_html` 复用主模板 `<style>` 块 · 主模板改 CSS 时这里自动跟随
  - dark-toggle JS 简化版 (无 TOC/jargon) · 未来如需统一 · 抽 `assets/shared-theme.js`

### FEATURE C · 组合批量分析 `--portfolio CSV`

- **位置**：`lib/portfolio_runner.py` (新文件 370 行) · `run.py` argparse + 早返回段
- **核心函数**：
  - `_parse_csv(path)` → list[{ticker, weight, note}] · 容错 header / 中英文 / 0-100
  - `_normalize_weights(holdings)` → 归一化到 sum=1.0 · 缺失均分 / 部分缺剩余均分 / 总和 > 1 重归一
  - `_portfolio_health(metrics)` → {weighted_score, max_weight, n_industries, verdict}
  - `_render_html` → 排名表 + KPI grid + metadata.json
  - `run_portfolio(csv, depth, auto_open, portfolio_name)` → dispatch
- **CSV 容错**：
  - header 兼容：ticker / code / symbol / 股票 / 代码 · weight / 权重 / 仓位 / pct / 比例
  - weight 0-1 视为比例 · >1 自动除以 100
  - 无 header 时假设单列 ticker · weight 平均
- **未来改该区域注意事项**：
  - CSV header 加新别名时 · 必须加到 `tk_keys / wt_keys / note_keys` 列表
  - 健康度门槛是 hardcode（weighted_score>=70, max_weight<0.40, n_industries>=3）· 改阈值要同时改测试
  - metadata.json schema 是 SaaS 契约 · 加字段 OK · 改既有字段必须升 schema 版本
  - 失败容忍：单只 fail 进 `failed[]` 不阻断 · 但全失败返 insufficient_data

### Phase D 暂缓说明（v3.7 范围）

`--sector LED` 板块全扫 + `--as-of 2024-Q3` 历史复盘 都需要：
- fetcher 接受 `as_of_date` 参数 · 走历史接口（baostock query_history_k_data_plus 已支持但 akshare 大多不支持）
- 板块扫需 industry → tickers 映射表 · 跨数据源对齐

工作量大 + 涉及数据层重构 · 留到 v3.7 单独迭代。

---

## v3.5.0 (2026-05-29 · 单一流派视角锁定 `--school` + SaaS 集成 `--output-dir`)

### FEATURE · `--school A/B/C/D/E/F/G` 单一流派视角锁定（社群反馈）

- **背景**：用户反馈 "我只想看 F 派游资视角 · 不想 51 评委一起 vote"。51 评委 vote 出来的共识在某些场景下不是用户想要的视角（如纯游资打板 / 纯价值长线）
- **位置**：
  - `lib/investor_evaluator.py::evaluate` 入口段
  - `lib/pipeline/score_fns.py::synthesize` return 段
  - `lib/report/institutional.py::_render_school_lock_banner` 新函数
  - `run.py::main` argparse 段
  - `SKILL.md` HARD-GATE-SCHOOL-LOCK
- **改动**：
  1. `run.py` argparse 新增 `--school` choices=[A,B,C,D,E,F,G] · 触发后 set `os.environ["UZI_SCHOOL"]`
  2. `investor_evaluator.get_locked_school()` 读 env + 大小写归一 + 合法性校验
  3. `evaluate()` 顶部检查 · `inv_group != locked` → `_skip_result("用户锁定 X 派视角")` 不进规则引擎/persona
  4. `score_fns.synthesize` 把 `school_lock={group, label}` 编码进 synthesis · 让报告层无需读 env
  5. `_render_school_lock_banner(syn)` · 7 派各自配色 + 代表评委提示 · 渲染在 data_gap_banner 上方
  6. `SKILL.md` 加 HARD-GATE · agent role-play 时只 role-play 该派 5-8 人 · `panel_insights` 不写跨派对比 · `great_divide_override.bull_say_rounds/bear_say_rounds` 限于该派内
- **兼容 v3.4.5**：锁定 F 派 + 京东方 (2000 亿) · F 派 23 人按 LHB 反查机制 · 实际上榜的赵老哥/孙哥仍参与评分（不会因射程超限而二次 skip）
- **未传 `--school` 时行为 100% 兼容**：`get_locked_school()` 返 "" · 全 51 评委正常 vote · banner 不渲染（_render_school_lock_banner 返 ""）
- **验证**：
  - `UZI_SCHOOL=F python3 -c "from lib.investor_evaluator import evaluate; print(evaluate('buffett', {...}))"` → signal=skip · reason 含"锁定 A 股游资 派视角"
  - `_render_school_lock_banner({"school_lock":{"group":"F","label":"A 股游资"}})` → 包含 "SCHOOL LOCK" + "赵老哥" + 深红配色
  - 11 个回归测试 (`test_v3_5_0_school_lock.py`) 全过
- **未来改该区域注意事项**：
  - `UZI_SCHOOL` env 大小写归一在 `get_locked_school()` 内完成 · 不要在其他位置再做 upper() 否则双重转换会失效
  - 非 A-G 的 group 字符串（实验派 / 未分类）也会被 skip · 不要假设所有评委都有 group · 必要时检查 `_INVESTOR_GROUP_MAP.get(id, "")`
  - `_render_school_lock_banner` 的 THEMES dict 必须包含所有 7 派 · 加新派时记得同步 SCHOOL_LABELS + THEMES + 测试
  - synthesis.school_lock 是 dict 或 None · 不要写 ""（空字符串）· 测试 `if syn.get("school_lock")` 会过 None 但不会过 dict（即使 group=""）
  - agent role-play 时 · 即使 panel.json 里非该派评委有 skip 状态 · 也不要 override 他们的 signal · 用户预期就是只看该派

### FEATURE · `--output-dir` CLI flag · 供 uzi-platform 集成
- **背景**：把 UZI-Skill 包装成 SaaS（`uzi-platform/`），后端 Celery worker 需要稳定产物路径挂载到 web 报告页
- **位置**：`run.py::main` argparse 段 + 报告找到后的拷贝段（≈ line 530）
- **改动**：
  1. argparse 新增 `--output-dir DIR`
  2. 报告路径确定后，把整目录（含 avatars / share-card.png / war-report.png / one-liner.txt）拷到该目录
  3. `full-report-standalone.html` 额外复制一份为 `index.html`，便于平台直接服务
  4. 生成 `report.meta.json`（schema=1 · ticker / depth / generated_at / one_liner / size_kb），供后端落 DB
  5. 拷贝失败不影响本地报告生成（silent fallback + warning）
- **不破坏现有行为**：未传 `--output-dir` 时与改动前完全一致；--remote / --no-browser / browser open 路径全部保留
- **验证**：
  - 不传 `--output-dir`：本地 `reports/{ticker}_{date}/` 仍正常生成（既有测试覆盖）
  - 传 `--output-dir /tmp/x`：`/tmp/x/index.html` + `/tmp/x/report.meta.json` 存在且 size > 0
- **未来改该区域注意事项**：
  - `report.meta.json` 的 schema 字段是 SaaS 后端契约 · 加字段 OK · **改/删既有字段必须升 schema 版本号**
  - 拷贝用 `shutil.copytree` 已存在目录会先删 · 不要把用户的 `--output-dir` 设为非空业务目录
  - `index.html` 永远是 `full-report-standalone.html` 的副本（self-contained · 不依赖 avatars/） · 不要改为 `full-report.html`（会拉 share-card.png CDN）

---

## v3.4.5 (2026-05-12 · F 派 LHB 反查 + low-confidence banner)

### BUG 1 · F 派游资遇大盘股 100% skip · 与 LHB 实际数据脱节
- **症状**：用户跑京东方 000725（约 2000 亿市值）· 51 评委里 F 派 23 人全 skip · 但 LHB 实际显示 3-5 个游资参与涨停博弈
- **位置**：`lib/investor_evaluator.py::_is_youzi_out_of_range`
- **根因**：v2.13.3 加的市值射程检查没考虑 LHB 实际数据 · 只看 SEATS[nickname] 的 fit_rules max_mcap · 超出就硬 skip
- **修法**：检测 `features["matched_youzi"]`（fetch_lhb.match_seats_in_lhb 反查的 30 天上榜游资昵称 list）· 若该游资在里面 · 即使市值超射程也不 skip
- **回归测试**：4 个测试覆盖 (无 LHB skip / 有 LHB active / 射程内 / 非 F 派)
- **未来注意**：
  - `matched_youzi` 是 list[str]（nickname）· 不是 list[dict]
  - 仅对 F 派（_INVESTOR_GROUP_MAP）生效 · A/B/C/D/E/G 派不受影响
  - 加新游资到 SEATS 时 · 用 list 兼容（不是 set）· 否则 nickname in matched 会失败

### BUG 2 · fund_score 偏低但缺数据时无警告 · 用户误判可信度
- **症状**：京东方实测 fund_score=37.6 · 但 agent 重评 65/100 · 报告无任何"评分不可信"提示 · 用户读到 0/24 票数会误以为应清仓
- **位置**：`lib/report/institutional.py::_render_data_gap_banner`
- **根因**：score_dimensions 对缺数据维度给默认中性 5-6 分 · 多维缺失时会人为拉低 fund_score · 但 banner 没区分"评分可信"vs"评分受缺数据干扰"
- **修法**：`_render_data_gap_banner(data_gaps, raw, syn)` 新增 syn 参数 · 检测 stock + fund_score<50 + cov<60% → 渲染 low-confidence 红色 banner · 引导用户看 agent 重评
- **未来注意**：
  - 阈值 fund_score<50 + cov<60% 是经验值 · 京东方/类似缺数据股的实测 · 调整需更新测试
  - low-confidence banner 只对 stock 触发 · ETF/LOF 走 fund-type banner（v3.4.4）
  - 不传 syn 时向后兼容 · 走老 banner
  - 用红色调 #7f1d1d/#b91c1c · 区别于橙色（普通缺数据警告）+ 蓝色（基金类型）

---

## v3.4.4 (2026-05-12 · data_gap_banner UX 优化)

### UX BUG 1 · ETF 17% 覆盖率让用户误判可信度
- **症状**：用户反馈"ETF 报告数据覆盖率 17% · 会不会影响可信度"
- **位置**：`lib/report/institutional.py::_render_data_gap_banner`
- **根因**：原 banner 不区分 stock vs ETF/基金 · 对基金来说"缺 ROE/PE"是字段本身没有 · 不是采集失败 · 但 banner 用同样的"⚠️ DATA QUALITY 警告"措辞让用户误以为不可信
- **修法**：
  1. `_render_data_gap_banner(data_gaps, raw=None)` 新增 raw 参数
  2. 检测 `basic.security_type` 或 `raw.security_type` · 或 ticker 反推 (调 `classify_security_type`)
  3. ETF/LOF/mutual_fund → 渲染 `data-gap-banner fund-type` 蓝色调 banner · 文案"FUND-TYPE NOTE · 字段差异属预期·不影响可信度·去看前 10 大持仓股"
  4. 普通 stock 走老 banner · 向后兼容
- **未来注意**：
  - 新增 sec_type 时 · 更新 `is_fund_like` 检测逻辑
  - raw 传入是可选参数 · 不传时走老 banner（不要 break 现有 caller）
  - ticker 反推依赖 `lib.market_router.classify_security_type` · 改前缀规则要回归测试

### UX BUG 2 · banner 橙底橙字对比度不足
- **症状**：banner subtitle `<strong>` 用 `#f59e0b` 浅橙 · 在 12% 橙色背景上几乎看不清；chip 用 `#fbbf24` 亮橙更糟
- **位置**：`assets/report-template.html` `.data-gap-banner` 系列 CSS
- **修法**：
  - title `#f59e0b` → `#92400e` 深棕
  - subtitle strong `#f59e0b` → `#7c2d12` 深棕红 + font-weight 800
  - chip text `#fbbf24` → `#7c2d12` + font-weight 600
  - subtitle 正文 `var(--text-bright)` → `#1f2937` 深灰（避免主题色干扰）
  - 左边条 `#f59e0b` → `#b45309` 深棕色（更醒目）
  - 新加 `.data-gap-banner.fund-type` 蓝色调 CSS (#0369a1 + #0c4a6e)
- **回归测试**：`tests/test_v3_4_4_banner_ux.py` 11 个测试 · 含 CSS 颜色字符串断言（守护回归）
- **未来注意**：
  - 任何 banner 文字颜色都必须在浅橙背景上 WCAG AA 通过 · 不要用 `#fXXXXX` 系列浅橙做文字
  - 信息性提示用蓝色调 · 警告/错误才用橙红色 · 维持视觉语义一致

---

## v3.4.3 (2026-05-12 · 开放式基金分类修复 + 字段级 fallback gate)

### BUG #60-followup · 开放式基金被误判为 convertible_bond
- **症状**：用户输 110011（易方达优质混合）→ classify_security_type 返 `convertible_bond` → early-exit · v3.4.0 加的 fund_holdings_runner 无机会触发
- **位置**：`lib/market_router.py::classify_security_type`
- **根因**：仅按前缀规则分类 · 110xxx 既是 SH 老转债前缀 也是开放式基金代码 · 同样 005xxx 不是股票前缀但是基金
- **修法**：
  1. 新增 `SecurityType` literal `mutual_fund`
  2. 在判 `convertible_bond` 之前 · 用 `akshare.fund_name_em()` 二次校验（懒加载 + 全表 set 缓存）· 基金代码优先识别为 mutual_fund
  3. 对不在 stock 前缀的码段（如 005xxx）· 也查一下基金清单
  4. run.py + preflight_helpers 把 mutual_fund 路由到 fund_holdings_runner
- **验证**：110011 → mutual_fund ✅ · 113008 真转债 → cb ✅（不误伤）
- **回归测试**：`tests/test_v3_4_3_mutual_fund_classification.py` (6 tests)
- **未来改该区域注意事项**：
  - `_is_mutual_fund_code` 是懒加载 module-level 缓存 · 单进程内只下载一次 · 不要在 hot path 调
  - `fund_name_em` 失败时 silent fallback 到老前缀规则 · 不抛异常（保证向后兼容）
  - 新增 sec_type 时 · run.py 两处分支 + preflight + fetch_basic 四处都要加路由
  - `akshare.fund_portfolio_hold_em` 对 ETF/LOF/mutual_fund 都 work · 不需为 mutual_fund 单独写持仓拉取

### REFACTOR (PR #63) · A 股 basic 字段级 fallback gate
- **症状**：xueqiu 拿到 price/PE/PB 但 name 空 → early return 跳过后续 fallback · 报告 name 永远显示为空
- **位置**：`lib/data_sources.py` · 新增 `_ensure_a_share_basic_fields` gate
- **根因**：之前 fallback 是 source-level（一个源 ok 就 early return）· 没做字段级 patch
- **修法**：新增 `_merge_missing_basic_fields` · 仅填空不覆盖 · 4 个早 return 点全部走 `_ensure_a_share_basic_fields` 字段级 gate · 备用源链 tencent_qt → baostock → ak_code_name → known_industry
- **验证**：茅台 600519 拿到 name=贵州茅台 / price / pe_ttm / pb / industry=白酒Ⅱ / listed_date 全字段
- **未来改该区域注意事项**：
  - `_merge_missing_basic_fields` 默认只填指定字段集 · 加新字段需更新 `fields` 元组
  - `_fallback_snap` 标记会去重 · 别在 hot loop 里反复 append 同 marker
  - `_ensure_a_share_basic_fields` 调用应在所有主 fallback 之后 · 否则被覆盖

---

## v3.4.2 (2026-05-11 · Windows + Clash Schannel TLS 兼容 · baostock 双 fallback)

### BUG · Windows Python + Schannel TLS 与东财不兼容 · PE/PB/ROE 全空
- **症状**：Windows + Clash 用户跑分析 · 所有 eastmoney 链路（xueqiu / push2 / baidu / tencent_qt）全挂 · 报告里 PE/PB/ROE 全 `—`
- **位置**：`lib/data_sources.fetch_basic` 链 + `fetch_financials.py::_fetch_a_share`
- **根因**：Windows Python 默认用 Schannel（系统 TLS）· 东财接口与 Schannel 兼容性差. Clash 国内规则 DIRECT → 仍走 Schannel · 代理救不了
- **不能修的事**：Schannel 本身没法修（需要换 Python TLS backend 或改 Clash 规则让 eastmoney 走代理）
- **能修的事**：增加 baostock fallback · 它走自有协议（非 HTTPS）· 完全绕过 SSL 兼容性
- **修法**（2 处 fallback）：
  1. `fetch_basic` · 在 tencent_qt 之后追加 baostock · `query_history_k_data_plus` 拿 peTTM/pbMRQ/close · `query_stock_basic` 拿 code_name/ipoDate
  2. `fetch_financials._fetch_a_share` · 当 ROE/revenue_history/net_margin 都空时触发 baostock · 拉 5 年季报 + 解析 roeAvg/MBRevenue/npMargin/gpMargin
- **验证**：baostock 茅台 sh.600519 实测拿到 peTTM=20.4 / pbMRQ=7.15 / ROE=19.25% / 净利率 52.6% / 营收 893.5 亿
- **回归测试**：`tests/test_v3_4_2_baostock_fallback.py` (6 tests · 含真机烟雾测试)
- **未来改该区域注意事项**：
  - **不要在 baostock fallback 段直接覆盖正常数据**：fetch_financials 检查 `needs_fallback = not roe and not revenue_history and not net_margin` · 仅当核心字段全空才触发 · 否则会让正常拿到数据的票被 baostock 覆盖（baostock 季报较慢 · 可能不是最新）
  - baostock `query_profit_data` 返回 ROE/Margin 都是**小数**（0.19 = 19%）· 渲染前必须 ×100
  - 不要把 baostock 当主源 · 它季度数据更新比 akshare 慢 1-3 天 · 仅当主源失败时启用
  - baostock 服务端要求 ≥0.9.1（v3.4.0 已锁版本）

---

## v3.4.1 (2026-05-11 · verdict 粒度细化 · 相近股票可区分)

### BUG · 50-65 verdict 段过宽 · 神剑(58) + 博云(59.9) 都判 "观望优先" 看不出差异
- **症状**：用户反馈"神剑股份、博云新材 这两支其实买入逻辑也不一样，但评分一致"
- **位置**：`lib/pipeline/score_fns.py::generate_synthesis` line 980+ verdict ladder
- **根因**：v2.11 verdict 5 档 (80/65/50/35) · 50-65 "观望优先" 跨度 15 分 · 神剑 58 + 博云 59.9 都在里面 · 用户感知一致
- **真实差异**：流派分上有差距（成长派 +13 · 中式价投 +15）· overall 也差 1.9 · 但被 verdict 段掩盖
- **修法**（3 层细化 · 不动核心 fund_score 公式以避免破坏白马评分）：
  1. verdict 7 档：80/70/65/60/55/50/35 (50-65 拆三档 · 65-70 加偏弱)
  2. verdict label 追加 "X 派看多 / Y 派看空"
  3. synthesis 加 verdict_detail = "基本面 X · 共识 Y" · assemble_report 渲染时追加显示
- **回归测试**：`tests/test_v3_4_1_verdict_granularity.py` (5 tests) + 更新 `test_v2_11_scoring_calibration` 阈值
- **未来改该区域注意事项**：
  - 不要直接改 score_dimensions 来放大差异 · 它是 v2.11 校准过的 · 改会破坏白马评分
  - 真正的根因是 score_dimensions 给缺数据维度默认 5-7 (中性) · 抹平了 ROE/营收差异 · 未来 v3.5+ 可考虑 "active-weighted"
  - verdict 阈值增加时 · 同步更新 `test_v2_11_scoring_calibration::_verdict_for` ladder

---

## v3.4.0 (2026-05-10 · 基金/ETF 持仓循环分析 + baostock ≥0.9.1)

### FEATURE · ETF/LOF 持仓循环分析（v2.10.4 early-exit 改为 opt-in 批量）
- **背景**：v2.9.2 引入 ETF/LOF 早退（避免对非个股标的跑 51 评委）· 但用户期望"分析整只 ETF" · 之前手动跑 10 次 stock-analyze 太麻烦
- **位置**：`lib/fund_holdings_runner.py`（新）+ `run.py`（两处分支接入 runner）
- **用户体验**：检测到 ETF/LOF → 列持仓 + 估算耗时 → 二次确认（y / 数字 / N） → 循环跑 stock-analyze + 生成 summary HTML
- **安全设计**：
  - 默认取消（除非用户输入 y）
  - 数字输入只跑前 K 只
  - 单只崩不中断（partial failure 容忍）
  - 非交互环境必须 `UZI_FUND_AUTO_YES=1` 显式确认
  - 可转债 / 指数仍 early-exit · 只对 ETF/LOF 启用
- **回归测试**：`tests/test_v3_4_0_fund_holdings.py` (7 tests · runtime 估算 / 取消 / auto_yes / partial failure / summary HTML 链接)
- **未来改该区域注意事项**：
  - **不要把 ETF/LOF pipeline 强行塞进主 22 维 stock pipeline** · 它们没有 ROE/护城河字段 · 这次设计意在循环复用 stock pipeline 而不是新建 fund pipeline
  - 默认取消逻辑必须保留 · 否则 agent 误传 ETF 会循环 10 次浪费 token
  - `UZI_FUND_AUTO_YES=1` 应用于 CI / agent 编排场景 · 不要默认开启
  - top_holdings 必须有 rank/code/name 三个字段 · weight_pct 可选

### CONFIG · baostock 锁版本 ≥0.9.1
- **背景**：社群通知 2026-04-22 起 baostock 服务端要求 ≥0.9.1
- **位置**：`requirements.txt`
- **修法**：`baostock>=0.8.9` → `baostock>=0.9.1`
- **验证**：本地 0.9.1 实测 login + 茅台 K 线 query 全过
- **未来改该区域注意事项**：baostock 服务端版本要求未来可能继续上调 · 看到 login() 大面积失败时优先升 baostock

---

## v3.3.4 (2026-05-10 · mini_racer V8 crash escape hatch · issue #61)

### BUG #61 · macOS Py 3.12/3.13 下 mini_racer V8 SIGTRAP（@dragonforai）
- **症状**：`python run.py SEHK.03690 --depth deep` → `[FATAL:address_pool_manager.cc(67)] Check failed: !pool->IsInitialized()` · Python 进程被 SIGTRAP 杀掉
- **位置**：`run_real_test.run_fetcher` (legacy 路径) + `lib/pipeline/collect.py::_run` (pipeline 路径)
- **根因**：
  - `mini_racer` 是 V8 isolate 的 ctypes 封装 · 非进程内 thread-safe
  - v2.6 加 `_MINI_RACER_LOCK` 串行化 · 但 macOS Python 3.12+ 下 libffi cross-thread ctypes call 时序仍可能让 V8 isolate pool 被多次初始化
  - SIGTRAP 是进程级 signal · Python `try/except` 抓不到 · 整个 process 被 kill
- **影响**：HK 港股 + deep 模式特别容易触发（因为 deep 启用更多 fetcher · 增加 mini_racer 调用频次）· 用户无法生成报告
- **修法**（多重 layer）：
  1. **显式 escape hatch**：`UZI_DISABLE_MINI_RACER=1` env var · 跳过 3 个 fetcher graceful 降级
  2. **自动恢复**（核心创新）：sentinel 文件机制
     - 调 mini_racer fetcher 前写 `~/.uzi-skill/_minirackercrash.sentinel`
     - 成功后删
     - 进程崩则 sentinel 留下 · 下次启动自动 disable
  3. **强制启用**：`UZI_FORCE_MINI_RACER=1` 覆盖 sentinel（debug 用）
  4. legacy + pipeline 两条路径都做了同样保护
- **验证**：UZI_DISABLE_MINI_RACER=1 e2e 跑通 · 614 KB HTML 仍生成
- **回归测试**：`tests/test_v3_3_4_minirackerguard.py` (7 tests)
- **未来改该区域注意事项**：
  - 不要试图用 Python `try/except` 抓 V8 SIGTRAP · 抓不到（进程级 signal）
  - sentinel 文件路径在 `~/.uzi-skill/_minirackercrash.sentinel` · 不要改路径
  - 调 mini_racer fetcher 时 **必须先 arm sentinel** · 成功后 disarm · 否则 auto-recovery 失效
  - 普通 Python 异常时也要 disarm sentinel · 否则误判 V8 crash 让用户每次都跑 fallback
  - **加新的 mini_racer 触发函数时**（akshare 升级可能引入更多 V8 调用）· 务必加进 `_MINI_RACER_FETCHERS` 集合
  - 长期方案：考虑用 subprocess 隔离 mini_racer call · 或换 cninfo HTTP API 不依赖 mini_racer

---

## v3.3.3 (2026-05-06 · 社区 PR · 4 项 hotfix)

### BUG #52 · LHB akshare 1.18+ "近一月" 字符串失效（@qdby26）
- **症状**：所有股票 `lhb_count_30d=0` / `matched_youzi=[]` / `inst_vs_youzi` 全 0 · 龙虎榜模块永远空
- **位置**：`lib/data_sources.py::_fetch_lhb_impl`
- **根因**：akshare 1.18+ 改了 API · `stock_lhb_stock_detail_em(symbol, date="近一月")` 返 `None` → `TypeError` → `except: return []` 静默吞掉
- **修法**：用 `stock_lhb_stock_detail_date_em` 拿历史日期 + 按 days 过滤 + 逐日调 YYYYMMDD 格式 + 列名归一化 `交易营业部名称 → 营业部名称`
- **验证**：6 mock 回归测试全过
- **未来改该区域注意事项**：
  - akshare 任何字符串简写参数（"近 X 月" / "今年" / "全部"）都不可信 · 优先用 YYYYMMDD/YYYY-MM-DD 数值格式
  - `except Exception: return []` 这种静默吞异常的写法是 anti-pattern · 必须至少 print warning

### BUG #54 · institutional.py 缺 svg_radar import（@DragonQuix）
- **症状**：报告里 BCG/Porter 5 forces 块缺失（_render_competitive_analysis 静默返空）
- **位置**：`lib/report/institutional.py:393`
- **根因**：v3.2 拆分时只 import 了 `svg_gauge / svg_progress_row` · 漏了 `svg_radar`（v3.3.2 已修过 svg_sparkline · 但忘了 svg_radar）
- **修法**：import 块加 `svg_radar`
- **验证**：`test_institutional_imports_svg_radar` + `test_render_competitive_analysis_does_not_raise_nameerror`
- **未来改该区域注意事项**：
  - **任何 lib/report/* 子模块用的 svg_* 函数必须 import** · v3.2 拆分时漏了 svg_sparkline (修过 #50) 又漏了 svg_radar · 已加回归测试守护 · 若再加 svg_xxx 也要更新 import
  - 推荐：CI 加 `python -c "from lib.report.institutional import *; ar.assemble('TEST.SH')"` 烟雾测试

### BUG #59 · Python 3.11 嵌套 f-string 反斜杠 SyntaxError（@Charlson852）
- **症状**：Python 3.11 import `lib.report.special_cards` 直接 `SyntaxError: f-string expression part cannot include a backslash`
- **位置**：`lib/report/special_cards.py::render_school_scores` · 第 500 行
- **根因**：Python 3.11 不允许 f-string 表达式部分有反斜杠 · `f"{f'...\\\"...\\\"...' if skip else ''}"` 这种嵌套 f-string + 反斜杠 attr 引号会触发 SyntaxError（Python 3.12+ 才允许）
- **影响**：所有 Python 3.11 用户（Debian 13 默认）完全无法 import · stage2 全崩
- **修法**：把内嵌 f-string 提取为独立变量 `skip_display` · 主 f-string 只插入变量 (无反斜杠)
- **PR #59 原版 bug 警告**：作者修这个的同时把 `items.append(...)` 从 for-loop **内**（8 缩进）错移到 for-loop **外**（4 缩进）· 会导致 7 流派只渲染最后一个 · 我们 cherry-pick 仅修复部分 · 保持原缩进
- **验证**：`test_school_scores_uses_skip_display_variable` + `test_render_school_scores_renders_all_seven_groups`
- **未来改该区域注意事项**：
  - **永远不要在 f-string 表达式部分用反斜杠**（即使 Python 3.12+ 允许 · 也会让 3.11 崩）· 把 HTML 等需要引号的部分提取为独立变量
  - 重写 render_school_scores 时 · `items.append` **必须**在 for-loop 内 · 否则只渲染最后一个流派 · `test_render_school_scores_renders_all_seven_groups` 守护这条
  - 缩进改动看似无害但语义巨变 · review PR 时关注控制流缩进

---

## v3.3.2 (2026-04-28 · GitHub issue #50 + #51 hotfix)

### BUG #50 · institutional.py 漏 import svg_sparkline · NameError 卡死 stage2
- **症状**：用户报"Stage 2 总是超时"· 实际是 `NameError: name 'svg_sparkline' is not defined`
- **位置**：`lib/report/institutional.py:211-212` · `_render_lbo_block` 函数内
- **根因**：v3.2 拆分时 institutional.py 的 import 块只列 `svg_gauge / svg_progress_row` · 漏了 svg_sparkline · 但 _render_lbo_block 实际调用了它
- **触发条件**：dim20.lbo.ebitda_path 或 debt_schedule 非空时（绝大多数股票都会触发）
- **影响**：stage2 整个崩 · HTML 不出 · 用户感知"卡住超时"
- **修法**：import 块加 `svg_sparkline`
- **验证**：手动构造 dim20 跑 _render_lbo_block · 应生成 2 个 SVG sparkline
- **回归测试**：`tests/test_v3_3_2_issue_fixes.py::test_institutional_imports_svg_sparkline` + `test_render_lbo_block_does_not_raise_nameerror`
- **未来改该区域注意事项**：
  - 任何在 lib/report/* 子模块用的 SVG 函数必须在文件顶部 import block 显式列出
  - v3.2 拆分时容易漏 import · 抽块前先 grep 该块用了哪些函数 · 全部加进 import 列表
  - 推荐：每个新 lib/report/*.py 文件都在 CI 跑 `python -c "import lib.report.X"` 烟雾测试

### BUG #51 · XueQiu cubes_search.json endpoint 已下线
- **症状**：用户报"XueQiu 登录成功但验证失败" · cookie 已保存但 endpoint 仍 400
- **位置**：`lib/xueqiu_browser.py:32` (LOGIN_TEST_URL) · `lib/xueqiu_browser.py::fetch_cubes_via_browser` · `fetch_contests.py::fetch_xueqiu_cubes`
- **根因**：XueQiu 把 `/cubes/cubes_search.json` endpoint 完全下线 · 未保留兼容
- **社区修法**：@Kylin824 提供新 URL `/query/v1/search/cube/stock.json?q={xq_symbol}&count={limit}&page=1`
- **修法**：3 处同步换新 endpoint
- **验证**：grep 项目无 `cubes/cubes_search.json` API 调用残留
- **回归测试**：`test_xueqiu_login_url_uses_new_endpoint` + `test_xueqiu_browser_fetch_uses_new_endpoint` + `test_fetch_contests_uses_new_endpoint`
- **未来改该区域注意事项**：
  - XueQiu API 不稳定 · 历史上多次改 endpoint · 任何报登录验证失败时优先怀疑 endpoint 失效
  - 改 LOGIN_TEST_URL 必须同步 fetch_cubes_via_browser 和 fetch_contests · 三处保持一致
  - `query/v1/search/cube/stock.json` 参数是 `q=` 不是 `code=` · category 参数也已废弃

---

## v3.2.0 (2026-04-23 · assemble_report.py 拆分 80%)

### REFACTOR · assemble_report.py 从 2964 → 587 行
- **症状**：v2.15.x 多个 hotfix（fund / moat / school_scores）都落在 assemble_report.py · 68 函数单文件耦合严重
- **位置**：`assemble_report.py` · 新增 `lib/report/` 5 个子模块
- **根因**：所有 render 相关代码堆一个文件 · 改 fund_managers 的人可能不小心碰到 dim_viz 的 SVG · 2964 行导致定位困难
- **修法**（4 次 commit 物理拆分）：
  1. `svg_primitives.py` (602 行) · 19 个 svg_* + 9 个 COLOR_* · 纯渲染无业务
  2. `dim_viz.py` (742 行) · 19 个 _viz_xxx + DIM_VIZ_RENDERERS dispatch
  3. `institutional.py` (532 行) · DCF/LBO/IC/catalyst/competitive/style_chip
  4. `panel_cards.py` (183) + `special_cards.py` (544 行) · 51 评委相关 + 特殊卡
- **验证**：332 tests 全过 · 002217 assemble() 0.0s 出 608KB HTML · 格式 byte-level 一致
- **回归测试**：4 处 grep 式 test 扩展为拼接 assemble_report + 对应子模块源码
- **未来改该区域注意事项**：
  - 新增 render 函数要选对目标文件：`svg_xxx` → svg_primitives · `_viz_xxx` → dim_viz · `render_dim_card` 核心 → assemble_report · panel 相关 → panel_cards · 深度卡片 → special_cards · 机构建模 → institutional
  - assemble_report.py 对所有抽离函数做 re-export · 改 API 时保持 re-export 完整否则外部调用崩
  - 循环依赖：每个子模块都重新定义 `_safe` 避免 import assemble_report（防止循环）
  - grep 式测试脆弱 · 再拆模块时记得扩展 src 拼接列表
  - `DIM_META` / `CAT_GROUPS` 仍在 assemble_report · 因为 render_dim_card 依赖它们

---

## v3.1.0 (2026-04-23 · rrt 瘦身 65% · 纯函数 + preflight 抽离)

### REFACTOR · run_real_test.py 从 2105 → 735 行
- **症状**：v2.x 连续 5 个 hotfix 都落在 rrt 屎山里 · 函数互相耦合 · 改动困难
- **位置**：`run_real_test.py` · `lib/pipeline/score_fns.py`（新）· `lib/pipeline/preflight_helpers.py`（新）
- **根因**：rrt 同时承担 collect + scoring 纯函数 + stage1/stage2 CLI 编排 · 职责混杂 · 2105 行单文件
- **影响**：改任何一处需要扫全文件找依赖 · 测试 grep 式脆弱 · v3.0 发完仍有这个债
- **修法**（2 步物理搬迁）：
  1. 搬 1228 行纯函数到 `score_fns.py` · rrt 做 re-export 保持兼容
  2. 搬 166 行 preflight/resolve/ETF 到 `preflight_helpers.py` · stage1 改调 `prepare_target()`
- **验证**：332 tests 全过 · 002217 resume e2e 10s 出报告 · 格式 100% 兼容
- **回归测试**：18 处 grep 式测试批量 patch 读 rrt + score_fns + preflight_helpers 三文件拼接
- **未来改该区域注意事项**：
  - 纯函数的 canonical 位置现在是 `score_fns.py` · rrt 只做 re-export · 新函数添加走 score_fns
  - preflight 任何新增检查都加到 `prepare_target()` · 不要回到 stage1 里堆逻辑
  - `collect_raw_data` 仍在 rrt（283 行）· legacy stage1 还用它 · 新 collector 是 `pipeline/collect.py`
  - 如果 stage1 签名变化（加/减参数）· 需同步 `preflight_helpers.prepare_target` 参数
  - grep 式测试（`(X / "run_real_test.py").read_text()`）脆弱 · 如果再搬函数记得扩展测试的文件列表

---

## v3.0.0 (2026-04-23 · pipeline 架构默认启用 + Phase 6c 解耦)

### REFACTOR · pipeline 成为主干 · legacy 转作 fallback
- **症状**：v2.x 连续 5 个 hotfix 都落在 assemble_report.py (2964 行) + run_real_test.py (2105 行) 两个巨文件 · 屎山深重
- **位置**：`run.py::main`（默认路径切换）+ `lib/pipeline/score.py`（Phase 6c 解耦）+ `lib/pipeline/run.py`（pipeline 编排）
- **根因**：v2.15.x 的 Phase 6a delegate 模式下 `pipeline.score_from_cache` 直接调 `rrt.stage1(ticker)` · 但 stage1 内部会重新跑 22 fetcher collect · 和 pipeline 刚做完的 collect 重复 · 每股多耗 5-10 分钟
- **影响**：pipeline dark-launch 两周下来 opt-in 用户反馈"比 legacy 慢" · 原因是重复 collect
- **修法**（3 步）：
  1. `pipeline/score.py::score_from_cache` 改为调 rrt 纯函数（`score_dimensions` / `generate_panel` / `generate_synthesis` / `_autofill_qualitative_via_mx`）· 不再调 `stage1`
  2. `pipeline/run.py::run_pipeline` 加 `_preflight_guards(ticker)` · 中文名 / ETF / LOF / 可转债 → 抛 `ValueError` 让 run.py fallback legacy（legacy 有完整交互）
  3. `run.py::main` 默认走 pipeline · `UZI_LEGACY=1` 强制走老路径 · pipeline 异常自动 fallback · 附 traceback
- **验证**：002217 resume 模式 `run_pipeline` 46.9s 出报告 · 以前约 120s+（score_from_cache 从 180s → 10.6s）
- **回归测试**：332 tests 全过（253 legacy + 79 pipeline）· 含 score/synthesize/collect/run_pipeline 的模块单测
- **未来改该区域注意事项**：
  - `pipeline.score_from_cache` 依赖 rrt 的 4 个函数签名 · 任何一个签名变 · pipeline 同步改（现状：`score_dimensions(raw)` / `generate_panel(dims_scored, raw)` / `generate_synthesis(raw, dims_scored, panel, agent_analysis=None)` / `_autofill_qualitative_via_mx(raw, ticker)`）
  - `pipeline/synthesize.py` 仍是 delegate · 调 `rrt.stage2(ticker)` · stage2 只读 cache 不 collect · 安全（改 stage2 时注意保持"只读 cache"原则）
  - `_preflight_guards` 里的异常类型必须是 `ValueError` · 其他异常 run.py 不会 fallback（视为 crash）
  - 如果 legacy 某个纯函数名变（如 `generate_panel` → `build_panel`）· pipeline/score.py 必须同步改 · 否则 AttributeError
  - `UZI_LEGACY=1` 是保险开关 · 绝不删 · 出问题时用户能临时回退

---

## v2.15.5 (2026-04-23 · 评分聚集在一个区间 · 区分度不足)

### BUG · consensus 公式把连续分压成三分类 + 规则严苛导致结构性居中
- **症状**：用户反馈"现在评分大多数都在一个区间内徘徊" · 采 7 股数据 consensus 聚集 40-55 · 流派间分歧 stdev 常 < 15
- **位置**：`run_real_test.py::generate_panel`（v2.11 原公式）+ `lib/investor_evaluator.py:69`（BULLISH_THRESHOLD=65 / BEARISH_THRESHOLD=35）
- **根因 1（最主要）**：v2.11 公式 `(bullish + 0.6*neutral)/active*100` 只看 signal 计数 · 单 investor score 虽然 stdev=30 信息丰富 · 但被压成 3 分类后"打 55 分"和"打 40 分"一样算 neutral 贡献 · 程度丢失
- **根因 2**：A 成长派规则严苛 · 平均 score 35 · D 技术派 51 · G 量化 58 · 跨流派结构性偏差 20 分
- **影响**：7 流派 consensus 分布挤在 30-55 区间 · 用户看不出"宏观派买入 vs 价值派回避"这种真正的分歧信号
- **修法**（3 步）：
  1. `generate_panel` 引入 `SCORE_WEIGHT=0.65 + VOTE_WEIGHT=0.35` 混合公式 · `raw = 0.65*score_mean + 0.35*vote_weighted`
  2. 加 `_polarize(c, k=1.3)` helper · `final = clip(50 + (raw-50)*1.3, 0, 100)` · 以 50 为中心把两端拉开
  3. 总盘 + `school_scores` 每个流派同步升级 · 新增 `score_mean` / `vote_consensus` 分量字段让用户看到"实分 vs 投票"的拆解
- **验证**：
  - 002217 F 游资 51→43.7（vote 机制高估修正·实分 42）· G 量化 50→59.3（实分 61 低估修正）
  - 总盘 range 从 62 → 68 分（两端更极端）
  - 7 股样本没有再聚集 40-55 区间
- **回归测试**：`tests/test_v2_15_4_school_scores.py`（9 tests · 含 `test_mixed_formula_polarizes_extremes` 校验数学 · `test_consensus_formula_in_panel_has_mixed_components` 守护常量）
- **未来改该区域注意事项**：
  - `SCORE_WEIGHT + VOTE_WEIGHT` 必须 == 1.0 · 否则 raw 会偏置
  - `POLARIZE_K` 调大（>1.5）会让 consensus 容易贴 0/100 · 不建议 · 想进一步拉开优先改 BULLISH_THRESHOLD
  - 若修改 `NEUTRAL_WEIGHT`（0.6→其他）· 必须同步 `stock_style.py::apply_style_weights` 里的 `neutral_w += w * 0.6`（v2.11 耦合）
  - `_polarize` 对 50 分不变 · 如果改变中心点需要同步更新 `_consensus_to_verdict` 阈值
  - 新增流派时 `school_scores` 聚合会自动处理 · 但 `GROUP_META` 要同步加 label + desc

---

## v2.15.4 (2026-04-22 · panel 只有总分看不到流派分歧)

### FEATURE · 按流派打分 (school_scores)
- **症状**：用户"打分系统我觉得可能还要优化一下，我们现在有几个流派，那么除了有一个最终分数，还要有不同流派各自给出的分数"· 51 位评委的分歧被聚合掉看不出来
- **位置**：`run_real_test.py::generate_panel`（~line 740）+ `assemble_report.py::render_school_scores` + `assets/report-template.html`
- **根因**：原设计只有一个 `panel_consensus` / `vote_distribution` / `signal_distribution` · 没有按 investor.group 分组聚合
- **影响**：结构性矛盾票（譬如宏观友好但成长性差）看总分只是中性 · 用户无法快速判断到底是"共识中性"还是"各派互相抵消"
- **修法**（3 改动）：
  1. `generate_panel` 末尾加 `by_group` 聚合 · 每个流派用和总盘一致的 `(bullish + 0.6*neutral)/active * 100` 公式生成 consensus · active 成员 score 均值生成 avg_score · `_consensus_to_verdict` 阈值 80/65/50/35 与综合分对齐
  2. `synthesis.json` 携带 `school_scores` · 报告层无须回拉 panel.json
  3. `render_school_scores` 渲染 7 卡片网格（配色按 verdict 语义）· 注入 `<!-- INJECT_SCHOOL_SCORES -->` 锚点
- **验证**：002217 · 宏观派 68 买入 vs 成长派 25 回避 · 分歧 43 分可见 · 总分 45.5 单看无法识别
- **回归测试**：`tests/test_v2_15_4_school_scores.py`（7 tests · 聚合数学 / 阈值一致 / 模板锚点 / render 函数 / 空数据兜底）
- **未来改该区域注意事项**：
  - 如果修改 `NEUTRAL_WEIGHT` 或 consensus 公式 · 必须同步改 `generate_panel` 下面的流派聚合段 · 两处必须保持公式一致
  - 如果新增/删除 investor · 需确认其 `group` 字段在 A-G 范围 · 否则 `school_scores` 会出现 `?` key
  - 如果改 verdict 阈值（如 65→70）· 必须同步 `_consensus_to_verdict` 和 overall 的 `verdict_label` 两处

---

## v2.15.3 (2026-04-21 · fetch_capital_flow 严重性能 bug)

### BUG · 每股重抓全 A 大宗/解禁/融资数据（3+ min/股）
- **症状**：用户"数据源不稳定"反馈 · 12_capital_flow 维度每股卡 3-5 min
- **位置**：`fetch_capital_flow.py::main()` · 4 个调用涉及全市场数据
- **根因**：`stock_dzjy_mrtj` / `stock_restricted_release_summary_em` / `stock_restricted_release_detail_em` / `stock_margin_detail_szse/sse` 都返回全市场整年数据（几千到几万行），原 main 每股分析都重下一遍后再 filter
- **修法**：
  - 新增 4 个 `_universe_*()` helper · 用 `cached("_universe", key, ttl=24h)` 做 module-level cache
  - `main()` 里从已 cache 的 universe 数据 filter 本股记录
  - cache key 用 `"_universe"` 作 ticker · 跨股共享
- **实测**：首次 382s（正常 · 建 cache）· 二次 cache 命中 universe 部分 0.01s
- **回归测试**：`tests/test_v2_15_3_capital_flow_cache.py` · 6 case
- **未来注意事项**：
  - 所有"全市场数据集 + 本股 filter" 模式都要走 universe cache · 不能 per-stock 重抓
  - 其他可能有同类问题的 fetcher：fetch_industry.py 的 cninfo 全行业数据 · 应审查
  - universe cache 统一放 `.cache/_universe/api_cache/` · 跟股票 cache 分开便于清理
  - TTL 24h · 如果是交易时间敏感的大宗/融资 · 可以缩短到 2h（但性能 vs 新鲜度要权衡）

---

## v2.15.2 (2026-04-21 · GitHub issue #36 + #30 hotfix)

### BUG · Gemini CLI 安装报错（#36）
- **症状**：`gemini extensions install ...` 失败 · 报 `missing "version"`
- **位置**：`gemini-extension.json`（仓库根目录）
- **根因**：Gemini CLI 硬校验 `version` 字段 · 我们没给
- **修法**：加 `"version": "2.15.2"` · 并把该文件纳入 `.version-bump.json::files` · 未来 bump 会自动同步
- **未来注意**：每次 bump version 时确认 `gemini-extension.json` 也被更新 · 否则 Gemini CLI 用户会装到过期版本

### FEATURE · 网络自检增强（#30）
- **需求**：Clash 用户偶尔代理配错 · 希望 plugin 能诊断 + 给具体修复建议
- **位置**：`lib/network_preflight.py`
- **实现**：
  1. `_detect_local_proxy()` · 扫常见代理端口（7890/7891/7897/10808/1080/8888）· 检到本地代理但 env 没 HTTPS_PROXY → 给 export 建议
  2. `diagnose_source(profile)` · 按 domestic/overseas/search 3 组独立诊断 · 每组列 affected_fetchers + multi-line fix
  3. `NetworkProfile` 新增 `local_proxy: dict` + `diagnostics: list` 字段
  4. `run_preflight` 写 cache 时把这两个新字段一起落盘 · agent 可读
  5. verbose 模式输出 · Clash hint + 每组 fix 多行
- **未来注意**：
  - 若加新代理工具（如 Quantumult X / Surge 一键），在 `_LOCAL_PROXY_PORTS` 里加新端口
  - `diagnose_source` 里的 `affected_fetchers` 列表要跟实际 fetcher 保持同步（加新 fetcher 时检查）
  - cache 文件 schema 变了 · 老 cache 读回要用 `NetworkProfile.from_dict` 的容错逻辑

---

## v2.15.1 (2026-04-20 · 报告质量 2 bug hotfix · 实测 300470 发现)

### BUG 1 · fund-card 渲染 0.0% 假数据
- **症状**：用户看到"每次都一大堆基金持有，看着就很不对劲" · 报告里 15-30 张 fund-card 中第 5/6 张起 5Y/年化/回撤/夏普全是 0.0%
- **位置**：
  - `fetch_fund_holders.py::_build_row_full` 
  - `assemble_report.py::render_fund_managers`
- **根因**：双层故障链
  1. fetch_fund_holders · compute_fund_stats 返 `{}` 时用 `stats.get("return_5y", 0)` 写 0（应该 None）· fund.eastmoney.com SSL 封或新基金 NAV 不足 50 条都会触发
  2. assemble_report · `INITIAL_SHOW = 6` 硬编码 · 所有 manager 都过 for 循环生成 fund-card · 即便 return_5y=None 也被 `m.get("return_5y") or 0` fallback 成 0
- **修法**：
  - fetch_fund_holders: stats 空时降级为 `_row_type="lite"` + 所有数值字段 None · 有 has_real_stats 判断
  - assemble_report: for 循环里 `is_lite` 跳过 full-card 生成 · `INITIAL_SHOW = min(6, len(cards))` 动态 · lite 去重（按 fund_code）+ cap 30 · 余量"另有 N 家"文案
- **回归测试**：`tests/test_v2_15_1_fund_lite_rendering.py` · 7 case
- **未来改该区域注意事项**：
  - 任何 fetcher 返"有字段但数值是 0"的场景都要考虑 render 端是否会误判为"实测数据"
  - 同理 8_materials / 3_macro / 7_industry 的数值字段如果网络失败默认返 0 会误导报告
  - `_build_row_full` 的 has_real_stats 判断必须保留 · 未来加新 stat 字段也要纳入判断
  - lite 去重是按 `fund_code` · 富国天惠 A/B/C/D 虽是同一产品不同份额，但在报告里应合并看
  - LITE_CAP=30 可调 · 太少看不到小仓机构 · 太多撑爆报告

### BUG 2 · 14_moat 污染成贵州茅台数据
- **症状**：中密控股 300470 报告 14_moat 四个字段（intangible/switching/network/scale/rd_summary）全部显示"贵州茅台表示，技术创新在公司发展历程中始终扮演关键角色... 成立研究院公司..."
- **位置**：`fetch_moat.py::main` 的 search 结果过滤环节
- **根因**：DDGS 对生僻公司（中密控股）查 "上市公司 专利 核心技术 品牌壁垒"时返回的是热门股（茅台）的高相关文章 · 原 filter 只做 `_is_garbage`（字典/百科）检测，没做"结果是否真含目标公司名"检测
- **修法**（`fetch_moat.py`）：
  - `_SUPERSTAR_POLLUTERS` 列表 · 15 个易污染股（茅台/五粮液/宁德/腾讯等）
  - `_result_mentions_company()` · 结果 title+body 不含目标公司名就丢（含 polluter 更是硬 drop）
  - polluter 集合动态排除目标自身（分析茅台时茅台自己的结果保留）
- **回归测试**：4 case
  - polluter 结果被丢
  - 真含目标公司保留
  - 无关结果保守过滤
  - 目标本身是 polluter 时自己不被误伤
- **未来改该区域注意事项**：
  - 其他用 search_trusted + keyword 评分的 dim（4_peers / 7_industry / 13_policy / 17_sentiment / 18_trap）也可能有同类污染 · 后续要逐个加这个 filter
  - `_SUPERSTAR_POLLUTERS` 名单要定期更新 · 2026 年茅台/宁德仍是顶级，但 2027+ 可能换人
  - 不要用 DDGS 对生僻公司做基本信息抓取 · 要靠 akshare / xueqiu API

---

## v2.15.0 (2026-04-20 · YAML persona 层 · 修 Rules 4 类历史立场硬伤)

### FEATURE · YAML persona 接入 agent role-play（取长补短 augur）
- **背景**：xgzlucario/augur 对比测试发现当前 Rules 引擎有 4 类"投资者历史立场错位"硬伤：
  1. 合力泰 × 木头姐 Rules 说"必须重仓"（她不会买 OEM 显示模组）
  2. 合力泰 × 赵老哥 Rules 说"观望"（这恰恰是他最爱的低价题材）
  3. 茅台 × 巴菲特 Rules 说"买入"（他公开说过"不懂中国白酒"）
  4. 中际旭创 × 段永平 Rules 说"强买"（PE 63 超他 40 红线）
  Rules 是"触发某条规则就按模板出话"，没有 persona 历史 context，所以写出的话没法对齐本人立场。
- **实现位置**：
  - `skills/deep-analysis/personas/` · 51 YAML 文件（12 flagship 手写 + 39 stub 自动生成）
  - `skills/deep-analysis/scripts/lib/personas.py` · 加载 + prefix-stable system message
  - `skills/deep-analysis/scripts/lib/i18n.py` · language_instruction（zh/en）
  - `skills/deep-analysis/SKILL.md::HARD-GATE-PERSONA-ROLEPLAY` · agent 必须读 YAML
- **混合架构设计**：
  - Rules 引擎保留（确定性兜底 · agent 失败仍可出报告）
  - YAML persona 补充（flagship 优先级 > Rules headline · stub Rules 优先）
  - 如冲突 · flagship persona 可覆盖 panel.json signal/score（记 `_rules_override`）
- **augur 吸收的具体设计**：
  - YAML persona 格式（philosophy/key_metrics/avoids/voice）
  - prefix-stable system message → prompt cache 命中 → input token 省 50-90%
  - language_instruction() i18n helper
- **保留的自有优势**：
  - 22 维真实 fetcher（vs augur 只靠 LLM web search）
  - 51 投资者含游资派（vs augur 仅 18 位西方人）
  - 17 机构方法 · HTML 报告 · 机械自查 gate
- **验证**（双盲 · 3 股票 × 5 投资者 = 15 格）：
  - 准确性 YAML 14/15 vs Rules 8/15
  - 入戏感 YAML 15/15 vs Rules 2/15
  - 明显错误 YAML 0 vs Rules 4
- **回归测试**：`tests/test_v2_15_0_persona_layer.py` · 14 case
  - 51 个 YAML 全部存在 · 12 flagship 身份正确 · 39 stub 标记正确
  - flagship 必填字段（philosophy + key_metrics + voice + a_share_view）
  - YAML id 跟 panel.json investor_id 1:1
  - `build_system_message` prefix 稳定（prompt cache 前提）
  - i18n zh 默认 / en opt-in / env override / unknown 回退
- **未来改该区域注意事项**：
  - **每次 panel.json 新增 investor_id 都必须同步建对应 persona YAML**（否则 agent role-play 会 silent fall through 到 Rules）
  - flagship 的 12 个 YAML 是"质量基线"· 修改要审慎，要 diff 对比历史 headline 看语气是否跑偏
  - stub 的 39 个 YAML 是占位 · 每当用户反馈"某评委说话不像本人"就把那个 stub 手写升级为 flagship · 长期目标所有 51 个都变 flagship
  - `_parse_minimal_yaml` 是零依赖 parser · 不支持嵌套 list / 复杂 YAML · 保持 YAML 文件简化风格（不要加锚点 / 不要加 >< 折叠）
  - `build_system_message` 必须 prefix-stable · 任何改动要先跑 `test_build_system_message_is_prefix_stable` 确认
  - prompt cache 对 Anthropic / OpenAI 都有效，但对其他 LLM provider 可能无加速 · 文档里不能承诺"一定省钱"
  - agent 走 sub-agent 调 role-play 时要注意：sub-agent 没有 persona YAML context，必须通过 Agent tool prompt 显式传入

---

## v2.14.0 (2026-04-20 · 自动检测 GitHub 新版本 · interactive prompt)

### FEATURE · 自动更新检查
- **需求**：用户每次使用插件时自动检测 GitHub 有没有新版本 · 有更新先提示用户是否更新 · 三选一（是/跳过本版/否）· 跳过本版后直到下一个更新版本出来之前不再跳弹窗
- **实现位置**：
  - `skills/deep-analysis/scripts/lib/update_check.py` · 核心模块（check_for_update + mark_skipped + cache）
  - `run.py::_maybe_prompt_update()` · CLI 直跑 interactive
  - `hooks/session-start` · agent 会话后台写 `.cache/_global/update_prompt.md`
  - `SKILL.md::HARD-GATE-UPDATE-PROMPT` · agent 展示规则
- **设计要点**：
  - 6h cache 防 GitHub API 限流（60 req/h 未认证）
  - semver 严格匹配 · 仅正式 tag 比较
  - 3 态 skip 逻辑：`skipped_version == latest` 才跳过；一旦有更新版立刻再弹
  - 非 TTY / `UZI_NO_UPDATE_CHECK=1` / 网络异常 全部 silent skip · 不阻塞主流程
  - 状态文件 `.cache/_global/update_check.json`
  - agent 环境走 `.cache/_global/update_prompt.md` 文件通道（因为 hook 无法直接跟用户 prompt）
- **防滥用**：timeout 5s + exception 全 catch · 永远不因检查挂主流程
- **回归测试**：`tests/test_v2_14_0_update_check.py` · 13 个 case
  - parse_semver 边界 / newer 比较 / env 禁用 / 同版本不弹 / 新版本弹
  - skip 后同版不弹 · 更新版本再弹
  - 网络失败 silent skip · cache 不重复打 API
  - handle_answer y/s/n 三路径 · format_prompt 含三选项
- **未来改该区域注意事项**：
  - `UZI_NO_UPDATE_CHECK=1` 在 CI / Codex 环境必须默认设 · 防阻塞
  - `check_for_update` 内部任何异常都要 catch 不能抛 · 主流程绝不被 update 检查影响
  - `mark_skipped` 只记 version · 不记时间 · 因为"跳过本版"语义与时间无关（除非 latest 变了）
  - GitHub API 未来可能变 schema · 只读 `tag_name` 和 `body` 两个字段 · 兼容性最大
  - hook 写 prompt 文件走 async `&` · 阻塞 session-start 会拖慢 agent 启动

---

## v2.13.7 (2026-04-19 · wire new sources · registry 登记但 fetcher 没用的 16 源接入)

### BUG · v2.13.4 / v2.13.6 新增源只登记未接入 · 数据流通失效
- **症状**：v2.13.6 加了 `jin10_flash` / `em_kuaixun` / `em_stock_ann` / `ths_news_today` 到 registry，但 `fetch_events.py` / `fetch_sentiment.py` 没调它们，数据源对实际报告 zero 影响
- **位置**：
  - `skills/deep-analysis/scripts/fetch_events.py` (15_events · A 股)
  - `skills/deep-analysis/scripts/fetch_sentiment.py` (17_sentiment)
  - `skills/deep-analysis/scripts/fetch_policy.py` (13_policy)
  - `skills/deep-analysis/scripts/lib/data_sources.py::_kline_us_chain` / `_kline_hk_chain`
- **根因**：
  - `data_source_registry.py` 只是声明清单（tier/markets/dims/health 元数据）· 真正的调用必须在 fetcher 里显式写代码
  - 之前添加 registry entry 时没同步改 fetcher，导致"注册但未使用"
  - 对外看：`SOURCES 已 70` 但用户报告里新闻还是 3-5 条（来自老 cninfo + ak.stock_news_em）
- **影响**：
  - 15_events 数据密度 3-5 条 · 应有 10-30 条
  - 17_sentiment heat 分数偏低 · 没利用金十/东财快讯的实时信号
  - 13_policy 期货/商品类 industry 没有权威协会源信号
  - 美股/港股 K 线在 yfinance 挂掉时（2026 年常见 cookie 失败）无 HTTP 兜底
- **修法**：
  1. 新建 `lib/news_providers.py`（160 行）· 4 新闻源统一聚合 · 10 min cache
  2. `fetch_events.py::main()` A 股路径调 `get_news_multi_source` 合并结果
  3. `fetch_sentiment.py` 调 `get_news_multi_source` 做情绪增强 + heat bonus
  4. `fetch_policy.py` 加 `_fetch_cfachina_titles` · 期货相关 industry 才触发
  5. `data_sources.py::_yahoo_v8_chart()` · 429 自动 retry · US/HK kline chain 都接入
- **验证**：
  - `python3 lib/news_providers.py "" ""` → sources_ok: 4/4, total_hits: 31 ✓
  - `_yahoo_v8_chart("AAPL", "1mo")` → 22 rows ✓
  - `_yahoo_v8_chart("0700.HK", "1mo")` → 21 rows ✓
  - pytest 全量 217 passed（baseline 205 + 12 新）
- **回归测试**：`tests/test_v2_13_7_wire_new_sources.py`
  - `news_providers` 模块 API 存在性 + dataclass
  - `fetch_jin10` / `fetch_em_kuaixun` 正则解析 · 特别 em_kuaixun 无尾 `;` 格式
  - `fetch_events` / `fetch_sentiment` 接入 news_providers 调用路径
  - `_yahoo_v8_chart` 解析 + 429 retry
  - `_kline_us_chain` yf/ak 全败时兜底到 v8
  - `fetch_policy` 期货 industry 调 cfachina · 非期货跳
- **未来改该区域注意事项**：
  - **每次往 `data_source_registry.SOURCES` 加新源，都必须同时改对应的 fetcher 去实际调用这个源**。registry 是静态声明，不是活调度
  - `news_providers.py` 是"ddgs 盲区"补充 · 不是全量替代 · 老的 cninfo / akshare 路径保留
  - `_yahoo_v8_chart` 的 User-Agent 用 Windows Chrome · 测试过 macOS UA 偶尔 429
  - em_kuaixun 响应格式是 `var ajaxResult={...}` 无尾 `;` · 正则用 `\s*;?\s*$` 兼容
  - cfachina 大部分列表 JS 渲染 · 只能抓首页静态标题链接 · 深度内容需 Playwright
  - 加新 news provider 时，要在 `_is_noise_news` 检查 title 是否会被 `_NOISE_KWS` 误过滤

---

## v2.13.5 (2026-04-19 · NetworkProfile 自适应 + agent HARD-GATE 主动触发 Playwright)

### BUG · agent role-play 阶段不主动调 Playwright · 低质量数据未被兜底
- **症状**：用户反馈"我使用下来，并没有遇到模型主动使用 Playwright 的问题"
- **位置**：SKILL.md / AGENTS.md / commands/analyze-stock.md 的 agent 工作流指引
- **根因**：
  - stage1 末尾 `autofill_via_playwright` 自动跑一次 OK，但 data 有字段但全是 "—" 时 `_dim_needs_fallback` 判"不需要兜底" → 跳过
  - agent 介入阶段只做 role-play，不碰数据补充
  - SKILL.md 只在多处散句提及 "Chrome/Playwright MCP"，**没有** HARD-GATE 明确要求 agent 主动调 autofill
- **影响**：
  - 每次 agent role-play 出报告时，某些维度仍空
  - 用户看到 "数据缺失" 的 commentary 模板话术
  - Playwright 基础设施已全 · 但 agent 层**被动**不用
- **修法**（三层）：
  1. `lib/network_preflight.py` 升级 NetworkProfile（9 目标 3 组 + 代理检测 + 写 cache）· 提供 agent 决策输入
  2. SKILL.md 加 `HARD-GATE-PLAYWRIGHT-AUTOFILL` · 明确 3 step 流程：读 net profile → 读 review_issues.json → 主动 FORCE 跑 autofill
  3. `lib/playwright_fallback.DIM_NETWORK_REQUIREMENTS` 每维声明网络能力 · `_filter_dims_by_network` 自动过滤
- **验证**：
  - agent 按 SKILL.md 指引跑 · 看到 `_review_issues.json` warning 主动调 Playwright
  - 测试构造 `NetworkProfile(domestic_ok=False)` → `_filter_dims_by_network` 全跳
  - `NetworkProfile(search_ok=False)` → 7_industry / 18_trap 跳 · 其他维度保留
- **回归测试**：`tests/test_v2_13_5_preflight_adaptive.py` 14 用例
  - Layer 1：代理检测 / recommendation 变化 / cache 读写 / stale 重测（6 用例）
  - Layer 3：domestic offline 全跳 / search offline 部分跳 / 全通保留（3 用例）
  - Layer 2：SKILL.md / AGENTS.md / commands 文档检查（3 用例）
  - 基本数据类：NetworkProfile 字段 / DIM_NETWORK_REQUIREMENTS 完整性（2 用例）
- **若未来改 agent 工作流**：
  - HARD-GATE-PLAYWRIGHT-AUTOFILL 不能删（SKILL.md line ~125 附近）· agent 读了就会主动用
  - `.cache/_global/network_profile.json` schema 不能破（agent 依赖 domestic_ok/overseas_ok/search_ok 三字段）
  - `DIM_NETWORK_REQUIREMENTS` 需覆盖 DIM_STRATEGIES 所有 key（有测试护栏 `test_dim_network_requirements_complete`）
  - 新增维度要同步加网络声明

---

## v2.13.3 (2026-04-19 · 51 评委规则全员历史立场还原)

### BUG · 19 位评委给中际旭创 100 分 · 立场与历史严重不符
- **症状**：用户截图报告 "彼得·林奇 100 分 · 看多 · PEG ≈ 63.253/60 < 1.5" 质疑"林奇历史上不会这么激进"。扫描面板发现 19 人 100 分（13 位游资 + 林奇 + 索罗斯 + 段永平 + 张坤 + 邓晓峰 etc），木头姐 13 分看空（CPO 是她赛道）
- **位置**：`lib/investor_criteria.py` 多处规则 · `lib/investor_evaluator.py` · `lib/seat_db.py`
- **5 处根因**：

  1. **F 组游资射程反向判定**：`_youzi_base_rules` 把 `market_cap > min_mcap` 当打分依据 · 9456 亿对所有游资都"在射程" · 13 位游资误打 100/25。`is_in_range` 定义了但 evaluator 从未调用

  2. **索罗斯反身性方向错**：`abs(upside_to_target) > 10` · 目标价 -63%（看空信号）也判"反身性差 = 看多 100"。`abs` 是 bug

  3. **林奇 PEG 过松 + 无 PE 红线**：`peg_reasonable PEG < 1.5` 太松 · 无 PE 上限。但林奇原话 "PE should approximately equal growth rate" (PEG ≤ 1) 和 "PE > 40 like Rolls Royce"（历史持仓 Taco Bell 0.6/Hanes 0.2/Fannie Mae 0.6 均 PEG < 1）

  4. **木头姐双 bug**：(a) `check=lambda f: f.get("industry_growth_pct", 0) > 20` · 但 stock_features v2.12.1 设的是 `industry_growth`（不带 _pct）· 中际旭创 40% 读成 0 · 判"增长太慢"看空。(b) 白名单缺 CPO/光模块/算力/数据中心/HBM · AI 基建本是 ARK 核心赛道

  5. **中国价投派无 PE 红线**：段永平/张坤/邓晓峰 rules 只看 `pe_quantile_5y < 50` 不看绝对 PE · 高估值成长股也 100 分。历史：段买苹果 PE 18 / 茅台 PE 30；张坤重仓 PE 15-35 区间；邓晓峰偏左侧

- **影响**：所有高 PE 成长股（CPO/光模块/AI/新能源等）的评委分布都被扭曲 · 5 大类评委立场都与历史不符 · 核心卖点"51 评委量化投票"的可信度崩塌

- **修法**：
  1. `seat_db.is_in_range` 加隐式 500 亿大市值上限 + `_MEGA_CAP_ALLOWLIST = {"章盟主"}`
  2. `investor_evaluator.evaluate` 加 `_is_youzi_out_of_range` 前置检查 · F 组超射程 skip
  3. `_youzi_base_rules` 移除 min_mcap/max_mcap 作为 Rule
  4. SOROS_RULES 拆 `sentiment_long_reflex`（只 upside > +10 pass）+ `sentiment_short_reflex_penalty`（upside < -15 扣分）
  5. LYNCH_RULES 6 条：`peg_ideal (PEG<1, 5分)` + `peg_acceptable (PEG 1-1.5, 3分)` + `pe_not_rolls_royce (PE<40, 3分)` + `fast_grower_zone (20-50%, 3分)` + `understandable (2)` + `research_support (2)`
  6. WOOD_RULES 字段兼容 `industry_growth` · 白名单加 CPO/光模块/算力等 12 词
  7. DUAN_RULES/ZHANGKUN_RULES/DENGXIAOFENG_RULES 各加 `pe_not_expensive`（PE<40/40/35）

- **验证**（300308.SZ 实测）：
  | 评委 | v2.13.2 | v2.13.3 |
  |---|---|---|
  | 林奇 | 100 bullish | 38 neutral |
  | 索罗斯 | 100 bullish | 42 neutral |
  | 段永平 | 100 bullish | 84 bullish |
  | 张坤 | 100 bullish | 78 bullish |
  | 邓晓峰 | 100 bullish | 76 bullish |
  | 木头姐 | 13 bearish | 80 bullish |
  | F 组 22 位游资 | 全打分 | 全 skip（射程外） |
  - 100 分从 19 人 → 5 人 · skip 从 1 → 23 人

- **回归测试**：`tests/test_v2_13_3_investor_rules.py` 15 用例
  - F 组：out_of_range / allowlist 章盟主 / small cap in range / 非游资不受影响
  - 索罗斯：+30 bullish / -63 bearish / +5 neutral 三方向
  - 林奇：PEG < 1 / PE 63 reject / PEG 1-1.5 临界
  - 木头姐：CPO 识别 + industry_growth 新字段兼容
  - 段永平/张坤：PE 63 扣分 + PE 30 高分护栏
  - 全量 173 passed（v2.13.2 158 + 新 15）

- **若未来改评委规则**：
  - **核心护栏 · 林奇的 PE 40 红线不能去掉**（历史持仓数据支撑 · Rolls Royce 原话）
  - **索罗斯反身性 abs() 绝对值是已知反向 bug**（目标价 -63% 不是 "反身性差 = 看多"）
  - **F 组游资必须 is_in_range 前置 skip**（大市值股游资不玩 · 9000 亿拉不动）
  - **中国价投派 PE 红线对应各自历史风格**（段 40 / 张 40 / 邓 35）· 改动需说明历史出处
  - **木头姐字段名用 `industry_growth` 口径**（与 stock_features 保持一致 · v2.12.1 字段）
  - 加新评委规则要同时加历史依据（书/年报/访谈 URL）到 `lib/investor_knowledge.py`

---

## v2.13.2 (2026-04-19 · Playwright 触发逻辑升级 · 数据质量感知 + FORCE flag)

### BUG · 维度有 data 但值都是 "—"/空时 Playwright 兜底未触发
- **症状**：用户反馈"有很多网站爬不到内容，也没拉起 Playwright"。中际旭创 cache 里 `7_industry.data` 有 12 个 key 但 `growth`/`tam`/`penetration` 都是 `"—"`，Playwright 却判定"已有数据"直接跳过
- **位置**：`lib/playwright_fallback.py::_dim_needs_fallback`
- **根因**：原版只看 `len(data)`：
  ```python
  if not data or not isinstance(data, dict): return True
  if dim.get("fallback") and len(data) < 4: return True
  return False
  ```
  数据 12 keys 但全是垃圾也判"不需要兜底" · 用户期望落空
- **修法**：
  1. 新加 `_dim_quality_score(data)` 计算有效值占比（排除 `_` 前缀诊断字段）
  2. `QUALITY_THRESHOLD = 0.5` · 低于 50% 触发兜底
  3. `dim.fallback=True` 总是触发（不再看 len）
  4. 返 tuple `(needs, reason)` 让日志可看
- **附加**：
  - 加 `UZI_PLAYWRIGHT_FORCE=1` 环境变量 · 用户强制 kill switch · 忽略 quality 判定
  - `autofill_via_playwright` 加清晰日志 · 每个维度 skip/run 原因可见 · 禁用时明确 `disabled_reason`
- **验证**：
  - `_dim_quality_score({"a":"—","b":"","c":None,"d":[],"e":"真实"})` → 20%
  - 12 keys 含 3 有效 → 触发 ✅
  - FORCE=1 · 质量 100% 的 dim 也触发
- **回归测试**：`test_v2_13_playwright_strategy.py` 新增 5 用例
  - `test_dim_quality_score_detects_mostly_empty`
  - `test_dim_quality_score_skips_ignoring_underscore_keys`
  - `test_autofill_triggers_on_low_quality_data`
  - `test_force_flag_ignores_quality_check`
  - `test_autofill_summary_has_disabled_reason_when_off`
- **若未来改 Playwright 触发**：
  - `_dim_needs_fallback` 返 tuple `(needs, reason)` 契约不能破（调用方日志依赖 reason）
  - `QUALITY_THRESHOLD` 如需调整必须跑 `test_autofill_triggers_on_low_quality_data` 确保低质量用例仍触发
  - `_` 前缀字段不计 quality 这个语义不能改（避免 `_autofill`/`_debug` 被误当有效数据）
  - `UZI_PLAYWRIGHT_FORCE` 是用户 kill switch · 不能移除

---

## v2.13.1 (2026-04-18 · Playwright 全 10 维覆盖 · 策略契约修订)

### 改进 · 扩展 DIM_STRATEGIES 到全 10 维（策略调整，非 bug 修复）
- **背景**：v2.13.0 Codex review 出于反爬/合规/信噪比担忧，明确排除 5 维（7_industry/14_moat/13_policy/18_trap/19_contests）。用户明确反馈："反爬合规不是问题，这个是开源研究项目受保护的"
- **位置**：
  - `lib/playwright_fallback.py::DIM_STRATEGIES` · 5 → 10 entry
  - `lib/analysis_profile.py` · `_PLAYWRIGHT_MEDIUM_DIMS` 4→6 维，`_PLAYWRIGHT_DEEP_DIMS` 5→10 维
  - `tests/test_v2_13_playwright_strategy.py` · 更新 count 断言 + 移除排除护栏
- **策略变化**：
  | 维度 | v2.13.0 | v2.13.1 | 目标页 |
  |---|---|---|---|
  | 7_industry | ❌ | ✅ medium + deep | 百度搜索 `{行业}+景气度` |
  | 14_moat | ❌ | ✅ medium + deep | 百度百科 `/item/{name}` |
  | 13_policy | ❌ | ✅ deep | 证监会 `csrc.gov.cn` |
  | 18_trap | ❌ | ✅ deep | 小红书 `/search_result?keyword={name}+老师+推荐` |
  | 19_contests | ❌ | ✅ deep | 雪球 `/cube/rank/list` 匿名组合排行 |
- **新增 5 个 parser**（`lib/playwright_fallback.py`）：
  - `_strategy_7_industry` · 抓百度 `<h3>` 标题 + `.content-right` 描述
  - `_strategy_14_moat` · 抓 `.lemma-summary` + `.basicInfo-item` 键值对
  - `_strategy_13_policy` · 抓证监会动态 `<a title="...">` 列表
  - `_strategy_18_trap` · 抓小红书 `"title":"..."` 帖子标题 + 命中数统计（风险信号）
  - `_strategy_19_contests` · 抓雪球组合 JSON 的 `name` + `total_gain`
- **回归测试**：
  - `test_dim_strategies_has_10_entries` (替代 `has_5_entries`)
  - `test_all_parsers_callable_and_return_none_on_empty_html` · 10 个 parser 都 mock `fetch_url` 返 None · 验证不抛
  - `test_medium_dims_subset_of_deep` · 护栏：medium 必须是 deep 子集
- **护栏测试移除**：
  - `test_excluded_dims_not_in_strategies` 移除（反爬合规不再是契约禁令）
- **v2.13.0 契约修订**：
  - ❌ 旧：v2.13.0 BUGS-LOG 说"不能不经 Codex review 加回排除维度"
  - ✅ 新：**开源研究场景不受合规限制** · 维度扩展由用户需求驱动即可
- **若未来改 Playwright 层**：
  - 10 个维度的 parser 如遇 HTML 变化 → 返 None 即可，不要 raise（已在 `fetch_url` 层 try/except）
  - `_PLAYWRIGHT_MEDIUM_DIMS ⊆ _PLAYWRIGHT_DEEP_DIMS` 关系必须保持（`test_medium_dims_subset_of_deep` 护栏）
  - 加新维度需同步：(1) `DIM_STRATEGIES` dict (2) `_PLAYWRIGHT_*_DIMS` 白名单 (3) 更新 `test_dim_strategies_has_10_entries` count

---

## v2.13.0 (2026-04-18 · Playwright 通用兜底 · 按三档 profile 分级)

### 改进 · Playwright fallback 通用化 + 按 profile 分级
- **背景**：v2.12.1 给 `fetch_peers.py` 加了雪球 Playwright Tier 3。用户提出"所有爬不到数据的都用 Playwright + 自动装"。直接做全量会导致 lite 用户也要背 150MB Chromium，且某些维度（小红书/抖音/微博）反爬 + 合规风险大
- **位置**：
  - 新增 `lib/playwright_fallback.py`（~320 行）· 通用模块
  - 新增 `lib/junk_filter.py` · 抽离 v2.12.1 的 `_is_junk_autofill`
  - `lib/analysis_profile.py` · AnalysisProfile 加 `playwright_mode` + `playwright_dims` 字段
  - `run_real_test.py:1750+` · 在 `_autofill_qualitative_via_mx` 之后调用
- **策略**（Codex review 后收敛）：
  | profile | playwright_mode | 覆盖维度 | 自动装行为 |
  |---|---|---|---|
  | lite | off | 无 | 不涉及（保持 30s-1min 快扫）|
  | medium | opt-in · 需 `UZI_PLAYWRIGHT_ENABLE=1` | 4 维（4_peers/8_materials/15_events/17_sentiment） | 未装时打印命令让用户手动装，本次跳过 |
  | deep | default 默认启用 | 5 维（medium 4 + 3_macro 官方权威） | 未装时 y/n 交互确认 → 同意自动装 → 失败 graceful degrade |
- **Codex review 排除的维度**：
  - `7_industry` → 百度搜索页信噪比差（保持 `search_trusted` site: 方案）
  - `14_moat` → 百度百科质量差
  - `13_policy` → `search_trusted` site: 限权威域已够
  - `18_trap` → 小红书/抖音反爬严 + UGC 合规风险
  - `19_contests` → `lib/xueqiu_browser` 已有专用登录路径
- **自动装流程**：
  1. 检测 `playwright` 包 + Chromium executable
  2. deep `auto=True` → `_confirm_install_interactive()` y/n 询问
  3. 同意 → `pip install playwright` 复用 `run.py::PYPI_MIRRORS` 清华/阿里云/中科大 fallback
  4. `playwright install chromium` 下载 ~150 MB · stdout 可见
  5. 任何环节失败 → 返 False · 调用方跳过 Playwright · **不阻塞主流程**
- **反爬 / 合规原则**：
  - 只抓官方权威页：`xueqiu.com/S/{sym}` public / `cninfo.com.cn` / `em.eastmoney.com` F10 / `stats.gov.cn`
  - 每次请求随机 0.5-1.5s sleep
  - 不抓 UGC 平台（小红书/抖音/微博）
- **验证**：
  - `is_playwright_enabled()` · lite False · medium opt-in + env True · deep 永远 True
  - `ensure_playwright_installed(auto=False)` 未装不跑 subprocess · 只打印命令
  - `ensure_playwright_installed(auto=True)` + user n → 不装 · 返 False
  - `autofill_via_playwright` 尊重 `profile.playwright_dims` 白名单
  - Playwright 返垃圾（"类型；类型"）被 `junk_filter` 过滤不写入
- **回归测试**：`tests/test_v2_13_playwright_strategy.py` · 21 个用例
  - 3 档 profile 字段检查 · `is_enabled` 三场景 · `ensure_installed` 5 种路径 · autofill 白名单 + 垃圾过滤 + 已有数据跳过 · `DIM_STRATEGIES` 5 维 · 排除维度护栏 · `junk_filter` 模块导出 · `run_real_test._is_junk_autofill` BC delegate
  - 全 mock · 无真实浏览器依赖 · CI 可跑
- **若未来改 Playwright 层**：
  - **不能把 lite 的 playwright_mode 改为 opt-in/default**（lite 设计上就是快扫 · 加浏览器破坏档位语义）
  - **不能静默自动装 Chromium**（150MB 下载用户必须知情 · deep 档已有 `_confirm_install_interactive`）
  - **安装失败必须 graceful degrade**（不能 raise 阻塞主流程 · 现有 `try/except` 不能删）
  - **不能把排除的 4 维（14_moat/13_policy/18_trap/19_contests/7_industry）加回 DIM_STRATEGIES 而不经 Codex 级 review**（反爬/合规/信噪比问题有先例）
  - **BC 契约**：`run_real_test._is_junk_autofill` 必须保留（现 delegate 到 `lib/junk_filter`）· 老代码可能直接 import

---

## v2.12.1 (2026-04-18 · 4 个报告板块空数据 / 错数据修复)

用户实测中际旭创（300308.SZ）发现 4 个板块问题 · 一次性修完.

### BUG · `4_peers` 东财 push2 挂了同行表空白
- **症状**：报告"同行对比"板块完全空 · `peer_table: []` · `peer_comparison: []`
- **位置**：`fetch_peers.py::main`（A 股分支 line 72-121 原版）
- **根因**：现有 try/except 只 catch 异常到 `peers_raw`，主链路 `ak.stock_board_industry_cons_em`（走 push2）挂了后没切换到 fallback 源
- **影响**：任何 push2 被反爬/限流的网络环境（国内代理、Codex 沙箱）同行表必空
- **修法**（三层 fallback + 一层保底）：
  1. Tier 1 主链（不变）
  2. Tier 2 · 2.5s 后 retry 一次（网络抖动兜底）
  3. Tier 3 · 雪球 Playwright 登录态（用户 opt-in `UZI_XQ_LOGIN=1`）· 复用 `lib/xueqiu_browser.py::fetch_with_browser` + 新加 `fetch_peers_via_browser(code)`
  4. Tier 4 · 最低保底：`_build_self_only_table` 返回公司自己一行 + `fallback: True` + `fallback_reason` 字段
- **验证**：中际旭创 E2E `peer_table` 至少有公司自己一行（不再空） + `fallback_reason` 明确说明降级原因
- **回归测试**：`test_v2_12_1_data_fixes.py::test_fetch_peers_has_self_only_fallback` / `test_fetch_peers_tier_chain_documented` / `test_fetch_peers_fallback_reason_surfaced` / `test_xueqiu_browser_has_fetch_peers_function` / `test_xueqiu_browser_peer_fn_respects_opt_in`
- **若未来改 fetch_peers**：Tier 4 `_build_self_only_table` 保底必须保留（不能回到"整表空"）· `data.fallback_reason` 字段 agent 依赖识别降级· 雪球 opt-in 必须保留 `is_login_enabled()` 检查不能改成默认启用（headless 环境会卡）

### BUG · `7_industry.growth/tam/penetration` 永远 `—`
- **症状**：行业景气板块的增速/TAM/渗透率 3 个字段永远是 `—`，即便 `dynamic_snippets` 已抓到 9 条 search 结果
- **位置**：`fetch_industry.py::_dynamic_industry_overview` (line 110-165) + `main` (line 185-188)
- **根因**：
  1. 原 growth regex `r"([+\-]?\d{1,3}(?:\.\d+)?)\s*%"` 不带上下文 · 容易被 `PE 25%` / `失业率 5%` 抢先匹配 · 且不匹"涨超40%"这类中文财经常见表达
  2. `penetration` 完全没 regex 抽取路径
  3. `main` line 187 `penetration` 没 fallback 到 dynamic（只 est 一条路径）
  4. `all_bodies` 只拼 `body` 不含 `title` · 关键数字常在 title 里（"净利齐涨超40%"）
- **影响**：所有未被 INDUSTRY_ESTIMATES 硬编码覆盖的 236+ 行业（包括通信设备）三字段全空 · 同时导致 Bug 4 BCG 缺 growth 输入
- **修法**：
  1. growth regex 上下文感知 · 关键词含 `增长/增速/CAGR/复合增长/同比/增幅/年均增长/涨超/涨幅/暴涨/翻倍/提升/上升/上涨/净利齐涨` + 0-20 字符 + %
  2. 加 `tam_context_pat` 优先匹"市场规模/规模达/产业规模/TAM/行业规模" 附近的"XX亿"
  3. 加 `penetration_heuristic` · 匹"渗透率 XX%" / "XX% 渗透率"
  4. main line 228 · `penetration = est.get("penetration") or dynamic.get("penetration_heuristic") or "—"` 补兜底
  5. `all_bodies` 改为拼 `title + body`
- **验证**：mock search_trusted 返含"增速 42% 预计 CAGR 30%" 的 snippets · `growth_heuristic` 抓到值不是 `—`
- **回归测试**：`test_industry_growth_regex_picks_context_aware` / `test_industry_penetration_regex_extracts` / `test_industry_penetration_fallback_wired_in_main`
- **若未来改 fetch_industry**：
  - 不能去掉上下文关键词直接裸匹 `%`（会被 PE/失业率等噪音抢先）
  - `penetration_heuristic` 在返回 dict 里必须保留（main 依赖）
  - `all_bodies` 必须同时拼 title + body（关键数字常在 title）

### BUG · `8_materials.core_material = "类型；类型"` (MX 垃圾数据无过滤)
- **症状**：原材料板块 `core_material` 显示为"类型；类型"这种 MX prompt 残留噪音
- **位置**：`run_real_test.py::_autofill_qualitative_via_mx` (line 1047-1068 原版)
- **根因**：后处理 `_autofill_qualitative_via_mx` 调 MX 妙想 API 填 6 个定性维度时，**直接把 MX 返回 `text` 写入 `data[字段]` 没做质量校验**。MX 偶尔会返回 prompt 模板残留（"类型；类型" / "抱歉，无法回答" / 重复片段）
- **影响**：6 个定性维度（3_macro/7_industry/8_materials/9_futures/13_policy/15_events）都可能被垃圾数据污染，比空还糟（显示错误数据）
- **修法**：
  1. 加 `_is_junk_autofill(text)` 函数 · 检测长度 < 5 / 黑名单短语（类型；类型/抱歉/无法回答/暂无数据/XXX/TODO/null）/ 分号分隔全同片段
  2. `_AUTOFILL_JUNK_PATTERNS` 模块级常量便于扩展
  3. MX 和 ddgs 返回后分别过滤 · 垃圾数据 `text = ""` 不写入
  4. 保留 `_autofill_failed` 标记让 agent/UI 明确知道是"数据不足"
- **验证**：中际旭创 E2E `core_material` 不再是"类型；类型"（可能是真实 ddgs 结果或 `—`）· 真实数据如"高端光通信收发模块"不被误伤
- **回归测试**：`test_junk_autofill_catches_type_duplication` / `test_junk_autofill_catches_refusal` / `test_junk_autofill_lets_real_text_through`
- **若未来改 _autofill_qualitative_via_mx**：
  - 写入 `data[字段]` 前必须先跑 `_is_junk_autofill(text)` 过滤
  - 遇到新的 MX 垃圾 pattern（如"未找到"/"NaN"）加到 `_AUTOFILL_JUNK_PATTERNS` 常量
  - 不能为了"省一次判断"就写无过滤版本 - 比空还糟的数据误导用户

### BUG · BCG 矩阵所有股都归为 "Dog (瘦狗)"
- **症状**：报告"BCG 矩阵定位"永远显示 Dog 瘦狗 + "考虑剥离/收缩" · 中际旭创作为 CPO 全球龙头被归 Dog 明显错误
- **位置**：
  - 计算：`lib/deep_analysis_methods.py::build_competitive_analysis` (line 488-503)
  - features 源头：`lib/stock_features.py` (line 340-341)
- **根因**：
  1. `stock_features.py:340-341` 写死 `f["industry_growth"] = _f(industry.get("growth"), default=10)` 和 `f["market_share"] = _f(industry.get("market_share"), default=10)` · 但 `industry.market_share` key 从未被任何 fetcher 写入 · 永远 default 10 · `industry.growth` 也因 Bug 2 永远 `—` → `_f("—")` = 0 或 default 10
  2. BCG 阈值 `market_share > 15` + `market_growth > 10` · 默认 10/10 不满足任何 `> 15` 条件 → 必落 Dog
  3. 阈值 `> 15 市场份额` 对 A 股单股非现实（很少有单股过 15% 市占率）
- **影响**：所有股票（茅台/中际旭创/宁德时代 etc）BCG 都是 Dog · "Star/Cash Cow/Question Mark"三档形同虚设
- **修法**：
  1. `stock_features.py` · 真实计算 `market_share = 公司市值 / 行业总市值 × 100`（数据源：`basic.market_cap_yi` / `industry.cninfo_metrics.total_mcap_yi`）
  2. `stock_features.py` · `industry_growth` 从 `industry.growth` 字符串 regex 解析 `[+\-]?\d+(?:\.\d+)?%`（Bug 2 修复后 growth 字段有真实值）
  3. `deep_analysis_methods.py` · BCG 阈值调整：Star `share>3 AND growth>15`、Cash Cow `share>3 AND growth≤15`、Question Mark `share≤3 AND growth>15`、Dog `share≤3 AND growth≤15`
  4. `default=10` 硬编改为 `default=0` · 让数据缺失时明确落 Dog（而不是假数据误导为 Dog）
- **验证**：
  - 中际旭创市值 9455 亿 / 通信设备行业 171648 亿 ≈ 5.5% > 3 · E2E 实测 BCG 升为 `Cash Cow (现金牛)`（growth 若抓到 >15% 则升 Star）
  - features market_share 5.5 + growth 25 → 单元测试验证归 Star
  - features share 0.5 + growth 2 → 归 Dog（回归护栏）
- **回归测试**：`test_stock_features_market_share_real_computation` / `test_bcg_thresholds_updated_for_realistic_a_share` / `test_bcg_classifies_zhongji_as_star` / `test_bcg_classifies_low_growth_small_share_as_dog` / `test_bcg_question_mark_for_high_growth_small_share`
- **若未来改 BCG / features**：
  - `stock_features.market_share` 必须真实计算 · 不能回退到 `default=10`
  - BCG 阈值 A 股上下文下 `share > 3` 是合理线（15% 是非现实）· 不能无理由拉回 15
  - `default=0` vs `default=10` 语义差异大 · 前者代表缺失（让 agent 识别），后者是假数据（历史 bug 根因）
  - 依赖链：Bug 4 需 Bug 2 先修好（growth 字段要有真实值）

---

## v2.11.0 (2026-04-18 · 评分校准 · 用户反馈驱动)

### BUG · 白马股被评"谨慎"、从未有股能拿"值得重仓"
- **症状**：
  - @崔越（微信）："测了几只股票，没有超过 65 分的"
  - @W.D（微信）："茅台 47 分"
  - @睡袍布太少（微信）："目前只测到天孚通信超过 65"
  - 观察：线性评分完全没有 ≥ 85 的股票，"值得重仓"档位形同虚设
- **位置**：
  - `run_real_test.py::generate_panel` 的 consensus 公式
  - `run_real_test.py::generate_synthesis` 的 verdict 阈值
  - `lib/stock_style.py::apply_style_weights` 的 neutral 权重（需同步）
- **根因**：
  1. 51 评委里价值派 6 + 中国价投 6 + 游资 23 = 35 人对大多数股偏保守 → bullish 常仅 5-15 人
  2. v2.9.1 consensus 公式 `(bullish + 0.5×neutral) / active` neutral 权重 0.5 过低，把 neutral 当"半空头"处理。实际语义是"不坑但不是我心头好"，应接近中位数
  3. verdict 阈值 85/70/55/40 太严 · 茅台白马实测 fund=62/consensus=37 → overall 47 → 谨慎
- **影响面**：所有 A 股 / 港股 / 美股。白马股结构性偏低 → 用户失去信心 → 卸载
- **修法**：
  1. `generate_panel` · consensus `NEUTRAL_WEIGHT 0.5 → 0.6` + 加 `consensus_formula.version` 诊断字段
  2. `generate_synthesis` · verdict 阈值 `85/70/55/40 → 80/65/50/35`
  3. `stock_style.apply_style_weights` · neutral 权重 `w*0.5 → w*0.6`（与 generate_panel 对齐）
- **验证**（模拟茅台典型 12/20/16/3 分布）：
  - 旧 consensus = (12 + 10) / 48 × 100 = 45.8 · overall = 62×0.6+45.8×0.4 = 55.5 → 观望
  - 新 consensus = (12 + 12) / 48 × 100 = 50.0 · overall = 62×0.6+50×0.4 = 57.2 → 观望优先
  - 对比茅台 47 实测 → 新公式提升 ~10 分，verdict 从 "谨慎" 升到 "观望优先"
- **回归测试**：`tests/test_v2_11_scoring_calibration.py` 8 个用例 · 护栏 `test_no_regressions.py::test_consensus_neutral_weighted_formula` 兼容 0.5/0.6 两种权重
- **若未来改 consensus**：
  - `NEUTRAL_WEIGHT` 必须同时改 `generate_panel` 和 `stock_style.apply_style_weights` 两处（否则加权前后分数不一致）
  - verdict 阈值任一改动必须跑 `test_verdict_thresholds_are_v2_11_calibrated`
  - 把 bullish-only 公式改回 `bullish / active` = **禁止**（forum 反馈已明确该公式导致白马结构性偏低）

---

## v2.10.7 (2026-04-18 · Codex 整体审查发现执行链路 3 处)

### BUG · `raw["market"]` 硬编 "A" 污染 HK/US 路径
- **症状**：`python run.py 00700.HK --depth lite` Self-Review 显示 `(A)`，应为 `(H)`；后续市场分支判断全错
- **位置**：`skills/deep-analysis/scripts/run_real_test.py::collect_raw_data` 入口 + post-fetch_basic 回填逻辑
- **根因**：
  1. 初始化时硬编码 `raw["market"] = "A"`
  2. post-fetch_basic 回填只在 `resolved_ticker != ticker` 分支里触发（用户直接输入 `00700.HK` 时 resolved == input，不触发）
  3. 回填读的是 `dims["0_basic"].get("data", {}).get("market", "A")`，但 fetch_basic 实际把 market 放在**顶层**（见 fetch_basic.py:80 `"market": ti.market`），不在 `.data` 里
- **影响**：所有 HK/US 直输 + 所有 resume cache 走 raw 的场景，`raw.market` 都被污染为 A
- **修法**：
  1. 入口用 `parse_ticker(ticker).market` 预填（非中文名即可拿到 H/U）
  2. post-fetch_basic 改为**无条件**从 `dims["0_basic"].get("market")` 顶层回填
  3. resume 从 cache 复用时也回填 `raw["market"]`
- **验证**：`python run.py 00700.HK --depth lite` Self-Review 显示 `(H)` ✅
- **回归测试**：`test_v2_10_4_fixes.py::test_raw_market_initialized_from_parse_ticker`
- **若未来改 collect_raw_data**：不能把 market 硬编码回 "A"；不能把顶层 market 改回读 `.data.market`；新增 resume 路径必须同步回填 market

### BUG · `resume` cache 对别名输入失效
- **症状**：用户用中文名 "贵州茅台" 或三位港股 "700" 输入时，`.cache/600519.SH/raw_data.json` 已存在也不命中缓存，重跑 Stage 1 耗时 + token 双爆
- **位置**：`run_real_test.py::collect_raw_data` 的 resume cache 加载块（line ~107-114）
- **根因**：注释写"尝试用原始 ticker 和 resolved ticker 都查"，实际只 `_read_cache(ticker, "raw_data")` 调了一次，发生在 fetch_basic 解析之前
- **影响**：别名输入下 resume 形同虚设；Codex 等 agent 环境反复耗 token 重跑
- **修法**：双重查询——先 `_read_cache(ticker)` 原样查；未命中 + 非中文名则 `_read_cache(parse_ticker(ticker).full)` 兜底
- **验证**：`python run.py 00700.HK`（cache 存在）→ 命中 15/15 维
- **回归测试**：`test_v2_10_4_fixes.py::test_resume_cache_tries_resolved_ticker`
- **若未来改 resume 路径**：不能移除 `parse_ticker.full` 兜底查询；中文名输入走 fetch_basic resolver 不在 resume 范畴内

### BUG · AGENTS.md 强制全量 agent 流程 · 抵消 CLI/lite 降载设计
- **症状**：v2.10.4/5 已把 `agent_analysis.json` 缺失降 warning 允许 CLI 直跑出报告，但 AGENTS.md 仍让 agent 看到"分析 XXX"就无条件 role-play 51 评委 + 写 agent_analysis.json，token 浪费
- **位置**：`AGENTS.md` Step 1-5 + `CLAUDE.md` "工作流" 段落
- **根因**：v2.10.4/5 是代码侧改，文档没同步更新
- **修法**：加"深浅两路径"决策树：
  - 快速路径（默认）：`python3 run.py <ticker> --depth lite/medium --no-browser` → 30s-4min 出完整报告，**不需要** role-play
  - 深度路径：仅当用户明确要 DCF / IC memo / 首次覆盖等深度产物时走两段式
- **若未来改 agent 流程**：run.py 的 CLI 直跑路径必须保持"缺 agent_analysis.json 降 warning 继续出 HTML"；文档里必须保留深浅两路径说明

---

## v2.10.5 (2026-04-18 · v2.10.4 遗漏补丁)

### BUG · `check_coverage_threshold` 非 profile-aware 阻塞 lite 出报告
- **症状**：`python run.py 600519.SH --depth lite --no-browser` 跑出 `coverage=17% (3/18)` → critical → `RuntimeError: BLOCKED by self-review`，HTML 生成失败
- **位置**：`skills/deep-analysis/scripts/lib/self_review.py::check_coverage_threshold:254`
- **根因**：分母用全 18 项 `CRITICAL_CHECKS`，lite 只启用 7 维，结构性偏低；CLI 直跑模式又没 agent 可补数据，critical 把流程卡死
- **影响**：任何 lite 模式 + 网络稍差的组合 → 报告 block
- **修法**：
  1. Profile-aware 分母：只算 `profile.fetchers_enabled` 里的 CRITICAL_CHECKS 项
  2. CLI-only/lite 模式下 `< 40%` 的 critical 降为 warning（允许继续出 HTML 供参考）
- **验证**：600519.SH lite → `critical=0 warning=2`，HTML 生成 ✅
- **回归测试**：
  - `test_v2_10_4_fixes.py::test_coverage_critical_downgrades_in_lite`
  - `test_v2_10_4_fixes.py::test_coverage_critical_preserved_in_medium`（回归护栏 · medium 仍 critical）
  - `test_v2_10_4_fixes.py::test_coverage_profile_aware_denominator`
- **若未来改 self_review**：分母必须读 profile，不能退回硬编码 18；CLI 模式下 critical 降级逻辑不能删

### BUG · `run.py` 直跑模式未自动标记 UZI_CLI_ONLY
- **症状**：`python run.py 002273.SZ --depth medium` → `agent_analysis` 缺失仍 critical → block HTML
- **位置**：`run.py::main()` 环境变量设置区
- **根因**：CLI 降级逻辑依赖 `UZI_DEPTH=lite / UZI_LITE=1 / UZI_CLI_ONLY=1 / CI=true` 四个信号；medium 模式都不命中
- **修法**：run.py main() 开头加 `os.environ.setdefault("UZI_CLI_ONLY", "1")` — run.py 是 CLI 直跑入口（agent 流程走 stage1/stage2 直接调用，不经 run.py）
- **验证**：002273.SZ medium → HTML 生成 ✅
- **回归测试**：`test_v2_10_4_fixes.py::test_run_py_sets_cli_only_env`
- **若未来改 run.py**：不能删 UZI_CLI_ONLY=1 setdefault；若新增 agent 专用入口必须另设标志区分

### BUG · `render_fund_managers` None 字段 TypeError
- **症状**：`TypeError: '>' not supported between instances of 'NoneType' and 'int'` in `assemble_report.py:1844`
- **位置**：`skills/deep-analysis/scripts/assemble_report.py::render_fund_managers`（5 处字段）
- **根因**：v2.10.2 fund_holders 双层策略（Top N full + rest lite）下，rest lite 基金的 `return_5y/annualized_5y/max_drawdown/sharpe/peer_rank_pct` 为 **显式 None**，但 `m.get("return_5y", 0)` 只处理 key 缺失、不处理值为 None
- **影响**：所有 lite + fund holders ≥ N+1 的场景 → 报告组装崩溃
- **修法**：`m.get("return_5y") or 0` 统一兜底（既处理缺失又处理 None）
- **验证**：`run.py 002273.SZ --depth medium` 正常生成 HTML
- **若未来改 fund_holders schema**：数值字段保持"None = 未计算"语义；新增数值字段 render 时必须用 `or 0` 不能用 `.get(k, 0)`

---

## v2.10.4 (2026-04-17 · Codex 测试反馈 3 bug)

### BUG · lite 模式与 self-review 冲突（9 critical 误报）
- **症状**：`UZI_DEPTH=lite` 跑完 gate 报 9 个 critical（维度缺失、data 为空）
- **位置**：`lib/self_review.py::check_all_dims_exist` + `::check_empty_dims`
- **根因**：硬编码检查全 20 维，不看 profile；lite 只启用 7 维，其余 13 维被误报 critical
- **修法**：两函数都读 `analysis_profile.get_profile().fetchers_enabled`，只检查启用的维度
- **回归测试**：
  - `test_check_all_dims_lite_respects_profile`
  - `test_check_empty_dims_lite_respects_profile`
  - `test_check_all_dims_medium_still_reports_missing`（护栏）
- **若未来加 self-review check**：新 check 涉及维度遍历必须 profile-aware

### BUG · agent_analysis.json 缺失在 CLI 直跑误报 critical
- **症状**：`python run.py` 直跑（无 agent 介入）必定 critical 阻止 HTML
- **位置**：`lib/self_review.py::check_agent_analysis_exists`
- **修法**：`UZI_DEPTH=lite / UZI_LITE=1 / UZI_CLI_ONLY=1 / CI=true` 任一命中 → 降 warning
- **回归测试**：`test_agent_analysis_missing_downgrades_in_lite` + `test_agent_analysis_missing_critical_in_medium`（护栏）
- **若未来改：** 正常两段式流程 agent_analysis 缺失仍是 critical，不能一刀切降级

### BUG · ETF 早退 RuntimeError（stage1 已识别非股，stage2 仍被调用）
- **症状**：`python run.py 512400.SH` → stage1 写 `_resolve_error.json` 识别为 ETF，但 `run_real_test.main()` 仍调 stage2 → `RuntimeError: Stage 2 缺少数据`
- **位置**：`run_real_test.py::main()` + `run.py::main()` 两处
- **修法**：
  1. `run_real_test.main()` 加 `status == "non_stock_security"` 分支，跳过 stage2 并 return
  2. `run.py::main()` 捕获 `run_analysis()` 返回的 `non_stock_security` dict，打印成分股提示后 `sys.exit(0)`
  3. 中文名输入路径同样捕获
- **回归测试**：`test_main_returns_early_on_non_stock_security` + `test_main_returns_early_on_name_not_resolved`
- **若未来加新的"非个股"类别**：早退 status 加到 `main()` 的分支列表里，不要让 stage2 被白白调用

---

## v2.8.3 (2026-04-17 critical · 行业分类碰撞错误)

### BUG#R10 · 申万行业被误映射到证监会"农副食品加工业"（严重）
- **症状**：用户分析云铝股份（000807.SZ），属于工业金属铝行业，但报告里 `7_industry` / `10_valuation` 两维都把它归类为**农副食品加工**
- **位置**：`fetch_industry.py::_cninfo_industry_metrics:90` + `fetch_valuation.py:122`
- **根因**：两处都用 `df["行业名称"].str.contains(industry_name[:2])` 做 fuzzy 匹配。证监会行业分类里含"工业"子串的有 4 个行业，其中农副食品加工业排第一，`iloc[0]` 盲选它
- **影响面**：所有带"工业 / 加工 / 制造"字样的申万行业（工业金属/工业母机/工业机械/工业气体 etc）全受影响；报告的 industry_pe、公司数量、行业景气度文本全是错的
- **修法**：新 `lib/industry_mapping.py`：
  1. `SW_TO_CSRC_INDUSTRY` 134 条申万 → 证监会硬映射
  2. `HIGH_COLLISION_TOKENS` 黑名单 12 个通用前缀
  3. `resolve_csrc_industry()` 4 策略解析：硬映射 → 整名子串 → 去前缀 fuzzy → 返 None
  4. **绝不再盲选 `iloc[0]`**，匹配不到明确返 None
- **验证**：云铝股份 → 工业金属 → 有色金属冶炼和压延加工业 PE 32.97 ✓
- **回归测试**：
  - `test_industry_mapping_blocks_high_collision_substring`
  - `test_resolve_csrc_industry_on_mock_df`（mock 6 个证监会行业，用工业金属查询必须选到有色金属加工业不能选到农副食品）
  - `test_fetch_industry_and_fetch_valuation_use_mapping`
- **若未来改 fetcher**：`resolve_csrc_industry` 是 single source of truth，不许退回裸 `str.contains(ind[:2])` pattern
- **若未来加新申万行业**：优先加到 SW_TO_CSRC_INDUSTRY 硬映射；不行再靠 fallback，不要用 iloc[0] 盲选

---

## v2.8.1 (2026-04-17 quotes expansion · 海外人物真实原话)

### 增强 · quotes-knowledge-base.md 补齐 22 位海外代表人物
- **动机**：v2.8.0 做完 investor_profile 后发现 quotes-knowledge-base（agent 必读语料）只覆盖中国投资者，海外 20+ 人物原话空白。用户："还有很多你要去找他们的言论，去找一下，收集一下"
- **方法**：4 个并行 research agent 按流派取证；严格要求真实可验证、不 fabricate
- **产出**：KB 306 → 639 行；人物 23 → 45；每人 3-5 条带 URL 原话
- **溯源标准**：优先原版书（Principles / Margin of Safety / One Up on Wall Street / Zero to One / Reminiscences）、官方年报（berkshirehathaway.com / oaktreecapital.com / ARK）、经过验证的 Goodreads / Farnam Street / 雪球 / WSJ / CNBC
- **发现的副作用**：`chengdu` 被写进 PROFILES 但 KB 把它归类为"席位集合体·无个人原话" → 移出 PROFILES 走 group F fallback（席位集合体不应冒充个人人物）
- **回归测试**：
  - `test_quotes_knowledge_base_covers_authored_personas`（每个 authored 必须在 KB 有段落）
  - `test_quotes_knowledge_base_has_source_urls`（抽查必须带 URL）
- **若未来改 investor_profile**：新增 authored 人物必须同步加 KB 段落，否则测试 fail
- **若未来改 KB**：不能删海外人物 URL（下游 agent 依赖可点击溯源）

---

## v2.8.0 (2026-04-17 persona profile · 因地制宜)

### 增强 · 每个评委用自己方法论回答 3 个问题
- **动机**：Codex 建议把评审升级成"流派 + 人物 + agent 写回"。实地审计发现这些 80% 已有；真正缺的是每个评委的 `time_horizon` / `position_sizing` / `what_would_change_my_mind`
- **关键原则**：**不是给所有人加 3 个同样的字段**，而是每人按自己方法论填 authentic 内容（Buffett 10 年 vs 赵老哥 T+2 vs Simons <2 天）
- **已落地**：`lib/investor_profile.py` 22 人手写 + 7 群 fallback
- **接入**：evaluator.evaluate / _skip_result / _unknown_result 三处返回 · generate_panel 写入 panel.json · assemble_report 新增「🧭 我的方法论」UI 区块
- **回归测试**：
  - `test_investor_profile_authentic_per_persona`（buffett/zhao_lg/simons 必须体现差异）
  - `test_investor_profile_group_fallback`（未注册投资者走 group fallback）
  - `test_evaluator_carries_profile_fields`
  - `test_panel_carries_profile_fields`
- **若未来加/改投资者**：不能把 authentic 人物换成 group fallback（退化）；新增投资者优先加到 PROFILES 而不是只塞进 investor_db
- **若改 panel 输出 schema**：不能删 3 个字段，报告 UI 已依赖

---

## v2.7.3 (2026-04-17 data-source expansion)

### 增强 · 权威域 site: 搜索 + 14 个 Codex 建议源
- **动机**：Codex 建议补"权威媒体 + 官方宏观 + 银行间利率 + 社区舆情"四块源
- **已落地**：14 个 DataSource（cnstock/cs_cn/stcn/nbd/pbc/safe/stats_gov/
  chinamoney/chinabond/ine/guba_em_list/jisilu/fx678/cmc）
- **核心机制**：`lib/web_search.py::search_trusted(query, dim_key=...)` 自动
  prepend `(site:d1 OR site:d2 ...)` 把 ddgs 限定在 dim 对应权威域白名单
- **接入 fetcher**：fetch_policy（全切）/ fetch_macro（部分）/
  fetch_events（权威+通用兜底）/ fetch_moat（权威+通用兜底）
- **不接入**：fetch_trap_signals（需要命中小红书/抖音风险信号，强制权威域
  反而漏；设计上保留现状）· fetch_sentiment（已有按平台 site: 设计）
- **回归测试**：`test_trusted_domains_covers_qualitative_dims` /
  `test_qualitative_fetchers_use_search_trusted` /
  `test_registry_contains_codex_authority_sources`
- **若未来改 web_search**：保持 TRUSTED_DOMAINS_BY_DIM 覆盖至少 5 个核心
  定性维度（3_macro/13_policy/15_events/14_moat/17_sentiment）
- **若未来改 registry**：cnstock/cs_cn/stcn/nbd/pbc/safe/stats_gov/chinabond/
  ine/guba_em_list 10 个权威源不得删除

---

## v2.7.2 (2026-04-17 hotfix)

### BUG#R7 · HK `1_financials` 永远空（stub 从未实现）
- **症状**：所有港股 `1_financials` 返回 `data={}`；ROE / 营收 / 净利 /
  毛利率 / 负债率 / ROIC 全缺；agent 盲评 → 报告完整性掉到 56%
- **位置**：`scripts/fetch_financials.py::main` HK 分支
- **根因**：旧代码 `else: data = {}`（HK 走这里），注释承认 "akshare has
  stock_financial_hk_abstract but field names differ" 但 stub 从未补上
- **修法**：新 `_fetch_hk(ti)` 调用 `ak.stock_financial_hk_analysis_indicator_em`，
  把 ROE_AVG / ROE_YEARLY / ROIC_YEARLY / OPERATE_INCOME / HOLDER_PROFIT /
  DEBT_ASSET_RATIO / CURRENT_RATIO / GROSS_PROFIT_RATIO + YoY 映射到 A 股
  一致的字段；额外保留 HK 特有 `eps` / `bps` / `currency`
- **验证**：`00700.HK` → `roe=21.1%` · `roe_history=[28.1, 29.8, 24.6, 15.1, 21.8, 21.1]` ·
  `revenue_history` 6 年亿元 · `financial_health` 完整
- **若未来改 fetch_financials**：HK 分支必须返回 ROE + 6 年历史，否则
  港股技术面/基本面评委全部盲评

### BUG#R8 · HK 2_kline 只有 1 条路径，GFW 一丢包就 0 根
- **症状**：港股 `kline_count=0`、`stage='—'`、所有技术指标 None；
  `ds.fetch_kline` 在东财 push2his 被代理丢包时直接失败无兜底
- **位置**：`scripts/lib/data_sources.py::_fetch_kline_impl` HK 分支
- **根因**：HK 只有 `ak.stock_hk_hist` 一条路径；A 股已有 6 路 fallback 链，
  但 HK 从未对齐
- **修法**：新 `_kline_hk_chain()` 三层 fallback：
  1. `ak.stock_hk_hist`（东财 push2）
  2. `ak.stock_hk_daily`（新浪, 返 5366 rows IPO-至今）
  3. `yfinance 0700.HK`（海外兜底；自动 `00700` → `700.HK`）
  所有路径返回结果归一到东财中文列（日期/开盘/收盘/最高/最低/成交量）
- **验证**：mock 东财失败后 Sina fallback 正常返 561 rows, stage='Stage 1 底部'
- **若未来改 HK kline**：必须保留至少 2 路以上 fallback；返回前归一到中文列

### BUG#R9 · Wave2 结束未 flush，timeout 标记会丢
- **症状**：跑完 465s 后 `raw_data.json` 里某维度**完全消失**（不是 OK 也不是
  timeout），agent 无法辨别"没跑过"还是"跑挂了"
- **位置**：`scripts/run_real_test.py::collect_raw_data` wave2 末尾
- **根因**：`_persist_progress()` 每 3 个 fetcher 落盘一次；wave2 整体 300s
  超时后把未完成 fetcher 标记 `_timeout=True` 写入 `dims` **仅在内存**；
  wave3 再跑 160s 期间若 Ctrl+C / crash，wave2 的 timeout 标记全丢
- **修法**：wave2 结束立即 `_persist_progress()` + stage1 收尾再 flush 一次。
  raw_data 始终反映最新完整状态。
- **若未来改 wave2/wave3**：任何新 wave 结束必须强制 flush，不要指望增量
  持久化覆盖 wave 结束的关键状态

---

## v2.7.1 (2026-04-17 hotfix)

### BUG#R5 · 19_contests xueqiu_cubes 全空（XueQiu 登录政策变化）
- **症状**：实盘比赛维度始终 0 个 cube，无任何雪球组合显示
- **根因**：`xueqiu.com/cubes/cubes_search.json` 2026 年起强制登录，HTTP 直访
  返 `400 + error_code: "400016"`（"遇到错误，请刷新页面或者重新登录"）
- **修法**：
  - 新 `lib/xueqiu_browser.py` Playwright + 持久化 cookie
  - `fetch_contests` HTTP fail → 检查 UZI_XQ_LOGIN → Playwright fallback
  - 未登录 → 透明标 `_login_required: True` + commentary 显示"⚠️ XueQiu 需登录"
  - run.py 加 `--enable-xueqiu-login` flag，README 说明登录步骤
- **回归测试**：`test_no_regressions.py::test_contests_login_required_marked`
- **若未来改 fetch_contests**：必须保留 `xueqiu_meta.login_required` 标记

### BUG#R6 · 18_trap signals 全 0（ddgs cache 残留）
- **症状**：杀猪盘 8 信号扫描永远命中 0/8（`signals_hit_count: 0`）
- **根因**：v2.6.1 之前 ddgs 未装时 `_ddg_search` 返 [] 被 cache 缓存了 12h；
  装 ddgs 后 cache 仍有效 → 永远返空
- **修法**：清 `.cache/_global/api_cache/ws__*.json` cache（一次性）
  + 改 `_auto_summarize_dim` 让 18_trap 显示 "已扫 ddgs 24 条搜索结果" 透明状态
- **若未来 lib/web_search 改依赖**：必须 bump cache_key_prefix 强制失效

---

## v2.7.0 (2026-04-17)

### BUG#R1 · `detect_style` 漏掉负 ROE 的困境股
- **症状**：ST 股（roe_5y_min < 0）被错判为 `small_speculative`（小盘投机），不是 `distressed`（困境反转）
- **位置**：`lib/stock_style.py:detect_style` 第 1 个判定分支
- **根因**：旧条件 `0 < roe_5y_min < 5` 排除了负值
- **修法**：改为 `roe_5y_min < 5`（去掉下界，允许负值）
- **回归测试**：`test_no_regressions.py::test_distressed_negative_roe`
- **若未来改 detect_style**：必须保留"负 ROE 也是困境"逻辑

### BUG#R2 · `fund_managers` 只显示 6 个（v2.4 修复后又出现的"假回归"）
- **症状**：报告里只显示 6 个基金经理，即便股票被几百家基金持有
- **位置**：`run_real_test.py:_fund_holders` 函数（wave3）
- **根因**：v2.4 把 `fetch_fund_holders.main()` 默认 limit 改成 None，但调用方
  `run_real_test.py:264` 一直写死 `limit=6` —— 修改 fetcher 默认值不会影响显式传参
- **修法**：把 `limit=6` 改为 `limit=None`
- **回归测试**：`test_no_regressions.py::test_fund_managers_no_cap`
- **若未来改 wave3 fetcher**：默认 limit 必须保持 None，render 端已支持 >6 紧凑展开

### BUG#R4 · fetch_fund_holders 并行调 akshare 触发 mini_racer V8 crash
- **症状**：Py3.13 macOS 跑 `fetch_fund_holders.main()` 默认 workers=3 → 致命 crash
  `Check failed: !pool->IsInitialized()`
- **根因**：v2.6 给 `_MINI_RACER_FETCHERS` 加了锁，但 fetch_fund_holders 不在
  wave2 列表里（它是 wave3 + 内部自己开 ThreadPoolExecutor）。其内部并行调
  `ak.fund_open_fund_info_em` 触发 mini_racer 同样问题。
- **修法**：fetch_fund_holders 默认 `UZI_FUND_WORKERS=1`（serial）；同样修
  `lib/quant_signal.py` 内部并发 → 默认 `UZI_QUANT_WORKERS=1`
- **若未来引入新模块调 akshare fund/portfolio 接口**：必须 default workers=1，
  或显式 import `_MINI_RACER_LOCK`

### BUG#R3 · 数据缺口 agent 没主动补齐就出报告
- **症状**：stage2 完成后直接发链接给用户，没检查 22 维定性 commentary 是否完整
- **位置**：原 SKILL.md 没有"输出前最后核查" 的 HARD-GATE
- **根因**：HARD-GATE-DATAGAPS 要求 agent 补数据，但没说"最后还要再核一遍"
- **修法**：新增 HARD-GATE-FINAL-CHECK，强制 agent 在发链接前打开 synthesis.json
  + raw_data.json 检查覆盖率 / commentary 完整性 / detected_style 合理性
- **若未来改 SKILL.md**：必须保留 FINAL-CHECK 这一节

---

## v2.6.1 (2026-04-17 hotfix)

### BUG · 直跑模式定性维度全空
- **症状**：浙江东方报告里宏观/政策/原材料/期货/事件 5 维 missing
- **根因 1**：`dim_commentary` 的 `dim_labels` 只覆盖 9/22 维
- **根因 2**：fallback 是 "[脚本占位]" 废话
- **根因 3**：`ddgs` 不在 requirements.txt（lib/web_search 静默返 0）
- **修法**：`_auto_summarize_dim` 全 22 维 + `_autofill_qualitative_via_mx` MX/ddgs 兜底 + 加 ddgs 到 requirements.txt
- **回归测试**：`test_no_regressions.py::test_22_dims_all_have_commentary`

---

## v2.6.0 (2026-04-17)

### BUG · KeyError 'skip'（论坛 #2）
- **位置**：`preview_with_mock.py:322`
- **根因**：`sig_dist = {"bullish": 0, "neutral": 0, "bearish": 0}` 漏 'skip' key
- **修法**：加 'skip' + 用 `.get()` 防御
- **回归测试**：`test_no_regressions.py::test_sig_dist_has_skip_key`

### BUG · per-fetcher hang 导致 pipeline 卡死（论坛 #11）
- **位置**：`run_real_test.py:collect_raw_data` ThreadPoolExecutor
- **根因**：`as_completed()` 没 timeout，单 fetcher 网络 hang 卡死整个流水线
- **修法**：`as_completed(futures, timeout=300)` + `fut.result(timeout=90)` + 长尾 fetcher 例外
- **若未来改 collect_raw_data**：必须保持双层 timeout

### BUG · OpenCode 跑到 60% 停止不能续（论坛 #9）
- **修法**：`collect_raw_data(resume=True)` 默认 + 增量保存 + `--no-resume` flag
- **若未来改 stage1**：resume 默认必须 True

### BUG · Python 3.9 `str | None` 语法报错（Codex blocker A）
- **修法**：所有新 .py 文件加 `from __future__ import annotations`
- **回归测试**：`test_no_regressions.py::test_all_modules_import_on_py39`

### BUG · mini_racer V8 thread crash on A 股（Codex blocker B）
- **位置**：`run_real_test.py:run_fetcher`
- **根因**：akshare 的 stock_industry_pe / stock_individual_fund_flow / stock_a_pe_and_pb
  内部用 mini_racer 解 JS 反爬，V8 isolate 不是 thread-safe
- **修法**：`_MINI_RACER_LOCK` 串行化这 3 个 fetcher
- **若未来加新 fetcher**：若它调用 mini_racer 相关 akshare 函数，必须加进 `_MINI_RACER_FETCHERS`

### BUG · 报告 banner 显示 v2.2（Codex blocker C）
- **修法**：`run.py:_get_version()` + `assemble_report.py:_get_plugin_version()` 动态读 plugin.json
- **若未来 bump 版本号**：只改 plugin.json 即可，banner 自动同步

### BUG · render_share_card / render_war_report 缺 main()（Codex blocker E）
- **修法**：`main = render` alias
- **若未来重命名函数**：必须保留 main alias

---

## v2.5.0 (2026-04-17)

### BUG · 港股 11 个 dim 全是 A-only stub
- **修法**：`lib/hk_data_sources.py` 解锁 50+ akshare HK 函数；HK 5 维（basic / peers / capital_flow / events + 原 kline）真实数据
- **若未来改 fetch_*.py**：HK 分支必须独立 try/except，不能让 HK 错误污染 A 股链路

---

## v2.4.0 (2026-04-17)

### BUG · 大佬抓作业 limit=50 截断
- **修法**：`fetch_fund_holders.main(limit=None)` 默认改无上限
- **回归**：v2.7 又因 wave3 调用层写死 `limit=6` 部分回归 → BUG#R2

### BUG · 6 维定性维度无方法论指引
- **修法**：`task2.5-qualitative-deep-dive.md` (~400 行) + HARD-GATE-QUALITATIVE
- **若未来改 SKILL.md**：必须保留 HARD-GATE-QUALITATIVE

### BUG · pip 直接挂掉无国内镜像 fallback
- **修法**：`run.py:check_dependencies` 4 级镜像 fallback
- **若未来改 dependencies**：保持 4 级 fallback 链

---

## v2.3.0 (2026-04-17)

### BUG · 中文名输错（"北部港湾" vs "北部湾港"）解析挂掉、22 fetcher 全炸
- **修法**：`lib/name_matcher.py` Levenshtein + `lib/mx_api.py` MX NLP 三层 fallback
- **若未来改 fetch_basic.py**：name_resolver 必须返回结构化 error，不能 fallback 当 ticker 用

### BUG · 关键字段缺失时 pipeline 不 abort 也不警示
- **修法**：`data_integrity.generate_recovery_tasks` + `_data_gaps.json` + HTML 橙色 banner
- **回归测试**：`test_no_regressions.py::test_data_gaps_banner_renders`

---

## 通用 Don't 清单（任何改动都不能违反）

1. ❌ `sig_dist` 字典少 `skip` key
2. ❌ `as_completed()` 不带 timeout
3. ❌ ThreadPoolExecutor 跑 mini_racer-using fetcher 不加锁
4. ❌ 改 fetcher 默认参数后忘记同步调用层
5. ❌ 加 fund 持仓数据流时硬编码 limit
6. ❌ `dim_commentary` 用 "[脚本占位]" 字符串而不是 raw_data 综合
7. ❌ 写 .py 文件用 `str | None` syntax 但忘 `from __future__ import annotations`
8. ❌ `run.py` banner 硬编码版本号
9. ❌ `lib/web_search` 改用其他依赖但不更新 requirements.txt
10. ❌ 把第一次 stage2 输出当最终报告（必须 agent FINAL-CHECK）

## 流程要求

- 每改 `lib/stock_style.py` 必须跑 `test_no_regressions.py::test_*_style*`
- 每改 `run_real_test.py` 必须跑 `test_no_regressions.py` 全套
- 每改 `lib/data_sources.py` `_fetch_basic_*` 必须 smoke test 三市场
- bump 版本号时 4 个 manifest（`.claude-plugin/`、`.cursor-plugin/`、`package.json`、`.version-bump.json`）必须同步
