#!/bin/bash
# Does the split CLB's gain grow with layers? At 7 nm (ASAP7 SPICE delays), with the same custom
# switch blocks (vertical links between layers) and delta placement model in every fabric: the
# 10-LUT 2D CLB, the 20-LUT split CLB on 2 layers, the 40-LUT split CLB over 4 layers (10 per
# layer, own-layer pins), and stacked 10-LUT CLBs on 4 layers (LaZagna-style), crossings as laid
# out (driver, bond, receiver) and direct (the bond as a via).
# Mux sizes come from VPR's routing graph (spice/rr_mux_sizes.py, checked against the RTL where
# LaZagna can generate it); tiles from cluster_size_model.py; all estimated. Every bond interface
# is the 1 um hybrid bond, although a real 4-layer stack needs at least one face-to-back (TSV)
# interface: the 4-layer crossings are optimistic, the direct ones most.
# Shared server: few jobs at low priority. Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
BIG=${BIG:-$HOME/3d-clb/bench_big}
OUT=${OUT:-/tmp/$USER/layers7nm}
M=${M:-$HOME/3d-clb/asap7_models}
mkdir -p $OUT
cd $B
J=$OUT/spice/delays_tt.json
if [ ! -s $J ]; then
  # No outer nice: make_spice.py runs Spectre under tcsh's nice +10, which fails at nice 19.
  python3 spice/make_spice.py --models $M --env ~/3d-clb/pnr_fast/clb_2d --out $OUT/spice \
    --fabric 2d10c_w100_7nm 3d20ownc_w100_7nm 3d40own_w100_7nm 3d10stack4_w100_7nm > $OUT/spice.log 2>&1 || exit 1
fi
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300 --place_delay_model delta" --timeout 21600
        --jobs ${JOBS:-4} --slim --seeds ${SEEDS:-1 2 3} --switchblocks custom --vertical dense --w3d 100)
SPLIT=(--local-inputs --own-layer-inputs)
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
  run split2         ""     ""         "${SPLIT[@]}" --n3d 20 --wire-spans 4 15 --delays $J 2d10c_w100_7nm 3d20ownc_w100_7nm
  run split2_direct  split2 "2d_n10_*" "${SPLIT[@]}" --n3d 20 --wire-spans 4 15 --delays $J 2d10c_w100_7nm 3d20ownc_w100_7nm_direct
  run split4         split2 "2d_n10_*" "${SPLIT[@]}" --n3d 40 --span 4 --layers 4 --wire-spans 4 14 --delays $J 2d10c_w100_7nm 3d40own_w100_7nm
  run split4_direct  split2 "2d_n10_*" "${SPLIT[@]}" --n3d 40 --span 4 --layers 4 --wire-spans 4 14 --delays $J 2d10c_w100_7nm 3d40own_w100_7nm_direct
  run stack4         split2 "2d_n10_*" --stacked --layers 4 --delays $J 2d10c_w100_7nm 3d10stack4_w100_7nm
  run stack4_direct  split2 "2d_n10_*" --stacked --layers 4 --delays $J 2d10c_w100_7nm 3d10stack4_w100_7nm_direct
done
echo LAYERS7NM_DONE
