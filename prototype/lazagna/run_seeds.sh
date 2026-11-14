#!/bin/bash
# Ten seeds of the main comparison, on the server's VPR: 2D CLBs of 8, 10 and 12 LUTs, the
# 20-LUT split CLB with layer-local pins as laid out, and stacked 10-LUT CLBs, all with
# 45 ps crossings. Seeds 1-3 are reused from run_ceilings.sh and run_baselines.sh when the
# architecture is unchanged. SPAN4 and SPAN16 are the split tile's wire spans (default from
# the estimated tile; set them from the measured tile). With RELAX=1.3 every run instead
# finds its fewest tracks and routes with 1.3 times as many, into its own folder.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
OUT=${OUT:-/tmp/$USER/ceil}
SEEDS=${SEEDS:-1 2 3 4 5 6 7 8 9 10}
SPAN4=${SPAN4:-4}
SPAN16=${SPAN16:-15}
TAG=${TAG:-seeds}
EXTRA=()
[ -n "$RELAX" ] && EXTRA=(--relax-w $RELAX)
cd $B
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300" --timeout 21600 --jobs ${JOBS:-12} --slim --scales 1.0
        --crossings 45 --seeds $SEEDS "${EXTRA[@]}")
N20=(--n3d 20 --w3d 100 --local-inputs --wire-spans $SPAN4 $SPAN16 --crossbar-scale 1.043 1.023 --clb-crossing 63)
for set in small big; do
  if [ $set = big ]; then SET=(--bench-dir /tmp/$USER/ceil/bench --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha --output $OUT/big)
  else SET=(--bench-dir $MCNC --output $OUT/small); fi
  run() { name=$1; shift; nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" "$@" > $OUT/${set}_${TAG}_$name.log 2>&1; cp $OUT/$set/results.csv $OUT/${set}_${TAG}_$name.csv; }
  run split   "${N20[@]}"
  run stacked --stacked --scales 1.041 --w3d 100
  run n2d8    "${N20[@]}" --n2d 8  --w2d 90  --wire-spans-2d 5 18 --crossbar-scale-2d 0.908 0.887
  run n2d12   "${N20[@]}" --n2d 12 --w2d 110 --wire-spans-2d 4 14 --crossbar-scale-2d 1.044 1.073
done
echo SEEDS_DONE
