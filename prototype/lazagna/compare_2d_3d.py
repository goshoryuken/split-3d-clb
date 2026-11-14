#!/usr/bin/env python3
"""Compare critical path delay of a 2D CLB against the two-layer CLB with VPR.

Both fabrics use a CLB-only grid of the same size, so a design makes the same
number of tile hops. wire_scale shrinks the wire driver delays of the 3D fabric
to model its smaller footprint; 1.0 gives 3D no benefit from it. crossing_ps is
the added delay of one layer crossing. Delays come from the architecture files,
not from a process, so compare ratios only.
"""
import argparse
import concurrent.futures
import csv
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relayer_net  # noqa: E402
import hardblocks  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "vtr_flow/benchmarks/blif/6"
# Planar delay of each switch, and the planar switch each inter-layer switch adds a crossing to.
PLANAR = {"L4_driver": 185.8258, "L16_driver": 379.2906}
INTER_LAYER = {"L4_inter_layer_driver": "L4_driver", "L16_inter_layer_driver": "L16_driver"}
IPIN_PLANAR = 106.0361


def make_arch(path, grid, scale, crossing_ps, clb_crossing_ps=None, routing=1.0):
    xml = path.read_text()
    xml, count = re.subn(r'\s*<col type="(complex_dsp|spram)"[^>]*/>', "", xml)
    assert count, "no hard block columns found"
    xml, count = re.subn(r'(<fixed_layout[^>]*?)width="\d+" height="\d+"',
                         rf'\1width="{grid}" height="{grid}"', xml, count=1)
    assert count == 1
    # routing scales every routing switch and connection block and the crossings, not the CLB.
    crossing_ps *= routing
    delays = {name: tdel * scale * routing for name, tdel in PLANAR.items()}
    delays.update({name: PLANAR[base] * scale * routing + crossing_ps for name, base in INTER_LAYER.items()})
    delays["ipin_cblock"] = IPIN_PLANAR * routing
    delays["ipin_inter_layer_cblock"] = IPIN_PLANAR * routing + crossing_ps
    for name, tdel in delays.items():
        xml, count = re.subn(rf'(name="{name}"[^>]*?Tdel=")[^"]+', rf'\g<1>{tdel}e-12', xml)
        assert count == 1, name
    inside = crossing_ps if clb_crossing_ps is None else clb_crossing_ps * routing
    return re.sub(r'layer_crossing_delay="[^"]+"', f'layer_crossing_delay="{inside}e-12"', xml)


def split_inputs(xml, fles=10, parts=2):
    """Replace the input port with one port per layer (parts of them, equal sizes)."""
    size = 4 * fles // parts
    ports = [f"I{i}" for i in range(parts)]
    xml, count = re.subn(rf'<input name="I" num_pins="{4 * fles}" equivalent="full"/>',
                         "\n".join(f'<input name="{p}" num_pins="{size}" equivalent="full"/>' for p in ports), xml)
    assert count == 2

    def pins(match):
        low, high = int(match.group(1)), int(match.group(2))
        assert low // size == high // size, "a pin range straddles two layers"
        return f"clb.I{low // size}[{low % size}:{high % size}]"
    xml = re.sub(r"clb\.I\[(\d+):(\d+)\]", pins, xml)
    every = " ".join(f"clb.{p}" for p in ports)
    xml, count = re.subn(r'clb\.I fle', f'{every} fle', xml)
    assert count >= 1
    xml, count = re.subn(r'in_port="clb\.I"', f'in_port="{every}"', xml)
    assert count == 1
    return xml


def set_span(xml, span):
    """Make the split CLB span this many layers, its FLEs and pins spread evenly over them."""
    tile = re.search(r'<tile name="clb".*?</tile>', xml, re.S).group(0)
    assert 'layer_span="2"' in tile
    return xml.replace(tile, tile.replace('layer_span="2"', f'layer_span="{span}"'))


