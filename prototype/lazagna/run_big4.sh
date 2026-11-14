#!/bin/bash
# A 40-LUT CLB over 4 layers (10 per layer) with a full layer-local crossbar per layer (40 pins
# and all 40 FLE outputs, 80-input muxes), sized by cluster_size_model.general(), against the
# 10-LUT 2D runs of run_sparse.sh, copied into its own folders (compare with run_sparse.sh's
# 12-LUT 2D rows). Custom switch
# blocks with vertical links, delta placement delay model, crossings 45 ps (63 ps per layer
# inside the CLB), 3 seeds. Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
OUT=/tmp/$USER/big4
for set in small big; do
  mkdir -p $OUT/$set
  for d in /tmp/$USER/sparse/$set/2d_n10_*; do [ -f $d/run.log ] && cp -r $d $OUT/$set/; done
done
cd $B
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300 --place_delay_model delta" --timeout 21600 --jobs ${JOBS:-12}
        --slim --scales 1.0 --crossings 45 --clb-crossing 63 --seeds 1 2 3 --switchblocks custom --vertical dense --local-inputs)
for set in small big; do
  if [ $set = big ]; then SET=(--bench-dir /tmp/$USER/ceil/bench --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha)
  else SET=(--bench-dir $MCNC); fi
  nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" --output $OUT/$set \
      --n3d 40 --span 4 --layers 4 --w3d 100 --wire-spans 4 14 --crossbar-scale 1.112 1.093 > $OUT/${set}_f40x4.log 2>&1
  cp $OUT/$set/results.csv $OUT/${set}_f40x4.csv
done
echo BIG4_DONE
