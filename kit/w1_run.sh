#!/usr/bin/env bash
# W1 v2 runner: Baseline and the Metrics Surface. Runs INSIDE the pod, terminal 1.
# Terminal 2 runs: python3 lab_watch.py
#
#   bash w1_run.sh preflight   # model, version, GPU, KV capacity, full idle surface   ~1 min
#   bash w1_run.sh firstgen    # one chat request, counters and usage reconciled       ~0.5 min
#   bash w1_run.sh baseline    # A, B, C at c=30, 200 prompts, 3 repeats interleaved   ~11 min
#   bash w1_run.sh rate        # fixed-rate TTFT, 70% of baseline req/s, 3 repeats     ~9 min
#   bash w1_run.sh cachedemo   # reproduces W1 v1's 13.1% prefix hits on purpose       ~1 min
#   bash w1_run.sh final       # full metrics surface, env, key-leak check, tarball    ~0.5 min
#   bash w1_run.sh all         # the six above, in that order
#
# Re-running a verb skips runs whose result exists. touch /workspace/lab/STOP to stop
# after the run in flight. SETTLE=5 bash w1_run.sh ... shortens the idle gaps.
#
# A100 arm (run sheet block 13, separate A100 pod): export WK=w1_a100 EXPECT_GPU=A100
# first, then preflight, baseline, final. Same seeds, so the prompts are identical.

source "$(cd "$(dirname "$0")" && pwd)/lab_lib.sh"
WK="${WK:-w1}"                 # week folder name; w1_a100 for the A100 arm
W="$LAB_DIR/$WK"
mkdir -p "$W"

# shape -> "input output shape-id"
declare -A SHAPE=( [A]="128 1024 1" [B]="4096 64 2" [C]="512 512 3" )
REPEATS="${REPEATS:-3}"
CONC=30
PROMPTS=200

TEN=(kv_cache_usage_perc num_requests_running num_requests_waiting num_requests_waiting_by_reason
     num_preemptions_total prefix_cache_hits_total prefix_cache_queries_total
     prompt_tokens_total generation_tokens_total iteration_tokens_total
     time_to_first_token_seconds inter_token_latency_seconds request_queue_time_seconds
     cache_config_info)

preflight() {
  say "W1 preflight"
  require_model; echo "served model OK: $MODEL"
  check_env
  capture_env "$W/env.txt"
  snap "$W/metrics-00-idle.txt"
  sed 's/{.*}//' "$W/metrics-00-idle.txt" | awk '{print $1}' | sort -u > "$W/metric-inventory.txt"
  echo "metric names in this version: $(wc -l < "$W/metric-inventory.txt")"
  for m in "${TEN[@]}"; do
    printf "%-34s %s\n" "$m" "$(grep -q "vllm:$m" "$W/metrics-00-idle.txt" && echo PRESENT || echo MISSING)"
  done | tee "$W/metric-check.txt"
  event MARK preflight "done"
  echo
  echo "Now, from the RunPod Logs tab, paste these three lines into the record:"
  echo "  Chunked prefill is enabled with max_num_batched_tokens=..."
  echo "  GPU KV cache size: ... tokens"
  echo "  Maximum concurrency for 8192 tokens per request: ...x"
}

firstgen() {
  say "W1 first generation"
  require_model; require_watch
  local b="$W/metrics-01-before-firstgen.txt" a="$W/metrics-02-after-firstgen.txt"
  event NEXT firstgen "POST /v1/chat/completions, 'Explain the KV cache in three sentences.', max_tokens 150"
  settle firstgen
  snap "$b"
  event START firstgen ""
  curl -s "$BASE/v1/chat/completions" \
    -H "Authorization: Bearer $VLLM_KEY" -H "Content-Type: application/json" \
    -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Explain the KV cache in three sentences.\"}],\"max_tokens\":150}" \
    > "$W/first-generation-response.json"
  snap "$a"
  local dp dg
  dp=$(cdelta "$b" "$a" vllm:prompt_tokens_total); dg=$(cdelta "$b" "$a" vllm:generation_tokens_total)
  event END firstgen "prompt_tokens +$dp generation_tokens +$dg"
  python3 - "$W/first-generation-response.json" "$dp" "$dg" <<'EOF' | tee "$W/first-generation-check.txt"
import json, sys
u = json.load(open(sys.argv[1]))["usage"]
dp, dg = int(sys.argv[2]), int(sys.argv[3])
print(f"usage: prompt_tokens={u['prompt_tokens']} completion_tokens={u['completion_tokens']}")
print(f"counters: prompt +{dp} generation +{dg}")
ok = u["prompt_tokens"] == dp and u["completion_tokens"] == dg
print("MATCH: the metrics surface counts exactly what the server processed" if ok else "MISMATCH: write it down, it is a finding")
print(f"The prompt was 7 words. The other {u['prompt_tokens'] - 9} or so tokens are the chat template, paid as prefill on every call.")
EOF
}

