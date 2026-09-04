#!/usr/bin/env python3
"""Summarize an LLGo Chrome trace and render a self-contained timeline."""

import argparse
import collections
import hashlib
import html
import json
from pathlib import Path


def rounded(value, digits=3):
    return round(value, digits)


def stage_of(event):
    args = event.get("args") or {}
    if args.get("stage"):
        return str(args["stage"])
    return str(event.get("name", "unknown")).split(" ", 1)[0]


def occupancy(worker_spans, start, end):
    points = []
    for event in worker_spans:
        event_start = max(start, event["ts"])
        event_end = min(end, event["ts"] + event.get("dur", 0))
        if event_end > event_start:
            points.append((event_start, 1))
            points.append((event_end, -1))
    points.sort(key=lambda item: (item[0], item[1]))

    active = 0
    maximum = 0
    previous = start
    by_count = collections.defaultdict(int)
    for timestamp, delta in points:
        if timestamp > previous:
            by_count[active] += timestamp - previous
            previous = timestamp
        active += delta
        maximum = max(maximum, active)
    if end > previous:
        by_count[active] += end - previous
    return maximum, by_count


def color_for(stage):
    colors = {
        "backend+publish": "#2563eb",
        "build": "#111827",
        "entry": "#0f766e",
        "entry-object": "#0f766e",
        "link": "#16a34a",
        "link-snapshot": "#0891b2",
        "load": "#db2777",
        "plan": "#9333ea",
        "pre": "#dc2626",
        "precompute": "#64748b",
        "prepare": "#4f46e5",
        "repair": "#ca8a04",
        "ssa": "#ea580c",
        "test": "#be123c",
    }
    if stage in colors:
        return colors[stage]
    palette = ["#0369a1", "#7c2d12", "#65a30d", "#6d28d9", "#047857"]
    digest = hashlib.sha256(stage.encode()).digest()
    return palette[int.from_bytes(digest[:2], "big") % len(palette)]


