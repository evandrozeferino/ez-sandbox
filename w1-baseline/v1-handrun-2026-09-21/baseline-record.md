---
type: baseline-record
week: W1
sandbox: v0.1
date: 2026-09-21
status: complete
model: Qwen/Qwen2.5-7B-Instruct
gpu: A100-SXM4-80GB
vllm: "0.29.0"
tags: [baseline, inference, ez-consulting]
---

# W1 Baseline Record, v1 hand run (21 Sep 2026)

This is the first W1 run, done by hand from a written sheet. It is kept as the record of what that run produced, not as the current baseline. The baseline later labs measure against is the automated rerun in `../v2/`. Within this record, the **original runs** are the reference and the reruns are a variance check only.

Source data is in the collapsed sections under Raw data. Every number in the tables was computed from the benchmark JSONs, not retyped.

## Environment

| Field | Value |
|---|---|
| Date | 2026-09-21 |
| vLLM | 0.29.0, V1 engine |
| GPU | NVIDIA A100-SXM4-80GB, 81,920 MiB |
| Driver | 580.159.04 |
| Region | US-KS-2 |
| GPU rate paid | $1.59/hr, On-Demand |
| Model | Qwen/Qwen2.5-7B-Instruct |
| max-model-len | 8192 |
| gpu-memory-utilization | 0.85 |
| Client | `vllm bench serve`, random dataset, `--random-range-ratio 0 --ignore-eos --temperature 0` |
| Load | 200 prompts per run, max concurrency 30, request rate inf |

## Baseline

| Measure | A, decode-heavy<br>128 in / 1024 out | B, prefill-heavy<br>4096 in / 64 out | C, balanced<br>512 in / 512 out |
|---|---:|---:|---:|
| Successful requests | 200 | 200 | 200 |
| Duration (s) | 83.3 | 60.4 | 42.1 |
| Request throughput (req/s) | 2.40 | 3.31 | 4.75 |
| Output token throughput (tok/s) | 2,459 | 212 | 2,434 |
| Total token throughput (tok/s) | 2,767 | 13,782 | 4,868 |
| Mean TTFT (ms) | 184.4 | 1,414.3 | 110.1 |
| Median TTFT (ms) | 175.5 | 907.3 | 104.5 |
| P95 TTFT (ms) | 330.1 | 5,394.4 | 176.1 |
| P99 TTFT (ms) | 334.1 | 7,732.2 | 195.1 |
| Mean TPOT (ms) | 11.47 | 120.32 | 11.56 |
| P95 TPOT (ms) | 11.60 | 131.99 | 11.65 |
| Mean ITL (ms) | 11.47 | 120.32 | 11.56 |
| P95 ITL (ms) | 12.40 | 160.38 | 12.38 |
| P99 ITL (ms) | 14.07 | 164.48 | 15.69 |
| Mean end-to-end (ms) | 11,916 | 8,994 | 6,016 |

## Derived costs, USD at $1.59/hr

| Measure | A, decode-heavy<br>128 in / 1024 out | B, prefill-heavy<br>4096 in / 64 out | C, balanced<br>512 in / 512 out |
|---|---:|---:|---:|
| Cost per 1M output tokens | $0.1796 | $2.0830 | $0.1815 |
| Cost per 1M total tokens | $0.1596 | $0.0320 | $0.0907 |
| Cost per 1,000 completed requests | $0.1839 | $0.1333 | $0.0929 |

Formulas: rate ÷ (tok/s × 3600) × 1,000,000 for the token rows; rate ÷ (req/s × 3600) × 1,000 for the request row. Exact throughputs from the JSONs, not the rounded printout.

## Live peaks, server side

| Peak | A, decode-heavy<br>128 in / 1024 out | B, prefill-heavy<br>4096 in / 64 out | C, balanced<br>512 in / 512 out |
|---|---:|---:|---:|
| `num_requests_running` | 30 | 30 | 30 |
| `num_requests_waiting` | 0 | 26 | 4 |
| `kv_cache_usage_perc` | 0.0362 (3.6%) | 0.1317 (13.2%) | 0.0326 (3.3%) |
| Preemptions | 0 | 0 | 0 |

Peaks were captured during the **reruns**, with the peak-tracker script, not during the original runs. Same workload, same pod. `kv_cache_usage_perc` is a fraction: 0.13 means 13%. Preemptions from the cumulative counter, zero across all runs.

## Variance check, original vs rerun

