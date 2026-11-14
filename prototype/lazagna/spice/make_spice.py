#!/usr/bin/env python3
"""Transistor-level delays of the CLB and routing in sky130, with Cadence Spectre.

Circuits follow the OpenFPGA circuit models LaZagna generates RTL from
(task/designs/openfpga_arch.xml): routing and connection-block muxes are two-level
transmission-gate muxes with an inverter on every input and a three-stage tapered
output buffer; crossbar muxes are the same with one inverter out; the LUT is a
transmission-gate tree with buffered and inverted select rails; config bits are
static (flip-flop outputs). Pass gates keep OpenFPGA's sizes (n 1, p 2, in units of
the 0.42 um minimum width). Every buffer that drives a long net is a tapered chain
sized for its load (stage effort about 4), the same rule in 2D and 3D, where
OpenFPGA's generic models would put a minimum inverter.

Wires are RC ladders. Resistance and capacitance per micron come from the kit's
tech LEF (read at run time, not stored here): ground capacitance doubled for
neighbours at minimum spacing, 1.5 times for long wires at double width and spacing.
Loads hang on the wire where the fabric puts them.

Each fabric gives a delay set for compare_2d_3d.py (--delays): every routing switch
Tdel (mux, buffer, wire and loads: VPR's wires have R = C = 0), the connection block,
both crossbar paths, the LUT inputs, the FLE output mux, and the layer crossing (a
driver, bond and receiver, as laid out) inside the CLB and in the routing.

7 nm: fabrics named *_7nm use ASAP7 (an open predictive FinFET kit), with the same circuits:
RVT devices at 0.7 V, sizes in fins, wire R and C per layer from OpenROAD's ASAP7 setup, and
every length scaled from sky130 by the 2D CLB's side in the ASAP7 layout (S7 below).

Usage (on the server):
  make_spice.py --models DIR --tlef FILE --env BLOCK_DIR --out DIR [--fabric NAME...] [--corner tt]
  make_spice.py --models ASAP7_MODEL_DIR --env BLOCK_DIR --out DIR --fabric NAME_7nm...
"""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path

VDD = 1.8
WN = 0.42          # um, minimum nfet width; size 1 inverter is n 0.42 / p 0.84
L = 0.15
C_GATE = 1.2       # fF per um of gate width, from the gate charge of 1 um devices (spice/cal.sp)
C_INV1 = C_GATE * 3 * WN
SEG_UM = 50        # um per wire ladder segment
STEP = "1p"        # transient print step
EDGE = 40e-12      # source edge

# ASAP7 (BSD licence; models/hspice/7nm_TT_160803.pm of github.com/The-OpenROAD-Project/
# asap7_pdk_r1p7). spice/cal7.sp at 0.7 V: one-fin RVT nfet 37.3 uA, pfet 32.0 uA; gate charge
# 0.0437 fF (n) and 0.0453 fF (p) per fin; FO4 7.9 ps falling, 8.1 rising with one fin each, so
# a size-1 inverter and every pass gate are one fin n and one fin p (OpenFPGA's p 2 makes up
# for sky130's weak pfet; ASAP7's is about as strong as its nfet).
ASAP7_C_INV1 = 0.0437 + 0.0453
# Ohm and fF per um per layer, from OpenROAD-flow-scripts flow/platforms/asap7/setRC.tcl
# (kohm and fF per um there). Vias V1-V9 in series: 3 x 17.2 + 2 x 11.8 + 2 x 8.2 + 2 x 6.3 ohm.
ASAP7_LAYERS = {"M2": (29.7127, 0.174942), "M3": (31.2870, 0.155554),
                "M4": (18.0365, 0.178475), "M5": (18.9935, 0.164264)}
ASAP7_VIAS = 3 * 17.2 + 2 * 11.8 + 2 * 8.2 + 2 * 6.3
# Hybrid bond at 1 um pitch, 0.5 um pads (Toronto's 3D FPGA work studies 1-5 um). Assumptions:
# pad 0.1 fF each, interface 0.2 fF (sky130's 1 fF times the pad side ratio 0.5 / 2.5), 0.5 ohm.
ASAP7_PAD_C = 0.1
ASAP7_BOND_C = 0.2
# DFFHQNx1_ASAP7_75t_R, RVT TT liberty (asap7sc7p5t_SEQ_RVT_TT_nldm_220123), 20 ps slews, 2.88 fF:
# clock to Q 64.69 ps (rise, the slower), setup 12.47 ps (fall, the larger). The sky130 sets keep
# VPR's template flip-flop (80 and 151 ps); at 7 nm that would be several times too slow.
ASAP7_FF = dict(ff_setup=12.47, ff_clk_q=64.69)

