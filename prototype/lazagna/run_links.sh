#!/bin/bash
# Direct links between neighbouring CLBs (compare_2d_3d.py --links-3d/--links-2d, VPR's <direct>
# with layer_offset and placement_macro="false"). Each link costs an input mux and a crossing
# (151 ps); the 2D control gets the same links to its east and west neighbours at the same delay.
# Every run uses VPR's delta placement delay model, which routes sample connections and so sees
# the links, in its own folder since the cache ignores VPR options. 3 seeds, crossings 45 ps.
# Group W uses the built-in Wilton switch blocks; group C the custom ones with vertical links,
# which four layers need. Waits for the server's VPR rebuild. Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
OUT=/tmp/$USER/links
mkdir -p $OUT
until grep -q BUILD_RC ~/3d-clb/vprbuild.log 2>/dev/null; do sleep 60; done
grep -q "BUILD_RC=0" ~/3d-clb/vprbuild.log || { echo "STOP: VPR build failed"; exit 1; }
cd $B
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300 --place_delay_model delta" --timeout 21600 --jobs ${JOBS:-10}
        --slim --scales 1.0 --crossings 45 --seeds 1 2 3)
N20=(--n3d 20 --w3d 100 --local-inputs --wire-spans 4 15 --crossbar-scale 1.043 1.023 --clb-crossing 63)
STACK=(--stacked --scales 1.041 --w3d 100)
N2D12=(--n2d 12 --w2d 110 --wire-spans-2d 4 14 --crossbar-scale-2d 1.044 1.073)
CUSTOM=(--switchblocks custom --vertical dense)
for set in small big; do
  if [ $set = big ]; then SET=(--bench-dir /tmp/$USER/ceil/bench --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha)
  else SET=(--bench-dir $MCNC); fi
  run() { name=$1; group=$2; shift 2; nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" --output $OUT/${set}_$group "$@" \
          > $OUT/${set}_$name.log 2>&1; cp $OUT/${set}_$group/results.csv $OUT/${set}_$name.csv; }
  # Group W: 2D 10 and 12 with and without links, stacked with and without, the 2-layer split.
  run w_split        w "${N20[@]}"
  run w_stacked      w "${STACK[@]}"
  run w_stacked_link w "${STACK[@]}" --links-3d vertical
  run w_2d10_link    w "${STACK[@]}" --links-3d vertical --links-2d horizontal
  run w_2d12         w "${STACK[@]}" --links-3d vertical "${N2D12[@]}"
  run w_2d12_link    w "${STACK[@]}" --links-3d vertical "${N2D12[@]}" --links-2d horizontal
  # Group C: four layers of 20-LUT split CLB pairs, with and without links.
  run c_split4       c "${N20[@]}" "${CUSTOM[@]}" --layers 4
  run c_split4_link  c "${N20[@]}" "${CUSTOM[@]}" --layers 4 --links-3d vertical
  run c_2d10_link    c "${N20[@]}" "${CUSTOM[@]}" --layers 4 --links-3d vertical --links-2d horizontal
done
echo LINKS_DONE
