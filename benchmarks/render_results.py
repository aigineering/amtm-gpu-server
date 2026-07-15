#!/usr/bin/env python3
"""Render benchmark results as comparison tables (stdout + markdown report).

Reads benchmarks/results/<run_id>/ directories produced by
playbooks/benchmark.yml (see docs/benchmarking.md), prints markdown tables per
run, and writes the same report to benchmarks/results/README.md. Runs are
grouped so differing applied configs are never silently merged: the grouping
key is the sha256 of the run's compose snapshot (the config actually applied
on the host), not the profile name.

Usage:
    python3 benchmarks/render_results.py            # all runs
    python3 benchmarks/render_results.py <run_id>…  # only these runs

Stdlib only — no dependencies.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
REPORT_PATH = RESULTS_DIR / "README.md"

# vllm bench serve result filenames: <scenario>-<instance>-c<tier>.json
# context = solo long-input capacity run; contextpair = both endpoints at once.
FILENAME_RE = re.compile(r"^(?P<scenario>solo|colocated|context|contextpair)-(?P<name>.+)-c(?P<tier>\d+)\.json$")

# Metric keys we surface if present (tolerant to vllm version differences).
METRIC_COLUMNS = [
    ("p50_ttft_ms", "TTFT p50"),
    ("p95_ttft_ms", "TTFT p95"),
    ("p99_ttft_ms", "TTFT p99"),
    ("p95_itl_ms", "ITL p95"),
    ("p95_tpot_ms", "TPOT p95"),
    ("p95_e2el_ms", "E2E p95"),
    ("output_throughput", "out tok/s"),
    ("request_throughput", "req/s"),
    ("duration", "run dur"),
]

LEGEND = """\
### Legend

**Scenarios**

| Scenario | Meaning |
|---|---|
| `solo` | Model alone on the GPU (other instances stopped) — per-model best case. ShareGPT workload (realistic short chat). |
| `colocated` | All models serving, load driven against every endpoint simultaneously — the production topology. ShareGPT workload. SLO verdicts are judged here. |
| `context` | Solo capacity probe: random long inputs at ~80% of the model's context window, zero prefix reuse (worst-case KV pressure). |
| `contextpair` | Same long-input probe against all endpoints at once — "does this context + all models fit, at how many users". |

**Columns**

| Column | Meaning |
|---|---|
| users | Concurrent simulated users (per model) for that row |
| TTFT p50/p95/p99 | Time to first token, ms — perceived responsiveness ("is it thinking?") at the median / 95th / 99th percentile |
| ITL p95 | Inter-token latency, ms — streaming smoothness; ≤100ms ≈ ≥10 tok/s per user, comfortably above reading speed |
| TPOT p95 | Time per output token, ms — close cousin of ITL, includes scheduling effects |
| E2E p95 | Full request latency, ms — complete answer time |
| out tok/s | Aggregate output token throughput across all users (capacity) |
| req/s | Completed requests per second (capacity in user terms) |
| run dur | Wall-clock duration of that benchmark run, seconds |
| SLO | PASS/FAIL against the working targets (docs/benchmarking.md) — only judged on `colocated` rows: TTFT p95 ≤ 1.5s (≤2.5s at 50 users) AND ITL p95 ≤ 100ms |

