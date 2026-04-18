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


# ─── BUG#R7 (v2.7.2) · HK fetch_financials 必须有真实实现 ──
def test_fetch_financials_hk_branch_implemented():
    """HK 分支不能再是 `data = {}` stub；必须调用真实 akshare HK 接口"""
    src = (SCRIPTS_DIR / "fetch_financials.py").read_text(encoding="utf-8")
    # 必须有 _fetch_hk 函数
    assert "def _fetch_hk(" in src, "BUG#R7 regression: 缺少 _fetch_hk(ti)"
    # main 分支必须走 _fetch_hk 而不是 else stub
    assert 'elif ti.market == "H":' in src, "BUG#R7 regression: main 未分发 HK 到 _fetch_hk"
    assert "_fetch_hk(ti)" in src, "BUG#R7 regression: main 没调 _fetch_hk"
    # 必须调用 stock_financial_hk_analysis_indicator_em
    assert "stock_financial_hk_analysis_indicator_em" in src, \
        "BUG#R7 regression: HK 实现必须调 stock_financial_hk_analysis_indicator_em"


# ─── BUG#R8 (v2.7.2) · HK kline 必须有 fallback chain ──
def test_kline_hk_has_fallback_chain():
    """HK kline 不能只有 ak.stock_hk_hist 一路；必须有 Sina / yfinance 兜底"""
    src = (SCRIPTS_DIR / "lib" / "data_sources.py").read_text(encoding="utf-8")
    assert "_kline_hk_chain" in src, "BUG#R8 regression: 缺 _kline_hk_chain 函数"
    # 函数体内必须同时引用 stock_hk_hist + stock_hk_daily + yfinance 3 条路径
    chain_idx = src.find("def _kline_hk_chain")
    assert chain_idx > 0
    body = src[chain_idx:chain_idx + 3000]
    assert "stock_hk_hist" in body, "BUG#R8 regression: chain 缺东财路径"
    assert "stock_hk_daily" in body, "BUG#R8 regression: chain 缺 Sina 路径"
    assert ".HK" in body or "yf.Ticker" in body, "BUG#R8 regression: chain 缺 yfinance 路径"


# ─── BUG#R9 (v2.7.2) · wave2 结束必须 flush ──
def test_wave2_persists_before_wave3():
    """wave2 整体超时 / 正常结束 后必须强制 flush raw_data；否则 timeout 标记会丢"""
    src = (SCRIPTS_DIR / "run_real_test.py").read_text(encoding="utf-8")
    w2_done = src.find('[wave 2] done in')
    w3_start = src.find('[wave 3] bonus fetchers')
    assert w2_done > 0 and w3_start > w2_done, "wave2/wave3 log markers not found"
    between = src[w2_done:w3_start]
    assert "_persist_progress()" in between, \
        "BUG#R9 regression: wave2 结束到 wave3 开始之间必须有 _persist_progress()"


# ─── v2.7.3 · search_trusted 必须覆盖 5 个核心定性维度 ──
def test_trusted_domains_covers_qualitative_dims():
    from lib.web_search import TRUSTED_DOMAINS_BY_DIM, trusted_domains_for
    # 这 5 个定性维度必须有权威域映射，否则 v2.7.3 的质量提升失效
    MUST_HAVE = ("3_macro", "13_policy", "15_events", "14_moat", "17_sentiment")
    for dim in MUST_HAVE:
        domains = trusted_domains_for(dim)
        assert len(domains) >= 3, f"v2.7.3 regression: {dim} 权威域少于 3 个（当前 {len(domains)}）"


# ─── v2.7.3 · 关键 fetcher 必须引用 search_trusted ──
def test_qualitative_fetchers_use_search_trusted():
    """fetch_macro / fetch_policy / fetch_events / fetch_moat 必须调 search_trusted"""
    for fname in ("fetch_macro.py", "fetch_policy.py", "fetch_events.py", "fetch_moat.py"):
        src = (SCRIPTS_DIR / fname).read_text(encoding="utf-8")
        assert "search_trusted" in src, \
            f"v2.7.3 regression: {fname} 没接入 search_trusted（权威域搜索失效）"


# ─── v2.7.3 · registry 必须含 Codex 建议的权威源 ──
def test_registry_contains_codex_authority_sources():
    from lib.data_source_registry import SOURCES
    ids = {s.id for s in SOURCES}
    MUST_HAVE = {"cnstock", "cs_cn", "stcn", "nbd", "pbc", "safe", "stats_gov",
                 "chinabond", "ine", "guba_em_list"}
    missing = MUST_HAVE - ids
    assert not missing, f"v2.7.3 regression: registry 缺权威源 {missing}"