def sparse_crossbars(xml, fraction=0.5):
    """Depopulate every CLB crossbar: each LUT input position reaches only part of the sources.

    Each crossbar's input pins and FLE outputs are cut into six groups; input position k of
    every FLE reads groups k to k+m-1 (mod 6), m = 6 * fraction, so each source reaches m of
    the six inputs of every FLE, like the 50% crossbar in VTR's 7 nm COFFE architecture. LUT
    inputs are interchangeable, so any FLE can still read any source. Pins stay interchangeable
    only within their group, so each group becomes its own equivalent input port.
    """
    keep = round(6 * fraction)
    tile = re.search(r'<tile name="clb".*?</tile>', xml, re.S).group(0)
    sizes = {name: int(n) for name, n in re.findall(r'<input name="(I\d?)" num_pins="(\d+)"', tile)}

    def cut(n):
        """Six contiguous (low, high) ranges covering 0..n-1."""
        size, extra = divmod(n, 6)
        out, low = [], 0
        for g in range(6):
            length = size + (g < extra)
            out.append((low, low + length - 1))
            low += length
        return out
    ranges = {port: cut(n) for port, n in sizes.items()}

    def group_ports(match):
        name, n = match.group(1), int(match.group(2))
        return "\n".join(f'<input name="{name}g{g}" num_pins="{high - low + 1}" equivalent="full"/>'
                         for g, (low, high) in enumerate(ranges[name]))

    def regroup_pins(match):
        port, low, high = match.group(1), int(match.group(2)), int(match.group(3))
        tokens = []
        for g, (a, b) in enumerate(ranges[port]):
            lo, hi = max(low, a), min(high, b)
            if lo <= hi:
                tokens.append(f"clb.{port}g{g}[{lo - a}:{hi - a}]")
        return " ".join(tokens)
    pb = re.search(r'<pb_type name="clb">.*?<pb_type name="fle"', xml, re.S).group(0)
    new_tile = re.sub(r'<input name="(I\d?)" num_pins="(\d+)" equivalent="full"/>', group_ports, tile)
    new_tile = re.sub(r"clb\.(I\d?)\[(\d+):(\d+)\]", regroup_pins, new_tile)
    new_pb = re.sub(r'<input name="(I\d?)" num_pins="(\d+)" equivalent="full"/>', group_ports, pb)
    xml = xml.replace(tile, new_tile).replace(pb, new_pb)

    def rewrite(match):
        block, name = match.group(0), match.group(1)
        head = re.search(r'<complete name="[^"]+" input="([^"]+)" output="([^"]+)"([^>]*)>', block)
        inputs, output, rest = head.group(1).split(), head.group(2), head.group(3)
        pin_ports = [i.split(".")[1] for i in inputs if i.startswith("clb.I")]
        assert len(pin_ports) == 1, "a sparse crossbar reads one input port"
        fle_port = next(i for i in inputs if i.startswith("fle["))
        delays = {port: d for d, port in re.findall(r'max="([^"]+)" in_port="([^"]+)"', block)}
        pin_delay = next(d for port, d in delays.items() if port.startswith("clb.I"))
        fle_delay = next(d for port, d in delays.items() if port.startswith("fle["))
        hi, lo = map(int, re.match(r"fle\[(\d+):(\d+)\]", fle_port).groups())
        fle_groups = [(lo + a, lo + b) for a, b in cut(hi - lo + 1)]
        sink_hi, sink_lo = map(int, re.match(r"fle\[(\d+):(\d+)\]", output).groups())
        parts = []
        for k in range(6):
            chosen = [(k + j) % 6 for j in range(keep)]
            pin_tokens = [f"clb.{pin_ports[0]}g{g}" for g in chosen]
            fle_tokens = [f"fle[{fle_groups[g][1]}:{fle_groups[g][0]}].out" for g in chosen if fle_groups[g][0] <= fle_groups[g][1]]
            sinks = f"fle[{sink_hi}:{sink_lo}].in[{k}:{k}]"
            parts.append(f'<complete name="{name}_in{k}" input="{" ".join(pin_tokens + fle_tokens)}" output="{sinks}"{rest}>\n'
                         f'          <delay_constant max="{pin_delay}" in_port="{" ".join(pin_tokens)}" out_port="{sinks}"/>\n'
                         f'          <delay_constant max="{fle_delay}" in_port="{" ".join(fle_tokens)}" out_port="{sinks}"/>\n'
                         '        </complete>')
        return "\n        ".join(parts)
    xml, count = re.subn(r'<complete name="(crossbar\d?)".*?</complete>', rewrite, xml, flags=re.S)
    assert count, "no crossbar to depopulate"
    return xml


def stretch_wires(xml, l4, l16):
    """Lengthen wires in tiles, keeping their delay.

    A half-footprint tile is about 0.71 as wide, so a wire of the same physical
    length, and so the same delay, crosses about 1.41 times as many tiles.
    """
    def segment(name, length, sb, cb):
        nonlocal xml
        block = re.search(rf'<segment name="{name}".*?</segment>', xml, re.S).group(0)
        new = re.sub(r'length="\d+"', f'length="{length}"', block, count=1)
        new = re.sub(r'<sb type="pattern">[^<]*</sb>', f'<sb type="pattern">{sb}</sb>', new)
        new = re.sub(r'<cb type="pattern">[^<]*</cb>', f'<cb type="pattern">{cb}</cb>', new)
        xml = xml.replace(block, new)
    segment("L4", l4, " ".join(["1"] * (l4 + 1)), " ".join(["1"] * l4))
    # Long wires keep their switch block every 4 tiles and still have no pin connections.
    segment("L16", l16, " ".join("1" if i % 4 == 0 or i == l16 else "0" for i in range(l16 + 1)),
            " ".join(["0"] * l16))
    return xml


def grid_for(bench, layers=1, fles=10):
    text = (BENCH / f"{bench}.blif").read_text().replace("\\\n", " ")
    luts = sum(line.startswith(".names") for line in text.splitlines())
    pads = sum(len(line.split()) - 1 for line in text.splitlines()
               if line.startswith((".inputs", ".outputs")))
    logic = math.ceil(math.sqrt(luts / fles / 0.7 / layers))
    # The 2D fabric has its pads on one layer, at 8 per perimeter tile.
    edge = math.ceil(pads / 8 / 4 / 0.9 / layers)
    return max(logic, edge) + 2, luts


def stack_clbs(xml):
    """Turns the two-layer CLB into a whole flat CLB on each layer, as stock LaZagna does."""
    xml = xml.replace(' layer_span="2"', "").replace(' instance_layer_offsets="0 0 0 0 0 1 1 1 1 1"', "")
    xml = re.sub(r' layer_crossing_delay="[^"]+"', "", xml)

    def merge_sides(match):
        block = match.group(0)
        pins = {}
        for side, text in re.findall(r'<loc side="(\w+)" pin_layer="\d" layer_offset="1">([^<]*)</loc>', block):
            pins[side] = f"{pins.get(side, '')} {text}".strip()
        for side, text in pins.items():
            block = re.sub(rf'<loc side="{side}" pin_layer="1" layer_offset="1">[^<]*</loc>\s*', "", block)
            block = re.sub(rf'<loc side="{side}" pin_layer="0" layer_offset="1">[^<]*</loc>',
                           f'<loc side="{side}" layer_offset="1">{text}</loc>', block)
        return block
    xml = re.sub(r"<pinlocations.*?</pinlocations>", merge_sides, xml, flags=re.S)
    xml, count = re.subn(r'<fill type="EMPTY" priority="10"/>', '<fill type="clb" priority="10"/>', xml)
    assert count == 1
    assert 'pin_layer="' not in xml
    return xml


