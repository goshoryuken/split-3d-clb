#!/bin/bash
# How the 20-LUT split CLB's advantage changes when routing costs more relative to logic, as in
# newer processes where wires dominate: routing switches, connection blocks and crossings in both
# fabrics are scaled by K (1 is run_seeds.sh / run_ceilings.sh). Against 2D CLBs of 10 and 12 LUTs,
# 3 seeds, server VPR. Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
cd $B
N20=(--n3d 20 --w3d 100 --local-inputs --wire-spans 4 15 --crossbar-scale 1.043 1.023 --clb-crossing 63)
for K in ${KS:-1.5 2 3}; do
  OUT=/tmp/$USER/proc_k$K
  mkdir -p $OUT
  COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300" --timeout 21600 --jobs ${JOBS:-8} --slim --scales 1.0
          --crossings 45 --seeds 1 2 3 --routing-scale $K)
  for set in small big; do
    if [ $set = big ]; then SET=(--bench-dir /tmp/$USER/ceil/bench --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha --output $OUT/big)
    else SET=(--bench-dir $MCNC --output $OUT/small); fi
    run() { name=$1; shift; nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" "$@" > $OUT/${set}_$name.log 2>&1; cp $OUT/$set/results.csv $OUT/${set}_$name.csv; }
    run split "${N20[@]}"
    run n2d12 "${N20[@]}" --n2d 12 --w2d 110 --wire-spans-2d 4 14 --crossbar-scale-2d 1.044 1.073
  done
done
echo PROCESS_DONE