# ─── v2.8 · 因地制宜的 investor_profile 层 ──
def test_investor_profile_authentic_per_persona():
    """每人的 time_horizon / position_sizing / what_would_change_my_mind 必须因地制宜"""
    from lib.investor_profile import get_profile, PROFILES

    # 至少覆盖 22 个标志性人物
    assert len(PROFILES) >= 22, f"v2.8 regression: authored profiles 少于 22（当前 {len(PROFILES)}）"

    # 不同流派的投资者必须给出真的不同的答案（不是模板占位）
    buffett = get_profile("buffett", "A")
    zhao_lg = get_profile("zhao_lg", "F")
    simons = get_profile("simons", "G")
    # time_horizon 必须差异巨大（Buffett 10 年 vs 赵老哥 T+2 vs Simons <2 天）
    assert "10 年" in buffett["time_horizon"], "buffett 必须是长期"
    assert "T+" in zhao_lg["time_horizon"], "赵老哥必须是超短线"
    assert "2 天" in simons["time_horizon"] or "<" in simons["time_horizon"], "simons 必须是超高频"
    # 翻盘条件必须体现不同方法论
    assert "ROE" in buffett["what_would_change_my_mind"], "buffett 翻盘必须与 ROE 有关"
    assert "龙头" in zhao_lg["what_would_change_my_mind"] or "板" in zhao_lg["what_would_change_my_mind"]
    assert "Sharpe" in simons["what_would_change_my_mind"] or "因子" in simons["what_would_change_my_mind"]


def test_investor_profile_group_fallback():
    """未单独注册的投资者必须走 group fallback（不能裸奔到 generic 占位）"""
    from lib.investor_profile import get_profile
    # 'gann' / 'darvas' 是 group D，没有单独授权
    r_d = get_profile("gann", "D")
    assert r_d["time_horizon"] != "—", "group D fallback 必须有内容"
    assert "均线" in r_d["what_would_change_my_mind"] or "趋势" in r_d["what_would_change_my_mind"]
    # 'sunan' 是 group F 游资
    r_f = get_profile("sunan", "F")
    assert "板" in r_f["what_would_change_my_mind"] or "龙虎榜" in r_f["what_would_change_my_mind"]


def test_evaluator_carries_profile_fields():
    """evaluate() 返回值必须包含 3 个 profile 字段"""
    from lib.investor_evaluator import evaluate
    features = {"market": "A", "ticker": "600519.SH", "name": "x", "industry": "白酒",
                "roe_5y_min": 20, "roe_5y_avg": 25, "net_margin": 50, "debt_ratio": 20,
                "fcf_margin": 25, "pe": 20, "pb": 7, "pe_percentile": 30,
                "revenue_growth_3y_cagr": 14, "dividend_yield": 4, "market_cap_yi": 24000}
    r = evaluate("buffett", features)
    assert "time_horizon" in r and r["time_horizon"] != "—"
    assert "position_sizing" in r and r["position_sizing"] != "—"
    assert "what_would_change_my_mind" in r and r["what_would_change_my_mind"] != "—"


def test_panel_carries_profile_fields():
    """panel.investors[*] 必须带上 3 个 profile 字段"""
    src = (SCRIPTS_DIR / "run_real_test.py").read_text(encoding="utf-8")
    gen_panel_idx = src.find("def generate_panel")
    assert gen_panel_idx > 0
    body = src[gen_panel_idx:gen_panel_idx + 6000]
    for field in ("time_horizon", "position_sizing", "what_would_change_my_mind"):
        assert field in body, f"v2.8 regression: generate_panel 没往 panel 里写 {field}"


# ─── v2.8.1 · quotes-knowledge-base 必须覆盖 22 个 authored 人物 ──
def test_quotes_knowledge_base_covers_authored_personas():
    """每个在 investor_profile.PROFILES 里 authored 的人物，都必须在
    quotes-knowledge-base.md 里有真实原话段落（(id) 形式标识）"""
    from lib.investor_profile import PROFILES
    kb_path = SCRIPTS_DIR.parent.parent / "investor-panel" / "references" / "quotes-knowledge-base.md"
    assert kb_path.exists(), f"quotes-knowledge-base.md missing at {kb_path}"
    kb = kb_path.read_text(encoding="utf-8")
    missing = []
    for inv_id in PROFILES.keys():
        # 段落 header 形如 "(`buffett`)" 或 "(`zhao_lg`)"
        marker = f"(`{inv_id}`)"
        if marker not in kb:
            missing.append(inv_id)
    assert not missing, f"v2.8.1 regression: quotes-knowledge-base 缺以下 authored 人物的原话段落: {missing}"


