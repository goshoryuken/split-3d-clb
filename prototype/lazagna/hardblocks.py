"""Hard blocks (20 Kb RAM, 27x27 / 2x18x19 DSP) for the 2D and 3D fabrics of compare_2d_3d.py.

Opt-in through compare_2d_3d.py --hard-blocks; with the default "none" nothing here runs and
the generated architectures are byte-identical to the CLB-only ones (checked,
HARDBLOCKS.md). Four placements of the hard blocks in a two-layer fabric, applied
the same way to the split-CLB fabric and to the stacked-CLB fabric (--stacked):

  columns  each layer has its own RAM and DSP columns at the same x (RAM over RAM, DSP over
           DSP): LaZagna's homogeneous layers.
  stacked  one column holds the RAM on layer 0 and the DSP directly above it on layer 1.
  span     one RAM or DSP tile spans both layers like the split CLB (layer_span="2"): half its
           pins on each layer; the DSP's two 18x19 multipliers sit one per layer, the RAM's
           core on layer 0 (its port-2 and upper data pins cross into it).
  layer    a third layer under the logic holds all hard blocks; the logic layers are CLB-only.

Hard blocks per LUT are the same in every fabric: LaZagna's base architecture has one RAM and
one DSP column per 6 columns of 10-LUT CLBs, one RAM and one DSP per 60 LUTs (patterns in
LAYOUTS; check_ratios() verifies them). Every tile is 1x1, as in LaZagna's base architecture
(VPR's multi-layer tiles must be 1x1). One grid cell of one layer is one "die cell" of silicon,
so a spanning hard block uses two die cells where the other placements use one, and the layer
placement's hard-block die is one third empty (die_cells() counts this).

In the layer placement the hard-block layer is two bonds from the upper logic layer, and this
VPR connects layers only at block pins and only to the adjacent layer
(is_pin_conencted_to_layer, max offset 1). Hard-block pins (inputs too) therefore reach the
middle layer's tracks, and with own-layer CLB inputs the upper logic layer's input pins reach
the middle layer too; otherwise a hard-block output has no path to an upper-layer LUT input.
An input pin reaches another layer's tracks only with VPR built with vpr-cb-layers.patch
(rr_graph.cpp, on this branch): without it a type placed on one layer only (stacked, layer)
gets no connection-block pattern for the other layer, so its input pins silently read only
their own layer, and in the layer placement some hard-block inputs have no path at all.

The RAM is VTR's mem20K block (single_port_ram / dual_port_ram models, the five modes of the
Koios 22 nm architecture) so Koios designs synthesized by hardblocks/synth_koios.sh pack into
it; its timing is LaZagna's spram's (40 nm template: setup, hold, clock-to-Q, a zero-delay
internal register-to-register path), the DSP's is LaZagna's complex_dsp's, both multiplied by
delay_scale (compare_2d_3d.py --hard-delay-scale). All hard-block delays are therefore
ESTIMATED, not simulated. The RAM clock pin is routable (Fc as the CLB's clock pin): with
--clock_modeling route, LaZagna's Fc 0 on it leaves the clock no path.
"""
import math
import re

# Template (40 nm) timing of LaZagna's spram and complex_dsp, in seconds, before delay_scale.
MEM_SETUP, MEM_HOLD, MEM_CLK_Q = -65.8482e-12, 139.2236e-12, 696.118e-12
DSP_DELAY = 2.7654e-9
UTIL_CLB, UTIL_HARD = 0.7, 0.8
LUTS_PER_HARD = 60  # LaZagna's base architecture: 6 CLB columns of 10 LUTs per RAM column and per DSP column

