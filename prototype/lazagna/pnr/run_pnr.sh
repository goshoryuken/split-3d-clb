#!/bin/bash
# Runs synthesis and place and route on the 2D CLB and on each 5-FLE layer of the
# two-layer CLB, then prints what is needed to compare them. Run it in tmux.
# Usage: bash ~/3d-clb/lazagna-bundle/pnr/run_pnr.sh 2>&1 | tee ~/3d-clb/pnr.log
# Set PERIOD (ns) and OUT to run at another clock in another folder. A clock
# neither block can meet makes both tools work on speed, which a delay comparison
# needs: at 15 ns they map the same logic to different cells. Set BLOCKS to run
# only some blocks.
set -e
B="$(cd "$(dirname "$0")" && pwd)"
FLOW=${FLOW:?path to the sky130 RTL-to-GDS flow}
L=~/3d-clb/LaZagna
OUT=${OUT:-~/3d-clb/pnr}
PERIOD=${PERIOD:-15}

[ -d "$FLOW/resources/cadence_sky130" ] || { echo "STOP: no sky130 kit in $FLOW/resources - check the setup"; exit 1; }
R3D=$(ls -td "$L"/tasks_run/3d_3d_cb_cw_50*/task_*/task/run001/verilog/SRC | grep -v clb_local | head -1)
R2D=$(ls -td "$L"/tasks_run/3d_2d*/task_*/task/run001/verilog/SRC | head -1)
mkdir -p "$OUT"

python3 "$B/../split_clb_layers.py" --source "$R3D" --arch "$L/arch_files/vtr_3d_clb_arch.xml" --output "$OUT/split"
python3 "$B/make_pnr_rtl.py" --source "$R3D" --top clb_layer0 --extra "$OUT/split/clb_split.v" --output "$OUT/clb_half.v"
python3 "$B/make_pnr_rtl.py" --source "$R3D" --top clb_layer1 --extra "$OUT/split/clb_split.v" --output "$OUT/clb_half1.v"
python3 "$B/make_pnr_rtl.py" --source "$R2D" --top logical_tile_clb_mode_clb_ --output "$OUT/clb_2d.v"
python3 "$B/setup_pnr.py" --flow "$FLOW" --rtl "$OUT/clb_half.v" --top clb_layer0 --output "$OUT/clb_half" --period "$PERIOD"
python3 "$B/setup_pnr.py" --flow "$FLOW" --rtl "$OUT/clb_half1.v" --top clb_layer1 --output "$OUT/clb_half1" --period "$PERIOD"
python3 "$B/setup_pnr.py" --flow "$FLOW" --rtl "$OUT/clb_2d.v" --top logical_tile_clb_mode_clb_ --output "$OUT/clb_2d" --period "$PERIOD"

for block in ${BLOCKS:-clb_half clb_half1 clb_2d}; do
  echo "=== $block: starting $(date)"
  tcsh -f "$B/run_block.csh" "$OUT/$block" || echo "FAIL: $block stopped early"
  tcsh -f "$B/run_innovus.csh" "$OUT/$block" "$B/report_paths.tcl" || echo "FAIL: $block path timing stopped early"
done

echo "=== RESULTS ==="
for block in clb_half clb_half1 clb_2d; do
  echo "--- $block"
  grep -hE 'Number of sequential cells|Total cell area|Combinational area|Noncombinational area' "$OUT/$block/outputs/synthesis/RPT/report.area" 2>/dev/null
  grep -cE 'lut6|logical_tile_clb_mode_default__fle' "$OUT/$block/outputs/synthesis/RPT/report.refs" 2>/dev/null | sed 's/^/FLE and LUT lines in netlist: /'
  S="$OUT/$block/outputs/apr/RPT/summary.rpt"
  [ -f "$S" ] && grep -iE 'Total area of Core|Total area of Standard cells|Total wire length|Core Density|Total area of Chip' "$S" | head -6
  [ -f "$OUT/$block/outputs/apr/RPT/final_timing.rpt" ] && grep -E 'Slack Time|Path 1:' "$OUT/$block/outputs/apr/RPT/final_timing.rpt" | head -2
  grep -hE '^\*\*ERROR|^Error:' "$OUT/$block/outputs/synthesis/synthesis.log" "$OUT/$block/outputs/apr/apr.log" 2>/dev/null | sort | uniq -c | sort -rn | head -5
done
for half in clb_half clb_half1; do
  echo "--- $half over clb_2d"
  python3 "$B/compare_paths.py" "$OUT/$half/outputs/paths/crossbar_paths.csv" "$OUT/clb_2d/outputs/paths/crossbar_paths.csv"
done