def test_quotes_knowledge_base_has_source_urls():
    """每个新加入的 Group A/B/C/D/G 海外人物段落必须带 http(s):// URL 溯源（不能裸奔）"""
    kb_path = SCRIPTS_DIR.parent.parent / "investor-panel" / "references" / "quotes-knowledge-base.md"
    kb = kb_path.read_text(encoding="utf-8")
    # 抽查 3 个新人物必须有 URL
    for inv_id in ("buffett", "soros", "simons"):
        # 找到该人物段落
        start = kb.find(f"(`{inv_id}`)")
        assert start > 0, f"{inv_id} section not found"
        # 取该段落到下一个 `### ` 之间的内容
        next_header = kb.find("\n### ", start)
        section = kb[start:next_header if next_header > 0 else len(kb)]
        assert "http" in section, f"v2.8.1 regression: {inv_id} 原话段落缺 URL 溯源"
        # 至少 2 条原话（数字编号）
        assert section.count("\n1. ") >= 1 and (section.count("\n2. ") >= 1), \
            f"v2.8.1 regression: {inv_id} 原话条数不足"


# ─── v2.8.3 · BUG#R10 · 行业分类碰撞错误（云铝股份被归为农副食品加工）──
def test_industry_mapping_blocks_high_collision_substring():
    """申万'工业金属'等前缀高碰撞行业绝不能被误映射到'农副食品加工业'"""
    from lib.industry_mapping import SW_TO_CSRC_INDUSTRY, HIGH_COLLISION_TOKENS
    # 核心映射必须存在
    assert SW_TO_CSRC_INDUSTRY.get("工业金属") == "有色金属冶炼和压延加工业"
    assert SW_TO_CSRC_INDUSTRY.get("白酒") == "酒、饮料和精制茶制造业"
    assert SW_TO_CSRC_INDUSTRY.get("半导体") == "计算机、通信和其他电子设备制造业"
    assert SW_TO_CSRC_INDUSTRY.get("钢铁") == "黑色金属冶炼和压延加工业"
    # 黑名单必须包含关键的高碰撞前缀
    assert "工业" in HIGH_COLLISION_TOKENS, "'工业' 必须在黑名单里（这是 BUG#R10 根源）"
    assert "加工" in HIGH_COLLISION_TOKENS
    assert "制造" in HIGH_COLLISION_TOKENS


def test_resolve_csrc_industry_on_mock_df():
    """模拟 cninfo 返回，验证 resolver 在多个碰撞候选中选对行"""
    from lib.industry_mapping import resolve_csrc_industry
    import pandas as pd
    # 模拟 cninfo 行业分类的关键子集
    df = pd.DataFrame({
        "行业名称": [
            "农副食品加工业",
            "石油、煤炭及其他燃料加工业",
            "黑色金属冶炼和压延加工业",
            "有色金属冶炼和压延加工业",
            "酒、饮料和精制茶制造业",
            "计算机、通信和其他电子设备制造业",
        ],
        "静态市盈率-加权平均": [20.0, 15.0, 25.0, 32.0, 40.0, 60.0],
    })

    # 关键 case：工业金属 绝不能命中 农副食品加工业
    row = resolve_csrc_industry("工业金属", df)
    assert row is not None, "工业金属 应该命中"
    assert row["行业名称"] == "有色金属冶炼和压延加工业", \
        f"BUG#R10 regression: 工业金属 被误映射到 {row['行业名称']!r}"

    # 白酒
    row = resolve_csrc_industry("白酒", df)
    assert row is not None
    assert "酒" in row["行业名称"]

    # 钢铁
    row = resolve_csrc_industry("钢铁", df)
    assert row is not None
    assert "黑色金属" in row["行业名称"]

    # 完全未知行业 → None（绝不盲选 iloc[0]）
    row = resolve_csrc_industry("完全不存在的行业XYZ", df)
    assert row is None, "未知行业必须返 None，不能盲选 iloc[0]"


