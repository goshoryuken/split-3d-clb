#!/usr/bin/env python3
"""The in-CLB layer crossing in SPICE, stage by stage, and moved towards the layout one step at a time.

Builds make_spice.py's feedback deck for one split fabric (default 3d20own_w100) with a measure at
every stage boundary, in the same order as the layout's worst crossing path
(pnr/crossing_stages_layout.py):

  crossing path, from the FLE output net (fleout):
    [inserted buffer] -> crossing driver -> wire to the pad -> via stacks, pads, bond -> receiver
    -> [inserted buffer] -> far net (wire and loads) -> far crossbar mux out
  same-layer path, from fleout: own net (wire and loads) -> own crossbar mux out

The crossing is VPR's clb_crossing: worst edge of the crossing path minus worst edge of the
same-layer path, as make_spice.py. Each stage's load (what it drives, chain sizes, wire R and C)
goes into the deck as comments and into the JSON.

Variants (each changes one thing from the one before; custom circuits sized as make_spice):
  base      make_spice.py as is; must give delays_tt.json's clb_crossing
  bondnet   the bond net's capacitance set to the layout's (--bond-pf), driver sized for it
  farnet    also the other layer's net set to the layout's (--other-pf plus the second inserted
            buffer's load, which Innovus split off it), receiver sized for it
  ownnet    also the FLE's own-layer net set to the layout's (--own-pf plus the first inserted
            buffer's load), FLE driver sized for it: the same kind of load on both layers, so
            the subtraction stays like for like
Extra capacitance is spread evenly along the existing 520 um net, without the extra wire
resistance a longer wire would add.

--cells CDL... adds two variants built from the standard cells the layout used, on the layout's
loads (cells read at run time from the kit's CDL netlists, never stored here):
  cells     crossing driver INVX1 -> INVX2, receiver BUFX16_HS, no inserted buffers
  cells+ins also Innovus's BUFX8_HS before the driver and CLKBUFX2_HS after the receiver, each
            driving its own load (--ins-pf): the layout's worst path, to set beside Tempus's
In the cells variants a cell's input pin is counted in the layout's load and again by the cell
itself, a few fF high per net.

Loads come from the layout's worst crossing path (pnr/crossing_path_local20_center.txt): what the
FLE output driver drives (--own-pf), the bond net (--bond-pf), what the receiver drives
(--other-pf), and what the two inserted buffers drive (--ins-pf).

Usage (on the server, like make_spice.py; spice/run_crossing_stages.sh does it all):
  crossing_stages.py --models DIR --tlef FILE --env BLOCK_DIR --out DIR
      [--fabric 3d20own_w100] [--corner tt] [--bond-pf PF] [--other-pf PF] [--own-pf PF]
      [--ins-pf PF PF] [--cells CDL...] [--loads-only]
--loads-only writes the decks and prints the loads without running Spectre.
Writes OUT/crossing_stages_<fabric>_<corner>.json and prints the tables.
"""
import argparse
import json
import math
import re
from pathlib import Path

import make_spice as ms

CROSS_STAGES = [("s_ins1", "inserted buffer (Innovus)"), ("s_driver", "crossing driver"),
                ("s_padwire", "wire to the pad"), ("s_bond", "via stacks, pads, bond"),
                ("s_receiver", "receiver"), ("s_ins2", "inserted buffer (Innovus)"),
                ("s_far_net", "far net (wire, loads)"), ("s_far_mux", "far crossbar mux")]
SAME_STAGES = [("s_own_net", "own net (wire, loads)"), ("s_own_mux", "own crossbar mux")]
CELLS = dict(fle="BUFX16_HS", drv1="INVX1", drv2="INVX2", rx="BUFX16_HS", ins1="BUFX8_HS", ins2="CLKBUFX2_HS")