def local_inputs(xml, fles=10, parts=2):
    """Feeds each layer's FLEs from that layer's input pins only.

    Input pins then never cross inside the CLB, which removes 40 crossings and
    shrinks each input mux from 50 to 30 inputs. Feedback still reaches every FLE.
    """
    xml = split_inputs(xml, fles, parts)
    block = re.search(r'<complete name="crossbar".*?</complete>', xml, re.S).group(0)
    crossing = re.search(r'layer_crossing_delay="[^"]+"', block)
    crossing = crossing.group(0) if crossing else ""
    every_pin = " ".join(f"clb.I{i}" for i in range(parts))
    pins = re.search(rf'max="([^"]+)" in_port="{re.escape(every_pin)}"', block).group(1)
    every = f"fle[{fles - 1}:0].out"
    feedback = re.search(rf'max="([^"]+)" in_port="{re.escape(every)}"', block).group(1)
    blocks = []
    for layer in range(parts):
        sinks = f"fle[{(layer + 1) * fles // parts - 1}:{layer * fles // parts}].in"
        blocks.append(f'<complete name="crossbar{layer}" input="clb.I{layer} {every}" output="{sinks}" {crossing}>\n'
                      f'          <delay_constant max="{pins}" in_port="clb.I{layer}" out_port="{sinks}"/>\n'
                      f'          <delay_constant max="{feedback}" in_port="{every}" out_port="{sinks}"/>\n'
                      '        </complete>')
    return xml.replace(block, "\n        ".join(blocks))


def apply_delays(xml, d):
    """Puts one fabric's transistor-level delays (spice/make_spice.py, in ps) into its architecture.

    Every routing switch's Tdel (mux, driver, wire and loads), the connection block, both
    crossbar paths of every crossbar, the LUT inputs, the FLE output mux and the layer
    crossings. Flip-flop timing keeps the template's.
    """
    cross = d.get("route_crossing", 0.0)
    tdel = {"L4_driver": d["l4"], "L16_driver": d["l16"], "L4_inter_layer_driver": d["l4"] + cross,
            "L16_inter_layer_driver": d["l16"] + cross, "ipin_cblock": d["cb"],
            "ipin_inter_layer_cblock": d["cb"] + cross, "3D_SB_switch": d["l4"] + cross}
    for name, value in tdel.items():
        xml, count = re.subn(rf'(name="{name}"[^>]*?Tdel=")[^"]+', rf'\g<1>{value}e-12', xml)
        assert count == 1, name

    def crossbar(match):
        block = match.group(0)
        block, pins = re.subn(r'max="[^"]+"( in_port="clb\.I)', rf'max="{d["xbar_pin"]}e-12"\1', block)
        block, feedback = re.subn(r'max="[^"]+"( in_port="fle\[)', rf'max="{d["xbar_fb"]}e-12"\1', block)
        assert pins and feedback, "crossbar delays not found"
        return block
    xml, count = re.subn(r'<complete name="crossbar\d*".*?</complete>', crossbar, xml, flags=re.S)
    assert count, "no crossbar"
    if "clb_crossing" in d:
        xml = re.sub(r'layer_crossing_delay="[^"]+"', f'layer_crossing_delay="{d["clb_crossing"]}e-12"', xml)
    lut = "\n".join(f"                {d[f'lut{k}']}e-12" for k in range(6))
    xml, count = re.subn(r'(<delay_matrix type="max" in_port="lut6.in" out_port="lut6.out">).*?(\s*</delay_matrix>)',
                         rf"\1\n{lut}\2", xml, flags=re.S)
    assert count == 1, "LUT delays"
    for port in ("lut6.out", "ff.Q"):
        xml, count = re.subn(rf'max="[^"]+"( in_port="{re.escape(port)}" out_port="ble6.out")',
                             rf'max="{d["ble"]}e-12"\1', xml)
        assert count == 1, port
    if "ff_clk_q" in d:
        # The kit's flip-flop (7 nm sets); the sky130 sets keep the template's.
        xml, setup = re.subn(r'(<T_setup value=")[^"]+(" port="ff\.D")', rf'\g<1>{d["ff_setup"]}e-12\2', xml)
        xml, clk_q = re.subn(r'(<T_clock_to_Q max=")[^"]+(" port="ff\.Q")', rf'\g<1>{d["ff_clk_q"]}e-12\2', xml)
        assert setup == clk_q == 1, "flip-flop timing"
    return xml


def scale_crossbar(xml, pins, feedback):
    """Speeds up the crossbar by the ratios measured in the half and 2D layouts."""
    for port, delay, scale in (("clb.I", 95, pins), ("fle[9:0].out", 75, feedback)):
        old = f'max="{delay}e-12" in_port="{port}"'
        assert old in xml, old
        xml = xml.replace(old, f'max="{delay * scale}e-12" in_port="{port}"')
    return xml


VERTICAL_SB = """        <switchblock name="vertical" type="unidir">
            <switchblock_location type="EVERYWHERE"/>
            <switchfuncs>
{funcs}
            </switchfuncs>
{wireconns}
        </switchblock>
"""
VERTICAL_WIRECONNS = {
    # Every wire that could go straight on can also turn onto the layer above or below, as in VTR's example.
    "dense": """            <wireconn num_conns="3*to" from_type="L16" from_switchpoint="0,12,8,4" to_type="L16" to_switchpoint="0"/>
            <wireconn num_conns="11*to" from_type="L4" from_switchpoint="0,3,2,1" to_type="L16" to_switchpoint="0"/>
            <wireconn num_conns="2*to" from_order="shuffled">
                <from type="L16" switchpoint="0,12,8,4"/>
                <from type="L4" switchpoint="0"/>
                <to type="L4" switchpoint="0"/>
            </wireconn>""",
    # Only short wires, one connection each, at their ends: far fewer vertical links per switch block.
    "sparse": """            <wireconn num_conns="1*to" from_type="L4" from_switchpoint="0" to_type="L4" to_switchpoint="0"/>""",
}