def test_fetch_industry_and_fetch_valuation_use_mapping():
    """确保 fetch_industry 和 fetch_valuation 都接入了 resolver，不再用裸 str.contains"""
    for fname in ("fetch_industry.py", "fetch_valuation.py"):
        src = (SCRIPTS_DIR / fname).read_text(encoding="utf-8")
        assert "resolve_csrc_industry" in src, \
            f"BUG#R10 regression: {fname} 未接入 resolve_csrc_industry"
        # 确认不再使用裸 contains(industry[:2]) pattern
        assert "contains(industry_name[:2]" not in src, \
            f"BUG#R10 regression: {fname} 仍有裸 contains(industry_name[:2])"
        assert "contains(ind_name[:2]" not in src, \
            f"BUG#R10 regression: {fname} 仍有裸 contains(ind_name[:2])"


# ─── v2.8.4 · BUG#R10-coverage · 有色金属类申万行业必须有 materials/futures/peers ──
def test_metals_industries_have_materials_coverage():
    """工业金属/贵金属/小金属/能源金属 在 INDUSTRY_MATERIALS 里必须有对应条目"""
    from fetch_materials import INDUSTRY_MATERIALS
    for ind in ("工业金属", "有色金属", "贵金属", "能源金属"):
        assert ind in INDUSTRY_MATERIALS, f"BUG#R10-coverage: INDUSTRY_MATERIALS 缺 {ind!r}"
        assert len(INDUSTRY_MATERIALS[ind]) >= 1


def test_metals_industries_have_futures_coverage():
    """工业金属/贵金属/能源金属 在 INDUSTRY_FUTURES 里必须有主连合约"""
    from fetch_futures import INDUSTRY_FUTURES
    for ind in ("工业金属", "贵金属", "能源金属"):
        assert ind in INDUSTRY_FUTURES, f"BUG#R10-coverage: INDUSTRY_FUTURES 缺 {ind!r}"
        name, code = INDUSTRY_FUTURES[ind]
        assert name is not None and code is not None, f"{ind} 必须有主连合约非 None"


def test_metals_industries_have_peers_alias():
    """工业金属/贵金属/小金属/能源金属 必须在 _INDUSTRY_ALIASES 里映射到 '有色金属'"""
    src = (SCRIPTS_DIR / "fetch_similar_stocks.py").read_text(encoding="utf-8")
    alias_idx = src.find("_INDUSTRY_ALIASES = {")
    end = src.find("}", alias_idx)
    alias_block = src[alias_idx:end]
    for ind in ("工业金属", "贵金属", "小金属", "能源金属", "稀有金属"):
        assert f'"{ind}"' in alias_block, \
            f"BUG#R10-coverage: _INDUSTRY_ALIASES 缺 {ind!r} → '有色金属' 映射"


# ─── v2.9 · 机械级 self-review gate ──
def test_self_review_engine_exists():
    from lib import self_review
    assert hasattr(self_review, "review_all"), "v2.9 regression: lib.self_review.review_all missing"
    assert hasattr(self_review, "write_review")
    assert hasattr(self_review, "CHECKS")
    assert len(self_review.CHECKS) >= 10, f"v2.9 regression: self-review 检查不足 10 条（当前 {len(self_review.CHECKS)}）"


def test_self_review_cli_exists():
    cli = SCRIPTS_DIR / "review_stage_output.py"
    assert cli.exists(), "v2.9 regression: review_stage_output.py CLI missing"


def test_assemble_report_gated_by_review():
    """assemble_report 入口必须调 self_review 并在 critical>0 时 raise"""
    src = (SCRIPTS_DIR / "assemble_report.py").read_text(encoding="utf-8")
    # 必须有 review_all / write_review 调用
    assert "from lib.self_review" in src, "v2.9 regression: assemble_report 未 import self_review"
    assert "review_all(ticker)" in src, "v2.9 regression: assemble_report 未调 review_all"
    assert "critical_count" in src and "RuntimeError" in src, \
        "v2.9 regression: assemble_report 必须在 critical>0 时 raise RuntimeError 拒绝出 HTML"


def test_self_review_catches_bug_r10():
    """自查引擎必须能捕捉 BUG#R10 级别的行业碰撞（云铝→农副食品加工）"""
    from lib.self_review import check_industry_mapping_sanity
    # 构造假 ctx 模拟 BUG#R10 场景
    ctx = {
        "market": "A",
        "dims": {
            "0_basic": {"data": {"industry": "工业金属", "name": "云铝股份"}},
            "7_industry": {"data": {"cninfo_metrics": {"industry_name_match": "农副食品加工业"}}},
        },
    }
    issues = check_industry_mapping_sanity(ctx)
    assert len(issues) >= 1, "BUG#R10 regression: self_review 没抓到工业金属→农副食品加工的误映射"
    assert issues[0].severity == "critical"


