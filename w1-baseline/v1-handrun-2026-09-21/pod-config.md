# W1 pod configuration

RunPod, 21 September 2026. Reproduce the baseline with exactly this.

| Field | Value |
|---|---|
| Container Image | `vllm/vllm-openai:latest` |
| Container Start Command | `--model Qwen/Qwen2.5-7B-Instruct --max-model-len 8192 --gpu-memory-utilization 0.85 --host 0.0.0.0 --port 8000 --api-key <redacted>` |
| Container Disk | 40 GB |
| Network Volume | none |
| Expose HTTP Ports | 8000 |
| Expose TCP Ports | 22 |
| Env `HF_TOKEN` | unset |
| Deploy type | On-Demand |

The API key is generated per pod with `openssl rand -hex 16` and is never committed.

## What actually ran

| Field | Value |
|---|---|
| GPU | NVIDIA A100-SXM4-80GB, 81,920 MiB |
| Driver | 580.159.04 |
| Region | US-KS-2 |
| Rate paid | $1.59/hr |
| vLLM | 0.29.0, V1 engine |
| Model served | Qwen/Qwen2.5-7B-Instruct, confirmed via `/v1/models` |

Replace the whole Start Command field rather than adding to a template's own. vLLM
takes the last occurrence of a repeated flag and ignores earlier ones silently, so a
leftover `--model` wins. Check `/v1/models` after boot, every time.

## Load generator

```
vllm bench serve --backend openai --endpoint /v1/completions \
  --base-url http://localhost:8000 --header "Authorization=Bearer <redacted>" \
  --model Qwen/Qwen2.5-7B-Instruct \
  --dataset-name random --random-range-ratio 0 --ignore-eos --temperature 0 \
  --num-prompts 200 --max-concurrency 30 --request-rate inf \
  --percentile-metrics ttft,tpot,itl,e2el --metric-percentiles 50,95,99 \
  --save-result --result-dir /workspace/w1
```

Shapes: A 128 in / 1024 out, B 4096 in / 64 out, C 512 in / 512 out.
