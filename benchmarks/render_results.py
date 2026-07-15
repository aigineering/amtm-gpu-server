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

import base64
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
| SLO | PASS/FAIL against the working targets (docs/benchmarking.md): TTFT p95 ≤ 1.5s (≤2.5s at 50 users) AND ITL p95 ≤ 100ms. Evaluated on every row; read per scenario — `colocated` is the binding product judgment, `solo` is a model's standalone ceiling, and `context`/`contextpair` failing at high tiers is the expected capacity cliff (worst-case probe), not a defect |

**Multi-turn conversations table** (conversation replay with growing history —
prefix-cache and KV-offloading behavior): parsed from the harness reports.
Columns: req/s (completed turns per second); TTFT/TPOT/e2e mean/tail in ms
(tail = p99, falling back to p90 or max when small runs omit percentiles);
input tokens per request mean/max (how deep conversations grew); approximate
total tokens in/out (count × mean); **ext cache hit** — external (offloaded)
prefix-cache hit rate for that tier (Δhits/Δqueries vs the previous snapshot;
requires KV offloading); **KV stored/loaded** — GB pushed to / pulled back
from CPU RAM during that tier (per-tier delta vs the c0 baseline snapshot).
Raw reports remain in `multiturn-*.txt`.
"""

# Working SLOs from docs/benchmarking.md (co-located scenario is what counts).
SLO_TTFT_P95_MS = {1: 1500, 5: 1500, 20: 1500, 50: 2500}
SLO_ITL_P95_MS = 100




MULTITURN_FILE_RE = re.compile(r"^multiturn-(?P<name>.+)-c(?P<clients>\d+)\.txt$")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def parse_multiturn(path):
    """Parse the multi-turn harness's stdout report; None if it isn't one.

    Column-agnostic: reads the header row (count/mean/std/min/…/max) instead of
    assuming a fixed percentile set, and strips ANSI colors first.
    """
    text = ANSI_RE.sub("", path.read_text(errors="replace"))
    if "Statistics summary" not in text:
        return None  # failed run or unexpected format — leave as a raw file
    stats = {"rows": {}}
    for key in ("runtime_sec", "requests_per_sec"):
        m = re.search(rf"^{key} = ([\d.]+)", text, re.MULTILINE)
        if m:
            stats[key] = float(m.group(1))
    header = None
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if header is None:
            if parts[0] == "count":
                # normalize: 25% -> p25, 99% -> p99; count/mean/std/min/max as-is
                header = [("p" + p[:-1]) if p.endswith("%") else p for p in parts]
            continue
        if len(parts) == len(header) + 1 and re.fullmatch(r"[a-z_]+", parts[0]):
            row = {}
            for i, value in enumerate(parts[1:]):
                # pandas truncates wide tables with a literal "..." column when
                # stdout is not a terminal — skip the marker, keep what exists.
                if header[i] == "..." or value == "...":
                    continue
                try:
                    row[header[i]] = float(value.replace(",", ""))
                except ValueError:
                    pass
            if row:
                stats["rows"][parts[0]] = row
    return stats if stats["rows"] else None




HTML_STYLE = """<style>
body { font-family: -apple-system, 'Segoe UI', sans-serif; margin: 2em auto; max-width: 1400px; padding: 0 1em; color: #1a1a1a; }
table { border-collapse: collapse; margin: 1em 0; font-size: 13px; }
th, td { border: 1px solid #d0d7de; padding: 4px 10px; text-align: left; white-space: nowrap; }
th { background: #f6f8fa; }
tr:nth-child(even) { background: #fafbfc; }
code { background: #f6f8fa; padding: 1px 5px; border-radius: 4px; font-size: 12px; }
h1, h2, h3 { border-bottom: 1px solid #eee; padding-bottom: 4px; }
.pass { color: #1a7f37; font-weight: 600; }
.fail { color: #cf222e; font-weight: 600; }
</style>"""

MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def md_inline(text):
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = MD_LINK_RE.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    return text


def md_to_html(md, title):
    """Just enough markdown->HTML for the reports this script generates."""
    lines, out, table = md.splitlines(), [], []

    def flush_table():
        if not table:
            return
        out.append("<table>")
        for i, cells in enumerate(table):
            tag = "th" if i == 0 else "td"
            row_html = []
            for c in cells:
                cls = ' class="pass"' if c == "PASS" else (' class="fail"' if c == "FAIL" else "")
                row_html.append(f"<{tag}{cls}>{md_inline(c)}</{tag}>")
            out.append("<tr>" + "".join(row_html) + "</tr>")
        out.append("</table>")
        table.clear()

    for line in lines:
        s = line.strip()
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", c) for c in cells):
                continue  # separator row
            table.append(cells)
            continue
        flush_table()
        m = re.match(r"^(#{1,6})\s+(.*)", s)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{md_inline(m.group(2))}</h{level}>")
        elif s:
            out.append(f"<p>{md_inline(s)}</p>")
    flush_table()
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title>"
            f"{HTML_STYLE}</head><body>" + "\n".join(out) + "</body></html>")


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
        # Hash the DECODED (and already key-redacted) compose text — same
        # digest the benchmark role uses for the run directory suffix.
        compose_b64 = meta.get("compose_file_b64", "")
        config_id = (hashlib.sha256(base64.b64decode(compose_b64)).hexdigest()[:10]
                     if compose_b64 else "unknown")
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
        multiturn = []
        for p in sorted(run_dir.glob("multiturn-*.txt")):
            if p.name.endswith(".metrics.txt"):
                continue  # /metrics snapshots, not harness reports
            fm = MULTITURN_FILE_RE.match(p.name)
            multiturn.append({"file": p.name,
                              "name": fm.group("name") if fm else p.name,
                              "clients": fm.group("clients") if fm else "?",
                              "stats": parse_multiturn(p),
                              "counters": parse_offload_counters(
                                  p.with_name(p.name[:-4] + ".metrics.txt"))})
        runs.append({"run_id": run_dir.name, "meta": meta, "config_id": config_id,
                     "results": results, "multiturn": multiturn,
                     "kvpool": parse_kvpool(run_dir)})
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
    """Pass/fail against the working SLOs — evaluated for every scenario.

    Interpretation differs by scenario (see legend): colocated is the binding
    product judgment; solo shows a model's standalone ceiling; context rows
    failing at high tiers is the expected capacity cliff, not a defect.
    """
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


KVPOOL_TOKENS_RE = re.compile(r"GPU KV cache size:\s*([\d,]+)\s*tokens")
KVPOOL_CONC_RE = re.compile(r"Maximum concurrency for\s*([\d,]+)\s*tokens per request:\s*([\d.]+)x")
KVPOOL_GIB_RE = re.compile(r"Available KV cache memory:\s*([\d.]+)\s*GiB")


OFFLOAD_COUNTERS = {
    "stored": r"vllm:kv_offload_store_bytes_total\{[^}]*\}\s+([\d.e+]+)",
    "loaded": r"vllm:kv_offload_load_bytes_total\{[^}]*\}\s+([\d.e+]+)",
    "hits": r"vllm:external_prefix_cache_hits_total\{[^}]*\}\s+([\d.e+]+)",
    "queries": r"vllm:external_prefix_cache_queries_total\{[^}]*\}\s+([\d.e+]+)",
}


def parse_offload_counters(path):
    """Cumulative offload/external-cache counters from a /metrics snapshot."""
    if not path.exists():
        return None
    text = path.read_text(errors="replace")
    out = {}
    for key, pattern in OFFLOAD_COUNTERS.items():
        if m := re.search(pattern, text):
            out[key] = float(m.group(1))
    return out or None


def parse_kvpool(run_dir):
    """Per-instance KV capacity figures scraped from engine startup logs."""
    pools = {}
    for p in sorted(run_dir.glob("kvpool-*.txt")):
        name = p.name[len("kvpool-"):-len(".txt")]
        text = p.read_text(errors="replace")
        entry = {}
        if m := KVPOOL_TOKENS_RE.search(text):
            entry["tokens"] = int(m.group(1).replace(",", ""))
        if m := KVPOOL_GIB_RE.search(text):
            entry["gib"] = float(m.group(1))
        if m := KVPOOL_CONC_RE.search(text):
            entry["conc"] = f"{m.group(2)}x @ {m.group(1)}"
        if entry:
            pools[name] = entry
    return pools


def config_section(meta, kvpool=None):
    """Static parameters of the run, documented once per summary."""
    out = ["\n### Configuration\n"]
    instances = meta.get("vllm_instances") or []
    if instances:
        out.append("| instance | model | context window | GPU mem fraction | KV pool | max conc @ctx | KV offload | other flags |")
        out.append("|---|---|---|---|---|---|---|---|")
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
            pool = (kvpool or {}).get(inst.get("name"), {})
            pool_str = (f"{pool['tokens']:,} tok" + (f" ({pool['gib']:.1f} GiB)" if "gib" in pool else "")) \
                if "tokens" in pool else "—"
            out.append(
                f"| {inst.get('name', '?')} | {model} | {int(inst.get('max_model_len', 0)):,} "
                f"| {inst.get('gpu_memory_utilization', '?')} | {pool_str} | {pool.get('conc', '—')} "
                f"| {kv_mode(args)} | `{' '.join(other) or '—'}` |"
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
            if "multi_turn_tiers" in w:
                parts.append(
                    f"multi-turn: tiers {w['multi_turn_tiers']} × "
                    f"{w.get('multi_turn_conversations_per_client', '?')} conv/client, "
                    f"{w.get('multi_turn_turns', '?')} turns")
            else:  # records written before the tier sweep existed
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
    out += config_section(meta, run.get("kvpool"))
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
    parsed = [m for m in run["multiturn"] if m["stats"]]
    unparsed = [m for m in run["multiturn"] if not m["stats"] and not m["file"].endswith("-c0.metrics.txt")]
    if parsed:
        parsed.sort(key=lambda m: (m["name"], int(m["clients"]) if str(m["clients"]).isdigit() else 0))
        # cumulative counters -> per-tier deltas, using the c0 baseline snapshot
        baselines = {m["name"]: m["counters"] for m in run["multiturn"]
                     if m["file"].endswith("-c0.metrics.txt") and m["counters"]}
        out.append("\n### Multi-turn conversations\n")
        out.append("| instance | clients | req/s | TTFT mean/tail | TPOT mean/tail | e2e mean/tail "
                   "| input tok mean/max | ≈tok in/out total | ext cache hit | KV stored/loaded | runtime |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        prev_counters = dict(baselines)
        for m in parsed:
            s = m["stats"]
            r = s["rows"]

            def pair(label):
                row = r.get(label) or {}
                mean = row.get("mean")
                # small runs: the harness's table omits 99% — fall back p99 -> p90 -> max
                tail = row.get("p99", row.get("p90", row.get("max")))
                left = f"{mean:,.0f}" if mean is not None else "—"
                right = f"{tail:,.0f}" if tail is not None else "—"
                return f"{left} / {right}"

            itok = r.get("input_num_tokens")
            otok = r.get("output_num_tokens")
            tin = f"{int(itok['count'] * itok['mean']):,}" if itok else "—"
            tout = f"{int(otok['count'] * otok['mean']):,}" if otok else "—"
            imeanmax = f"{itok['mean']:,.0f} / {itok['max']:,.0f}" if itok else "—"

            hit, kv = "—", "—"
            cur, base = m["counters"], prev_counters.get(m["name"])
            if cur and base:
                dq = cur.get("queries", 0) - base.get("queries", 0)
                dh = cur.get("hits", 0) - base.get("hits", 0)
                ds = cur.get("stored", 0) - base.get("stored", 0)
                dl = cur.get("loaded", 0) - base.get("loaded", 0)
                if dq > 0:
                    hit = f"{dh / dq:.1%}"
                if "stored" in cur or "loaded" in cur:
                    kv = f"{ds / 1e9:.2f} / {dl / 1e9:.2f} GB"
            if cur:
                prev_counters[m["name"]] = cur
            out.append(
                f"| {m['name']} | {m['clients']} | {s.get('requests_per_sec', 0):.2f} "
                f"| {pair('ttft_ms')} | {pair('tpot_ms')} | {pair('latency_ms')} "
                f"| {imeanmax} | {tin} / {tout} | {hit} | {kv} | {s.get('runtime_sec', 0):,.0f}s |"
            )
    if unparsed:
        out.append("\nunparsed multi-turn files (failed or unexpected format): "
                   + ", ".join("`" + m["file"] + "`" for m in unparsed))
    return out


def render(runs):
    stdout_parts = []
    for run in runs:
        section = run_section(run)
        report = "\n".join([f"# {run['run_id']}", "", LEGEND, ""] + section) + "\n"
        per_run_path = RESULTS_DIR / run["run_id"] / "README.md"
        per_run_path.write_text(report)
        (RESULTS_DIR / run["run_id"] / "report.html").write_text(
            md_to_html(report, run["run_id"]))
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
    index_md = "\n".join(index) + "\n"
    INDEX_PATH.write_text(index_md)
    (RESULTS_DIR / "index.html").write_text(md_to_html(index_md, "benchmark results index"))

    print("\n".join(["# Benchmark results", "", LEGEND] + stdout_parts + warnings))
    print(f"(index written to {INDEX_PATH})", file=sys.stderr)


if __name__ == "__main__":
    render(load_runs(only=set(sys.argv[1:]) or None))