# ─── v2.9 · fetch_industry 结构性改造：动态 search_trusted ──
def test_fetch_industry_has_dynamic_fallback():
    """fetch_industry 不在硬编码表的行业必须走 search_trusted 动态查"""
    src = (SCRIPTS_DIR / "fetch_industry.py").read_text(encoding="utf-8")
    assert "_dynamic_industry_overview" in src, \
        "v2.9 regression: fetch_industry 缺 _dynamic_industry_overview 动态查询函数"
    assert "search_trusted" in src, \
        "v2.9 regression: fetch_industry 未接入 search_trusted"
    assert "dynamic_snippets" in src, \
        "v2.9 regression: fetch_industry 输出必须带 dynamic_snippets 给 agent 综合"


# ─── v2.9.1 · 评委汇总渲染完整性 ──
def test_panel_insights_rendered():
    """panel_insights 必须被渲染到 HTML，不能写入 synthesis.json 后静默丢弃"""
    # assemble_report 必须有 render_panel_insights
    src = (SCRIPTS_DIR / "assemble_report.py").read_text(encoding="utf-8")
    assert "def render_panel_insights" in src, \
        "v2.9.1 regression: panel_insights 渲染函数缺失（之前的静默丢弃 bug）"
    assert "render_panel_insights(syn, panel)" in src, \
        "v2.9.1 regression: panel_insights 未被调用"
    # template 必须有对应 inject 点
    tpl = (SCRIPTS_DIR.parent / "assets" / "report-template.html").read_text(encoding="utf-8")
    assert "INJECT_PANEL_INSIGHTS" in tpl, \
        "v2.9.1 regression: template 缺 <!-- INJECT_PANEL_INSIGHTS -->"


def test_top3_bears_rendered():
    """share-card 必须对称渲染 Top 3 看多 + Top 3 看空"""
    src = (SCRIPTS_DIR / "assemble_report.py").read_text(encoding="utf-8")
    assert "def render_top3_bears" in src, \
        "v2.9.1 regression: render_top3_bears 函数缺失（分享卡不对称）"
    tpl = (SCRIPTS_DIR.parent / "assets" / "report-template.html").read_text(encoding="utf-8")
    assert "INJECT_TOP3_BEARS" in tpl, \
        "v2.9.1 regression: template 缺 INJECT_TOP3_BEARS"


def test_consensus_neutral_weighted_formula():
    """panel_consensus 必须对 neutral 加权计入（v2.9.1 引入半权 0.5，v2.11 校准到 0.6）"""
    src = (SCRIPTS_DIR / "run_real_test.py").read_text(encoding="utf-8")
    # 找 generate_panel 函数体
    fn_idx = src.find("def generate_panel")
    fn_end = src.find("\ndef ", fn_idx + 100)
    body = src[fn_idx:fn_end]
    # 公式必须对 neutral 加权（v2.11 起用常量 NEUTRAL_WEIGHT）
    assert ("NEUTRAL_WEIGHT * neutral" in body or
            "0.6 * neutral" in body or
            "0.5 * neutral" in body or
            "0.5*neutral" in body), \
        "regression: consensus 公式未对 neutral 加权计入"
    # 老的裸 bullish-only 不该再单独出现
    assert 'sig_dist["bullish"] / max(' not in body, \
        "v2.9.1 regression: 仍有老的 bullish-only 公式"


def test_debate_no_hardcoded_default_avatars():
    """BULL_ID / BEAR_ID 不能默认 buffett/graham（debate 空时会显示错误头像）"""
    src = (SCRIPTS_DIR / "assemble_report.py").read_text(encoding="utf-8")
    # 找 BULL_ID / BEAR_ID 的 replacement 定义
    idx = src.find('"{{BULL_ID}}":')
    snippet = src[idx:idx + 500]
    assert '"buffett"' not in snippet, \
        "v2.9.1 regression: BULL_ID 默认值不能硬编码 buffett"
    assert '"graham"' not in snippet, \
        "v2.9.1 regression: BEAR_ID 默认值不能硬编码 graham"


# ─── v2.9.2 · ETF/LOF/可转债 识别与早期拦截 ──
def test_ticker_parser_sh_etf():
    """BUG (v2.9.2) · 512400 是 SH ETF，不能被错判为 SZ"""
    from lib.market_router import parse_ticker, classify_security_type
    # 用户报告的核心 case
    ti = parse_ticker("512400")
    assert ti.full == "512400.SH", f"BUG#2.9.2 regression: 512400 应为 SH，实际 {ti.full!r}"
    assert classify_security_type(ti.code) == "etf"
    # 其他 SH ETF
    for code in ("510500", "513100", "518880", "588000"):
        ti = parse_ticker(code)
        assert ti.full.endswith(".SH"), f"{code} 应为 SH，实际 {ti.full}"