# Each layer: its fill and its columns (tile, startx, repeatx). Spanning hard tiles (span) sit on
# layer 0 and reserve layer 1 above them (EMPTY columns where layer 1 is filled with CLBs).
D, M, E = "complex_dsp", "memory", "EMPTY"
LAYOUTS = {
    ("2d", None): [dict(fill="clb", cols=[(D, 2, 8), (M, 4, 8)])],
    ("split", "columns"): [dict(fill="clb", cols=[(D, 2, 8), (M, 4, 8)]), dict(fill=E, cols=[(D, 2, 8), (M, 4, 8)])],
    ("split", "stacked"): [dict(fill="clb", cols=[(M, 2, 4)]), dict(fill=E, cols=[(D, 2, 4)])],
    ("split", "span"): [dict(fill="clb", cols=[(D, 2, 5), (M, 4, 5)]), dict(fill=E)],
    ("split", "layer"): [dict(fill=E, cols=[(D, 1, 3), (M, 2, 3)]), dict(fill="clb"), dict(fill=E)],
    ("stack", "columns"): [dict(fill="clb", cols=[(D, 2, 8), (M, 4, 8)]), dict(fill="clb", cols=[(D, 2, 8), (M, 4, 8)])],
    ("stack", "stacked"): [dict(fill="clb", cols=[(M, 2, 4)]), dict(fill="clb", cols=[(D, 2, 4)])],
    ("stack", "span"): [dict(fill="clb", cols=[(D, 2, 5), (M, 4, 5)]), dict(fill="clb", cols=[(E, 2, 5), (E, 4, 5)])],
    ("stack", "layer"): [dict(fill=E, cols=[(D, 1, 3), (M, 2, 3)]), dict(fill="clb"), dict(fill="clb")],
}
MEM_INPUTS = [("addr1", 11), ("addr2", 11), ("data", 40), ("we1", 1), ("we2", 1)]
MEM_OUTPUTS = [("out", 40)]
# Pins of each layer of a spanning RAM: port 1 (and data/out[19:0]) below, port 2 above.
MEM_LAYER_PINS = [["addr1[0:10]", "data[0:19]", "we1", "out[0:19]", "clk"], ["addr2[0:10]", "data[20:39]", "we2", "out[20:39]"]]
DSP_LAYER_PINS = [["I[0:36]", "result[0:36]"], ["I[37:73]", "result[37:73]"]]
MODES = [  # name, model, address bits, data bits, dual port
    ("mem_512x40_sp", "single_port_ram", 9, 40, False), ("mem_1024x20_sp", "single_port_ram", 10, 20, False),
    ("mem_2048x10_sp", "single_port_ram", 11, 10, False), ("mem_1024x20_dp", "dual_port_ram", 10, 20, True),
    ("mem_2048x10_dp", "dual_port_ram", 11, 10, True)]


def fabric_kind(label, stacked):
    return "2d" if label == "2d" else ("stack" if stacked else "split")


def layout_spec(label, stacked, mode):
    return LAYOUTS[(fabric_kind(label, stacked), None if label == "2d" else mode)]


def count_blocks(blif_text):
    """RAM blocks and DSP blocks (two 18x19 multipliers share one) a BLIF needs."""
    rams = two = one = 0
    for line in blif_text.splitlines():
        if line.startswith(".subckt"):
            model = line.split()[1]
            rams += model in ("single_port_ram", "dual_port_ram")
            two += model == "two_mult_18x19"
            one += model == "one_mult_27x27"
    return rams, math.ceil(two / 2) + one


def columns(grid, start, repeat):
    return [x for x in range(1, grid - 1) if x >= start and (x - start) % repeat == 0]


def tiles(grid, spec, fles):
    """LUT, RAM and DSP capacity of a grid x grid device with this layout.

    CLBs count on the layers whose fill is clb (a split CLB on its anchor layer); a column
    of any tile, EMPTY included, takes its x out of that layer's CLBs.
    """
    luts = rams = dsps = 0
    rows = grid - 2
    for layer in spec:
        taken = set()
        for tile, start, repeat in layer.get("cols", []):
            xs = columns(grid, start, repeat)
            taken |= set(xs)
            rams += len(xs) * rows if tile == M else 0
            dsps += len(xs) * rows if tile == D else 0
        if layer["fill"] == "clb":
            luts += (rows - len(taken)) * rows * fles
    return luts, rams, dsps


def die_cells(grid, spec):
    """Silicon in grid cells: every layer's interior cells (I/O ring excluded)."""
    return (grid - 2) ** 2 * len(spec)


