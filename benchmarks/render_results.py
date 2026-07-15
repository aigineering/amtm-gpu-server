#!/usr/bin/env python3
"""Render benchmark results as comparison tables.

Reads benchmarks/results/<run_id>/ directories produced by
playbooks/benchmark.yml (see docs/benchmarking.md) and prints a markdown
table per scenario, grouped so that runs with differing applied configs are
never silently merged: the grouping key is the sha256 of the run's compose
snapshot (the config actually applied on the host), not the profile name.

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

# vllm bench serve result filenames: <scenario>-<instance>-c<tier>.json
FILENAME_RE = re.compile(r"^(?P<scenario>solo|colocated)-(?P<name>.+)-c(?P<tier>\d+)\.json$")

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
]

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
        runs.append({"run_id": run_dir.name, "meta": meta, "config_id": config_id, "results": results})
    return runs


def fmt(value):
    if value is None:
        return "—"
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
    for run in runs:
        meta = run["meta"]
        print(f"\n## {run['run_id']}")
        print(
            f"profile: **{meta.get('profile_name', '?')}** | config: `{run['config_id']}` | "
            f"git: `{str(meta.get('repo_git_sha', '?'))[:10]}`"
            f"{' (dirty)' if meta.get('repo_git_dirty') else ''} | "
            f"host: {meta.get('host', {}).get('instance_type', '?')} "
            f"({meta.get('host', {}).get('gpu', '?')}) | "
            f"image: {meta.get('vllm_image', '?')}"
        )
        if not run["results"]:
            print("\n_(no parsed result files — multi-turn output is plain text, see the .txt files)_")
            continue
        headers = ["scenario", "model", "users"] + [label for _, label in METRIC_COLUMNS] + ["SLO"]
        print("\n| " + " | ".join(headers) + " |")
        print("|" + "---|" * len(headers))
        ordered = sorted(run["results"], key=lambda r: (r["scenario"], r["name"], int(r["tier"])))
        for r in ordered:
            row = [r["scenario"], r["name"], r["tier"]]
            row += [fmt(r["data"].get(key)) for key, _ in METRIC_COLUMNS]
            row.append(slo_verdict(r["scenario"], r["tier"], r["data"]))
            print("| " + " | ".join(row) + " |")

    # Warn when the same profile name maps to different applied configs.
    by_name = {}
    for run in runs:
        by_name.setdefault(run["meta"].get("profile_name", "?"), set()).add(run["config_id"])
    for name, configs in by_name.items():
        if len(configs) > 1:
            print(
                f"\nWARNING: profile '{name}' appears with {len(configs)} different applied "
                f"configs ({', '.join(sorted(configs))}) — do not compare across them.",
                file=sys.stderr,
            )


if __name__ == "__main__":
    render(load_runs(only=set(sys.argv[1:]) or None))
