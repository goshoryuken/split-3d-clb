#!/bin/bash
# Follow-up to run_links.sh: the same east/west links for the 20-LUT split CLB as for the 12-LUT
# 2D CLB (one link per CLB output each way), at the vertical-link price (151 ps, which flatters a
# link that crosses a tile) and at 196 ps for both (input mux plus a driver and one tile of wire).
# Also the 2-layer split CLB with the custom switch blocks the 4-layer runs used. Same delta
# placement delay model, folders and 3 seeds as run_links.sh, whose runs this reuses. Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
OUT=/tmp/$USER/links
cd $B
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300 --place_delay_model delta" --timeout 21600 --jobs ${JOBS:-12}
        --slim --scales 1.0 --crossings 45 --seeds 1 2 3)
N20=(--n3d 20 --w3d 100 --local-inputs --wire-spans 4 15 --crossbar-scale 1.043 1.023 --clb-crossing 63)
N2D12=(--n2d 12 --w2d 110 --wire-spans-2d 4 14 --crossbar-scale-2d 1.044 1.073)
CUSTOM=(--switchblocks custom --vertical dense)
for set in small big; do
  if [ $set = big ]; then SET=(--bench-dir /tmp/$USER/ceil/bench --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha)
  else SET=(--bench-dir $MCNC); fi
  run() { name=$1; group=$2; shift 2; nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" --output $OUT/${set}_$group "$@" \
          > $OUT/${set}_$name.log 2>&1; cp $OUT/${set}_$group/results.csv $OUT/${set}_$name.csv; }
  run w_split_hlink    w  "${N20[@]}" "${N2D12[@]}" --links-3d horizontal --links-2d horizontal
  run w_split_hlink196 w196 "${N20[@]}" "${N2D12[@]}" --links-3d horizontal --links-2d horizontal --link-ps 196
  run c_split2         c  "${N20[@]}" "${CUSTOM[@]}"
done
echo LINKS2_DONE
