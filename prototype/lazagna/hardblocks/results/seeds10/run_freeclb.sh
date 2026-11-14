#!/bin/bash
# Packer ceiling: the split CLB with free in-CLB layer crossings (clb_crossing 0, routing crossings
# unchanged), same Koios sweep as run_hb10.sh (columns, hard inputs both, relaxed 1.3x, 10 seeds).
# Routed clocks into freeclb_route, then ideal-clock reruns at the same widths into freeclb_ideal.
S=$SCRATCH
HERE=~/sharc-lab/vtr-3d-prototype/prototype/lazagna
export VPR_REAL=$SCRATCH/vprbuild/vpr/vpr
J=$S/delays_freeclb.json
HC=$(python3 -c "import json; print(json.load(open('$J'))['3d20own_w100']['clb_crossing'])")
run() {  # OUT [extra]
  mkdir -p $1/split
  nice -n 10 python3 compare_2d_3d.py --vpr $HERE/hardblocks/vpr_timed.sh \
    "--vpr-args= --timing_report_detail detailed --timing_report_npaths 10" --timeout 14400 --slim \
    --seeds 1 2 3 4 5 6 7 8 9 10 --bench-dir ~/sharc-lab/koios_blifs --w2d 100 --w3d 100 \
    --hard-crossing-ps "$HC" --hard-blocks columns --relax-w 1.3 --hard-inputs both --no-2d --jobs 12 \
    --benches eltwise_layer spmv conv_layer attention_layer tpu_like.small.os robot_rl bwave_like.fixed.small \
    --n3d 20 --local-inputs --wire-spans 4 15 --own-layer-inputs --delays $J 2d10_w100 3d20own_w100_freeclb \
    --output $1/split "${@:2}"
}
cd $HERE
date; run $S/freeclb_route > $S/freeclb_route.log 2>&1; date
mkdir -p $S/freeclb_route/stack; $S/prep_ideal.sh $S/freeclb_route $S/freeclb_ideal
run $S/freeclb_ideal --clock-modeling ideal > $S/freeclb_ideal.log 2>&1; date
echo FREECLB_DONE