# Fabrics. Mux sizes are the averages over one interior tile of the RTL LaZagna
# generated (tasks_run/*/verilog/SRC/routing/{sb,cbx,cby}_*.v); loads per track per
# tile are that tile's SB and CB mux inputs over its 2W tracks. Sizes in um: the 2D
# CLB core and tiles from pnr/tile_results_*.txt, the 20-LUT layer core 520 x 520 as
# laid out. The 12-LUT 2D CLB was not generated or laid out: cluster_size_model.py.
# l16 is the long wire's length in the fabric's own tiles, as the sweeps' --wire-spans
# give it (L4 stays 4 tiles in every fabric).
FABRICS = {
    "2d10_w100": dict(clb=495.9, tile=576.9, xbar=50, pin_fanout=60, fb_fanout=60, fb_other=0,
                      sb=10, cb=13, sb_loads=460 / 200, cb_loads=528 / 200, opin_loads=10, l16=16),
    "2d12_w110": dict(clb=559.6, tile=641.4, xbar=60, pin_fanout=72, fb_fanout=72, fb_other=0,
                      sb=10, cb=15, sb_loads=460 / 200, cb_loads=48 * 14.5 / 220, opin_loads=11, l16=14,
                      estimated=True),
    "3d20_w100": dict(clb=520.0, tile=622.0, xbar=60, pin_fanout=60, fb_fanout=60, fb_other=60,
                      sb=12, cb=26, sb_loads=555 / 200, cb_loads=1056 / 200, opin_loads=10, l16=15),
    "3d20own_w66": dict(clb=520.0, tile=577.9, xbar=60, pin_fanout=60, fb_fanout=60, fb_other=60,
                        sb=13, cb=9, sb_loads=360 / 132, cb_loads=348 / 132, opin_loads=7, l16=16),
    # Own-layer pins at 100 tracks, not generated or laid out: routing scaled from the
    # 66-track layout (63,540 um2 per layer x 100/66) on the 270,400 um2 layer core;
    # connection-block muxes from the 66-track ones x 100/66; switch blocks as 3d20_w100.
    "3d20own_w100": dict(clb=520.0, tile=605.6, xbar=60, pin_fanout=60, fb_fanout=60, fb_other=60,
                         sb=12, cb=13, sb_loads=555 / 200, cb_loads=348 / 132, opin_loads=10, l16=15,
                         estimated=True),
    "2d10_w84": dict(clb=495.9, tile=567.7, xbar=50, pin_fanout=60, fb_fanout=60, fb_other=0,
                     sb=11, cb=11, sb_loads=379 / 168, cb_loads=444 / 168, opin_loads=8, l16=16),
    # Stacked 10-LUT CLBs (stock LaZagna 3D, compare_2d_3d.py --stacked): the 2D CLB on each
    # layer, its pins reaching both layers' tracks; tile 1.041 x the 2D tile wide, as laid out
    # (the stacked tile layout). Muxes from LaZagna's stacked RTL (tasks_run/3d_3d_cb_cw_100_
    # 14x14_..._3d_clb_tile_w100_l4_stacked_vp_0.739_run1_2026-11-07_08:44:45): switch blocks
    # averaged over the 66 in the CLB-only columns (x 5-8, both layers), 11.87 inputs per mux,
    # 542 per block; connection blocks 1056 inputs per tile (cbx 520 + cby 536), about 26 per mux.
    # Signals change layers only in the routing (no crossing inside the CLB).
    "3d10stack_w100": dict(clb=495.9, tile=600.6, xbar=50, pin_fanout=60, fb_fanout=60, fb_other=0,
                           sb=12, cb=26, sb_loads=542 / 200, cb_loads=1056 / 200, opin_loads=10, l16=16,
                           stacked=True),
}

# Fabrics with custom switch blocks and vertical links between layers (run_4layer_7nm.sh), which
# LaZagna cannot generate RTL for: mux sizes and loads from VPR's routing graph
# (spice/rr_mux_sizes.py on clma, 2026-11-10; the same tool gives the RTL's numbers for 2d10_w100,
# sb 9.96 / cb 13.22, and 3d20_w100, sb 12.09 / cb 26.42). sb_loads and cb_loads are mux inputs
# per tile-layer over 2W: wire muxes x mean inputs, and IPIN inputs. Layer cores: the 2D CLB and
# the 20-LUT layer as laid out; the 40-LUT layer (80-input crossbar muxes) from
# cluster_size_model.general(), 520 x sqrt(1.22 / 1.06). Routing area per tile-layer scales with
# its mux inputs (SB + CB) from the fabric it is estimated from, so the bigger 3D muxes also make
# the tile wider. All estimated.
def _tile(core, ref_tile, ref_core, ref_inputs, inputs):
    return round(math.sqrt(core ** 2 + (ref_tile ** 2 - ref_core ** 2) * inputs / ref_inputs), 1)