def check_ratios(fles_2d=10, fles_split=20, fles_stack=10, grid=242):
    """Hard blocks per LUT of every layout, on a grid big enough that edge effects vanish."""
    out = {}
    for (kind, mode), spec in LAYOUTS.items():
        fles = {"2d": fles_2d, "split": fles_split, "stack": fles_stack}[kind]
        luts, rams, dsps = tiles(grid, spec, fles)
        out[(kind, mode)] = (luts / rams, luts / dsps)
    return out


def grid_for(blif_path, spec, fles):
    """Smallest grid whose CLBs, RAMs and DSPs all fit at their utilization limits.

    Pads: 8 per perimeter tile of every layer (all layers have the I/O ring), 90% usable.
    """
    text = blif_path.read_text().replace("\\\n", " ")
    luts = sum(line.startswith(".names") for line in text.splitlines())
    pads = sum(len(line.split()) - 1 for line in text.splitlines() if line.startswith((".inputs", ".outputs")))
    rams, dsps = count_blocks(text)
    edge = math.ceil(pads / 8 / 4 / 0.9 / len(spec)) + 2
    grid = max(edge, 4)
    while True:
        cap = tiles(grid, spec, fles)
        if cap[0] * UTIL_CLB >= luts and cap[1] * UTIL_HARD >= rams and cap[2] * UTIL_HARD >= dsps:
            return grid, luts, rams, dsps
        grid += 1


def expand(token, prefix):
    """'data[0:19]' -> ['memory.data[0]', ...]; 'we1' -> ['memory.we1']."""
    m = re.match(r"(\w+)\[(\d+):(\d+)\]", token)
    if not m:
        return [f"{prefix}.{token}"]
    return [f"{prefix}.{m.group(1)}[{i}]" for i in range(int(m.group(2)), int(m.group(3)) + 1)]


def pinlocations(prefix, layer_pins, outputs, three_d, span, inputs_reach_other):
    """Spread each layer's pins round-robin over the four sides.

    In a 3D fabric outputs reach the neighbouring layer's routing (layer_offset="1"); inputs
    do so only if inputs_reach_other.
    """
    lines = ['<pinlocations pattern="custom">']
    for layer, tokens in enumerate(layer_pins):
        pins = [p for t in tokens for p in expand(t, prefix)]
        sides = {s: {"in": [], "out": []} for s in ("left", "top", "right", "bottom")}
        for i, pin in enumerate(pins):
            kind = "out" if re.match(rf"{prefix}\.({'|'.join(outputs)})\b", pin) else "in"
            sides[("left", "top", "right", "bottom")[i % 4]][kind].append(pin)
        where = f' pin_layer="{layer}"' if span > 1 else ""
        for side, groups in sides.items():
            if three_d and not inputs_reach_other:
                if groups["out"]:
                    lines.append(f'          <loc side="{side}"{where} layer_offset="1">{" ".join(groups["out"])}</loc>')
                if groups["in"]:
                    lines.append(f'          <loc side="{side}"{where}>{" ".join(groups["in"])}</loc>')
            else:
                reach = ' layer_offset="1"' if three_d else ""
                lines.append(f'          <loc side="{side}"{where}{reach}>{" ".join(groups["out"] + groups["in"])}</loc>')
    lines.append("        </pinlocations>")
    return "\n".join(lines)


def memory_models():
    """VTR's single_port_ram / dual_port_ram models, as in the Koios 22 nm architecture.

    Sequential ports with combinational_sink_ports: VPR times them as registered inputs and
    outputs with an internal register-to-register path (timing_graph_builder.cpp), not as a
    combinational path through the RAM.
    """
    def model(name, ins, outs):
        ports = "".join(f'\n        <port name="{p}" clock="clk" combinational_sink_ports="{sink}"/>' for p, sink in ins)
        outs_x = "".join(f'\n        <port name="{p}" clock="clk"/>' for p in outs)
        return (f'\n    <model name="{name}">\n      <input_ports>{ports}\n        <port name="clk" is_clock="1"/>\n'
                f'      </input_ports>\n      <output_ports>{outs_x}\n      </output_ports>\n    </model>')
    return (model("single_port_ram", [("addr", "out"), ("data", "out"), ("we", "out")], ["out"])
            + model("dual_port_ram", [("addr1", "out1"), ("addr2", "out2"), ("data1", "out1"), ("data2", "out2"),
                                      ("we1", "out1"), ("we2", "out2")], ["out1", "out2"]))


