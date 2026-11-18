#!/bin/bash
# Experiment D: the layer pass through the hardware flow (ff_test/run_ff_test.py). A 20-LUT test
# design (make_ff_design.py --count 20: 18 flip-flops in a chain plus 2 combinational LUTs, one CLB)
# on the sweeps' split CLB (20 FLEs, one crossbar per layer reading only its own layer's pins,
# own-layer input pins): VPR packs and writes its criticalities, layer_pass.py rewrites the .net,
# OpenFPGA's VPR places and routes that .net and OpenFPGA writes the fabric Verilog and bitstream,
# split_clb_layers.py splits the CLB into its two layers, and Icarus runs the configured fabric
# against the design's reference Verilog (1,000 cycles per case, then 5,000).
#   pass        the pass as the sweeps run it; cuts: clk, reset must fail, every used crossing caught
#   control     layer_pass.py --control: every FLE renumbered within its layer (exercises the rewrite
#               on every FLE; no layer change)
#   fault_net   negative control: one FLE input of the rewritten .net moved to another FLE's output
#   fault_lut   negative control: one truth-table row dropped from LUT d0 (an FLE the pass moves) in
#               the implemented netlist only
#   nopass      the same fabric and design without the pass, for comparison
#   default10_regression   run_ff_test.py with none of the new options (the original 10-LUT test),
#               to show those options leave it unchanged
# Logs: <case>.txt here. Usage: hwcheck/run_hwcheck.sh WORK    Env: OF (the OpenFPGA build folder
# holding openfpga/openfpga and the try/ support files; default build/of at the repo root, as in ff_test/).
HERE=$(cd "$(dirname "$0")" && pwd)
LZ=$(cd "$HERE/../../../../.." && pwd)
WORK=$(mkdir -p "${1:?usage: run_hwcheck.sh WORK}" && cd "$1" && pwd)
OF=${OF:-$LZ/../../build/of}
one() {  # NAME ARGS...
  name=$1; shift
  python3 "$LZ/ff_test/run_ff_test.py" --work "$WORK/$name" --support "$OF/try" --openfpga "$OF/openfpga/openfpga" \
    --fles 20 --local --own-layer --jobs 2 "$@" > "$HERE/$name.txt" 2>&1
  echo "$name: exit $?"
}
one pass --layer-pass
one control --layer-pass --pass-args=--control
one fault_net --layer-pass --plant-fault net
one fault_lut --layer-pass --plant-fault lut:d0
one nopass
python3 "$LZ/ff_test/run_ff_test.py" --work "$WORK/default10" --support "$OF/try" --openfpga "$OF/openfpga/openfpga" \
  --jobs 2 > "$HERE/default10_regression.txt" 2>&1
echo "default10_regression: exit $?"
