"""Auto self-review engine · v2.9.

**Why this exists**:
过往版本只有 SKILL.md 里"软要求"级别的 HARD-GATE-FINAL-CHECK。agent 可能
跳过、可能忘、可能做半截。BUG#R10 那种"工业金属→农副食品加工"跑完报告
才发现的严重问题说明 soft gate 不够。

本模块提供**机械级**自查：
  1. 加载 raw_data / synthesis / panel / dimensions
  2. 跑 ~20 条自动检查（参考 BUG 经验 + 常见坑）
  3. 输出 `.cache/{ticker}/_review_issues.json`
  4. `stage2` 检查 issues 文件，critical != 0 时 **拒绝**生成 HTML

每条 issue 包含：
  - severity: critical / warning / info
  - category: industry / data / valuation / panel / consistency / hk
  - dim: 关联维度 key
  - issue: 人读的问题描述
  - evidence: 触发的具体值
  - suggested_fix: agent 下一步怎么处理
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class Issue:
    severity: str          # critical / warning / info
    category: str          # industry / data / valuation / panel / consistency / hk / self-check
    dim: str               # e.g. "7_industry" / "overall" / "panel"
    issue: str             # human-readable
    evidence: str = ""     # specific value that triggered
    suggested_fix: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
# 检查注册表
# 每个 check 函数接收 (ctx: dict) 返回 list[Issue]
# ctx 包含 raw / syn / panel / dims / ticker / market
# ═══════════════════════════════════════════════════════════════

def _get_dim(ctx: dict, key: str) -> dict:
    return (ctx["dims"].get(key) or {}).get("data") or {}


def check_industry_mapping_sanity(ctx: dict) -> list[Issue]:
    """BUG#R10 class · 行业被错误映射到高碰撞类别"""
    issues = []
    basic = _get_dim(ctx, "0_basic")
    ind = basic.get("industry", "")
    ind_metrics = _get_dim(ctx, "7_industry").get("cninfo_metrics") or {}
    matched = ind_metrics.get("industry_name_match", "")

    # 已知的高碰撞错位：工业金属 不该映射到 农副食品加工
    COLLISION_REDFLAGS = [
        ("工业金属", "农副食品", "有色金属"),
        ("工业母机", "农副食品", "专用设备"),
        ("工业机械", "农副食品", "通用设备"),
        ("白酒",     "农副食品", "酒、饮料和精制茶"),
    ]
    for sw, wrong, right in COLLISION_REDFLAGS:
        if sw in ind and wrong in matched:
            issues.append(Issue(
                severity="critical",
                category="industry",
                dim="7_industry",
                issue=f"BUG#R10 class regression: 申万行业 {ind!r} 被误映射到证监会 {matched!r}",
                evidence=f"industry={ind!r}, matched={matched!r}",
                suggested_fix=f"检查 lib/industry_mapping.SW_TO_CSRC_INDUSTRY[{sw!r}] 是否指向含 {right!r} 的证监会名；必要时清 cache 重跑",
            ))
    return issues


def check_all_dims_exist(ctx: dict) -> list[Issue]:
    """应跑的维度必须都存在 · v2.10.4 · profile-aware (lite 只查启用的维度)."""
    issues = []
    dims = ctx["dims"]

    # v2.10.4 · 按 profile.fetchers_enabled 决定"应跑"的维度集
    # lite 模式只跑 7 个维度，未启用的不能报 critical missing
    required_numbered = set(range(20))
    try:
        from lib.analysis_profile import get_profile
        profile = get_profile()
        # profile.fetchers_enabled 形如 {"0_basic", "1_financials", ...}
        enabled_nums = {
            int(k.split("_")[0])
            for k in profile.fetchers_enabled
            if k[0].isdigit() and k.split("_")[0].isdigit()
        }
        if enabled_nums:
            required_numbered = enabled_nums
    except Exception:
        pass  # profile 加载失败，fallback 到全 20 维

    present_nums = {int(k.split("_")[0]) for k in dims if k[0].isdigit() and k.split("_")[0].isdigit()}
    missing = required_numbered - present_nums
    if missing:
        for num in sorted(missing):
            issues.append(Issue(
                severity="critical",
                category="data",
                dim=f"{num}_",
                issue=f"应跑的维度 {num} 完全缺失（fetcher 从未运行或崩溃）",
                evidence=f"dims 里没有 key 以 {num}_ 开头",
                suggested_fix=f"重跑 run.py <ticker> --no-resume 或手动 fetch_X",
            ))
    return issues