def memory_pb_type(scale, crossing):
    """VTR's mem20K pb_type with LaZagna's spram timing times scale."""
    setup, hold, clk_q = (f"{v * scale:.6g}" for v in (MEM_SETUP, MEM_HOLD, MEM_CLK_Q))
    cross = f' layer_crossing_delay="{crossing}"' if crossing is not None else ""
    out = ['    <pb_type name="memory">']
    out += [f'      <input name="{n}" num_pins="{w}"/>' for n, w in MEM_INPUTS]
    out += [f'      <output name="{n}" num_pins="{w}"/>' for n, w in MEM_OUTPUTS] + ['      <clock name="clk" num_pins="1"/>']
    for name, model, abits, dbits, dual in MODES:
        if dual:
            ports = [("addr1", abits, "address1"), ("addr2", abits, "address2"), ("data1", dbits, "data_in1"),
                     ("data2", dbits, "data_in2"), ("we1", 1, "write_en1"), ("we2", 1, "write_en2")]
            outs = [("out1", dbits, "data_out1"), ("out2", dbits, "data_out2")]
            wires = [("addr1", f"memory.addr1[{abits - 1}:0]"), ("addr2", f"memory.addr2[{abits - 1}:0]"),
                     ("data1", f"memory.data[{dbits - 1}:0]"), ("data2", f"memory.data[{2 * dbits - 1}:{dbits}]"),
                     ("we1", "memory.we1"), ("we2", "memory.we2")]
            owires = [("out1", f"memory.out[{dbits - 1}:0]"), ("out2", f"memory.out[{2 * dbits - 1}:{dbits}]")]
            paths = [("addr1", "out1"), ("data1", "out1"), ("we1", "out1"), ("addr2", "out2"), ("data2", "out2"), ("we2", "out2")]
        else:
            ports = [("addr", abits, "address"), ("data", dbits, "data_in"), ("we", 1, "write_en")]
            outs = [("out", dbits, "data_out")]
            wires = [("addr", f"memory.addr1[{abits - 1}:0]"), ("data", f"memory.data[{dbits - 1}:0]"), ("we", "memory.we1")]
            owires = [("out", f"memory.out[{dbits - 1}:0]")]
            paths = [("addr", "out"), ("data", "out"), ("we", "out")]
        out.append(f'      <mode name="{name}">')
        # Not class="memory": VPR would then expect one-bit-wide memory slices in the netlist
        # (as ODIN writes them); koios_hb.v already splits RAMs into whole blocks.
        out.append(f'        <pb_type name="{name}" blif_model=".subckt {model}" num_pb="1">')
        out += [f'          <input name="{p}" num_pins="{w}"/>' for p, w, c in ports]
        out += [f'          <output name="{p}" num_pins="{w}"/>' for p, w, c in outs]
        out.append('          <clock name="clk" num_pins="1"/>')
        # As LaZagna's spram: setup on every port, clock-to-Q on every port (the input ports' is
        # the start of the internal path), and a zero-delay internal path from inputs to outputs.
        for p, _, _ in ports + outs:
            out.append(f'          <T_setup value="{setup}" port="{name}.{p}" clock="clk"/>')
        for p, _, _ in ports + outs:
            out.append(f'          <T_hold value="{hold}" port="{name}.{p}" clock="clk"/>')
        for p, _, _ in ports + outs:
            out.append(f'          <T_clock_to_Q max="{clk_q}" port="{name}.{p}" clock="clk"/>')
        out += [f'          <delay_constant max="0" in_port="{name}.{a}" out_port="{name}.{b}"/>' for a, b in paths]
        out.append('        </pb_type>')
        out.append('        <interconnect>')
        out += [f'          <direct name="{p}" input="{w}" output="{name}.{p}"{cross}/>' for p, w in wires]
        out += [f'          <direct name="{p}" input="{name}.{p}" output="{w}"{cross}/>' for p, w in owires]
        out.append(f'          <direct name="clk" input="memory.clk" output="{name}.clk"{cross}/>')
        out.append('        </interconnect>')
        out.append('      </mode>')
    out.append('    </pb_type>')
    return "\n".join(out)


