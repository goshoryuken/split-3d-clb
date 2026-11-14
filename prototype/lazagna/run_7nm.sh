#!/bin/bash
# The main comparisons with 7 nm (ASAP7) transistor-level delays: the 20-LUT split CLB with
# own-layer pins and stacked 10-LUT CLBs against the 10- and 12-LUT 2D CLBs, crossings as laid
# out (driver, bond, receiver) and direct (the bond as a via). Same fabrics, tracks, wire spans
# and seeds as the sky130 runs (run_spice_delays.sh OWN=1, run_stacked_spice.sh).
# First runs Spectre for the 7 nm fabrics (spice/make_spice.py, *_7nm) with the ASAP7 models in M
# (7nm_TT_160803.pm). Passes share 2D and 3D runs by copying. Shared server: few jobs at low
# priority. Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
BIG=${BIG:-/tmp/$USER/ceil/bench}
OUT=${OUT:-/tmp/$USER/sweep7nm}
M=${M:-$HOME/3d-clb/asap7_models}
mkdir -p $OUT
cd $B
J=$OUT/spice/delays_tt.json
if [ ! -s $J ]; then
  # No outer nice: make_spice.py runs Spectre under tcsh's nice +10, which fails at nice 19.
  python3 spice/make_spice.py --models $M --env ~/3d-clb/pnr_fast/clb_2d --out $OUT/spice \
    --fabric 2d10_w100_7nm 2d12_w110_7nm 3d20own_w100_7nm 3d10stack_w100_7nm > $OUT/spice.log 2>&1 || exit 1
fi
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300" --timeout 21600 --jobs ${JOBS:-8} --slim
        --seeds ${SEEDS:-1 2 3 4 5 6 7 8 9 10})
N20=(--n3d 20 --w3d 100 --local-inputs --wire-spans 4 15 --own-layer-inputs)
N2D12=(--n2d 12 --w2d 110 --wire-spans-2d 4 14)
for set in ${SETS:-small big}; do
  if [ $set = big ]; then
    [ -e $BIG/sha.blif ] || { echo "no big benchmarks in $BIG"; exit 1; }
    SET=(--bench-dir $BIG --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha)
  else SET=(--bench-dir $MCNC); fi
  # run NAME REUSE_FROM PATTERN ARGS...: copies matching earlier runs into this pass's folder.
  run() {
    name=$1 from=$2 pattern=$3; shift 3
    mkdir -p $OUT/$name/$set
    for d in ${from:+$OUT/$from/$set/$pattern}; do
      [ -e "$d" ] && [ ! -e $OUT/$name/$set/$(basename $d) ] && cp -r $d $OUT/$name/$set/
    done
    nice -n 19 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" --output $OUT/$name/$set "$@" \
      > $OUT/${set}_$name.log 2>&1
    cp $OUT/$name/$set/results.csv $OUT/${set}_$name.csv
  }
  run split          ""    ""        "${N20[@]}" --delays $J 2d10_w100_7nm 3d20own_w100_7nm
  run split_direct   split "2d_n10_*" "${N20[@]}" --delays $J 2d10_w100_7nm 3d20own_w100_7nm_direct
  run n2d12          split "3d_*"     "${N20[@]}" "${N2D12[@]}" --delays $J 2d12_w110_7nm 3d20own_w100_7nm
  run stacked        split "2d_n10_*" --stacked --w3d 100 --delays $J 2d10_w100_7nm 3d10stack_w100_7nm
  run stacked_direct split "2d_n10_*" --stacked --w3d 100 --delays $J 2d10_w100_7nm 3d10stack_w100_7nm_direct
done
echo SWEEP_7NM_DONE