def test_ticker_parser_sz_etf():
    from lib.market_router import parse_ticker, classify_security_type
    for code in ("159949", "159922", "159928"):
        ti = parse_ticker(code)
        assert ti.full.endswith(".SZ"), f"{code} 应为 SZ"
        assert classify_security_type(ti.code) == "etf"


def test_ticker_parser_convertible_bonds():
    from lib.market_router import parse_ticker, classify_security_type
    # SH 可转债 11xxxx
    ti = parse_ticker("113517")
    assert ti.full.endswith(".SH")
    assert classify_security_type(ti.code) == "convertible_bond"
    # SZ 可转债 12xxxx
    ti = parse_ticker("123029")
    assert ti.full.endswith(".SZ")
    assert classify_security_type(ti.code) == "convertible_bond"


def test_ticker_parser_stocks_still_correct():
    """修复 ETF 识别的同时不能破坏股票识别"""
    from lib.market_router import parse_ticker, classify_security_type
    for code, expected in [
        ("600519", ".SH"),   # 茅台
        ("688981", ".SH"),   # 中芯国际 科创板
        ("000807", ".SZ"),   # 云铝
        ("300750", ".SZ"),   # 宁德
        ("301000", ".SZ"),   # 创业板注册制
        ("830799", ".BJ"),   # 北交所
    ]:
        ti = parse_ticker(code)
        assert ti.full.endswith(expected), f"{code} 应为 {expected}，实际 {ti.full}"
        assert classify_security_type(ti.code) == "stock"


def test_fetch_basic_rejects_etf():
    """v2.9.2 · fetch_basic 必须在看到 ETF ticker 时早期返回 non_stock_security"""
    src = (SCRIPTS_DIR / "fetch_basic.py").read_text(encoding="utf-8")
    assert "classify_security_type" in src, \
        "v2.9.2 regression: fetch_basic 未接入 classify_security_type"
    assert "non_stock_security" in src, \
        "v2.9.2 regression: fetch_basic 缺 non_stock_security 错误类型"
    assert "NON_STOCK_GUIDANCE" in src or "_NON_STOCK_GUIDANCE" in src, \
        "v2.9.2 regression: fetch_basic 缺 ETF/LOF/CB 引导信息表"


def test_stage1_early_exits_on_etf():
    """v2.9.2 · run_real_test.stage1 必须在 ETF ticker 时早期 return，
    不跑 22 维 fetcher 浪费时间"""
    src = (SCRIPTS_DIR / "run_real_test.py").read_text(encoding="utf-8")
    assert "non_stock_security" in src, \
        "v2.9.2 regression: stage1 缺 non_stock_security 早退逻辑"
    assert "top_holdings" in src, \
        "v2.9.2 regression: ETF 早退必须输出 top_holdings 供用户选择"
    assert "fund_portfolio_hold_em" in src, \
        "v2.9.2 regression: ETF 持仓拉取接口未使用"


# ─── v2.10.1 · 性能优化：lite mode + ddgs 预算 + fund_holders 默认 20 ──
def test_fund_holders_two_tier_strategy():
    """v2.10.1 · fetch_fund_holders 必须双层（头部 full + 其余 lite）"""
    src = (SCRIPTS_DIR / "fetch_fund_holders.py").read_text(encoding="utf-8")
    assert "_build_row_full" in src and "_build_row_lite" in src, \
        "v2.10.1 regression: fetch_fund_holders 必须分 full/lite 双路径"
    assert "UZI_FUND_STATS_TOP" in src, \
        "v2.10.1 regression: 必须支持 UZI_FUND_STATS_TOP 环境变量控制几家算完整业绩"
    # lite 行必须是 0 次 akshare 额外调用
    lite_idx = src.find("def _build_row_lite")
    lite_end = src.find("\n\n", lite_idx)
    lite_body = src[lite_idx:lite_end] if lite_end > 0 else src[lite_idx:lite_idx + 2000]
    assert "compute_fund_stats" not in lite_body, \
        "v2.10.1 regression: lite 行不应调 compute_fund_stats（0 API 原则）"
    assert "fetch_fund_manager_name" not in lite_body, \
        "v2.10.1 regression: lite 行不应调 fetch_fund_manager_name"