| Measure | A orig | A rerun | Δ | B orig | B rerun | Δ | C orig | C rerun | Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Output tok/s | 2,459 | 2,492 | +1.3% | 212 | 230 | +8.5% | 2,434 | 2,341 | -3.8% |
| Total tok/s | 2,767 | 2,804 | +1.3% | 13,782 | 14,959 | +8.5% | 4,868 | 4,682 | -3.8% |
| Mean TTFT (ms) | 184.4 | 95.9 | -48.0% | 1,414.3 | 1,326.2 | -6.2% | 110.1 | 239.4 | +117.4% |
| P95 TTFT (ms) | 330.1 | 147.1 | -55.4% | 5,394.4 | 5,029.5 | -6.8% | 176.1 | 677.8 | +284.8% |
| Mean TPOT (ms) | 11.47 | 11.39 | -0.6% | 120.32 | 110.42 | -8.2% | 11.56 | 11.80 | +2.1% |

## Counters

**First generation (block 3).** Prompt tokens +38, generation tokens +77. The prompt was 7 words, roughly 9 tokens. The rest is the chat template's default system prompt and role markers, paid as prefill on every call.

**Final counters**, captured after the three original runs and before the reruns:

| Counter | Value |
|---|---:|
| `prompt_tokens_total` | 947,238 |
| `generation_tokens_total` | 320,077 |
| `prefix_cache_queries_total` | 947,238 |
| `prefix_cache_hits_total` | 124,480 |
| Prefix cache hit rate | 13.1% |
| `num_preemptions_total` | 0 |

**Reconciliation.** Client-side totals for the three original runs: 947,200 input and 320,000 output tokens. Add block 3's 38 and 77 and the server counters match to the token: 947,238 vs 947,238, 320,077 vs 320,077. The metrics surface counts exactly what the server processed.

## Findings and open questions

1. **Throughput is stable run to run, TTFT is not.** Throughput moved +1.3% (A), +8.5% (B, total) and -3.8% (C). Mean TTFT moved -48.0% (A) and +117.4% (C). Consequence for W3: one run per condition cannot prove a saving; use three repeats and report the median. Compare TTFT at a fixed request rate, since under `--request-rate inf` it is dominated by the opening burst.
2. **KV cache never came close to full.** Peaks of 3.6%, 13.2% and 3.3%, zero preemptions. At concurrency 30 this A100 has large headroom. W2 must push much harder to find saturation.
3. **B queued without KV pressure.** 26 waiting at peak while KV sat at 13.2%. Likely cause, not yet verified: the per-step prefill token budget admits only a few 4,096-token prompts at a time. The constraint is admission, not memory. W2's first thread.
4. **Per output token, B costs 11.6× A.** Same GPU, same hour. The prefill-heavy shape spends the GPU on input tokens that never appear as output.
5. **Prefix cache hit rate 13.1% on random prompts.** Expected near zero. Cause unknown: candidates are prompt reuse inside the benchmark client or shared leading tokens from the random generator. Investigate before W4. From W2, snapshot counters between runs so hits can be attributed.
6. **Client reports peak concurrent requests of 60; server never exceeded 30 running.** Trust the server. The client figure is probably a per-second counting artefact.

## Prefill vs decode, in two sentences

Yours to write, from the Baseline table. Which shape had the higher TTFT, which had the higher token throughput, and why that is the physics rather than a fault.

## Raw data

> [!example]- vLLM version and nvidia-smi
> ```
> 0.29.0
> name, memory.total [MiB], driver_version
> NVIDIA A100-SXM4-80GB, 81920 MiB, 580.159.04
> ```

