# shellcheck shell=bash disable=SC2054
# lab_lib.sh: shared helpers for the week runners. Sourced, never run directly.
#
# Every step the runner takes is written to $LAB_DIR/events.tsv with a UTC
# timestamp to the millisecond, and printed here as:
#   [12:03:04.512] NEXT   B_c30_r1  vllm bench serve ... (the exact command)
#   [12:03:14.530] START  B_c30_r1
#   [12:04:15.101] END    B_c30_r1  completed=200/200 ...
# lab_watch.py in terminal 2 prints the same events in line with its gauges.

set -uo pipefail

: "${VLLM_KEY:?export VLLM_KEY first (the key in the pod Start Command)}"
BASE="${BASE:-http://localhost:8000}"
MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}"
EXPECT_VLLM="${EXPECT_VLLM:-0.29.0}"
EXPECT_GPU="${EXPECT_GPU:-H100}"   # series GPU from 10 Nov 2026; the W1 A100 arm sets EXPECT_GPU=A100
LAB_DIR="${LAB_DIR:-/workspace/lab}"
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETTLE="${SETTLE:-10}"          # idle seconds before every run, so gauges return to zero
EVENTS="$LAB_DIR/events.tsv"
mkdir -p "$LAB_DIR"

now_epoch() { date -u +%s.%3N; }
now_utc()   { date -u +%H:%M:%S.%3N; }

event() { # kind tag detail
  local t u
  read -r t u < <(date -u +"%s.%3N %H:%M:%S.%3N")
  printf '%s\t%s\t%s\t%s\t%s\n' "$t" "$u" "$1" "$2" "${3:-}" >> "$EVENTS"
  printf '[%s] %-6s %s  %s\n' "$u" "$1" "$2" "${3:-}"
}

say() { printf '\n==== %s ====\n' "$*"; }

snap() { curl -s "$BASE/metrics" | grep -E "^vllm" | grep -v "_created" > "$1"; }

counter() { # file metric -> summed value across label sets
  awk -v m="$2" '$1 == m || index($1, m "{") == 1 {s += $NF} END {printf "%.0f", s + 0}' "$1"
}

cdelta() { # before after metric
  echo $(( $(counter "$2" "$3") - $(counter "$1" "$3") ))
}

stopped() { [ -e "$LAB_DIR/STOP" ]; }