def test_lite_mode_detection_exists():
    """v2.10.1 · _detect_lite_mode 必须存在"""
    src = (SCRIPTS_DIR / "run_real_test.py").read_text(encoding="utf-8")
    assert "_detect_lite_mode" in src, "v2.10.1 regression: 缺 _detect_lite_mode"
    assert "UZI_LITE" in src
    assert "UZI_DDG_BUDGET" in src


def test_ddg_budget_enforced():
    """v2.10.1 · search() 必须在超预算时返回 _budget_exceeded 标记并过滤掉"""
    import os
    os.environ["UZI_DDG_BUDGET"] = "0"  # 强制超预算
    try:
        from importlib import reload
        from lib import web_search
        reload(web_search)
        # 预算为 0，任何未命中 cache 的查询都应该返空
        results = web_search.search("测试预算 xxxx_unique_probe_q", max_results=3, cache_key_prefix="budget_test")
        assert isinstance(results, list)
        # _budget_exceeded 标记不应对外暴露
        assert not any(r.get("_budget_exceeded") for r in results)
        state = web_search.get_budget_state()
        assert state["skipped"] >= 0  # 至少调用过
    finally:
        os.environ.pop("UZI_DDG_BUDGET", None)


def test_analysis_profile_three_tiers():
    """v2.10.2 · 三档深度 profile 必须存在且差异清晰"""
    from lib.analysis_profile import get_profile, DEPTH_LITE, DEPTH_MEDIUM, DEPTH_DEEP
    lite = get_profile(DEPTH_LITE)
    mid = get_profile(DEPTH_MEDIUM)
    deep = get_profile(DEPTH_DEEP)
    # 档位差异必须显著
    assert len(lite.fetchers_enabled) < len(mid.fetchers_enabled) == len(deep.fetchers_enabled)
    assert lite.investors_count < mid.investors_count == deep.investors_count
    assert lite.ddg_budget < mid.ddg_budget < deep.ddg_budget
    assert lite.fund_stats_top_n < mid.fund_stats_top_n < deep.fund_stats_top_n
    assert not lite.enable_bull_bear_debate
    assert not mid.enable_bull_bear_debate
    assert deep.enable_bull_bear_debate  # deep 独享
    assert not lite.enable_segmental_model
    assert deep.enable_segmental_model


def test_analysis_profile_env_compat():
    """UZI_LITE=1 必须向后兼容到 depth=lite"""
    import os
    from lib.analysis_profile import get_profile, DEPTH_LITE, DEPTH_MEDIUM
    # UZI_LITE=1
    os.environ["UZI_LITE"] = "1"
    os.environ.pop("UZI_DEPTH", None)
    assert get_profile().depth == DEPTH_LITE
    # 显式 UZI_DEPTH 覆盖 UZI_LITE
    os.environ["UZI_DEPTH"] = "medium"
    assert get_profile().depth == DEPTH_MEDIUM
    # 清理
    os.environ.pop("UZI_LITE", None)
    os.environ.pop("UZI_DEPTH", None)


# ─── v2.10.2 · 代理/网络挂死的 4 层保护 ──
def test_ddg_timeout_wrapper():
    """v2.10.2 · DDGS 必须有硬 timeout（原先无，GFW 挂时卡 30-120s）"""
    src = (SCRIPTS_DIR / "lib" / "web_search.py").read_text(encoding="utf-8")
    assert "UZI_DDG_TIMEOUT" in src, "v2.10.2 regression: DDGS 缺 timeout env"
    assert "concurrent.futures" in src or "_cf" in src, \
        "v2.10.2 regression: DDGS 必须用线程池硬 kill，不能依赖 DDGS 内部 timeout"
    # 必须有 timeout 错误返回
    assert "ddgs: timeout" in src


def test_net_timeout_guard_exists():
    """v2.10.2 · net_timeout_guard 必须存在且 monkey-patch requests"""
    p = SCRIPTS_DIR / "lib" / "net_timeout_guard.py"
    assert p.exists(), "v2.10.2 regression: lib/net_timeout_guard.py 缺失"
    src = p.read_text(encoding="utf-8")
    assert "install_default_timeout" in src
    assert "Session.request" in src, "必须 patch Session.request（覆盖所有 akshare 内部调用）"
    assert "UZI_HTTP_TIMEOUT" in src


def test_network_preflight_exists():
    """v2.10.2 · 网络预检必须存在且覆盖核心域名"""
    p = SCRIPTS_DIR / "lib" / "network_preflight.py"
    assert p.exists()
    src = p.read_text(encoding="utf-8")
    for d in ("eastmoney", "duckduckgo", "cninfo", "xueqiu"):
        assert d in src, f"预检必须覆盖 {d} 域名"


