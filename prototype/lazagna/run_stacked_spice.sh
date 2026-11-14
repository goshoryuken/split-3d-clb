#!/bin/bash
# Split against stacked with transistor-level delays: stacked 10-LUT CLBs (stock LaZagna 3D,
# --stacked) against the 10-LUT 2D CLB, with routing crossings as laid out (driver, bond,
# receiver) and direct (the bond as a via). Ten seeds, so the results sit beside the split CLB's
# runs: run_spice_delays.sh OWN=1 SEEDS=1..10 and run_layout_delays.sh.
# First runs Spectre for the stacked fabric (spice/make_spice.py --fabric 3d10stack_w100) and
# merges its two sets into J (default spice/delays_tt.json) as $OUT/delays.json. PREV, when set,
# holds 2D runs to reuse ($PREV/{small,big}/2d_n10_*). Shared server: few jobs at low priority.
# Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
BIG=${BIG:-/tmp/$USER/ceil/bench}
OUT=${OUT:-/tmp/$USER/stackedsweep}
J=${J:-$B/spice/delays_tt.json}
R=$(readlink -f ~/3d-clb/pnr_fast/clb_2d/resources)
mkdir -p $OUT
cd $B
if [ ! -s $OUT/delays.json ]; then
  # No outer nice: make_spice.py runs Spectre under tcsh's nice +10, which fails at nice 19.
  python3 spice/make_spice.py --models $R/cadence_sky130/sky130_release_0.1.0/models \
    --tlef $R/cadence_sky130/sky130_scl_9T_0.1.2/sky130_scl_9T_tech/lef/sky130_scl_9T.tlef \
    --env ~/3d-clb/pnr_fast/clb_2d --out $OUT/spice --fabric 3d10stack_w100 > $OUT/spice.log 2>&1 || exit 1
  python3 -c "import json,sys; d=json.load(open('$J')); d.update(json.load(open('$OUT/spice/delays_tt.json')));
json.dump(d, open('$OUT/delays.json', 'w'), indent=1)" || exit 1
fi
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300" --timeout 21600 --jobs ${JOBS:-3} --slim
        --seeds ${SEEDS:-1 2 3 4 5 6 7 8 9 10})
for set in ${SETS:-small big}; do
  if [ $set = big ]; then
    [ -e $BIG/sha.blif ] || { echo "no big benchmarks in $BIG"; exit 1; }
    SET=(--bench-dir $BIG --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha)
  else SET=(--bench-dir $MCNC); fi
  for v in laid direct; do
    fab=3d10stack_w100; [ $v = direct ] && fab=3d10stack_w100_direct
    mkdir -p $OUT/$v/$set
    # 2D runs: from PREV, and the direct pass reuses the laid-out pass's.
    for d in ${PREV:+$PREV/$set/2d_n10_*} $OUT/laid/$set/2d_n10_*; do
      [ -e "$d" ] && [ ! -e $OUT/$v/$set/$(basename $d) ] && cp -r $d $OUT/$v/$set/
    done
    nice -n 19 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" --output $OUT/$v/$set --stacked --w3d 100 \
      --delays $OUT/delays.json 2d10_w100 $fab > $OUT/${set}_stacked_$v.log 2>&1
    cp $OUT/$v/$set/results.csv $OUT/${set}_stacked_$v.csv
  done
done
echo STACKED_SWEEP_DONE
