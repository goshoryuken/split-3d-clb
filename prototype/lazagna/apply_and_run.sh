#!/bin/bash
# Puts the two-layer CLB into the server's LaZagna build, rebuilds, generates RTL
# for it and for its 2D baseline, and checks both. Safe to re-run.
# Usage: bash ~/3d-clb/lazagna-bundle/apply_and_run.sh 2>&1 | tee ~/3d-clb/run.log
set -e
export CCACHE_DISABLE=1
B="$(cd "$(dirname "$0")" && pwd)"
L=~/3d-clb/LaZagna
V="$L/OpenFPGA/vtr-verilog-to-routing"
BENCH=${BENCH:-ex5p}
cd "$L"

case "$(git -C OpenFPGA rev-parse HEAD)" in 9f473f97*) ;; *) echo "STOP: OpenFPGA is not 9f473f97 - check the setup"; exit 1;; esac
case "$(git -C "$V" rev-parse HEAD)" in 5abd3acaa*) ;; *) echo "STOP: VTR is not 5abd3acaa - check the setup"; exit 1;; esac

SRC=$(find benchmarks -type d -name "$BENCH" | head -1)
if [ -z "$SRC" ]; then echo "STOP: no benchmark folder named $BENCH under benchmarks/ - check the setup"; exit 1; fi
for e in blif act v; do
  [ -n "$(find "$SRC" -name "*.$e" | head -1)" ] || { echo "STOP: $SRC has no .$e file - check the setup"; exit 1; }
done

if grep -q pin_physical_layer "$V/libs/libarchfpga/src/physical_types.h"; then
  echo "VTR already up to date"
else
  if [ -f "$V/libs/libarchfpga/src/pb_type_layers.cpp" ]; then
    git -C "$V" apply -R "$B/archive/previous/vtr-3d-clb.patch"
  else
    git -C "$V" apply -R "$B/lazagna-vtr-fixes.patch"
  fi
  git -C "$V" apply "$B/vtr-3d-clb.patch"
  echo "VTR patched"
fi
if grep -q 'is_ignored_pin\[rr_graph.node_pin_num' OpenFPGA/openfpga/src/annotation/annotate_rr_graph.cpp; then
  echo "OpenFPGA already up to date"
else
  if grep -q find_pb_graph_pin_interc_layer_offset OpenFPGA/openfpga/src/fabric/build_grid_modules.cpp; then
    git -C OpenFPGA apply -R "$B/archive/previous/openfpga-labels.patch"
  elif grep -q find_pin_grid_layer OpenFPGA/openfpga/src/fabric/build_top_module_connection.cpp; then
    git -C OpenFPGA apply -R "$B/archive/previous/openfpga-pins.patch"
  elif grep -rq vtr_parent_relative_layer_offset OpenFPGA/openfpga/src; then
    git -C OpenFPGA apply -R "$B/archive/previous/openfpga-lazagna.patch"
  fi
  git -C OpenFPGA apply "$B/openfpga-lazagna.patch"
  echo "OpenFPGA patched"
fi

cp "$B/vtr_3d_clb_arch.xml" "$B/vtr_2d_clb_arch.xml" arch_files/
# LaZagna reuses a generated architecture of the same name, so clear the old ones.
find arch_files -maxdepth 1 -name 'vtr_[23]d_clb_arch_*' -delete
cp "$B/3d_clb.yaml" "$B/2d_clb.yaml" setup_files/
rm -rf benchmarks/clb_compare
mkdir -p benchmarks/clb_compare
cp -r "$SRC" benchmarks/clb_compare/

source .venv/bin/activate
cd OpenFPGA
make prebuild CMAKE_FLAGS="-DOPENFPGA_WITH_SWIG=OFF -DOPENFPGA_WITH_YOSYS=OFF -DOPENFPGA_WITH_YOSYS_PLUGIN=OFF -DOPENFPGA_WITH_TEST=OFF -DTATUM_EXECUTION_ENGINE=serial -DVPR_EXECUTION_ENGINE=serial"
nice -n 19 make -C build -j4
cd ..

# LaZagna lowers its own priority to 11, which fails if the shell is already lower.
sed -i 's/^\( *\)process\.nice(11)$/\1process.nice(max(process.nice(), 11))/' lazagna/main.py

run_one() {
  name=$1
  STAMP=$(mktemp)
  python3 lazagna/main.py -f setup_files/${name}_clb.yaml -v > ~/3d-clb/$name.log 2>&1 || true
  TOP=$(find tasks_run -name fpga_top.v -newer "$STAMP" 2>/dev/null | head -1)
  if [ -z "$TOP" ]; then echo "FAIL $name: no new fpga_top.v. See ~/3d-clb/$name.log"; return 1; fi
  S=$(dirname "$TOP")
  R=${S%/verilog/SRC}
  echo "=== $name ==="
  echo "RTL: $S"
  echo "bitstream lines: $(wc -l < "$S/fabric_bitstream.bit")"
  grep -rh "Final critical path delay" "$R" --include='*.log' | head -1
  grep -rh "Total wirelength" "$R" --include='*.log' | head -1
  if [ "$name" = 3d ]; then
    N0=$(grep -rh 'vtr_parent_relative_layer_offset = 0' "$S" | wc -l)
    N1=$(grep -rh 'vtr_parent_relative_layer_offset = 1' "$S" | wc -l)
    U=$(grep -c undriven_interlayer "$S/fpga_top.v" || true)
    P=$(grep -cE '\.[a-z_0-9]*pin_I_(2[0-9]|3[0-9])_\[?[0-9:]*\]?\(cb[xy]_1_' "$S/fpga_top.v" || true)
    echo "CLB parts on layer 0: $N0  on layer 1: $N1  undriven: $U  layer 1 pins driven from layer 1: $P"
    python3 "$B/split_clb_layers.py" --source "$S" --arch arch_files/vtr_3d_clb_arch.xml --output ~/3d-clb/split
    if [ "$N1" -gt 0 ] && [ "$U" = 0 ] && [ "$P" -gt 0 ]; then echo "PASS 3d"; else echo "FAIL 3d"; fi
  else
    echo "PASS 2d"
  fi
}
run_one 3d || true
run_one 2d || true