def fb_deck(fabric, f, wires, vias, models, corner, bond_pf=None, other_pf=None, own_pf=None, cells=None,
            ins_pf=None):
    """make_spice.decks()'s feedback deck with stage measures and loads; circuits as the variant says.

    own_pf, other_pf: the whole own-layer and far-layer nets' pF (with ins_pf, the part left to
    the FLE driver and the receiver after Innovus's buffers took theirs)."""
    m2 = wires["local"]
    d = ms.Deck(f"{fabric} feedback crossing, stage by stage", models, corner)
    if cells:
        d.add(cells["text"])
    loads = {}
    d.source("lutout", sizes=(1, 1))
    r3, c3 = wires["opin"]
    opin_wire = f["tile"] / 2
    clb = f["clb"]
    c_fb_model = m2[1] * clb + ms.C_INV1 * f["fb_fanout"] + c3 * opin_wire + ms.C_INV1 * f["opin_loads"]
    c_fb = c_fb_model + ms.C_INV1   # the crossing driver's input, as make_spice (two layers)
    own_extra = max(0.0, own_pf * 1e3 - c_fb) if own_pf else 0.0
    if cells:   # the layout's FLE output: the mux's last inverter (tap_buf4, INVX2_HS), then BUFX16_HS
        fle_sizes = f"mux out 2 -> {CELLS['fle']}"
        d.mux("lutout", "fle0", 2, [2])
        inst(d, cells, "fle", "fle0", "fleout")
    else:
        fle_sizes = ms.chain(c_fb + own_extra, 1)
        d.mux("lutout", "fleout", 2, fle_sizes)
    d.wire("fleout", opin_wire, r3, c3, [(1.0, f["opin_loads"])])
    far = d.wire("fleout", clb, *m2, [(i / f["fb_fanout"], 1) for i in range(1, f["fb_fanout"])], end="xin")
    spread(d, "fleout", far, own_extra)
    d.mux(far, "lutin", f["xbar"], [1])
    d.inv("lutin", d.name("ld"))
    d.inv("lutin", d.name("ld"))
    loads["fle_driver"] = dict(drives_fF=c_fb + own_extra, model_fF=c_fb, sizes=fle_sizes)
    loads["s_own_net"] = dict(um=clb, R_ohm=m2[0] * clb, wire_fF=m2[1] * clb, unit_loads=f["fb_fanout"] - 1,
                              opin_um=opin_wire, opin_wire_fF=c3 * opin_wire, opin_loads=f["opin_loads"],
                              extra_fF=own_extra, total_fF=m2[1] * clb + ms.C_INV1 * f["fb_fanout"] + own_extra)
    loads["s_own_mux"] = dict(inputs=f["xbar"], out_sizes=[1], drives="two unit inverters")

    # Crossing: make_spice.crossing() with its nodes named.
    r4, c4 = wires["padwire"]
    pad_c = wires["pad_c"]
    wire_um = clb / 2
    c_pad_side = c4 * wire_um + pad_c
    c_bond_model = c_pad_side + ms.BOND_C + pad_c + ms.C_INV1
    bond_extra = max(0.0, bond_pf * 1e3 - c_bond_model) if bond_pf else 0.0
    c_other_model = m2[1] * clb + ms.C_INV1 * f["fb_other"]
    other_extra = max(0.0, other_pf * 1e3 - c_other_model) if other_pf else 0.0
    start = "fleout"
    if ins_pf:   # Innovus's buffer between the FLE net and the driver, with the loads it took
        inst(d, cells, "ins1", "fleout", "xb")
        d.add(f"c{d.name('c')} xb 0 {ins_pf[0] * 1e3:.4g}f")
        loads["s_ins1"] = dict(cell=CELLS["ins1"], drives_fF=ins_pf[0] * 1e3)
        start = "xb"
    if cells:
        inst(d, cells, "drv1", start, "xdn")
        inst(d, cells, "drv2", "xdn", "xdrv")
        loads["s_driver"] = dict(cells=f"{CELLS['drv1']} -> {CELLS['drv2']}", drives_fF=c_bond_model + bond_extra)
    else:
        sizes = ms.chain(c_bond_model + bond_extra, 0)
        d.buffer(start, "xdrv", sizes)
        loads["s_driver"] = dict(sizes=sizes, drives_fF=c_bond_model + bond_extra, model_fF=c_bond_model)
    d.wire("xdrv", wire_um, r4, c4, [], end="pw")
    loads["s_padwire"] = dict(um=wire_um, R_ohm=r4 * wire_um, wire_fF=c4 * wire_um)
    d.add(f"r{d.name('r')} pw p1 {vias:.4g}")
    d.add(f"c{d.name('c')} p1 0 {pad_c + ms.BOND_C / 2:.4g}f")
    d.add(f"r{d.name('r')} p1 p2 {ms.BOND_R}")
    d.add(f"c{d.name('c')} p2 0 {pad_c + ms.BOND_C / 2:.4g}f")
    d.add(f"r{d.name('r')} p2 pad {vias:.4g}")
    if bond_extra:
        d.add(f"c{d.name('c')} pad 0 {bond_extra:.4g}f")   # the layout's bond net beyond the model's
    loads["s_bond"] = dict(via_stack_ohm=vias, bond_ohm=ms.BOND_R, pad_fF=pad_c, bond_fF=ms.BOND_C,
                           extra_fF=bond_extra, total_fF=2 * pad_c + ms.BOND_C + bond_extra)
    if cells:
        inst(d, cells, "rx", "pad", "rx0")
        loads["s_receiver"] = dict(cell=CELLS["rx"], drives_fF=c_other_model + other_extra)
    else:
        sizes = ms.chain(c_other_model + other_extra, 0)
        d.buffer("pad", "rx0", sizes)
        loads["s_receiver"] = dict(sizes=sizes, drives_fF=c_other_model + other_extra, model_fF=c_other_model)
    # Innovus's second buffer sits at the far end of the receiver's net and drives the last mux input.
    end = "xb2" if ins_pf else "xin2"
    far2 = d.wire("rx0", clb, *m2, [(i / f["fb_other"], 1) for i in range(1, f["fb_other"])], end=end)
    spread(d, "rx0", far2, other_extra)
    loads["s_far_net"] = dict(um=clb, R_ohm=m2[0] * clb, wire_fF=m2[1] * clb, unit_loads=f["fb_other"] - 1,
                              extra_fF=other_extra, total_fF=c_other_model + other_extra)
    if ins_pf:
        inst(d, cells, "ins2", "xb2", "xin2")
        d.add(f"c{d.name('c')} xin2 0 {ins_pf[1] * 1e3:.4g}f")
        loads["s_ins2"] = dict(cell=CELLS["ins2"], drives_fF=ins_pf[1] * 1e3)
    d.mux("xin2", "lutin2", f["xbar"], [1])
    d.inv("lutin2", d.name("ld"))
    d.inv("lutin2", d.name("ld"))
    loads["s_far_mux"] = dict(inputs=f["xbar"], out_sizes=[1], drives="two unit inverters")

    d.measure("same", "fleout", "lutin")
    d.measure("s_own_net", "fleout", "xin")
    d.measure("s_own_mux", "xin", "lutin")
    d.measure("cross", "fleout", "lutin2")
    bounds = ([("s_ins1", "fleout", "xb")] if ins_pf else []) + [
        ("s_driver", start, "xdrv"), ("s_padwire", "xdrv", "pw"), ("s_bond", "pw", "pad"),
        ("s_receiver", "pad", "rx0"), ("s_far_net", "rx0", end)] + (
        [("s_ins2", "xb2", "xin2")] if ins_pf else []) + [("s_far_mux", "xin2", "lutin2")]
    for name, a, b in bounds:
        d.measure(name, a, b)
    loads = {k: {key: (round(v, 2) if isinstance(v, float) else [round(s, 3) for s in v] if isinstance(v, list) else v)
                 for key, v in load.items()} for k, load in loads.items()}
    for k, load in loads.items():
        d.add(f"* load {k}: {json.dumps(load)}")
    return d, loads


