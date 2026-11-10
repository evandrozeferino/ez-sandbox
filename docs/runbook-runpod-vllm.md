
---
type: runbook
week: 1
topic: RunPod vLLM Deploy, Clean Path
status: superseded by the W1 v2 and W2 v2 run sheets and lab-kit (30 Sep 2026)
provider: RunPod
tags: [runbook, gpu, runpod, vllm, setup]
---

# Runbook: RunPod vLLM (Deploy → Live Metrics in ~15 min)

> Hard-won from the 27 Jun session. Path that WORKS: official vLLM image,
> container disk only, web terminal for access. Skips every wall that cost
> hours (SSH keys, volume quota, manual pip install, CUDA mismatch).

## Golden rules (the scar tissue)

1. **Use `vllm/vllm-openai:latest`**: version-locked vLLM+PyTorch+CUDA. Never `pip install vllm` into a venv.
2. **Container disk only.** No network volume until the EU-RO quota cap is understood. 40GB container disk.
3. **Web terminal is the reliable access path.** SSH key injection on community cloud is flaky. Don't fight it.
4. **Stop the pod the instant you have what you need.** Billing is per-second.
5. **`/metrics` is unauthenticated. `/v1/*` needs the API key** (the image uses HF_TOKEN as the key by default, or set --api-key explicitly).

## Pre-flight (once, ~2 min)

- [ ] HF token in clipboard (hf_...)
- [ ] Llama-3 access approved? If yes use `meta-llama/Meta-Llama-3-8B-Instruct`. If pending, use `Qwen/Qwen2.5-7B-Instruct` (ungated).

## Step 1: Deploy (~3 min)

Pods → Deploy → A100 80GB (accept whatever region has stock).

**Edit Template / Customize:**

| Field | Value |
|---|---|
| Container Image | `vllm/vllm-openai:latest` |
| Container Start Command | `--model Qwen/Qwen2.5-7B-Instruct --max-model-len 8192 --gpu-memory-utilization 0.85 --host 0.0.0.0 --port 8000 --api-key <redacted>` |
| Container Disk | `40 GB` |
| Network Volume | **none** |
| Expose HTTP Ports | `8000` |
| Expose TCP Ports | `22` |
| Env `HF_TOKEN` | `<your token>` |

Deploy On-Demand (not Spot).

> `--api-key <redacted>` makes auth predictable. You set it, you know it.
> Swap model name for Llama-3 once approved.

## Step 2: Watch boot (~5 min)

Dashboard → pod → **Logs** tab. Wait for:
```
INFO ... Application startup complete.
```

Model downloads on first boot (~5 min for 7B). If it errors, read the last 30 log lines.

## Step 3: Hit it via web terminal (the reliable path)

Dashboard → pod → Connect → **Start Web Terminal**. Inside the pod:

```bash
# /metrics is open, no auth
curl -s http://localhost:8000/metrics | grep -E "^vllm" | grep -v "_created"

# /v1/* needs the key you set
curl -s http://localhost:8000/v1/models \
  -H "Authorization: Bearer <redacted>" | python3 -m json.tool
```

## Step 4: Make metrics move off zero (the real lesson)

Fire load, then re-read metrics. Watch `generation_tokens_total` jump:

```bash
# Generate
curl -s http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer <redacted>" \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen2.5-7B-Instruct","messages":[{"role":"user","content":"Explain KV cache in 3 sentences."}],"max_tokens":150}' \
  | python3 -m json.tool

# Re-read: these are now non-zero
curl -s http://localhost:8000/metrics | grep -E \
  "generation_tokens_total|prompt_tokens_total|num_requests_running|kv_cache_usage" \
  | grep -v "_created"
```

## Step 5: Capture + STOP

```bash
curl -s http://localhost:8000/metrics | grep "^vllm" | grep -v "_created" > /tmp/metrics.txt
cat /tmp/metrics.txt   # select-copy into Obsidian
```
Then dashboard → **Stop pod**. Verify state = Stopped.

## The 6 metrics that matter (idle = 0.0, that's correct)

| Metric | Measures | Study day |
|---|---|---|
| `vllm:kv_cache_usage_perc` | KV-cache fill %. →1.0 = preemptions begin | D2 |
| `vllm:num_requests_running` | Live batch size | D3 |
| `vllm:num_requests_waiting` | Queue depth = saturation | D3 |
| `vllm:num_preemptions_total` | Evictions from memory pressure | D2/D5 |
| `vllm:prefix_cache_hits_total / _queries_total` | Cache effectiveness | D5 |
| `vllm:prompt_tokens_total / generation_tokens_total` | Throughput (rate() = tok/s) | D1 |

Bonus: `num_requests_waiting_by_reason{reason="capacity"}` counts requests waiting for scheduling capacity. It does not say which limit binds: token budget, sequence cap and KV memory all count as capacity (vLLM 0.29). Read it next to kv_cache_usage_perc, num_requests_running and iteration_tokens_total.

## Failure playbook

| Symptom | Cause | Fix |
|---|---|---|
| `Expecting value: line 1 column 1` | curl got empty body | Check URL, `curl -v` to see HTTP code |
| `//v1/models` double slash | trailing `/` on URL | drop trailing slash |
| `{"error":"Unauthorized"}` on /v1/* | API key needed | add `-H "Authorization: Bearer <key>"` |
| `301 Moved Permanently` | double-slash redirect | fix URL |
| `Disk quota exceeded` | network volume capped | use container disk, no volume |
| `NVIDIA driver too old` | manual pip vllm vs driver | use `vllm/vllm-openai:latest` image |
| Web terminal `Unauthorized` on /v1 | same as above | use /metrics (open) or add key |

## Open items for future

- [ ] Why did `ez-vol-eu` cap at ~23GB not 50GB? Support ticket if reusing volumes.
- [ ] Get Llama-3 approval live → swap into Step 1.
- [x] Dropped 30 Sep: lab-kit's lab_watch.py monitor and lab_report.py charts cover it.

> Key redacted in this copy. Generate one per pod with `openssl rand -hex 16`.