> [!example]- Metric inventory, 66 names
> ```
> vllm:cache_config_info
> vllm:e2e_request_latency_seconds_bucket
> vllm:e2e_request_latency_seconds_count
> vllm:e2e_request_latency_seconds_sum
> vllm:engine_sleep_state
> vllm:estimated_flops_per_gpu_total
> vllm:estimated_read_bytes_per_gpu_total
> vllm:estimated_write_bytes_per_gpu_total
> vllm:external_prefix_cache_hits_total
> vllm:external_prefix_cache_queries_total
> vllm:generation_tokens_total
> vllm:inter_token_latency_seconds_bucket
> vllm:inter_token_latency_seconds_count
> vllm:inter_token_latency_seconds_sum
> vllm:iteration_tokens_total_bucket
> vllm:iteration_tokens_total_count
> vllm:iteration_tokens_total_sum
> vllm:kv_cache_usage_perc
> vllm:mm_cache_hits_total
> vllm:mm_cache_queries_total
> vllm:num_preemptions_total
> vllm:num_requests_running
> vllm:num_requests_waiting
> vllm:num_requests_waiting_by_reason
> vllm:prefix_cache_hits_total
> vllm:prefix_cache_queries_total
> vllm:prompt_tokens_by_source_total
> vllm:prompt_tokens_cached_total
> vllm:prompt_tokens_total
> vllm:request_decode_time_seconds_bucket
> vllm:request_decode_time_seconds_count
> vllm:request_decode_time_seconds_sum
> vllm:request_generation_tokens_bucket
> vllm:request_generation_tokens_count
> vllm:request_generation_tokens_sum
> vllm:request_inference_time_seconds_bucket
> vllm:request_inference_time_seconds_count
> vllm:request_inference_time_seconds_sum
> vllm:request_max_num_generation_tokens_bucket
> vllm:request_max_num_generation_tokens_count
> vllm:request_max_num_generation_tokens_sum
> vllm:request_params_max_tokens_bucket
> vllm:request_params_max_tokens_count
> vllm:request_params_max_tokens_sum
> vllm:request_params_n_bucket
> vllm:request_params_n_count
> vllm:request_params_n_sum
> vllm:request_prefill_kv_computed_tokens_bucket
> vllm:request_prefill_kv_computed_tokens_count
> vllm:request_prefill_kv_computed_tokens_sum
> vllm:request_prefill_time_seconds_bucket
> vllm:request_prefill_time_seconds_count
> vllm:request_prefill_time_seconds_sum
> vllm:request_prompt_tokens_bucket
> vllm:request_prompt_tokens_count
> vllm:request_prompt_tokens_sum
> vllm:request_queue_time_seconds_bucket
> vllm:request_queue_time_seconds_count
> vllm:request_queue_time_seconds_sum
> vllm:request_success_total
> vllm:request_time_per_output_token_seconds_bucket
> vllm:request_time_per_output_token_seconds_count
> vllm:request_time_per_output_token_seconds_sum
> vllm:time_to_first_token_seconds_bucket
> vllm:time_to_first_token_seconds_count
> vllm:time_to_first_token_seconds_sum
> ```

> [!example]- Ten-metric check, all PRESENT, no substitutions
> ```
> kv_cache_usage_perc                PRESENT
> num_requests_running               PRESENT
> num_requests_waiting               PRESENT
> num_preemptions_total              PRESENT
> prefix_cache_hits_total            PRESENT
> prefix_cache_queries_total         PRESENT
> prompt_tokens_total                PRESENT
> generation_tokens_total            PRESENT
> time_to_first_token_seconds        PRESENT
> inter_token_latency_seconds        PRESENT
> ```

> [!example]- First generation, counters before and after
> ```
> before
> # HELP vllm:prompt_tokens_total Number of prefill tokens processed.
> # TYPE vllm:prompt_tokens_total counter
> vllm:prompt_tokens_total{engine="0",model_name="Qwen/Qwen2.5-7B-Instruct"} 0.0
> # HELP vllm:generation_tokens_total Number of generation tokens processed.
> # TYPE vllm:generation_tokens_total counter
> vllm:generation_tokens_total{engine="0",model_name="Qwen/Qwen2.5-7B-Instruct"} 0.0
>
> after
> # HELP vllm:prompt_tokens_total Number of prefill tokens processed.
> # TYPE vllm:prompt_tokens_total counter
> vllm:prompt_tokens_total{engine="0",model_name="Qwen/Qwen2.5-7B-Instruct"} 38.0
> # HELP vllm:generation_tokens_total Number of generation tokens processed.
> # TYPE vllm:generation_tokens_total counter
> vllm:generation_tokens_total{engine="0",model_name="Qwen/Qwen2.5-7B-Instruct"} 77.0
>
> ```

> [!example]- Run A original, decode-heavy, result block
> ```
> ============ Serving Benchmark Result ============
> Successful requests:                     200
> Failed requests:                         0
> Maximum request concurrency:             30
> Benchmark duration (s):                  83.27
> Total input tokens:                      25600
> Total generated tokens:                  204800
> Request throughput (req/s):              2.40
> Output token throughput (tok/s):         2459.41
> Peak output token throughput (tok/s):    2730.00
> Peak concurrent requests:                60.00
> Total token throughput (tok/s):          2766.84
> ---------------Time to First Token----------------
> Mean TTFT (ms):                          184.38
> Median TTFT (ms):                        175.52
> P50 TTFT (ms):                           175.52
> P95 TTFT (ms):                           330.07
> P99 TTFT (ms):                           334.07
> -----Time per Output Token (excl. 1st token)------
> Mean TPOT (ms):                          11.47
> Median TPOT (ms):                        11.52
> P50 TPOT (ms):                           11.52
> P95 TPOT (ms):                           11.60
> P99 TPOT (ms):                           11.62
> ---------------Inter-token Latency----------------
> Mean ITL (ms):                           11.47
> Median ITL (ms):                         11.36
> P50 ITL (ms):                            11.36
> P95 ITL (ms):                            12.40
> P99 ITL (ms):                            14.07
> ----------------End-to-end Latency----------------
> Mean E2EL (ms):                          11915.91
> Median E2EL (ms):                        11965.15
> P50 E2EL (ms):                           11965.15
> P95 E2EL (ms):                           12033.59
> P99 E2EL (ms):                           12036.96
> ==================================================
> ```

