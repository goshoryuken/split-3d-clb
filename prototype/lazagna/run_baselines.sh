#!/bin/bash
# Is 10 LUTs the best 2D CLB? 2D CLBs of 8 and 12 LUTs (sizes and crossbar delays from
# cluster_size_model.py) against the same 20-LUT split CLB runs as run_ceilings.sh
# (crossings 45 ps), which this reuses. Compare each 2D size's results with the 10-LUT 2D
# rows of compare_results_ceil_*_measured45.csv. Run in tmux on the server.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
OUT=/tmp/$USER/ceil
cd $B
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300" --timeout 14400 --jobs 8 --slim --scales 1.0
        --crossings 45 --clb-crossing 63 --n3d 20 --w3d 100 --local-inputs --wire-spans 4 15 --crossbar-scale 1.043 1.023)
for set in big small; do
  if [ $set = big ]; then SET=(--bench-dir $OUT/bench --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha --output $OUT/big)
  else SET=(--bench-dir $MCNC --output $OUT/small); fi
  run() { name=$1; shift; nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" "$@" > $OUT/${set}_$name.log 2>&1; cp $OUT/$set/results.csv $OUT/${set}_$name.csv; }
  run n2d8  --n2d 8  --w2d 90  --wire-spans-2d 5 18 --crossbar-scale-2d 0.908 0.887
  run n2d12 --n2d 12 --w2d 110 --wire-spans-2d 4 14 --crossbar-scale-2d 1.044 1.073
done
echo BASELINES_DONE
