#!/bin/bash
# Places and routes the routing of one typical tile of the 3D and 2D fabrics, so
# the whole tile can be compared and not only the CLB. The 3D fabric is generated
# with the tracks and wire spans the speed model uses. Run it in tmux.
# Usage: bash ~/3d-clb/lazagna-bundle/pnr/run_tile.sh 2>&1 | tee ~/3d-clb/tile.log
# PERIOD is one no routing block meets, so both fabrics are mapped for speed.
set -e
B="$(cd "$(dirname "$0")" && pwd)"
FLOW=${FLOW:?path to the sky130 RTL-to-GDS flow}
L=~/3d-clb/LaZagna
OUT=${OUT:-~/3d-clb/pnr_tile}
PERIOD=${PERIOD:-0.5}
WIDTH=${WIDTH:-70}
SPAN4=${SPAN4:-6}
SPAN16=${SPAN16:-23}
FABRICS=${FABRICS:-2d 3d}
# STACKED=1 builds a whole flat CLB on each layer instead of the split CLB.
# FLES sets the split CLB's size, LOCAL=1 feeds each layer's FLEs from its own pins, and
# OWN=1 lets input pins reach only their own layer's tracks (smaller connection blocks).
# WIDTH2D generates the 2D fabric at that many tracks instead of reusing an existing one.
FLES=${FLES:-10}
NAME=3d_clb_tile_w${WIDTH}_l${SPAN4}${STACKED:+_stacked}$([ "$FLES" = 10 ] || echo "_n$FLES")${LOCAL:+_local}${OWN:+_own}
mkdir -p "$OUT"
cd "$L"
source .venv/bin/activate

find_rtl() { ls -td tasks_run/$1/task_*/task/run001/verilog/SRC 2>/dev/null | head -1; }

R3D=$(find_rtl "3d_3d_cb_cw_${WIDTH}_*${NAME}*")
if [ ! -f "$R3D/fpga_top.v" ]; then
  python3 - <<PY
import sys
from pathlib import Path
sys.path.insert(0, "$B/..")
import compare_2d_3d
arch = Path("$B/../vtr_3d_clb_arch.xml").read_text()
if "$STACKED":
    arch = compare_2d_3d.stack_clbs(arch)
if $FLES != 10:
    arch = compare_2d_3d.resize_clb(arch, $FLES)
if "$LOCAL":
    arch = compare_2d_3d.local_inputs(arch, $FLES)
if "$OWN":
    arch = compare_2d_3d.own_layer_inputs(arch)
Path("arch_files/$NAME.xml").write_text(compare_2d_3d.stretch_wires(arch, $SPAN4, $SPAN16))
PY
  sed -e "s/^experiment_name: .*/experiment_name: \"$NAME\"/" -e "s/channel_width: 50/channel_width: $WIDTH/" \
      -e "s/vtr_3d_clb_arch.xml/$NAME.xml/" "$B/../3d_clb.yaml" > "setup_files/$NAME.yaml"
  # LaZagna reuses a generated architecture of the same name, so clear the old ones.
  find arch_files -maxdepth 1 -name "${NAME}_*" -delete
  # The layer-local crossbars need the original crossbar's mux type; the file is shared, so put it back.
  SETTINGS=task/designs/openfpga_arch.xml
  cp "$SETTINGS" "$OUT/openfpga_arch.bak"
  [ -n "$LOCAL" ] && sed -i 's#<interconnect name="crossbar" circuit_model_name="mux_2level"/>#<interconnect name="crossbar0" circuit_model_name="mux_2level"/><interconnect name="crossbar1" circuit_model_name="mux_2level"/>#' "$SETTINGS"
  python3 lazagna/main.py -f "setup_files/$NAME.yaml" -v > ~/3d-clb/$NAME.log 2>&1 || true
  cp "$OUT/openfpga_arch.bak" "$SETTINGS"
  R3D=$(find_rtl "3d_3d_cb_cw_${WIDTH}_*${NAME}*")
  [ -f "$R3D/fpga_top.v" ] || { echo "STOP: no 3D fabric was generated, see ~/3d-clb/$NAME.log"; exit 1; }
fi
if [ -n "$WIDTH2D" ]; then
  NAME2D=2d_clb_tile_w$WIDTH2D
  R2D=$(find_rtl "3d_2d_cw_${WIDTH2D}_*${NAME2D}*")
  if [ ! -f "$R2D/fpga_top.v" ]; then
    sed -e "s/^experiment_name: .*/experiment_name: \"$NAME2D\"/" -e "s/channel_width: 100/channel_width: $WIDTH2D/" \
        "$B/../2d_clb.yaml" > "setup_files/$NAME2D.yaml"
    python3 lazagna/main.py -f "setup_files/$NAME2D.yaml" -v > ~/3d-clb/$NAME2D.log 2>&1 || true
    R2D=$(find_rtl "3d_2d_cw_${WIDTH2D}_*${NAME2D}*")
    [ -f "$R2D/fpga_top.v" ] || { echo "STOP: no 2D fabric was generated, see ~/3d-clb/$NAME2D.log"; exit 1; }
  fi
else
  R2D=$(find_rtl "3d_2d*")
fi
echo "3D RTL: $R3D"
echo "2D RTL: $R2D"

python3 "$B/tile_blocks.py" "$R2D" > "$OUT/tile_2d.txt"
python3 "$B/tile_blocks.py" "$R3D" > "$OUT/tile_3d.txt"
cat "$OUT/tile_2d.txt" "$OUT/tile_3d.txt"
[ -n "$PICK_ONLY" ] && exit 0

for fabric in $FABRICS; do
  [ "$fabric" = 2d ] && SRC=$R2D || SRC=$R3D
  grep '^block' "$OUT/tile_$fabric.txt" | while read -r _ layer kind module inputs; do
    block=$OUT/$fabric/$module
    [ -f "$block/outputs/apr/RPT/summary.rpt" ] && continue
    echo "=== $fabric layer $layer $kind $module: starting $(date)"
    mkdir -p "$OUT/$fabric"
    python3 "$B/make_pnr_rtl.py" --source "$L/$SRC" --top "$module" --output "$OUT/$fabric/$module.v"
    python3 "$B/setup_pnr.py" --flow "$FLOW" --rtl "$OUT/$fabric/$module.v" --top "$module" --output "$block" --period "$PERIOD"
    tcsh -f "$B/run_block.csh" "$block" || echo "FAIL: $module stopped early"
  done
done

echo "=== RESULTS ==="
for fabric in $FABRICS; do
  grep -E '^(block|scale)' "$OUT/tile_$fabric.txt" | while read -r what layer kind module inputs; do
    [ "$what" = scale ] && { echo "$fabric scale $layer $kind"; continue; }
    S=$OUT/$fabric/$module/outputs
    core=$(grep -h 'Total area of Core' "$S/apr/RPT/summary.rpt" 2>/dev/null | grep -oE '[0-9.]+' | head -1)
    cell=$(grep -h 'Total cell area' "$S/synthesis/RPT/report.area" 2>/dev/null | grep -oE '[0-9.]+' | head -1)
    drc=$(grep -h 'Total number of DRC violations' "$S/apr/LOG/step_route.log" 2>/dev/null | tail -1 | grep -oE '[0-9]+' | tail -1)
    slack=$(grep -h 'Slack Time' "$S/apr/RPT/final_timing.rpt" 2>/dev/null | head -1 | grep -oE '[-0-9.]+' | tail -1)
    echo "$fabric $layer $kind $module inputs=$inputs cell=$cell core=$core drc=$drc slack=$slack"
  done
done