Multi-turn results (conversation replay with growing history — prefix-cache
and KV-offloading behavior) are plain-text harness reports: see the
`multiturn-*.txt` files inside each run directory.
"""

# Working SLOs from docs/benchmarking.md (co-located scenario is what counts).
SLO_TTFT_P95_MS = {1: 1500, 5: 1500, 20: 1500, 50: 2500}
SLO_ITL_P95_MS = 100


def load_runs(only=None):
    runs = []
    if not RESULTS_DIR.is_dir():
        sys.exit(f"no results directory at {RESULTS_DIR}")
    for run_dir in sorted(RESULTS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        if only and run_dir.name not in only:
            continue
        meta_path = run_dir / "metadata.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        compose_b64 = meta.get("compose_file_b64", "")
        config_id = hashlib.sha256(compose_b64.encode()).hexdigest()[:10] if compose_b64 else "unknown"
        results = []
        for f in sorted(run_dir.glob("*.json")):
            m = FILENAME_RE.match(f.name)
            if not m:
                continue
            try:
                data = json.loads(f.read_text())
            except json.JSONDecodeError:
                print(f"warning: unparseable {f}", file=sys.stderr)
                continue
            results.append({**m.groupdict(), "data": data})
        multiturn = sorted(p.name for p in run_dir.glob("multiturn-*.txt"))
        runs.append({"run_id": run_dir.name, "meta": meta, "config_id": config_id,
                     "results": results, "multiturn": multiturn})
    return runs


def fmt(key, value):
    if value is None:
        return "—"
    if key == "duration":
        return f"{value:,.0f}s"
    if isinstance(value, float):
        return f"{value:,.1f}"
    return str(value)


def slo_verdict(scenario, tier, data):
    """Pass/fail against the working SLOs — judged on the co-located scenario."""
    if scenario != "colocated":
        return ""
    ttft = data.get("p95_ttft_ms")
    itl = data.get("p95_itl_ms")
    if ttft is None or itl is None:
        return "?"
    ok = ttft <= SLO_TTFT_P95_MS.get(int(tier), 2500) and itl <= SLO_ITL_P95_MS
    return "PASS" if ok else "FAIL"


def render(runs):
    out = ["# Benchmark results", "", LEGEND]
    for run in runs:
        meta = run["meta"]
        out.append(f"\n## {run['run_id']}\n")
        out.append(
            f"profile: **{meta.get('profile_name', '?')}** | config: `{run['config_id']}` | "
            f"git: `{str(meta.get('repo_git_sha', '?'))[:10]}`"
            f"{' (dirty)' if meta.get('repo_git_dirty') else ''} | "
            f"host: {meta.get('host', {}).get('instance_type', '?')} "
            f"({meta.get('host', {}).get('gpu', '?')}) | "
            f"image: {meta.get('vllm_image', '?')} | "
            f"first run: {meta.get('timestamp_utc', '?')}"
        )
        if run["results"]:
            total_dur = sum(r["data"].get("duration") or 0 for r in run["results"])
            headers = ["scenario", "model", "users"] + [label for _, label in METRIC_COLUMNS] + ["SLO"]
            out.append("\n| " + " | ".join(headers) + " |")
            out.append("|" + "---|" * len(headers))
            ordered = sorted(run["results"], key=lambda r: (r["scenario"], r["name"], int(r["tier"])))
            for r in ordered:
                row = [r["scenario"], r["name"], r["tier"]]
                row += [fmt(key, r["data"].get(key)) for key, _ in METRIC_COLUMNS]
                row.append(slo_verdict(r["scenario"], r["tier"], r["data"]))
                out.append("| " + " | ".join(row) + " |")
            out.append(f"\ntotal benchmarked load time: {total_dur / 60:,.1f} min "
                       f"across {len(run['results'])} runs")
        else:
            out.append("\n_(no parsed result files)_")
        if run["multiturn"]:
            out.append(f"\nmulti-turn reports: {', '.join('`' + m + '`' for m in run['multiturn'])}")

    # Warn when the same profile name maps to different applied configs.
    by_name = {}
    for run in runs:
        by_name.setdefault(run["meta"].get("profile_name", "?"), set()).add(run["config_id"])
    for name, configs in sorted(by_name.items()):
        if len(configs) > 1:
            out.append(
                f"\n**WARNING**: profile '{name}' appears with {len(configs)} different applied "
                f"configs ({', '.join(sorted(configs))}) — do not compare across them."
            )

    text = "\n".join(out) + "\n"
    print(text)
    REPORT_PATH.write_text(text)
    print(f"(report written to {REPORT_PATH})", file=sys.stderr)


if __name__ == "__main__":
    render(load_runs(only=set(sys.argv[1:]) or None))
