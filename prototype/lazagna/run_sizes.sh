#!/bin/bash
# Split CLBs with layer-local pins at 24 and 30 LUTs, against the 10-LUT 2D CLB, on the
# server's VPR. Sizes and crossbar delays come from cluster_size_model.py, scaled by
# what the 20-LUT layout measured over its estimate (CLB inputs 1.033, feedback 1.006);
# the crossing keeps the 20-LUT layout's 63 ps. Run in tmux after run_ceilings.sh.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
OUT=/tmp/$USER/ceil
cd $B
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300" --timeout 14400 --jobs 12 --slim --scales 1.0
        --crossings 73 --clb-crossing 63 --local-inputs)
for set in big small; do
  if [ $set = big ]; then SET=(--bench-dir $OUT/bench --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha --output $OUT/big)
  else SET=(--bench-dir $MCNC --output $OUT/small); fi
  run() { name=$1; shift; nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" "$@" > $OUT/${set}_$name.log 2>&1; cp $OUT/$set/results.csv $OUT/${set}_$name.csv; }
  run n24 --n3d 24 --w3d 104 --wire-spans 3 14 --crossbar-scale 1.140 1.140
  run n30 --n3d 30 --w3d 116 --wire-spans 3 12 --crossbar-scale 1.261 1.293
done
echo SIZES_DONE