FABRICS.update({
    # 2D, custom switch blocks: 45.5 wire muxes x 8.95, 542 IPIN inputs; tile from 2d10_w100 (RTL 460 + 528).
    "2d10c_w100": dict(clb=495.9, tile=_tile(495.9, 576.9, 495.9, 460 + 528, 408 + 542), xbar=50,
                       pin_fanout=60, fb_fanout=60, fb_other=0, sb=9, cb=13, sb_loads=408 / 200,
                       cb_loads=542 / 200, opin_loads=9, l16=16, estimated=True),
    # 20-LUT split, own-layer pins, vertical links: 45.5 x 15.69 = 714, 542; tile from 3d20own_w100
    # (550 + 542, the own-layer graph).
    "3d20ownc_w100": dict(clb=520.0, tile=_tile(520.0, 605.6, 520.0, 550 + 542, 714 + 542), xbar=60,
                          pin_fanout=60, fb_fanout=60, fb_other=60, sb=16, cb=13, sb_loads=714 / 200,
                          cb_loads=542 / 200, opin_loads=18, l16=15, estimated=True),
    # 40-LUT split over 4 layers (10 FLEs each, 40 own-layer pins + 40 feedback per crossbar mux):
    # 45.7 x 19.32 = 883, 535; tile from 3d20own_w100.
    "3d40own_w100": dict(clb=557.6, tile=_tile(557.6, 605.6, 520.0, 550 + 542, 883 + 535), xbar=80,
                         pin_fanout=60, fb_fanout=60, fb_other=60, layers=4, sb=19, cb=13,
                         sb_loads=883 / 200, cb_loads=535 / 200, opin_loads=22, l16=14, estimated=True),
    # Stacked 10-LUT CLBs on 4 layers: 45.6 x 19.16 = 874, 1355; tile from 3d10stack_w100 (RTL 542 + 1056).
    "3d10stack4_w100": dict(clb=495.9, tile=_tile(495.9, 600.6, 495.9, 542 + 1056, 874 + 1355), xbar=50,
                            pin_fanout=60, fb_fanout=60, fb_other=0, sb=19, cb=33, sb_loads=874 / 200,
                            cb_loads=1355 / 200, opin_loads=22, l16=16, stacked=True, estimated=True),
})

# Bond between layers: per side a via stack from met1 to met5 and a 2.5 um met5 pad
# (pnr/setup_pnr.py), plus the bond interface. BOND_R and BOND_C are assumptions.
PAD_UM = 2.5
BOND_R = 0.5       # ohm, Cu-Cu interface
BOND_C = 1.0       # fF, interface and pad overlap

# 7 nm fabrics: every length times S7, the 2D CLB's side in the ASAP7 layout (pnr/asap7, core
# 201.744 x 199.872 um in the kit's 4x units, so a quarter of that) over its sky130 side. The
# routing tiles were not laid out in ASAP7 and are taken to scale as the CLB does: estimated.
S7 = math.sqrt(201.744 * 199.872) / 4 / 495.9
for _name in ("2d10_w100", "2d12_w110", "3d20own_w100", "3d10stack_w100",
              "2d10c_w100", "3d20ownc_w100", "3d40own_w100", "3d10stack4_w100"):
    FABRICS[_name + "_7nm"] = dict(FABRICS[_name], clb=round(FABRICS[_name]["clb"] * S7, 2),
                                   tile=round(FABRICS[_name]["tile"] * S7, 2), kit="asap7", estimated=True)

HEADER = """* {title}
simulator lang=spice
.lib "{models}/sky130.lib.spice" {corner}
.temp 27
.param u=1e-6
.subckt inv a y vdd vss sz=1
xp y a vdd vdd pfet_01v8 l=0.15u w='sz*0.84*u'
xn y a vss vss nfet_01v8 l=0.15u w='sz*0.42*u'
.ends
.subckt tg a b en enb vdd vss
xn a en b vss nfet_01v8 l=0.15u w='0.42*u'
xp a enb b vdd pfet_01v8 l=0.15u w='0.84*u'
.ends
vdd vdd 0 {vdd}
vhi vhi 0 {vdd}
vlo vlo 0 0
"""
SKY130_HEADER = HEADER

ASAP7_HEADER = """* {title}
simulator lang=spice
.include "{models}/7nm_{corner_uc}_160803.pm"
.temp 25
.subckt inv a y vdd vss sz=1
mp y a vdd vdd pmos_rvt l=21n nfin='sz'
mn y a vss vss nmos_rvt l=21n nfin='sz'
.ends
.subckt tg a b en enb vdd vss
mn a en b vss nmos_rvt l=21n nfin=1
mp a enb b vdd pmos_rvt l=21n nfin=1
.ends
vdd vdd 0 {vdd}
vhi vhi 0 {vdd}
vlo vlo 0 0
"""