def check_empty_dims(ctx: dict) -> list[Issue]:
    """有 key 但 data 完全空的维度 · v2.10.4 · profile-aware (lite 只查启用的维度)"""
    issues = []
    dims = ctx["dims"]

    # v2.10.4 · 只检查当前 profile 启用的维度
    enabled_nums = None
    try:
        from lib.analysis_profile import get_profile
        profile = get_profile()
        enabled_nums = {
            int(k.split("_")[0])
            for k in profile.fetchers_enabled
            if k[0].isdigit() and k.split("_")[0].isdigit()
        } or None
    except Exception:
        pass

    for k, v in sorted(dims.items()):
        if not isinstance(v, dict): continue
        # 跳过 profile 未启用的维度
        if enabled_nums is not None and k[0].isdigit():
            try:
                num = int(k.split("_")[0])
                if num not in enabled_nums:
                    continue
            except ValueError:
                pass
        data = v.get("data")
        if data in (None, {}, []):
            # 区分是 timeout 还是真空
            is_timeout = bool(v.get("_timeout"))
            err = v.get("error", "")
            sev = "warning" if is_timeout or err else "critical"
            issues.append(Issue(
                severity=sev,
                category="data",
                dim=k,
                issue=f"维度 {k} data 为空" + (" (timeout)" if is_timeout else (" (crash)" if err else "")),
                evidence=f"_timeout={is_timeout}, error={err[:60]}",
                suggested_fix="agent 用 WebSearch / mx_api / 手工查权威源补齐，写入 agent_analysis.dim_commentary",
            ))
    return issues


def check_hk_kline_populated(ctx: dict) -> list[Issue]:
    """BUG#R8 class · HK 股 kline 不能为 0 rows"""
    issues = []
    if ctx["market"] != "H": return issues
    kline = _get_dim(ctx, "2_kline")
    count = kline.get("kline_count", 0)
    stage = kline.get("stage", "—")
    if count == 0:
        issues.append(Issue(
            severity="critical",
            category="hk",
            dim="2_kline",
            issue="港股 kline_count=0，技术面维度不可用",
            evidence=f"kline_count={count}, stage={stage!r}",
            suggested_fix="检查 _kline_hk_chain 三层 fallback 是否都失败（东财→新浪→yfinance）；可能需手动重跑",
        ))
    elif stage == "—" and count > 60:
        issues.append(Issue(
            severity="warning",
            category="hk",
            dim="2_kline",
            issue="港股有 kline 数据但 stage 未分类",
            evidence=f"kline_count={count}, stage={stage!r}",
            suggested_fix="indicators.stage 计算失败，查 _stage() 函数是否遇到 ma200=None",
        ))
    return issues


def check_hk_financials_populated(ctx: dict) -> list[Issue]:
    """BUG#R7 class · HK 股 1_financials 不能为空"""
    issues = []
    if ctx["market"] != "H": return issues
    fin = _get_dim(ctx, "1_financials")
    if not fin:
        issues.append(Issue(
            severity="critical",
            category="hk",
            dim="1_financials",
            issue="港股 1_financials 完全空，ROE/营收/净利全缺",
            evidence="data={}",
            suggested_fix="检查 fetch_financials._fetch_hk 是否调了 stock_financial_hk_analysis_indicator_em",
        ))
    elif not fin.get("roe_history"):
        issues.append(Issue(
            severity="warning",
            category="hk",
            dim="1_financials",
            issue="港股 roe_history 缺失（6 年 ROE 历史是评委依赖字段）",
            evidence=f"keys={list(fin.keys())[:5]}",
            suggested_fix="agent 用 mx_api 或 hkexnews 补齐",
        ))
    return issues


