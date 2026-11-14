#!/bin/bash
# Synthesize Koios designs to 6-LUTs, flip-flops and hard blocks with plain Yosys (no parmys).
# hard_mem is defined, so each design instantiates VTR's single_port_ram / dual_port_ram
# primitives; koios_hb.v splits them into the architecture's 20 Kb blocks. complex_dsp stays
# undefined, so multipliers are behavioral and mulmap.v maps them onto the architecture's
# 18x19 / 27x27 hard multipliers (the DSP's floating-point modes are not modeled).
# Usage: synth_koios.sh OUTPUT_DIR name...   (names under vtr_flow/benchmarks/verilog/koios)
# Env: YOSYS (default: this repo's build/yosys/yosys), JOBS (parallel designs, default 4).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
YOSYS=${YOSYS:-$ROOT/build/yosys/yosys}
OUT=$(mkdir -p "$1" && cd "$1" && pwd)
shift
run_one() {
    n=$1
    f=$ROOT/vtr_flow/benchmarks/verilog/koios/$n.v
    nice "$YOSYS" -q -l "$OUT/$n.ylog" -p "read_verilog -nomem2reg -Dhard_mem $HERE/koios_hb.v $f;
        hierarchy -check -auto-top; proc; flatten; opt_expr; opt_clean; opt -nodffe -nosdff; fsm; opt;
        wreduce; peepopt; opt_clean; tee -o $OUT/$n.premul.stat stat; techmap -map $HERE/mulmap.v;
        synth -flatten -auto-top; async2sync; dffunmap; abc -lut 6; opt_clean -purge;
        write_blif $OUT/$n.raw.blif" > /dev/null 2>&1 || { echo "$n: yosys failed (see $OUT/$n.ylog)"; return; }
    python3 "$HERE/fix_blif.py" "$OUT/$n.raw.blif" "$OUT/$n.blif"
    rm -f "$OUT/$n.raw.blif"
}
i=0
for n in "$@"; do
    run_one "$n" &
    i=$((i + 1))
    [ $((i % ${JOBS:-4})) -eq 0 ] && wait
done
wait
