#!/bin/bash
# The split fabric with the timing-aware layer pass (compare_2d_3d.py --layer-pass: VPR packs and
# writes its connection criticalities, layer_pass.py moves FLEs between the CLB's two layers, VPR
# places and routes the rewritten netlist). Three points of the crossing range, each exactly as the
# pass-off run it is compared with; only --layer-pass is added:
#   k100     SPICE crossings (339 ps in-CLB), the headline (run_hb10.sh / run_hardblocks.sh)
#   k162     every crossing 1.62x (549 ps in-CLB, crossings/run_crossings.sh)
#   k162pin  1.62x plus the budgeted layout's input-pin cost (+79 ps on xbar_pin, crossings/run_pinpath.sh)
# Every run routes at the track count of its pass-off twin (same design and seed, routed-clock CSV;
# --widths), so the pass changes nothing but which layer each FLE sits on. Ideal clocks use the same
# widths, as prep_ideal.sh did. Stacked has one CLB per layer, so the pass cannot apply; its results
# are the committed ones. Table: layerpass_table.py OUT.
# SETS picks the points (default "k100 k162 k162pin"); k224, k272 and k300 (every crossing 2.24x,
# 2.72x and 3.0x; 2.72x puts the routing crossing at LaZagna's default; crossings/run_crossings.sh)
# run the same way, each at the track count of crossings/k<NNN>_route/split.
# CONTROL=1 runs only the control at point CK (default k162) instead (layer_pass.py --control: every
# FLE stays on its layer and gets a random slot within it), into control_<CK>_{route,ideal}: the same
# kind of change to VPR's input with no crossing removed, to see how much any rewrite moves the
# results by itself.
# Usage: layerpass/run_layerpass.sh OUT
# Env: VPR (default: this branch's build/vpr/vpr/vpr), JOBS (per set, default 2), SETS, CONTROL=1, CK.
HERE=$(cd "$(dirname "$0")" && pwd)
S10=$(cd "$HERE/.." && pwd)
LZ=$(cd "$HERE/../../../.." && pwd)
OUT=$(mkdir -p "${1:?usage: run_layerpass.sh OUT}" && cd "$1" && pwd)
VPR=${VPR:-$LZ/../../build/vpr/vpr/vpr}
J=$S10/crossings/delays_crossings.json
run() {  # OUT SET WIDTHS ARGS...
  out=$1; set=$2; widths=$3; shift 3; mkdir -p "$out"
  python3 compare_2d_3d.py --vpr "$VPR" \
    "--vpr-args= --timing_report_detail detailed --timing_report_npaths 10" --timeout 14400 --slim \
    --seeds 1 2 3 4 5 6 7 8 9 10 --bench-dir "$LZ/hardblocks/koios" --w2d 100 --w3d 100 \
    --hard-crossing-ps 339.23 --hard-blocks columns --relax-w 1.3 --hard-inputs both --no-2d \
    --jobs ${JOBS:-2} \
    --benches eltwise_layer spmv conv_layer attention_layer tpu_like.small.os robot_rl bwave_like.fixed.small \
    --output "$out" --n3d 20 --local-inputs --wire-spans 4 15 --own-layer-inputs \
    --delays "$J" 2d10_w100 "$set" --layer-pass --widths "$widths" "$@"
}
delays() { case $1 in k100) echo 3d20own_w100;; *) echo 3d20own_w100_$1;; esac; }
widths() { case $1 in k100) echo $S10/route/split/results_columns.csv;; *) echo $S10/crossings/$1_route/split/results.csv;; esac; }
cd "$LZ"
if [ -n "$CONTROL" ]; then
  CK=${CK:-k162}
  for c in route ideal; do
    [ $c = ideal ] && CM=(--clock-modeling ideal) || CM=()
    run $OUT/control_${CK}_$c/split $(delays $CK) $(widths $CK) "${CM[@]}" \
      --layer-pass-args=--control > $OUT/control_${CK}_$c.log 2>&1 &
  done
  wait
  python3 "$HERE/layerpass_table.py" "$OUT"
  exit
fi
for c in route ideal; do
  [ $c = ideal ] && CM=(--clock-modeling ideal) || CM=()
  for s in ${SETS:-k100 k162 k162pin}; do
    run $OUT/${s}_$c/split $(delays $s) $(widths $s) "${CM[@]}" > $OUT/${s}_$c.log 2>&1 &
  done
done
wait
python3 "$HERE/layerpass_table.py" "$OUT"