def check_panel_non_empty(ctx: dict) -> list[Issue]:
    """51 评委不能全是 skip / 评分全 0"""
    issues = []
    panel = ctx.get("panel") or {}
    investors = panel.get("investors", [])
    if not investors:
        issues.append(Issue(
            severity="critical", category="panel", dim="panel",
            issue="panel.json 无 investors", evidence="",
            suggested_fix="重跑 generate_panel()",
        ))
        return issues

    sigs = [i.get("signal") for i in investors]
    skip_rate = sigs.count("skip") / len(sigs)
    if skip_rate > 0.5:
        issues.append(Issue(
            severity="warning", category="panel", dim="panel",
            issue=f"{skip_rate*100:.0f}% 评委 skip（可能是不在其能力圈的股票，也可能是 bug）",
            evidence=f"{sigs.count('skip')}/{len(sigs)} skip",
            suggested_fix="确认是否是港股/美股/ST 股，否则查 investor_knowledge.reality_check",
        ))

    avg_score = sum(i.get("score", 0) for i in investors if isinstance(i.get("score"), (int, float))) / len(investors)
    if avg_score == 0 or avg_score > 100:
        issues.append(Issue(
            severity="critical", category="panel", dim="panel",
            issue=f"panel 分数异常 (avg={avg_score:.1f})", evidence=f"avg={avg_score}",
            suggested_fix="查 investor_evaluator 或 rules 是否传入了错误 features",
        ))
    return issues


def check_coverage_threshold(ctx: dict) -> list[Issue]:
    """_integrity.coverage_pct 必须 >= 60%"""
    issues = []
    integrity = ctx["raw"].get("_integrity") or {}
    pct = integrity.get("coverage_pct", 100)
    if pct < 60:
        issues.append(Issue(
            severity="critical" if pct < 40 else "warning",
            category="data", dim="overall",
            issue=f"数据完整性仅 {pct:.0f}%（< 60% 不该出报告）",
            evidence=f"coverage_pct={pct}, missing_critical={integrity.get('missing_critical', [])[:3]}",
            suggested_fix="agent 用 WebSearch / mx_api 补齐 missing_critical 维度，重跑 stage2",
        ))
    return issues


def check_placeholder_strings(ctx: dict) -> list[Issue]:
    """synthesis 里不能有 '[脚本占位]' / '[TODO]' / 'placeholder'"""
    issues = []
    syn = ctx.get("syn") or {}
    dim_comm = syn.get("dim_commentary") or {}
    BAD_MARKERS = ["[脚本占位]", "[TODO]", "PLACEHOLDER", "占位符", "[未实现]", "placeholder"]
    for dim, text in dim_comm.items():
        if not isinstance(text, str): continue
        for marker in BAD_MARKERS:
            if marker.lower() in text.lower():
                issues.append(Issue(
                    severity="critical", category="consistency", dim=dim,
                    issue=f"dim_commentary[{dim}] 含占位符 {marker!r}",
                    evidence=text[:100],
                    suggested_fix=f"agent 写真实 commentary 覆盖该维度；检查 _auto_summarize_dim 是否漏了 {dim}",
                ))
    return issues


def check_valuation_sanity(ctx: dict) -> list[Issue]:
    """DCF / Comps 不能全 0 / NaN"""
    issues = []
    vm = _get_dim(ctx, "20_valuation_models")
    if not vm: return issues
    dcf = vm.get("dcf") or {}
    iv = dcf.get("intrinsic_value_per_share", 0)
    if iv in (None, 0, "—"):
        issues.append(Issue(
            severity="warning", category="valuation", dim="20_valuation_models",
            issue="DCF 内在价值为 0/None（可能负 FCF 或假设异常）",
            evidence=f"intrinsic_value_per_share={iv}",
            suggested_fix="检查 fetch_financials.net_profit_history 最新值是否 > 0",
        ))

    comps = vm.get("comps") or {}
    target_price = comps.get("target_price_implied")
    if target_price in (None, 0, "—"):
        issues.append(Issue(
            severity="info", category="valuation", dim="20_valuation_models",
            issue="Comps 隐含目标价缺失",
            evidence=f"target_price_implied={target_price}",
            suggested_fix="检查 fetch_peers 是否返回足够同行样本",
        ))
    return issues


def check_industry_data_coverage(ctx: dict) -> list[Issue]:
    """7_industry 维度 TAM/growth 是否依赖了被 v2.9 弃用的 INDUSTRY_ESTIMATES"""
    issues = []
    ind = _get_dim(ctx, "7_industry")
    if not ind: return issues
    # 如果 needs_web_search=True 且 agent 没补，则提示
    if ind.get("needs_web_search") and not ind.get("agent_populated"):
        queries = ind.get("web_search_queries", [])
        if queries:
            issues.append(Issue(
                severity="warning", category="data", dim="7_industry",
                issue=f"行业景气度字段需要 agent 用 search_trusted 补齐（{ctx['market'].get('industry','') if isinstance(ctx['market'], dict) else ''} 不在硬编码表里）",
                evidence=f"needs_web_search=True, {len(queries)} 条建议查询未执行",
                suggested_fix=f"agent 执行: " + "; ".join(queries[:2]),
            ))
    return issues