baseline() {
  say "W1 baseline: A, B, C at concurrency $CONC, $PROMPTS prompts, $REPEATS repeats"
  require_model
  local r s in out sid
  for r in $(seq 1 "$REPEATS"); do
    for s in A B C; do
      read -r in out sid <<< "${SHAPE[$s]}"
      bench "$W" "${s}_r${r}" "$in" "$out" "$CONC" "$PROMPTS" inf $((sid * 1000 + r * 100 + CONC)) \
        "baseline shape $s ($in in / $out out), repeat $r of $REPEATS" || return 1
    done
  done
  event MARK baseline "done"
}

rate() {
  say "W1 fixed-rate TTFT: Poisson arrivals at 70% of each shape's baseline req/s"
  require_model
  local r s in out sid med rps n
  for s in A B C; do
    read -r in out sid <<< "${SHAPE[$s]}"
    med=$(median_reqs "$W/json/${s}_r[0-9].json")
    if [ "$med" = "0" ]; then echo "no baseline JSONs for $s, run baseline first"; return 1; fi
    rps=$(python3 -c "print(round(0.7 * $med, 2))")
    n=$(python3 -c "print(max(60, round($rps * 40)))")
    echo "$s: baseline median $med req/s -> rate $rps req/s, $n prompts (about 40 s of arrivals)"
    for r in $(seq 1 "$REPEATS"); do
      bench "$W" "${s}_rate_r${r}" "$in" "$out" 0 "$n" "$rps" $((sid * 1000 + r * 100 + 50)) \
        "fixed rate $rps req/s, shape $s, repeat $r" || return 1
    done
  done
  event MARK rate "done"
}

cachedemo() {
  say "W1 cache demo: same seed, same prompt count, nested lengths"
  echo "Prediction: X_seed0_128 near 0 hits. X_seed0_512 near 25,600 (200 prompts x 128 shared tokens)."
  require_model
  bench "$W" X_seed0_128 128 1 0 200 inf 0 "seed 0, 128-token prompts, 1 output token" || return 1
  bench "$W" X_seed0_512 512 1 0 200 inf 0 "seed 0, 512-token prompts: the first 128 of each match the run before" || return 1
  event MARK cachedemo "done"
}

final() {
  say "W1 final capture"
  snap "$W/metrics-99-final.txt"
  capture_env "$W/env.txt"
  cp "$EVENTS" "$W/events.tsv" 2>/dev/null
  cp "$LAB_DIR/watch.csv" "$W/watch.csv" 2>/dev/null
  leak_check "$W"
  ls "$W/json" | wc -l | sed 's/^/result files: /'
  tar czf "$LAB_DIR/$WK.tgz" -C "$LAB_DIR" "$WK"
  event MARK final "$WK captured to $LAB_DIR/$WK.tgz"
  echo "Copy off from the Mac: scp -P <port> root@<pod-ip>:$LAB_DIR/$WK.tgz ."
  if [ "$WK" = w1 ]; then echo "Do NOT terminate the pod: W2 runs on it next."; else echo "Copied off? Then terminate this pod (Terminate, never Stop) and check the Storage tab."; fi
}

case "${1:-}" in
  preflight|firstgen|baseline|rate|cachedemo|final) "$1" ;;
  all) preflight && firstgen && baseline && rate && cachedemo && final ;;
  *) sed -n '2,15p' "$0"; exit 1 ;;
esac