> [!example]- Run B original, prefill-heavy, result block
> ```
> ============ Serving Benchmark Result ============
> Successful requests:                     200
> Failed requests:                         0
> Maximum request concurrency:             30
> Benchmark duration (s):                  60.37
> Total input tokens:                      819200
> Total generated tokens:                  12800
> Request throughput (req/s):              3.31
> Output token throughput (tok/s):         212.03
> Peak output token throughput (tok/s):    808.00
> Peak concurrent requests:                35.00
> Total token throughput (tok/s):          13782.05
> ---------------Time to First Token----------------
> Mean TTFT (ms):                          1414.33
> Median TTFT (ms):                        907.26
> P50 TTFT (ms):                           907.26
> P95 TTFT (ms):                           5394.40
> P99 TTFT (ms):                           7732.25
> -----Time per Output Token (excl. 1st token)------
> Mean TPOT (ms):                          120.32
> Median TPOT (ms):                        127.11
> P50 TPOT (ms):                           127.11
> P95 TPOT (ms):                           131.99
> P99 TPOT (ms):                           137.64
> ---------------Inter-token Latency----------------
> Mean ITL (ms):                           120.32
> Median ITL (ms):                         146.38
> P50 ITL (ms):                            146.38
> P95 ITL (ms):                            160.38
> P99 ITL (ms):                            164.48
> ----------------End-to-end Latency----------------
> Mean E2EL (ms):                          8994.19
> Median E2EL (ms):                        9025.24
> P50 E2EL (ms):                           9025.24
> P95 E2EL (ms):                           13382.49
> P99 E2EL (ms):                           15766.01
> ==================================================
> ```

> [!example]- Run C original, balanced, result block
> ```
> ============ Serving Benchmark Result ============
> Successful requests:                     200
> Failed requests:                         0
> Maximum request concurrency:             30
> Benchmark duration (s):                  42.07
> Total input tokens:                      102400
> Total generated tokens:                  102400
> Request throughput (req/s):              4.75
> Output token throughput (tok/s):         2434.07
> Peak output token throughput (tok/s):    2640.00
> Peak concurrent requests:                60.00
> Total token throughput (tok/s):          4868.14
> ---------------Time to First Token----------------
> Mean TTFT (ms):                          110.13
> Median TTFT (ms):                        104.51
> P50 TTFT (ms):                           104.51
> P95 TTFT (ms):                           176.11
> P99 TTFT (ms):                           195.11
> -----Time per Output Token (excl. 1st token)------
> Mean TPOT (ms):                          11.56
> Median TPOT (ms):                        11.60
> P50 TPOT (ms):                           11.60
> P95 TPOT (ms):                           11.65
> P99 TPOT (ms):                           11.68
> ---------------Inter-token Latency----------------
> Mean ITL (ms):                           11.56
> Median ITL (ms):                         11.52
> P50 ITL (ms):                            11.52
> P95 ITL (ms):                            12.38
> P99 ITL (ms):                            15.69
> ----------------End-to-end Latency----------------
> Mean E2EL (ms):                          6016.41
> Median E2EL (ms):                        6035.17
> P50 E2EL (ms):                           6035.17
> P95 E2EL (ms):                           6117.51
> P99 E2EL (ms):                           6141.80
> ==================================================
> ```

> [!example]- Run A rerun, result block
> ```
> ============ Serving Benchmark Result ============
> Successful requests:                     200
> Failed requests:                         0
> Maximum request concurrency:             30
> Benchmark duration (s):                  82.17
> Total input tokens:                      25600
> Total generated tokens:                  204800
> Request throughput (req/s):              2.43
> Output token throughput (tok/s):         2492.29
> Peak output token throughput (tok/s):    2760.00
> Peak concurrent requests:                60.00
> Total token throughput (tok/s):          2803.83
> ---------------Time to First Token----------------
> Mean TTFT (ms):                          95.87
> Median TTFT (ms):                        97.31
> P50 TTFT (ms):                           97.31
> P95 TTFT (ms):                           147.11
> P99 TTFT (ms):                           150.71
> -----Time per Output Token (excl. 1st token)------
> Mean TPOT (ms):                          11.39
> Median TPOT (ms):                        11.44
> P50 TPOT (ms):                           11.44
> P95 TPOT (ms):                           11.46
> P99 TPOT (ms):                           11.46
> ---------------Inter-token Latency----------------
> Mean ITL (ms):                           11.39
> Median ITL (ms):                         11.35
> P50 ITL (ms):                            11.35
> P95 ITL (ms):                            12.60
> P99 ITL (ms):                            17.81
> ----------------End-to-end Latency----------------
> Mean E2EL (ms):                          11751.30
> Median E2EL (ms):                        11804.92
> P50 E2EL (ms):                           11804.92
> P95 E2EL (ms):                           11840.15
> P99 E2EL (ms):                           11843.27
> ==================================================
> ```

