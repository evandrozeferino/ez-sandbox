#!/usr/bin/env python3
"""lab_report.py: turns a week's captured folder into tables and charts. Runs on the Mac.

  python3 lab_report.py w1 <folder>   # folder = the unpacked w1/ from w1.tgz
  python3 lab_report.py w2 <folder>   # folder = the unpacked w2/ from w2.tgz
  python3 lab_report.py w2 w2 --extra lever/w2   # merge in the lever run's capture
  options: --rate 1.59 (GPU $/hr paid)  --out <dir> (default: the folder's parent)

Writes, next to the record:
  w1: w1_report.md, w1_timeline.png
  w2: w2_report.md, w2_saturation.png, w2_timeline.png

Every number comes from the benchmark JSONs, the before/after counter snapshots,
the monitor's watch.csv and the runner's events.tsv. Nothing is typed by hand.
Medians across repeats; spread = (max - min) / median.
Charts need matplotlib; the tables do not.
"""
import argparse
import csv
import glob
import json
import os
import re
import statistics as st
import sys

# W1 v1, hand run 21 Sep 2026, original runs (W1_Baseline_Record.md)
V1 = {
    "A": {"output_throughput": 2459.41, "total_token_throughput": 2766.84, "mean_ttft_ms": 184.38,
          "p95_ttft_ms": 330.07, "mean_tpot_ms": 11.47, "p95_tpot_ms": 11.60},
    "B": {"output_throughput": 212.03, "total_token_throughput": 13782.05, "mean_ttft_ms": 1414.33,
          "p95_ttft_ms": 5394.40, "mean_tpot_ms": 120.32, "p95_tpot_ms": 131.99},
    "C": {"output_throughput": 2434.07, "total_token_throughput": 4868.14, "mean_ttft_ms": 110.13,
          "p95_ttft_ms": 176.11, "mean_tpot_ms": 11.56, "p95_tpot_ms": 11.65},
}
SHAPE_NAME = {"A": "A, decode-heavy, 128 in / 1024 out", "B": "B, prefill-heavy, 4096 in / 64 out",
              "C": "C, balanced, 512 in / 512 out"}


# ---------------------------------------------------------------- loading

def read_metrics(path):
    out = {}
    if os.path.exists(path):
        for line in open(path):
            m = re.match(r"^(vllm:[a-zA-Z_:]+)(\{[^}]*\})?\s+([0-9.eE+-]+|NaN)$", line.strip())
            if m:
                out[(m.group(1), m.group(2) or "")] = float(m.group(3))
    return out


def total(m, name, label=None):
    return sum(v for (n, l), v in m.items() if n == name and (label is None or label in l))


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_many(folders):
    """Merge several captured folders (e.g. w2/ and the lever run's w2/)."""
    runs, watch, windows = {}, [], {}
    for fo in folders:
        r, w, wi = load(fo)
        for k, v in r.items():
            runs.setdefault(k, v)
        windows.update(wi)
        watch += w
    seen, uniq = set(), []
    for r in sorted(watch, key=lambda x: x.get("t") or 0):
        if r.get("t") not in seen:
            seen.add(r.get("t"))
            uniq.append(r)
    return runs, uniq, windows


