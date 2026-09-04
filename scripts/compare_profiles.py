#!/usr/bin/env python3
"""Create serial-versus-parallel reports from profile artifacts."""

import argparse
import html
import json
from pathlib import Path


def load_profiles(root):
    profiles = {}
    for path in root.rglob("metrics.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        profiles[value["mode"]] = value
    return profiles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    profiles = load_profiles(args.root)
    missing = {"serial", "parallel"} - profiles.keys()
    if missing:
        raise SystemExit("missing profile(s): " + ", ".join(sorted(missing)))
    serial = profiles["serial"]
    parallel = profiles["parallel"]
    speedup = serial["wall_seconds"] / parallel["wall_seconds"]
    saved = serial["wall_seconds"] - parallel["wall_seconds"]
    comparison = {
        "serial": serial,
        "parallel": parallel,
        "speedup": round(speedup, 4),
        "wall_seconds_saved": round(saved, 4),
        "wall_percent_reduction": round((1 - parallel["wall_seconds"] / serial["wall_seconds"]) * 100, 3),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "comparison.json").write_text(
        json.dumps(comparison, indent=2) + "\n", encoding="utf-8"
    )

    rows = [
        ("Wall time", f"{serial['wall_seconds']:.3f} s", f"{parallel['wall_seconds']:.3f} s"),
        ("Trace worker capacity", serial["trace_capacity"], parallel["trace_capacity"]),
        ("Maximum active workers", serial["max_active_workers"], parallel["max_active_workers"]),
        ("Average active workers", f"{serial['average_active_workers']:.3f}", f"{parallel['average_active_workers']:.3f}"),
        ("Worker utilization", f"{serial['worker_utilization_percent']:.1f}%", f"{parallel['worker_utilization_percent']:.1f}%"),
        ("Time with 2+ workers", f"{serial['parallel_time_percent']:.1f}%", f"{parallel['parallel_time_percent']:.1f}%"),
        ("Worker spans", serial["worker_span_count"], parallel["worker_span_count"]),
    ]
    markdown_rows = "\n".join(f"| {name} | {left} | {right} |" for name, left, right in rows)
    markdown = f"""## LLGo etcdctl parallel-build comparison

**Speedup: {speedup:.2f}x**; **wall-time reduction: {comparison['wall_percent_reduction']:.1f}%**
({saved:.2f} seconds saved).

| Metric | Serial (`-p 1`) | Parallel (default) |
|---|---:|---:|
{markdown_rows}

The two cases ran on separate clean `ubuntu-24.04` runners. Module download and
the LLGo command build are excluded from the measured interval.
"""
    (args.output / "summary.md").write_text(markdown, encoding="utf-8")

    html_rows = "".join(
        f"<tr><td>{html.escape(str(name))}</td><td>{html.escape(str(left))}</td>"
        f"<td>{html.escape(str(right))}</td></tr>"
        for name, left, right in rows
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LLGo etcdctl parallel build comparison</title>
<style>
body {{ font: 15px/1.5 system-ui,sans-serif; margin: 28px; color:#111827; }}
.hero {{ display:flex; gap:18px; flex-wrap:wrap; margin:20px 0; }}
.card {{ border:1px solid #d1d5db; border-radius:10px; padding:16px; min-width:210px; background:#f9fafb; }}
.value {{ font-size:32px; font-weight:700; color:#166534; }}
table {{ border-collapse:collapse; width:100%; max-width:900px; }}
th,td {{ padding:9px 12px; border-bottom:1px solid #e5e7eb; text-align:left; }}
th {{ background:#f3f4f6; }}
</style></head><body>
<h1>LLGo etcdctl parallel build comparison</h1>
<div class="hero">
 <div class="card"><div>Speedup</div><div class="value">{speedup:.2f}x</div></div>
 <div class="card"><div>Wall-time reduction</div><div class="value">{comparison['wall_percent_reduction']:.1f}%</div></div>
 <div class="card"><div>Time saved</div><div class="value">{saved:.2f}s</div></div>
</div>
<table><thead><tr><th>Metric</th><th>Serial (`-p 1`)</th><th>Parallel (default)</th></tr></thead>
<tbody>{html_rows}</tbody></table>
<p>The individual artifacts contain self-contained timelines and raw Chrome/Perfetto traces.</p>
</body></html>
"""
    (args.output / "comparison.html").write_text(document, encoding="utf-8")


if __name__ == "__main__":
    main()
