#!/bin/bash
# Strict ablation for split vs stacked: the split 20-LUT CLB (10 + 10, per-layer crossbars, in-CLB
# crossing 339 ps) on the stacked fabric's exact routing: input pins reach both layers' tracks
# (LaZagna's 3D connection block, no --own-layer-inputs), L16 spans 16 tiles (no --wire-spans 4 15),
# and the stacked SPICE set's routing delays (l4, l16, cb, route_crossing from 3d10stack_w100).
# Everything else as run_hb10.sh (columns, hard inputs both, relaxed 1.3x, 10 seeds).
# Routed clocks, then ideal clocks at the same widths.
MY=$SCRATCH
HERE=~/sharc-lab/vtr-3d-prototype/build/lazagna-vtr/prototype/lazagna
export VPR_REAL=$SCRATCH/vprbuild/vpr/vpr
J=$MY/delays_ablation.json
HC=$(python3 -c "import json; print(json.load(open('$J'))['3d20own_w100']['clb_crossing'])")
run() {  # OUT [extra]
  mkdir -p $1/split
  nice -n 10 python3 compare_2d_3d.py --vpr $HERE/hardblocks/vpr_timed.sh \
    "--vpr-args= --timing_report_detail detailed --timing_report_npaths 10" --timeout 14400 --slim \
    --seeds 1 2 3 4 5 6 7 8 9 10 --bench-dir ~/sharc-lab/koios_blifs --w2d 100 --w3d 100 \
    --hard-crossing-ps "$HC" --hard-blocks columns --relax-w 1.3 --hard-inputs both --no-2d --jobs 12 \
    --benches eltwise_layer spmv conv_layer attention_layer tpu_like.small.os robot_rl bwave_like.fixed.small \
    --n3d 20 --local-inputs --delays $J 2d10_w100 3d20_stackroute \
    --output $1/split "${@:2}"
}
cd $HERE
date
R=$MY/abl_route; I=$MY/abl_ideal
run $R > $R.log 2>&1
mkdir -p $R/stack; $MY/prep_ideal.sh $R $I
run $I --clock-modeling ideal > $I.log 2>&1
date
echo ABLATION_DONE