> [!example]- Run B rerun, result block
> ```
> ============ Serving Benchmark Result ============
> Successful requests:                     200
> Failed requests:                         0
> Maximum request concurrency:             30
> Benchmark duration (s):                  55.62
> Total input tokens:                      819200
> Total generated tokens:                  12800
> Request throughput (req/s):              3.60
> Output token throughput (tok/s):         230.15
> Peak output token throughput (tok/s):    666.00
> Peak concurrent requests:                36.00
> Total token throughput (tok/s):          14959.44
> ---------------Time to First Token----------------
> Mean TTFT (ms):                          1326.16
> Median TTFT (ms):                        910.52
> P50 TTFT (ms):                           910.52
> P95 TTFT (ms):                           5029.53
> P99 TTFT (ms):                           7094.04
> -----Time per Output Token (excl. 1st token)------
> Mean TPOT (ms):                          110.42
> Median TPOT (ms):                        117.44
> P50 TPOT (ms):                           117.44
> P95 TPOT (ms):                           120.68
> P99 TPOT (ms):                           126.28
> ---------------Inter-token Latency----------------
> Mean ITL (ms):                           110.42
> Median ITL (ms):                         146.50
> P50 ITL (ms):                            146.50
> P95 ITL (ms):                            158.80
> P99 ITL (ms):                            161.66
> ----------------End-to-end Latency----------------
> Mean E2EL (ms):                          8282.39
> Median E2EL (ms):                        8309.91
> P50 E2EL (ms):                           8309.91
> P95 E2EL (ms):                           12431.47
> P99 E2EL (ms):                           14536.35
> ==================================================
> ```

> [!example]- Run C rerun, result block
> ```
> ============ Serving Benchmark Result ============
> Successful requests:                     200
> Failed requests:                         0
> Maximum request concurrency:             30
> Benchmark duration (s):                  43.74
> Total input tokens:                      102400
> Total generated tokens:                  102400
> Request throughput (req/s):              4.57
> Output token throughput (tok/s):         2341.14
> Peak output token throughput (tok/s):    2640.00
> Peak concurrent requests:                60.00
> Total token throughput (tok/s):          4682.29
> ---------------Time to First Token----------------
> Mean TTFT (ms):                          239.40
> Median TTFT (ms):                        136.89
> P50 TTFT (ms):                           136.89
> P95 TTFT (ms):                           677.77
> P99 TTFT (ms):                           789.43
> -----Time per Output Token (excl. 1st token)------
> Mean TPOT (ms):                          11.80
> Median TPOT (ms):                        11.60
> P50 TPOT (ms):                           11.60
> P95 TPOT (ms):                           12.49
> P99 TPOT (ms):                           12.71
> ---------------Inter-token Latency----------------
> Mean ITL (ms):                           11.80
> Median ITL (ms):                         11.51
> P50 ITL (ms):                            11.51
> P95 ITL (ms):                            12.78
> P99 ITL (ms):                            18.88
> ----------------End-to-end Latency----------------
> Mean E2EL (ms):                          6267.81
> Median E2EL (ms):                        6062.27
> P50 E2EL (ms):                           6062.27
> P95 E2EL (ms):                           6838.82
> P99 E2EL (ms):                           6962.29
> ==================================================
> ```

