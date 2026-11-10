#!/usr/bin/env python3
"""lab_watch.py: the monitor. Runs INSIDE the pod, in terminal 2, for the whole lab.

Every 0.5 s it reads /metrics and prints one timestamped line: what the scheduler
holds (running, waiting, KV), what the engine is doing (prefill tok/s, decode tok/s,
steps/s, tokens per step), and the cache hit rate since the last line. Every event
the runner in terminal 1 writes (NEXT, START, END, ...) is printed in line, on the
same clock, so cause and effect read top to bottom.

Everything printed is also saved: <dir>/watch.csv, one row per sample.

Usage:
  python3 lab_watch.py                      # defaults: /workspace/lab, 0.5 s
  python3 lab_watch.py --interval 0.25
  python3 lab_watch.py --quiet              # CSV only, no screen output
Ctrl-C stops it. Restarting appends to the same CSV.

Standard library only.
"""
import argparse
import csv
import datetime as dt
import os
import re
import signal
import sys
import time
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--base", default=os.environ.get("BASE", "http://localhost:8000"))
ap.add_argument("--dir", default=os.environ.get("LAB_DIR", "/workspace/lab"))
ap.add_argument("--interval", type=float, default=0.5)
ap.add_argument("--quiet", action="store_true")
ap.add_argument("--header-every", type=int, default=30)
a = ap.parse_args()

os.makedirs(a.dir, exist_ok=True)
CSV = os.path.join(a.dir, "watch.csv")
EVENTS = os.path.join(a.dir, "events.tsv")
HEART = os.path.join(a.dir, ".watch_heartbeat")

LINE = re.compile(r"^(vllm:[a-zA-Z_:]+)(\{[^}]*\})?\s+([0-9.eE+-]+|NaN)$")

# column -> (metric, label filter or None)
GAUGES = {
    "running": ("vllm:num_requests_running", None),
    "waiting": ("vllm:num_requests_waiting", None),
    "waiting_capacity": ("vllm:num_requests_waiting_by_reason", 'reason="capacity"'),
    "waiting_deferred": ("vllm:num_requests_waiting_by_reason", 'reason="deferred"'),
    "kv": ("vllm:kv_cache_usage_perc", None),
}
COUNTERS = {
    "preempt_total": ("vllm:num_preemptions_total", None),
    "prompt_total": ("vllm:prompt_tokens_total", None),
    "gen_total": ("vllm:generation_tokens_total", None),
    "hits_total": ("vllm:prefix_cache_hits_total", None),
    "queries_total": ("vllm:prefix_cache_queries_total", None),
    "steps_total": ("vllm:iteration_tokens_total_count", None),
    "step_tokens_total": ("vllm:iteration_tokens_total_sum", None),
    "finished_total": ("vllm:request_success_total", None),
}
DERIVED = ["prefill_tps", "decode_tps", "steps_ps", "tok_per_step", "hit_pct", "done_ps"]
COLS = ["t", "utc"] + list(GAUGES) + list(COUNTERS) + DERIVED

stop = False


def _stop(*_):
    global stop
    stop = True


signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)


def scrape():
    txt = urllib.request.urlopen(a.base + "/metrics", timeout=2).read().decode()
    vals = {}
    for line in txt.splitlines():
        m = LINE.match(line)
        if not m:
            continue
        name, labels, v = m.group(1), m.group(2) or "", float(m.group(3))
        for col, (metric, need) in {**GAUGES, **COUNTERS}.items():
            if name == metric and (need is None or need in labels):
                vals[col] = vals.get(col, 0.0) + v
    return vals


