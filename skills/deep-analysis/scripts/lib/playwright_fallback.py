"""Playwright 通用兜底层 · v2.13.0

设计哲学：
- 按三档 AnalysisProfile 分级（lite/medium/deep）· 不搞"一刀切全启用"
- 未装时：deep 交互式 y/n · medium 打印命令让用户自己装 · lite 完全不涉及
- 只抓官方权威页（stats.gov.cn / cninfo / em F10 / 雪球 public 页）· 不抓 UGC 平台
- 所有抓取失败 graceful degrade · 不阻塞主流程

维度策略（post-Codex review 精简）：
- medium opt-in · 4 维：4_peers / 8_materials / 15_events / 17_sentiment
- deep default  · 5 维：上述 4 + 3_macro

被明确排除的：
- 14_moat → 百度百科质量差
- 13_policy → ddgs site: 已够
- 18_trap → 小红书/抖音反爬 + UGC 合规
- 19_contests → lib/xueqiu_browser 专用登录路径已有
- 7_industry → 百度搜索页不是结构化源
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

# ─── 配置 ─────────────────────────────────────────────────────────

UA_PC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 15  # 单次 Playwright 抓取硬上限（秒）

# pip 镜像链（与 run.py::PYPI_MIRRORS 对齐 · 大陆网络兜底）
_PYPI_MIRRORS = (
    ("清华", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    ("阿里云", "https://mirrors.aliyun.com/pypi/simple/"),
    ("中科大", "https://pypi.mirrors.ustc.edu.cn/simple/"),
)


# ─── profile 驱动的启用判断 ───────────────────────────────────────

def is_playwright_enabled() -> bool:
    """按当前 profile 判断 Playwright 兜底是否应启用.

    - lite (off) → 永远 False
    - medium (opt-in) → 需 UZI_PLAYWRIGHT_ENABLE=1
    - deep (default) → 永远 True
    """
    try:
        from lib.analysis_profile import get_profile
        mode = get_profile().playwright_mode
    except Exception:
        return False
    if mode == "off":
        return False
    if mode == "default":
        return True
    # opt-in: 必须 env 显式启用
    return os.environ.get("UZI_PLAYWRIGHT_ENABLE") == "1"


def playwright_dims() -> frozenset[str]:
    """当前 profile 允许 Playwright 兜底的维度白名单."""
    try:
        from lib.analysis_profile import get_profile
        return get_profile().playwright_dims
    except Exception:
        return frozenset()


# ─── 安装检测 + 按需自动装（分档策略） ────────────────────────────

def _is_playwright_pkg_installed() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _is_chromium_installed() -> bool:
    """检测 Playwright 的 Chromium 是否已下载（通过尝试取路径）."""
    if not _is_playwright_pkg_installed():
        return False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
            return exe and Path(exe).exists()
    except Exception:
        return False


def _pip_install_playwright() -> bool:
    """pip install playwright · 先试默认 pypi，失败依次试国内镜像."""
    print("   📦 pip install playwright ...")
    # 默认 pypi
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "playwright"],
        check=False,
    )
    if r.returncode == 0 and _is_playwright_pkg_installed():
        print("   ✓ playwright 包已装（pypi.org）")
        return True
    # 国内镜像 fallback
    for name, url in _PYPI_MIRRORS:
        print(f"   ↪ 试 {name} 镜像...")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "playwright",
             "--index-url", url, "--trusted-host", url.split("/")[2]],
            check=False,
        )
        if r.returncode == 0 and _is_playwright_pkg_installed():
            print(f"   ✓ playwright 包已装（via {name}）")
            return True
    print("   ❌ playwright 包安装失败 · 所有镜像都不通")
    return False


def _install_chromium_browser() -> bool:
    """playwright install chromium · 下载 ~150 MB · stdout 可见."""
    print("   📥 下载 Chromium 浏览器 (~150 MB · 仅首次 · 之后永久复用)...")
    print("      大陆网络可能 3-5 分钟 · 可 Ctrl+C 中断降级")
    r = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=False,
    )
    ok = r.returncode == 0 and _is_chromium_installed()
    if ok:
        print("   ✓ Chromium 下载完成")
    else:
        print("   ❌ Chromium 下载失败 · 跳过 Playwright 兜底")
    return ok


def _confirm_install_interactive() -> bool:
    """deep 档未装时 y/n 询问."""
    if not sys.stdin.isatty():
        # 非 TTY（CI / hooks / pipe）自动接受 · deep 用户选 deep 就是同意
        print("   ℹ️  非交互环境检测到 · deep 模式默认同意安装 Playwright + Chromium")
        return True
    try:
        print("")
        print("   ⚠️  Playwright 未安装 · deep 模式需要浏览器兜底抓取")
        print("   📦 需要下载约 180 MB (playwright 包 + Chromium)")
        print("   · 仅首次 · 之后永久复用 · 可 Ctrl+C 中断")
        ans = input("   是否继续安装？(y/N): ").strip().lower()
        return ans in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print("\n   跳过 Playwright 安装 · 其他兜底仍跑")
        return False


def ensure_playwright_installed(auto: bool) -> bool:
    """检测 Playwright + Chromium 是否可用 · 按 auto 模式决定是否装.

    Args:
        auto: deep 模式 True（交互 y/n 后自动装）· medium 模式 False（只打印命令）

    Returns:
        True: 可用 · False: 不可用（调用方应 graceful degrade）
    """
    pkg_ok = _is_playwright_pkg_installed()
    browser_ok = pkg_ok and _is_chromium_installed()
    if pkg_ok and browser_ok:
        return True

    if not auto:
        # medium opt-in · 只打印命令让用户手动装
        print("   ℹ️  Playwright 未安装（medium 模式 opt-in 不自动装）")
        print("      手动安装命令：")
        print(f"         {sys.executable} -m pip install playwright")
        print(f"         {sys.executable} -m playwright install chromium")
        print("      装完后重跑即可 · 本次分析跳过 Playwright 兜底")
        return False

    # auto 模式（deep 档）· 交互式询问后安装
    if not _confirm_install_interactive():
        return False

    # 装包
    if not pkg_ok:
        if not _pip_install_playwright():
            return False

    # 装 Chromium
    if not _is_chromium_installed():
        if not _install_chromium_browser():
            return False

    return True


# ─── 通用抓取接口 ────────────────────────────────────────────────

def fetch_url(url: str, wait_for: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> str | None:
    """通用 Playwright 抓取 · 返 HTML text 或 None.

    失败静默返 None（调用方 graceful degrade）· 不 raise.

    Args:
        url: 目标页面
        wait_for: CSS selector · 等待元素出现（可选）
        timeout: 秒 · 硬上限
    """
    if not _is_chromium_installed():
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    # 随机 0.5-1.5s sleep（简单反爬风控）
    time.sleep(0.5 + (os.urandom(1)[0] % 100) / 100)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=UA_PC, locale="zh-CN")
            page = ctx.new_page()
            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            if wait_for:
                try:
                    page.wait_for_selector(wait_for, timeout=5_000)
                except Exception:
                    pass  # 元素没出来也返当前 HTML
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        # 不 raise · 让调用方降级
        print(f"   ⚠️  Playwright fetch 失败 {url[:50]}: {type(e).__name__}: {str(e)[:80]}")
        return None


# ─── 维度策略 · 每维 {url_tmpl, parser, needs} ────────────────────

def _strategy_4_peers(ticker: str, raw: dict) -> dict | None:
    """4_peers · 抓雪球 stock 页 · 解析同板块股票名单（复用 v2.12.1 xueqiu parser）."""
    code = ticker.split(".")[0]
    # 代码 → 雪球 symbol
    if code.startswith(("6", "9")):
        xq_sym = f"SH{code}"
    elif code.startswith(("0", "3")):
        xq_sym = f"SZ{code}"
    elif code.startswith(("4", "8")):
        xq_sym = f"BJ{code}"
    elif code.isdigit() and len(code) <= 5:
        xq_sym = f"HK{code.zfill(5)}"
    else:
        xq_sym = code.upper()

    url = f"https://xueqiu.com/S/{xq_sym}"
    html = fetch_url(url, timeout=15)
    if not html:
        return None

    peers: list[dict] = []
    seen: set[str] = set()
    link_pat = re.compile(r'/S/([A-Z]{2}\d{5,6})"[^>]*>([^<]{1,20})</a>', re.IGNORECASE)
    for m in link_pat.finditer(html):
        xq_code = m.group(1).upper()
        name = m.group(2).strip()
        if xq_code.startswith(("SH", "SZ", "BJ")):
            normalized = f"{xq_code[2:]}.{xq_code[:2]}"
        elif xq_code.startswith("HK"):
            normalized = f"{xq_code[2:]}.HK"
        else:
            normalized = xq_code
        if normalized in seen or not name or len(name) < 2:
            continue
        seen.add(normalized)
        peers.append({"name": name, "code": normalized})
        if len(peers) >= 20:
            break

    return {"peer_table_playwright": peers} if peers else None


def _strategy_8_materials(ticker: str, raw: dict) -> dict | None:
    """8_materials · 东财 F10 业务分析页."""
    code = ticker.split(".")[0]
    url = f"https://emweb.securities.eastmoney.com/PC_HSF10/BusinessAnalysis/Index?type=web&code={code}"
    html = fetch_url(url, wait_for=".m_table", timeout=15)
    if not html:
        return None
    # 抽"主营业务" / "原材料" 字段（HTML 会动态加载，正则找文本）
    biz_match = re.search(r"主营业务[：:]\s*([^\n<]{5,200})", html)
    if biz_match:
        return {"core_business_playwright": biz_match.group(1).strip()[:200]}
    return None


def _strategy_15_events(ticker: str, raw: dict) -> dict | None:
    """15_events · 巨潮 cninfo 公告列表."""
    code = ticker.split(".")[0]
    url = f"http://www.cninfo.com.cn/new/disclosure/stock?stockCode={code}"
    html = fetch_url(url, timeout=15)
    if not html:
        return None
    # 抓公告标题（cninfo HTML 公告列表用 .announcement-title class）
    titles = re.findall(r'announcement-title[^>]*>([^<]{5,80})<', html)
    if titles:
        return {"event_titles_playwright": titles[:10]}
    return None


def _strategy_17_sentiment(ticker: str, raw: dict) -> dict | None:
    """17_sentiment · 雪球讨论区页 public · 不需登录."""
    code = ticker.split(".")[0]
    if code.startswith(("6", "9")): xq_sym = f"SH{code}"
    elif code.startswith(("0", "3")): xq_sym = f"SZ{code}"
    else: xq_sym = code
    url = f"https://xueqiu.com/S/{xq_sym}/POST"
    html = fetch_url(url, timeout=15)
    if not html:
        return None
    # 抓最新几条讨论标题
    posts = re.findall(r'"title":"([^"]{5,100})"', html)
    return {"xueqiu_posts_playwright": posts[:8]} if posts else None


def _strategy_3_macro(ticker: str, raw: dict) -> dict | None:
    """3_macro · 统计局 stats.gov.cn 最新宏观 · 仅 deep 启用."""
    url = "https://www.stats.gov.cn/sj/sjjd/"
    html = fetch_url(url, timeout=15)
    if not html:
        return None
    # 抓最新宏观数据快讯标题
    titles = re.findall(r'<a[^>]*href="[^"]*"[^>]*>([^<]{5,60})</a>', html)
    # 过滤掉 nav 菜单噪音（长度太短 / 纯数字）
    clean = [t.strip() for t in titles if len(t.strip()) >= 10 and not t.strip().isdigit()][:10]
    return {"macro_headlines_playwright": clean} if clean else None


def _strategy_7_industry(ticker: str, raw: dict) -> dict | None:
    """7_industry · 百度搜索行业景气度 · 抓第一页 snippet."""
    # 从 raw 取行业名
    basic = ((raw.get("dimensions") or {}).get("0_basic") or {}).get("data") or {}
    industry = basic.get("industry", "") or ""
    if not industry:
        return None
    import urllib.parse
    q = urllib.parse.quote(f"{industry} 行业景气度 增速 市场规模 2026")
    url = f"https://www.baidu.com/s?wd={q}"
    html = fetch_url(url, timeout=15)
    if not html:
        return None
    # 百度搜索结果用 <h3> 标题包装 · 抓最多 10 条
    titles = re.findall(r'<h3[^>]*>\s*<a[^>]*>([^<]{5,80})</a>', html)
    # 抓 body 片段（第一页结果的描述）
    descs = re.findall(r'<span class="content-right_[^"]*">([^<]{10,200})</span>', html)
    if not titles and not descs:
        return None
    return {
        "baidu_search_titles_playwright": [t.strip() for t in titles[:10]],
        "baidu_search_descs_playwright": [d.strip() for d in descs[:5]],
    }


def _strategy_14_moat(ticker: str, raw: dict) -> dict | None:
    """14_moat · 百度百科公司词条 · 抓公司简介/主营/竞争优势字段."""
    basic = ((raw.get("dimensions") or {}).get("0_basic") or {}).get("data") or {}
    name = basic.get("name", "") or ""
    if not name or len(name) < 2:
        return None
    import urllib.parse
    url = f"https://baike.baidu.com/item/{urllib.parse.quote(name)}"
    html = fetch_url(url, timeout=15)
    if not html:
        return None
    # 百度百科用 .basicInfo-item / .lemmaWgt-lemmaTitle-title · 抽公司简介段
    intro_match = re.search(r'<div class="lemma-summary[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    intro = ""
    if intro_match:
        # 去 HTML tag
        intro = re.sub(r'<[^>]+>', '', intro_match.group(1)).strip()[:500]
    # 抽基础信息栏（主营/注册资本/行业等）
    info_pairs = re.findall(
        r'<dt[^>]*class="basicInfo-item[^"]*">([^<]+)</dt>\s*<dd[^>]*class="basicInfo-item[^"]*">([^<]+)</dd>',
        html,
    )
    info = {re.sub(r'\s+', '', k): v.strip()[:100] for k, v in info_pairs[:10]}
    if not intro and not info:
        return None
    return {
        "baike_intro_playwright": intro,
        "baike_basic_info_playwright": info,
    }


def _strategy_13_policy(ticker: str, raw: dict) -> dict | None:
    """13_policy · 证监会 csrc.gov.cn 新闻动态 · 抓最新政策标题."""
    url = "http://www.csrc.gov.cn/csrc/c100028/common_list.shtml"
    html = fetch_url(url, timeout=15)
    if not html:
        return None
    # 证监会 HTML 用 <li> + <a> 结构
    titles = re.findall(r'<a[^>]*title="([^"]{10,100})"', html)
    if not titles:
        titles = re.findall(r'<a[^>]*>([^<]{10,80})</a>', html)
    # 过滤纯 nav 菜单
    clean = [t.strip() for t in titles if not t.strip().isdigit() and "首页" not in t][:15]
    return {"csrc_policy_titles_playwright": clean} if clean else None


def _strategy_18_trap(ticker: str, raw: dict) -> dict | None:
    """18_trap · 小红书搜索 · 查股票名是否被"老师"/"推荐"包装."""
    basic = ((raw.get("dimensions") or {}).get("0_basic") or {}).get("data") or {}
    name = basic.get("name", "") or ""
    if not name or len(name) < 2:
        return None
    import urllib.parse
    # 小红书搜索 + "老师带" / "推荐" 触发词
    q = urllib.parse.quote(f"{name} 老师 推荐")
    url = f"https://www.xiaohongshu.com/search_result?keyword={q}"
    html = fetch_url(url, timeout=15)
    if not html:
        return None
    # 小红书帖子 title
    titles = re.findall(r'"title":"([^"]{5,80})"', html)
    # 命中数（多则风险高）
    clean = [t for t in titles if name in t or "推荐" in t or "老师" in t][:10]
    return {
        "xhs_trap_post_count_playwright": len(clean),
        "xhs_trap_titles_playwright": clean,
    } if clean else None


def _strategy_19_contests(ticker: str, raw: dict) -> dict | None:
    """19_contests · 雪球实盘组合排行榜 · 抓前 10 收益组合."""
    # 雪球组合排行榜（公开，不需要登录）
    url = "https://xueqiu.com/cube/rank/list"
    html = fetch_url(url, timeout=15)
    if not html:
        return None
    # 组合项 JSON 嵌入 HTML · 抽 name + total_gain
    items = re.findall(
        r'"name":"([^"]{3,40})"[^}]*?"total_gain":([\-\d.]+)',
        html,
    )
    if not items:
        return None
    top10 = [
        {"name": name, "total_gain_pct": float(gain) if gain else 0}
        for name, gain in items[:10]
    ]
    return {"xueqiu_contest_top10_playwright": top10}


# 维度 → 策略映射（v2.13.1 · 全 10 维 · 开源研究不受反爬合规限制）
DIM_STRATEGIES: dict[str, Callable] = {
    "4_peers":       _strategy_4_peers,
    "8_materials":   _strategy_8_materials,
    "15_events":     _strategy_15_events,
    "17_sentiment":  _strategy_17_sentiment,
    "3_macro":       _strategy_3_macro,
    # v2.13.1 新增（v2.13.0 Codex review 因反爬合规担心暂排除，用户明确开源研究场景不受限，加回）
    "7_industry":    _strategy_7_industry,
    "14_moat":       _strategy_14_moat,
    "13_policy":     _strategy_13_policy,
    "18_trap":       _strategy_18_trap,
    "19_contests":   _strategy_19_contests,
}


# ─── 入口 · post-fetch 兜底 ──────────────────────────────────────

def _is_empty_value(v) -> bool:
    """判断一个值是否"实质为空"（— / None / 空串 / 空容器）."""
    if v is None:
        return True
    if isinstance(v, str):
        s = v.strip()
        return s in ("", "—", "-", "--", "N/A", "n/a", "None", "null", "TBD")
    if isinstance(v, (list, dict, tuple, set)):
        return len(v) == 0
    return False


def _dim_quality_score(data: dict) -> float:
    """数据质量分数 = 有效值占比（非 "—"/None/空）· 0.0-1.0.

    只统计"公开字段"（不以 `_` 开头的 key · 排除诊断字段）.
    """
    if not isinstance(data, dict) or not data:
        return 0.0
    public_keys = [k for k in data.keys() if not str(k).startswith("_")]
    if not public_keys:
        return 0.0
    valid = sum(1 for k in public_keys if not _is_empty_value(data[k]))
    return valid / len(public_keys)


# v2.13.2 · 数据质量阈值 · 低于此值 → 触发 Playwright 兜底
# 中际旭创实测：7_industry 有 12 keys 但 growth/tam/penetration 都 "—" → quality ~0.25
QUALITY_THRESHOLD = 0.5


def _dim_needs_fallback(dim: dict) -> tuple[bool, str]:
    """判断维度是否需要 Playwright 兜底 · 返 (needs, reason).

    v2.13.2 升级：除了"data 空"判断外，增加"数据质量"判断——
    data 即使非空，但有效字段 < 50% 也触发兜底（解决 "growth=—,tam=—,penetration=—"
    12 keys 但全垃圾"的情况）.
    """
    if not isinstance(dim, dict):
        return True, "dim 非 dict"
    data = dim.get("data")
    if not data or not isinstance(data, dict):
        return True, "data 为空或非 dict"
    # fallback 标记 · 总是需要兜底
    if dim.get("fallback"):
        return True, "主链标 fallback=True"
    # 数据质量检查 · 有效值 < 50%
    q = _dim_quality_score(data)
    if q < QUALITY_THRESHOLD:
        return True, f"有效字段占比 {q:.0%} < {QUALITY_THRESHOLD:.0%}"
    return False, f"有效字段占比 {q:.0%} 已达标"


def autofill_via_playwright(raw: dict, ticker: str) -> dict:
    """post-fetch 兜底 · 对 profile.playwright_dims 里数据不足的维度尝试浏览器抓取.

    在 run_real_test.py::_autofill_qualitative_via_mx 之后调用.

    环境变量：
    - `UZI_PLAYWRIGHT_FORCE=1` · 忽略 `_dim_needs_fallback`，对所有白名单维度强制跑
      （用户发现自动判定太保守时的 kill switch）

    Returns:
        {"enabled": bool, "attempted": int, "succeeded": int, "failed": 0,
         "skipped": int, "skip_reasons": {dim: reason}, "disabled_reason": str}
    """
    summary = {
        "enabled": False, "attempted": 0, "succeeded": 0, "failed": 0,
        "skipped": 0, "skip_reasons": {},
        "disabled_reason": "",
    }

    # ─── 1. 启用检查 · 失败时明确说原因 ───
    try:
        from lib.analysis_profile import get_profile
        profile = get_profile()
    except Exception as e:
        summary["disabled_reason"] = f"profile 加载失败: {e}"
        print(f"   ⚠️  Playwright skip · {summary['disabled_reason']}")
        return summary

    mode = profile.playwright_mode
    if mode == "off":
        summary["disabled_reason"] = f"profile={profile.depth} · playwright_mode=off（lite 档不用浏览器）"
        print(f"   ℹ️  Playwright skip · {summary['disabled_reason']}")
        return summary

    if mode == "opt-in" and os.environ.get("UZI_PLAYWRIGHT_ENABLE") != "1":
        summary["disabled_reason"] = (
            f"profile={profile.depth} · opt-in 未启用 · "
            "export UZI_PLAYWRIGHT_ENABLE=1 启用后重跑"
        )
        print(f"   ℹ️  Playwright skip · {summary['disabled_reason']}")
        return summary

    # ─── 2. 安装检查 · 失败时 graceful degrade ───
    auto_install = (mode == "default")
    if not ensure_playwright_installed(auto=auto_install):
        summary["disabled_reason"] = "Playwright 包或 Chromium 未安装 · 已降级跳过"
        return summary

    summary["enabled"] = True
    dims = raw.get("dimensions", {})
    force = os.environ.get("UZI_PLAYWRIGHT_FORCE") == "1"

    print(f"   🎭 profile={profile.depth} · playwright_dims={len(profile.playwright_dims)}"
          f" · FORCE={force}")

    from lib.junk_filter import is_junk_autofill_text

    for dim_key in sorted(profile.playwright_dims):
        dim = dims.get(dim_key, {})

        if not force:
            needs, reason = _dim_needs_fallback(dim)
            if not needs:
                summary["skipped"] += 1
                summary["skip_reasons"][dim_key] = reason
                print(f"   ⏭  {dim_key:14s} skip · {reason}")
                continue

        strategy = DIM_STRATEGIES.get(dim_key)
        if not strategy:
            summary["skipped"] += 1
            summary["skip_reasons"][dim_key] = "DIM_STRATEGIES 未定义"
            continue

        summary["attempted"] += 1
        try:
            result = strategy(ticker, raw)
        except Exception as e:
            summary["failed"] += 1
            print(f"   ❌ {dim_key:14s} parser 异常: {type(e).__name__}: {str(e)[:80]}")
            continue

        if not result:
            summary["failed"] += 1
            print(f"   ✗ {dim_key:14s} 页面抓取失败或解析无数据")
            continue

        # 过滤垃圾数据
        if is_junk_autofill_text(str(result)):
            summary["failed"] += 1
            print(f"   ✗ {dim_key:14s} 抓到疑似垃圾数据 · 已过滤")
            continue

        # 写入
        data = dim.setdefault("data", {})
        data.update(result)
        dim["source"] = (dim.get("source", "") + " + playwright_fallback").lstrip(" +")
        # 确保 dim 进入 dimensions（如果之前没有）
        dims.setdefault(dim_key, dim)
        summary["succeeded"] += 1
        print(f"   ✓ {dim_key:14s} via playwright · 字段: {', '.join(list(result.keys())[:3])}")

    print(
        f"   📊 Playwright 兜底 · 尝试 {summary['attempted']} · 成功 {summary['succeeded']}"
        f" · 失败 {summary['failed']} · 跳过 {summary['skipped']}（数据已足）"
    )
    return summary