def add_links(xml, kind, delay_ps):
    """Add direct links from a CLB's outputs to a neighbouring CLB's inputs, skipping the routing.

    kind "vertical": to the CLB directly above and below (layer_offset); a split CLB
    links its top layer to the next CLB's bottom layer and back, two layers apart.
    kind "horizontal": to the CLB east and west, as a same-cost 2D control.
    Each CLB output drives one input of each neighbour; the links cost one input mux
    and a crossing (delay_ps) and are routing shortcuts, never placement macros.
    """
    tile = re.search(r'<tile name="clb".*?</tile>', xml, re.S).group(0)
    outputs = int(re.search(r'<output name="O" num_pins="(\d+)"', tile).group(1))
    ports = {name: int(n) for name, n in re.findall(r'<input name="(I\d?)" num_pins="(\d+)"', tile)}
    span = 2 if 'layer_span="2"' in tile else 1
    links = []
    if kind == "vertical" and span == 2:
        half = outputs // 2
        low, high = ("I0", "I1") if "I0" in ports else ("I", "I")
        start = 0 if low != high else ports["I"] // 2
        # Top layer outputs to the bottom-layer inputs of the CLB above, and back down.
        links.append(("up", f"clb.O[{outputs - 1}:{half}]", f"clb.{low}[{half - 1}:0]", 0, 2))
        links.append(("down", f"clb.O[{half - 1}:0]", f"clb.{high}[{start + half - 1}:{start}]", 0, -2))
    elif kind == "vertical":
        links.append(("up", f"clb.O[{outputs - 1}:0]", f"clb.I[{outputs - 1}:0]", 0, 1))
        links.append(("down", f"clb.O[{outputs - 1}:0]", f"clb.I[{2 * outputs - 1}:{outputs}]", 0, -1))
    elif kind == "horizontal" and "I0" in ports:
        # Layer-local split CLB: east links land on the neighbour's bottom-layer inputs, west on its top.
        links.append(("east", f"clb.O[{outputs - 1}:0]", f"clb.I0[{outputs - 1}:0]", 1, 0))
        links.append(("west", f"clb.O[{outputs - 1}:0]", f"clb.I1[{outputs - 1}:0]", -1, 0))
    elif kind == "horizontal":
        links.append(("east", f"clb.O[{outputs - 1}:0]", f"clb.I[{outputs - 1}:0]", 1, 0))
        links.append(("west", f"clb.O[{outputs - 1}:0]", f"clb.I[{2 * outputs - 1}:{outputs}]", -1, 0))
    else:
        raise ValueError(kind)
    switch = (f'    <switch type="mux" name="direct_link" R="0.0" Cin="0.0" Cout="0.0" Tdel="{delay_ps}e-12" '
              'mux_trans_size="1" buf_size="1"/>\n  </switchlist>')
    xml, count = re.subn(r"\s*</switchlist>", "\n" + switch, xml, count=1)
    assert count == 1
    lines = [f'    <direct name="{name}" from_pin="{src}" to_pin="{dst}" x_offset="{dx}" y_offset="0" z_offset="0" '
             f'layer_offset="{dz}" placement_macro="false" switch_name="direct_link"/>' for name, src, dst, dx, dz in links]
    block = "  <directlist>\n" + "\n".join(lines) + "\n  </directlist>\n"
    assert "<directlist>" not in xml and xml.count("</architecture>") == 1
    return xml.replace("</architecture>", block + "</architecture>")


def own_layer_inputs(xml):
    """CLB input pins reach only their own layer's tracks; outputs still reach both layers.

    Connection blocks then select from one layer's tracks instead of two, about
    halving their size, and a signal changes layers at its source pin instead.
    """
    def split(match):
        side, layer, pins = match.group(1), match.group(2), match.group(3).split()
        outs = [p for p in pins if not p.startswith("clb.I")]
        ins = [p for p in pins if p.startswith("clb.I")]
        lines = []
        if outs:
            lines.append(f'<loc side="{side}" pin_layer="{layer}" layer_offset="1">{" ".join(outs)}</loc>')
        if ins:
            lines.append(f'<loc side="{side}" pin_layer="{layer}">{" ".join(ins)}</loc>')
        return "\n          ".join(lines)
    tile = re.search(r'<tile name="clb".*?</tile>', xml, re.S).group(0)
    new, count = re.subn(r'<loc side="(\w+)" pin_layer="(\d)" layer_offset="1">([^<]*)</loc>', split, tile)
    assert count, "no pin_layer locations in the CLB tile"
    return xml.replace(tile, new)


def add_layers(xml, total, span=2):
    """Repeat the two-layer grid up to total layers.

    Split CLBs repeat as pairs (a CLB on layers 0-1, another on 2-3); stacked CLBs
    get one more CLB layer each. Only switch blocks that cross layers connect the
    layers beyond the first two, so use this with custom switch blocks.
    """
    layers = [re.search(rf'<layer die="{d}">.*?</layer>', xml, re.S).group(0) for d in (0, 1)]
    if span == total:
        # One CLB spans every layer: the layers above the first hold only its reserved cells.
        extra = [layers[1].replace('die="1"', f'die="{d}"') for d in range(2, total)]
    else:
        extra = [layers[d % 2].replace(f'die="{d % 2}"', f'die="{d}"') for d in range(2, total)]
    return xml.replace(layers[1], "\n".join([layers[1]] + extra))