> [!example]- Benchmark result JSONs, six files
> ```
> ===== w1_A_decode_heavy.json =====
> {
>   "date": "20260921-221648",
>   "endpoint_type": "openai",
>   "backend": "openai",
>   "label": null,
>   "model_id": "Qwen/Qwen2.5-7B-Instruct",
>   "tokenizer_id": "Qwen/Qwen2.5-7B-Instruct",
>   "num_prompts": 200,
>   "request_rate": "inf",
>   "burstiness": 1.0,
>   "max_concurrency": 30,
>   "duration": 83.27187827788293,
>   "completed": 200,
>   "failed": 0,
>   "total_input_tokens": 25600,
>   "total_output_tokens": 204800,
>   "request_throughput": 2.4017712117960013,
>   "request_goodput": null,
>   "output_throughput": 2459.4137208791053,
>   "total_token_throughput": 2766.8404359889932,
>   "max_output_tokens_per_s": 2730.0,
>   "max_concurrent_requests": 60,
>   "rtfx": 0.0,
>   "mean_ttft_ms": 184.38423642888665,
>   "median_ttft_ms": 175.51744356751442,
>   "std_ttft_ms": 76.0049616128711,
>   "p50_ttft_ms": 175.51744356751442,
>   "p95_ttft_ms": 330.0701489439234,
>   "p99_ttft_ms": 334.0661904914304,
>   "mean_tpot_ms": 11.467771239081198,
>   "median_tpot_ms": 11.523996085157929,
>   "std_tpot_ms": 0.16666613183952805,
>   "p50_tpot_ms": 11.523996085157929,
>   "p95_tpot_ms": 11.601849343948146,
>   "p99_tpot_ms": 11.618868079184866,
>   "mean_itl_ms": 11.467771539592047,
>   "median_itl_ms": 11.363640893250704,
>   "std_itl_ms": 2.583086908513229,
>   "p50_itl_ms": 11.363640893250704,
>   "p95_itl_ms": 12.399570830166336,
>   "p99_itl_ms": 14.068310568109176,
>   "mean_e2el_ms": 11915.914214008953,
>   "median_e2el_ms": 11965.147689450532,
>   "std_e2el_ms": 179.8350002729247,
>   "p50_e2el_ms": 11965.147689450532,
>   "p95_e2el_ms": 12033.587013673969,
>   "p99_e2el_ms": 12036.960487505421
> }
>
> ===== w1_B_prefill_heavy.json =====
> {
>   "date": "20260921-222037",
>   "endpoint_type": "openai",
>   "backend": "openai",
>   "label": null,
>   "model_id": "Qwen/Qwen2.5-7B-Instruct",
>   "tokenizer_id": "Qwen/Qwen2.5-7B-Instruct",
>   "num_prompts": 200,
>   "request_rate": "inf",
>   "burstiness": 1.0,
>   "max_concurrency": 30,
>   "duration": 60.36837328085676,
>   "completed": 200,
>   "failed": 0,
>   "total_input_tokens": 819200,
>   "total_output_tokens": 12800,
>   "request_throughput": 3.312993031459097,
>   "request_goodput": null,
>   "output_throughput": 212.03155401338222,
>   "total_token_throughput": 13782.051010869845,
>   "max_output_tokens_per_s": 808.0,
>   "max_concurrent_requests": 35,
>   "rtfx": 0.0,
>   "mean_ttft_ms": 1414.3278164369985,
>   "median_ttft_ms": 907.263063127175,
>   "std_ttft_ms": 1506.3427434596117,
>   "p50_ttft_ms": 907.263063127175,
>   "p95_ttft_ms": 5394.399180822069,
>   "p99_ttft_ms": 7732.247918657956,
>   "mean_tpot_ms": 120.31534813041428,
>   "median_tpot_ms": 127.11060803294893,
>   "std_tpot_ms": 23.968954592239477,
>   "p50_tpot_ms": 127.11060803294893,
>   "p95_tpot_ms": 131.99397336381173,
>   "p99_tpot_ms": 137.63601675348738,
>   "mean_itl_ms": 120.31535434137498,
>   "median_itl_ms": 146.38040796853602,
>   "std_itl_ms": 55.89958468939664,
>   "p50_itl_ms": 146.38040796853602,
>   "p95_itl_ms": 160.3847974911332,
>   "p99_itl_ms": 164.47925873100758,
>   "mean_e2el_ms": 8994.194748653099,
>   "median_e2el_ms": 9025.239226641133,
>   "std_e2el_ms": 2255.719171100296,
>   "p50_e2el_ms": 9025.239226641133,
>   "p95_e2el_ms": 13382.492928858841,
>   "p99_e2el_ms": 15766.010556840336
> }
>
> ===== w1_C_balanced.json =====
> {
>   "date": "20260921-222210",
>   "endpoint_type": "openai",
>   "backend": "openai",
>   "label": null,
>   "model_id": "Qwen/Qwen2.5-7B-Instruct",
>   "tokenizer_id": "Qwen/Qwen2.5-7B-Instruct",
>   "num_prompts": 200,
>   "request_rate": "inf",
>   "burstiness": 1.0,
>   "max_concurrency": 30,
>   "duration": 42.069489718880504,
>   "completed": 200,
>   "failed": 0,
>   "total_input_tokens": 102400,
>   "total_output_tokens": 102400,
>   "request_throughput": 4.7540391228049845,
>   "request_goodput": null,
>   "output_throughput": 2434.068030876152,
>   "total_token_throughput": 4868.136061752304,
>   "max_output_tokens_per_s": 2640.0,
>   "max_concurrent_requests": 60,
>   "rtfx": 0.0,
>   "mean_ttft_ms": 110.13111817417666,
>   "median_ttft_ms": 104.5110875274986,
>   "std_ttft_ms": 28.743053923005487,
>   "p50_ttft_ms": 104.5110875274986,
>   "p95_ttft_ms": 176.11311038490376,
>   "p99_ttft_ms": 195.10777916759253,
>   "mean_tpot_ms": 11.558266896189512,
>   "median_tpot_ms": 11.604832378699063,
>   "std_tpot_ms": 0.16376215136031932,
>   "p50_tpot_ms": 11.604832378699063,
>   "p95_tpot_ms": 11.653491183331715,
>   "p99_tpot_ms": 11.676421354245942,
>   "mean_itl_ms": 11.560303557824605,
>   "median_itl_ms": 11.522016022354364,
>   "std_itl_ms": 1.275111386875646,
>   "p50_itl_ms": 11.522016022354364,
>   "p95_itl_ms": 12.377468100748954,
>   "p99_itl_ms": 15.686852694489144,
>   "mean_e2el_ms": 6016.405502127018,
>   "median_e2el_ms": 6035.172767937183,
>   "std_e2el_ms": 93.1539443099818,
>   "p50_e2el_ms": 6035.172767937183,
>   "p95_e2el_ms": 6117.510754452087,
>   "p99_e2el_ms": 6141.799902515486
> }
>
> ===== w1_A_rerun.json =====
> {
>   "date": "20260921-224422",
>   "endpoint_type": "openai",
>   "backend": "openai",
>   "label": null,
>   "model_id": "Qwen/Qwen2.5-7B-Instruct",
>   "tokenizer_id": "Qwen/Qwen2.5-7B-Instruct",
>   "num_prompts": 200,
>   "request_rate": "inf",
>   "burstiness": 1.0,
>   "max_concurrency": 30,
>   "duration": 82.17328031267971,
>   "completed": 200,
>   "failed": 0,
>   "total_input_tokens": 25600,
>   "total_output_tokens": 204800,
>   "request_throughput": 2.4338811745006983,
>   "request_goodput": null,
>   "output_throughput": 2492.294322688715,
>   "total_token_throughput": 2803.8311130248044,
>   "max_output_tokens_per_s": 2760.0,
>   "max_concurrent_requests": 60,
>   "rtfx": 0.0,
>   "mean_ttft_ms": 95.86511437781155,
>   "median_ttft_ms": 97.30929438956082,
>   "std_ttft_ms": 25.285765774506952,
>   "p50_ttft_ms": 97.30929438956082,
>   "p95_ttft_ms": 147.11132030934095,
>   "p99_ttft_ms": 150.70770404301584,
>   "mean_tpot_ms": 11.393384874669993,
>   "median_tpot_ms": 11.438322613354433,
>   "std_tpot_ms": 0.1436674081078486,
>   "p50_tpot_ms": 11.438322613354433,
>   "p95_tpot_ms": 11.457729186768937,
>   "p99_tpot_ms": 11.459154411262759,
>   "mean_itl_ms": 11.393497346765875,
>   "median_itl_ms": 11.350466404110193,
>   "std_itl_ms": 1.5937448859194816,
>   "p50_itl_ms": 11.350466404110193,
>   "p95_itl_ms": 12.601187732070683,
>   "p99_itl_ms": 17.811334058642387,
>   "mean_e2el_ms": 11751.297841165215,
>   "median_e2el_ms": 11804.919481975958,
>   "std_e2el_ms": 157.836788443875,
>   "p50_e2el_ms": 11804.919481975958,
>   "p95_e2el_ms": 11840.145185193978,
>   "p99_e2el_ms": 11843.274585185573
> }
>
> ===== w1_B_rerun.json =====
> {
>   "date": "20260921-224758",
>   "endpoint_type": "openai",
>   "backend": "openai",
>   "label": null,
>   "model_id": "Qwen/Qwen2.5-7B-Instruct",
>   "tokenizer_id": "Qwen/Qwen2.5-7B-Instruct",
>   "num_prompts": 200,
>   "request_rate": "inf",
>   "burstiness": 1.0,
>   "max_concurrency": 30,
>   "duration": 55.61704936577007,
>   "completed": 200,
>   "failed": 0,
>   "total_input_tokens": 819200,
>   "total_output_tokens": 12800,
>   "request_throughput": 3.596019606949726,
>   "request_goodput": null,
>   "output_throughput": 230.14525484478247,
>   "total_token_throughput": 14959.44156491086,
>   "max_output_tokens_per_s": 666.0,
>   "max_concurrent_requests": 36,
>   "rtfx": 0.0,
>   "mean_ttft_ms": 1326.1558079114184,
>   "median_ttft_ms": 910.5164168868214,
>   "std_ttft_ms": 1372.2705928633216,
>   "p50_ttft_ms": 910.5164168868214,
>   "p95_ttft_ms": 5029.52855362091,
>   "p99_ttft_ms": 7094.0399610204595,
>   "mean_tpot_ms": 110.41642696020148,
>   "median_tpot_ms": 117.4381978898531,
>   "std_tpot_ms": 21.791922308140897,
>   "p50_tpot_ms": 117.4381978898531,
>   "p95_tpot_ms": 120.67698180298541,
>   "p99_tpot_ms": 126.2762668681523,
>   "mean_itl_ms": 110.41643200009796,
>   "median_itl_ms": 146.49595017544925,
>   "std_itl_ms": 61.628055992041006,
>   "p50_itl_ms": 146.49595017544925,
>   "p95_itl_ms": 158.79567228257656,
>   "p99_itl_ms": 161.65736308321357,
>   "mean_e2el_ms": 8282.390706404112,
>   "median_e2el_ms": 8309.912487631664,
>   "std_e2el_ms": 2060.058215436475,
>   "p50_e2el_ms": 8309.912487631664,
>   "p95_e2el_ms": 12431.474351813084,
>   "p99_e2el_ms": 14536.345548960378
> }
>
> ===== w1_C_rerun.json =====
> {
>   "date": "20260921-224601",
>   "endpoint_type": "openai",
>   "backend": "openai",
>   "label": null,
>   "model_id": "Qwen/Qwen2.5-7B-Instruct",
>   "tokenizer_id": "Qwen/Qwen2.5-7B-Instruct",
>   "num_prompts": 200,
>   "request_rate": "inf",
>   "burstiness": 1.0,
>   "max_concurrency": 30,
>   "duration": 43.73931173188612,
>   "completed": 200,
>   "failed": 0,
>   "total_input_tokens": 102400,
>   "total_output_tokens": 102400,
>   "request_throughput": 4.57254565929073,
>   "request_goodput": null,
>   "output_throughput": 2341.143377556854,
>   "total_token_throughput": 4682.286755113708,
>   "max_output_tokens_per_s": 2640.0,
>   "max_concurrent_requests": 60,
>   "rtfx": 0.0,
>   "mean_ttft_ms": 239.3993312586099,
>   "median_ttft_ms": 136.8903648108244,
>   "std_ttft_ms": 182.8474547438199,
>   "p50_ttft_ms": 136.8903648108244,
>   "p95_ttft_ms": 677.7700789738446,
>   "p99_ttft_ms": 789.4254033407196,
>   "mean_tpot_ms": 11.797286775651155,
>   "median_tpot_ms": 11.603595040111626,
>   "std_tpot_ms": 0.4152206937349005,
>   "p50_tpot_ms": 11.603595040111626,
>   "p95_tpot_ms": 12.492406559942212,
>   "p99_tpot_ms": 12.713068722986021,
>   "mean_itl_ms": 11.797864544455752,
>   "median_itl_ms": 11.512220837175846,
>   "std_itl_ms": 5.2718048957532995,
>   "p50_itl_ms": 11.512220837175846,
>   "p95_itl_ms": 12.784871552139515,
>   "p99_itl_ms": 18.87583717703819,
>   "mean_e2el_ms": 6267.812873616349,
>   "median_e2el_ms": 6062.270862981677,
>   "std_e2el_ms": 336.3284856960348,
>   "p50_e2el_ms": 6062.270862981677,
>   "p95_e2el_ms": 6838.816368044354,
>   "p99_e2el_ms": 6962.290655616671
> }
>
> ```

