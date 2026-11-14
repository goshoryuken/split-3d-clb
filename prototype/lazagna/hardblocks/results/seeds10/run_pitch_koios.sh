#!/bin/bash
# sky130 bond pitch on Koios: split (hard inputs both) and stacked CLBs at 1 and 10 um bond pitch
# (make_spice.py --pitch sets), same sweep as run_hb10.sh (columns, relaxed 1.3x, 10 seeds); the
# 5 um point and the 2D runs are hb10. Routed clocks into pk_route, then ideal-clock reruns at the
# same widths into pk_ideal.
S=$SCRATCH
HERE=~/sharc-lab/vtr-3d-prototype/prototype/lazagna
export VPR_REAL=$SCRATCH/vprbuild/vpr/vpr
J=$S/delays_pitch_sky130.json
HC=$(python3 -c "import json; print(json.load(open('$J'))['3d20own_w100']['clb_crossing'])")
run() {  # OUT FAB(split|stack) PITCH [extra]
  if [ $2 = split ]; then F=(--n3d 20 --local-inputs --wire-spans 4 15 --own-layer-inputs --delays $J 2d10_w100 3d20own_w100_p$3)
  else F=(--stacked --delays $J 2d10_w100 3d10stack_w100_p$3); fi
  mkdir -p $1/$2
  nice -n 10 python3 compare_2d_3d.py --vpr $HERE/hardblocks/vpr_timed.sh \
    "--vpr-args= --timing_report_detail detailed --timing_report_npaths 10" --timeout 14400 --slim \
    --seeds 1 2 3 4 5 6 7 8 9 10 --bench-dir ~/sharc-lab/koios_blifs --w2d 100 --w3d 100 \
    --hard-crossing-ps "$HC" --hard-blocks columns --relax-w 1.3 --hard-inputs both --no-2d --jobs 6 \
    --benches eltwise_layer spmv conv_layer attention_layer tpu_like.small.os robot_rl bwave_like.fixed.small \
    "${F[@]}" --output $1/$2 "${@:4}" > $1/$2_p$3.log 2>&1
  cp $1/$2/results.csv $1/$2_p$3.csv
}
cd $HERE
date
for p in 1 10; do run $S/pk_route split $p & run $S/pk_route stack $p & wait; date; done
$S/prep_ideal.sh $S/pk_route $S/pk_ideal
for p in 1 10; do run $S/pk_ideal split $p --clock-modeling ideal & run $S/pk_ideal stack $p --clock-modeling ideal & wait; date; done
echo PITCH_KOIOS_DONE
