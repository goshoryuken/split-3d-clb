#!/bin/bash
# Why the 40-LUT split CLB over 4 layers loses at 7 nm (run_4layer_7nm.sh, 3 seeds: 1.341 small,
# 1.105 bigger, against 1.049 / 0.955 for the 2-layer split). Two diagnostic passes, same
# fabric, delays and seeds, after that sweep finishes:
#   split4_freeclb   layer crossings inside the CLB cost nothing: the most a layer-aware packer
#                    could recover (routing crossings unchanged).
#   split4_allpins   input pins reach every layer's tracks (no --own-layer-inputs). Upper bound:
#                    keeps the own-layer connection-block delays, so bigger CB muxes are not charged.
# Shared server: few jobs at low priority. Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
BIG=${BIG:-$HOME/3d-clb/bench_big}
OUT=${OUT:-/tmp/$USER/layers7nm}
until grep -q LAYERS7NM_DONE $OUT/../layers7nm.log 2>/dev/null; do sleep 300; done
cd $B
J=$OUT/spice/delays_tt.json
J2=$OUT/spice/delays_diag.json
python3 -c "import json; d = json.load(open('$J'));
d['3d40own_w100_7nm_freeclb'] = dict(d['3d40own_w100_7nm'], clb_crossing=0.0)
json.dump(d, open('$J2', 'w'), indent=1)" || exit 1
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300 --place_delay_model delta" --timeout 21600
        --jobs ${JOBS:-4} --slim --seeds ${SEEDS:-1 2 3} --switchblocks custom --vertical dense --w3d 100)
N40=(--n3d 40 --span 4 --layers 4 --wire-spans 4 14 --local-inputs)
for set in ${SETS:-small big}; do
  if [ $set = big ]; then
    SET=(--bench-dir $BIG --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha)
  else SET=(--bench-dir $MCNC); fi
  run() {
    name=$1; shift
    mkdir -p $OUT/$name/$set
    for d in $OUT/split2/$set/2d_n10_*; do
      [ -e "$d" ] && [ ! -e $OUT/$name/$set/$(basename $d) ] && cp -r $d $OUT/$name/$set/
    done
    nice -n 19 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" --output $OUT/$name/$set "$@" \
      > $OUT/${set}_$name.log 2>&1
    cp $OUT/$name/$set/results.csv $OUT/${set}_$name.csv
  }
  run split4_freeclb "${N40[@]}" --own-layer-inputs --delays $J2 2d10c_w100_7nm 3d40own_w100_7nm_freeclb
  run split4_allpins "${N40[@]}" --delays $J 2d10c_w100_7nm 3d40own_w100_7nm
done
echo DIAG_DONE
