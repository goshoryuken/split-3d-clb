#!/bin/bash
# Equal tracks: LaZagna-style stacked CLBs routed at the split fabric's relaxed track count for the
# same design and seed (split_widths.tsv, from ../route/split/results_columns.csv), with routed and
# ideal clocks. Everything else as the stacked pass of run_hb10.sh (columns, hard inputs both,
# 10 seeds). Usage: VPR_REAL=path/to/vpr run_equal_tracks.sh OUT
HERE=$(cd "$(dirname "$0")" && pwd)
LZ=$(cd "$HERE/../../../.." && pwd)
OUT=$(mkdir -p "${1:?output dir}" && cd "$1" && pwd)
export VPR_REAL=${VPR_REAL:-$LZ/../../build/vpr/vpr/vpr}
J=$LZ/spice/delays_tt_all.json
HC=$(python3 -c "import json; print(json.load(open('$J'))['3d20own_w100']['clb_crossing'])")
run() {  # OUT [extra]
  mkdir -p "$1/stack"
  python3 compare_2d_3d.py --vpr "$HERE/vpr_eq.sh" \
    "--vpr-args= --timing_report_detail detailed --timing_report_npaths 10" --timeout 14400 --slim \
    --seeds ${SEEDS:-1 2 3 4 5 6 7 8 9 10} --bench-dir "$LZ/hardblocks/koios" --w2d 100 --w3d 100 \
    --hard-crossing-ps "$HC" --hard-blocks columns --relax-w 1.3 --hard-inputs both --no-2d --jobs ${JOBS:-8} \
    --benches ${BENCHES:-eltwise_layer spmv conv_layer attention_layer tpu_like.small.os robot_rl bwave_like.fixed.small} \
    --stacked --delays "$J" 2d10_w100 3d10stack_w100 --output "$1/stack" "${@:2}"
}
cd "$LZ"
run "$OUT/eq_route" > "$OUT/eq_route.log" 2>&1 &
run "$OUT/eq_ideal" --clock-modeling ideal > "$OUT/eq_ideal.log" 2>&1 &
wait
