#!/bin/bash
# Newer benchmarks (synth_bench.sh) through the main comparisons, at both nodes: the 20-LUT split
# CLB with own-layer pins (crossing as laid out, and direct) and stacked 10-LUT CLBs (laid out,
# direct) against the 10-LUT 2D CLB, and the split CLB against the 12-LUT 2D. Same fabrics, delays
# and seeds as run_spice_delays.sh OWN=1, run_stacked_spice.sh and run_7nm.sh.
# Pilot (2026-11-09, 1 seed, sky130): bnn (130k LUTs) does not route at 100 tracks in either
# fabric (1.1% overuse, flat after 15 iterations of up to 10 min); stereovision3 stops VPR at a
# timing-graph assertion on its second clock. So BENCHES defaults to diffeq1.
# Shared server: few jobs at low priority. Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
BENCH=${BENCH:-/tmp/$USER/newbench}
OUT=${OUT:-/tmp/$USER/newbenchsweep}
J130=${J130:-/tmp/$USER/stackedsweep/delays.json}   # sky130, with the stacked fabric merged in
J7=${J7:-/tmp/$USER/sweep7nm/spice/delays_tt.json}
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300" --timeout 21600 --jobs ${JOBS:-4} --slim
        --seeds ${SEEDS:-1 2 3 4 5 6 7 8 9 10} --bench-dir $BENCH --benches ${BENCHES:-diffeq1})
N20=(--n3d 20 --w3d 100 --local-inputs --wire-spans 4 15 --own-layer-inputs)
N2D12=(--n2d 12 --w2d 110 --wire-spans-2d 4 14)
cd $B
for node in sky130 7nm; do
  if [ $node = 7nm ]; then J=$J7 S=_7nm; else J=$J130 S=; fi
  # run NAME REUSE_FROM PATTERN ARGS...: copies matching earlier runs into this pass's folder.
  run() {
    name=$1 from=$2 pattern=$3; shift 3
    o=$OUT/$node/$name; mkdir -p $o
    for d in ${from:+$OUT/$node/$from/$pattern}; do
      [ -e "$d" ] && [ ! -e $o/$(basename $d) ] && cp -r $d $o/
    done
    nice -n 19 python3 compare_2d_3d.py "${COMMON[@]}" --output $o "$@" > $OUT/${node}_$name.log 2>&1
    cp $o/results.csv $OUT/${node}_$name.csv
  }
  run split          ""    ""         "${N20[@]}" --delays $J 2d10_w100$S 3d20own_w100$S
  run split_direct   split "2d_n10_*" "${N20[@]}" --delays $J 2d10_w100$S 3d20own_w100${S}_direct
  run n2d12          split "3d_*"     "${N20[@]}" "${N2D12[@]}" --delays $J 2d12_w110$S 3d20own_w100$S
  run stacked        split "2d_n10_*" --stacked --w3d 100 --delays $J 2d10_w100$S 3d10stack_w100$S
  run stacked_direct split "2d_n10_*" --stacked --w3d 100 --delays $J 2d10_w100$S 3d10stack_w100${S}_direct
done
echo NEWBENCH_DONE
