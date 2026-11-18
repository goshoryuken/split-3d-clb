#!/bin/bash
# Experiment E: the 3 designs of experiment C (reduction_layer, softmax, tpu_like.small.ws, picked by
# newdesigns_rule.txt) at the settings C skipped, so every table can have 10 designs. Each set is made
# as the 7 designs' committed set was, in C's flow (run_newdesigns.sh: netlists from hardblocks/koios, VPR
# under hardblocks/vpr_timed.sh, 10 seeds, each fabric at 1.3x its own minimum tracks, ideal clocks
# at the routed widths):
#   k162 k224 k272 k300  crossings/run_crossings.sh: split (pass off) 3d20own_w100_kNNN and stacked
#        3d10stack_w100_kNNN, routed then ideal; then the split with the pass at its pass-off twin's
#        track count (--widths, as run_layerpass.sh). k162 runs no stacked: C's k162pin point already
#        ran stacked 3d10stack_w100_k162 (newdesigns/k162pin_*/stack).
#   2d   the 10-LUT 2D fabric at k = 1 (SPICE delays), as run_hb10.sh: compare_2d_3d.py's split pass
#        without --no-2d. With C=DIR (run_newdesigns.sh's output) C's k = 1 split runs are copied in
#        first and reused, so only the 2D runs are new.
#   abl  ablation/run_ablation.sh: the split CLB on the stacked fabric's exact routing
#        (ablation/delays_ablation.json, 3d20_stackroute) at k = 1, routed then ideal.
#   eq   equal_tracks/run_equal_tracks.sh: stacked at the split's track count, routed and ideal (VPR
#        through equal_tracks/vpr_eq.sh, untimed, as there). The split's widths: EQ_LOOKUP, or with
#        C=DIR C's k = 1 split runs (their width.txt), written to OUT/split_widths.tsv.
# Runs ideal clocks for routed runs whose relaxed route failed too, at their width (as run_newdesigns.sh).
# At most two compare_2d_3d.py runs at a time, each with JOBS parallel VPR runs (2 x JOBS when alone).
# Layout: OUT/kNNN_{route,ideal}/{split,stack}, OUT/on/kNNN_{route,ideal}/split,
# OUT/2d_{route,ideal}/split, OUT/abl_{route,ideal}/split, OUT/eq_{route,ideal}/stack.
# Usage: layerpass/run_newdesigns_e.sh OUT    Env: C, VPR, JOBS (default 6), STEPS (default
# "k162 k224 k272 k300 2d abl eq"), BENCHES (default the 3), SEEDS (default 1-10), EQ_LOOKUP, BENCH
# (netlist folder, default hardblocks/koios).
HERE=$(cd "$(dirname "$0")" && pwd)
S10=$(cd "$HERE/.." && pwd)
LZ=$(cd "$HERE/../../../.." && pwd)
OUT=$(mkdir -p "${1:?usage: run_newdesigns_e.sh OUT}" && cd "$1" && pwd)
export VPR_REAL=${VPR:-$LZ/../../build/vpr/vpr/vpr}
J=$S10/crossings/delays_crossings.json
BENCHES=${BENCHES:-reduction_layer softmax tpu_like.small.ws}
SEEDS=${SEEDS:-1 2 3 4 5 6 7 8 9 10}
JOBS=${JOBS:-6}
VPRW=$LZ/hardblocks/vpr_timed.sh
run() {  # OUT JOBS ARGS...
  out=$1; jobs=$2; shift 2; mkdir -p "$out"
  python3 compare_2d_3d.py --vpr "$VPRW" \
    "--vpr-args= --timing_report_detail detailed --timing_report_npaths 10" --timeout 14400 --slim \
    --seeds $SEEDS --bench-dir "${BENCH:-$LZ/hardblocks/koios}" --w2d 100 --w3d 100 \
    --hard-crossing-ps 339.23 --hard-blocks columns --relax-w 1.3 --hard-inputs both --jobs $jobs \
    --benches $BENCHES --output "$out" "$@"
}
SPLIT=(--n3d 20 --local-inputs --wire-spans 4 15 --own-layer-inputs)
IDEAL=(--clock-modeling ideal)
seed_ideal() {  # R I: ideal-clock folders at the routed widths
  mkdir -p $1/split $1/stack
  "$LZ/hardblocks/prep_ideal.sh" $1 $2 > /dev/null
  # prep_ideal.sh seeds only routed runs that routed. One whose relaxed route failed still has its
  # width, and its ideal twin must route at it too, not at a width search of its own.
  for d in $1/split/*_hb*/ $1/stack/*_hb*/; do
    [ -d $d ] || continue
    t=$2/$(basename $(dirname $d))/$(basename $d)_clkideal
    [ -s $d/width.txt ] && [ ! -e $t ] && mkdir -p $t && cp $d/arch.xml $d/width.txt $t/
  done
}
point() {  # K
  R=$OUT/$1_route; I=$OUT/$1_ideal; P=3d20own_w100_$1; T=3d10stack_w100_$1
  if [ $1 = k162 ]; then
    run $R/split $((2 * JOBS)) "${SPLIT[@]}" --no-2d --delays $J 2d10_w100 $P > $R.split.log 2>&1
  else
    run $R/split $JOBS "${SPLIT[@]}" --no-2d --delays $J 2d10_w100 $P > $R.split.log 2>&1 &
    run $R/stack $JOBS --stacked --no-2d --delays $J 2d10_w100 $T > $R.stack.log 2>&1 &
    wait
  fi
  seed_ideal $R $I
  if [ $1 = k162 ]; then
    run $I/split $((2 * JOBS)) "${SPLIT[@]}" --no-2d --delays $J 2d10_w100 $P "${IDEAL[@]}" > $I.split.log 2>&1
  else
    run $I/split $JOBS "${SPLIT[@]}" --no-2d --delays $J 2d10_w100 $P "${IDEAL[@]}" > $I.split.log 2>&1 &
    run $I/stack $JOBS --stacked --no-2d --delays $J 2d10_w100 $T "${IDEAL[@]}" > $I.stack.log 2>&1 &
    wait
  fi
  ON=("${SPLIT[@]}" --no-2d --delays $J 2d10_w100 $P --layer-pass --widths $R/split/results.csv)
  run $OUT/on/$1_route/split $JOBS "${ON[@]}" > $OUT/on/$1_route.log 2>&1 &
  run $OUT/on/$1_ideal/split $JOBS "${ON[@]}" "${IDEAL[@]}" > $OUT/on/$1_ideal.log 2>&1 &
  wait
}
twod() {
  R=$OUT/2d_route; I=$OUT/2d_ideal; mkdir -p $R/split $I/split
  if [ -n "$C" ]; then  # C's k = 1 split runs, reused by compare_2d_3d.py
    for d in "$C"/k100_route/split/3d_*/; do [ -e $R/split/$(basename $d) ] || cp -R "${d%/}" $R/split/; done
    for d in "$C"/k100_ideal/split/3d_*/; do [ -e $I/split/$(basename $d) ] || cp -R "${d%/}" $I/split/; done
  fi
  run $R/split $((2 * JOBS)) "${SPLIT[@]}" --delays $J 2d10_w100 3d20own_w100 > $R.log 2>&1
  seed_ideal $R $I
  run $I/split $((2 * JOBS)) "${SPLIT[@]}" --delays $J 2d10_w100 3d20own_w100 "${IDEAL[@]}" > $I.log 2>&1
}
abl() {
  R=$OUT/abl_route; I=$OUT/abl_ideal
  A=(--n3d 20 --local-inputs --no-2d --delays $S10/ablation/delays_ablation.json 2d10_w100 3d20_stackroute)
  run $R/split $((2 * JOBS)) "${A[@]}" > $R.log 2>&1
  seed_ideal $R $I
  run $I/split $((2 * JOBS)) "${A[@]}" "${IDEAL[@]}" > $I.log 2>&1
}
eq() {
  export EQ_LOOKUP=${EQ_LOOKUP:-$OUT/split_widths.tsv}
  if [ ! -s "$EQ_LOOKUP" ]; then
    python3 - "${C:?eq needs C or EQ_LOOKUP}/k100_route/split" > "$EQ_LOOKUP" <<'EOF'
import pathlib, re, sys
print("# bench\tseed\tsplit_min_width\tsplit_relaxed_width")
for d in sorted(pathlib.Path(sys.argv[1]).glob("3d_*_hbcolumns")):
    m = re.fullmatch(r"3d_n20_wx1\.3_s1\.0_c[\d.]+_(.+)_(\d+)_hbcolumns", d.name)
    if (d / "width.txt").exists():
        relaxed, least = (d / "width.txt").read_text().split()[:2]
        print(f"{m.group(1)}\t{m.group(2)}\t{least}\t{relaxed}")
EOF
  fi
  VPRW=$S10/equal_tracks/vpr_eq.sh
  run $OUT/eq_route/stack $JOBS --stacked --no-2d --delays $J 2d10_w100 3d10stack_w100 > $OUT/eq_route.log 2>&1 &
  run $OUT/eq_ideal/stack $JOBS --stacked --no-2d --delays $J 2d10_w100 3d10stack_w100 "${IDEAL[@]}" \
    > $OUT/eq_ideal.log 2>&1 &
  wait
  VPRW=$LZ/hardblocks/vpr_timed.sh
}
mkdir -p $OUT/on
cd "$LZ"
for s in ${STEPS:-k162 k224 k272 k300 2d abl eq}; do
  echo "$(date '+%F %T') $s"
  case $s in k*) point $s;; 2d) twod;; abl) abl;; eq) eq;; *) echo "unknown step $s"; exit 1;; esac
done
echo "$(date '+%F %T') done"
