#!/bin/bash
# The split fabric at 1.62x (every crossing; in-CLB 549 ps, the timing-budgeted layout pnr_local20u)
# plus the cost that layout put on CLB input-pin paths, 1.363 vs 1.284 ns
# (pnr/crossing_stages_results.txt), added in full as +79 ps on xbar_pin (269.82 -> 348.82 ps, delay
# set 3d20own_w100_k162pin). That is the harshest reading: the layout's pin paths got 6% slower, the
# model's 29%. Stacked is unchanged, so k162_{route,ideal}/stack is reused. Results go to
# k162pin_{route,ideal}/split; the table: crossings_table.py on OUT (it prints the row as k = 1.62).
# Usage: crossings/run_pinpath.sh OUT     Env: VPR (default build/vpr/vpr/vpr), JOBS (default 12).
HERE=$(cd "$(dirname "$0")" && pwd)
LZ=$(cd "$HERE/../../../.." && pwd)
OUT=$(mkdir -p "${1:?usage: run_pinpath.sh OUT}" && cd "$1" && pwd)
VPR=${VPR:-$LZ/../../build/vpr/vpr/vpr}
J=$HERE/delays_crossings.json
run() {  # OUT ARGS...
  out=$1; shift; mkdir -p "$out"
  python3 compare_2d_3d.py --vpr "$VPR" \
    "--vpr-args= --timing_report_detail detailed --timing_report_npaths 10" --timeout 14400 --slim \
    --seeds 1 2 3 4 5 6 7 8 9 10 --bench-dir "$LZ/hardblocks/koios" --w2d 100 --w3d 100 \
    --hard-crossing-ps 339.23 --hard-blocks columns --relax-w 1.3 --hard-inputs both --no-2d \
    --jobs ${JOBS:-12} \
    --benches eltwise_layer spmv conv_layer attention_layer tpu_like.small.os robot_rl bwave_like.fixed.small \
    --output "$out" --n3d 20 --local-inputs --wire-spans 4 15 --own-layer-inputs \
    --delays "$J" 2d10_w100 3d20own_w100_k162pin "$@"
}
cd "$LZ"
R=$OUT/k162_route; I=$OUT/k162_ideal
mkdir -p $R/stack $I
run $R/split > $R.split.log 2>&1
"$LZ/hardblocks/prep_ideal.sh" $R $I > /dev/null
run $I/split --clock-modeling ideal > $I.split.log 2>&1
for c in route ideal; do
  mkdir -p $OUT/k162_$c/stack; cp $HERE/k162_$c/stack/results*.csv $OUT/k162_$c/stack/
done
python3 "$HERE/crossings_table.py" "$OUT"
