#!/bin/bash
# The in-CLB crossing stage by stage in Spectre (crossing_stages.py), on the server: six small
# feedback decks, one Spectre at a time. Loads are the layout's worst crossing path
# (pnr/crossing_path_local20_center.txt): the FLE output driver drives 0.627 pF, the inserted BUFX8
# 0.165, the crossing driver's bond net 0.074, the receiver 0.386, the inserted CLKBUFX2 0.050.
# First copy make_spice.py, crossing_stages.py, delays_tt.json and this file to $OUT/code; then in
# tmux: bash $OUT/code/run_crossing_stages.sh. It stops if the machine is busy. Ends with STAGES_DONE.
set -e
OUT=${OUT:-/tmp/$USER/crossing_stages}
ENV=${ENV:-$HOME/3d-clb/pnr_fast/clb_2d}
K=$(readlink -f "$ENV/resources")/cadence_sky130
SCL=$K/sky130_scl_9T_0.1.2
uptime
read load _ < /proc/loadavg
if awk -v l="$load" -v n="$(nproc)" 'BEGIN { exit !(l > n / 2) }'; then
  echo "STOP: load $load on $(nproc) cores, try later"; exit 1
fi
# The standard cells' transistor netlists, for the as-laid-out variants (read at run time only).
CDL=$(find "$SCL" -iname '*.cdl' 2>/dev/null | sort | tr '\n' ' ')
echo "CDL: ${CDL:-none found, so no standard-cell variants}"
cd "$OUT/code"
# No outer nice: make_spice.run starts Spectre under tcsh's nice +10, which fails at nice 19.
python3 crossing_stages.py --models "$K/sky130_release_0.1.0/models" \
  --tlef "$SCL/sky130_scl_9T_tech/lef/sky130_scl_9T.tlef" --env "$ENV" --out "$OUT" \
  --own-pf 0.627 --ins-pf 0.165 0.050 --bond-pf 0.074 --other-pf 0.386 ${CDL:+--cells $CDL} \
  2>&1 | tee "$OUT/crossing_stages.log"
echo STAGES_DONE