def check_metals_materials_populated(ctx: dict) -> list[Issue]:
    """v2.8.4 coverage · 有色金属类股票必须有原材料数据"""
    issues = []
    basic = _get_dim(ctx, "0_basic")
    ind = basic.get("industry", "")
    METAL_IND = ("工业金属", "有色金属", "贵金属", "能源金属", "小金属", "稀有金属",
                 "钢铁", "普钢", "特钢", "煤炭开采")
    if not any(k in ind for k in METAL_IND):
        return issues
    mat = _get_dim(ctx, "8_materials")
    core = mat.get("core_material", "—")
    if core == "—" or not mat.get("materials_detail"):
        issues.append(Issue(
            severity="warning", category="data", dim="8_materials",
            issue=f"金属类行业 {ind!r} 但 materials 无原材料数据",
            evidence=f"core_material={core!r}",
            suggested_fix="检查 INDUSTRY_MATERIALS 是否覆盖该细分；必要时走 search_trusted",
        ))
    return issues


def check_agent_analysis_exists(ctx: dict) -> list[Issue]:
    """agent_analysis.json 是否写回.

    v2.10.4 · 分两档：
      - 真实 agent 介入（Claude Code / Codex / Cursor 等）：missing → critical
      - lite 模式 or CLI 直跑（没 agent）：missing → warning，允许报告生成
    """
    issues = []
    ag = ctx.get("ag")

    # v2.10.4 · 识别是否处于"无 agent 直跑"模式
    import os
    is_cli_only = (
        os.environ.get("UZI_DEPTH") == "lite"
        or os.environ.get("UZI_LITE") == "1"
        or os.environ.get("UZI_CLI_ONLY") == "1"
        # CI/batch 环境也视为无 agent
        or os.environ.get("CI") == "true"
    )

    if ag is None:
        severity = "warning" if is_cli_only else "critical"
        note = "（lite/CLI 直跑模式可接受）" if is_cli_only else ""
        issues.append(Issue(
            severity=severity,
            category="self-check",
            dim="agent_analysis",
            issue=f"agent_analysis.json 不存在{note}",
            evidence="file not found",
            suggested_fix=(
                "CLI 直跑无 agent 环境可以忽略此项；"
                "若走 Claude Code/Codex/Cursor 则 agent 必须读 panel.json + raw_data.json "
                "后写 agent_analysis.json"
            ),
        ))
        return issues
    if not ag.get("agent_reviewed"):
        issues.append(Issue(
            severity="warning" if is_cli_only else "critical",
            category="self-check", dim="agent_analysis",
            issue="agent_analysis.agent_reviewed != True",
            evidence=f"agent_reviewed={ag.get('agent_reviewed')}",
            suggested_fix="agent 核查完内容后必须显式设置 agent_reviewed: true",
        ))
    # dim_commentary 覆盖率
    dc = ag.get("dim_commentary") or {}
    if len(dc) < 15:
        issues.append(Issue(
            severity="warning", category="self-check", dim="agent_analysis",
            issue=f"agent 仅覆盖 {len(dc)}/22 维 dim_commentary（建议 ≥ 15）",
            evidence=f"covered_dims={list(dc.keys())}",
            suggested_fix="agent 补写更多维度的 dim_commentary，尤其是 14_moat / 13_policy / 7_industry 定性维度",
        ))
    return issues