def use_kit(kit, pitch=None):
    """Sets the supply, unit inverter load, bond and simulation settings for sky130 or asap7.

    pitch: bond pitch in um, pads half the pitch (default: 5 um sky130, 1 um asap7, the values
    the delay sets were made with). Pad capacitance scales with pad area, the interface's with
    pad side (the same rule that set ASAP7_BOND_C from sky130's)."""
    global VDD, C_INV1, BOND_C, HEADER, SEG_UM, STEP, EDGE, PAD_UM, ASAP7_PAD_C
    if kit == "asap7":
        VDD, C_INV1, BOND_C, HEADER, SEG_UM, STEP, EDGE = 0.7, ASAP7_C_INV1, ASAP7_BOND_C, ASAP7_HEADER, 5, "0.1p", 10e-12
        side = (pitch or 1.0) / 2 / 0.5
        ASAP7_PAD_C *= side ** 2
        BOND_C *= side
    else:
        VDD, C_INV1, BOND_C, HEADER = 1.8, C_GATE * 3 * WN, 1.0, SKY130_HEADER
        SEG_UM, STEP, EDGE = 50, "1p", 40e-12
        PAD_UM = (pitch or 5.0) / 2
        BOND_C *= PAD_UM / 2.5


def read_tlef(path):
    """Per-micron R (ohm) and C (fF) of met2-met5, and via resistance met1 to met5."""
    layers, current = {}, None
    for line in Path(path).read_text().splitlines():
        start = re.match(r"\s*LAYER\s+(\S+)\s*$", line)
        if start:
            current = start.group(1)
            layers.setdefault(current, {})
            continue
        if current and re.match(rf"\s*END\s+{re.escape(current)}\b", line):
            current = None
            continue
        if current:
            for key, pattern in (("width", r"^\s*WIDTH\s+([\d.]+)\s*;"), ("rsq", r"RESISTANCE\s+RPERSQ\s+([\d.eE+-]+)"),
                                 ("carea", r"CAPACITANCE\s+CPERSQDIST\s+([\d.eE+-]+)"),
                                 ("cedge", r"EDGECAPACITANCE\s+([\d.eE+-]+)"),
                                 ("rcut", r"^\s*RESISTANCE\s+([\d.eE+-]+)\s*;")):
                found = re.search(pattern, line)
                if found and key not in layers[current]:
                    layers[current][key] = float(found.group(1))
    metals = {}
    for name in ("met2", "met3", "met4", "met5"):
        m = layers[name]
        metals[name] = m
    vias = sum(layers[v].get("rcut", 0.0) for v in ("mcon", "via", "via2", "via3", "via4") if v in layers)
    return metals, vias


def wire_rc(metals, name, width_factor=1.0, coupling=2.0):
    """Ohm and fF per micron of a wire on that metal; LEF caps are pF per um2 and pF per um."""
    m = metals[name]
    w = m["width"] * width_factor
    r = m["rsq"] / w
    c = (m["carea"] * w + 2 * m["cedge"]) * 1e3 * coupling
    return r, c


def wire_roles(kit, metals):
    """Ohm and fF per um for each kind of wire, and one bond pad's fF.

    local: CLB pin and feedback nets; route: L4 tracks; long: L16 tracks (double width and
    spacing); opin: FLE output to the tile edge; padwire: to the bond pad. sky130 puts them on
    met2, met3/met4, met3/met4 wide, met3 and met4; ASAP7 on M2/M3, M4/M5, M4/M5 wide (half
    the resistance, about the same capacitance), M4 and M5."""
    if kit == "asap7":
        lay = ASAP7_LAYERS
        def avg(a, b):
            return tuple((x + y) / 2 for x, y in zip(lay[a], lay[b]))
        route = avg("M4", "M5")
        return dict(local=avg("M2", "M3"), route=route, long=(route[0] / 2, route[1]),
                    opin=lay["M4"], padwire=lay["M5"], pad_c=ASAP7_PAD_C)
    return dict(local=wire_rc(metals, "met2"),
                route=tuple((a + b) / 2 for a, b in zip(wire_rc(metals, "met3"), wire_rc(metals, "met4"))),
                long=tuple((a + b) / 2 for a, b in zip(wire_rc(metals, "met3", 2.0, 1.5),
                                                       wire_rc(metals, "met4", 2.0, 1.5))),
                opin=wire_rc(metals, "met3"), padwire=wire_rc(metals, "met4"), pad_c=pad_cap(metals))


def chain(c_load, parity, stages=None, c_first=None):
    """Inverter sizes from size 1 for a load, stage effort near 4; parity 0 even, 1 odd stages.

    stages fixes the count, as for OpenFPGA's three-stage tap_buf4 on routing muxes."""
    c_first = c_first or C_INV1
    n = stages or max(1, round(math.log(max(c_load / c_first, 1.0)) / math.log(4)))
    if n % 2 != parity:
        n += 1
    f = (c_load / c_first) ** (1.0 / n)
    return [f ** i for i in range(n)]


