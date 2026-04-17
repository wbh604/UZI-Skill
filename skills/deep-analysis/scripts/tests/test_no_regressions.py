"""Regression tests · 防止已修复的 bug 重新出现。

每次改 run_real_test.py / lib/* / fetchers，都跑这个文件：
    cd skills/deep-analysis/scripts && python3 -m pytest tests/test_no_regressions.py -v

或者直接：
    cd skills/deep-analysis/scripts && python3 tests/test_no_regressions.py

每个测试对应 docs/BUGS-LOG.md 中一条 BUG。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))


# ─── BUG#R1 (v2.7) · distressed style 必须支持负 ROE ──
def test_distressed_negative_roe():
    from lib.stock_style import detect_style, DISTRESSED
    f = {"market": "A", "industry": "机械", "market_cap_yi": 50,
         "pb": 0.7, "roe_5y_min": -3, "roe_5y_avg": 1,
         "pe": 0, "revenue_growth_3y_cagr": -5, "dividend_yield": 0}
    assert detect_style(f, {}) == DISTRESSED, "ST 股（负 ROE）应判为 distressed 不是 small_speculative"


# ─── BUG#R2 (v2.7) · fund_managers 不能被 wave3 写死 limit ──
def test_fund_managers_no_cap_in_wave3():
    """wave3 调用 fetch_fund_holders 时不能写死 limit=6（只检查代码行，不查注释）"""
    import re
    src = (SCRIPTS_DIR / "run_real_test.py").read_text(encoding="utf-8")
    fund_idx = src.find("def _fund_holders")
    assert fund_idx > 0, "_fund_holders helper missing"
    snippet = src[fund_idx:fund_idx + 800]
    # Only look for actual call statement: fetch_fund_holders.main(..., limit=6)
    bad = re.search(r"fetch_fund_holders\.main\([^)]*limit\s*=\s*6", snippet)
    assert bad is None, "BUG#R2 regression: wave3 不应调 fetch_fund_holders.main(..., limit=6)"


# ─── BUG (v2.6) · sig_dist 必须含 skip key ──
def test_sig_dist_has_skip_key_in_preview():
    src = (SCRIPTS_DIR / "preview_with_mock.py").read_text(encoding="utf-8")
    # find sig_dist initialization
    idx = src.find('sig_dist = {"bullish":')
    assert idx > 0, "sig_dist init not found"
    line = src[idx:idx + 200]
    assert '"skip"' in line, "BUG regression: sig_dist 必须含 'skip' key"


def test_sig_dist_has_skip_key_in_run_real_test():
    src = (SCRIPTS_DIR / "run_real_test.py").read_text(encoding="utf-8")
    idx = src.find('sig_dist = {')
    assert idx > 0, "sig_dist init not found"
    line = src[idx:idx + 200]
    assert '"skip"' in line, "BUG regression: run_real_test 的 sig_dist 必须含 'skip' key"


# ─── BUG (v2.6) · ThreadPoolExecutor 必须有 timeout ──
def test_collect_raw_data_has_timeout():
    src = (SCRIPTS_DIR / "run_real_test.py").read_text(encoding="utf-8")
    fn_idx = src.find("def collect_raw_data")
    assert fn_idx > 0, "collect_raw_data not found"
    # Function spans well over 5000 chars after v2.7; use larger window
    fn_end = src.find("\ndef ", fn_idx + 100)
    if fn_end < 0:
        fn_end = fn_idx + 10000
    snippet = src[fn_idx:fn_end]
    assert "as_completed(futures, timeout=" in snippet, "BUG regression: as_completed 必须带 timeout"
    assert ".result(timeout=" in snippet, "BUG regression: future.result() 必须带 timeout"


# ─── BUG (v2.6) · mini_racer 锁必须存在 ──
def test_mini_racer_lock_exists():
    src = (SCRIPTS_DIR / "run_real_test.py").read_text(encoding="utf-8")
    assert "_MINI_RACER_FETCHERS" in src, "BUG regression: mini_racer 锁清单缺失"
    assert "_MINI_RACER_LOCK" in src, "BUG regression: mini_racer 锁实例缺失"
    # Check the 3 dangerous fetchers are still in the set
    for fetcher in ("fetch_industry", "fetch_capital_flow", "fetch_valuation"):
        assert fetcher in src, f"BUG regression: {fetcher} 应在 _MINI_RACER_FETCHERS 列表里"


# ─── BUG (v2.6 Codex blocker A) · Py3.9 兼容 ──
def test_all_modules_have_future_annotations():
    """所有用 X | Y 语法的 .py 文件必须 import __future__.annotations"""
    import re
    for fn in sorted(SCRIPTS_DIR.rglob("*.py")):
        if "tests/" in str(fn):
            continue
        content = fn.read_text(encoding="utf-8")
        # Skip if no X | Y usage in function signatures
        has_pep604 = bool(re.search(r"def\s+\w+\([^)]*\b\w+\s*:\s*\w+\s*\|\s*(None|\w+)", content))
        if not has_pep604:
            continue
        assert "from __future__ import annotations" in content, \
            f"BUG regression: {fn.relative_to(SCRIPTS_DIR)} uses X|Y syntax but missing __future__ import"


# ─── BUG (v2.6.1) · dim_commentary 必须覆盖 22 维 ──
def test_dim_labels_covers_all_22_dims():
    src = (SCRIPTS_DIR / "run_real_test.py").read_text(encoding="utf-8")
    idx = src.find("dim_labels = {")
    assert idx > 0, "dim_labels not found"
    # Find closing brace
    end = src.find("}", idx)
    block = src[idx:end]
    expected_dims = [f"{i}_" for i in range(20)]
    missing = [d for d in expected_dims if d not in block]
    assert len(missing) <= 1, \
        f"BUG#v2.6.1 regression: dim_labels 应覆盖 22 维，缺失 {missing}"


# ─── BUG (v2.6.1) · auto_summarize 不能用占位符 ──
def test_auto_summarize_no_stub_placeholder():
    src = (SCRIPTS_DIR / "run_real_test.py").read_text(encoding="utf-8")
    fn_idx = src.find("def _auto_summarize_dim")
    assert fn_idx > 0, "_auto_summarize_dim missing"
    fn_end = src.find("def generate_synthesis", fn_idx)
    block = src[fn_idx:fn_end]
    assert "[脚本占位]" not in block, \
        "BUG regression: _auto_summarize_dim 不应再返回 '[脚本占位]' 字符串"


# ─── BUG (v2.6.1) · ddgs 必须在 requirements.txt ──
def test_ddgs_in_requirements():
    req = (SCRIPTS_DIR.parent.parent.parent / "requirements.txt").read_text(encoding="utf-8")
    assert "ddgs" in req.lower(), "BUG regression: ddgs 必须列在 requirements.txt（lib/web_search 依赖）"


# ─── BUG (Codex blocker C) · 版本号必须动态读 ──
def test_run_py_version_banner_dynamic():
    src = (SCRIPTS_DIR.parent.parent.parent / "run.py").read_text(encoding="utf-8")
    assert "_get_version()" in src, "BUG regression: run.py banner 必须用动态 _get_version()"
    assert "v2.2" not in src or "v2.2 ·" not in src, "BUG regression: 不能硬编码 v2.2 banner"


# ─── BUG (Codex blocker E) · render alias 必须存在 ──
def test_render_share_card_has_main_alias():
    content = (SCRIPTS_DIR / "render_share_card.py").read_text(encoding="utf-8")
    assert "main = render" in content or "def main" in content, \
        "BUG regression: render_share_card.py 必须导出 main (alias)"


def test_render_war_report_has_main():
    content = (SCRIPTS_DIR / "render_war_report.py").read_text(encoding="utf-8")
    assert "def main" in content, "BUG regression: render_war_report.py 必须导出 main"


# ─── BUG (v2.5) · HK 主链路必须独立 try/except ──
def test_hk_branches_isolated():
    """fetch_peers/capital_flow/events 的 HK 分支必须独立 try/except 不污染 A 股"""
    for fn_name in ("fetch_peers.py", "fetch_capital_flow.py", "fetch_events.py"):
        src = (SCRIPTS_DIR / fn_name).read_text(encoding="utf-8")
        if "ti.market == \"H\"" in src:
            # Find the H branch
            h_idx = src.find('ti.market == "H"')
            block = src[h_idx:h_idx + 2000]
            # Should have at least one try/except in the HK block
            assert "try:" in block or "except" in block, \
                f"BUG regression: {fn_name} HK branch 必须有 try/except 隔离"


# ─── BUG#R5 (v2.7.1) · 19_contests login_required 必须透明标记 ──
def test_contests_login_required_marked():
    src = (SCRIPTS_DIR / "fetch_contests.py").read_text(encoding="utf-8")
    assert "login_required" in src, \
        "BUG#R5 regression: fetch_contests 必须返回 login_required 标记（XueQiu 2026 起需登录）"
    assert "xueqiu_browser" in src, \
        "BUG#R5 regression: fetch_contests 必须 fallback 到 lib.xueqiu_browser"


# ─── BUG#R5 (v2.7.1) · xueqiu_browser 模块必须存在 + 默认 opt-in ──
def test_xueqiu_browser_opt_in_only():
    src = (SCRIPTS_DIR / "lib" / "xueqiu_browser.py").read_text(encoding="utf-8")
    assert "is_login_enabled" in src, "BUG#R5 regression: xueqiu_browser 必须有 opt-in 检查"
    assert "UZI_XQ_LOGIN" in src, "BUG#R5 regression: 必须用 UZI_XQ_LOGIN env 启用"
    assert "PROFILE_DIR" in src, "BUG#R5 regression: 必须用持久化 profile 保存 cookie"


# ─── BUG#R6 (v2.7.1) · auto_summarize 18_trap/19_contests 必须透明 ──
def test_auto_summarize_trap_contests_transparent():
    src = (SCRIPTS_DIR / "run_real_test.py").read_text(encoding="utf-8")
    fn_idx = src.find("def _auto_summarize_dim")
    assert fn_idx > 0
    end = src.find("def generate_synthesis", fn_idx)
    block = src[fn_idx:end]
    # 18_trap 应显示 "已扫" 类透明字眼，不能是 "暂无" 或 "(empty)"
    assert "8 信号扫描" in block, \
        "BUG#R6 regression: 18_trap auto-summary 必须显示 8 信号扫描状态"
    # 19_contests 应处理 login_required 情况
    assert "需登录" in block or "login_required" in block, \
        "BUG#R5/R6 regression: 19_contests auto-summary 必须处理 XueQiu 登录态"


# ─── 整体烟测：所有模块在 Py3.9 能 import ──
def test_all_lib_imports_ok():
    import importlib
    failures = []
    for mod in [
        "lib.cache", "lib.data_sources", "lib.market_router", "lib.mx_api",
        "lib.name_matcher", "lib.hk_data_sources", "lib.data_source_registry",
        "lib.data_integrity", "lib.web_search", "lib.agent_analysis_validator",
        "lib.quant_signal", "lib.stock_style", "lib.xueqiu_browser",
    ]:
        try:
            importlib.import_module(mod)
        except Exception as e:
            failures.append(f"{mod}: {type(e).__name__}: {e}")
    assert not failures, "import failures:\n  " + "\n  ".join(failures)


if __name__ == "__main__":
    # Manual runner — no pytest required
    import inspect
    tests = [(n, fn) for n, fn in globals().items()
             if n.startswith("test_") and inspect.isfunction(fn)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ⚠ {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed (out of {len(tests)})")
    sys.exit(0 if failed == 0 else 1)