def check_factcheck_redflags(ctx: dict) -> list[Issue]:
    """BUG (v2.6) class · 禁止联想编造的经典红旗词组合"""
    issues = []
    ag = ctx.get("ag") or {}
    syn = ctx.get("syn") or {}
    basic = _get_dim(ctx, "0_basic")
    main_business = (basic.get("main_business") or "") + str(basic.get("industry") or "")

    # 收集所有 commentary 文本
    all_text = ""
    for text in (ag.get("dim_commentary") or {}).values():
        if isinstance(text, str): all_text += text + " "
    for text in (syn.get("dim_commentary") or {}).values():
        if isinstance(text, str): all_text += text + " "

    # 红旗关联词：如果声称 "Apple/苹果" 但 main_business 不含相关词 → 嫌疑
    REDFLAGS = [
        ("苹果|Apple", ["光学", "镜头", "屏幕", "代工", "结构件", "精密"], "苹果产业链"),
        ("特斯拉|Tesla", ["电池", "零部件", "车身", "锂电"], "特斯拉供应链"),
    ]
    import re
    for claim_pattern, justify_kws, label in REDFLAGS:
        if re.search(claim_pattern, all_text, re.I):
            if not any(k in main_business for k in justify_kws):
                issues.append(Issue(
                    severity="warning", category="consistency", dim="synthesis",
                    issue=f"commentary 提到 {label} 但 main_business 未见相关业务",
                    evidence=f"claim mentions {claim_pattern}, main_business={main_business[:80]!r}",
                    suggested_fix="在 raw_data.dimensions['5_chain'] 里找到明确证据，否则删除该关联",
                ))
    return issues


# ═══════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════

def check_consensus_formula_sanity(ctx: dict) -> list[Issue]:
    """v2.9.1 · panel_consensus 使用正确的半权 neutral 公式"""
    issues = []
    panel = ctx.get("panel") or {}
    cf = panel.get("consensus_formula") or {}
    cons = panel.get("panel_consensus", -1)
    if cons < 0: return issues
    # 如果 panel 里有 consensus_formula 但 version 不是 v2.9.1+，可能是老 panel.json
    version = cf.get("version", "")
    if cf and "v2.9.1" not in version and "bullish + 0.5" not in version:
        issues.append(Issue(
            severity="warning", category="panel", dim="panel",
            issue="consensus_formula 不是 v2.9.1 半权公式，可能是旧 cache",
            evidence=f"version={version!r}",
            suggested_fix="清 cache 重跑或直接 stage2() 重新合成",
        ))
    # bullish=0 但 consensus > 20% 必然公式错
    sig = panel.get("signal_distribution") or {}
    if sig.get("bullish", 0) == 0 and cons > 20:
        issues.append(Issue(
            severity="critical", category="panel", dim="panel",
            issue="panel_consensus 公式异常：bullish=0 但 consensus > 20%",
            evidence=f"consensus={cons}, bullish={sig.get('bullish', 0)}, neutral={sig.get('neutral', 0)}",
            suggested_fix="检查 generate_panel 的 consensus 公式",
        ))
    return issues


def check_panel_insights_rendered(ctx: dict) -> list[Issue]:
    """v2.9.1 · panel_insights 字段必须在报告里渲染（之前被丢掉的 bug）"""
    issues = []
    # 这个检查是 meta-level — 确认 assemble_report 源码里引用了 panel_insights
    # 如果有人改代码删掉了 render 也能抓到
    from pathlib import Path
    ar = Path(__file__).resolve().parent.parent / "assemble_report.py"
    if ar.exists():
        src = ar.read_text(encoding="utf-8")
        if "render_panel_insights" not in src:
            issues.append(Issue(
                severity="critical", category="self-check", dim="report",
                issue="v2.9.1 regression: assemble_report 缺 render_panel_insights",
                evidence="grep 失败",
                suggested_fix="恢复 render_panel_insights 函数 + INJECT_PANEL_INSIGHTS 替换",
            ))
    return issues


def check_debate_bull_bear_populated(ctx: dict) -> list[Issue]:
    """v2.9.1 · debate.bull / bear 不能是空对象（否则模板会显示默认 buffett 假头像）"""
    issues = []
    syn = ctx.get("syn") or {}
    debate = syn.get("debate") or {}
    bull = debate.get("bull") or {}
    bear = debate.get("bear") or {}
    if not bull.get("investor_id"):
        issues.append(Issue(
            severity="warning", category="panel", dim="debate",
            issue="debate.bull 未选出 bullish 代表（可能全 skip 或全 bearish）",
            evidence=f"bull={bull}",
            suggested_fix="确认 panel 有非 skip 投资者，或 agent 用 great_divide_override 指定",
        ))
    if not bear.get("investor_id"):
        issues.append(Issue(
            severity="warning", category="panel", dim="debate",
            issue="debate.bear 未选出 bearish 代表",
            evidence=f"bear={bear}",
            suggested_fix="同上",
        ))
    if bull.get("investor_id") and bull.get("investor_id") == bear.get("investor_id"):
        issues.append(Issue(
            severity="critical", category="panel", dim="debate",
            issue="debate bull 和 bear 是同一人",
            evidence=f"both={bull.get('investor_id')!r}",
            suggested_fix="generate_synthesis 选 bull/bear 逻辑应排除同人",
        ))
    return issues


