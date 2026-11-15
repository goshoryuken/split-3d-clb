#!/bin/bash
# Rerun the Koios results from a fresh clone: 2D, LaZagna-style stacked CLBs and the split CLB,
# RAM/DSP in per-layer columns, routed clocks (minimum-width search, then 1.3x relaxed), then
# ideal clocks at the same widths. ABLATION=1 also runs the split CLB on the stacked fabric's
# exact routing. Prints the same ratios as hardblocks/results/seeds10/{ideal,route}_table.txt.
#
# Usage (from anywhere, after the README build):
#   prototype/lazagna/reproduce_koios.sh OUT              # 7 designs x 10 seeds
#   QUICK=1 prototype/lazagna/reproduce_koios.sh OUT      # spmv, seed 1 only (a few minutes)
# Env: VPR (default build/vpr/vpr/vpr), JOBS (parallel VPR runs per fabric, default 4),
#      ABLATION=1, BENCHES / SEEDS to choose designs and seeds.
# Each VPR run needs about 1.5 GB of memory. The full sweep is about 420 VPR runs.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
OUT=$(mkdir -p "${1:?usage: reproduce_koios.sh OUT}" && cd "$1" && pwd)
export VPR=${VPR:-$ROOT/build/vpr/vpr/vpr}
[ -x "$VPR" ] || { echo "no VPR at $VPR: build it first (README, Build) or set VPR"; exit 1; }
ALL="eltwise_layer spmv conv_layer attention_layer tpu_like.small.os robot_rl bwave_like.fixed.small"
if [ -n "$QUICK" ]; then BENCHES=${BENCHES:-spmv}; SEEDS=${SEEDS:-1}; fi
export BENCHES=${BENCHES:-$ALL} SEEDS=${SEEDS:-1 2 3 4 5 6 7 8 9 10}
export BENCH=$HERE/hardblocks/koios RELAX=1.3 HARD_INPUTS=both PLACEMENTS=columns
export JOBS_SPLIT=${JOBS:-4} JOBS_STACK=${JOBS:-4}
cd "$HERE"

echo "== routed clocks -> $OUT/route"
./run_hardblocks.sh "$OUT/route"
hardblocks/prep_ideal.sh "$OUT/route" "$OUT/ideal" > /dev/null
echo "== ideal clocks -> $OUT/ideal"
CLOCK=ideal ./run_hardblocks.sh "$OUT/ideal"

if [ -n "$ABLATION" ]; then
  # The split CLB with stacked's routing: pins reach both layers (no --own-layer-inputs), L16 spans
  # 16 tiles (no --wire-spans), and the stacked SPICE set's routing delays (3d20_stackroute).
  J=$HERE/hardblocks/results/seeds10/ablation/delays_ablation.json
  HC=$(python3 -c "import json; print(json.load(open('$J'))['3d20own_w100']['clb_crossing'])")
  abl() {  # OUT [extra]
    mkdir -p "$1/split"
    python3 compare_2d_3d.py --vpr "$VPR" "--vpr-args= --timing_report_detail detailed --timing_report_npaths 10" \
      --timeout 14400 --slim --seeds $SEEDS --bench-dir "$BENCH" --w2d 100 --w3d 100 --hard-crossing-ps "$HC" \
      --hard-blocks columns --relax-w 1.3 --hard-inputs both --no-2d --jobs ${JOBS:-4} --benches $BENCHES \
      --n3d 20 --local-inputs --delays "$J" 2d10_w100 3d20_stackroute --output "$1/split" "${@:2}" > "$1.log" 2>&1
  }
  echo "== ablation, routed then ideal clocks -> $OUT/ablation_route, $OUT/ablation_ideal"
  abl "$OUT/ablation_route"
  mkdir -p "$OUT/ablation_route/stack"; hardblocks/prep_ideal.sh "$OUT/ablation_route" "$OUT/ablation_ideal" > /dev/null
  abl "$OUT/ablation_ideal" --clock-modeling ideal
fi

for m in ideal route; do
  echo; echo "== $m clocks: 3D over 2D, and split over stacked (lower is faster)"
  python3 compare_configs.py "$OUT/$m/split/results_columns.csv:2d" \
    stacked="$OUT/$m/stack/results_columns.csv:3d" split="$OUT/$m/split/results_columns.csv:3d" | tail -3
  args=(split="$OUT/$m/split/results_columns.csv:3d")
  [ -n "$ABLATION" ] && args+=(ablation="$OUT/ablation_$m/split/results_columns.csv:3d")
  python3 compare_configs.py "$OUT/$m/stack/results_columns.csv:3d" "${args[@]}" | tail -$((${#args[@]} + 1))
done
