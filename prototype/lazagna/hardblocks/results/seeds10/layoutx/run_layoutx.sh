#!/bin/bash
# Split CLB with the in-CLB layer crossing set to the Innovus/Tempus layout values
# (pnr/direct_crossing_results.txt: tap 1.435-0.931 = 504 ps; driver+receiver 1.692-0.932 = 760 ps).
# Everything else as run_freeclb.sh / run_hb10.sh (columns, hard inputs both, relaxed 1.3x, 10 seeds,
# routing crossings and hard-block crossing unchanged). Routed clocks, then ideal clocks at the same widths.
MY=$SCRATCH
HERE=~/sharc-lab/vtr-3d-prototype/build/lazagna-vtr/prototype/lazagna
export VPR_REAL=$SCRATCH/vprbuild/vpr/vpr
J=$MY/delays_layoutx.json
HC=$(python3 -c "import json; print(json.load(open('$J'))['3d20own_w100']['clb_crossing'])")
run() {  # OUT FABRIC [extra]
  mkdir -p $1/split
  nice -n 10 python3 compare_2d_3d.py --vpr $HERE/hardblocks/vpr_timed.sh \
    "--vpr-args= --timing_report_detail detailed --timing_report_npaths 10" --timeout 14400 --slim \
    --seeds 1 2 3 4 5 6 7 8 9 10 --bench-dir ~/sharc-lab/koios_blifs --w2d 100 --w3d 100 \
    --hard-crossing-ps "$HC" --hard-blocks columns --relax-w 1.3 --hard-inputs both --no-2d --jobs 8 \
    --benches eltwise_layer spmv conv_layer attention_layer tpu_like.small.os robot_rl bwave_like.fixed.small \
    --n3d 20 --local-inputs --wire-spans 4 15 --own-layer-inputs --delays $J 2d10_w100 $2 \
    --output $1/split "${@:3}"
}
one() {  # PS
  R=$MY/x$1_route; I=$MY/x$1_ideal
  run $R 3d20own_w100_x$1 > $R.log 2>&1
  mkdir -p $R/stack; $MY/prep_ideal.sh $R $I
  run $I 3d20own_w100_x$1 --clock-modeling ideal > $I.log 2>&1
}
cd $HERE
date
one 504 &
one 760 &
wait
date
echo LAYOUTX_DONE