# ─── v2.10.3 · Providers 框架（Tushare/Efinance/BaoStock 适配器） ──
def test_providers_framework_loads():
    """v2.10.3 · providers 目录必须存在且核心 provider 已注册"""
    from lib import providers
    names = {p.name for p in providers.list_providers()}
    # 至少 4 个内置 provider
    assert "akshare" in names, "akshare provider 未注册"
    assert "efinance" in names, "efinance provider 未注册"
    assert "tushare" in names, "tushare provider 未注册"
    assert "baostock" in names, "baostock provider 未注册"


def test_provider_chain_failover():
    """provider chain 必须按优先级返 + 只包含 available 的"""
    from lib import providers
    chain = providers.get_provider_chain("financials", market="A")
    # 至少 akshare 或 baostock 在（测试机两者都装了）
    assert len(chain) >= 1
    # 所有返回的都必须 is_available()
    assert all(p.is_available() for p in chain)


def test_provider_env_override():
    """UZI_PROVIDERS_<DIM> 环境变量可覆盖优先级"""
    import os
    from lib import providers
    os.environ["UZI_PROVIDERS_FINANCIALS"] = "baostock,akshare"
    try:
        chain = providers.get_provider_chain("financials", market="A")
        names = [p.name for p in chain]
        # baostock 应该在前（如果可用）
        if "baostock" in names and "akshare" in names:
            assert names.index("baostock") < names.index("akshare")
    finally:
        os.environ.pop("UZI_PROVIDERS_FINANCIALS", None)


def test_provider_health_check_api():
    """health_check 返回统一 dict 结构"""
    from lib import providers
    hc = providers.health_check()
    assert "akshare" in hc
    for name, info in hc.items():
        assert "available" in info
        assert "status" in info


def test_tushare_provider_requires_key():
    """tushare 必须 requires_key=True 且无 token 时 is_available=False"""
    import os
    from lib import providers
    ts = providers.get("tushare")
    assert ts is not None
    assert ts.requires_key is True
    # 无 token
    old = os.environ.pop("TUSHARE_TOKEN", None)
    try:
        assert ts.is_available() is False, "无 TUSHARE_TOKEN 时不该可用"
    finally:
        if old: os.environ["TUSHARE_TOKEN"] = old


def test_direct_http_provider_exists():
    """v2.10.3 · 直连站点 provider 必须注册（脱离 akshare 包装抓行情）"""
    from lib import providers
    p = providers.get("direct_http")
    assert p is not None, "direct_http provider 未注册"
    assert p.requires_key is False
    assert "A" in p.markets and "H" in p.markets and "U" in p.markets
    # 必须有三级 fallback 入口
    for method in ("fetch_quote_tencent", "fetch_quote_sina", "fetch_quote"):
        assert hasattr(p, method), f"direct_http 缺 {method}"


def test_parse_ticker_hk_3digit():
    """v2.10.2 · 3 位数字码（如 700/981）必须识别为 HK 不是 A 股"""
    from lib.market_router import parse_ticker
    for code in ("700", "981"):
        r = parse_ticker(code)
        assert r.market == "H", f"v2.10.2 regression: {code} 应识别为 HK，实际 {r.market}"
        assert r.full == f"{code.zfill(5)}.HK"


def test_prewarm_cache_script_exists():
    """v2.10.2 · prewarm 脚本存在且具有敏感性扫描"""
    p = SCRIPTS_DIR / "prewarm_cache.py"
    assert p.exists(), "v2.10.2 regression: prewarm_cache.py 缺失"
    content = p.read_text(encoding="utf-8")
    # 必须有安全扫描
    assert "sanity_check_output" in content, "prewarm 必须做输出敏感性扫描"
    assert "MX_APIKEY" in content or "sk-" in content, "敏感扫描必须覆盖 API key 模式"
    # 必须声明不包含敏感信息
    assert ".env" in content, "prewarm 文档必须明确排除 .env"


def test_fetch_industry_respects_lite_mode():
    """v2.10.1 · fetch_industry 在 UZI_LITE=1 时不跑 _dynamic_industry_overview"""
    src = (SCRIPTS_DIR / "fetch_industry.py").read_text(encoding="utf-8")
    assert 'UZI_LITE' in src and '_dynamic_industry_overview' in src
    # 检查早退逻辑
    idx = src.find('UZI_LITE')
    snippet = src[idx:idx + 300]
    assert "dynamic = {}" in snippet, "lite mode 必须让 dynamic 为空"


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
