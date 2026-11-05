#!/usr/bin/env python3
"""行业资金流轮动：本地 CSV 中信40正式排名 + 可选申万30独立观察。"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

from lib.industry_rotation.snapshot import build_snapshot
from lib.industry_rotation.report import render_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", type=Path, required=True, help="主动买卖额原始CSV（不随技能分发）")
    parser.add_argument("--as-of", type=date.fromisoformat, required=True, help="研究截止日 YYYY-MM-DD")
    parser.add_argument("--proxy-json", type=Path, help="可选：符合代理观察契约的本地日期快照")
    parser.add_argument("--output-dir", type=Path, help="结果目录，默认 scripts/reports/rotation/<截止日>")
    args = parser.parse_args(argv)
    if args.as_of > date.today():
        parser.error("--as-of 不能晚于今天")
    output = args.output_dir or Path(__file__).resolve().parent / "reports" / "rotation" / str(args.as_of)
    outputs = [output / name for name in ("rotation.json", "rankings.csv", "report.html")]
    inputs = {path.resolve() for path in (args.input_csv, args.proxy_json) if path}
    if any(path.resolve() in inputs for path in outputs):
        parser.error("输出路径不得覆盖输入文件")
    try:
        result = build_snapshot(args.input_csv, args.as_of, args.proxy_json)
        json_text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        report = render_report(result)
        output.mkdir(parents=True, exist_ok=True)
        outputs[0].write_text(json_text + "\n", encoding="utf-8")
        with outputs[1].open("w", encoding="utf-8-sig", newline="") as handle:
            fields = ["layer", "data_date", "window", "variant", "rank", "code", "name", "score", "rank_change"]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for layer in ("formal", "proxy"):
                section = result[layer]
                if section is None:
                    continue
                for window, block in section["windows"].items():
                    for variant in ("base", "composite"):
                        for row in block[variant]:
                            safe = dict(row)
                            # Spreadsheet apps must treat externally supplied labels as text.
                            for key in ("name", "code"):
                                if safe[key].lstrip().startswith(("=", "+", "-", "@")):
                                    safe[key] = "'" + safe[key]
                            writer.writerow({"layer": layer, "data_date": section.get("data_date", section.get("as_of")),
                                             "window": window, "variant": variant, **safe})
        outputs[2].write_text(report, encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        parser.error(str(exc))
    print(f"正式数据截至 {result['formal']['data_date']}；仅供研究观察")
    for path in outputs:
        print(path.resolve())


if __name__ == "__main__":
    main()