class Deck:
    def __init__(self, title, models, corner):
        self.lines = [HEADER.format(title=title, models=models, corner=corner, corner_uc=corner.upper(), vdd=VDD)]
        self.count = 0
        self.measures = []

    def name(self, kind):
        self.count += 1
        return f"{kind}{self.count}"

    def add(self, text):
        self.lines.append(text)

    def inv(self, a, y, size=1.0):
        self.add(f"x{self.name('i')} {a} {y} vdd 0 inv sz={size:.4g}")

    def buffer(self, a, y, sizes):
        node = a
        for i, size in enumerate(sizes):
            out = y if i == len(sizes) - 1 else self.name("n")
            self.inv(node, out, size)
            node = out

    def tg(self, a, b, on):
        en, enb = ("vhi", "vlo") if on else ("vlo", "vhi")
        self.add(f"x{self.name('t')} {a} {b} {en} {enb} vdd 0 tg")

    def mux(self, inp, out, n, out_sizes):
        """OpenFPGA two-level mux, inputs plus one constant: input inverter, two pass gates, buffer."""
        m = n + 1
        branch = math.ceil(math.sqrt(m))
        groups = math.ceil(m / branch)
        a, level1, level2 = self.name("n"), self.name("n"), self.name("n")
        self.inv(inp, a)
        self.tg(a, level1, True)
        for _ in range(branch - 1):
            self.tg("0", level1, False)
        self.tg(level1, level2, True)
        for _ in range(groups - 1):
            self.tg("0", level2, False)
        self.buffer(level2, out, out_sizes)

    def wire(self, start, length, r_um, c_um, loads, segments=None, end=None):
        """RC ladder; loads is a list of (fraction along the wire, inverter count). Returns end node."""
        segments = segments or max(4, int(length / SEG_UM))
        nodes = [start] + [self.name("w") for _ in range(segments)]
        if end:
            nodes[-1] = end
        r, c = r_um * length / segments, c_um * length / segments
        for i in range(segments):
            self.add(f"r{self.name('r')} {nodes[i]} {nodes[i + 1]} {r:.4g}")
            self.add(f"c{self.name('c')} {nodes[i + 1]} 0 {c:.4g}f")
        for fraction, count in loads:
            node = nodes[min(segments, max(1, round(fraction * segments)))]
            for _ in range(count):
                self.inv(node, self.name("ld"))
        return nodes[-1]

    def source(self, node, edge=None, sizes=(1, 4)):
        edge = edge or EDGE
        self.add(f"vsrc src 0 pulse(0 {VDD} 1n {edge} {edge} 3n 8n)")
        self.buffer("src", node, list(sizes))

    def measure(self, name, start, end):
        for k in (1, 2):
            self.measures.append(f".measure tran {name}_{k} trig v({start}) val={VDD / 2} cross={k} "
                                 f"targ v({end}) val={VDD / 2} cross={k}")

    def text(self, stop="10n"):
        return "\n".join(self.lines + [f".tran {STEP} {stop}"] + self.measures + [".end", ""])


def routing_hop(d, start, f, wires, length_tiles, wire, loads_every, name, end=None):
    """SB mux, tapered driver, wire over length_tiles tiles with mux-input loads. Returns end node."""
    r_um, c_um = wire
    length = length_tiles * f["tile"]
    per_tile = []
    for t in range(1, length_tiles + 1):
        if t % loads_every == 0 or t == length_tiles:
            count = round(f["sb_loads"] + (f["cb_loads"] if loads_every == 1 else 0))
            per_tile.append((t / length_tiles, count))
    c_load = c_um * length + C_INV1 * sum(c for _, c in per_tile)
    drv = d.name("drv")
    d.mux(start, drv, f["sb"], chain(c_load, 1, stages=3))
    return d.wire(drv, length, r_um, c_um, per_tile, end=end)


def crossing(d, start, wires, vias, c_after, wire_um):
    """Driver, wire to the pad, via stacks, pads and bond, receiver sized for c_after."""
    r4, c4 = wires["padwire"]
    pad_c = wires["pad_c"]
    c_pad_side = c4 * wire_um + pad_c
    a = d.name("x")
    d.buffer(start, a, chain(c_pad_side + BOND_C + pad_c + C_INV1, 0))
    p0 = d.wire(a, wire_um, r4, c4, []) if wire_um > 0 else a
    p1, p2, p3 = d.name("p"), d.name("p"), d.name("p")
    d.add(f"r{d.name('r')} {p0} {p1} {vias:.4g}")
    d.add(f"c{d.name('c')} {p1} 0 {pad_c + BOND_C / 2:.4g}f")
    d.add(f"r{d.name('r')} {p1} {p2} {BOND_R}")
    d.add(f"c{d.name('c')} {p2} 0 {pad_c + BOND_C / 2:.4g}f")
    d.add(f"r{d.name('r')} {p2} {p3} {vias:.4g}")
    out = d.name("rx")
    d.buffer(p3, out, chain(c_after, 0))
    return out