require_model() {
  local served
  served=$(curl -s "$BASE/v1/models" -H "Authorization: Bearer $VLLM_KEY" \
           | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"][0]["id"])' 2>/dev/null)
  if [ "$served" != "$MODEL" ]; then
    echo "ABORT: /v1/models reports '$served', expected '$MODEL'."
    echo "Wrong model, wrong key, or server not up. Nothing was measured."
    exit 1
  fi
}

require_watch() {
  # The monitor must be running so every run has a server-side timeline.
  local hb="$LAB_DIR/.watch_heartbeat" age
  if [ -e "$hb" ]; then
    age=$(python3 -c "import time;print(int(time.time()-float(open('$hb').read() or 0)))" 2>/dev/null || echo 999)
  else
    age=999
  fi
  if [ "$age" -gt 5 ]; then
    echo "lab_watch.py is not running in terminal 2. Starting a silent copy so no data is lost."
    echo "Start the visible one in terminal 2 when you can: python3 $KIT/lab_watch.py"
    nohup python3 "$KIT/lab_watch.py" --quiet >/dev/null 2>&1 &
    sleep 2
  fi
}

settle() { # tag
  event SETTLE "$1" "${SETTLE}s idle so gauges return to zero"
  sleep "$SETTLE"
}

# bench <week_dir> <tag> <in> <out> <concurrency|0> <num_prompts> <rate|inf> <seed> [label]
bench() {
  local wdir=$1 tag=$2 in=$3 outl=$4 c=$5 n=$6 rate=$7 seed=$8 label=${9:-}
  mkdir -p "$wdir/json" "$wdir/metrics" "$wdir/logs"
  if stopped; then echo "STOP file present, not starting $tag. rm $LAB_DIR/STOP to resume."; return 1; fi
  if [ -e "$wdir/json/$tag.json" ]; then echo "skip $tag, result exists"; return 0; fi

  local conc_args=()
  [ "$c" != 0 ] && conc_args=(--max-concurrency "$c")
  local cmd=(vllm bench serve
    --backend openai --endpoint /v1/completions --base-url "$BASE"
    --header "Authorization=Bearer $VLLM_KEY" --model "$MODEL"
    --dataset-name random --random-input-len "$in" --random-output-len "$outl"
    --random-range-ratio 0 --ignore-eos --temperature 0 --seed "$seed"
    --num-prompts "$n" --request-rate "$rate" "${conc_args[@]}"
    --percentile-metrics ttft,tpot,itl,e2el --metric-percentiles 50,95,99
    --save-result --result-dir "$wdir/json" --result-filename "$tag.json"
    --metadata "tag=$tag" "in=$in" "out=$outl" "concurrency=$c" "seed=$seed")

  require_watch
  local shown="${cmd[*]}"
  event NEXT "$tag" "${label:+$label | }${shown//$VLLM_KEY/\$VLLM_KEY}"
  settle "$tag"
  snap "$wdir/metrics/${tag}_before.txt"
  event START "$tag" "in=$in out=$outl c=$c n=$n rate=$rate seed=$seed"
  "${cmd[@]}" 2>&1 | grep -v "^Namespace(" | grep -vF "$VLLM_KEY" > "$wdir/logs/$tag.log" || true
  snap "$wdir/metrics/${tag}_after.txt"

  local b="$wdir/metrics/${tag}_before.txt" a="$wdir/metrics/${tag}_after.txt" ok
  ok=$(python3 -c "import json;print(json.load(open('$wdir/json/$tag.json'))['completed'])" 2>/dev/null || echo 0)
  event END "$tag" "completed=$ok/$n prefix_hits=$(cdelta "$b" "$a" vllm:prefix_cache_hits_total)/$(cdelta "$b" "$a" vllm:prefix_cache_queries_total) preemptions=$(cdelta "$b" "$a" vllm:num_preemptions_total)"
  grep -E "Request throughput|Output token throughput|Mean TTFT|P95 TTFT|Mean TPOT|P95 TPOT" "$wdir/logs/$tag.log" | sed 's/^/              /'
  if [ "$ok" != "$n" ]; then
    echo "!!!!! $tag completed $ok of $n. Read $wdir/logs/$tag.log."
    echo "      Kept as $tag.failed.json so a re-run repeats it. rm $LAB_DIR/STOP, then re-run the same verb."
    mv "$wdir/json/$tag.json" "$wdir/json/$tag.failed.json" 2>/dev/null
    touch "$LAB_DIR/STOP"
    event FAIL "$tag" "completed $ok of $n"
    return 1
  fi
}

median_reqs() { # dir glob -> median request_throughput of matching JSONs
  python3 - "$@" <<'EOF'
import glob, json, statistics, sys
xs = [json.load(open(f))["request_throughput"] for f in sorted(glob.glob(sys.argv[1]))]
print(f"{statistics.median(xs):.4f}" if xs else "0")
EOF
}

capture_env() { # out_file
  { python3 -c "import vllm; print('vllm', vllm.__version__)" 2>/dev/null || echo "vllm unknown"
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null || echo "gpu unknown"
    curl -s "$BASE/metrics" | grep '^vllm:cache_config_info'
    date -u +"captured %Y-%m-%dT%H:%M:%SZ"
  } > "$1"
}

check_env() { # warn on version or GPU drift, print KV capacity
  local v gpu info blocks bsize
  v=$(python3 -c "import vllm; print(vllm.__version__)" 2>/dev/null || echo unknown)
  gpu=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
  echo "vllm $v   gpu $gpu"
  [ "$v" != "$EXPECT_VLLM" ] && echo "WARNING: vLLM is $v, not $EXPECT_VLLM. Numbers are not directly comparable to W1 v1. Record it."
  case "$gpu" in *SXM*|*"H100 80GB HBM3"*) ;; *) echo "WARNING: GPU is not an SXM part. Record it; it changes comparability." ;; esac
  case "$gpu" in *"$EXPECT_GPU"*) ;; *) echo "WARNING: GPU is not $EXPECT_GPU. Every prediction in the run sheet assumes $EXPECT_GPU. Stop and check." ;; esac
  info=$(curl -s "$BASE/metrics" | grep '^vllm:cache_config_info')
  blocks=$(echo "$info" | grep -o 'num_gpu_blocks="[0-9]*"' | grep -o '[0-9]*')
  bsize=$(echo "$info" | grep -o 'block_size="[0-9]*"' | grep -o '[0-9]*')
  if [ -n "$blocks" ] && [ -n "$bsize" ]; then
    echo "KV capacity: $((blocks * bsize)) tokens ($blocks blocks of $bsize)"
  else
    echo "KV capacity: cache_config_info not parsed; use 'GPU KV cache size' from the Logs tab"
  fi
}

leak_check() { # dir
  if grep -rlF "$VLLM_KEY" "$1" 2>/dev/null; then echo "LEAK: the files above contain the key. Delete them before copying off."; else echo "key-leak check: clean"; fi
}
