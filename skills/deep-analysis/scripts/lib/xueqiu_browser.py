"""XueQiu (雪球) Playwright fetcher · v2.7.1

XueQiu 已对 cubes_search.json 等 API 加登录鉴权（HTTP 直访返 400/401）。
本模块用 Playwright 驱动真实浏览器 + 持久化 cookie 解决：

第一次运行：
1. 检查持久化目录 `~/.uzi-skill/playwright-xueqiu/` 是否含 XueQiu cookie
2. 若无：弹出有头浏览器窗口让用户手动登录，登录后回车确认
3. 关闭浏览器，cookie 持久化到本地
后续运行：
1. 用持久化 profile 直接打开 XueQiu，cookie 已带
2. 拿到 cubes_search.json 等需登录接口的数据
3. 关闭浏览器

Opt-in only：默认不启动 Playwright（headless 环境会卡）。需用户：
- 设环境变量 `UZI_XQ_LOGIN=1`
- 或 `python run.py {ticker} --enable-xueqiu-login`

不愿登录的用户：fetch_contests 看到 401/400 后跳过，标 `_login_required: True`。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PROFILE_DIR = Path.home() / ".uzi-skill" / "playwright-xueqiu"
COOKIE_FILE = PROFILE_DIR / "cookies.json"
LOGIN_URL = "https://xueqiu.com/"
LOGIN_TEST_URL = "https://xueqiu.com/cubes/cubes_search.json?code=SH600519&category=2&count=1&page=1"


def is_login_enabled() -> bool:
    """User must explicitly opt-in (env var or CLI flag)."""
    return os.environ.get("UZI_XQ_LOGIN") == "1"


def _has_valid_cookies() -> bool:
    if not COOKIE_FILE.exists():
        return False
    try:
        cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(cookies, list) or not cookies:
        return False
    # XueQiu auth cookies: xq_a_token / xq_id_token / xq_r_token (need at least xq_a_token)
    has_auth = any(c.get("name") == "xq_a_token" for c in cookies)
    return has_auth


def _save_cookies(context) -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    cookies = context.cookies()
    COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")


def _interactive_login() -> bool:
    """Open headed browser, ask user to login, save cookies. Returns True on success."""
    if not sys.stdin.isatty():
        print("⚠️  XueQiu 登录需要交互式 TTY；当前是非交互环境，跳过。")
        print("   解决：在交互式终端运行一次：")
        print("     UZI_XQ_LOGIN=1 python -m lib.xueqiu_browser login")
        return False
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        print("❌ Playwright 未安装。请运行：pip install playwright && playwright install chromium")
        return False

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print()
    print("━" * 50)
    print("🌐 XueQiu 登录流程（首次需要）")
    print("━" * 50)
    print("即将打开有头 Chrome 窗口。请：")
    print("  1) 在弹出的浏览器里点击 \"登录\" 完成登录（账号密码 / 微信扫码 / 手机短信均可）")
    print("  2) 看到 XueQiu 主页右上角变成你的头像 = 登录成功")
    print("  3) 回到本终端按回车，cookie 会被保存供后续使用")
    input("\n准备好后按回车继续... ")

    with sync_playwright() as p:
        browser_ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR / "chromium-profile"),
            headless=False,
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = browser_ctx.new_page()
        page.goto(LOGIN_URL)

        print("\n浏览器已打开。请完成登录后回到此终端，按回车继续...")
        input()

        # Verify by hitting protected endpoint
        try:
            response = page.goto(LOGIN_TEST_URL, timeout=10000)
            text = page.content()
            ok = response and response.status == 200 and "error_code" not in text
        except Exception:
            ok = False

        if not ok:
            print("⚠️  登录验证失败 — cubes_search.json 仍返回错误。")
            print("   可能：(a) 实际未登录成功 (b) 该接口仍有反爬。Cookie 仍会被保存以便重试。")

        _save_cookies(browser_ctx)
        browser_ctx.close()

    if ok:
        print(f"✅ 登录成功 · cookie 已保存到 {COOKIE_FILE}")
        print(f"   下次跑分析时自动复用，无需再登录。")
        return True
    else:
        print(f"⚠️  cookie 已保存到 {COOKIE_FILE}（但登录可能未生效）")
        return False


def fetch_with_browser(url: str, timeout: int = 15) -> str | None:
    """Use persistent Playwright profile to fetch URL (with login cookies). Returns response text or None."""
    if not is_login_enabled():
        return None
    if not PROFILE_DIR.exists():
        print(f"   ℹ️ XueQiu 未登录 (UZI_XQ_LOGIN=1 但首次需跑 `python -m lib.xueqiu_browser login`)")
        return None
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR / "chromium-profile"),
                headless=True,
                user_agent="Mozilla/5.0 Chrome/124",
            )
            page = ctx.new_page()
            response = page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            text = page.content()
            ctx.close()
            return text
    except Exception as e:
        print(f"   ⚠️ XueQiu Playwright 失败: {type(e).__name__}: {str(e)[:100]}")
        return None


def fetch_cubes_via_browser(xq_symbol: str, limit: int = 50) -> list[dict]:
    """Fetch xueqiu cubes through authenticated Playwright. Empty list on any failure."""
    url = f"https://xueqiu.com/cubes/cubes_search.json?code={xq_symbol}&category=2&count={limit}&page=1"
    text = fetch_with_browser(url, timeout=20)
    if not text:
        return []
    # Playwright wraps JSON in <html><body>{...}</body></html>; strip
    import re
    json_match = re.search(r'\{.*"list".*\}|\{.*"cubes".*\}', text, re.DOTALL)
    if not json_match:
        return []
    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return []
    cubes = data.get("list") or data.get("cubes") or []
    out = []
    for c in cubes:
        if not isinstance(c, dict):
            continue
        out.append({
            "name": c.get("name"),
            "owner": (c.get("owner") or {}).get("screen_name"),
            "symbol": c.get("symbol"),
            "daily_gain": c.get("daily_gain"),
            "monthly_gain": c.get("monthly_gain"),
            "total_gain": c.get("total_gain"),
            "annualized_gain_rate": c.get("annualized_gain_rate"),
            "url": f"https://xueqiu.com/P/{c.get('symbol')}" if c.get("symbol") else None,
            "stocks_count": c.get("stocks_count"),
            "view_rebalancing_count": c.get("view_rebalancing_count"),
        })
    return out


# ─── CLI for one-time login ──
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "login":
        os.environ["UZI_XQ_LOGIN"] = "1"  # ensure enabled for this run
        ok = _interactive_login()
        sys.exit(0 if ok else 1)

    elif cmd == "status":
        print(f"PROFILE_DIR: {PROFILE_DIR}")
        print(f"  exists:        {PROFILE_DIR.exists()}")
        print(f"  cookie file:   {COOKIE_FILE.exists()}")
        print(f"  has valid auth cookie: {_has_valid_cookies()}")
        print(f"  is_login_enabled(): {is_login_enabled()}")
        print()
        print("Setup steps:")
        print(f"  1) export UZI_XQ_LOGIN=1")
        print(f"  2) python -m lib.xueqiu_browser login   # one-time interactive login")
        print(f"  3) python run.py <ticker> --no-browser  # XueQiu cubes will use saved cookies")

    elif cmd == "test":
        sym = sys.argv[2] if len(sys.argv) > 2 else "SH600519"
        os.environ["UZI_XQ_LOGIN"] = "1"
        cubes = fetch_cubes_via_browser(sym, limit=10)
        print(f"Fetched {len(cubes)} cubes for {sym}")
        for c in cubes[:3]:
            print(f"  · {c.get('name')} (owner: {c.get('owner')}) total_gain={c.get('total_gain')}")
    else:
        print(f"Unknown command: {cmd}. Use: status | login | test [SYMBOL]")
