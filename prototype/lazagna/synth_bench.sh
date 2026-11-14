#!/bin/bash
# Synthesize VTR Verilog benchmarks to 6-LUTs and flip-flops for the CLB-only sweep.
# Multipliers become LUT logic, since the sweep's fabric has no DSP blocks; designs
# with memories are not supported. Unclocked latches go on the clock named "clock",
# which only bgm needs.
#
# Needs Yosys and ABC built out of tree from this VTR checkout:
#   cmake -S abc -B build/abc -DCMAKE_BUILD_TYPE=Release && make -C build/abc -j12
#   cd build/yosys && PATH=/opt/homebrew/opt/bison/bin:/opt/homebrew/opt/flex/bin:$PATH \
#     make -f ../../yosys/Makefile CONFIG=clang ENABLE_TCL=0 ENABLE_READLINE=0 ENABLE_PLUGINS=0 \
#     ABCEXTERNAL=$PWD/../abc/abc -j12
#
# Usage: synth_bench.sh OUTPUT_DIR bench...   (e.g. bgm stereovision0 stereovision1 stereovision2 blob_merge diffeq2 sha)
# A bench is a path under vtr_flow/benchmarks/verilog without .v, so Koios designs are koios/NAME.
# Memory-free designs added 2026-11-09: koios/bnn koios/gemm_layer diffeq1 stereovision3 (Koios with
# complex_dsp and hard_mem undefined, its no-hard-block mode).
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT=$(mkdir -p "$1" && cd "$1" && pwd)
shift
for b in "$@"; do
    f=$ROOT/vtr_flow/benchmarks/verilog/$b.v
    n=$(basename "$b")
    (cd "$(dirname "$f")" && nice "$ROOT/build/yosys/yosys" -q -p "read_verilog -nomem2reg $f;
        synth -flatten -auto-top; async2sync; dffunmap; abc -lut 6; opt_clean -purge; write_blif $OUT/$n.blif") \
        > "$OUT/$n.ylog" 2>&1 &
done
wait
for b in "$@"; do
    b=$(basename "$b")
    awk '$1 == ".latch" && NF == 4 {print $1, $2, $3, "re clock", $4; next} {print}' "$OUT/$b.blif" > "$OUT/$b.tmp"
    mv "$OUT/$b.tmp" "$OUT/$b.blif"
    echo "$b: $(grep -c '^.names' "$OUT/$b.blif") LUTs, $(grep -c '^.latch' "$OUT/$b.blif") flip-flops"
done