def memory_tile(three_d, span, inputs_reach_other):
    layer_pins = MEM_LAYER_PINS if span > 1 else [[t for layer in MEM_LAYER_PINS for t in layer]]
    span_attr = f' layer_span="{span}"' if span > 1 else ""
    ports = "".join(f'\n        <input name="{n}" num_pins="{w}"/>' for n, w in MEM_INPUTS)
    ports += "".join(f'\n        <output name="{n}" num_pins="{w}"/>' for n, w in MEM_OUTPUTS)
    return (f'<tile name="memory" height="1" width="1"{span_attr} area="137668">\n      <sub_tile name="memory">\n'
            '        <equivalent_sites>\n          <site pb_type="memory" pin_mapping="direct"/>\n        </equivalent_sites>'
            f'{ports}\n        <clock name="clk" num_pins="1"/>\n'
            '        <fc in_type="frac" in_val="0.15" out_type="frac" out_val="0.10"/>\n        '
            + pinlocations("memory", layer_pins, ["out"], three_d, span, inputs_reach_other)
            + "\n      </sub_tile>\n    </tile>")


def layout(grid, spec):
    out = [f'<fixed_layout name="12x12" width="{grid}" height="{grid}">']
    for die, layer in enumerate(spec):
        out.append(f'      <layer die="{die}">')
        out.append('        <perimeter type="io" priority="100"/>')
        out.append('        <corners type="EMPTY" priority="101"/>')
        out.append(f'        <fill type="{layer["fill"]}" priority="10"/>')
        for tile, start, repeat in layer.get("cols", []):
            out.append(f'        <col type="{tile}" startx="{start}" starty="1" repeatx="{repeat}" priority="20"/>')
        out.append('      </layer>')
    out.append('    </fixed_layout>')
    return "\n".join(out)


def delay_scale(spice_2d, template=(95.0, 261.0, 25.0)):
    """SPICE over template delay of the CLB path crossbar + LUT (mean over inputs) + BLE output.

    template: the 40 nm template's crossbar input (95 ps), LUT (261 ps, every input) and LUT to
    BLE output (25 ps) delays, from vtr_2d_clb_arch.xml.
    """
    lut = sum(spice_2d[f"lut{k}"] for k in range(6)) / 6
    return (spice_2d["xbar_pin"] + lut + spice_2d["ble"]) / sum(template)


