#!/usr/bin/env python3
"""Render benchmark results as comparison tables (stdout + markdown report).

Reads benchmarks/results/<run_id>/ directories produced by
playbooks/benchmark.yml (see docs/benchmarking.md), prints markdown tables per
run, writes each run's report to benchmarks/results/<run_id>/README.md (so
GitHub renders it inside the run's folder) and an index to
benchmarks/results/README.md. Runs are
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
INDEX_PATH = RESULTS_DIR / "README.md"

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
    ("total_input_tokens", "in tok"),
    ("total_output_tokens", "out tok"),
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
| in tok / out tok | Total tokens processed in that run: prompt tokens sent (prefill work) / tokens generated (decode work). Multi-turn runs are not included — see their own reports. |
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
            # Real model identity: basename of the served model_id
            # (e.g. /models/gemma-4-26b-a4b-it-awq-4bit); the filename part is
            # just the instance alias.
            model_id = (data.get("model_id") or "").rstrip("/").rsplit("/", 1)[-1]
            results.append({**m.groupdict(), "model": model_id or m.group("name"), "data": data})
        multiturn = sorted(p.name for p in run_dir.glob("multiturn-*.txt"))
        runs.append({"run_id": run_dir.name, "meta": meta, "config_id": config_id,
                     "results": results, "multiturn": multiturn})
    return runs


def fmt(key, value):
    if value is None:
        return "—"
    if key == "duration":
        return f"{value:,.0f}s"
    if key in ("total_input_tokens", "total_output_tokens"):
        return f"{int(value):,}"
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




def kv_mode(extra_args):
    """Human-readable KV offload mode from an instance's extra_args."""
    args = list(extra_args or [])
    if "--kv-offloading-backend" in args:
        try:
            size = args[args.index("--kv-offloading-size") + 1]
        except (ValueError, IndexError):
            size = "?"
        return f"native, {size} GB RAM"
    return "off"


def config_section(meta):
    """Static parameters of the run, documented once per summary."""
    out = ["\n### Configuration\n"]
    instances = meta.get("vllm_instances") or []
    if instances:
        out.append("| instance | model | context window | GPU mem fraction | KV offload | other flags |")
        out.append("|---|---|---|---|---|---|")
        kv_tokens = {"--kv-offloading-backend", "--kv-offloading-size"}
        for inst in instances:
            args = list(inst.get("extra_args") or [])
            other, skip = [], False
            for i, a in enumerate(args):
                if skip:
                    skip = False
                    continue
                if a in kv_tokens:
                    skip = True
                    continue
                other.append(a)
            model = (inst.get("model_path") or "?").rstrip("/").rsplit("/", 1)[-1]
            out.append(
                f"| {inst.get('name', '?')} | {model} | {int(inst.get('max_model_len', 0)):,} "
                f"| {inst.get('gpu_memory_utilization', '?')} | {kv_mode(args)} "
                f"| `{' '.join(other) or '—'}` |"
            )
    w = meta.get("workload") or {}
    if w:
        parts = [f"dataset={w.get('dataset', '?')}",
                 f"tiers={w.get('concurrency_tiers', '?')}",
                 f"prompts/user={w.get('prompts_per_user', '?')}",
                 f"seed={w.get('seed', '?')}",
                 f"scenarios={w.get('scenarios', '?')}"]
        if str(w.get("context_stress", "")).lower() in ("true", "1"):
            frac = float(w.get("context_input_fraction", 0.8))
            parts.append(f"context-stress inputs≈{frac:.0%} of window, {w.get('context_output_len', '?')} out")
        if str(w.get("multi_turn", "")).lower() in ("true", "1"):
            parts.append(f"multi-turn: {w.get('multi_turn_clients', '?')} clients / "
                         f"{w.get('multi_turn_num_conversations', '?')} conversations")
        out.append("\nworkload: " + " | ".join(parts))
    return out


