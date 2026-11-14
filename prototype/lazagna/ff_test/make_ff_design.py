#!/usr/bin/env python3
"""Write a flip-flop test of ten (or --count) LUTs as BLIF and a reference Verilog model.

All but the last two FLEs use their flip-flop and two use only their LUT, so one
CLB has to select both outputs. Each flip-flop reads its neighbour and itself, so
a wrong value or a missed clock on either layer changes later cycles.
"""
import argparse
from pathlib import Path
import random

NAME = "ff_ten"
INPUTS = ["a", "b", "c", "d", "e", "f"]


def fanin(i, count=10):
    flops = count - 2
    if i == 0:
        return ["a", "b", "c", "d", "e", "f"]
    if i < flops:
        return [f"q{i - 1}", f"q{i}", "b", "c", "d", "e"]
    if i == count - 1:
        return [f"c{count - 2}", "q3", "a", "b", "c", "d"]
    return [f"q{i - 1}", f"q{i - 5}", "a", "b", "c", "d"]


def outputs(count=10):
    return [f"q{i}" for i in range(count - 2)] + [f"c{count - 2}", f"c{count - 1}"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=10, help="LUTs in the design")
    args = parser.parse_args()
    count, flops = args.count, args.count - 2
    args.output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(2026)
    masks = [rng.getrandbits(64) for _ in range(count)]
    outs = outputs(count)

    blif = [f".model {NAME}", ".inputs clk " + " ".join(INPUTS), ".outputs " + " ".join(outs)]
    for i, mask in enumerate(masks):
        out = f"d{i}" if i < flops else outs[i]
        names = fanin(i, count)
        blif.append(".names " + " ".join(names) + " " + out)
        for row in range(64):
            if mask >> row & 1:
                blif.append("".join(str(row >> b & 1) for b in range(6)) + " 1")
        if i < flops:
            blif.append(f".latch d{i} q{i} re clk 0")
    blif.append(".end")
    (args.output / f"{NAME}.blif").write_text("\n".join(blif) + "\n")

    ports = ", ".join(["input clk"] + [f"input {n}" for n in INPUTS]
                      + [f"output reg {n} = 1'b0" for n in outs[:flops]] + [f"output {n}" for n in outs[flops:]])
    v = [f"// Reference for {NAME}: index bit 0 is the first LUT input.", f"module {NAME}({ports});"]
    for i, mask in enumerate(masks):
        names = fanin(i, count)
        index = "{" + ", ".join(reversed(names)) + "}"
        v.append(f"  localparam [63:0] LUT{i} = 64'h{mask:016x};")
        v.append(f"  assign {'d' + str(i) if i < flops else outs[i]} = LUT{i}[{index}];")
    v = v[:2] + [f"  wire d{i};" for i in range(flops)] + v[2:]
    for i in range(flops):
        v.append(f"  always @(posedge clk) q{i} <= d{i};")
    v.append("endmodule")
    (args.output / f"{NAME}.v").write_text("\n".join(v) + "\n")


if __name__ == "__main__":
    main()
