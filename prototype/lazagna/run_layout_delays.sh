#!/bin/bash
# VPR with the CLB layer crossing measured in layout (spice/layout_delays.py) instead of SPICE's:
# the 20-LUT split CLB with own-layer pins against the 10-LUT 2D CLB, ten seeds, low and high
# conversions of the layout crossing, routing crossings with driver and receiver. Same fabrics
# and options as run_spice_delays.sh OWN=1; reuses its 2D runs (PREV). J is the delay file
# layout_delays.py wrote; SETS picks small and/or big. Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
OUT=${OUT:-/tmp/$USER/layoutsweep}
PREV=${PREV:-/tmp/$USER/spicesweep_own}
J=${J:?set J to the delay file from spice/layout_delays.py}
cd $B
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300" --timeout 21600 --jobs ${JOBS:-10} --slim
        --seeds ${SEEDS:-1 2 3 4 5 6 7 8 9 10})
N20=(--n3d 20 --w3d 100 --local-inputs --wire-spans 4 15 --own-layer-inputs)
for set in ${SETS:-small big}; do
  if [ $set = big ]; then SET=(--bench-dir /tmp/$USER/ceil/bench --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha)
  else SET=(--bench-dir $MCNC); fi
  for v in low high; do
    mkdir -p $OUT/$v/$set
    for d in $PREV/$set/2d_n10_*; do [ -e $OUT/$v/$set/$(basename $d) ] || cp -r $d $OUT/$v/$set/; done
    nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" --output $OUT/$v/$set "${N20[@]}" \
      --delays $J 2d10_w100 3d20own_w100_layout_$v > $OUT/${set}_$v.log 2>&1
    cp $OUT/$v/$set/results.csv $OUT/${set}_$v.csv
  done
done
echo LAYOUT_SWEEP_DONE
