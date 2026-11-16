#!/bin/bash
# Places and routes both CLB layers with real crossings: the same core size on
# both, a driver and receiver on each critical signal, and bond pads at matching
# spots. Then it exports them and times the whole CLB against the 2D one.
# Needs the 2 ns run of run_pnr.sh and its join2d results in pnr_fast. Run in tmux.
# FLES gives the CLB size when it is not 10; CENTER_PADS=1 puts the bond pads mid-core.
# DIRECT=1 uses each bond as a via: one BUFX16 on the sending layer drives the other layer's
# net through the pad, with no receiver, and synthesis keeps it. BOND_LOAD (pF) is that net's
# load, default 1.0: 0.96 pF in the first direct layout (pnr_local20d), where without a kept
# driver synthesis left a CLKBUFX4 that took 1.25 ns. TAP=1 (implies DIRECT) puts an FLE output's
# crossing driver inside the FLE, beside the FLE's own output driver, instead of after it.
# BOND_LOADS=CSV (bond_net_loads.py) gives each bond output port its own load, what it really
# drives on the other layer, instead of 6 fF. KEEP_NETS=1 stops Innovus inserting buffers on the
# crossing nets (each crossing signal and its bond net, on both layers). BOND_DELAYS="IN OUT" (ns) sets
# the input delay on bond input ports and the output delay on bond output ports (default 0 and 0).
set -e
B="$(cd "$(dirname "$0")" && pwd)"
FLOW=${FLOW:?path to the sky130 RTL-to-GDS flow}
L=~/3d-clb/LaZagna
FAST=~/3d-clb/pnr_fast
OUT=${OUT:-~/3d-clb/pnr_bond}
PERIOD=${PERIOD:-2}
CORE=${CORE:-354}
R3D=${RTL_3D:-$(ls -td "$L"/tasks_run/3d_3d_cb_cw_50*/task_*/task/run001/verilog/SRC | grep -v clb_local | head -1)}
SPLIT=${SPLIT:-$FAST/split}
mkdir -p "$OUT/join3d" "$OUT/split"
[ -n "$TAP" ] && DIRECT=1
TAP_ARGS=()
[ -n "$TAP" ] && TAP_ARGS=(--tap "$R3D/lb/logical_tile_clb_mode_default__fle.v")
python3 "$B/add_crossing_buffers.py" "$SPLIT/clb_split.v" "$SPLIT/clb_crossings.csv" "$OUT/split/clb_split.v" ${DIRECT:+--direct} "${TAP_ARGS[@]}"
BOND=()
[ -n "$DIRECT" ] && BOND=(--bond-load ${BOND_LOAD:-1.0} --bond-driver BUFX16 --keep-crossing-drivers)
[ -n "$BOND_LOADS" ] && BOND+=(--bond-loads "$BOND_LOADS")
[ -n "$KEEP_NETS" ] && BOND+=(--keep-crossing-nets "$SPLIT/clb_crossings.csv")
[ -n "$BOND_DELAYS" ] && BOND+=(--bond-delays $BOND_DELAYS)

layer() {
  n=$1
  block=$OUT/clb_half$n
  python3 "$B/make_pnr_rtl.py" --source "$R3D" --top clb_layer$n --extra "$OUT/split/clb_split.v" --output "$OUT/clb_half$n.v"
  python3 "$B/setup_pnr.py" --flow "$FLOW" --rtl "$OUT/clb_half$n.v" --top clb_layer$n --output "$block" --period "$PERIOD" --core "$CORE" ${CENTER_PADS:+--center-pads} "${BOND[@]}"
  tcsh -f "$B/run_block.csh" "$block" > "$OUT/layer$n.log" 2>&1 || echo "FAIL: layer $n stopped early"
  tcsh -f "$B/run_innovus.csh" "$block" "$B/export_layout.tcl" >> "$OUT/layer$n.log" 2>&1 || echo "FAIL: layer $n export"
}
layer 0 &
layer 1 &
wait
for n in 0 1; do
  # Buffers Innovus named after an FLE output net (FE_OCPC123_n_..._fle_out_0): none expected with KEEP_NETS.
  echo "INSERTED_ON_CROSSING_NETS layer $n: $(grep -oE 'FE_[A-Z]+[0-9]+_[nx]_logical_tile_clb_mode_default__fle_[0-9]+_fle_out_[0-9]+' \
    "$OUT/clb_half$n/outputs/paths/clb_layer$n.routed.v" 2>/dev/null | sort -u | wc -l)"
done

python3 "$B/join_netlist.py" "$OUT/split/clb_split.v" "$OUT/join3d" \
  "$OUT/clb_half0/outputs/paths/clb_layer0.routed.v" "$OUT/clb_half1/outputs/paths/clb_layer1.routed.v"
export PNR_LAYERS=2 PNR_NETLIST=$OUT/join3d/joined.v PNR_FLES=${FLES:-10} PNR_CROSSING_PATH=1
export PNR_SPEF="$OUT/join3d/top.spef $OUT/clb_half0/outputs/paths/clb_layer0.spef $OUT/clb_half1/outputs/paths/clb_layer1.spef"
tcsh -f "$B/run_tempus.csh" "$OUT/clb_half0" "$OUT/join3d" "$B/join_timing.tcl" > "$OUT/join.log" 2>&1
grep -E 'JOIN_' "$OUT/join.log"
python3 "$B/compare_joined.py" "$OUT/join3d/clb_paths.csv" "$FAST/join2d/clb_paths.csv" ${FLES:-10}
echo BOND_DONE
