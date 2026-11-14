#!/usr/bin/env python3
"""Renames a routed CLB netlist so it can sit next to the RTL in one simulation.

The top module becomes clb_dut and every other module gets a prefix, because the
gate netlist reuses module names from the RTL with different contents.
Usage: rename_netlist.py <netlist> <output> <prefix>
"""
from pathlib import Path
import re
import sys

TOP = "logical_tile_clb_mode_clb_"


def main():
    source, output, prefix = sys.argv[1:]
    text = Path(source).read_text()
    names = set(re.findall(r"^\s*module\s+(\w+)", text, re.M))

    def rename(match):
        name = match.group(2)
        if name == TOP:
            return match.group(1) + "clb_dut"
        return match.group(1) + (prefix + name if name in names else name)
    Path(output).write_text(re.sub(r"^(\s*(?:module\s+)?)(\w+)", rename, text, flags=re.M))


if __name__ == "__main__":
    main()
