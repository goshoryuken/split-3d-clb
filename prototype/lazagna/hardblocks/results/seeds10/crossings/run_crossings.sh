#!/bin/bash
# Crossing-delay sensitivity with every layer crossing scaled together: the split fabric's in-CLB
# and routing crossings and the stacked fabric's routing crossing, all times k. k = 1.49 and 2.24
# put the in-CLB crossing at the layout values (504 and 760 ps, pnr/direct_crossing_results.txt;
# SPICE: 339 ps); 1.75 and 2.0 fill in between; 1.36 and 1.62 put it at SPICE with the layout's
# crossing-side loads (463 ps) and at the timing-budgeted layout (549 ps), from
# pnr/crossing_stages_results.txt; 2.72 puts the routing crossing at LaZagna's default
# (0.739 of an L4 driver) and 3.0 goes past it. ABL=1 also runs the ablation fabric (split CLB on
# stacked's routing, as ablation/run_ablation.sh) at k = 2.24. These are all the crossings there
# are: with --hard-blocks columns each RAM/DSP sits on one layer, so --hard-crossing-ps (used only
# by --hard-blocks span) changes nothing here; the arch files are identical with it at 339 or 760
# ps. Everything else as run_hb10.sh (columns, hard inputs both, relaxed 1.3x with its own width
# search, 10 seeds); routed clocks, then ideal clocks at the same widths. k = 1 is the headline
# (../ideal, ../route). Delay sets: delays_crossings.json, *_k<NNN>.
# Usage: crossings/run_crossings.sh OUT [K...]     (default K: 149 175 200 224 272 300)
# Env: VPR (default build/vpr/vpr/vpr), JOBS (parallel VPR runs per fabric, default 4), ABL=1.
HERE=$(cd "$(dirname "$0")" && pwd)
LZ=$(cd "$HERE/../../../.." && pwd)
OUT=$(mkdir -p "${1:?usage: run_crossings.sh OUT [K...]}" && cd "$1" && pwd); shift
KS=${*:-149 175 200 224 272 300}
VPR=${VPR:-$LZ/../../build/vpr/vpr/vpr}
J=$HERE/delays_crossings.json
HC=$(python3 -c "import json; print(json.load(open('$J'))['3d20own_w100']['clb_crossing'])")
run() {  # OUT JOBS ARGS...
  out=$1; jobs=$2; shift 2; mkdir -p "$out"
  python3 compare_2d_3d.py --vpr "$VPR" \
    "--vpr-args= --timing_report_detail detailed --timing_report_npaths 10" --timeout 14400 --slim \
    --seeds ${SEEDS:-1 2 3 4 5 6 7 8 9 10} --bench-dir "$LZ/hardblocks/koios" --w2d 100 --w3d 100 \
    --hard-crossing-ps "$HC" --hard-blocks columns --relax-w 1.3 --hard-inputs both --no-2d --jobs $jobs \
    --benches ${BENCHES:-eltwise_layer spmv conv_layer attention_layer tpu_like.small.os robot_rl bwave_like.fixed.small} \
    --output "$out" "$@"
}
SPLIT=(--n3d 20 --local-inputs --wire-spans 4 15 --own-layer-inputs)
one() {  # K: split and stacked, routed then ideal at the same widths
  R=$OUT/k$1_route; I=$OUT/k$1_ideal
  run $R/split ${JOBS:-4} "${SPLIT[@]}" --delays $J 2d10_w100 3d20own_w100_k$1 > $R.split.log 2>&1 &
  run $R/stack ${JOBS:-4} --stacked --delays $J 2d10_w100 3d10stack_w100_k$1 > $R.stack.log 2>&1 &
  wait
  "$LZ/hardblocks/prep_ideal.sh" $R $I > /dev/null
  run $I/split ${JOBS:-4} "${SPLIT[@]}" --delays $J 2d10_w100 3d20own_w100_k$1 --clock-modeling ideal > $I.split.log 2>&1 &
  run $I/stack ${JOBS:-4} --stacked --delays $J 2d10_w100 3d10stack_w100_k$1 --clock-modeling ideal > $I.stack.log 2>&1 &
  wait
}
abl() {  # ablation fabric at k = 2.24 (compare with k224's stacked runs)
  R=$OUT/abl224_route; I=$OUT/abl224_ideal
  run $R/split ${JOBS:-4} --n3d 20 --local-inputs --delays $J 2d10_w100 3d20_stackroute_k224 > $R.log 2>&1
  mkdir -p $R/stack; "$LZ/hardblocks/prep_ideal.sh" $R $I > /dev/null
  run $I/split ${JOBS:-4} --n3d 20 --local-inputs --delays $J 2d10_w100 3d20_stackroute_k224 --clock-modeling ideal > $I.log 2>&1
}
cd "$LZ"
for k in $KS; do one $k & done
[ -n "$ABL" ] && abl &
wait
python3 "$HERE/crossings_table.py" "$OUT"
