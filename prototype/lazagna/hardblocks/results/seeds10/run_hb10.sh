#!/bin/bash
# 7 Koios designs x 10 seeds, 2D / split (hard inputs both) / stacked,
# per-layer columns only. Routed clocks (width search + 1.3x relaxed), then ideal-clock reruns at
# the same widths. Pilot seeds 1-4 copied in and reused.
S=$SCRATCH
HERE=~/sharc-lab/vtr-3d-prototype/prototype/lazagna
export VPR=$SCRATCH/vprbuild/vpr/vpr
export BENCH=~/sharc-lab/koios_blifs RELAX=1.3 TIMED=1 HARD_INPUTS=both PLACEMENTS=columns
export SEEDS="1 2 3 4 5 6 7 8 9 10" JOBS_SPLIT=8 JOBS_STACK=4
export BENCHES="eltwise_layer spmv conv_layer attention_layer tpu_like.small.os robot_rl bwave_like.fixed.small"
date; $HERE/run_hardblocks.sh $S/hb10_route; date
$S/prep_ideal.sh $S/hb10_route $S/hb10_ideal
CLOCK=ideal $HERE/run_hardblocks.sh $S/hb10_ideal; date
echo HB10_DONE
