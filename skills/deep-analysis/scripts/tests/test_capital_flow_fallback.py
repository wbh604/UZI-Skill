"""Regression tests for fetch_capital_flow · 主力资金多源兜底.

背景
----
`ak.stock_individual_fund_flow` 走 push2his.eastmoney.com。该域在部分网络
环境会被直接 RST（企业代理 / 运营商 / 境外段），而原实现用
`_safe(lambda: ..., [])` 把异常吞成 `[]`：

  * `main_fund_flow_20d` 静默为空，报告里资金面永远显示「—」；
  * 返回值不带 `error`，pipeline 与 self_review 都无法区分
    「真的没有数据」和「抓取失败」，只能按 critical 处理，
    直接把报告卡在 self-review 阶段出不来。

修复后：东财失败/空 → 回退新浪同口径数据（超大单 + 大单 = 主力），
并把两次尝试的错误合并写入 `main_flow_error`，让下游能正确分级。

全部 mock，不发真实网络请求。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import fetch_capital_flow as fcf  # noqa: E402
from lib.market_router import parse_ticker  # noqa: E402


SINA_PAYLOAD = [
    {
        "opendate": "2026-10-19",
        "trade": "261.70",
        "changeratio": "-0.0293",
        "turnover": "3255420000",
        "r0_net": "100052470.0",
        "r1_net": "197652912.72",
        "r2_net": "-66291757.0",
        "r3_net": "-12345678.0",
    },
    {
        "opendate": "2026-10-16",
        "trade": "269.60",
        "changeratio": "0.01",
        "turnover": "1000000000",
        "r0_net": "-5000000.0",
        "r1_net": "2000000.0",
        "r2_net": "1000000.0",
        "r3_net": "2000000.0",
    },
]


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(payload):
    def _open(req, timeout=15):
        return _FakeResp(payload.encode("utf-8"))
    return _open


# ─── 新浪口径映射 ────────────────────────────────────────────────

def test_sina_main_flow_maps_r0_plus_r1_to_main_net():
    """东财「主力净流入」= 超大单 + 大单；新浪 r0 + r1 与之同口径。"""
    ti = parse_ticker("301377.SZ")
    with patch("urllib.request.urlopen", _fake_urlopen(json.dumps(SINA_PAYLOAD))):
        rows = fcf._sina_main_flow(ti)

    assert len(rows) == 2
    first = rows[0]
    assert first["日期"] == "2026-10-19"
    assert first["主力净流入-净额"] == pytest.approx(100052470.0 + 197652912.72)
    assert first["超大单净流入-净额"] == pytest.approx(100052470.0)
    assert first["大单净流入-净额"] == pytest.approx(197652912.72)
    # 净占比 = 主力净额 / 成交额 * 100
    assert first["主力净流入-净占比"] == pytest.approx(
        (100052470.0 + 197652912.72) / 3255420000 * 100
    )


def test_sina_symbol_prefix_follows_exchange():
    assert fcf._sina_symbol(parse_ticker("301377.SZ")) == "sz301377"
    assert fcf._sina_symbol(parse_ticker("688257.SH")) == "sh688257"


def test_sina_main_flow_returns_empty_on_null_payload():
    ti = parse_ticker("301377.SZ")
    with patch("urllib.request.urlopen", _fake_urlopen("null")):
        assert fcf._sina_main_flow(ti) == []


# ─── 多源编排 ────────────────────────────────────────────────────

def test_fetch_main_flow_prefers_eastmoney_when_available():
    ti = parse_ticker("301377.SZ")

    class _Df:
        def tail(self, n):
            return self

        def to_dict(self, orient):
            return [{"主力净流入-净额": 1.0, "日期": "2026-10-19"}]

        def __len__(self):
            return 1

    with patch.object(fcf.ak, "stock_individual_fund_flow", return_value=_Df()):
        records, source, error = fcf._fetch_main_flow(ti)

    assert source == "akshare:eastmoney"
    assert error is None
    assert records[0]["主力净流入-净额"] == 1.0


def test_fetch_main_flow_falls_back_to_sina_when_eastmoney_raises():
    """push2his 被 RST（ProxyError / RemoteDisconnected）时不应静默返回空。"""
    ti = parse_ticker("301377.SZ")

    with patch.object(
        fcf.ak, "stock_individual_fund_flow", side_effect=ConnectionError("push2his reset")
    ), patch("urllib.request.urlopen", _fake_urlopen(json.dumps(SINA_PAYLOAD))):
        records, source, error = fcf._fetch_main_flow(ti)

    assert source == "sina:MoneyFlow.ssl_qsfx_zjlrqs"
    assert len(records) == 2
    # 东财的失败原因要带出来，便于下游区分「降级」和「真空」
    assert "eastmoney" in (error or "")
    assert "push2his reset" in (error or "")


def test_fetch_main_flow_falls_back_when_eastmoney_returns_empty():
    """akshare 不抛异常但返回空表（例如字段改名/停牌）同样要回退。"""
    ti = parse_ticker("301377.SZ")

    class _Empty:
        def tail(self, n):
            return self

        def to_dict(self, orient):
            return []

        def __len__(self):
            return 0

    with patch.object(fcf.ak, "stock_individual_fund_flow", return_value=_Empty()), \
            patch("urllib.request.urlopen", _fake_urlopen(json.dumps(SINA_PAYLOAD))):
        records, source, _ = fcf._fetch_main_flow(ti)

    assert source == "sina:MoneyFlow.ssl_qsfx_zjlrqs"
    assert len(records) == 2


def test_fetch_main_flow_reports_error_when_all_sources_fail():
    ti = parse_ticker("301377.SZ")

    with patch.object(fcf.ak, "stock_individual_fund_flow", side_effect=OSError("east down")), \
            patch("urllib.request.urlopen", side_effect=OSError("sina down")):
        records, source, error = fcf._fetch_main_flow(ti)

    assert records == []
    assert source is None
    assert "east down" in (error or "")
    assert "sina down" in (error or "")