def spread(d, near, far, extra_ff, pieces=10):
    """Adds extra_ff of capacitance in equal parts along the wire from near to far (its ladder nodes)."""
    if extra_ff <= 0:
        return
    nodes = wire_nodes(d, near, far)
    picks = [nodes[min(len(nodes) - 1, round((i + 1) * len(nodes) / pieces) - 1)] for i in range(pieces)]
    for node in picks:
        d.add(f"c{d.name('c')} {node} 0 {extra_ff / pieces:.4g}f")


def wire_nodes(d, near, far):
    """Nodes of the RC ladder from near to far, in order, read back from the deck's resistors."""
    nxt = {}
    for line in d.lines:
        found = re.match(r"r(r\d+) (\S+) (\S+) ", line)
        if found:
            nxt.setdefault(found.group(2), []).append(found.group(3))
    for first in nxt.get(near, []):   # a node can start several ladders (the FLE output: opin and feedback)
        nodes = [first]
        while nodes[-1] != far and len(nxt.get(nodes[-1], [])) == 1:
            nodes.append(nxt[nodes[-1]][0])
        if nodes[-1] == far:
            return nodes
    raise SystemExit(f"no ladder from {near} to {far}")


# Standard cells from the kit's CDL, turned into Spectre SPICE with the deck's device models.
POWER, GROUND = {"VDD", "VPWR", "VPB", "VCC"}, {"VSS", "VGND", "VNB", "GND"}
INPUTS, OUTPUTS = {"A", "I", "IN", "A0"}, {"Y", "Z", "X", "ZN", "OUT"}


