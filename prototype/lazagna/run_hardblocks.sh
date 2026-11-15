#!/bin/bash
# Hard-block placement study (HARDBLOCKS.md): Koios designs with RAM and DSP blocks on the 10-LUT
# 2D fabric, the 20-LUT split CLB (own-layer input pins) and LaZagna-style stacked 10-LUT CLBs,
# with the 3D fabrics' hard blocks in per-layer columns, stacked RAM-under-DSP, spanning both
# layers, or on a layer of their own (hardblocks.py). sky130 SPICE delays for the CLBs and
# routing (spice/delays_tt_all.json, as laid out); hard-block delays estimated (hardblocks.py).
# W tracks per layer (default 100, as the SPICE sweeps run_spice_delays.sh, run_stacked_spice.sh), or with
# RELAX=1.3 each run's minimum width times 1.3 (VTR's relaxed routing).
# Runs locally.
#
# Usage: BENCH=dir-of-koios-blifs [BENCHES="..."] [SEEDS="1 2"] [JOBS_SPLIT=4] [JOBS_STACK=3] [RELAX=1.3] [W=100]
#        run_hardblocks.sh OUT
# BLIFs come from hardblocks/synth_koios.sh. The split pass also runs the 2D fabric; the stacked pass
# runs only its 3D fabric. Per-placement results: OUT/{split,stack}/results_<placement>.csv; tables:
# hb_table.py OUT, critical paths: hb_paths.py OUT.
# HARD_INPUTS=both: the split fabric's hard-block inputs read both layers (CLB inputs stay own-layer).
# FABRICS="split" or "stack": run one 3D fabric only. NO2D=1: no 2D runs (copy them in from another
# OUT/split and rerun to get CSVs with 2D rows; finished runs are reused).
# CLOCK=ideal: VPR's ideal clocks instead of clocks routed on general routing (as every sweep so far).
# VPR: a binary built from this branch (vpr-cb-layers.patch applied, e.g. cmake -S ../ -B build
# -DPROTOTYPE_BUILD_VPR=ON && make -C build vpr); the stacked and layer placements need it.
# TIMED=1 wraps VPR in /usr/bin/time -l (wall time and peak memory at the end of each run.log).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:?output dir}
mkdir -p "$OUT/split" "$OUT/stack"
VPR=${VPR:-$HERE/../../build/vpr/vpr/vpr}   # the README build
[ -x "$VPR" ] || { echo "no VPR at $VPR: build it (README, Build) or set VPR"; exit 1; }
if [ -n "$TIMED" ]; then export VPR_REAL=$VPR; VPR=$HERE/hardblocks/vpr_timed.sh; fi
BENCH=${BENCH:?dir of koios blifs}
J=$HERE/spice/delays_tt_all.json
# Crossing inside a spanning hard block: the split CLB's laid-out crossing, in both 3D fabrics.
HC=$(python3 -c "import json; print(json.load(open('$J'))['3d20own_w100']['clb_crossing'])")
PLACEMENTS=${PLACEMENTS:-columns stacked span layer}
# Fixed tracks: up to 300 router iterations, as the SPICE sweeps. RELAX: VPR's default (50) for the
# minimum-width search and the relaxed route, as VTR's own flow.
ITER="--max_router_iterations 300"; [ -n "$RELAX" ] && ITER=""
# Detailed timing reports (each routing node and its layer) for hb_paths.py; reports only.
REPORT="--timing_report_detail detailed --timing_report_npaths 10"
COMMON=(--vpr "$VPR" "--vpr-args=$ITER $REPORT" --timeout ${TIMEOUT:-14400} --slim
        --seeds ${SEEDS:-1} --bench-dir "$BENCH" --w2d ${W:-100} --w3d ${W:-100} --hard-crossing-ps "$HC"
        --benches ${BENCHES:-eltwise_layer spmv conv_layer attention_layer tpu_like.small.os}
        --hard-blocks $PLACEMENTS)
[ -n "$RELAX" ] && COMMON+=(--relax-w "$RELAX")
[ -n "$CLOCK" ] && COMMON+=(--clock-modeling "$CLOCK")
[ -n "$HARD_INPUTS" ] && COMMON+=(--hard-inputs "$HARD_INPUTS")
N20=(--n3d 20 --local-inputs --wire-spans 4 15 --own-layer-inputs --delays $J 2d10_w100 3d20own_w100)
STACK=(--stacked --delays $J 2d10_w100 3d10stack_w100)
cd "$HERE"
# Both 3D fabrics at once; the 2D runs only in the split pass (hb_table.py reads them from there).
FABRICS=${FABRICS:-split stack}
SPLIT2D=(); [ -n "$NO2D" ] && SPLIT2D=(--no-2d)
[[ " $FABRICS " == *" split "* ]] && nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" --jobs ${JOBS_SPLIT:-4} "${N20[@]}" "${SPLIT2D[@]}" --output "$OUT/split" > "$OUT/split.log" 2>&1 &
[[ " $FABRICS " == *" stack "* ]] && nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" --jobs ${JOBS_STACK:-3} "${STACK[@]}" --no-2d --output "$OUT/stack" > "$OUT/stack.log" 2>&1 &
wait
echo HARDBLOCKS_DONE
