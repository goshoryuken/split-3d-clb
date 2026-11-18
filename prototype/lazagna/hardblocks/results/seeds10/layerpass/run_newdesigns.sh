#!/bin/bash
# Experiment C: the layer pass on Koios designs it has never seen (the list and the rule that picked
# it: newdesigns_rule.txt). The same flow as the 7-design results, at two points of the crossing range:
#   k100     SPICE delays: split 3d20own_w100, stacked 3d10stack_w100 (the headline, run_hb10.sh)
#   k162pin  split 3d20own_w100_k162pin (every crossing 1.62x plus the input-pin cost,
#            crossings/run_pinpath.sh), stacked 3d10stack_w100_k162 (the pin cost is the split's only)
# For each point:
#   1. routed clocks: split (pass off) and stacked, each with its own width search, routed at 1.3x
#      its own minimum (as run_hardblocks.sh / crossings/run_crossings.sh), 2 x JOBS runs each;
#   2. ideal clocks at the same widths (prep_ideal.sh), and split with the pass, routed and ideal, at
#      the pass-off twin's track count (--widths, as run_layerpass.sh).
# VPR runs under /usr/bin/time -l (hardblocks/vpr_timed.sh, as the headline's TIMED=1), so each
# run.log and min_width.log ends with wall time and peak memory; results are unaffected.
# Layout: OUT/<point>_{route,ideal}/{split,stack} (pass off), OUT/on/<point>_{route,ideal}/split.
# TRIAL=1: only seed 1 of the split k100 routed runs, each VPR step capped at 30 minutes (the trial of
# newdesigns_rule.txt; the full sweep reuses it). TRIAL_TIMEOUT changes the cap (experiment E's
# lstm and dla_like.small trials: 28800, with an 8-hour stop on the whole trial outside this script).
# Usage: layerpass/run_newdesigns.sh OUT     Env: BENCHES (required), BENCH (netlist folder, default
# hardblocks/koios), VPR, JOBS (per run, default 3),
# POINTS (default "k100 k162pin"), TRIAL=1, TRIAL_TIMEOUT.
HERE=$(cd "$(dirname "$0")" && pwd)
S10=$(cd "$HERE/.." && pwd)
LZ=$(cd "$HERE/../../../.." && pwd)
OUT=$(mkdir -p "${1:?usage: run_newdesigns.sh OUT}" && cd "$1" && pwd)
export VPR_REAL=${VPR:-$LZ/../../build/vpr/vpr/vpr}
J=$S10/crossings/delays_crossings.json
BENCHES=${BENCHES:?designs}
SEEDS="1 2 3 4 5 6 7 8 9 10"; TIMEOUT=14400
[ -n "$TRIAL" ] && { SEEDS=1; TIMEOUT=${TRIAL_TIMEOUT:-1800}; }
run() {  # OUT ARGS...
  out=$1; shift; mkdir -p "$out"
  python3 compare_2d_3d.py --vpr "$LZ/hardblocks/vpr_timed.sh" \
    "--vpr-args= --timing_report_detail detailed --timing_report_npaths 10" --timeout $TIMEOUT --slim \
    --seeds $SEEDS --bench-dir "${BENCH:-$LZ/hardblocks/koios}" --w2d 100 --w3d 100 \
    --hard-crossing-ps 339.23 --hard-blocks columns --relax-w 1.3 --hard-inputs both --no-2d \
    --jobs ${JOBS:-3} --benches $BENCHES --output "$out" "$@"
}
SPLIT=(--n3d 20 --local-inputs --wire-spans 4 15 --own-layer-inputs)
split_set() { case $1 in k100) echo 3d20own_w100;; *) echo 3d20own_w100_$1;; esac; }
stack_set() { case $1 in k100) echo 3d10stack_w100;; k162pin) echo 3d10stack_w100_k162;; esac; }
IDEAL=(--clock-modeling ideal)
cd "$LZ"
if [ -n "$TRIAL" ]; then
  run $OUT/k100_route/split "${SPLIT[@]}" --delays $J 2d10_w100 3d20own_w100 > $OUT/trial.log 2>&1
  exit
fi
point() {  # K
  R=$OUT/$1_route; I=$OUT/$1_ideal; P=$(split_set $1); T=$(stack_set $1)
  JOBS=$((2 * ${JOBS:-3})) run $R/split "${SPLIT[@]}" --delays $J 2d10_w100 $P > $R.split.log 2>&1 &
  JOBS=$((2 * ${JOBS:-3})) run $R/stack --stacked --delays $J 2d10_w100 $T > $R.stack.log 2>&1 &
  wait
  "$LZ/hardblocks/prep_ideal.sh" $R $I > /dev/null
  # prep_ideal.sh seeds only routed runs that routed. One whose relaxed route failed still has its
  # width, and its ideal twin must route at it too, not at a width search of its own.
  for d in $R/split/*_hb*/ $R/stack/*_hb*/; do
    t=$I/$(basename $(dirname $d))/$(basename $d)_clkideal
    [ -s $d/width.txt ] && [ ! -e $t ] && mkdir -p $t && cp $d/arch.xml $d/width.txt $t/
  done
  run $I/split "${SPLIT[@]}" --delays $J 2d10_w100 $P "${IDEAL[@]}" > $I.split.log 2>&1 &
  run $I/stack --stacked --delays $J 2d10_w100 $T "${IDEAL[@]}" > $I.stack.log 2>&1 &
  run $OUT/on/$1_route/split "${SPLIT[@]}" --delays $J 2d10_w100 $P --layer-pass \
    --widths $R/split/results.csv > $OUT/on/$1_route.log 2>&1 &
  run $OUT/on/$1_ideal/split "${SPLIT[@]}" --delays $J 2d10_w100 $P --layer-pass \
    --widths $R/split/results.csv "${IDEAL[@]}" > $OUT/on/$1_ideal.log 2>&1 &
  wait
}
mkdir -p $OUT/on
for k in ${POINTS:-k100 k162pin}; do point $k; done
