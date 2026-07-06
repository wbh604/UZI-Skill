from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def _clear_proxy_env(monkeypatch):
    for key in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
        "UZI_PROXY_MODE", "UZI_PROXY_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_proxy_router_auto_uses_local_proxy_and_bypasses_domestic(monkeypatch):
    import lib.net_proxy_router as router

    _clear_proxy_env(monkeypatch)
    monkeypatch.setattr(router, "_detect_local_http_proxy", lambda: "http://127.0.0.1:7897")

    result = router.configure_proxy_routing()

    assert result["mode"] == "auto"
    assert result["proxy_url"] == "http://127.0.0.1:7897"
    assert result["configured_proxy"] is True
    assert result["configured_no_proxy"] is True
    assert router.os.environ["HTTP_PROXY"] == "http://127.0.0.1:7897"
    assert router.os.environ["HTTPS_PROXY"] == "http://127.0.0.1:7897"
    no_proxy = router.os.environ["NO_PROXY"]
    for domain in ("eastmoney.com", ".eastmoney.com", "cninfo.com.cn", "xueqiu.com", "localhost", "127.0.0.1"):
        assert domain in no_proxy


def test_proxy_router_respects_off_mode(monkeypatch):
    import lib.net_proxy_router as router

    _clear_proxy_env(monkeypatch)
    monkeypatch.setenv("UZI_PROXY_MODE", "off")
    monkeypatch.setattr(router, "_detect_local_http_proxy", lambda: "http://127.0.0.1:7897")

    result = router.configure_proxy_routing()

    assert result["mode"] == "off"
    assert "HTTP_PROXY" not in router.os.environ
    assert "NO_PROXY" not in router.os.environ


def test_fetch_peers_opt_in_uses_direct_eastmoney_before_static(monkeypatch):
    import pandas as pd
    import fetch_peers

    monkeypatch.setenv("UZI_PEERS_TRY_AK", "1")
    monkeypatch.setattr(fetch_peers, "fetch_basic_fast", lambda _ti: {
        "code": "600036.SH",
        "name": "招商银行",
        "industry": "银行",
        "pe_ttm": 5.9,
        "pb": 0.79,
    })
    monkeypatch.setattr(fetch_peers, "_eastmoney_industry_cons_direct", lambda _industry: pd.DataFrame([
        {"代码": "600036", "名称": "招商银行", "总市值": 735699370371.0, "市盈率-动态": 5.9, "市净率": 0.79},
        {"代码": "601398", "名称": "工商银行", "总市值": 2000000000000.0, "市盈率-动态": 6.1, "市净率": 0.62},
    ]))
    monkeypatch.setattr(
        fetch_peers.ak,
        "stock_board_industry_cons_em",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("akshare should not run after direct Eastmoney succeeds")),
    )

    result = fetch_peers.main("600036.SH")

    assert result["fallback"] is False
    assert "eastmoney:29.push2" in result["source"]
    assert result["data"]["peer_table"][0]["name"] == "招商银行"
    assert any(row["name"] == "工商银行" for row in result["data"]["peer_table"])


def test_capital_flow_uses_http_direct_before_akshare(monkeypatch):
    import fetch_capital_flow as fcf

    monkeypatch.setattr(fcf, "_fetch_main_fund_flow_http", lambda _ti: [
        {"日期": "2026-07-03", "主力净流入-净额": 10000.0}
    ])
    monkeypatch.setattr(
        fcf.ak,
        "stock_individual_fund_flow",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("akshare should not run after HTTP direct succeeds")),
    )

    result = fcf.main("600036.SH")

    assert result["data"]["main_fund_flow_20d"] == [{"日期": "2026-07-03", "主力净流入-净额": 10000.0}]
    assert result["data"]["_skipped_universe_heavy"] is True
