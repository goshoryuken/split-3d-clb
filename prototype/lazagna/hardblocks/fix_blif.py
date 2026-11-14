#!/usr/bin/env python3
"""Make a Yosys BLIF from synth_koios.sh fit the hard-block architecture.

1. Renames the fixed-size memory blocks of koios_hb.v to the VTR model names the
   architecture declares (dp_bram_* -> dual_port_ram, sp_bram_* -> single_port_ram).
2. Drops hard-block pins tied to a constant ($true/$false/$undef: zero-extended address
   and data pads, always-on write enables), so no constant generator has to be routed to
   them; VPR treats a missing pin as unconnected.
3. Puts unclocked latches on the clock named "clock", as synth_bench.sh does.
Prints a count of each hard block.

Usage: fix_blif.py IN.blif OUT.blif
"""
import collections
import re
import sys

RENAME = {"dp_bram_1024x20": "dual_port_ram", "dp_bram_2048x10": "dual_port_ram",
          "sp_bram_512x40": "single_port_ram", "sp_bram_1024x20": "single_port_ram",
          "sp_bram_2048x10": "single_port_ram"}
HARD = set(RENAME.values()) | {"two_mult_18x19", "one_mult_27x27"}


def main(src, dst):
    text = open(src).read().replace("\\\n", " ")
    out, counts = [], collections.Counter()
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] == ".subckt":
            model = RENAME.get(parts[1], parts[1])
            if model in HARD:
                counts[model] += 1
                parts = [".subckt", model] + [p for p in parts[2:]
                                              if not re.search(r"=\$(true|false|undef)$", p)]
                line = " ".join(parts)
        elif parts and parts[0] == ".latch" and len(parts) == 4:
            line = f"{parts[0]} {parts[1]} {parts[2]} re clock {parts[3]}"
        out.append(line)
    open(dst, "w").write("\n".join(out) + "\n")
    luts = sum(1 for l in out if l.startswith(".names"))
    print(f"{dst}: {luts} .names, {sum(1 for l in out if l.startswith('.latch'))} latches, "
          + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
