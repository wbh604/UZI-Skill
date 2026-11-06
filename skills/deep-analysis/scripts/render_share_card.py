"""Render the 1080×1920 share-card PNG by Playwright-screenshotting #share-card.

Usage: python scripts/render_share_card.py {ticker}
Requires: pip install playwright
          + 系统 Chrome/Edge（复用本机浏览器），或 playwright install chromium
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[!] playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

from lib.browser_locator import browser_launch_kwargs


def render(ticker: str, selector: str = "#share-card", out_name: str = "share-card.png", scale: int = 2) -> Path:
    date = datetime.now().strftime("%Y%m%d")
    report_dir = Path("reports") / f"{ticker}_{date}"
    html_path = report_dir / "full-report.html"
    if not html_path.exists():
        raise FileNotFoundError(f"{html_path} not found. Run assemble_report.py first.")

    out_path = report_dir / out_name

    with sync_playwright() as p:
        browser = p.chromium.launch(**browser_launch_kwargs())
        ctx = browser.new_context(device_scale_factor=scale, viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.goto(f"file:///{html_path.resolve().as_posix()}")
        page.evaluate("document.fonts && document.fonts.ready")

        # Move the hidden element into the viewport so it can be screenshotted
        page.evaluate(f'''(() => {{
          const el = document.querySelector("{selector}");
          if (!el) return;
          el.style.position = "static";
          el.style.left = "0";
          el.style.top = "0";
        }})()''')

        el = page.locator(selector)
        el.screenshot(path=str(out_path), omit_background=False)
        browser.close()

    print(f"[ok] {out_name}: {out_path}")
    return out_path


# v2.6 · run_real_test.stage2 expects `from render_share_card import main`
# Provide alias so both `render(...)` and `main(...)` work.
main = render


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"
    render(ticker)