def run_section(run):
    """One run's report body (returned as a list of markdown lines)."""
    out = []
    meta = run["meta"]
    out.append(
        f"profile: **{meta.get('profile_name', '?')}** | config: `{run['config_id']}` | "
        f"git: `{str(meta.get('repo_git_sha', '?'))[:10]}`"
        f"{' (dirty)' if meta.get('repo_git_dirty') else ''} | "
        f"host: {meta.get('host', {}).get('instance_type', '?')} "
        f"({meta.get('host', {}).get('gpu', '?')}) | "
        f"image: {meta.get('vllm_image', '?')} | "
        f"first run: {meta.get('timestamp_utc', '?')}"
    )
    out += config_section(meta)
    model_map = {r["name"]: r["model"] for r in run["results"]}
    if model_map:
        out.append("\nserved (observed): " + ", ".join(f"`{k}` = {v}" for k, v in sorted(model_map.items())))
    if run["results"]:
        total_dur = sum(r["data"].get("duration") or 0 for r in run["results"])
        total_in = sum(r["data"].get("total_input_tokens") or 0 for r in run["results"])
        total_out = sum(r["data"].get("total_output_tokens") or 0 for r in run["results"])
        headers = ["scenario", "model", "users"] + [label for _, label in METRIC_COLUMNS] + ["SLO"]
        out.append("\n| " + " | ".join(headers) + " |")
        out.append("|" + "---|" * len(headers))
        ordered = sorted(run["results"], key=lambda r: (r["scenario"], r["name"], int(r["tier"])))
        for r in ordered:
            row = [r["scenario"], r["model"], r["tier"]]
            row += [fmt(key, r["data"].get(key)) for key, _ in METRIC_COLUMNS]
            row.append(slo_verdict(r["scenario"], r["tier"], r["data"]))
            out.append("| " + " | ".join(row) + " |")
        out.append(
            f"\ntotals: {total_dur / 60:,.1f} min of benchmarked load across "
            f"{len(run['results'])} runs | {int(total_in):,} prompt tokens in | "
            f"{int(total_out):,} tokens generated"
        )
        run["totals"] = (total_dur, total_in, total_out)
    else:
        out.append("\n_(no parsed result files)_")
        run["totals"] = (0, 0, 0)
    if run["multiturn"]:
        out.append(f"\nmulti-turn reports: {', '.join('`' + m + '`' for m in run['multiturn'])}")
    return out


def render(runs):
    stdout_parts = []
    for run in runs:
        section = run_section(run)
        report = "\n".join([f"# {run['run_id']}", "", LEGEND, ""] + section) + "\n"
        per_run_path = RESULTS_DIR / run["run_id"] / "README.md"
        per_run_path.write_text(report)
        stdout_parts.append("\n".join([f"\n## {run['run_id']}\n"] + section))
        print(f"(report written to {per_run_path})", file=sys.stderr)

    # Index: one line per run, plus the cross-config warnings.
    index = ["# Benchmark results index", "",
             "Per-run reports (tables + legend) live in each run's own `README.md`.", "",
             "| run | profile | models | config | runs | load time | tokens in/out |", "|---|---|---|---|---|---|---|"]
    for run in runs:
        dur, tin, tout = run["totals"]
        models = ", ".join(sorted({r["model"] for r in run["results"]})) or "—"
        index.append(
            f"| [{run['run_id']}]({run['run_id']}/README.md) | {run['meta'].get('profile_name', '?')} "
            f"| {models} | `{run['config_id']}` | {len(run['results'])} | {dur / 60:,.1f} min "
            f"| {int(tin):,} / {int(tout):,} |"
        )
    by_name = {}
    for run in runs:
        by_name.setdefault(run["meta"].get("profile_name", "?"), set()).add(run["config_id"])
    warnings = []
    for name, configs in sorted(by_name.items()):
        if len(configs) > 1:
            warnings.append(
                f"\n**WARNING**: profile '{name}' appears with {len(configs)} different applied "
                f"configs ({', '.join(sorted(configs))}) — do not compare across them."
            )
    index += warnings
    INDEX_PATH.write_text("\n".join(index) + "\n")

    print("\n".join(["# Benchmark results", "", LEGEND] + stdout_parts + warnings))
    print(f"(index written to {INDEX_PATH})", file=sys.stderr)


if __name__ == "__main__":
    render(load_runs(only=set(sys.argv[1:]) or None))
