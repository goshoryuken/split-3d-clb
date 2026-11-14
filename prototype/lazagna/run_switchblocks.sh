#!/bin/bash
# Switch blocks whose wires can turn onto the layer above or below, and four layers, on the
# server's VPR. Both fabrics use the custom planar switch blocks in switchblocks.xml, so the
# 2D baseline differs from the built-in Wilton runs. Crossings cost the 45 ps our bond measured.
# Dense vertical links are optimistic: their area is not in the tile model. Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
OUT=/tmp/$USER/ceil_sb
mkdir -p $OUT
cd $B
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300" --timeout 21600 --jobs 8 --slim --scales 1.0
        --crossings 45 --switchblocks custom)
N20=(--n3d 20 --w3d 100 --local-inputs --wire-spans 4 15 --crossbar-scale 1.043 1.023 --clb-crossing 63)
STACK=(--stacked --scales 1.041 --w3d 100)
for set in small big; do
  if [ $set = big ]; then SET=(--bench-dir /tmp/$USER/ceil/bench --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha --output $OUT/big)
  else SET=(--bench-dir $MCNC --output $OUT/small); fi
  run() { name=$1; shift; nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" "$@" > $OUT/${set}_$name.log 2>&1; cp $OUT/$set/results.csv $OUT/${set}_$name.csv; }
  run split_planar  "${N20[@]}"
  run split_dense   "${N20[@]}" --vertical dense
  run split_sparse  "${N20[@]}" --vertical sparse
  run stacked_dense "${STACK[@]}" --vertical dense
  run split4_dense  "${N20[@]}" --vertical dense --layers 4
  run stacked4_dense "${STACK[@]}" --vertical dense --layers 4
done
echo SB_DONE