CHECKS = [
    check_industry_mapping_sanity,
    check_all_dims_exist,
    check_empty_dims,
    check_hk_kline_populated,
    check_hk_financials_populated,
    check_panel_non_empty,
    check_coverage_threshold,
    check_placeholder_strings,
    check_valuation_sanity,
    check_industry_data_coverage,
    check_metals_materials_populated,
    check_agent_analysis_exists,
    check_factcheck_redflags,
    # v2.9.1 · 评委汇总一致性检查
    check_consensus_formula_sanity,
    check_panel_insights_rendered,
    check_debate_bull_bear_populated,
]


def review_all(ticker: str, cache_root: str | None = None) -> dict:
    """Run all checks on a ticker's cached stage2 output.

    Returns:
        {
            "ticker": str,
            "reviewed_at": iso-ts,
            "critical_count": int,
            "warning_count": int,
            "info_count": int,
            "passed": bool (critical_count == 0),
            "issues": [{severity, category, dim, issue, evidence, suggested_fix}, ...],
        }
    """
    from datetime import datetime
    from lib.cache import read_task_output

    raw = read_task_output(ticker, "raw_data") or {}
    syn = read_task_output(ticker, "synthesis") or {}
    panel = read_task_output(ticker, "panel") or {}
    ag = read_task_output(ticker, "agent_analysis")

    dims = raw.get("dimensions") or {}
    market = raw.get("market", "A")
    ctx = {
        "ticker": ticker, "market": market,
        "raw": raw, "syn": syn, "panel": panel, "ag": ag, "dims": dims,
    }

    all_issues: list[Issue] = []
    for check_fn in CHECKS:
        try:
            result = check_fn(ctx)
            all_issues.extend(result or [])
        except Exception as e:
            all_issues.append(Issue(
                severity="warning", category="self-check", dim="review-engine",
                issue=f"check {check_fn.__name__} 自己炸了: {type(e).__name__}: {str(e)[:100]}",
            ))

    crit = sum(1 for i in all_issues if i.severity == "critical")
    warn = sum(1 for i in all_issues if i.severity == "warning")
    info = sum(1 for i in all_issues if i.severity == "info")

    report = {
        "ticker": ticker,
        "market": market,
        "reviewed_at": datetime.now().isoformat(timespec="seconds"),
        "critical_count": crit,
        "warning_count": warn,
        "info_count": info,
        "passed": crit == 0,
        "issues": [i.to_dict() for i in all_issues],
        "checks_run": [c.__name__ for c in CHECKS],
    }
    return report


def write_review(ticker: str, report: dict) -> Path:
    """Write review to `.cache/{ticker}/_review_issues.json` (agent reads it)."""
    from lib.cache import write_task_output
    write_task_output(ticker, "_review_issues", report)
    return Path(f".cache/{ticker}/_review_issues.json")


def format_human(report: dict) -> str:
    """Human-readable summary of review."""
    lines = []
    mark = "✓" if report["passed"] else "✗"
    lines.append(f"{mark} Self-Review · {report['ticker']} ({report['market']})")
    lines.append(f"  critical={report['critical_count']} warning={report['warning_count']} info={report['info_count']}")
    lines.append(f"  reviewed_at={report['reviewed_at']}")
    if report["issues"]:
        lines.append("")
        for sev in ("critical", "warning", "info"):
            sev_issues = [i for i in report["issues"] if i["severity"] == sev]
            if not sev_issues: continue
            icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}[sev]
            lines.append(f"  {icon} {sev.upper()} ({len(sev_issues)}):")
            for i in sev_issues:
                lines.append(f"    [{i['dim']}] {i['issue']}")
                if i.get("evidence"): lines.append(f"      evidence: {i['evidence'][:120]}")
                if i.get("suggested_fix"): lines.append(f"      fix: {i['suggested_fix'][:200]}")
    return "\n".join(lines)
