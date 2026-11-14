#!/usr/bin/env python3
"""Collect a CLB's modules into one synthesizable Verilog file.

OpenFPGA's netlist models muxes with tri-state pass gates, which synthesis
cannot map. Each mux primitive becomes the same function in AND-OR logic.
Standard cells then stand in for pass gates, so absolute area is high. Compare
blocks built this way with each other, not with a pass-gate FPGA.
"""
import argparse
from pathlib import Path
import re

TGATE = re.compile(r"TGATE\s+\w+\s*\(\s*\.in\(([^)]*)\),\s*\.sel\(([^)]*)\),\s*\.selb\(([^)]*)\),\s*\.out\(([^)]*)\)\);")
SIM_ONLY = re.compile(r"`ifdef\s+(ENABLE_TIMING|ENABLE_SIGNAL_INITIALIZATION|ENABLE_FORMAL_VERIFICATION)\b.*?`endif[^\n]*\n", re.S)
KEYWORDS = {"module", "input", "output", "wire", "reg", "assign", "always", "begin", "end", "if", "else"}


def synthesizable(body):
    """Rewrites one module, or returns None for the pass gate itself."""
    if re.match(r"\s*module\s+TGATE\b", body):
        return None
    if re.match(r"\s*module\s+crossing_buffer\b", body):
        return body.replace("assign out = in;", "BUFX4 buffer (.A(in), .Y(out));")
    if re.match(r"\s*module\s+crossing_driver\b", body):
        # Drives the other layer's whole net through the bond (add_crossing_buffers.py --direct).
        return body.replace("assign out = in;", "BUFX16 buffer (.A(in), .Y(out));")
    body = SIM_ONLY.sub("", body)
    body = body.replace("(in === 1'bz)? $random : ~in", "~in").replace("(in === 1'bz)? $random : in", "in")
    gates = TGATE.findall(body)
    if gates:
        outputs = {g[3] for g in gates}
        if len(outputs) != 1:
            raise SystemExit("mux primitive with several outputs")
        terms = " | ".join(f"({sel} & {data})" for data, sel, _, _ in gates)
        body = TGATE.sub("", body)
        body = body.rstrip() + f"\n\tassign {outputs.pop()} = {terms};\n"
    return body


def modules_in(text):
    for match in re.finditer(r"^\s*module\s+(\w+)", text, re.M):
        yield match.group(1), text[match.start():text.index("endmodule", match.start())]


def child_modules(body):
    for kind, _ in re.findall(r"^\s*(\w+)\s+(\w+)\s*\(", body, re.M):
        if kind not in KEYWORDS:
            yield kind


def collect(files, top):
    known = {}
    for path in files:
        known.update(modules_in(Path(path).read_text()))
    order, todo = [], [top]
    while todo:
        name = todo.pop()
        if name in order:
            continue
        if name not in known:
            raise SystemExit(f"no definition found for module {name}")
        order.append(name)
        todo += [c for c in child_modules(known[name]) if c != "TGATE" and c not in order]
    return [(name, known[name]) for name in order]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="OpenFPGA Verilog folder")
    parser.add_argument("--top", required=True)
    parser.add_argument("--extra", type=Path, nargs="*", default=[], help="more Verilog files to search")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    includes = re.findall(r'`include "([^"]*cell_library[^"]*)"', (args.source / "fabric_netlists.v").read_text())
    folders = ("lb", "routing", "sub_module")
    files = [f for folder in folders for f in sorted(args.source.glob(f"{folder}/*.v"))] + includes + args.extra
    parts = [synthesizable(body) for _, body in collect(files, args.top)]
    text = "\n".join(p + "endmodule\n" for p in parts if p is not None)
    if "TGATE" in text or "1'bz" in text or "$random" in text:
        raise SystemExit("simulation-only construct left in the output")
    args.output.write_text(text)
    print(f"{args.output}: {sum(p is not None for p in parts)} modules")


if __name__ == "__main__":
    main()
