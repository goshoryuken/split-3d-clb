#!/bin/bash
# The 20-LUT split CLB laid out again with its crossings set up the way SPICE models them, to see
# how much of the layout's +760 ps crossing (pnr_local20c) comes from the setup. Same RTL, split,
# 520 um core, mid-core pads and 2 ns clock as pnr_local20c; one change per run:
#   s  each bond output port's load set to what it really drives on the other layer
#      (bond_net_loads.py on pnr_local20c), not 6 fF, so the tools size the crossing driver for it
#   t  also no buffers inserted on the crossing nets (on pnr_local20c's worst crossing path Innovus
#      put a BUFX8 before the driver and a CLKBUFX2 after the receiver). The FLE output nets lose
#      their inserted buffers on same-layer paths too, so the subtraction stays like for like.
#   u  s plus timing budgets on the bond ports instead of 0 ns: each layer alone sees the crossing
#      half-paths as critical as they are joined. From pnr_local20c's worst crossing path
#      (crossing_path_local20_center.txt): the sending half reaches the port at 2.210, 1.210 ns after
#      the 1.000 clock edge (input delay); the receiving half needs 4.252 - 2.212 = 2.040 ns and must
#      end by 2.922, so the port is due at 0.882, 2.118 ns before the next edge at 3.000 (output delay).
# Each run lays out both layers at once (two Innovus jobs), then joins them in Tempus; the runs go
# one after the other. Shared server: run in tmux; it stops if the machine is busy. Where jobs per
# user are limited, run nothing else meanwhile. Results:
# $WORK/pnr_local20{s,t,u}/join3d/{clb_paths.csv,crossing_path.txt}. Ends with FIX_DONE.
set -e
B="$(cd "$(dirname "$0")" && pwd)"
L=~/3d-clb/LaZagna
REF=${REF:-$HOME/3d-clb/pnr_local20c}
WORK=${WORK:-/tmp/$USER}
SCL=$(readlink -f ~/3d-clb/pnr_fast/clb_2d/resources)/cadence_sky130/sky130_scl_9T_0.1.2
uptime
read load _ < /proc/loadavg
if awk -v l="$load" -v n="$(nproc)" 'BEGIN { exit !(l > n / 2) }'; then
  echo "STOP: load $load on $(nproc) cores, try later"; exit 1
fi
# pnr_local20c ran run_bond.sh on run_local.sh FLES=20's fabric and split (pnr_local20); the RTL line
# in that run's log names the fabric (a newer local20 fabric exists, so not the newest). Read only.
RTL_3D=${RTL_3D:-$L/$(sed -n 's/^RTL: //p' ~/3d-clb/pnr_local20.log | head -1)}
SPLIT=${SPLIT:-$HOME/3d-clb/pnr_local20/split0}
[ -f "$RTL_3D/fpga_top.v" ] || { echo "STOP: no RTL at $RTL_3D"; exit 1; }
[ -f "$SPLIT/clb_crossings.csv" ] || { echo "STOP: no $SPLIT"; exit 1; }
echo "RTL: $RTL_3D"
echo "SPLIT: $SPLIT"
mkdir -p "$WORK"
python3 "$B/bond_net_loads.py" --layout "$REF" \
  --lib "$SCL/sky130_scl_9T/lib/sky130_tt_1.8_25_nldm.lib" "$SCL/sky130_scl_9T_HS/lib/sky130_tt_1.8_25_nldm.lib" \
  > "$WORK/bond_loads_local20c.csv"
for run in ${RUNS:-s t}; do
  keep=""; [ "$run" = t ] && keep=1
  delays=""; [ "$run" = u ] && delays="1.210 2.118"
  RTL_3D="$RTL_3D" SPLIT="$SPLIT" OUT="$WORK/pnr_local20$run" CORE=520 FLES=20 CENTER_PADS=1 \
    BOND_LOADS="$WORK/bond_loads_local20c.csv" KEEP_NETS=$keep BOND_DELAYS=$delays bash "$B/run_bond.sh" > "$WORK/pnr_local20$run.log" 2>&1 \
    || echo "FAIL: run $run, see $WORK/pnr_local20$run.log"
  grep -E "KEEP_CROSSING_NETS|INSERTED_ON|JOIN_|CROSSING_PATH|FAIL|BOND_DONE|feedback|pin:" "$WORK/pnr_local20$run.log" \
    "$WORK"/pnr_local20$run/layer*.log 2>/dev/null || true
  # Same inputs as pnr_local20c, and its constraints plus only this run's change.
  o=$WORK/pnr_local20$run
  cmp -s "$o/split/clb_split.v" "$REF/split/clb_split.v" && echo "split: same as $REF" || echo "split: DIFFERS from $REF"
  for n in 0 1; do
    cmp -s "$o/clb_half$n.v" "$REF/clb_half$n.v" && echo "layer $n RTL: same as $REF" || echo "layer $n RTL: DIFFERS from $REF"
    diff "$REF/clb_half$n/scripts/synthesis/steps/step_constraints.tcl" "$o/clb_half$n/scripts/synthesis/steps/step_constraints.tcl" \
      | grep '^[<>]' | grep -v '^[<>] #' | sed "s/^/layer $n constraints: /" | head -5
  done
done
echo FIX_DONE