def custom_switchblocks(xml, vertical=None):
    """Replace the built-in Wilton switch block with VTR-style custom ones.

    vertical is None for planar switch blocks only, or "dense" or "sparse" for
    switch blocks whose wires can also turn onto the layer above or below.
    """
    xml, count = re.subn(r'<switch_block type="wilton" fs="3"/>', '<switch_block type="custom"/>', xml)
    assert count == 1
    block = ""
    if vertical:
        funcs = "\n".join(f'                <func type="{side}{way}" formula="t"/>' for side in "ltrb" for way in "au")
        block = VERTICAL_SB.format(funcs=funcs, wireconns=VERTICAL_WIRECONNS[vertical])
    text = (Path(__file__).resolve().parent / "switchblocks.xml").read_text().replace("VERTICAL\n", block)
    # The template's switchpoints assume L4 and L16 wires; fit them to the wires' actual lengths.
    l4 = int(re.search(r'<segment name="L4"[^>]*length="(\d+)"', xml).group(1))
    l16 = int(re.search(r'<segment name="L16"[^>]*length="(\d+)"', xml).group(1))
    short_up = ",".join(str(i) for i in range(l4))
    short_down = ",".join(["0"] + [str(i) for i in range(l4 - 1, 0, -1)])
    long_points = ",".join(["0"] + [str(i) for i in range(4 * ((l16 - 1) // 4), 0, -4)])
    text = text.replace('"0,1,2,3"', f'"{short_up}"').replace('"0,3,2,1"', f'"{short_down}"').replace('"0,12,8,4"', f'"{long_points}"')
    assert xml.count("</architecture>") == 1
    return xml.replace("</architecture>", text + "</architecture>")


def resize_clb(xml, n, delay_scale=1.0):
    """Gives the CLB n FLEs and 4n inputs, the 10-FLE CLB's ratio.

    Pins spread evenly over the four sides, and over both layers when the CLB is
    split. delay_scale multiplies both crossbar delays, for the wider muxes of a
    bigger crossbar.
    """
    inputs = 4 * n
    xml, count = re.subn(r'<input name="I" num_pins="40" equivalent="full"/>',
                         f'<input name="I" num_pins="{inputs}" equivalent="full"/>', xml)
    assert count == 2
    xml, count = re.subn(r'<output name="O" num_pins="10" equivalent="none"/>',
                         f'<output name="O" num_pins="{n}" equivalent="none"/>', xml)
    assert count == 2
    xml, count = re.subn(r'(<pb_type name="fle" num_pb=")10"', rf'\g<1>{n}"', xml)
    assert count == 1
    tile_span = re.search(r'<tile name="clb"[^>]*layer_span="(\d+)"', xml)
    span = int(tile_span.group(1)) if tile_span else 1
    offsets = " ".join(str(i * span // n) for i in range(n))
    xml = re.sub(r'instance_layer_offsets="[^"]+"', f'instance_layer_offsets="{offsets}"', xml)
    xml = xml.replace("fle[9:0]", f"fle[{n - 1}:0]")
    block = re.search(r'<complete name="crossbar".*?</complete>', xml, re.S).group(0)
    xml = xml.replace(block, re.sub(r'max="([\d.]+)e-12"',
                                    lambda m: f'max="{float(m.group(1)) * delay_scale}e-12"', block))
    tile = re.search(r'<tile name="clb".*?</tile>', xml, re.S).group(0)
    old = re.search(r'<pinlocations pattern="custom">.*?</pinlocations>', tile, re.S).group(0)
    reach = ' layer_offset="1"' if 'layer_offset="1"' in old else ""
    layers = span

    def chunks(low, high):
        """Splits low..high-1 into four runs, longer runs first, as the 10-FLE CLB does."""
        size, extra = divmod(high - low, 4)
        runs = []
        for side in range(4):
            length = size + (side < extra)
            runs.append((low, low + length - 1) if length else None)
            low += length
        return runs

    lines = ['<pinlocations pattern="custom">']
    for layer in range(layers):
        ins = chunks(layer * inputs // layers, (layer + 1) * inputs // layers)
        outs = chunks(layer * n // layers, (layer + 1) * n // layers)
        for side, name in enumerate(("left", "top", "right", "bottom")):
            pins = ["clb.clk"] if layer == 0 and side == 0 else []
            pins += [f"clb.{port}[{run[0]}:{run[1]}]" for port, run in (("O", outs[side]), ("I", ins[side])) if run]
            where = f' pin_layer="{layer}"' if layers > 1 else ""
            lines.append(f'          <loc side="{name}"{where}{reach}>{" ".join(pins)}</loc>')
    lines.append("        </pinlocations>")
    return xml.replace(tile, tile.replace(old, "\n".join(lines)))


def fabric_xml(label, source, scale, crossing, inside, fles, growth, grid, hard="none"):
    """The architecture of one fabric: the base file with every chosen rewrite applied."""
    xml = make_arch(source, grid, scale if label == "3d" else SCALE_2D, crossing, inside, ROUTING)
    if label == "3d" and STACKED:
        xml = stack_clbs(xml)
    if label == "3d" and not STACKED and SPAN != 2:
        xml = set_span(xml, SPAN)
    if label == "3d" and LAYERS != 2:
        xml = add_layers(xml, LAYERS, 1 if STACKED else SPAN)
    if label == "3d" and WIRE_SPANS:
        xml = stretch_wires(xml, *WIRE_SPANS)
    if label == "2d" and WIRE_SPANS_2D:
        xml = stretch_wires(xml, *WIRE_SPANS_2D)
    if label == "3d" and CROSSBAR_SCALE:
        xml = scale_crossbar(xml, *CROSSBAR_SCALE)
    if label == "2d" and CROSSBAR_SCALE_2D:
        xml = scale_crossbar(xml, *CROSSBAR_SCALE_2D)
    if fles != 10 or growth != 1.0:
        assert not RELAYER, "rearranging FLEs supports the 10-FLE CLB only"
        xml = resize_clb(xml, fles, growth)
    if LOCAL_INPUTS and (label == "3d" or LOCAL_2D):
        xml = local_inputs(xml, fles, SPAN if label == "3d" else 2)
    if label == "3d" and OWN_LAYER_INPUTS:
        xml = own_layer_inputs(xml)
    if (SPARSE if label == "3d" else SPARSE_2D) < 1.0:
        xml = sparse_crossbars(xml, SPARSE if label == "3d" else SPARSE_2D)
    xml = split_inputs(xml) if label == "3d" and RELAYER else xml
    if SWITCHBLOCKS == "custom":
        xml = custom_switchblocks(xml, VERTICAL if label == "3d" else None)
    links = LINKS_3D if label == "3d" else LINKS_2D
    assert not (links and (SPARSE if label == "3d" else SPARSE_2D) < 1.0), "links need the full crossbar's input port"
    if links:
        xml = add_links(xml, links, LINK_PS)
    if DELAYS:
        xml = apply_delays(xml, DELAYS[label])
    if hard != "none":
        hard_scale = HARD_SCALE if HARD_SCALE else (hardblocks.delay_scale(DELAYS["2d"]) if DELAYS else 1.0)
        if HARD_CROSSING >= 0:
            crossing_s = HARD_CROSSING * 1e-12
        elif DELAYS and "clb_crossing" in DELAYS["3d"]:
            crossing_s = DELAYS["3d"]["clb_crossing"] * 1e-12
        else:
            crossing_s = (crossing if inside is None else inside) * ROUTING * 1e-12
        own = OWN_LAYER_INPUTS and label == "3d" and not STACKED
        xml = hardblocks.apply(xml, hard, label, STACKED, own, grid, hard_scale, crossing_s,
                               own and HARD_INPUTS == "own")
    return xml


def run(job):
    label, source, width, scale, crossing, bench, seed, out = job[:8]
    hard = job[8] if len(job) > 8 else "none"
    if DELAYS:
        crossing = DELAYS[label].get("route_crossing", 0.0)
    inside = None if CLB_CROSSING < 0 else CLB_CROSSING
    fles, growth = (N3D, GROWTH_3D) if label == "3d" else (N2D, GROWTH_2D)
    clb_layers = (LAYERS if STACKED else LAYERS // SPAN) if label == "3d" else 1
    extra = {}
    if hard != "none":
        spec = hardblocks.layout_spec(label, STACKED, hard)
        grid, luts, rams, dsps = hardblocks.grid_for(BENCH / f"{bench}.blif", spec, fles)
        cap = hardblocks.tiles(grid, spec, fles)
        extra = {"hard": hard if label == "3d" else "2d", "layers": len(spec), "rams": rams, "dsps": dsps,
                 "lut_cap": cap[0], "ram_cap": cap[1], "dsp_cap": cap[2], "die_cells": hardblocks.die_cells(grid, spec)}
        tag = f"_hb{hard if label == '3d' else ''}"
    else:
        grid, luts = grid_for(bench, clb_layers, fles)
        tag = ""
    tag += "" if CLOCK == "route" else f"_clk{CLOCK}"
    work = out / f"{label}_n{fles}_w{f'x{RELAX}' if RELAX else width}_s{scale}_c{crossing}_{bench}_{seed}{tag}"
    work.mkdir(parents=True, exist_ok=True)
    arch = work / "arch.xml"
    log_file = work / "run.log"
    xml = fabric_xml(label, source, scale, crossing, inside, fles, growth, grid, hard)
    if RELAX:
        # VTR's usual method: find the fewest tracks that route, then route with RELAX times as many.
        width_file = work / "width.txt"
        if not (arch.exists() and arch.read_text() == xml and width_file.exists()):
            arch.write_text(xml)
            log_file.unlink(missing_ok=True)
            search = [str(VPR), str(arch), str(BENCH / f"{bench}.blif"), "--clock_modeling", CLOCK, "--disp", "off",
                      "--seed", str(seed), "--place_bounding_box_mode", "cube_bb"] + EXTRA
            found = subprocess.run(search, cwd=work, text=True, capture_output=True, timeout=TIMEOUT)
            (work / "min_width.log").write_text(found.stdout + found.stderr)
            least = re.search(r"Best routing used a channel width factor of (\d+)", found.stdout + found.stderr)
            if not least:
                return result_row(label, 0, scale, crossing, bench, luts, grid, seed, fles, 1, "", extra)
            width_file.write_text(f"{2 * math.ceil(RELAX * int(least.group(1)) / 2)} {least.group(1)}\n")
        width = int(width_file.read_text().split()[0])
    if arch.exists() and arch.read_text() == xml and log_file.exists():
        # The same run finished before, in this or an earlier sweep into the same folder.
        log = log_file.read_text()
        if "Final critical path delay" in log:
            return result_row(label, width, scale, crossing, bench, luts, grid, seed, fles, 0, log, extra)
    arch.write_text(xml)
    command = [str(VPR), str(arch), str(BENCH / f"{bench}.blif"), "--route_chan_width", str(width),
               "--clock_modeling", CLOCK, "--disp", "off", "--seed", str(seed),
               "--place_bounding_box_mode", "cube_bb"] + EXTRA
    if label == "3d" and RELAYER:
        packed = subprocess.run(command + ["--pack"], cwd=work, text=True, capture_output=True, timeout=7200)
        (work / "pack.log").write_text(packed.stdout + packed.stderr)
        relayer_net.rearrange(work / f"{bench}.net", work / f"{bench}.net")
        command += ["--place", "--route", "--analysis"]
    result = subprocess.run(command, cwd=work, text=True, capture_output=True, timeout=TIMEOUT)
    log = result.stdout + result.stderr
    log_file.write_text(log)
    if SLIM:
        # Keep what the summary and timing checks read; packing, placement and routing files are large.
        for path in work.iterdir():
            if path.name not in ("arch.xml", "run.log", "report_timing.setup.rpt", "width.txt", "min_width.log") and path.is_file():
                path.unlink()
    return result_row(label, width, scale, crossing, bench, luts, grid, seed, fles, result.returncode, log, extra)


def result_row(label, width, scale, crossing, bench, luts, grid, seed, fles, returncode, log, extra=None):
    delay = re.search(r"Final critical path delay \(least slack\): ([\d.]+) ns", log)
    routed = returncode == 0 and delay is not None
    wire = re.search(r"Total wirelength: (\d+)", log)
    row = {"fabric": label, "fles": fles, "chan_width": width, "wire_scale": scale, "crossing_ps": crossing,
           "bench": bench, "luts": luts,
           "grid": grid, "seed": seed, "routed": routed, "cpd_ns": delay.group(1) if delay else "",
           "wirelength": wire.group(1) if wire else ""}
    row.update(extra or {})
    return row


def main():
    global DELAYS
    global BENCH, VPR, CLB_CROSSING, EXTRA, RELAYER, WIRE_SPANS, CROSSBAR_SCALE, STACKED, LOCAL_INPUTS, LOCAL_2D, SCALE_2D
    global N2D, N3D, GROWTH_2D, GROWTH_3D, WIRE_SPANS_2D, TIMEOUT, CROSSBAR_SCALE_2D, SLIM, SWITCHBLOCKS, VERTICAL, LAYERS
    global RELAX, ROUTING, OWN_LAYER_INPUTS, LINKS_2D, LINKS_3D, LINK_PS, SPAN, SPARSE, SPARSE_2D, HARD, HARD_SCALE
    global HARD_CROSSING, CLOCK, HARD_INPUTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vpr", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--benches", nargs="+",
                        default="alu4 apex2 apex4 ex5p misex3 seq spla pdc tseng dsip des bigkey "
                                "diffeq elliptic frisc s298".split())
    parser.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--w2d", type=int, default=100)
    parser.add_argument("--w3d", type=int, default=50)
    parser.add_argument("--scales", nargs="+", type=float, default=[1.0, 0.85, 0.707])
    parser.add_argument("--crossings", nargs="+", type=float, default=[138.5, 50.0, 10.0])
    parser.add_argument("--clb-crossing", type=float, default=-1.0,
                        help="crossing delay inside the CLB, when it differs from routing")
    parser.add_argument("--vpr-args", default="", help="extra VPR options for every run")
    parser.add_argument("--relayer", action="store_true", help="rearrange FLEs inside 3D CLBs after packing")
    parser.add_argument("--wire-spans", nargs=2, type=int, metavar=("L4", "L16"),
                        help="tiles crossed by the two 3D wire types, with their delay unchanged")
    parser.add_argument("--crossbar-scale", nargs=2, type=float, metavar=("PINS", "FEEDBACK"),
                        help="3D crossbar delay over 2D, for CLB inputs and for FLE feedback")
    parser.add_argument("--stacked", action="store_true", help="a whole flat CLB on each layer instead of one split CLB")
    parser.add_argument("--local-inputs", action="store_true", help="feed each layer's FLEs from that layer's pins only")
    parser.add_argument("--local-2d", action="store_true", help="give the 2D CLB the same split crossbar")
    parser.add_argument("--scale-2d", type=float, default=1.0, help="wire delay scale of the 2D fabric")
    parser.add_argument("--n2d", type=int, default=10, help="FLEs in the 2D CLB")
    parser.add_argument("--n3d", type=int, default=10, help="FLEs in the 3D CLB, half on each layer when split")
    parser.add_argument("--growth", nargs=2, type=float, default=[1.0, 1.0], metavar=("2D", "3D"),
                        help="crossbar delay over the 10-FLE crossbar's, for wider muxes in a bigger CLB")
    parser.add_argument("--wire-spans-2d", nargs=2, type=int, metavar=("L4", "L16"),
                        help="tiles crossed by the two 2D wire types, for a 2D tile of another size")
    parser.add_argument("--crossbar-scale-2d", nargs=2, type=float, metavar=("PINS", "FEEDBACK"),
                        help="2D crossbar delay over the 10-FLE 2D crossbar's, for CLB inputs and FLE feedback")
    parser.add_argument("--switchblocks", choices=["wilton", "custom"], default="wilton",
                        help="built-in Wilton switch blocks, or VTR-style custom ones (switchblocks.xml) in both fabrics")
    parser.add_argument("--vertical", choices=["none", "dense", "sparse"], default="none",
                        help="with custom switch blocks, 3D wires that turn onto the layer above or below")
    parser.add_argument("--span", type=int, default=2, help="layers one split 3D CLB spans")
    parser.add_argument("--sparse", type=float, default=1.0,
                        help="fraction of crossbar sources each 3D LUT input reaches (0.5 halves the crossbar)")
    parser.add_argument("--sparse-2d", type=float, default=1.0, help="the same for the 2D CLB")
    parser.add_argument("--links-3d", choices=["vertical", "horizontal"],
                        help="direct links from each 3D CLB to the CLBs above and below, or east and west")
    parser.add_argument("--links-2d", choices=["horizontal"], help="direct links from each 2D CLB to its east and west CLBs")
    parser.add_argument("--link-ps", type=float, default=151.0,
                        help="delay of a direct link: an input mux (106 ps) and a crossing (45 ps)")
    parser.add_argument("--own-layer-inputs", action="store_true",
                        help="3D CLB input pins reach only their own layer's tracks")
    parser.add_argument("--routing-scale", type=float, default=1.0,
                        help="multiply routing switch, connection block and crossing delays in both fabrics")
    parser.add_argument("--relax-w", type=float, default=0.0,
                        help="find each run's fewest tracks and route with this many times as many (VTR uses 1.3)")
    parser.add_argument("--layers", type=int, default=2, help="layers of the 3D fabric; more than 2 needs --vertical")
    parser.add_argument("--slim", action="store_true", help="delete each run's large VPR outputs once it is read")
    parser.add_argument("--timeout", type=int, default=7200, help="seconds allowed for one VPR run")
    parser.add_argument("--bench-dir", type=Path, default=BENCH, help="folder of LUT-mapped BLIF benchmarks")
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--no-2d", action="store_true", help="run only the 3D fabric (its 2D runs come from another sweep)")
    parser.add_argument("--clock-modeling", choices=["route", "ideal"], default="route",
                        help="VPR --clock_modeling: clocks routed on general routing (default, as every sweep so "
                             "far), or ideal (no skew); ideal runs get their own folders")
    parser.add_argument("--hard-blocks", nargs="+", choices=["none", "columns", "stacked", "span", "layer"], default=["none"],
                        help="give both fabrics RAM and DSP columns (hardblocks.py), placed in the 3D fabric as "
                             "columns on each layer, RAM under DSP in one column, tiles spanning both layers, or "
                             "on a layer of their own (several: one 3D run of each, sharing the 2D runs, and "
                             "results_<placement>.csv for each); none (default) keeps the CLB-only fabrics")
    parser.add_argument("--hard-delay-scale", type=float, default=0.0,
                        help="multiply the template's hard-block delays by this; 0 (default) scales them by the "
                             "2D SPICE set's CLB path over the template's (1.0 without --delays)")
    parser.add_argument("--hard-inputs", choices=["own", "both"], default="own",
                        help="with --own-layer-inputs: hard-block input pins read only their own layer's tracks, "
                             "as the CLB's (default), or both layers' (a bigger connection block on the hard blocks only)")
    parser.add_argument("--hard-crossing-ps", type=float, default=-1.0,
                        help="crossing delay inside a spanning hard block; default the 3D set's clb_crossing, "
                             "else the routing crossing")
    parser.add_argument("--delays", nargs=3, metavar=("JSON", "FABRIC_2D", "FABRIC_3D"),
                        help="transistor-level delays from spice/make_spice.py for each fabric, replacing the "
                             "template's routing, CLB and crossing delays (--scales and --crossings are ignored)")
    args = parser.parse_args()
    BENCH = args.bench_dir.resolve()
    VPR = args.vpr.resolve()
    CLB_CROSSING = args.clb_crossing
    EXTRA = args.vpr_args.split()
    RELAYER = args.relayer
    WIRE_SPANS = args.wire_spans
    CROSSBAR_SCALE = args.crossbar_scale
    STACKED = args.stacked
    LOCAL_INPUTS = args.local_inputs
    LOCAL_2D = args.local_2d
    SCALE_2D = args.scale_2d
    N2D, N3D = args.n2d, args.n3d
    GROWTH_2D, GROWTH_3D = args.growth
    WIRE_SPANS_2D = args.wire_spans_2d
    TIMEOUT = args.timeout
    CROSSBAR_SCALE_2D = args.crossbar_scale_2d
    SLIM = args.slim
    LAYERS = args.layers
    RELAX = args.relax_w
    ROUTING = args.routing_scale
    OWN_LAYER_INPUTS = args.own_layer_inputs
    DELAYS = None
    if args.delays:
        sets = json.loads(Path(args.delays[0]).read_text())
        DELAYS = {"2d": sets[args.delays[1]], "3d": sets[args.delays[2]]}
        args.scales, args.crossings = [1.0], [DELAYS["3d"].get("route_crossing", 0.0)]
    LINKS_2D, LINKS_3D, LINK_PS = args.links_2d, args.links_3d, args.link_ps
    SPAN, SPARSE, SPARSE_2D = args.span, args.sparse, args.sparse_2d
    HARD, HARD_SCALE, HARD_CROSSING = args.hard_blocks, args.hard_delay_scale, args.hard_crossing_ps
    CLOCK = args.clock_modeling
    HARD_INPUTS = args.hard_inputs
    assert HARD == ["none"] or ("none" not in HARD and LAYERS == 2 and SPAN == 2 and not RELAYER), \
        "hard blocks: two-layer fabrics only, and not with none"
    assert LAYERS == 2 or args.vertical != "none", "layers beyond two connect only through vertical switch blocks"
    SWITCHBLOCKS = args.switchblocks
    VERTICAL = None if args.vertical == "none" else args.vertical
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    two_d = "none" if HARD == ["none"] else HARD[0]  # the 2D fabric is the same for every placement
    jobs = [("2d", here / "vtr_2d_clb_arch.xml", args.w2d, 1.0, 0.0, b, s, out, two_d)
            for b in args.benches for s in args.seeds]
    if args.no_2d:
        jobs = []
    configs = [(x, c) for c in args.crossings for x in args.scales]
    jobs += [("3d", here / "vtr_3d_clb_arch.xml", args.w3d, x, c, b, s, out, hb)
             for hb in HARD for x, c in configs for b in args.benches for s in args.seeds]
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        rows = []
        for row in pool.map(run, jobs):
            rows.append(row)
            print(row, flush=True)
    with open(out / "results.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    if HARD != ["none"]:
        # One file per placement, with the shared 2D rows, for compare_configs.py.
        for hb in HARD:
            with open(out / f"results_{hb}.csv", "w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(r for r in rows if r["fabric"] == "2d" or r["hard"] == hb)

    def mean(fabric, scale, crossing, bench, hb="none"):
        values = [float(r["cpd_ns"]) for r in rows if r["fabric"] == fabric and r["bench"] == bench
                  and r["wire_scale"] == scale and r["crossing_ps"] == crossing and r["routed"]
                  and (fabric == "2d" or r.get("hard", "none") == hb)]
        return statistics.mean(values) if len(values) == len(args.seeds) else None
    for hb in HARD:
        print("\n3D delay / 2D delay, geometric mean over benchmarks that routed in every run"
              + ("" if hb == "none" else f" (hard blocks: {hb})"))
        print("crossing_ps  " + "  ".join(f"wire {x}" for x in args.scales))
        for crossing in args.crossings:
            cells = []
            for scale in args.scales:
                ratios = []
                for bench in args.benches:
                    base = mean("2d", 1.0, 0.0, bench)
                    value = mean("3d", scale, crossing, bench, hb)
                    if base and value:
                        ratios.append(value / base)
                cells.append(f"{statistics.geometric_mean(ratios):.3f}" if ratios else "failed")
            print(f"{crossing:11.1f}  " + "  ".join(f"{c:>8}" for c in cells) + f"  ({len(ratios)} benchmarks)")
    failed = [r for r in rows if not r["routed"]]
    print(f"{len(failed)} of {len(rows)} runs failed to route")


if __name__ == "__main__":
    main()
