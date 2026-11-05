"""Self-contained HTML with escaped labels and no external assets or requests."""
from __future__ import annotations

from html import escape

from .snapshot import WINDOWS


def _text(value):
    return escape(str(value), quote=True)


def _names(items):
    return _text("、".join(items) if items else "无")


def _table(rows, formal):
    body = []
    for row in rows:
        change = row.get("rank_change")
        delta = "—" if change is None else f"{change:+d}"
        score = float(row["score"])
        # The signed meter shows standardized factor strength, not probability.
        width = min(abs(score) / 4, 1) * 50
        left = 50 if score >= 0 else 50 - width
        color = "positive" if score >= 0 else "negative"
        marker = " class='selected'" if row["rank"] <= 5 else ""
        body.append(
            f"<tr{marker}><td>{row['rank']}</td><th scope='row'>{_text(row['name'])}"
            f"<small>{_text(row['code'])}</small></th><td>{score:.4f}</td>"
            f"<td><span class='meter'><i class='{color}' style='left:{left:.2f}%;width:{width:.2f}%'></i>"
            f"</span></td><td>{delta}</td></tr>"
        )
    last = "较前日名次" if formal else "变化未导入"
    return (
        "<div class='table-scroll'><table><thead><tr><th>名次</th><th>行业</th>"
        f"<th>因子分</th><th>强度</th><th>{last}</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def render_report(result):
    formal = result["formal"]
    sections = []
    for layer in ("formal", "proxy"):
        data = result[layer]
        if data is None:
            sections.append("<section><h2>临时观察</h2><p>未导入代理快照；正式结果不受影响。</p></section>")
            continue
        is_formal = layer == "formal"
        title = "正式研究 · 中信40" if is_formal else "临时观察 · 申万30"
        cutoff = data.get("data_date", data.get("as_of"))
        note = "基础因子 + 近似资金图综合因子" if is_formal else data["warning"]
        sections.append(
            f"<section class='{layer}'><div class='section-title'><h2>{title}</h2>"
            f"<span>数据 {_text(cutoff)} · 距截止日 {data['age_calendar_days']} 个自然日</span></div>"
            f"<p>{_text(note)}</p><div class='core'><strong>W20–24 共同入选</strong>"
            f"<span>基础：{_names(data['common_core']['base'])}</span>"
            f"<span>综合：{_names(data['common_core']['composite'])}</span></div>"
        )
        for window in WINDOWS:
            block = data["windows"][str(window)]
            sections.append(f"<div class='window' data-window='{window}'><h3>W = {window} 个交易日</h3><div class='columns'>")
            for variant, label in (("base", "基础因子"), ("composite", "综合五因子 · 近似图")):
                sections.append(f"<article><h3>{label}</h3>")
                if is_formal:
                    change = block[variant + "_changes"]
                    target = block[variant + "_weekly_target"]
                    sections.append(f"<p class='changes'>新进：{_names(change['entered'])} · 退出：{_names(change['exited'])}</p>")
                    if target:
                        sections.append(
                            f"<div class='target'><strong>周频模型目标：{_names(target['names'])}</strong>"
                            f"<span>信号 {_text(target['signal_date'])} · 模型调仓收盘 {_text(target['model_entry_close'])}"
                            f" · 每行业 {target['target_weight_each']:.0%}</span></div>"
                        )
                    else:
                        sections.append("<p>周频目标不可用：尚无满足窗口长度的已确认跨周信号。</p>")
                sections.append(_table(block[variant], is_formal) + "</article>")
            sections.append("</div></div>")
        sections.append("</section>")
    warnings = "".join(f"<li>{_text(item)}</li>" for item in result["warnings"])
    options = "".join(f"<option value='{window}'>W = {window}</option>" for window in WINDOWS)
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>UZI 行业资金流轮动</title><style>
:root{color-scheme:light;font-family:system-ui,-apple-system,"PingFang SC",sans-serif;color:#202723;background:#f5f6f5;letter-spacing:0}
*{box-sizing:border-box}body{margin:0}header{background:#17231e;color:#fff;padding:28px max(20px,calc((100% - 1440px)/2));border-bottom:4px solid #4c9b77}
h1{font-size:28px;line-height:1.35;margin:6px 0 12px}h2{font-size:21px;margin:0}h3{font-size:16px;margin:16px 0 10px}p{line-height:1.6;color:#5e6963;font-size:14px}header p{color:#b8d2c3;margin:0}
main{max-width:1480px;margin:auto;padding:0 20px}.toolbar{display:flex;align-items:center;gap:16px;justify-content:space-between;padding:16px 0;border-bottom:1px solid #d6ddd8;flex-wrap:wrap;background:#f5f6f5}
label{font-size:14px;font-weight:600}select{margin-left:10px;padding:8px 28px 8px 10px;border:1px solid #adb9b1;border-radius:4px;background:white;color:#202723;font-size:14px}.badge{color:#835116;font-weight:600;font-size:14px}
section{padding:24px 0;border-bottom:1px solid #d6ddd8}.section-title{display:flex;align-items:baseline;gap:12px;justify-content:space-between;flex-wrap:wrap}.section-title span{font-size:13px;color:#5e6963}
.core{display:flex;gap:12px 24px;flex-wrap:wrap;background:#e6f0e9;padding:14px 16px;font-size:14px;line-height:1.6}.proxy .core{background:#f5eddd}.columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px}article{min-width:0}
.target{min-height:92px;line-height:1.6;font-size:13px;padding:12px 0;border-top:1px solid #d6ddd8}.target span{display:block;color:#5e6963;margin-top:6px}.changes{min-height:44px;margin:8px 0;font-size:13px}
.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;background:white;table-layout:fixed;min-width:360px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #e3e8e4;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}thead{background:#e9edeb;color:#536057}thead th:first-child{width:46px}thead th:nth-child(2){width:30%}thead th:nth-child(3){width:72px}thead th:last-child{width:76px}tbody th{font-weight:500}small{display:block;color:#76837b;font-size:11px;margin-top:4px}.selected{background:#edf6f0}.proxy .selected{background:#fff9ed}
.meter{display:block;position:relative;width:100%;height:16px;background:linear-gradient(90deg,transparent 49%,#a9b6ad 49%,#a9b6ad 51%,transparent 51%)}.meter i{position:absolute;height:10px;top:3px}.positive{background:#3d8a65}.negative{background:#b86a58}.window[hidden]{display:none}li{margin-bottom:10px;line-height:1.7;font-size:14px;color:#5e6963}footer{font-size:12px;overflow-wrap:anywhere;padding:24px 0;color:#6a756e}a{color:#287751}select:focus-visible{outline:3px solid #719d85}
@media(max-width:760px){h1{font-size:24px}.columns{grid-template-columns:minmax(0,1fr);gap:20px}main{padding:0 14px}.core{display:grid;gap:8px}.target{min-height:0}.changes{min-height:0}header{padding:22px 16px}}
@media print{.window[hidden]{display:block}.toolbar{display:none}body{background:white}.columns{display:block}article{break-inside:avoid}}
</style></head><body>""" + (
        f"<header><p>UZI / INDUSTRY ROTATION</p><h1>行业资金流轮动</h1>"
        f"<p>研究截止日 {_text(result['as_of'])} · 正式数据 {_text(formal['data_date'])} · 周频 Top 5 等权模型</p></header>"
        f"<main><div class='toolbar'><label>平滑窗口<select id='window'>{options}</select></label>"
        "<span class='badge'>观察状态 · 非交易指令</span><a href='rankings.csv' download>排名 CSV</a></div>"
        + "".join(sections)
        + f"<section><h2>方法与边界</h2><ul>{warnings}</ul></section>"
        f"<footer>正式输入 SHA256：{_text(formal['input']['sha256'])}<br>"
        "<a href='rotation.json' download>完整结果与来源记录 JSON</a></footer></main>"
    ) + """<script>
const picker = document.getElementById('window');
function selectWindow(){document.querySelectorAll('.window').forEach(section => {
  section.hidden = section.dataset.window !== picker.value;
});}
picker.addEventListener('change', selectWindow); selectWindow();
</script></body></html>"""
