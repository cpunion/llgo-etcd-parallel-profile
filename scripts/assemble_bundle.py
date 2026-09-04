#!/usr/bin/env python3
"""Collect every matrix result into one browsable artifact."""

import argparse
import html
import json
import re
import shutil
from pathlib import Path


CASES = {
    ("etcd", "serial"): "etcd serial (-p 1)",
    ("etcd", "parallel"): "etcd parallel (default)",
    ("llgo-test", "main"): "llgo test on main",
    ("llgo-test", "optimized"): "llgo test on combined profile branch",
}


def read_text(path, default=""):
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return default


def read_float(path):
    try:
        return float(read_text(path))
    except ValueError:
        return None


def comparison(group, left, right, results, output):
    left_value = results.get((group, left), {}).get("wall_seconds")
    right_value = results.get((group, right), {}).get("wall_seconds")
    if left_value is None or right_value is None or right_value <= 0:
        return None
    speedup = left_value / right_value
    saved = left_value - right_value
    reduction = (1 - right_value / left_value) * 100
    value = {
        "left": left,
        "right": right,
        "left_wall_seconds": left_value,
        "right_wall_seconds": right_value,
        "speedup": round(speedup, 4),
        "wall_seconds_saved": round(saved, 4),
        "wall_percent_reduction": round(reduction, 3),
    }
    directory = output / group / "comparison"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "comparison.json").write_text(
        json.dumps(value, indent=2) + "\n", encoding="utf-8"
    )
    title = "etcd serial vs parallel" if group == "etcd" else "llgo test main vs combined branch"
    (directory / "index.html").write_text(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
body {{ font:15px/1.5 system-ui,sans-serif; margin:28px; color:#111827 }}
.cards {{ display:flex; gap:14px; flex-wrap:wrap }}
.card {{ border:1px solid #d1d5db; border-radius:10px; padding:16px; background:#f9fafb }}
.value {{ font-size:30px; font-weight:700; color:#166534 }}
</style></head><body><h1>{html.escape(title)}</h1><div class="cards">
<div class="card">Speedup<div class="value">{speedup:.2f}x</div></div>
<div class="card">Wall-time reduction<div class="value">{reduction:.1f}%</div></div>
<div class="card">Time saved<div class="value">{saved:.2f}s</div></div>
</div><p>{left}: {left_value:.3f}s; {right}: {right_value:.3f}s.</p></body></html>\n""",
        encoding="utf-8",
    )
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(rf"^raw-{re.escape(args.run_id)}-(etcd|llgo-test)-(.+)$")
    results = {}
    for source in sorted(args.root.iterdir()):
        match = pattern.match(source.name)
        if not match or not source.is_dir():
            continue
        group, variant = match.groups()
        destination = args.output / group / variant
        shutil.copytree(source, destination, dirs_exist_ok=True)
        results[(group, variant)] = {
            "title": CASES.get((group, variant), f"{group} {variant}"),
            "wall_seconds": read_float(source / "wall-seconds.txt"),
            "exit_status": read_text(source / "exit-status.txt", "missing"),
            "commit": read_text(source / "llgo-commit.txt", "unknown"),
            "has_trace": (source / "trace.json").is_file(),
            "has_report": (source / "report.html").is_file(),
        }

    comparisons = {
        "etcd": comparison("etcd", "serial", "parallel", results, args.output),
        "llgo-test": comparison("llgo-test", "main", "optimized", results, args.output),
    }
    manifest = {
        "run_id": args.run_id,
        "results": {f"{group}/{variant}": value for (group, variant), value in results.items()},
        "comparisons": comparisons,
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    rows = []
    markdown_rows = []
    for key in CASES:
        value = results.get(key)
        if value is None:
            rows.append(f"<tr><td>{html.escape(CASES[key])}</td><td colspan=4>missing</td></tr>")
            markdown_rows.append(f"| {CASES[key]} | missing | — | — |")
            continue
        group, variant = key
        wall = "—" if value["wall_seconds"] is None else f'{value["wall_seconds"]:.3f}s'
        report = f'<a href="{group}/{variant}/report.html">timeline</a>' if value["has_report"] else "—"
        trace = f'<a href="{group}/{variant}/trace.json">trace.json</a>' if value["has_trace"] else "—"
        commit = html.escape(value["commit"][:12])
        rows.append(
            f"<tr><td>{html.escape(value['title'])}</td><td>{wall}</td>"
            f"<td>{html.escape(value['exit_status'])}</td><td>{commit}</td><td>{report} · {trace}</td></tr>"
        )
        markdown_rows.append(
            f"| {value['title']} | {wall} | {value['exit_status']} | `{value['commit'][:12]}` |"
        )

    comparison_cards = []
    for group, value in comparisons.items():
        if value is None:
            continue
        label = "etcd parallelism" if group == "etcd" else "combined branch vs main"
        comparison_cards.append(
            f'<a class="card" href="{group}/comparison/index.html">{html.escape(label)}'
            f'<span>{value["speedup"]:.2f}x</span>{value["wall_percent_reduction"]:.1f}% less wall time</a>'
        )
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LLGo parallel profile bundle</title><style>
body {{ font:15px/1.5 system-ui,sans-serif; margin:28px; color:#111827 }}
.cards {{ display:flex; gap:14px; flex-wrap:wrap; margin:18px 0 }}
.card {{ color:inherit; text-decoration:none; border:1px solid #d1d5db; border-radius:10px; padding:16px; background:#f9fafb; min-width:220px }}
.card span {{ display:block; font-size:30px; font-weight:700; color:#166534 }}
table {{ border-collapse:collapse; width:100%; max-width:1100px }}
th,td {{ padding:9px 12px; border-bottom:1px solid #e5e7eb; text-align:left }}
th {{ background:#f3f4f6 }}
</style></head><body><h1>LLGo parallel profile bundle</h1>
<p>GitHub Actions run {html.escape(args.run_id)}. All raw logs, resource measurements,
executables, Chrome/Perfetto traces, and HTML timelines are grouped below.</p>
<div class="cards">{''.join(comparison_cards)}</div>
<table><thead><tr><th>Workload</th><th>Wall time</th><th>Exit</th><th>LLGo commit</th><th>Profile</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></body></html>\n"""
    (args.output / "index.html").write_text(document, encoding="utf-8")
    summary = "\n".join(
        [
            "## LLGo parallel profile bundle",
            "",
            "| Workload | Wall time | Exit | LLGo commit |",
            "|---|---:|---:|---|",
            *markdown_rows,
            "",
        ]
    )
    for group, value in comparisons.items():
        if value is not None:
            summary += (
                f"- **{group}: {value['speedup']:.2f}x speedup, "
                f"{value['wall_percent_reduction']:.1f}% wall-time reduction.**\n"
            )
    (args.output / "summary.md").write_text(summary, encoding="utf-8")


if __name__ == "__main__":
    main()
