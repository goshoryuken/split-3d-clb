#!/bin/bash
# Decision 1: the 20-LUT split CLB with input pins reaching only their own layer's tracks, so its
# connection blocks select from one layer instead of two (about half the size; outputs still reach
# both layers). Tile per layer about 1.06 of 2D instead of 1.16 (CLB 270,400 + switch block 47,435
# + connection blocks about 34,500 um2), width 1.03, spans 4 and 16. Ten seeds, crossings 45 ps,
# against the 10-LUT 2D runs it reuses; compare with run_seeds.sh's 12-LUT 2D rows. Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
OUT=/tmp/$USER/ceil
cd $B
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300" --timeout 21600 --jobs ${JOBS:-12} --slim --scales 1.0
        --crossings 45 --seeds 1 2 3 4 5 6 7 8 9 10
        --n3d 20 --w3d 100 --local-inputs --wire-spans 4 16 --crossbar-scale 1.043 1.023 --clb-crossing 63 --own-layer-inputs)
for set in small big; do
  if [ $set = big ]; then SET=(--bench-dir $OUT/bench --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha --output $OUT/big)
  else SET=(--bench-dir $MCNC --output $OUT/small); fi
  nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" > $OUT/${set}_ownlayer.log 2>&1
  cp $OUT/$set/results.csv $OUT/${set}_ownlayer.csv
done
echo OWNLAYER_DONE