def apply(xml, mode, label, stacked, own_layer_inputs, grid, scale, crossing_s, hard_inputs_own=None):
    """Rewrite the architecture's hard blocks and layout for this fabric and placement.

    crossing_s is the delay (seconds) charged inside a spanning hard block per layer a pin's
    path crosses; unused for single-layer hard blocks. own_layer_inputs: the split CLB's input
    pins reach only their own layer's tracks; hard-block inputs then do too (unless
    hard_inputs_own is False), except in the layer placement (module docstring).
    """
    three_d = label == "3d"
    spec = layout_spec(label, stacked, mode)
    span = 2 if three_d and mode == "span" else 1
    crossing = crossing_s if span > 1 else None
    if hard_inputs_own is None:
        hard_inputs_own = own_layer_inputs
    reach_other = not hard_inputs_own or mode == "layer"
    # Models: LaZagna's four spram models -> VTR's single_port_ram and dual_port_ram.
    xml, count = re.subn(r'\s*<model name="spram(512x40|1024x20|2048x10)?">.*?</model>', "", xml, flags=re.S)
    assert count == 4, count
    xml = xml.replace("<models>", "<models>" + memory_models(), 1)
    # Tiles and pb_types.
    xml, count = re.subn(r'<tile name="spram".*?</tile>', lambda m: memory_tile(three_d, span, reach_other), xml, flags=re.S)
    assert count == 1
    xml, count = re.subn(r'<pb_type name="spram">.*?</pb_type>\s*<!-- Define BRAM end -->',
                         lambda m: memory_pb_type(scale, crossing), xml, flags=re.S)
    assert count == 1, "spram pb_type"
    dsp_tile = re.search(r'<tile name="complex_dsp".*?</tile>', xml, re.S).group(0)
    new_tile = re.sub(r'<pinlocations pattern="custom">.*?</pinlocations>',
                      lambda m: pinlocations("complex_dsp", DSP_LAYER_PINS if span > 1 else [[t for l in DSP_LAYER_PINS for t in l]],
                                             ["result"], three_d, span, reach_other), dsp_tile, flags=re.S)
    if span > 1:
        new_tile = new_tile.replace('<tile name="complex_dsp" height="1" width="1"', f'<tile name="complex_dsp" height="1" width="1" layer_span="{span}"')
    xml = xml.replace(dsp_tile, new_tile)
    dsp_pb = re.search(r'<pb_type name="complex_dsp">.*?\n    </pb_type>', xml, re.S).group(0)
    new_pb = dsp_pb.replace(f'max="{DSP_DELAY:.4e}"'.replace("e-09", "e-9"), f'max="{DSP_DELAY * scale:.6g}"')
    assert new_pb != dsp_pb, "DSP delay"
    if span > 1:
        # One 18x19 multiplier per layer, wired straight to its own layer's pins. LaZagna's
        # wrapper (mult_18x19_top) would sit on layer 0, so the layer-1 multiplier's signals
        # would cross down into it and back up (two crossings each way); drop the wrapper.
        mode = re.search(r'<mode name="two_mult_18x19">.*?</mode>', new_pb, re.S).group(0)
        inner = re.search(r'<pb_type name="two_mult_18x19" num_pb="2">.*?</pb_type>\s*<interconnect>.*?</interconnect>\s*</pb_type>',
                          mode, re.S).group(0)
        inner = inner.replace('num_pb="2">', 'num_pb="2" instance_layer_offsets="0 1">', 1)
        wires = [("a0", "complex_dsp.I[17:0]", "two_mult_18x19[0].A"), ("b0", "complex_dsp.I[36:18]", "two_mult_18x19[0].B"),
                 ("a1", "complex_dsp.I[54:37]", "two_mult_18x19[1].A"), ("b1", "complex_dsp.I[73:55]", "two_mult_18x19[1].B"),
                 ("y0", "two_mult_18x19[0].Y", "complex_dsp.result[36:0]"), ("y1", "two_mult_18x19[1].Y", "complex_dsp.result[73:37]")]
        flat = ('<mode name="two_mult_18x19">\n          ' + inner + '\n          <interconnect>\n'
                + "".join(f'            <direct name="{n}" input="{i}" output="{o}"/>\n' for n, i, o in wires)
                + '          </interconnect>\n        </mode>')
        new_pb = new_pb.replace(mode, flat)
        new_pb = re.sub(r'(<direct name="[^"]+" input="[^"]+" output="[^"]+")', rf'\1 layer_crossing_delay="{crossing}"', new_pb)
    xml = xml.replace(dsp_pb, new_pb)
    if three_d and mode == "layer" and own_layer_inputs and not stacked:
        # The upper logic layer's input pins also read the middle layer's tracks (docstring).
        # VPR allows one <loc> per side, pin layer and layer offset: merge them into the outputs'.
        tile = re.search(r'<tile name="clb".*?</tile>', xml, re.S).group(0)
        new = tile
        for side, pins in re.findall(r'<loc side="(\w+)" pin_layer="1">([^<]*)</loc>', tile):
            new, count = re.subn(rf'\s*<loc side="{side}" pin_layer="1">[^<]*</loc>', "", new)
            assert count == 1
            new, count = re.subn(rf'(<loc side="{side}" pin_layer="1" layer_offset="1">[^<]*)</loc>', rf'\1 {pins}</loc>', new)
            assert count == 1, side
        assert new != tile, "no own-layer input pins on the CLB's upper layer"
        xml = xml.replace(tile, new)
    # Layout.
    xml, count = re.subn(r'<fixed_layout name="12x12".*?</fixed_layout>', lambda m: layout(grid, spec), xml, flags=re.S)
    assert count == 1
    return xml