def std_cells(cdl_paths, names):
    """{'text': subcircuits, 'ports': {cell: ports}} for the named cells, first CDL that has each."""
    texts = [re.sub(r"\n\+", " ", Path(p).read_text(errors="replace")) for p in cdl_paths]
    out, ports = [], {}
    for name in names:
        for text in texts:
            found = re.search(rf"^\.SUBCKT\s+{re.escape(name)}\s+(.*?)$(.*?)^\.ENDS", text, re.M | re.S | re.I)
            if found:
                break
        else:
            raise SystemExit(f"{name} is in none of {cdl_paths}")
        ports[name] = found.group(1).split()
        body = [device(line, name) for line in found.group(2).splitlines()
                if line.strip() and not line.lstrip().startswith(("*", "$", "."))]
        out.append(f".subckt {name} {' '.join(ports[name])}\n" + "\n".join(body) + f"\n.ends {name}")
    return dict(text="\n".join(out), ports=ports)


def device(line, cell):
    """One CDL transistor line as an instance of the deck's model subcircuit (sky130 wraps its models)."""
    tokens = line.split("$")[0].split()
    if not tokens[0][0] in "mM":
        raise SystemExit(f"{cell}: only flat transistor cells are handled, found: {line.strip()}")
    name, nodes, model = tokens[0], tokens[1:5], tokens[5]
    model = model.split("__")[-1]
    model = {"nshort": "nfet_01v8", "pshort": "pfet_01v8"}.get(model.lower(), model)
    params = []
    for item in tokens[6:]:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = {"m": "mult"}.get(key.lower(), key.lower())
        if key not in ("w", "l", "nf", "mult", "ad", "as", "pd", "ps"):
            continue
        if re.fullmatch(r"[-+\d.eE]+", value):   # a bare number: metres in an SI CDL, else microns
            number = float(value)
            if key in ("w", "l", "pd", "ps") and number >= 1e-3:
                value += "u"
            elif key in ("ad", "as") and number >= 1e-9:
                value += "p"
        params.append(f"{key}={value}")
    return f"x{name} {' '.join(nodes)} {model} {' '.join(params)}"


def inst(d, cells, role, a, y):
    cell = CELLS[role]
    nodes = []
    for port in cells["ports"][cell]:
        p = port.upper()
        nodes.append("vdd" if p in POWER else "0" if p in GROUND else a if p in INPUTS else y if p in OUTPUTS else None)
        if nodes[-1] is None:
            raise SystemExit(f"{cell}: port {port} is not input, output, power or ground")
    d.add(f"x{d.name(role)} {' '.join(nodes)} {cell}")


