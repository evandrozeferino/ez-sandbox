# ez-sandbox

A single-GPU inference lab, rebuilt from scratch each session and versioned here.
One capability is added per session, v0.1 to v0.8, and each is tagged.

Everything in this repo is measured on rented hardware in my own lab. Nothing here
is a client result.

## Current version

**v0.1, tag `week1-baseline`.** A reproducible baseline for Qwen2.5-7B-Instruct under
vLLM 0.29.0, measured across three workload shapes. The hand run used an A100 SXM
80GB; the scripted baseline uses an H100 SXM 80GB, the GPU for the rest of the series. W1 was run twice:
once by hand from a written sheet, then again fully scripted. The scripted run is the
baseline. The hand run is kept, with its gaps, as the reason the lab is scripted.

## Layout

```
docs/
  runbook-runpod-vllm.md      the June deploy runbook, superseded by kit/ and kept for history
kit/                          runner, 0.5 s monitor and report scripts used from W1 v2 on
w1-baseline/
  v2/                         the baseline: scripted rerun, 3 repeats per shape, timelines
  v1-handrun-2026-09-21/
    baseline-record.md        the hand-run record: baseline, derived costs, peaks, findings
    pod-config.md             exact pod and load generator configuration
    env.txt                   vLLM version, GPU, driver
    metric-inventory.txt      the 66 vllm: metric names this version exports
    first-generation-counters.txt
    metrics-final-counters.txt
    w1_A_decode_heavy.json    200 prompts, 128 in / 1024 out
    w1_B_prefill_heavy.json   200 prompts, 4096 in / 64 out
    w1_C_balanced.json        200 prompts, 512 in / 512 out
    w1_A_rerun.json           same three shapes, repeated, as a variance check
    w1_B_rerun.json
    w1_C_rerun.json
```

## How to boot it

Follow the run sheet in `w1-baseline/v2/`, which uses the scripts in `kit/`. Generate
a fresh API key per pod. Terminate the pod when finished, and check the provider's
storage tab is empty; a stopped pod still bills its disk.

## What W1 established

Throughput is stable between identical runs, within a few percent. Time to first
token is not: it moved by up to 117% between identical runs under an unthrottled
request rate. Any later comparison therefore needs repeats and a median, and latency
comparisons need a fixed request rate.

At concurrency 30 the KV cache peaked at 13% and no requests were preempted, so this
card has significant headroom at that concurrency. The prefill-heavy shape queued
requests anyway, which points at an admission limit rather than a memory limit.

The scripted rerun (v2, 10 Nov 2026, H100 SXM 80GB) confirmed and sharpened this.
Medians of three runs at concurrency 30: output throughput 4,513 tok/s for the
decode-heavy shape (A100 hand run: 2,459), 585 for the prefill-heavy shape (212) and
4,102 for the balanced shape (2,434). Mean time per output token on the prefill-heavy
shape fell from 120 ms to 29 ms. Throughput now varies by 0.3% or less between repeats.
The server log reports `max_num_batched_tokens=8192` on the H100, against 2,048 on the
A100: each engine step fits two 4,096-token prompts instead of half of one. The
prefill-heavy shape still queued, peaking at 21 waiting requests, because fixed-length
requests finish and are refilled in synced waves, and each refill fills the step
budget. At a fixed arrival rate of 70% of capacity, the same shape's median time to
first token fell from about 1.4 s to 195 ms. A cache demo with the default seed
reproduced the hand run's prefix cache hits on purpose (26,256 hits against 25,600
predicted), so the 13.1% was an artefact of overlapping prompts, not cache reuse in
the workload.

Full numbers for the hand run in `w1-baseline/v1-handrun-2026-09-21/baseline-record.md`,
and for the scripted baseline in `w1-baseline/v2/`.

## Known gaps in the hand run

The complete `/metrics` dump was not captured; `metrics-final-counters.txt` holds the
cumulative counters only. Each shape ran once, with the benchmark's default seed, which
made the three shapes' prompts overlap and produced a 13.1% prefix cache hit rate on
"random" prompts. The scripted rerun in `w1-baseline/v2/` fixes all three: full surface
captured by script, three repeats per shape, a unique seed per run.
