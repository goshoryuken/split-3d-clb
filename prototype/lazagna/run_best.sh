#!/bin/bash
# The 20-LUT split CLB with every lever that helped, against the best 2D CLB (12 LUTs) given the
# same east/west direct links. Delta placement delay model, 151 ps links, crossings 45 ps (63 ps
# per layer inside the CLB), and an optimistic 10 ps bonding variant. Also ten seeds of the plain
# fair link comparison (built-in switch blocks), reusing run_links2.sh's seeds 1-3. Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
cd $B
BASE=(--vpr $V "--vpr-args=--max_router_iterations 300 --place_delay_model delta" --timeout 21600 --jobs ${JOBS:-12} --slim --scales 1.0)
N20=(--n3d 20 --w3d 100 --local-inputs --wire-spans 4 15 --crossbar-scale 1.043 1.023)
N2D12=(--n2d 12 --w2d 110 --wire-spans-2d 4 14 --crossbar-scale-2d 1.044 1.073)
LINKS=(--links-3d horizontal --links-2d horizontal)
for set in small big; do
  if [ $set = big ]; then SET=(--bench-dir /tmp/$USER/ceil/bench --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha)
  else SET=(--bench-dir $MCNC); fi
  run() { out=$1; name=$2; shift 2; nice -n 10 python3 compare_2d_3d.py "${BASE[@]}" "${SET[@]}" --output $out/$set "$@" \
          > $out/${set}_$name.log 2>&1; cp $out/$set/results.csv $out/${set}_$name.csv; }
  # Ten seeds of split + links vs 2D 12 + links, in run_links.sh's folders (seeds 1-3 reused).
  mkdir -p /tmp/$USER/links
  run /tmp/$USER/links w10_split_hlink "${N20[@]}" "${N2D12[@]}" "${LINKS[@]}" --crossings 45 --clb-crossing 63 --seeds 1 2 3 4 5 6 7 8 9 10
  mv /tmp/$USER/links/$set/results.csv /tmp/$USER/links/$set/results_w10.csv 2>/dev/null
  # Every lever: links, switch blocks with vertical links, measured and optimistic bonding.
  mkdir -p /tmp/$USER/best
  run /tmp/$USER/best all45 "${N20[@]}" "${N2D12[@]}" "${LINKS[@]}" --switchblocks custom --vertical dense --crossings 45 --clb-crossing 63 --seeds 1 2 3
  run /tmp/$USER/best all10 "${N20[@]}" "${N2D12[@]}" "${LINKS[@]}" --switchblocks custom --vertical dense --crossings 10 --clb-crossing 10 --seeds 1 2 3
done
echo BEST_DONE
