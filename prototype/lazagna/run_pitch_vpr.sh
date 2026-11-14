#!/bin/bash
# Bond-pitch sweep, speed: the 20-LUT split CLB (own-layer pins) and stacked 10-LUT CLBs at 7 nm
# with crossings as laid out, at 1, 5 and 10 um bond pitch (run_pitch_spice.sh delay sets), on the
# bigger VTR designs. Same VPR, options, tracks and seeds as run_7nm.sh; its 10-LUT 2D runs (pitch
# does not touch them) are copied in and reused. Waits for run_pitch_spice.sh (PITCH_DONE).
# Shared server: few jobs at low priority. Run in tmux. Ends with PITCH_VPR_DONE.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
BIG=${BIG:-$HOME/3d-clb/bench_big}
SP=${SP:-/tmp/$USER/pitch2}
OLD=${OLD:-/tmp/$USER/sweep7nm}
OUT=${OUT:-/tmp/$USER/pitchvpr}
until grep -q PITCH_DONE $SP.log 2>/dev/null; do sleep 120; done
mkdir -p $OUT
cd $B
J=$OUT/delays_pitch.json
python3 -c "import json; d = {'2d10_w100_7nm': json.load(open('$OLD/spice/delays_tt.json'))['2d10_w100_7nm']}
for p in (${PITCHES:-1, 5, 10},):
    for k, v in json.load(open(f'$SP/7nm_p{p}/delays_tt.json')).items():
        d[f'{k}_p{p}'] = v
json.dump(d, open('$J', 'w'), indent=1)" || exit 1
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300" --timeout 21600 --jobs ${JOBS:-4} --slim
        --seeds ${SEEDS:-1 2 3 4 5 6 7 8 9 10}
        --bench-dir $BIG --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha)
N20=(--n3d 20 --w3d 100 --local-inputs --wire-spans 4 15 --own-layer-inputs)
run() {
  name=$1; shift
  mkdir -p $OUT/$name
  for d in $OLD/split/big/2d_n10_*; do
    [ -e "$d" ] && [ ! -e $OUT/$name/$(basename $d) ] && cp -r $d $OUT/$name/
  done
  nice -n 19 python3 compare_2d_3d.py "${COMMON[@]}" --output $OUT/$name "$@" > $OUT/$name.log 2>&1
  cp $OUT/$name/results.csv $OUT/$name.csv
}
for p in ${PITCHES_SH:-5 10 1}; do
  run split_p$p "${N20[@]}" --delays $J 2d10_w100_7nm 3d20own_w100_7nm_p$p
  run stacked_p$p --stacked --w3d 100 --delays $J 2d10_w100_7nm 3d10stack_w100_7nm_p$p
done
echo PITCH_VPR_DONE
