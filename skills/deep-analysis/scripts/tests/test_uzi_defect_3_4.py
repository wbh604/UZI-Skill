import os
import pytest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(SCRIPTS, rel), encoding="utf-8") as f:
        return f.read()


def test_fmt_msg_pe_ttm_renders():
    from lib.investor_evaluator import _fmt_msg
    assert _fmt_msg("PE {pe_ttm:.0f} + PB {pb:.1f}", {"pe_ttm": 17.8, "pb": 2.3}) == "PE 18 + PB 2.3"


def test_fmt_msg_missing_degrades_to_qmark():
    from lib.investor_evaluator import _fmt_msg
    out = _fmt_msg("ROE {roe_5y_avg:.1f}%", {})
    assert "{" not in out and "}" not in out
    assert out == "ROE ?%"


def test_fmt_msg_single_brace_interp():
    from lib.investor_evaluator import _fmt_msg
    assert _fmt_msg("热度 {sentiment_heat:.0f}", {"sentiment_heat": 50}) == "热度 50"


def test_criteria_no_double_brace():
    assert "{{" not in _read("lib/investor_criteria.py"), "缺陷3b: 不应残留双花括号"


def test_criteria_no_bare_roe_key():
    assert 'f.get("roe", 0)' not in _read("lib/investor_criteria.py"), "缺陷4: 不应再引用未填充的 roe 键"


def test_stock_features_aliases():
    src = _read("lib/stock_features.py")
    assert 'f["pe_ttm"]' in src
    assert 'f["roe_ttm"]' in src


def test_renderer_roe_field():
    assert "roe_ttm" in _read("lib/pipeline/renderer/financials.py")
