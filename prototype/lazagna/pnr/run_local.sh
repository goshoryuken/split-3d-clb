#!/bin/bash
# Lays out the local-pin CLB, where each layer's FLEs read only that layer's pins:
# generates its fabric, splits it by layer, then runs the bonded layout flow.
# FLES sets the CLB size (10 by default, half on each layer, four inputs per FLE).
set -e
B="$(cd "$(dirname "$0")" && pwd)"
L=~/3d-clb/LaZagna
OUT=${OUT:-~/3d-clb/pnr_local}
FLES=${FLES:-10}
NAME=3d_clb_local$([ "$FLES" = 10 ] || echo "$FLES")
mkdir -p "$OUT"
cd "$L"
source .venv/bin/activate
python3 - <<PY
import sys
from pathlib import Path
sys.path.insert(0, "$B/..")
import compare_2d_3d
arch = Path("$B/../vtr_3d_clb_arch.xml").read_text()
if $FLES != 10:
    arch = compare_2d_3d.resize_clb(arch, $FLES)
Path("arch_files/$NAME.xml").write_text(compare_2d_3d.local_inputs(arch, $FLES))
PY
sed -e "s/^experiment_name: .*/experiment_name: \"$NAME\"/" -e "s/vtr_3d_clb_arch.xml/$NAME.xml/" "$B/../3d_clb.yaml" > "setup_files/$NAME.yaml"
find arch_files -maxdepth 1 -name "${NAME}_*" -delete
# The new crossbars need the same mux type as the original one, or OpenFPGA picks a
# one-hot mux with about twice the config bits. This file is shared, so put it back.
SETTINGS=task/designs/openfpga_arch.xml
cp "$SETTINGS" "$OUT/openfpga_arch.bak"
sed -i 's#<interconnect name="crossbar" circuit_model_name="mux_2level"/>#<interconnect name="crossbar0" circuit_model_name="mux_2level"/><interconnect name="crossbar1" circuit_model_name="mux_2level"/>#' "$SETTINGS"
python3 lazagna/main.py -f "setup_files/$NAME.yaml" -v > ~/3d-clb/$NAME.log 2>&1 || true
cp "$OUT/openfpga_arch.bak" "$SETTINGS"
R3D=$(ls -td tasks_run/3d_3d_cb_cw_50_*${NAME}*/task_*/task/run001/verilog/SRC 2>/dev/null | head -1)
[ -f "$R3D/fpga_top.v" ] || { echo "STOP: no fabric, see ~/3d-clb/$NAME.log"; exit 1; }
echo "RTL: $R3D"
python3 "$B/../split_clb_layers.py" --source "$R3D" --arch "arch_files/$NAME.xml" --output "$OUT/split0"
RTL_3D="$L/$R3D" SPLIT="$OUT/split0" OUT="$OUT" CORE=${CORE:-312} FLES=$FLES bash "$B/run_bond.sh"