def pad_cap(metals):
    m5 = metals["met5"]
    return (m5["carea"] * PAD_UM ** 2 + m5["cedge"] * 4 * PAD_UM) * 1e3


def bond(d, start, wires, vias):
    """Via stack, pad, bond, pad, via stack: the bond as a via, with no driver or receiver."""
    p1, p2, p3 = d.name("p"), d.name("p"), d.name("p")
    d.add(f"r{d.name('r')} {start} {p1} {vias:.4g}")
    d.add(f"c{d.name('c')} {p1} 0 {wires['pad_c'] + BOND_C / 2:.4g}f")
    d.add(f"r{d.name('r')} {p1} {p2} {BOND_R}")
    d.add(f"c{d.name('c')} {p2} 0 {wires['pad_c'] + BOND_C / 2:.4g}f")
    d.add(f"r{d.name('r')} {p2} {p3} {vias:.4g}")
    return p3


def decks(fabric, f, wires, vias, models, corner):
    m2, m34, long34 = wires["local"], wires["route"], wires["long"]
    out = {}

    # Routing: two hops in a row, the second measured from SB mux input to the next one's.
    # In 3D each style of crossing gets its own deck: the direct bond's pads load the hop's end,
    # which an as-laid-out fabric (crossing driver's input only) does not have. With 5-10 um pads
    # at 7 nm that load is several fF.
    for seg, tiles, wire, every in (("l4", 4, m34, 1), ("l16", f["l16"], long34, 4)):
        three_d = f["fb_other"] or f.get("stacked")
        for style in ("laid", "direct") if three_d else ("laid",):
            d = Deck(f"{fabric} {seg} hop" + (", bond as a via" if style == "direct" else ""), models, corner)
            d.source("s0")
            a = routing_hop(d, "s0", f, wires, tiles, wire, every, seg)
            b = routing_hop(d, a, f, wires, tiles, wire, every, seg, end="hopend")
            d.inv("hopend", d.name("ld"))
            if style == "laid":
                d.measure(seg, a, "hopend")
                if three_d:
                    # The same hop crossing layers at its end: driver, bond, receiver into the next mux input.
                    x = crossing(d, "hopend", wires, vias, C_INV1 * 2, 0)
                    d.measure(f"{seg}_cross", "hopend", x)
                out[seg] = d
            else:
                # Direct: the wire end goes through the bond into the next mux's input inverter.
                d.measure(f"{seg}_via", a, "hopend")
                y = bond(d, "hopend", wires, vias)
                d.inv(y, d.name("ld"))
                d.measure(f"{seg}_direct", "hopend", y)
                out[f"{seg}_direct"] = d

    # Connection block, CLB input pin net, crossbar mux, LUT input.
    d = Deck(f"{fabric} connection block and crossbar from a pin", models, corner)
    d.source("s0")
    track = routing_hop(d, "s0", f, wires, 4, m34, 1, "l4")
    c_pin = m2[1] * f["clb"] + C_INV1 * f["pin_fanout"]
    d.mux(track, "pin", f["cb"], chain(c_pin, 1, stages=3))
    far = d.wire("pin", f["clb"], *m2, [(i / f["pin_fanout"], 1) for i in range(1, f["pin_fanout"])], end="xin")
    d.mux(far, "lutin", f["xbar"], [1])
    d.inv("lutin", d.name("ld"), 1)
    d.inv("lutin", d.name("ld"), 1)
    d.measure("cb", track, "pin")
    d.measure("xbar_pin", "pin", "lutin")
    out["cb"] = d

    # FLE output mux and driver, feedback net, crossbar mux; in 3D also across the bond.
    d = Deck(f"{fabric} feedback", models, corner)
    d.source("lutout", sizes=(1, 1))
    r3, c3 = wires["opin"]
    opin_wire = f["tile"] / 2
    c_fb = m2[1] * f["clb"] + C_INV1 * f["fb_fanout"] + c3 * opin_wire + C_INV1 * f["opin_loads"]
    # A split CLB over more than two layers: a middle layer's FLE output drives a crossing driver
    # towards each neighbour, and each receiver also feeds the next crossing (one per layer crossed,
    # as VPR's layer_crossing_delay charges it).
    layers = f.get("layers", 2)
    c_fb += C_INV1 * (2 if layers > 2 else 1) if f["fb_other"] else 0
    d.mux("lutout", "fleout", 2, chain(c_fb, 1))
    d.wire("fleout", opin_wire, r3, c3, [(1.0, f["opin_loads"])])
    far = d.wire("fleout", f["clb"], *m2, [(i / f["fb_fanout"], 1) for i in range(1, f["fb_fanout"])], end="xin")
    d.mux(far, "lutin", f["xbar"], [1])
    d.inv("lutin", d.name("ld"))
    d.inv("lutin", d.name("ld"))
    d.measure("ble", "lutout", "fleout")
    d.measure("xbar_fb", "fleout", "lutin")
    if f["fb_other"]:
        c_other = m2[1] * f["clb"] + C_INV1 * f["fb_other"] + (C_INV1 if layers > 2 else 0)
        rx = crossing(d, "fleout", wires, vias, c_other, f["clb"] / 2)
        far2 = d.wire(rx, f["clb"], *m2, [(i / f["fb_other"], 1) for i in range(1, f["fb_other"])], end="xin2")
        d.mux(far2, "lutin2", f["xbar"], [1])
        d.inv("lutin2", d.name("ld"))
        d.inv("lutin2", d.name("ld"))
        d.measure("xbar_fb_cross", "fleout", "lutin2")
    out["fb"] = d

    # 3D with a direct crossing: one driver, sized for both layers' nets, reaches the
    # other layer through the bond (a via stack and pads), with no receiver.
    if f["fb_other"]:
        d = Deck(f"{fabric} feedback, direct crossing", models, corner)
        d.source("lutout", sizes=(1, 1))
        r4, c4 = wires["padwire"]
        pad_wire = f["clb"] / 2
        # Over more than two layers the bottom layer's driver reaches every layer through the bonds
        # in series, measured to the farthest. make_spice charges that whole extra delay for each
        # layer crossed (conservative: the nearer layers are reached sooner).
        other = c4 * pad_wire + 2 * wires["pad_c"] + BOND_C + m2[1] * f["clb"] + C_INV1 * f["fb_other"]
        c_both = c_fb - C_INV1 * (2 if layers > 2 else 1) + other * (layers - 1)
        d.mux("lutout", "fleout", 2, chain(c_both, 1))
        d.wire("fleout", opin_wire, r3, c3, [(1.0, f["opin_loads"])])
        far = d.wire("fleout", f["clb"], *m2, [(i / f["fb_fanout"], 1) for i in range(1, f["fb_fanout"])], end="xin")
        d.mux(far, "lutin", f["xbar"], [1])
        d.inv("lutin", d.name("ld"))
        d.inv("lutin", d.name("ld"))
        node = "fleout"
        for k in range(1, layers):
            node = bond(d, d.wire(node, pad_wire, r4, c4, []), wires, vias)
            last = k == layers - 1
            far2 = d.wire(node, f["clb"], *m2, [(i / f["fb_other"], 1) for i in range(1, f["fb_other"])],
                          end="xin2" if last else None)
            if not last:
                d.inv(far2, d.name("ld"))   # that layer's last crossbar mux input
        d.mux(far2, "lutin2", f["xbar"], [1])
        d.inv("lutin2", d.name("ld"))
        d.inv("lutin2", d.name("ld"))
        d.measure("ble_direct", "lutout", "fleout")
        d.measure("xbar_fb_direct", "fleout", "lutin")
        d.measure("xbar_fb_cross_direct", "fleout", "lutin2")
        out["fbd"] = d

    # LUT: one six-input tree per input, the other inputs at 0, contents making out = in[k].
    d = Deck(f"{fabric} LUT", models, corner)
    d.source("s0")
    for k in range(6):
        pin = d.name("n")
        d.mux("s0", pin, f["xbar"], [1])      # the crossbar mux that drives this LUT input
        rails = {}
        for j in range(6):
            load = 2 ** (5 - j) * C_INV1   # 2^(5-j) pass gates' n and p gates (each a unit inverter's)
            src = pin if j == k else "vlo"
            true_rail, comp_rail = d.name("t"), d.name("c")
            d.buffer(src, true_rail, chain(load, 0))
            d.buffer(src, comp_rail, chain(load, 1))
            rails[j] = (true_rail, comp_rail)
        level = ["vhi" if (i >> k) & 1 else "vlo" for i in range(64)]
        for j in range(6):
            nxt = []
            for i in range(0, len(level), 2):
                node = d.name("q")
                t, c = rails[j]
                d.add(f"x{d.name('t')} {level[i + 1]} {node} {t} {c} vdd 0 tg")
                d.add(f"x{d.name('t')} {level[i]} {node} {c} {t} vdd 0 tg")
                nxt.append(node)
            level = nxt
        out_node = f"lut{k}"
        d.inv(level[0], out_node)
        d.inv(out_node, d.name("ld"))
        d.inv(out_node, d.name("ld"))
        d.measure(f"lut{k}", pin, out_node)
    out["lut"] = d
    return out


