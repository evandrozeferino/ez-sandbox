#!/usr/bin/env bash
# W2 v2 runner: Saturation, Batching and Preemption. Runs INSIDE the pod, terminal 1,
# on the same pod as W1 v2. Terminal 2 keeps running: python3 lab_watch.py
#
#   bash w2_run.sh preflight   # config check and the predictions to test          ~0.5 min
#   bash w2_run.sh sweep B     # prefill-heavy ladder, 3 repeats interleaved       ~16 min
#   bash w2_run.sh sweep A     # decode-heavy ladder, 3 repeats interleaved        ~25 min
#   bash w2_run.sh rate        # fixed-rate TTFT at 70% of each shape's best req/s ~8 min
#   bash w2_run.sh final       # env, full surface, key-leak check, tarball        ~0.5 min
#   bash w2_run.sh all         # the five above, in that order
#   bash w2_run.sh lever       # ONLY after the lever restart (run sheet block 6)  ~6 min
#
# GPU: H100 SXM 80GB from 10 Nov 2026. Ladders and predictions assume it.
#
# Long verbs survive an SSH drop only under nohup; the run sheet shows how.
# Re-running a verb skips finished runs. touch /workspace/lab/STOP to stop cleanly.

SETTLE="${SETTLE:-5}"
source "$(cd "$(dirname "$0")" && pwd)/lab_lib.sh"
W="$LAB_DIR/w2"
mkdir -p "$W"

declare -A SHAPE=( [A]="128 1024 1" [B]="4096 64 2" )
LADDER_A=(1 32 64 128 256 512 1024)   # H100: KV fills near 790 running, so 1024 must preempt; c=1 is the decode ceiling (post 01)
LADDER_B=(8 16 32 64 128 256)         # H100: the 8,192 budget holds B near 126 running, so 256 shows the queue
REPEATS="${REPEATS:-3}"

prompts_for() { # shape concurrency
  local s=$1 c=$2 n
  if [ "$c" -le 32 ] || { [ "$s" = A ] && [ "$c" -le 256 ]; }; then n=$((4 * c)); else n=$((2 * c)); fi
  [ "$n" -lt 64 ] && n=64
  [ "$c" = 1 ] && n=4   # c=1 decodes ~200 tok/s on H100; 64 prompts would take ~5 min a repeat
  echo "$n"
}

preflight() {
  say "W2 preflight"
  require_model; echo "served model OK: $MODEL"
  check_env
  capture_env "$W/env.txt"
  snap "$W/metrics-00-start.txt"
  cat <<'EOF'

Predictions to test (H100 SXM 80GB, vLLM 0.29.0 defaults; derivations in the run sheet):
  token budget 8,192 per step, sequence cap 1,024, KV capacity ~880,000-940,000 tokens
  B: running plateaus near 126 from c=128 up; req/s flat past it (~8-11, estimate);
     tok/step near 8,192 when saturated; P95 TPOT rises to ~200 ms+ (estimate); KV ~58%
  A: c=1 below the ~220 tok/s paper ceiling; running = c up to 512; KV ~32% at 256, ~65% at 512;
     at 1024 KV pins near 100% and preemptions start; throughput no higher than at 512
  preemptions: zero on B and on A up to 512; above zero at A c=1024, on default config
EOF
  event MARK preflight "done"
}

sweep() {
  local s=${1:?shape A or B} in out sid r c ladder
  read -r in out sid <<< "${SHAPE[$s]}"
  if [ "$s" = A ]; then ladder=("${LADDER_A[@]}"); else ladder=("${LADDER_B[@]}"); fi
  say "W2 sweep $s ($in in / $out out): ladder ${ladder[*]}, $REPEATS repeats interleaved"
  require_model
  for r in $(seq 1 "$REPEATS"); do
    for c in "${ladder[@]}"; do
      bench "$W" "${s}_c${c}_r${r}" "$in" "$out" "$c" "$(prompts_for "$s" "$c")" inf \
        $((sid * 100000 + c * 10 + r)) "sweep $s, concurrency $c, repeat $r of $REPEATS" || return 1
    done
  done
  event MARK "sweep_$s" "done"
}

