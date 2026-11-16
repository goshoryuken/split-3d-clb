#!/bin/bash
# Times finished bonded layouts (run_bond.sh outputs) again with this folder's join_timing.tcl,
# without touching them: each joined CLB is read from its folder and timed into $WORK/<name>, one
# Tempus at a time. Used to add the mux_in column (arrival at the crossbar mux) to clb_paths.csv.
# Usage: retime_joined.sh FLES LAYOUT_DIR...   Env: WORK (default /tmp/$USER/retime). Run in tmux.
set -e
B="$(cd "$(dirname "$0")" && pwd)"
FLES=${1:?usage: retime_joined.sh FLES LAYOUT_DIR...}; shift
WORK=${WORK:-/tmp/$USER/retime}
uptime
read load _ < /proc/loadavg
if awk -v l="$load" -v n="$(nproc)" 'BEGIN { exit !(l > n / 2) }'; then
  echo "STOP: load $load on $(nproc) cores, try later"; exit 1
fi
for L in "$@"; do
  W=$WORK/$(basename "$L")
  mkdir -p "$W"
  PNR_LAYERS=2 PNR_NETLIST=$L/join3d/joined.v PNR_FLES=$FLES PNR_CROSSING_PATH=1 \
  PNR_SPEF="$L/join3d/top.spef $L/clb_half0/outputs/paths/clb_layer0.spef $L/clb_half1/outputs/paths/clb_layer1.spef" \
    tcsh -f "$B/run_tempus.csh" "$L/clb_half0" "$W" "$B/join_timing.tcl" > "$W.log" 2>&1 || true
  echo "$(basename "$L"): $(grep -E 'JOIN_DONE|JOIN_FAILED' "$W.log" | head -1)"
  cmp -s <(cut -d, -f1-8 "$W/clb_paths.csv") "$L/join3d/clb_paths.csv" \
    && echo "  clb_paths.csv: same as the original in its first 8 columns" \
    || echo "  clb_paths.csv: DIFFERS from the original"
done
echo RETIME_DONE
