#!/bin/bash
# Bond-pitch sweep, delays: the split CLB (own-layer pins) and stacked CLBs at 1, 5 and 10 um bond
# pitch, sky130 and 7 nm (ASAP7). Pads are half the pitch (make_spice.py --pitch); 5 um sky130 and
# 1 um 7 nm are the existing delay sets, rerun as a check. Spectre only, one deck at a time.
# Shared server: run in tmux. Results: $OUT/{sky130,7nm}_p<pitch>/delays_tt.json; ends with PITCH_DONE.
B=~/3d-clb/lazagna-bundle
OUT=${OUT:-/tmp/$USER/pitch}
R=$(readlink -f ~/3d-clb/pnr_fast/clb_2d/resources)
M7=${M7:-$HOME/3d-clb/asap7_models}
ENV=~/3d-clb/pnr_fast/clb_2d
cd $B
for p in ${PITCHES:-1 5 10}; do
  # No outer nice: make_spice.py runs Spectre under tcsh's nice +10, which fails at nice 19.
  python3 spice/make_spice.py --models $R/cadence_sky130/sky130_release_0.1.0/models \
    --tlef $R/cadence_sky130/sky130_scl_9T_0.1.2/sky130_scl_9T_tech/lef/sky130_scl_9T.tlef \
    --env $ENV --out $OUT/sky130_p$p --pitch $p --fabric 3d20own_w100 3d10stack_w100 > $OUT/sky130_p$p.log 2>&1
  python3 spice/make_spice.py --models $M7 --env $ENV --out $OUT/7nm_p$p --pitch $p \
    --fabric 3d20own_w100_7nm 3d10stack_w100_7nm > $OUT/7nm_p$p.log 2>&1
done
echo PITCH_DONE