rate() {
  say "W2 fixed-rate TTFT: Poisson arrivals at 70% of each shape's best median req/s"
  require_model
  local s in out sid best rps n r
  for s in B A; do
    read -r in out sid <<< "${SHAPE[$s]}"
    best=$(python3 - "$W" "$s" <<'EOF'
# Best median req/s over the sweep points that are safe to aim at: completed runs only
# (not *.failed.json) and no preemptions in any repeat. W2 v2 picked A's rate with a
# failed run inside c=1024's median; c=1024 also preempted, so it is not a target.
import glob, json, os, re, statistics, sys
w, shape = sys.argv[1], sys.argv[2]
def preempted(tag):
    def val(path):
        try:
            for line in open(path):
                if line.startswith("vllm:num_preemptions_total"):
                    return float(line.split()[-1])
        except OSError:
            pass
        return 0.0
    m = os.path.join(w, "metrics", tag)
    return val(m + "_after.txt") - val(m + "_before.txt") > 0
by, bad = {}, set()
for f in glob.glob(os.path.join(w, "json", f"{shape}_c*_r*.json")):
    m = re.search(r"_c(\d+)_r\d+\.json$", os.path.basename(f))
    if not m:
        continue  # skips A_c1024_r1.failed.json and similar
    c, tag = int(m.group(1)), os.path.basename(f)[:-5]
    by.setdefault(c, []).append(json.load(open(f))["request_throughput"])
    if preempted(tag):
        bad.add(c)
ok = {c: v for c, v in by.items() if c not in bad}
if bad:
    print(f"excluded (preempted): c={sorted(bad)}", file=sys.stderr)
print(f"{max(statistics.median(v) for v in ok.values()):.4f}" if ok else "0")
EOF
)
    if [ "$best" = "0" ]; then echo "no sweep results for $s, run sweep $s first"; return 1; fi
    rps=$(python3 -c "print(round(0.7 * $best, 2))")
    n=$(python3 -c "print(max(100, round($rps * 40)))")
    echo "$s: best median $best req/s -> rate $rps req/s, $n prompts"
    for r in $(seq 1 "$REPEATS"); do
      bench "$W" "${s}_rate_r${r}" "$in" "$out" 0 "$n" "$rps" $((sid * 100000 + 90000 + r)) \
        "fixed rate $rps req/s, shape $s, repeat $r" || return 1
    done
  done
  event MARK rate "done"
}

lever() {
  say "W2 lever run: expects the server restarted with --max-num-batched-tokens 2048 --max-num-seqs 256 (the A100 defaults)"
  require_model
  check_env
  local r
  for r in $(seq 1 "$REPEATS"); do
    bench "$W" "L_B_c128_r${r}" 4096 64 128 256 inf $((250000 + r)) "lever: B at c=128, budget 2048" || return 1
  done
  bench "$W" L_A_c1024_r1 128 1024 1024 2048 inf 150001 "lever: A at c=1024, seq cap 256, expect queueing and zero preemptions" || return 1
  event MARK lever "done"
}

final() {
  say "W2 final capture"
  snap "$W/metrics-99-final.txt"
  capture_env "$W/env-final.txt"
  cp "$EVENTS" "$W/events.tsv" 2>/dev/null
  cp "$LAB_DIR/watch.csv" "$W/watch.csv" 2>/dev/null
  leak_check "$W"
  ls "$W/json" | wc -l | sed 's/^/result files: /'
  tar czf "$LAB_DIR/w2.tgz" -C "$LAB_DIR" w2
  event MARK final "w2 captured to $LAB_DIR/w2.tgz"
  echo "Copy off from the Mac: scp -P <port> root@<pod-ip>:$LAB_DIR/w2.tgz ."
}

case "${1:-}" in
  preflight|rate|final|lever) "$1" ;;
  sweep) sweep "${2:-}" ;;
  all) preflight && sweep B && sweep A && rate && final ;;
  *) sed -n '2,15p' "$0"; exit 1 ;;
esac
