"""Regression tests for v2.13.0 · Playwright 分级兜底策略.

按三档 AnalysisProfile:
- lite: playwright_mode='off' · 永远禁用
- medium: playwright_mode='opt-in' · UZI_PLAYWRIGHT_ENABLE=1 才启用 · 未装只打命令
- deep: playwright_mode='default' · 自动启用 · 未装 y/n 交互装

全测试 mock 真实 Playwright · 零真实浏览器依赖.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def _reset_env():
    for k in ("UZI_DEPTH", "UZI_LITE", "UZI_PLAYWRIGHT_ENABLE"):
        os.environ.pop(k, None)


def _reload_all():
    """重新加载 profile + playwright_fallback（env 变动后）."""
    import lib.analysis_profile as ap
    import lib.playwright_fallback as pf
    importlib.reload(ap)
    importlib.reload(pf)
    return ap, pf


# ─── Profile 字段三档默认值 ──────────────────────────────────────

def test_profile_has_playwright_fields():
    """AnalysisProfile 必须有 playwright_mode + playwright_dims 字段."""
    _reset_env()
    ap, _ = _reload_all()
    for depth in ("lite", "medium", "deep"):
        p = ap.get_profile(depth)
        assert hasattr(p, "playwright_mode"), f"{depth} profile 缺 playwright_mode"
        assert hasattr(p, "playwright_dims"), f"{depth} profile 缺 playwright_dims"


def test_lite_profile_disables_playwright():
    _reset_env()
    ap, _ = _reload_all()
    p = ap.get_profile("lite")
    assert p.playwright_mode == "off"
    assert p.playwright_dims == frozenset()


def test_medium_profile_opt_in():
    """v2.13.1 · medium 6 维（扩展自 v2.13.0 的 4 维）."""
    _reset_env()
    ap, _ = _reload_all()
    p = ap.get_profile("medium")
    assert p.playwright_mode == "opt-in"
    assert len(p.playwright_dims) == 6
    expected = {"4_peers", "8_materials", "15_events", "17_sentiment",
                "7_industry", "14_moat"}
    assert p.playwright_dims == expected
    # deep-only 维度不在 medium
    assert "3_macro" not in p.playwright_dims
    assert "13_policy" not in p.playwright_dims
    assert "18_trap" not in p.playwright_dims
    assert "19_contests" not in p.playwright_dims


def test_deep_profile_default_on():
    """v2.13.1 · deep 全 10 维覆盖."""
    _reset_env()
    ap, _ = _reload_all()
    p = ap.get_profile("deep")
    assert p.playwright_mode == "default"
    assert len(p.playwright_dims) == 10
    expected = {"4_peers", "8_materials", "15_events", "17_sentiment",
                "7_industry", "14_moat", "3_macro",
                "13_policy", "18_trap", "19_contests"}
    assert p.playwright_dims == expected


def test_medium_dims_subset_of_deep():
    """medium 维度必须是 deep 的子集（deep 不能比 medium 少）."""
    _reset_env()
    ap, _ = _reload_all()
    medium = ap.get_profile("medium").playwright_dims
    deep = ap.get_profile("deep").playwright_dims
    assert medium.issubset(deep), "medium dims must be subset of deep"
    assert len(deep) > len(medium), "deep 应比 medium 覆盖更多维度"


# ─── is_playwright_enabled 三档行为 ───────────────────────────────

def test_is_enabled_false_in_lite():
    _reset_env()
    os.environ["UZI_DEPTH"] = "lite"
    _, pf = _reload_all()
    assert pf.is_playwright_enabled() is False


def test_is_enabled_false_in_medium_without_env():
    _reset_env()
    os.environ["UZI_DEPTH"] = "medium"
    _, pf = _reload_all()
    assert pf.is_playwright_enabled() is False


def test_is_enabled_true_in_medium_with_env():
    _reset_env()
    os.environ["UZI_DEPTH"] = "medium"
    os.environ["UZI_PLAYWRIGHT_ENABLE"] = "1"
    _, pf = _reload_all()
    assert pf.is_playwright_enabled() is True
    _reset_env()


def test_is_enabled_true_in_deep_always():
    _reset_env()
    os.environ["UZI_DEPTH"] = "deep"
    _, pf = _reload_all()
    # deep 永远 True · 不需要 env
    assert pf.is_playwright_enabled() is True
    _reset_env()


# ─── ensure_playwright_installed 安装策略 ─────────────────────────

def test_ensure_installed_returns_true_if_all_present():
    """playwright 包 + chromium 都装了 → 直接 True，不跑 pip."""
    _reset_env()
    _, pf = _reload_all()
    with patch.object(pf, "_is_playwright_pkg_installed", return_value=True), \
         patch.object(pf, "_is_chromium_installed", return_value=True):
        assert pf.ensure_playwright_installed(auto=False) is True
        assert pf.ensure_playwright_installed(auto=True) is True


def test_ensure_installed_non_auto_only_prints_hint():
    """medium opt-in 模式：未装时只打印命令，不跑 subprocess."""
    _reset_env()
    _, pf = _reload_all()
    with patch.object(pf, "_is_playwright_pkg_installed", return_value=False), \
         patch.object(pf, "_is_chromium_installed", return_value=False), \
         patch.object(pf, "_pip_install_playwright") as mock_pip, \
         patch.object(pf, "_install_chromium_browser") as mock_chr:
        result = pf.ensure_playwright_installed(auto=False)
        assert result is False
        mock_pip.assert_not_called()  # 不自动跑 pip
        mock_chr.assert_not_called()


def test_ensure_installed_auto_mode_calls_pip_and_chromium():
    """deep default 模式：未装时交互确认后自动装."""
    _reset_env()
    _, pf = _reload_all()
    with patch.object(pf, "_is_playwright_pkg_installed", side_effect=[False, True, True]), \
         patch.object(pf, "_is_chromium_installed", side_effect=[False, False, True]), \
         patch.object(pf, "_confirm_install_interactive", return_value=True) as mock_confirm, \
         patch.object(pf, "_pip_install_playwright", return_value=True) as mock_pip, \
         patch.object(pf, "_install_chromium_browser", return_value=True) as mock_chr:
        result = pf.ensure_playwright_installed(auto=True)
        assert result is True
        mock_confirm.assert_called_once()
        mock_pip.assert_called_once()
        mock_chr.assert_called_once()


def test_ensure_installed_respects_user_decline():
    """用户 y/n 选 n → 跳过安装，返 False · 不 raise."""
    _reset_env()
    _, pf = _reload_all()
    with patch.object(pf, "_is_playwright_pkg_installed", return_value=False), \
         patch.object(pf, "_is_chromium_installed", return_value=False), \
         patch.object(pf, "_confirm_install_interactive", return_value=False), \
         patch.object(pf, "_pip_install_playwright") as mock_pip:
        result = pf.ensure_playwright_installed(auto=True)
        assert result is False
        mock_pip.assert_not_called()  # 用户拒绝了


def test_ensure_installed_graceful_on_chromium_failure():
    """chromium 下载失败 → 返 False · 不 raise."""
    _reset_env()
    _, pf = _reload_all()
    with patch.object(pf, "_is_playwright_pkg_installed", return_value=True), \
         patch.object(pf, "_is_chromium_installed", return_value=False), \
         patch.object(pf, "_confirm_install_interactive", return_value=True), \
         patch.object(pf, "_install_chromium_browser", return_value=False):
        result = pf.ensure_playwright_installed(auto=True)
        assert result is False


# ─── autofill_via_playwright 核心行为 ───────────────────────────

def test_autofill_skipped_when_disabled():
    """is_playwright_enabled False → autofill 立刻返 · 不跑任何 strategy."""
    _reset_env()
    os.environ["UZI_DEPTH"] = "lite"
    _, pf = _reload_all()
    raw = {"dimensions": {"4_peers": {"data": {}}}}
    summary = pf.autofill_via_playwright(raw, "300308.SZ")
    assert summary["enabled"] is False
    assert summary["attempted"] == 0


def test_autofill_respects_dim_whitelist():
    """v2.13.1 · medium 6 维白名单内全被调用 · deep-only 维度（3_macro/18_trap 等）跳过.

    medium profile.playwright_dims = {4_peers, 8_materials, 15_events, 17_sentiment, 7_industry, 14_moat}.
    用 patch.dict(clear=True) 避免真实网络调用。
    """
    _reset_env()
    os.environ["UZI_DEPTH"] = "medium"
    os.environ["UZI_PLAYWRIGHT_ENABLE"] = "1"
    _, pf = _reload_all()

    called_dims = []

    def tracking_strategy(ticker, raw):
        called_dims.append(ticker)
        return None  # 不产生数据 · attempted++ 但 succeeded 不增

    # 所有策略都 mock 成 tracking · 避免真实网络
    mocked_strategies = {k: tracking_strategy for k in pf.DIM_STRATEGIES.keys()}

    with patch.object(pf, "ensure_playwright_installed", return_value=True), \
         patch.dict(pf.DIM_STRATEGIES, mocked_strategies, clear=True):
        # raw 里同时放白名单内 + 白名单外的 dim
        raw = {
            "dimensions": {
                # medium 白名单内 6 维
                "4_peers":      {"data": {}},
                "8_materials":  {"data": {}},
                "15_events":    {"data": {}},
                "17_sentiment": {"data": {}},
                "7_industry":   {"data": {}},
                "14_moat":      {"data": {}},
                # deep-only (medium 白名单外)
                "3_macro":      {"data": {}},
                "13_policy":    {"data": {}},
                "18_trap":      {"data": {}},
                "19_contests":  {"data": {}},
                # 未知 dim
                "99_nonexistent": {"data": {}},
            }
        }
        summary = pf.autofill_via_playwright(raw, "300308.SZ")
    # medium 白名单 6 维 · 都有空 data · 都应 attempted
    # deep-only 4 维 + 99_nonexistent 都在白名单外 · 不调
    assert summary["attempted"] == 6
    assert len(called_dims) == 6
    _reset_env()


def test_autofill_filters_junk_results():
    """Playwright parser 返回垃圾数据 → is_junk_autofill 过滤 · 不写入 data."""
    _reset_env()
    os.environ["UZI_DEPTH"] = "deep"
    _, pf = _reload_all()

    def junk_strategy(ticker, raw):
        return {"core_business": "类型；类型"}  # 已知垃圾模式

    # clear=True 只保留 8_materials · 避免其他 strategy 出真实网络
    with patch.object(pf, "ensure_playwright_installed", return_value=True), \
         patch.dict(pf.DIM_STRATEGIES, {"8_materials": junk_strategy}, clear=True):
        raw = {"dimensions": {"8_materials": {"data": {}}}}
        summary = pf.autofill_via_playwright(raw, "300308.SZ")
    # 垃圾被过滤 · data 不应被写入
    assert "core_business" not in raw["dimensions"]["8_materials"]["data"]
    assert summary["failed"] >= 1
    _reset_env()


def test_autofill_skips_dim_with_existing_data():
    """已有充足真实数据的 dim 不应被 Playwright 覆盖."""
    _reset_env()
    os.environ["UZI_DEPTH"] = "deep"
    _, pf = _reload_all()

    called = []

    def tracking_strategy(ticker, raw):
        called.append(ticker)
        return {"x": "data"}

    # clear=True 避免其他 deep 白名单 dim 走真实网络
    with patch.object(pf, "ensure_playwright_installed", return_value=True), \
         patch.dict(pf.DIM_STRATEGIES, {"4_peers": tracking_strategy}, clear=True):
        # 4_peers 有 4 个非空字段（quality 100%）· 不需要兜底
        raw = {
            "dimensions": {
                "4_peers": {
                    "data": {
                        "peer_table": [{"a": 1}, {"b": 2}],
                        "peer_comparison": [{"c": 3}],
                        "rank": "1/50",
                        "industry": "光模块",
                    },
                    "fallback": False,
                },
            }
        }
        pf.autofill_via_playwright(raw, "300308.SZ")
    # 4_peers 有数据 · 不触发 strategy
    assert called == [], f"已有数据的 dim 不应被重抓，但 strategy 被调用 {len(called)} 次"
    _reset_env()


# ─── v2.13.2 · 数据质量感知 + FORCE flag ──────────────────────────

def test_dim_quality_score_detects_mostly_empty():
    """12 个 key 但 9 个是 "—" → quality 25% → 触发兜底."""
    _, pf = _reload_all()
    mostly_empty = {
        "industry": "通信设备",      # 非空
        "lifecycle": "景气上行",     # 非空
        "growth": "—",
        "tam": "—",
        "penetration": "—",
        "note": "",
        "extra1": None,
        "extra2": "",
        "extra3": "N/A",
        "extra4": [],
        "extra5": {},
        "cninfo_metrics": {"x": 1},  # 非空
    }
    score = pf._dim_quality_score(mostly_empty)
    # 3/12 非空（industry, lifecycle, cninfo_metrics） · 质量 25%
    assert score < 0.5, f"expected quality < 50%, got {score:.0%}"
    needs, _ = pf._dim_needs_fallback({"data": mostly_empty, "fallback": False})
    assert needs is True, "quality 25% 应触发 Playwright 兜底"


def test_dim_quality_score_skips_ignoring_underscore_keys():
    """_前缀诊断字段不计入 quality 分母."""
    _, pf = _reload_all()
    data = {
        "name": "中际旭创",            # 公开 · 非空 · 1/2 = 50%
        "growth": "—",                # 公开 · 空
        "_autofill": {"source": "mx"}, # 诊断 · 不计
        "_debug": "...",              # 诊断 · 不计
    }
    score = pf._dim_quality_score(data)
    assert score == 0.5, f"expected 0.5 (1/2 · 忽略 _ 前缀), got {score}"


def test_autofill_triggers_on_low_quality_data():
    """data 非空但全是 "—" 的维度也应触发 Playwright 兜底（v2.13.2 核心改进）."""
    _reset_env()
    os.environ["UZI_DEPTH"] = "deep"
    _, pf = _reload_all()
    called = []

    def tracking_strategy(ticker, raw):
        called.append(ticker)
        return {"growth_from_playwright": "25%/年"}

    with patch.object(pf, "ensure_playwright_installed", return_value=True), \
         patch.dict(pf.DIM_STRATEGIES, {"7_industry": tracking_strategy}, clear=True):
        raw = {
            "dimensions": {
                "7_industry": {
                    "data": {
                        "industry": "通信设备",
                        "growth": "—",
                        "tam": "—",
                        "penetration": "—",
                        "lifecycle": "—",
                    },
                    "fallback": False,  # 主链标称成功，但 data 全 "—"
                }
            }
        }
        summary = pf.autofill_via_playwright(raw, "300308.SZ")

    assert len(called) == 1, "低质量数据应触发 Playwright（v2.13.2）"
    assert summary["succeeded"] == 1
    # 写入确认
    assert "growth_from_playwright" in raw["dimensions"]["7_industry"]["data"]
    _reset_env()


def test_force_flag_ignores_quality_check():
    """UZI_PLAYWRIGHT_FORCE=1 时即使数据质量高也触发."""
    _reset_env()
    os.environ["UZI_DEPTH"] = "deep"
    os.environ["UZI_PLAYWRIGHT_FORCE"] = "1"
    _, pf = _reload_all()
    called = []

    def tracking_strategy(ticker, raw):
        called.append(ticker)
        return None  # 模拟抓失败

    with patch.object(pf, "ensure_playwright_installed", return_value=True), \
         patch.dict(pf.DIM_STRATEGIES, {"4_peers": tracking_strategy}, clear=True):
        raw = {
            "dimensions": {
                "4_peers": {
                    "data": {
                        "peer_table": [{"a": 1}, {"b": 2}, {"c": 3}, {"d": 4}],
                        "peer_comparison": [{"e": 5}],
                        "rank": "1/50",
                        "industry": "光模块",
                    },
                    "fallback": False,
                }
            }
        }
        pf.autofill_via_playwright(raw, "300308.SZ")
    # FORCE=1 · 即使数据已足也调
    assert len(called) == 1, "FORCE=1 应忽略 quality check"
    _reset_env()


def test_autofill_summary_has_disabled_reason_when_off():
    """lite 档 / medium 未 opt-in → summary.disabled_reason 明确."""
    _reset_env()
    os.environ["UZI_DEPTH"] = "medium"  # opt-in 未设
    _, pf = _reload_all()
    summary = pf.autofill_via_playwright({"dimensions": {}}, "300308.SZ")
    assert summary["enabled"] is False
    assert "opt-in" in summary["disabled_reason"] or "UZI_PLAYWRIGHT_ENABLE" in summary["disabled_reason"]
    _reset_env()

    _reset_env()
    os.environ["UZI_DEPTH"] = "lite"
    _, pf = _reload_all()
    summary = pf.autofill_via_playwright({"dimensions": {}}, "300308.SZ")
    assert summary["enabled"] is False
    assert "off" in summary["disabled_reason"] or "lite" in summary["disabled_reason"]
    _reset_env()


# ─── DIM_STRATEGIES 稳定性 ──────────────────────────────────────

def test_dim_strategies_has_10_entries():
    """v2.13.1 · 全 10 维覆盖（v2.13.0 的 5 维 + v2.13.1 的 5 维）."""
    _reset_env()
    _, pf = _reload_all()
    assert len(pf.DIM_STRATEGIES) == 10
    expected = {
        "4_peers", "8_materials", "15_events", "17_sentiment", "3_macro",
        "7_industry", "14_moat", "13_policy", "18_trap", "19_contests",
    }
    assert set(pf.DIM_STRATEGIES.keys()) == expected


def test_all_parsers_callable_and_return_none_on_empty_html():
    """10 个 parser 都应可调用 · fetch_url 返 None 时 parser 返 None 不抛."""
    _reset_env()
    _, pf = _reload_all()
    # mock fetch_url 返 None（模拟网络失败）
    minimal_raw = {
        "ticker": "300308.SZ",
        "dimensions": {"0_basic": {"data": {"name": "中际旭创", "industry": "通信设备"}}},
    }
    with patch.object(pf, "fetch_url", return_value=None):
        for dim_key, strategy in pf.DIM_STRATEGIES.items():
            result = strategy("300308.SZ", minimal_raw)
            assert result is None, f"{dim_key} parser 应在 fetch_url 返 None 时返 None，got {result}"


# ─── junk_filter 模块 ────────────────────────────────────────────

def test_junk_filter_module_exports_pattern_and_fn():
    """lib/junk_filter.py 必须导出 JUNK_PATTERNS 和 is_junk_autofill_text."""
    from lib import junk_filter
    assert hasattr(junk_filter, "JUNK_PATTERNS")
    assert hasattr(junk_filter, "is_junk_autofill_text")
    assert junk_filter.is_junk_autofill_text("类型；类型") is True
    assert junk_filter.is_junk_autofill_text("真实分析内容") is False


def test_run_real_test_still_has_backward_compat_delegate():
    """run_real_test.py::_is_junk_autofill 保留 BC delegate."""
    import run_real_test
    importlib.reload(run_real_test)
    # _is_junk_autofill 应仍可调用（delegate 到 junk_filter）
    assert run_real_test._is_junk_autofill("类型；类型") is True
    assert run_real_test._is_junk_autofill("真实光模块原材料：光芯片 PCB") is False