def table(results):
    """Stage rows, variant columns: delay on the crossing path's slower edge / load driven (fF)."""
    names = [n for n in results if "error" not in results[n]]
    width = 18
    lines = [f"{'stage':26}" + "".join(f"{n:>{width}}" for n in names)]

    def row(label, cell):
        lines.append(f"{label:26}" + "".join(f"{cell(results[n]):>{width}}" for n in names))

    def stage(k):
        def cell(r):
            if k not in r["stages_worst_edge"]:
                return "-"
            load = r["loads"].get(k, {})
            fF = load.get("drives_fF", load.get("total_fF", load.get("wire_fF")))
            delay = f"{r['stages_worst_edge'][k]:.0f}" if "stages_worst_edge" in r else "?"
            return f"{delay} / {fF:.0f}" if fF is not None else delay
        return cell

    lines.append("crossing path (ps / fF driven or wire fF)")
    for k, label in CROSS_STAGES:
        if any(k in results[n].get("stages_worst_edge", {}) for n in names):
            row("  " + label, stage(k))
    row("  sum of stages", lambda r: f"{sum(v for s, v in r['stages_worst_edge'].items() if s in dict(CROSS_STAGES)):.0f}")
    row("  measured, that edge", lambda r: f"{r['edges'][r['worst_edge']]['cross']:.0f}")
    lines.append("same-layer path")
    for k, label in SAME_STAGES:
        row("  " + label, lambda r, k=k: f"{r['edges'][r['worst_edge']][k]:.0f}")
    row("  measured, that edge", lambda r: f"{r['edges'][r['worst_edge']]['same']:.0f}")
    lines.append("worst edge of each, as make_spice")
    row("  crossing path", lambda r: f"{r['cross']:.1f}")
    row("  same layer", lambda r: f"{r['same']:.1f}")
    row("  clb_crossing", lambda r: f"{r['clb_crossing']:.1f}")
    row("FLE driver drives fF", lambda r: f"{r['loads']['fle_driver']['drives_fF']:.0f}")
    for n, r in results.items():
        if "error" in r:
            lines.append(f"{n}: {r['error']}")
    return "\n".join(lines)


def loads_table(results):
    names = list(results)
    keys = ["fle_driver"] + [k for k, _ in CROSS_STAGES] + [k for k, _ in SAME_STAGES]
    lines = []
    for k in keys:
        for n in names:
            load = results[n].get("loads", {}).get(k)
            if load:
                lines.append(f"{n:10} {k:12} {json.dumps(load)}")
    return "\n".join(lines)


