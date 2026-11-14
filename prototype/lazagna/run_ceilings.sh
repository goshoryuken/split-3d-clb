#!/bin/bash
# Ceiling cases for the two-layer CLB, against the 10-FLE 2D CLB, on the server's VPR.
# Each case runs on the 7 bigger designs and the 16 small ones, 3 seeds. Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
OUT=/tmp/$USER/ceil
mkdir -p $OUT
cd $B
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300" --timeout 14400 --jobs 12 --slim --scales 1.0)
# 20-FLE split CLB with layer-local pins, as laid out with bond pads mid-core.
N20=(--n3d 20 --w3d 100 --local-inputs --wire-spans 4 15 --crossbar-scale 1.043 1.023)
for set in big small; do
  if [ $set = big ]; then SET=(--bench-dir $OUT/bench --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha --output $OUT/big)
  else SET=(--bench-dir $MCNC --output $OUT/small); fi
  run() { name=$1; shift; nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" "$@" > $OUT/${set}_$name.log 2>&1; cp $OUT/$set/results.csv $OUT/${set}_$name.csv; }
  run measured   "${N20[@]}" --crossings 73 --clb-crossing 63
  run free_clb   "${N20[@]}" --crossings 73 --clb-crossing 0
  run free_all   "${N20[@]}" --crossings 10 --clb-crossing 0
  run stacked    --stacked --scales 1.041 --w3d 100 --crossings 73
  run stacked10  --stacked --scales 1.041 --w3d 100 --crossings 10
  # Routing crossings at the cost measured for our own driver, bond pad and receiver.
  run measured45 "${N20[@]}" --crossings 45 --clb-crossing 63
  run stacked45  --stacked --scales 1.041 --w3d 100 --crossings 45
done
echo CEILINGS_DONE