def run(deck_path, env):
    """Runs Spectre on a deck and returns its measures in seconds."""
    folder = deck_path.parent
    subprocess.run(["tcsh", "-fc", f"unsetenv ENV_SETUP; source envsetup >& /dev/null; cd {folder}; "
                    f"nice +10 spectre -64 {deck_path.name} +escchars =log {deck_path.stem}.log >& /dev/null"],
                   cwd=env, check=False)
    log = (folder / f"{deck_path.stem}.log").read_text(errors="replace")
    if "completes with 0 errors" not in log:
        raise SystemExit(f"{deck_path}: Spectre failed, see {deck_path.stem}.log")
    values = {}
    for line in (folder / f"{deck_path.stem}.measure").read_text().splitlines():
        found = re.match(r"\s*(\w+)\s+=\s+([-\d.eE+]+)", line)
        if found:
            values[found.group(1)] = float(found.group(2))
    return values


def worst(values, name):
    edges = [values.get(f"{name}_{k}") for k in (1, 2)]
    if None in edges:
        raise SystemExit(f"measure {name} missing: {values}")
    return max(edges) * 1e12


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", required=True, help="folder holding sky130.lib.spice (or 7nm_TT_160803.pm)")
    parser.add_argument("--tlef", help="sky130's tech LEF, for wire R and C (not needed for *_7nm)")
    parser.add_argument("--env", required=True, help="a SiliconJackets block folder whose envsetup loads Spectre")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fabric", nargs="+", default=list(FABRICS))
    parser.add_argument("--corner", default="tt")
    parser.add_argument("--pitch", type=float,
                        help="bond pitch in um, pads half of it (default 5 for sky130, 1 for 7 nm)")
    args = parser.parse_args()
    kits = {FABRICS[fabric].get("kit", "sky130") for fabric in args.fabric}
    if len(kits) != 1:
        raise SystemExit("run sky130 and 7 nm fabrics separately")
    kit = kits.pop()
    use_kit(kit, args.pitch)
    if kit == "asap7":
        wires, vias = wire_roles(kit, None), ASAP7_VIAS
    else:
        if not args.tlef:
            raise SystemExit("--tlef is needed for sky130 fabrics")
        metals, vias = read_tlef(args.tlef)
        wires = wire_roles(kit, metals)
    results = {}
    for fabric in args.fabric:
        f = FABRICS[fabric]
        folder = args.out / f"{fabric}_{args.corner}"
        folder.mkdir(parents=True, exist_ok=True)
        values = {}
        for key, d in decks(fabric, f, wires, vias, args.models, args.corner).items():
            path = folder / f"{key}.sp"
            path.write_text(d.text("20n" if key.startswith("l16") else "10n"))
            values.update(run(path, args.env))
        res = {name: round(worst(values, name), 2) for name in
               ["l4", "l16", "cb", "xbar_pin", "ble", "xbar_fb"] + [f"lut{k}" for k in range(6)]}
        if kit == "asap7":
            res.update(ASAP7_FF)
        if f["fb_other"]:
            res["clb_crossing"] = round(worst(values, "xbar_fb_cross") - res["xbar_fb"], 2)
            res["route_crossing"] = round(worst(values, "l4_cross"), 2)
            res["crossing_over_l4"] = round(res["route_crossing"] / res["l4"], 3)
            # The same fabric with direct crossings (the bond as a via, no receivers).
            direct = dict(res, l4=round(worst(values, "l4_via"), 2), l16=round(worst(values, "l16_via"), 2))
            direct["ble"] = round(worst(values, "ble_direct"), 2)
            direct["xbar_fb"] = round(worst(values, "xbar_fb_direct"), 2)
            direct["clb_crossing"] = round(worst(values, "xbar_fb_cross_direct") - direct["xbar_fb"], 2)
            direct["route_crossing"] = round(worst(values, "l4_direct"), 2)
            direct["crossing_over_l4"] = round(direct["route_crossing"] / direct["l4"], 3)
            direct["estimated_geometry"] = bool(f.get("estimated"))
            results[fabric + "_direct"] = direct
            print(fabric + "_direct", json.dumps(direct), flush=True)
        elif f.get("stacked"):
            # Stacked CLBs cross layers only in the routing; direct is the bond as a via there.
            res["route_crossing"] = round(worst(values, "l4_cross"), 2)
            res["crossing_over_l4"] = round(res["route_crossing"] / res["l4"], 3)
            direct = dict(res, route_crossing=round(worst(values, "l4_direct"), 2),
                          l4=round(worst(values, "l4_via"), 2), l16=round(worst(values, "l16_via"), 2),
                          estimated_geometry=bool(f.get("estimated")))
            direct["crossing_over_l4"] = round(direct["route_crossing"] / direct["l4"], 3)
            results[fabric + "_direct"] = direct
            print(fabric + "_direct", json.dumps(direct), flush=True)
        res["estimated_geometry"] = bool(f.get("estimated"))
        results[fabric] = res
        print(fabric, json.dumps(res), flush=True)
    (args.out / f"delays_{args.corner}.json").write_text(json.dumps(results, indent=1) + "\n")


if __name__ == "__main__":
    main()