def load(folder):
    ev_path = os.path.join(folder, "events.tsv")
    windows = {}
    if os.path.exists(ev_path):
        starts = {}
        for line in open(ev_path):
            p = line.rstrip("\n").split("\t")
            if len(p) < 4:
                continue
            t, kind, tag = float(p[0]), p[2], p[3]
            if kind == "START":
                starts[tag] = t
            elif kind == "END" and tag in starts:
                windows[tag] = (starts[tag], t)
    watch = []
    wp = os.path.join(folder, "watch.csv")
    if os.path.exists(wp):
        with open(wp) as fh:
            for r in csv.DictReader(fh):
                if r.get("t") == "t":  # header repeated after a monitor restart
                    continue
                watch.append({k: fnum(v) for k, v in r.items() if k != "utc"})
    runs = {}
    for jp in sorted(glob.glob(os.path.join(folder, "json", "*.json"))):
        tag = os.path.splitext(os.path.basename(jp))[0]
        if tag.endswith(".failed"):
            continue
        run = {"tag": tag, "j": json.load(open(jp))}
        b = read_metrics(os.path.join(folder, "metrics", tag + "_before.txt"))
        a = read_metrics(os.path.join(folder, "metrics", tag + "_after.txt"))
        d = lambda n, l=None: total(a, n, l) - total(b, n, l)
        run["preempt"] = d("vllm:num_preemptions_total")
        run["hits"] = d("vllm:prefix_cache_hits_total")
        run["queries"] = d("vllm:prefix_cache_queries_total")
        qc = d("vllm:request_queue_time_seconds_count")
        run["queue_ms"] = 1000 * d("vllm:request_queue_time_seconds_sum") / qc if qc else None
        sc = d("vllm:iteration_tokens_total_count")
        run["tok_per_step"] = d("vllm:iteration_tokens_total_sum") / sc if sc else None
        if tag in windows:
            s, e = windows[tag]
            run["window"] = (s, e)
            sel = [r for r in watch if r.get("t") is not None and s <= r["t"] <= e]
            if sel:
                g = lambda k: [r[k] for r in sel if r.get(k) is not None]
                run["peak_running"] = max(g("running") or [0])
                run["peak_waiting"] = max(g("waiting") or [0])
                run["mean_waiting"] = st.mean(g("waiting") or [0])
                run["peak_kv"] = max(g("kv") or [0])
                run["mean_prefill_tps"] = st.mean(g("prefill_tps") or [0])
                run["mean_decode_tps"] = st.mean(g("decode_tps") or [0])
                run["samples"] = len(sel)
        runs[tag] = run
    return runs, watch, windows


# ---------------------------------------------------------------- helpers

def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def spread(xs):
    xs = [x for x in xs if x is not None]
    return (max(xs) - min(xs)) / st.median(xs) if len(xs) > 1 and st.median(xs) else None


def summarise(group, rate):
    J = lambda k: [r["j"].get(k) for r in group]
    R = lambda k: [r.get(k) for r in group]
    s = {
        "n": len(group),
        "ok": all(r["j"].get("completed") == r["j"].get("num_prompts") for r in group),
        "req_s": med(J("request_throughput")), "out_tps": med(J("output_throughput")),
        "tot_tps": med(J("total_token_throughput")),
        "mean_ttft": med(J("mean_ttft_ms")), "p50_ttft": med(J("median_ttft_ms")),
        "p95_ttft": med(J("p95_ttft_ms")), "p99_ttft": med(J("p99_ttft_ms")),
        "mean_tpot": med(J("mean_tpot_ms")), "p95_tpot": med(J("p95_tpot_ms")),
        "p95_itl": med(J("p95_itl_ms")), "mean_e2el": med(J("mean_e2el_ms")),
        "spread_tput": spread(J("total_token_throughput")), "spread_ttft": spread(J("p95_ttft_ms")),
        "peak_running": med(R("peak_running")), "peak_waiting": med(R("peak_waiting")),
        "mean_waiting": med(R("mean_waiting")), "peak_kv": med(R("peak_kv")),
        "tok_per_step": med(R("tok_per_step")), "queue_ms": med(R("queue_ms")),
        "preempt": sum(r["preempt"] for r in group), "hits": sum(r["hits"] for r in group),
        "queries": sum(r["queries"] for r in group),
    }
    s["cost_out"] = rate / (s["out_tps"] * 3600) * 1e6 if s["out_tps"] else None
    s["cost_tot"] = rate / (s["tot_tps"] * 3600) * 1e6 if s["tot_tps"] else None
    s["cost_1k_req"] = rate / (s["req_s"] * 3600) * 1000 if s["req_s"] else None
    return s


def f(x, fmt="{:,.0f}"):
    return "n/a" if x is None else fmt.format(x)


def pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def delta(new, old):
    return "n/a" if not new or not old else f"{100 * (new / old - 1):+.1f}%"


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" if i == 0 else "---:" for i in range(len(header))) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def mpl():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        print("matplotlib missing: python3 -m pip install --user matplotlib, then re-run for the charts.")
        return None


def timeline(plt, watch, windows, tags, path, title, pad=8):
    """One column per run: running/waiting, KV %, prefill vs decode tok/s, tokens/step."""
    tags = [t for t in tags if t in windows]
    if not tags or not watch:
        return
    fig, axes = plt.subplots(4, len(tags), figsize=(5.2 * len(tags), 10), squeeze=False, sharex="col")
    for col, tag in enumerate(tags):
        s, e = windows[tag]
        sel = [r for r in watch if r.get("t") and s - pad <= r["t"] <= e + pad]
        x = [r["t"] - s for r in sel]
        get = lambda k, scale=1: [(r.get(k) or 0) * scale for r in sel]
        ax = axes[0][col]
        ax.plot(x, get("running"), color="#2a6fb0", label="running")
        ax.plot(x, get("waiting"), color="#c0504d", label="waiting")
        ax.set_title(tag, fontsize=10)
        ax.legend(fontsize=7)
        axes[1][col].plot(x, get("kv", 100), color="#6b4fa0")
        axes[1][col].set_ylabel("KV %" if col == 0 else "")
        axes[2][col].plot(x, get("prefill_tps"), color="#d98c2b", label="prefill tok/s")
        axes[2][col].plot(x, get("decode_tps"), color="#2e8b57", label="decode tok/s")
        axes[2][col].legend(fontsize=7)
        axes[3][col].plot(x, get("tok_per_step"), color="#555", lw=0.8)
        axes[3][col].set_ylabel("tokens / step" if col == 0 else "")
        axes[3][col].set_xlabel("seconds from START")
        for row in axes:
            row[col].axvline(0, color="#999", ls="--", lw=0.8)
            row[col].axvline(e - s, color="#999", ls="--", lw=0.8)
            row[col].grid(alpha=0.3)
    axes[0][0].set_ylabel("requests")
    fig.suptitle(title + "  Dashed lines: START and END.", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    print(f"wrote {path}")


# ---------------------------------------------------------------- W1

def report_w1(folder, out, rate):
    runs, watch, windows = load(folder)
    base = {s: [r for t, r in runs.items() if re.fullmatch(rf"{s}_r\d+", t)] for s in "ABC"}
    rated = {s: [r for t, r in runs.items() if re.fullmatch(rf"{s}_rate_r\d+", t)] for s in "ABC"}
    S = {s: summarise(g, rate) for s, g in base.items() if g}
    L = ["<!-- generated by lab_report.py w1, do not edit by hand, re-run the script -->", ""]

    L += ["### Baseline, concurrency 30, 200 prompts, median of repeats", ""]
    L += table(["Measure"] + [SHAPE_NAME[s] for s in S], [
        ["Repeats"] + [f"{S[s]['n']}{'' if S[s]['ok'] else ' FAILED'}" for s in S],
        ["Request throughput (req/s)"] + [f(S[s]["req_s"], "{:.2f}") for s in S],
        ["Output token throughput (tok/s)"] + [f(S[s]["out_tps"]) for s in S],
        ["Total token throughput (tok/s)"] + [f(S[s]["tot_tps"]) for s in S],
        ["Mean TTFT (ms)"] + [f(S[s]["mean_ttft"], "{:,.1f}") for s in S],
        ["Median TTFT (ms)"] + [f(S[s]["p50_ttft"], "{:,.1f}") for s in S],
        ["P95 TTFT (ms)"] + [f(S[s]["p95_ttft"], "{:,.1f}") for s in S],
        ["P99 TTFT (ms)"] + [f(S[s]["p99_ttft"], "{:,.1f}") for s in S],
        ["Mean TPOT (ms)"] + [f(S[s]["mean_tpot"], "{:.2f}") for s in S],
        ["P95 TPOT (ms)"] + [f(S[s]["p95_tpot"], "{:.2f}") for s in S],
        ["P95 ITL (ms)"] + [f(S[s]["p95_itl"], "{:.2f}") for s in S],
        ["Mean end-to-end (ms)"] + [f(S[s]["mean_e2el"]) for s in S],
        ["Spread, total throughput"] + [pct(S[s]["spread_tput"]) for s in S],
        ["Spread, P95 TTFT"] + [pct(S[s]["spread_ttft"]) for s in S],
    ])
    L += ["", f"### Derived costs, USD at ${rate:.2f}/hr", ""]
    L += table(["Measure"] + list(S), [
        ["Cost per 1M output tokens"] + [f(S[s]["cost_out"], "${:.4f}") for s in S],
        ["Cost per 1M total tokens"] + [f(S[s]["cost_tot"], "${:.4f}") for s in S],
        ["Cost per 1,000 completed requests"] + [f(S[s]["cost_1k_req"], "${:.4f}") for s in S],
    ])
    if "A" in S and "B" in S and S["A"]["cost_out"] and S["B"]["cost_out"]:
        L += ["", f"Per output token, B costs {S['B']['cost_out'] / S['A']['cost_out']:.1f}x A (W1 v1: 11.6x)."]
    L += ["", "### Server side, from the monitor and the counters (median of repeats)", ""]
    L += table(["Measure"] + list(S), [
        ["Peak running"] + [f(S[s]["peak_running"]) for s in S],
        ["Peak waiting"] + [f(S[s]["peak_waiting"]) for s in S],
        ["Mean waiting"] + [f(S[s]["mean_waiting"], "{:.1f}") for s in S],
        ["Peak KV cache"] + [pct(S[s]["peak_kv"]) for s in S],
        ["Mean tokens per engine step"] + [f(S[s]["tok_per_step"]) for s in S],
        ["Mean queue time (ms)"] + [f(S[s]["queue_ms"]) for s in S],
        ["Preemptions, all repeats"] + [f(S[s]["preempt"]) for s in S],
        ["Prefix cache hits, all repeats"] + [f"{f(S[s]['hits'])} of {f(S[s]['queries'])}" for s in S],
    ])
    L += ["", "### Against W1 v1 (hand run, 21 Sep, single original run)", ""]
    keys = [("output_throughput", "out_tps", "Output tok/s", "{:,.0f}"), ("total_token_throughput", "tot_tps", "Total tok/s", "{:,.0f}"),
            ("mean_ttft_ms", "mean_ttft", "Mean TTFT ms", "{:,.1f}"), ("p95_ttft_ms", "p95_ttft", "P95 TTFT ms", "{:,.1f}"),
            ("mean_tpot_ms", "mean_tpot", "Mean TPOT ms", "{:.2f}"), ("p95_tpot_ms", "p95_tpot", "P95 TPOT ms", "{:.2f}")]
    rows = []
    for s in S:
        for k1, k2, name, fm in keys:
            rows.append([f"{s}: {name}", f(V1[s][k1], fm), f(S[s][k2], fm), delta(S[s][k2], V1[s][k1])])
    L += table(["Shape and measure", "v1", "v2 median", "Change"], rows)
    L += ["", "Throughput and TPOT are the comparable columns. TTFT under request-rate inf moved up to 117% between identical v1 runs."]

    R = {s: summarise(g, rate) for s, g in rated.items() if g}
    if R:
        L += ["", "### Fixed-rate TTFT, Poisson arrivals at 70% of baseline req/s", ""]
        L += table(["Shape", "Runs", "Target req/s", "Achieved req/s", "Median TTFT ms", "P95 TTFT ms", "P95 TPOT ms", "Peak running", "Mean waiting"],
                   [[s, R[s]["n"], rated[s][0]["j"].get("request_rate", "n/a"), f(R[s]["req_s"], "{:.2f}"), f(R[s]["p50_ttft"], "{:,.1f}"),
                     f(R[s]["p95_ttft"], "{:,.1f}"), f(R[s]["p95_tpot"], "{:.2f}"), f(R[s]["peak_running"]), f(R[s]["mean_waiting"], "{:.1f}")] for s in R])

    X = [runs[t] for t in ("X_seed0_128", "X_seed0_512") if t in runs]
    if X:
        L += ["", "### Cache demo: seed 0, 200 prompts, nested lengths", ""]
        L += table(["Run", "Prompt tokens queried", "Hits", "Hit rate", "Predicted hits"],
                   [[r["tag"], f(r["queries"]), f(r["hits"]), pct(r["hits"] / r["queries"] if r["queries"] else None),
                     "~0" if r["tag"].endswith("128") else "~25,600"] for r in X])

    fg = os.path.join(folder, "first-generation-check.txt")
    if os.path.exists(fg):
        L += ["", "### First generation", "", "```"] + open(fg).read().strip().splitlines() + ["```"]

    md = os.path.join(out, "w1_report.md")
    open(md, "w").write("\n".join(L) + "\n")
    print(f"wrote {md}")
    plt = mpl()
    if plt:
        timeline(plt, watch, windows, ["A_r1", "B_r1", "C_r1"], os.path.join(out, "w1_timeline.png"),
                 "W1 v2, repeat 1 of each shape, server side every 0.5 s.")


def compare_w1(folder, rate, vs, vs_rate, out):
    """Same baseline (same seeds, same prompts) on two GPUs: medians side by side."""
    def med(fold, r):
        runs, _, _ = load(fold)
        return {s: summarise([x for t, x in runs.items() if re.fullmatch(rf"{s}_r\d+", t)], r) for s in "ABC"}
    A, B = med(folder, rate), med(vs, vs_rate)
    na, nb = os.path.basename(folder), os.path.basename(vs)
    rows = []
    for s in "ABC":
        a, b = A[s], B[s]
        for key, label, fmt in [("req_s", "Req/s", "{:.2f}"), ("out_tps", "Output tok/s", None), ("tot_tps", "Total tok/s", None),
                                ("p95_ttft", "P95 TTFT ms", "{:,.1f}"), ("mean_tpot", "Mean TPOT ms", "{:.2f}"),
                                ("p95_tpot", "P95 TPOT ms", "{:.2f}"), ("cost_out", "$ per 1M output tokens", "${:.4f}")]:
            x, y = a.get(key), b.get(key)
            ratio = f"{x / y:.2f}x" if x and y else "n/a"
            rows.append([SHAPE_NAME[s], label, f(x, fmt) if fmt else f(x), f(y, fmt) if fmt else f(y), ratio])
    L = ["<!-- generated by lab_report.py w1 --vs, do not edit by hand -->", "",
         f"### Same baseline, two GPUs: {na} (${rate}/hr) against {nb} (${vs_rate}/hr)", "",
         "Same image, model, flags and seeds. Each GPU runs its own vLLM defaults. Medians of repeats.", ""]
    L += table(["Shape", "Measure", na, nb, f"{na} / {nb}"], rows)
    md = os.path.join(out, "w1_gpu_compare.md")
    open(md, "w").write("\n".join(L) + "\n")
    print(f"wrote {md}")


# ---------------------------------------------------------------- W2

def knee(points):
    k, why = points[-1][0], "throughput still rising at the top of the ladder"
    for (c0, s0), (c1, s1) in zip(points, points[1:]):
        if s0["tot_tps"] and s1["tot_tps"] and s1["tot_tps"] < 1.10 * s0["tot_tps"]:
            k, why = c0, f"total throughput changed {100 * (s1['tot_tps'] / s0['tot_tps'] - 1):+.1f}% from c={c0} to c={c1}"
            break
    safe, safe_why = None, "no point met the conditions"
    for c, s in points:
        if c > k:
            break
        if (s["mean_waiting"] is None or s["mean_waiting"] < 1) and s["preempt"] == 0:
            safe = c
            safe_why = (f"at or below the knee, mean waiting {f(s['mean_waiting'], '{:.1f}')}, zero preemptions, "
                        f"P95 TPOT {f(s['p95_tpot'], '{:.1f}')} ms")
    return k, why, safe, safe_why


def report_w2(folder, out, rate, extra=()):
    runs, watch, windows = load_many([folder, *extra])
    curves = {}
    for s in "AB":
        cs = sorted({int(m.group(1)) for t in runs if (m := re.fullmatch(rf"{s}_c(\d+)_r\d+", t))})
        curves[s] = [(c, summarise([r for t, r in runs.items() if re.fullmatch(rf"{s}_c{c}_r\d+", t)], rate)) for c in cs]
    L = ["<!-- generated by lab_report.py w2, do not edit by hand, re-run the script -->", ""]
    for s, pts in curves.items():
        if not pts:
            continue
        L += [f"### Curve {SHAPE_NAME[s]}", ""]
        L += table(["Concurrency", "Runs", "Req/s", "Output tok/s", "Total tok/s", "P50 TTFT ms", "P95 TTFT ms", "P95 TPOT ms",
                    "Peak running", "Mean waiting", "Peak KV", "Tokens/step", "Queue ms", "Preemptions", "Prefix hit",
                    "$/1M out", "Spread tput", "Spread P95 TTFT"],
                   [[c, f"{x['n']}{'' if x['ok'] else ' FAILED'}", f(x["req_s"], "{:.2f}"), f(x["out_tps"]), f(x["tot_tps"]),
                     f(x["p50_ttft"], "{:,.1f}"), f(x["p95_ttft"], "{:,.1f}"), f(x["p95_tpot"], "{:.2f}"), f(x["peak_running"]),
                     f(x["mean_waiting"], "{:.1f}"), pct(x["peak_kv"]), f(x["tok_per_step"]), f(x["queue_ms"]), f(x["preempt"]),
                     pct(x["hits"] / x["queries"] if x["queries"] else None), f(x["cost_out"], "${:.4f}"),
                     pct(x["spread_tput"]), pct(x["spread_ttft"])] for c, x in pts])
        k, why, safe, safe_why = knee(pts)
        L += ["", f"- **Knee:** c={k}. {why}.", f"- **Max safe concurrency:** {f(safe)}. {safe_why}.", ""]
    rated = {s: [r for t, r in runs.items() if re.fullmatch(rf"{s}_rate_r\d+", t)] for s in "AB"}
    R = {s: summarise(g, rate) for s, g in rated.items() if g}
    if R:
        L += ["### Fixed-rate TTFT, Poisson arrivals at 70% of best req/s", ""]
        L += table(["Shape", "Runs", "Target req/s", "Achieved req/s", "Median TTFT ms", "P95 TTFT ms", "P95 TPOT ms", "Peak running", "Mean waiting"],
                   [[s, R[s]["n"], rated[s][0]["j"].get("request_rate", "n/a"), f(R[s]["req_s"], "{:.2f}"), f(R[s]["p50_ttft"], "{:,.1f}"),
                     f(R[s]["p95_ttft"], "{:,.1f}"), f(R[s]["p95_tpot"], "{:.2f}"), f(R[s]["peak_running"]), f(R[s]["mean_waiting"], "{:.1f}")] for s in R])
        L.append("")
    lever = {name: [r for t, r in runs.items() if re.fullmatch(pat, t)] for name, pat in
             [("B c=128, H100 default budget 8192", r"B_c128_r\d+"), ("B c=128, budget 2048", r"L_B_c128_r\d+"),
              ("A c=1024, H100 default seq cap 1024", r"A_c1024_r\d+"), ("A c=1024, seq cap 256", r"L_A_c1024_r\d+")]}
    if lever["B c=128, budget 2048"] or lever["A c=1024, seq cap 256"]:
        L += ["### Lever run: --max-num-batched-tokens 2048 --max-num-seqs 256 (the A100 defaults, on this H100)", ""]
        rows = []
        for name, g in lever.items():
            if g:
                x = summarise(g, rate)
                rows.append([name, x["n"], f(x["req_s"], "{:.2f}"), f(x["tot_tps"]), f(x["p95_ttft"], "{:,.1f}"), f(x["p95_tpot"], "{:.2f}"),
                             f(x["peak_running"]), f(x["mean_waiting"], "{:.1f}"), pct(x["peak_kv"]), f(x["tok_per_step"]), f(x["preempt"])])
        L += table(["Condition", "Runs", "Req/s", "Total tok/s", "P95 TTFT ms", "P95 TPOT ms", "Peak running", "Mean waiting", "Peak KV", "Tokens/step", "Preemptions"], rows)
        L.append("")
    md = os.path.join(out, "w2_report.md")
    open(md, "w").write("\n".join(L) + "\n")
    print(f"wrote {md}")

    plt = mpl()
    if not plt:
        return
    shapes = [s for s in "AB" if curves[s]]
    if shapes:
        fig, axes = plt.subplots(len(shapes), 4, figsize=(18, 4.2 * len(shapes)), squeeze=False)
        panels = [("tot_tps", "Total tok/s"), ("p95_ttft", "P95 TTFT (ms)"), ("p95_tpot", "P95 TPOT (ms)"), ("peak_running", "Peak running / mean waiting")]
        for row, s in enumerate(shapes):
            cs = [c for c, _ in curves[s]]
            k, _, safe, _ = knee(curves[s])
            for col, (key, title) in enumerate(panels):
                ax = axes[row][col]
                ax.plot(cs, [x[key] or 0 for _, x in curves[s]], marker="o", color="#2a6fb0")
                if key == "peak_running":
                    ax.plot(cs, [x["mean_waiting"] or 0 for _, x in curves[s]], marker="s", color="#c0504d", label="mean waiting")
                    ax.legend(fontsize=8)
                ax.axvline(k, color="#888", ls="--", lw=1)
                if safe:
                    ax.axvline(safe, color="#2e8b57", ls=":", lw=1.5)
                ax.set_xscale("log", base=2)
                ax.set_xticks(cs)
                ax.set_xticklabels([str(c) for c in cs])
                ax.set_xlabel("max concurrency")
                ax.set_title(f"{s}: {title}", fontsize=10)
                ax.grid(alpha=0.3)
        fig.suptitle("W2 saturation curves. Dashed: knee. Dotted: max safe concurrency. Medians of repeats.", fontsize=11)
        fig.tight_layout()
        p = os.path.join(out, "w2_saturation.png")
        fig.savefig(p, dpi=100)
        print(f"wrote {p}")
    tl = [t for t in ["B_c16_r1", "B_c128_r1", "B_c256_r1", "A_c64_r1", "A_c512_r1", "A_c1024_r1"] if t in windows]
    timeline(plt, watch, windows, tl, os.path.join(out, "w2_timeline.png"), "W2 v2, selected points, repeat 1, every 0.5 s.", pad=4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("week", choices=["w1", "w2"])
    ap.add_argument("folder")
    ap.add_argument("--rate", type=float, default=3.99, help="GPU $/hr; 3.99 = H100 SXM Secure, 1.79 = A100 SXM Secure (Nov 2026)")
    ap.add_argument("--vs", default=None, help="w1 only: a second captured folder to compare, e.g. w1_a100")
    ap.add_argument("--vs-rate", type=float, default=1.79, help="w1 only: $/hr of the --vs GPU")
    ap.add_argument("--out", default=None)
    ap.add_argument("--extra", nargs="*", default=[], help="w2 only: more captured folders to merge, e.g. the lever run")
    a = ap.parse_args()
    folder = os.path.abspath(a.folder)
    if not os.path.isdir(os.path.join(folder, "json")):
        sys.exit(f"{folder}/json not found. Point at the unpacked {a.week}/ folder.")
    out = a.out or os.path.dirname(folder)
    os.makedirs(out, exist_ok=True)
    if a.week == "w1":
        report_w1(folder, out, a.rate)
        if a.vs:
            compare_w1(folder, a.rate, os.path.abspath(a.vs), a.vs_rate, out)
    else:
        report_w2(folder, out, a.rate, [os.path.abspath(x) for x in a.extra])


if __name__ == "__main__":
    main()
