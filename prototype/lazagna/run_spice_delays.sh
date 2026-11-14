#!/bin/bash
# The main comparison with transistor-level sky130 delays (spice/make_spice.py) instead of the
# 40 nm template's: the 20-LUT split CLB with layer-local pins against the 10- and 12-LUT 2D CLBs,
# with crossings as laid out (driver, bond, receiver) and direct (the bond as a via). Same fabrics,
# tracks and wire spans as run_seeds.sh; VPR's default placement delay model, as there. 3 seeds.
# DELAYS is the delay file (default the typical corner); OWN=1 gives the split CLB input pins that
# reach only their own layer's tracks (fabric 3d20own_w100); SETS picks small and/or big. Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
OUT=${OUT:-/tmp/$USER/spicesweep}
J=${DELAYS:-/tmp/$USER/spice/run3/delays_tt.json}
mkdir -p $OUT
cd $B
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300" --timeout 21600 --jobs ${JOBS:-10} --slim
        --seeds ${SEEDS:-1 2 3})
N20=(--n3d 20 --w3d 100 --local-inputs --wire-spans 4 15)
F3D=3d20_w100
[ -n "$OWN" ] && { N20+=(--own-layer-inputs); F3D=3d20own_w100; }
N2D12=(--n2d 12 --w2d 110 --wire-spans-2d 4 14)
for set in ${SETS:-small big}; do
  if [ $set = big ]; then SET=(--bench-dir /tmp/$USER/ceil/bench --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha --output $OUT/$set)
  else SET=(--bench-dir $MCNC --output $OUT/$set); fi
  run() { name=$1; shift; nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" "$@" > $OUT/${set}_$name.log 2>&1; cp $OUT/$set/results.csv $OUT/${set}_$name.csv; }
  run n2d10        "${N20[@]}" --delays $J 2d10_w100 $F3D
  run n2d12        "${N20[@]}" "${N2D12[@]}" --delays $J 2d12_w110 $F3D
  run n2d10_direct "${N20[@]}" --delays $J 2d10_w100 ${F3D}_direct
  run n2d12_direct "${N20[@]}" "${N2D12[@]}" --delays $J 2d12_w110 ${F3D}_direct
done
echo SPICE_SWEEP_DONE