def render_html(metrics, spans, path):
    start = metrics["trace_start_us"]
    duration = max(1, metrics["trace_duration_us"])
    lanes = sorted({int(event.get("tid", 0)) for event in spans})
    row_height = 28
    left = 150
    width = 1450
    plot_width = width - left - 20
    height = 58 + row_height * len(lanes)
    lane_index = {lane: index for index, lane in enumerate(lanes)}
    stages = sorted({stage_of(event) for event in spans})
    legend = "".join(
        f'<span class="legend-item"><span class="swatch" '
        f'style="background:{color_for(stage)}"></span>{html.escape(stage)}</span>'
        for stage in stages
    )

    svg = []
    for tick in range(11):
        x = left + plot_width * tick / 10
        seconds = metrics["trace_seconds"] * tick / 10
        svg.append(
            f'<line x1="{x:.1f}" y1="24" x2="{x:.1f}" y2="{height - 10}" '
            'stroke="#d1d5db" stroke-width="1"/>'
        )
        svg.append(
            f'<text x="{x:.1f}" y="17" text-anchor="middle" '
            f'font-size="11" fill="#4b5563">{seconds:.1f}s</text>'
        )
    for lane in lanes:
        y = 34 + lane_index[lane] * row_height
        label = "coordinator" if lane == 0 else f"worker {lane}"
        svg.append(
            f'<text x="{left - 8}" y="{y + 17}" text-anchor="end" '
            f'font-size="12" fill="#374151">{label}</text>'
        )
        svg.append(
            f'<line x1="{left}" y1="{y + row_height - 3}" x2="{width - 20}" '
            f'y2="{y + row_height - 3}" stroke="#e5e7eb"/>'
        )

    for event in sorted(spans, key=lambda item: (item.get("tid", 0), item["ts"])):
        lane = int(event.get("tid", 0))
        x = left + (event["ts"] - start) / duration * plot_width
        rect_width = max(0.8, event.get("dur", 0) / duration * plot_width)
        y = 37 + lane_index[lane] * row_height
        stage = stage_of(event)
        title = html.escape(
            f'{event.get("name", "")} — {event.get("dur", 0) / 1_000_000:.3f}s'
        )
        svg.append(
            f'<rect x="{x:.2f}" y="{y}" width="{rect_width:.2f}" height="19" '
            f'rx="2" fill="{color_for(stage)}"><title>{title}</title></rect>'
        )

    stage_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['stage'])}</td>"
        f"<td>{item['count']}</td>"
        f"<td>{item['total_seconds']:.3f}</td>"
        f"<td>{item['max_seconds']:.3f}</td>"
        "</tr>"
        for item in metrics["stages"]
    )
    top_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['name'])}</td>"
        f"<td>{item['lane']}</td>"
        f"<td>{item['seconds']:.3f}</td>"
        "</tr>"
        for item in metrics["longest_spans"]
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LLGo etcdctl {html.escape(metrics['mode'])} build profile</title>
<style>
body {{ font: 14px/1.45 system-ui, sans-serif; margin: 24px; color: #111827; }}
h1, h2 {{ margin: 0.7em 0 0.35em; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(155px,1fr)); gap: 12px; }}
.card {{ border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; background: #f9fafb; }}
.value {{ font-size: 24px; font-weight: 650; }}
.timeline {{ overflow-x: auto; border: 1px solid #d1d5db; border-radius: 8px; background: white; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 7px 14px; margin: 8px 0 12px; }}
.legend-item {{ display: inline-flex; align-items: center; gap: 5px; }}
.swatch {{ width: 12px; height: 12px; border-radius: 2px; }}
svg {{ min-width: 1100px; width: 100%; height: auto; display: block; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #e5e7eb; padding: 7px 9px; text-align: left; }}
th {{ background: #f3f4f6; }}
code {{ background: #f3f4f6; padding: 2px 4px; border-radius: 4px; }}
.note {{ color: #4b5563; }}
</style>
</head>
<body>
<h1>LLGo etcdctl {html.escape(metrics['mode'])} build</h1>
<p class="note">Requested parallelism: <code>{html.escape(metrics['requested_parallelism'])}</code>;
trace capacity: {metrics['trace_capacity']} worker lane(s). The raw
<a href="trace.json">trace.json</a> can be loaded into
<a href="https://ui.perfetto.dev/">Perfetto</a>.</p>
<div class="cards">
  <div class="card"><div>Measured wall time</div><div class="value">{metrics['wall_seconds']:.2f}s</div></div>
  <div class="card"><div>Trace duration</div><div class="value">{metrics['trace_seconds']:.2f}s</div></div>
  <div class="card"><div>Maximum active workers</div><div class="value">{metrics['max_active_workers']}</div></div>
  <div class="card"><div>Average active workers</div><div class="value">{metrics['average_active_workers']:.2f}</div></div>
  <div class="card"><div>Worker utilization</div><div class="value">{metrics['worker_utilization_percent']:.1f}%</div></div>
  <div class="card"><div>Time with 2+ workers</div><div class="value">{metrics['parallel_time_percent']:.1f}%</div></div>
</div>
<h2>Timeline</h2>
<p class="note">Colors identify trace stages only; they do not encode status or utilization. Hover over a span for its name and duration.</p>
<div class="legend">{legend}</div>
<div class="timeline"><svg viewBox="0 0 {width} {height}" role="img">
{''.join(svg)}
</svg></div>
<h2>Stages</h2>
<table><thead><tr><th>Stage</th><th>Spans</th><th>Total worker-seconds</th><th>Longest span</th></tr></thead>
<tbody>{stage_rows}</tbody></table>
<h2>Longest spans</h2>
<table><thead><tr><th>Span</th><th>Lane</th><th>Duration</th></tr></thead>
<tbody>{top_rows}</tbody></table>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--requested-parallelism", required=True)
    parser.add_argument("--wall-seconds", required=True, type=float)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown", required=True, type=Path)
    parser.add_argument("--html", required=True, type=Path)
    args = parser.parse_args()

    events = json.loads(args.trace.read_text(encoding="utf-8"))
    spans = [
        event for event in events
        if event.get("ph") == "X" and isinstance(event.get("ts"), (int, float))
    ]
    if not spans:
        raise SystemExit("trace contains no complete spans")
    worker_spans = [event for event in spans if int(event.get("tid", 0)) > 0]
    worker_lanes = {
        int(event.get("tid", 0)) for event in events
        if event.get("ph") == "M" and event.get("name") == "thread_name"
        and int(event.get("tid", 0)) > 0
    }
    capacity = len(worker_lanes) or len({int(event.get("tid", 0)) for event in worker_spans})

    build_spans = [event for event in spans if event.get("name") == "build"]
    window = max(build_spans, key=lambda event: event.get("dur", 0)) if build_spans else None
    if window:
        trace_start = window["ts"]
        trace_end = window["ts"] + window.get("dur", 0)
    else:
        trace_start = min(event["ts"] for event in spans)
        trace_end = max(event["ts"] + event.get("dur", 0) for event in spans)
    trace_duration = max(1, trace_end - trace_start)

    maximum, by_count = occupancy(worker_spans, trace_start, trace_end)
    active_area = sum(count * duration for count, duration in by_count.items())
    parallel_time = sum(duration for count, duration in by_count.items() if count >= 2)

    stages = collections.defaultdict(list)
    for event in worker_spans:
        stages[stage_of(event)].append(event.get("dur", 0))
    stage_metrics = sorted(
        (
            {
                "stage": stage,
                "count": len(durations),
                "total_seconds": rounded(sum(durations) / 1_000_000),
                "max_seconds": rounded(max(durations) / 1_000_000),
            }
            for stage, durations in stages.items()
        ),
        key=lambda item: (-item["total_seconds"], item["stage"]),
    )
    longest = sorted(spans, key=lambda event: event.get("dur", 0), reverse=True)[:20]

    metrics = {
        "mode": args.mode,
        "requested_parallelism": args.requested_parallelism,
        "wall_seconds": rounded(args.wall_seconds, 6),
        "trace_start_us": trace_start,
        "trace_duration_us": trace_duration,
        "trace_seconds": rounded(trace_duration / 1_000_000),
        "trace_capacity": capacity,
        "span_count": len(spans),
        "worker_span_count": len(worker_spans),
        "max_active_workers": maximum,
        "average_active_workers": rounded(active_area / trace_duration),
        "worker_utilization_percent": rounded(
            active_area / (trace_duration * capacity) * 100 if capacity else 0
        ),
        "parallel_time_percent": rounded(parallel_time / trace_duration * 100),
        "stages": stage_metrics,
        "longest_spans": [
            {
                "name": str(event.get("name", "")),
                "lane": int(event.get("tid", 0)),
                "seconds": rounded(event.get("dur", 0) / 1_000_000),
            }
            for event in longest
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(
        "\n".join(
            [
                f"### {args.mode.capitalize()} etcdctl build",
                "",
                "| Metric | Value |",
                "|---|---:|",
                f"| Measured wall time | {metrics['wall_seconds']:.3f} s |",
                f"| Trace duration | {metrics['trace_seconds']:.3f} s |",
                f"| Trace worker capacity | {capacity} |",
                f"| Maximum active workers | {maximum} |",
                f"| Average active workers | {metrics['average_active_workers']:.3f} |",
                f"| Worker utilization | {metrics['worker_utilization_percent']:.1f}% |",
                f"| Trace time with 2+ workers | {metrics['parallel_time_percent']:.1f}% |",
                f"| Worker spans | {len(worker_spans)} |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    render_html(metrics, spans, args.html)


if __name__ == "__main__":
    main()
