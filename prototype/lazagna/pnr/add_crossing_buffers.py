#!/usr/bin/env python3
"""Gives each timing-critical signal between the layers a driver and a receiver.

In the plain split, a CLB input or FLE output reaches the other layer directly and
has to drive that layer's whole net. Here it leaves through a driver, crosses one
bond pad, and enters through a receiver that drives the local net. The new nets
between the layers are named x_<signal>. Global and config signals stay as they
are. Logic does not change.

With --direct the bond is used as a via: one strong driver (crossing_driver) on the
sending layer reaches the other layer's net through the pad, with no receiver. The
nets are still named x_<signal>, so they get bond pads.

With --tap FLE_FILE (implies --direct) an FLE output's crossing driver sits inside the FLE,
fed by the BLE output in parallel with the FLE's own output driver, instead of after it on
the layer's net. FLE_FILE is OpenFPGA's logical_tile_clb_mode_default__fle.v; the crossing
FLEs use a copy of it with one more output, fle_tap.
Usage: add_crossing_buffers.py <clb_split.v> <clb_crossings.csv> <output> [--direct] [--tap FLE_FILE]
"""
import csv
from pathlib import Path
import re
import sys

BUFFER = "module crossing_buffer(input in, output out);\nassign out = in;\nendmodule\n\n"
DRIVER = "module crossing_driver(input in, output out);\nassign out = in;\nendmodule\n\n"
CRITICAL = ("input pin", "FLE output")
FLE = "logical_tile_clb_mode_default__fle"


def tapped_fle(source):
    """The FLE module with a second output, fle_tap, driven by a crossing driver from the BLE output."""
    text = Path(source).read_text()
    start = re.search(rf"^module {FLE}\(", text, re.M).start()
    body = text[start:text.index("endmodule", start)]
    feed = re.search(r"direct_interc\s+direct_interc_0_\s*\(\s*\.in\(([^)]*)\)", body).group(1)
    head_end = body.index(");")
    body = body[:head_end] + ",\n\t\tfle_tap" + body[head_end:]
    body = body.replace(f"module {FLE}(", f"module {FLE}_tap(", 1)
    body = body.replace("output [0:0] fle_out;\n", "output [0:0] fle_out;\noutput [0:0] fle_tap;\n", 1)
    assert "fle_tap;" in body
    return body + f"\tcrossing_driver xd_tap (.in({feed}), .out(fle_tap));\nendmodule\n\n"


def edit_layer(text, crossings, layer, direct=False, tap=False):
    head = re.match(r"module (\w+)\(([^)]*)\);\n", text)
    ports = head.group(2).split(", ")
    body = text[head.end():text.index("endmodule")]
    added = []

    def declare(old, new):
        nonlocal body
        body, count = re.subn(rf"^{old};\n", f"{new};\n" if new else "", body, flags=re.M)
        assert count == 1, old

    for signal, source, sink, kind in crossings:
        bond = "x_" + signal[2:]
        if layer == source and tap and kind == "FLE output":
            ports.append(bond)
            added.append(f"output {bond};\n")
            body, count = re.subn(rf"^{FLE} (\w+ \(.*\.fle_out\(\{{{signal}\}}\))",
                                  rf"{FLE}_tap \1, .fle_tap({{{bond}}})", body, flags=re.M)
            assert count == 1, signal
            ports.remove(signal)
            declare(f"output {signal}", f"wire {signal}")
        elif layer == source:
            ports.append(bond)
            cell = "crossing_driver" if direct else "crossing_buffer"
            added += [f"output {bond};\n", f"{cell} xd_{signal[2:]} (.in({signal}), .out({bond}));\n"]
            if kind == "FLE output":
                ports.remove(signal)
                declare(f"output {signal}", f"wire {signal}")
        elif layer == sink:
            ports[ports.index(signal)] = bond
            declare(f"input {signal}", f"wire {signal}")
            added += [f"input {bond};\n", f"assign {signal} = {bond};\n" if direct else
                      f"crossing_buffer xr_{signal[2:]} (.in({bond}), .out({signal}));\n"]
    declarations = [line for line in added if line.startswith(("input ", "output "))]
    instances = [line for line in added if not line.startswith(("input ", "output "))]
    return f"module {head.group(1)}({', '.join(ports)});\n" + "".join(declarations) + body + "".join(instances) + "endmodule\n"


def edit_wrapper(text, crossings):
    for signal, source, sink, kind in crossings:
        bond = "x_" + signal[2:]
        text = text.replace(f"wire {signal};\n", f"wire {signal};\nwire {bond};\n", 1)
        for layer in (source, sink):
            start = text.index(f"clb_layer{layer} layer{layer} (")
            end = text.index(");", start)
            call = text[start:end]
            if layer == sink or kind == "FLE output":
                call = call.replace(f".{signal}({signal})", f".{bond}({bond})")
            else:
                call += f", .{bond}({bond})"
            text = text[:start] + call + text[end:]
    return text


def main():
    args = sys.argv[1:]
    fle_file = None
    if "--tap" in args:
        fle_file = args.pop(args.index("--tap") + 1)
        args.remove("--tap")
    direct = "--direct" in args or fle_file is not None
    source, table, output = [a for a in args if a != "--direct"]
    crossings = [(f"n_{r['signal']}_{r['bit']}", int(r["from_layer"]), int(r["to_layer"]), r["type"])
                 for r in csv.DictReader(open(table)) if r["type"] in CRITICAL]
    text = Path(source).read_text()
    pieces = re.split(r"(?=^module )", text, flags=re.M)
    out = [pieces[0], DRIVER if direct else BUFFER] + ([tapped_fle(fle_file)] if fle_file else [])
    for piece in pieces[1:]:
        layer = re.match(r"module clb_layer(\d)\(", piece)
        tail = piece[piece.index("endmodule") + len("endmodule\n"):]
        out.append((edit_layer(piece, crossings, int(layer.group(1)), direct, fle_file is not None) + tail) if layer
                   else edit_wrapper(piece, crossings))
    Path(output).write_text("".join(out))
    print(f"{output}: {len(crossings)} crossings {'tapped' if fle_file else 'direct' if direct else 'buffered'}")


if __name__ == "__main__":
    main()