def split_wide(text, most=100):
    """Splits an inverter too wide for the transistor models into equal ones in parallel.

    make_spice's inv makes its pfet sz x 0.84 um wide, and sky130's models stop at 100 um, so a
    chain sized for a big load (the FLE driver for 0.79 pF ends at sz 150) fails in Spectre. Parallel
    copies with the same input and output are the same inverter. make_spice's own decks never get
    there, so the base variant is unchanged.
    """
    out = []
    for line in text.splitlines():
        found = re.match(r"(x\S+)(\s+\S+\s+\S+\s+\S+\s+\S+\s+inv\s+)sz=([\d.]+)\s*$", line)
        k = math.ceil(float(found.group(3)) / most) if found else 1
        if k <= 1:
            out.append(line)
            continue
        size = float(found.group(3)) / k
        out += [f"{found.group(1)}_{i}{found.group(2)}sz={size:.4g}" for i in range(k)]
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", required=True)
    parser.add_argument("--tlef", required=True)
    parser.add_argument("--env", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fabric", default="3d20own_w100")
    parser.add_argument("--corner", default="tt")
    parser.add_argument("--bond-pf", type=float, help="layout's bond net (pF)")
    parser.add_argument("--other-pf", type=float, help="what the layout's receiver drives (pF)")
    parser.add_argument("--own-pf", type=float, help="what the layout's FLE output driver drives (pF)")
    parser.add_argument("--ins-pf", type=float, nargs=2, help="what the two inserted buffers drive (pF)")
    parser.add_argument("--cells", nargs="+", help="the kit's standard-cell CDL files, for the as-laid-out variants")
    parser.add_argument("--loads-only", action="store_true", help="write decks and print loads, no Spectre")
    args = parser.parse_args()
    ms.use_kit("sky130")
    metals, vias = ms.read_tlef(args.tlef)
    wires = ms.wire_roles("sky130", metals)
    f = ms.FABRICS[args.fabric]
    ins = args.ins_pf or (0.0, 0.0)
    whole_own = args.own_pf + ins[0] if args.own_pf else None      # the nets before Innovus split them
    whole_other = args.other_pf + ins[1] if args.other_pf else None
    variants = [("base", {}),
                ("bondnet", dict(bond_pf=args.bond_pf)),
                ("farnet", dict(bond_pf=args.bond_pf, other_pf=whole_other)),
                ("ownnet", dict(bond_pf=args.bond_pf, other_pf=whole_other, own_pf=whole_own))]
    if args.cells:
        cells = None
        try:
            cells = std_cells(args.cells, list(dict.fromkeys(CELLS.values())))
        except SystemExit as e:
            print(f"cells: {e}", flush=True)
        if cells:
            variants += [("cells", dict(bond_pf=args.bond_pf, other_pf=whole_other, own_pf=whole_own, cells=cells))]
            if args.ins_pf:
                variants += [("cells+ins", dict(bond_pf=args.bond_pf, other_pf=args.other_pf, own_pf=args.own_pf,
                                                cells=cells, ins_pf=args.ins_pf))]
    folder = args.out / f"stages_{args.fabric}_{args.corner}"
    folder.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, kw in variants:
        if any(v is None for k, v in kw.items() if k.endswith("_pf")):
            continue
        try:
            d, loads = fb_deck(args.fabric, f, wires, vias, args.models, args.corner, **kw)
            path = folder / f"{name.replace('+', '_')}.sp"
            path.write_text(split_wide(d.text()))
            results[name] = dict(loads=loads)
            if args.loads_only:
                continue
            values = ms.run(path, args.env)
        except SystemExit as e:
            results[name] = dict(results.get(name, {}), error=str(e))
            print(name, "failed:", e, flush=True)
            continue
        edges = {k: {m[:-2]: round(v * 1e12, 2) for m, v in values.items() if m.endswith(f"_{k}")} for k in (1, 2)}
        same = max(edges[k]["same"] for k in (1, 2))
        cross = max(edges[k]["cross"] for k in (1, 2))
        worst = 1 if edges[1]["cross"] >= edges[2]["cross"] else 2
        stages = {k: v for k, v in edges[worst].items() if k.startswith("s_")}
        results[name] = dict(clb_crossing=round(cross - same, 2), same=same, cross=cross, worst_edge=worst,
                             stages_worst_edge=stages, edges=edges, loads=loads)
        print(name, "clb_crossing", results[name]["clb_crossing"], flush=True)
    print(loads_table(results))
    if args.loads_only:
        return
    expected = Path(__file__).with_name("delays_tt.json")
    if args.corner == "tt" and expected.exists() and "clb_crossing" in results.get("base", {}):
        want = json.loads(expected.read_text())[args.fabric]["clb_crossing"]
        got = results["base"]["clb_crossing"]
        print(f"base {got} vs delays_tt.json's clb_crossing {want}: off by {got - want:+.2f} ps, "
              f"{'reproduced' if abs(got - want) < 1 else 'NOT reproduced'} (within 1 ps)")
    print(table(results))
    out = args.out / f"crossing_stages_{args.fabric}_{args.corner}.json"
    out.write_text(json.dumps(dict(fabric=args.fabric, corner=args.corner, bond_pf=args.bond_pf, other_pf=args.other_pf,
                                   own_pf=args.own_pf, ins_pf=args.ins_pf, variants=results), indent=1) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