> [!example]- Final counters, raw
> ```
> # HELP vllm:prefix_cache_queries_total Prefix cache queries, in terms of number of queried tokens.
> # TYPE vllm:prefix_cache_queries_total counter
> vllm:prefix_cache_queries_total{engine="0",model_name="Qwen/Qwen2.5-7B-Instruct"} 947238.0
> # HELP vllm:prefix_cache_hits_total Prefix cache hits, in terms of number of cached tokens.
> # TYPE vllm:prefix_cache_hits_total counter
> vllm:prefix_cache_hits_total{engine="0",model_name="Qwen/Qwen2.5-7B-Instruct"} 124480.0
> # HELP vllm:num_preemptions_total Cumulative number of preemption from the engine.
> # TYPE vllm:num_preemptions_total counter
> vllm:num_preemptions_total{engine="0",model_name="Qwen/Qwen2.5-7B-Instruct"} 0.0
> # HELP vllm:prompt_tokens_total Number of prefill tokens processed.
> # TYPE vllm:prompt_tokens_total counter
> vllm:prompt_tokens_total{engine="0",model_name="Qwen/Qwen2.5-7B-Instruct"} 947238.0
> # HELP vllm:generation_tokens_total Number of generation tokens processed.
> # TYPE vllm:generation_tokens_total counter
> vllm:generation_tokens_total{engine="0",model_name="Qwen/Qwen2.5-7B-Instruct"} 320077.0
> ```
