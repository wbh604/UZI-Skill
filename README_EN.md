<div align="center">

# 游资 (UZI) Skills

*"51 legendary investors review your stock picks — Buffett and a Chinese day-trader finally sit at the same table."*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://python.org)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.com/product/claude-code)
[![Dimensions](https://img.shields.io/badge/Dimensions-22-brightgreen)]()
[![Investors](https://img.shields.io/badge/Investors-51-orange)]()
[![Methods](https://img.shields.io/badge/Institutional%20Methods-17-red)]()
[![Self-Review](https://img.shields.io/badge/Self--Review-13%20checks-blueviolet)](skills/deep-analysis/scripts/lib/self_review.py)

**A-share / HK / US deep-analysis engine — with first-class Chinese-market coverage Western terminals don't touch. v2.14.0: auto GitHub update check (y/s/n prompt) · v2.13.7: 16 news / futures / market-data sources wired · mechanical self-review gate (13 checks).**

[Install](#install) · [Usage](#usage) · [Why Western Investors Should Care](#-why-western-investors-should-care) · [Jury Panel](#-51-investor-jury) · [Methods](#-17-institutional-methods) · [Self-Review Gate 🆕](#-mechanical-self-review-gate-new-in-v29) · [Screenshots](#-what-the-report-looks-like) · [FAQ](#-faq)

**English** | [中文](README.md)

</div>

---

## 🌏 Why Western Investors Should Care

If you've ever tried to research a Chinese A-share from outside China, you know the pain:
- Bloomberg covers HK and ADRs, but A-share data is thin and the context is missing.
- Reuters / FT give you macro headlines, not per-company fundamentals.
- Anthropic's [financial-services-plugins](https://github.com/anthropics/financial-services-plugins) ships great institutional models (DCF / LBO / Comps) — **US-only**, and gated behind paid FactSet / S&P feeds.
- You end up copy-pasting from Eastmoney through Google Translate, and by the time you've built a DCF in Excel, the name's already moved 8%.

**This plugin fixes the Chinese half of that problem.** It reads A-share / H-share / US markets with the same interface, speaks to 20+ free Chinese data sources (akshare / Eastmoney / XueQiu / CNInfo / HKEXNews / mx妙想 API), and hands Claude enough context to actually reason about a Chinese company — not just translate its ticker.

It's also why this exists: **if legends get Chinese stocks wrong, ordinary investors need every analytical advantage they can get.** Charlie Munger famously loaded up on Alibaba (BABA) through Daily Journal Corp in 2021, then had to cut the position in half in 2022 after a ~70% drawdown. At the 2022 DJCO meeting, [Munger called it "one of the worst mistakes I ever made"](https://www.cnbc.com/2023/02/15/charlie-munger-says-he-regrets-alibaba-investment-one-of-the-worst-mistakes.html) — an estimated nine-figure hit. Even one of the greatest investors of all time underestimated how differently the Chinese regulatory and competitive landscape behaves.

So yes — this plugin helps you understand Chinese names like **Alibaba** (`BABA` / `09988.HK`), **Tencent** (`00700.HK`), **Kweichow Moutai** (`600519.SH`), **CATL** (`300750.SZ`), **BYD** (`002594.SZ`), **Pop Mart** (`09992.HK`), **Pinduoduo** (`PDD`) — the same names that keep showing up in Western portfolios and keep surprising their owners 😉

---

## What It Does

One sentence: give it a ticker, Claude becomes your analyst — pulls **22 dimensions of data**, runs **17 Wall-Street analysis models**, has **51 investors with distinct methodologies** score the stock, and produces a 600 KB Bloomberg-style HTML report.

```
/stock-deep-analyzer:analyze-stock 600519         # Kweichow Moutai (A-share)
/stock-deep-analyzer:analyze-stock 00700.HK       # Tencent (HK)
/stock-deep-analyzer:analyze-stock BABA           # Alibaba ADR
/stock-deep-analyzer:analyze-stock AAPL           # Apple
```

After 5-8 minutes you get:
- **A self-contained HTML report** — opens in any browser, works offline
- **A portrait share card** (1080×1920) for social media
- **A landscape war-report card** (1920×1080)
- **A one-line summary** for chat / Slack / Telegram

---

## 💬 Test Group & Feedback

This is early-stage; forum reports plenty of bugs. If you want to help test or just trade notes, WeChat group QR below (primarily Chinese-speaking — if you prefer English, file issues on GitHub and we'll reply). For the latest features, track the `develop` branch.

<p align="center">
  <img src="docs/screenshots/b9857c297761d9420c45285b4fce2255.jpg" width="300" alt="WeChat group QR code" />
</p>

---

## Install

No matter which agent you use, **one line does it**:

### Claude Code

```
/plugin marketplace add wbh604/UZI-Skill
/plugin install stock-deep-analyzer@uzi-skill
```

Then say `/stock-deep-analyzer:analyze-stock Tencent` or `/stock-deep-analyzer:analyze-stock 00700.HK`.

> ⚠️ **Always use the `stock-deep-analyzer:` namespace prefix**
>
> After install, all skills/commands live under `stock-deep-analyzer:<name>`. Short names (`/analyze-stock`) don't always resolve in every environment — to be safe, always use the full name:
> - `/stock-deep-analyzer:analyze-stock <ticker>`
> - `/stock-deep-analyzer:quick-scan <ticker>`
> - `/stock-deep-analyzer:scan-trap <ticker>`
> - `/stock-deep-analyzer:dcf <ticker>` / `:ic-memo` / `:investor-panel` / `:trap-detector` / ...
>
> Cursor / Gemini CLI / Codex behave the same way — use the full prefixed name.

### Codex

Just tell Codex:

> Please follow https://raw.githubusercontent.com/wbh604/UZI-Skill/main/.codex/INSTALL.md to install UZI-Skill, then deep-analyze Alibaba (BABA).

### OpenClaw / 龙虾

> Install https://github.com/wbh604/UZI-Skill and analyze Tencent (00700.HK) for me.

### Cursor

```
/add-plugin stock-deep-analyzer
```

Then say "analyze BABA".

### Gemini CLI

```bash
gemini extensions install https://github.com/wbh604/UZI-Skill
```

### OpenCode

> Follow https://raw.githubusercontent.com/wbh604/UZI-Skill/main/.opencode/INSTALL.md and analyze Pop Mart (09992.HK).

### Windsurf / Devin / Any Other Agent

Paste this:

> Clone https://github.com/wbh604/UZI-Skill, read `AGENTS.md`, then deep-analyze Alibaba (09988.HK).

### CLI Only

```bash
git clone https://github.com/wbh604/UZI-Skill.git
cd UZI-Skill && pip install -r requirements.txt
python skills/deep-analysis/scripts/run_real_test.py BABA
```

### 📱 Not at your desk?

Tell any agent:

> Analyze 00700.HK in remote mode — generate a public link so I can view it on my phone.

The agent spins up a Cloudflare Tunnel and gives you a `https://xxx.trycloudflare.com` URL.

---

## Usage

### Full deep analysis (5-8 minutes)

```
/stock-deep-analyzer:analyze-stock 600519          # A-share by ticker
/stock-deep-analyzer:analyze-stock 00700.HK        # HK
/stock-deep-analyzer:analyze-stock BABA            # US ADR
/stock-deep-analyzer:analyze-stock AAPL            # US
```

> **Ticker format tips for English users:**
> - A-share: 6-digit + `.SH` (Shanghai) or `.SZ` (Shenzhen) — e.g. `600519.SH`, `002594.SZ`. Bare 6-digit like `600519` also works.
> - HK: 5-digit + `.HK` — e.g. `00700.HK`, `09988.HK`.
> - US: plain symbol — `AAPL`, `BABA`, `PDD`, `NVDA`.
> - Chinese names also resolve: `贵州茅台`, `腾讯控股`. For English input, prefer ticker codes over company names (name-resolution is tuned for Chinese).

### Single-purpose commands

> All commands require the `/stock-deep-analyzer:` prefix for reliable dispatch across environments.

| Command | What It Does |
|---|---|
| `/stock-deep-analyzer:dcf 600519` | DCF valuation · WACC + 5×5 sensitivity table |
| `/stock-deep-analyzer:comps 002273` | Peer comparison · PE / PB percentile ranking |
| `/stock-deep-analyzer:lbo 600519` | LBO stress test · PE-buyer IRR perspective |
| `/stock-deep-analyzer:initiate BABA` | Initiating-coverage report · JPM / GS format |
| `/stock-deep-analyzer:ic-memo BABA` | Investment-committee memo · 3-scenario returns |
| `/stock-deep-analyzer:earnings AAPL` | Earnings beat/miss analysis |
| `/stock-deep-analyzer:catalysts 300750` | Catalyst calendar · next 60 days |
| `/stock-deep-analyzer:thesis 600519` | Investment-thesis tracker · 5 pillars |
| `/stock-deep-analyzer:screen AAPL` | 5 quant screens · value / growth / quality / GARP / short |
| `/stock-deep-analyzer:dd BABA` | Due-diligence checklist · 21 items across 5 workstreams |
| `/stock-deep-analyzer:quick-scan 00700.HK` | 30-second sanity check |
| `/stock-deep-analyzer:panel-only 600519` | Just run the 51-investor jury — no HTML report |
| `/stock-deep-analyzer:scan-trap 600519` | Pump-and-dump / trap detection (8 signals) |
| `/stock-deep-analyzer:segmental-model 300308` | 🆕 Bottom-up segmental revenue model · 3-scenario × 3-year projection · cross-checks top-down DCF |

---

## 🎚️ Three Analysis Depths (new in v2.10.3)

Let users pick how much thinking they want — quick / standard / deep-dive:

```bash
python run.py 600519 --depth lite     # ⚡ Quick read (1-2 min)
python run.py 600519                    # 📊 Standard (5-8 min) · default
python run.py 600519 --depth deep       # 🔬 Institutional (15-20 min)
```

Or via env var:

```bash
export UZI_DEPTH=lite       # or medium / deep
python run.py 600519
```

### Differences

| Aspect | ⚡ **lite** | 📊 **medium** | 🔬 **deep** |
|---|---|---|---|
| **Runtime** | 1-2 min | 5-8 min | 15-20 min |
| **Fetchers** | Core 7 dims | All 22 dims | All 22 + reinforced fallback |
| **Investors** | 10 representatives | 51 full panel | 51 + **Bull-Bear structured debate** |
| **Institutional methods** | DCF only | All 17 | All 17 + **Segmental Build-Up** |
| **ddgs qualitative queries** | **all skipped** (saves tokens) | on-demand · budget 30 | full throttle · budget 60 |
| **fund_holders** | Top 5 with full 5Y stats | Top 20 full + rest as listing | Top 100 full |
| **Self-review gate** | critical blocks | critical blocks · warning ack-able | both block |
| **Token cost (Codex)** | minimal | moderate | maximum |
| **Use case** | Quick glance · boss just asked · preview ETF holdings | Daily deep analysis · writing research | Investment committee memo · pre-position deep dive |

### Auto-downgrade

- **First install** / empty `.cache/_global` → auto-switches to lite (saves cold-start time)
- **Network preflight 3+ domains unreachable** → auto lite (prevents hanging)
- Manual `--depth` always overrides auto-detection

### Picking the right depth

| Question | Recommended |
|---|---|
| "Can I buy this stock?" | `medium` (default) |
| "Give me a verdict in 15 minutes" | `lite` |
| "Prepping for investment committee tomorrow" | `deep` (includes Bull-Bear debate + bottom-up segmental) |
| "I typed an ETF code — system asked me to pick a holding" | `lite` (quick verdict on component) |
| "Codex environment / first install" | Don't worry — auto lite |

### Implicit depth per command

| Command | Implicit depth |
|---|---|
| `/stock-deep-analyzer:quick-scan 600519` | lite |
| `/stock-deep-analyzer:panel-only 600519` | lite |
| `/stock-deep-analyzer:analyze-stock 600519` | medium (default) |
| `/stock-deep-analyzer:ic-memo 600519` | deep |
| `/stock-deep-analyzer:initiate 600519` | deep |

---

## 🎭 51 Investor Jury

Not template phrases. Each investor has their own **quantified rule set** (180 rules total) + their own **real quoted voice** + their own **authentic decision profile** (time horizon / position sizing / what-would-change-my-mind).

| Group | Style | Count | Representatives |
|---|---|---|---|
| A | Classic Value | 6 | Buffett · Graham · Munger · Fisher · Templeton · Klarman |
| B | Growth | 4 | Lynch · O'Neil · Thiel · Cathie Wood |
| C | Macro / Hedge | 5 | Soros · Dalio · Howard Marks · Druckenmiller · Julian Robertson |
| D | Technical | 4 | Livermore · Minervini · Darvas · Gann |
| E | China Value | 6 | Duan Yongping (段永平) · Zhang Kun · Zhu Shaoxing · Xie Zhiyu · Feng Liu · Deng Xiaofeng |
| F | A-Share Day Traders (游资) | 23 | Zhang Mengzhu · Zhao Laoge · Foshan Shadowless Kick · Beijing Trader · Xin Duoduo … |
| G | Quant | 3 | Simons · Thorp · David Shaw |

**Every verdict cites the specific rule it hit.** And each investor answers three questions in their own voice:

| Investor | Time Horizon | What Would Change My Mind |
|---|---|---|
| Buffett | 10+ years / forever | ROE below 12% for 2 consecutive years · CEO change + strategic pivot |
| Zhao Laoge (赵老哥) | T+2 to T+5 | Leader breaks the limit-up · volume doesn't confirm |
| Simons | Avg holding < 2 days | Signal Sharpe drops below 0.5 · factor decay |
| Lynch | Until the story plays out, typically 3-5 years | PEG > 2 · inventory growing faster than revenue |
| Soros | One reflexivity cycle, weeks to months, flip anytime | Market stops validating my narrative |

Their quotes are sourced from **real public materials** — Berkshire annual letters, Oaktree memos, *Principles*, *Margin of Safety*, Lost Tree Club speeches, XueQiu / Zhihu columns — each citation links to the original source.

---

## 📐 17 Institutional Methods

Ported from [anthropics/financial-services-plugins](https://github.com/anthropics/financial-services-plugins), adapted with A-share / H-share parameters.

**Valuation (6)**: DCF · Comps · 3-Statement · LBO · Merger Model · Unit Economics

**Research (7)**: Initiating Coverage · Earnings Analysis · Catalyst Calendar · Thesis Tracker · Morning Note · Quant Screen · Sector Overview

**Decision (6)**: IC Memo · Porter 5 Forces + BCG · DD Checklist · Value Creation Plan · Portfolio Rebalance · Trap Detection (unique to this plugin)

---

## 📸 What The Report Looks Like

> All screenshots from a real analysis of Crystal Optech (002273.SZ).

### Score dashboard
<img src="docs/screenshots/hero-score.png" width="700" />

### The Great Divide — Bull vs Bear
<img src="docs/screenshots/great-divide.png" width="700" />

### 51 Jury Seats
<img src="docs/screenshots/jury-seats.png" width="700" />

### Chat-room mode
<img src="docs/screenshots/chat-room.png" width="700" />

### DCF Sensitivity Heatmap
<img src="docs/screenshots/dcf-model.png" width="700" />

### IC Memo — 3 Scenarios
<img src="docs/screenshots/ic-memo.png" width="700" />

### 22-Dimension Deep Cards
<img src="docs/screenshots/deep-scan.png" width="700" />

### Social Share Card
<img src="docs/screenshots/share-card.png" width="300" />

---

## 🔓 Login-Required Data Sources (optional)

Some sources need login to avoid being sampled out. **All are opt-in** — defaults work without any login, just with limited data.

| Source | What It Unlocks | How to Enable |
|---|---|---|
| **XueQiu** (`cubes_search`) | Dim 19 · real-money portfolios holding this stock + their returns | `export UZI_XQ_LOGIN=1 && python -m lib.xueqiu_browser login` (one-time browser prompt; cookies persisted to `~/.uzi-skill/playwright-xueqiu/`). Or use flag: `python run.py BABA --enable-xueqiu-login`. |

If you don't enable, the dim transparently reports `"⚠️ XueQiu login required, 0 cubes shown"` — no silent data holes.

---

## ❓ FAQ

**Q: How long does it take?**
A: 5-8 minutes per stock. Most time is data fetching. Modeling itself is <1 second.

**Q: Do I need paid data sources?**
A: No. All free (akshare / yfinance / DuckDuckGo / CNInfo / HKEXNews / Eastmoney / XueQiu backend). Zero API keys required. Optional `MX_APIKEY` (mx妙想 API) for enhanced A-share indicators — it's free too.

**Q: Does it work for US / HK stocks?**
A: Yes. `/stock-deep-analyzer:analyze-stock AAPL`, `/stock-deep-analyzer:analyze-stock BABA`, `/stock-deep-analyzer:analyze-stock 00700.HK`. HK now has 4-layer kline fallback (Eastmoney → Sina → yfinance → Yahoo Chart v8) since v2.13.7.

**Q: Can I use English company names?**
A: Best: use ticker codes (`BABA` / `00700.HK` / `600519.SH`). Name-resolution works for Chinese names (`贵州茅台` → `600519.SH`); for English names prefer the ticker.

**Q: Does the 51-investor panel quote real investors?**
A: Yes. The `quotes-knowledge-base.md` contains real published quotes from 45+ investors (22 Western, 23 Chinese), each with source URLs (Berkshire letters, Oaktree memos, books, interviews). Agents are instructed to mimic each investor's voice **using these real quotes**, not fabricate a "Buffett-style" line.

**Q: Is this investment advice?**
A: **No.** This is a research tool, not a fortune teller. The 51 investor opinions are rule-engine simulations, not the real people's views. Don't bet the farm on Claude's Buffett impression.

**Q: I'm behind the Great Firewall, will data sources work?**
A: Most do. `akshare` / `yfinance` / Eastmoney / XueQiu all work from mainland China. Some Western sources (Bloomberg / Reuters) aren't used. DuckDuckGo web search occasionally rate-limits — see `docs/NETWORK-TROUBLESHOOTING.md` if the `3_macro` / `13_policy` / `15_events` dims report empty.

**Q: I'm outside China, will Chinese data sources work?**
A: Yes. akshare / Eastmoney / XueQiu / CNInfo / HKEXNews all serve international IPs. No VPN needed. The mx妙想 API (A-share indicators) requires the free `MX_APIKEY` env var.

**Q: How do I know the report I'm about to read is reliable?**
A: As of v2.9, self-review is **mechanically enforced**. 13 automated checks run before HTML generation; if any critical check fails, the report *physically cannot be shipped*. Check `.cache/<ticker>/_review_issues.json` for any warnings, each with a `suggested_fix`. Every time a new BUG is fixed, a matching check is added — so the same class of bug will be **auto-caught next run, no user feedback needed**.

**Q: Does the plugin auto-notify me about new versions?**
A: Yes, since v2.14.0. Every CLI run or agent session silently polls `api.github.com/.../releases/latest`; if a newer tag is out, you get a 3-option prompt (yes / skip-this-version / no) with the release notes summary. "Skip" suppresses the prompt only for that specific tag — once a newer version drops, you'll be asked again. Disable with `export UZI_NO_UPDATE_CHECK=1` (recommended for CI / Codex). Cached 6h to stay under GitHub's 60-req/h unauthenticated limit.

**Q: I ran analyses on earlier versions — were those reports correct?**
A: If you analyzed "industrial metals / machine tools / industrial machinery" stocks (like Yunnan Aluminum / 云铝股份 `000807.SZ`) before 2026-04-17, the `7_industry` dim was misclassified as "agricultural food processing" (BUG#R10). Clear the cache and re-run:
```bash
rm -rf skills/deep-analysis/scripts/.cache/<ticker>/raw_data.json
python run.py <ticker> --no-resume
```

---

## 🛠 Architecture in One Diagram

```
          user says "/analyze-stock BABA"
                       ↓
   ┌──────────────────────────────────────────────┐
   │   Task 1 · Stage1 — parallel data fetch      │
   │   22 fetchers × 20+ sources                  │
   │   (akshare / yfinance / DDG / mx / cninfo …) │
   └──────────────────────────────────────────────┘
                       ↓ raw_data.json
   ┌──────────────────────────────────────────────┐
   │   Task 2 · Rule engine scoring               │
   │   22 dims → dimensions.json                  │
   │   51 investors × 180 rules → panel.json      │
   └──────────────────────────────────────────────┘
                       ↓ HARD-GATE (agent takes over)
   ┌──────────────────────────────────────────────┐
   │   Task 3 · Agent analysis                    │
   │   reads quotes-knowledge-base.md             │
   │   writes agent_analysis.json                 │
   │     (dim_commentary · panel_insights ·       │
   │      great_divide · narrative_override …)    │
   └──────────────────────────────────────────────┘
                       ↓ stage2 merge
   ┌──────────────────────────────────────────────┐
   │   Task 4 · Synthesis · style weighting       │
   │   7+1 stock style × 7 investor-school matrix │
   │   → synthesis.json                           │
   └──────────────────────────────────────────────┘
                       ↓
   ┌──────────────────────────────────────────────┐
   │   🛡 v2.9 · Mechanical self-review gate       │
   │   lib/self_review.py — 13 auto checks         │
   │   critical > 0 → RuntimeError (BLOCK HTML)    │
   │   agent must fix issues → re-review → pass    │
   └──────────────────────────────────────────────┘
                       ↓ only when passed
   ┌──────────────────────────────────────────────┐
   │   Task 5 · Report assembly                   │
   │   → full-report.html (single file, offline)  │
   │   → share-card.png · war-report.png          │
   └──────────────────────────────────────────────┘
```

### 🛡 Mechanical Self-Review Gate (new in v2.9)

Previous versions had soft "HARD-GATE-FINAL-CHECK" — agents could skip, forget, or do half of it. BUG#R10 (a Chinese aluminum producer classified as "agricultural food processing") was caught only after reports were already sent to users. **Soft gates aren't enough — v2.9 enforces mechanically.**

`lib/self_review.py` runs **13 automated checks** before any HTML can be generated. Each check corresponds to a historical BUG:

| severity | check | catches |
|---|---|---|
| 🔴 critical | industry mapping sanity | BUG#R10 collision (工业金属 → 农副食品加工) |
| 🔴 critical | all dims present | wave2 timeout dropped `12_capital_flow` |
| 🔴 critical | HK kline has data | BUG#R8 Hong Kong kline no fallback |
| 🔴 critical | HK financials populated | BUG#R7 empty stub |
| 🔴 critical | panel non-empty, scores sane | panel engine glitches |
| 🔴 critical | coverage_pct ≥ 60% | data integrity floor |
| 🔴 critical | no "[PLACEHOLDER]" strings | template leak |
| 🔴 critical | agent_analysis.json exists & reviewed | agent skipped |
| 🟡 warning | DCF / Comps not all zero | valuation pipeline check |
| 🟡 warning | metal stocks have materials data | v2.8.x coverage gap |
| 🟡 warning | no fabricated narratives (e.g. "Apple supply chain" without evidence) | hallucination guard |

`assemble_report::assemble()` runs `review_all(ticker)` automatically. If `critical_count > 0`, it raises `RuntimeError` — **physically impossible to ship a bad report**. Agent must:

```
loop:
  1. python review_stage_output.py <ticker>
  2. read .cache/<ticker>/_review_issues.json
  3. for each critical: execute suggested_fix (backfill, refetch, override)
  4. re-run review
  5. only when critical_count == 0 → HTML generation proceeds
```

Every time a new BUG is fixed, a matching `check_*` rule is added to self_review. The same bug class will be **automatically caught on the next run, without needing user feedback.**

---

## ⭐ Star History

Live count: ![GitHub Repo stars](https://img.shields.io/github/stars/wbh604/UZI-Skill?style=social)

<a href="https://star-history.com/#wbh604/uzi-skill&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=wbh604/uzi-skill&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=wbh604/uzi-skill&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=wbh604/uzi-skill&type=Date" />
 </picture>
</a>

> Note: star-history.com caches server-side for 24h, so the chart may lag during fast-growth days. For the true current count, see the shields.io badge above — or click the chart to open the live star-history.com page (that triggers a backend refresh).

---

## ⚠️ Disclaimer

This tool generates analysis reports using AI models on public data. All scores, recommendations, and simulated commentary are algorithm outputs and do **not** represent any real investor's actual views (even if a quote is real, the scoring around it is simulated). **Not investment advice.** Past performance is not indicative of future results. Charlie Munger still lost money on Alibaba, and he actually read the 10-Q. Invest at your own risk.

---

## Thanks

[Linux.do](https://linux.do/) — "Linux.do is all you need to learn AI." Thanks for the testing community.

---

<div align="center">

MIT License · Made by FloatFu-true · O.o

</div>