def utc(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def fmt_int(x):
    return "-" if x is None else f"{x:,.0f}"


HEADER = ("time (UTC)      run  wait   KV%   pre* |  prefill tok/s   decode tok/s | steps/s  tok/step | hit%  done/s")


def row_text(r):
    hit = "-" if r.get("hit_pct") is None else f"{r['hit_pct']:.0f}"
    tps = "-" if r.get("tok_per_step") is None else f"{r['tok_per_step']:,.0f}"
    return (f"{r['utc']}  {r.get('running', 0):>4.0f} {r.get('waiting', 0):>5.0f} "
            f"{100 * r.get('kv', 0):>5.1f} {r.get('preempt_seen', 0):>5.0f} | "
            f"{fmt_int(r.get('prefill_tps')):>14} {fmt_int(r.get('decode_tps')):>14} | "
            f"{r.get('steps_ps') or 0:>7.1f} {tps:>9} | {hit:>4}  {r.get('done_ps') or 0:>6.1f}")


class EventTail:
    """Reads events.tsv written by the runner and returns new lines."""

    def __init__(self, path):
        self.path, self.pos = path, 0
        if os.path.exists(path):
            self.pos = os.path.getsize(path)  # only events from now on

    def new(self):
        if not os.path.exists(self.path):
            return []
        size = os.path.getsize(self.path)
        if size < self.pos:
            self.pos = 0
        with open(self.path) as fh:
            fh.seek(self.pos)
            chunk = fh.read()
            self.pos = fh.tell()
        return [l.rstrip("\n").split("\t") for l in chunk.splitlines() if l.strip()]


def main():
    tail = EventTail(EVENTS)
    new_file = not os.path.exists(CSV)
    fh = open(CSV, "a", newline="")
    w = csv.writer(fh)
    if new_file:
        w.writerow(COLS)
    prev, n_lines, down = None, 0, False
    if not a.quiet:
        print(f"lab_watch: {a.base}/metrics every {a.interval}s -> {CSV}", flush=True)
        print("pre* = preemptions since this monitor started. Rates are per second over the last interval.", flush=True)
        print("prefill tok/s = prompt tokens computed (cache hits excluded); vLLM books a prompt when its", flush=True)
        print("prefill completes, so it arrives in lumps. tok/step is smooth over a few seconds, not per line.", flush=True)
    while not stop:
        t = time.time()
        for ev in tail.new():
            if not a.quiet and len(ev) >= 4:
                detail = ev[4] if len(ev) > 4 else ""
                if ev[2] == "NEXT" and " | " in detail:  # full command is in terminal 1
                    detail = detail.split(" | ")[0]
                print(f">>> {ev[1]}  {ev[2]:<6} {ev[3]}  {detail}", flush=True)
        try:
            v = scrape()
            if down and not a.quiet:
                print(f"{utc(t)}  server back", flush=True)
            down = False
        except Exception as exc:
            if not down and not a.quiet:
                print(f"{utc(t)}  server unreachable: {exc}", flush=True)
            down = True
            time.sleep(a.interval)
            continue
        r = {"t": round(t, 3), "utc": utc(t), **v}
        if prev:
            dtt = t - prev["t"]
            d = {k: v.get(k, 0) - prev.get(k, 0) for k in COUNTERS}
            if any(x < 0 for x in d.values()):  # server restarted, counters reset
                d = {k: 0 for k in d}
            if dtt > 0:
                # prompt tokens actually computed (cache hits excluded). vLLM counts a
                # prompt when its prefill completes, so this arrives in lumps.
                r["prefill_tps"] = max(0.0, d["step_tokens_total"] - d["gen_total"]) / dtt
                r["decode_tps"] = d["gen_total"] / dtt
                r["steps_ps"] = d["steps_total"] / dtt
                r["done_ps"] = d["finished_total"] / dtt
            r["tok_per_step"] = d["step_tokens_total"] / d["steps_total"] if d["steps_total"] else None
            r["hit_pct"] = 100 * d["hits_total"] / d["queries_total"] if d["queries_total"] else None
            r["preempt_seen"] = prev.get("preempt_seen", 0) + d["preempt_total"]
        w.writerow([r.get(c, "") if not isinstance(r.get(c), float) else round(r[c], 4) for c in COLS])
        fh.flush()
        try:
            with open(HEART, "w") as hb:
                hb.write(str(t))
        except OSError:
            pass
        if not a.quiet and prev:
            if n_lines % a.header_every == 0:
                print(HEADER, flush=True)
            print(row_text(r), flush=True)
            n_lines += 1
        prev = r
        time.sleep(max(0.0, a.interval - (time.time() - t)))
    fh.close()


if __name__ == "__main__":
    main()
