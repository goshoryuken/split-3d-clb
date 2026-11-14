#!/usr/bin/env python3
"""Full VPR regressions. Keep each command, log and artifact for inspection."""
import argparse
from collections import Counter
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vpr", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    vpr = str(args.vpr.resolve())
    circuit = str(ROOT / "prototype/ten_luts.blif")
    original = (ROOT / "prototype/physical_split_fle.xml").read_text()
    count = 0

    def run(name, xml, error=None, extra=(), circuit_path=None):
        nonlocal count
        work = args.output / name
        work.mkdir(exist_ok=True)
        arch = work / "arch.xml"
        arch.write_text(xml)
        report = work / "internal_layers.tsv"
        if report.exists():
            report.unlink()
        command = [vpr, str(arch), str(circuit_path or circuit), "--route_chan_width", "100", "--disp", "off", *extra]
        (work / "command.txt").write_text("\n".join(command) + "\n")
        result = subprocess.run(command, cwd=work, text=True, capture_output=True, timeout=120)
        log = result.stdout + result.stderr
        (work / "run.log").write_text(log)
        if error:
            assert result.returncode > 0, (name, result.returncode, log[-3000:])
            assert error in log, (name, log[-3000:])
            assert not report.exists(), name + " produced a success report"
        else:
            assert result.returncode == 0 and "VPR succeeded" in log, (name, log[-3000:])
            if "--pack" not in extra:
                assert (work / (Path(circuit_path or circuit).stem + ".route")).stat().st_size > 0
        count += 1
        print("PASS: " + name)
        return work

    def audit(work, layer=0, circuit_name="ten_luts"):
        rows = [line.split("\t") for line in (work / "internal_layers.tsv").read_text().splitlines()
                if not line.startswith("#")]
        atoms = [r for r in rows if r[0] == "atom"]
        assert len(atoms) == 10
        assert len({r[2] for r in atoms}) == 1, "LUTs were split into multiple CLBs"
        assert Counter(int(r[3]) for r in atoms) == {0: 5, 1: 5}
        assert Counter(int(r[4]) for r in atoms) == {layer: 5, layer + 1: 5}
        edges = [r for r in rows if r[0] == "edge"]
        assert edges and all(r[5] != r[6] for r in edges)
        assert any(r[2].startswith("n") for r in edges), "No used LUT-output crossing"
        footprint = [r for r in rows if r[0] == "footprint"]
        assert len(footprint) == 2 and {int(r[4]) for r in footprint} == {layer, layer + 1}
        netlist = ET.parse(work / (circuit_name + ".net"))
        used_fles = [b for b in netlist.iter("block")
                     if b.get("instance", "").startswith("fle[") and b.get("name") != "open"]
        assert len(used_fles) == 10
        return edges

    baseline = run("split", original, extra=("--gen_post_synthesis_netlist", "on"))
    base_edges = audit(baseline)
    packed_only = run("packing_only", original, extra=("--pack",))
    assert not (packed_only / "internal_layers.tsv").exists()
    rtl = (baseline / "ten_luts_post_synthesis.v").read_text()
    assert Counter(re.findall(r"vtr_relative_layer = (\d+)", rtl)) == {"0": 5, "1": 5}
    assert Counter(re.findall(r"vtr_absolute_layer = (\d+)", rtl)) == {"0": 5, "1": 5}
    # An absolute layer must include the placed root's nonzero anchor.
    shifted = ET.fromstring(original)
    layout = shifted.find("./layout/fixed_layout")
    for layer_node in layout.findall("layer"):
        layer_node.set("die", str(int(layer_node.get("die")) + 1))
    bottom = ET.Element("layer", die="0", has_prog_routing="false")
    ET.SubElement(bottom, "fill", type="EMPTY", priority="1")
    layout.insert(0, bottom)
    elevated = run("nonzero_anchor", ET.tostring(shifted, encoding="unicode"),
                   extra=("--gen_post_synthesis_netlist", "on"))
    audit(elevated, layer=1)
    elevated_rtl = (elevated / "ten_luts_post_synthesis.v").read_text()
    assert Counter(re.findall(r"vtr_relative_layer = (\d+)", elevated_rtl)) == {"0": 5, "1": 5}
    assert Counter(re.findall(r"vtr_absolute_layer = (\d+)", elevated_rtl)) == {"1": 5, "2": 5}
    stronger = run("asymmetric", original, extra=("--gen_post_synthesis_netlist", "on"),
                   circuit_path=ROOT / "prototype/asymmetric_ten_luts.blif")
    audit(stronger, circuit_name="asymmetric_ten_luts")
    # Keep packing and placement identical to isolate the timing change.
    # Disable the architecture digest check ONLY for this controlled timing-only edit.
    delayed_xml = original.replace('name="crossbar"', 'name="crossbar" layer_crossing_delay="1e-9"')
    delayed = run("illustrative_delay", delayed_xml,
                  extra=("--route", "--verify_file_digests", "off", "--net_file", str(baseline / "ten_luts.net"),
                         "--place_file", str(baseline / "ten_luts.place")))
    # --net_file is loaded externally, so copy only for audit's explicit netlist check.
    (delayed / "ten_luts.net").write_bytes((baseline / "ten_luts.net").read_bytes())
    delayed_edges = audit(delayed)
    before = {(r[1], r[2], r[3], r[4]): float(r[7]) for r in base_edges}
    differences = [float(r[7]) - before[(r[1], r[2], r[3], r[4])] for r in delayed_edges]
    assert any(abs(d - 1e-9) < 1e-15 for d in differences), differences
    assert all(abs(d) < 1e-15 or abs(d - 1e-9) < 1e-15 for d in differences)
    def critical(work):
        return float(re.search(r"Final critical path delay \(least slack\): ([0-9.]+) ns",
                               (work / "run.log").read_text())[1])
    assert critical(delayed) > critical(baseline), "Timing analysis ignored illustrative delay"

    run("span_too_short", original.replace('layer_span="2"', 'layer_span="1"'), "exceed layer_span")
    run("implicit_span_too_short", original.replace(' layer_span="2"', ''), "exceed layer_span")
    run("span_zero", original.replace('layer_span="2"', 'layer_span="0"'), "layer_span must")
    run("span_overflow", original.replace('layer_span="2"', 'layer_span="2147483648"'), "layer_span must")
    run("span_fraction", original.replace('layer_span="2"', 'layer_span="1.5"'), "layer_span must")
    run("overlap", original.replace('<fill type="EMPTY" priority="1"/>',
        '<fill type="EMPTY" priority="1"/><single type="io" x="1" y="1" priority="10"/>'), "footprint overlaps")
    run("top_boundary", original.replace('layer_span="2"', 'layer_span="3"'), "beyond device layers")
    run("unsupported_width", original.replace('name="clb" layer_span="2"',
        'name="clb" width="2" layer_span="2"'), "width=height=capacity=1")
    run("flat_routing_rejected", original, "currently support clustered routing", extra=("--flat_routing", "on"))
    run("delay_negative", original.replace('name="crossbar"',
        'name="crossbar" layer_crossing_delay="-1"'), "layer_crossing_delay must")
    run("delay_nan", original.replace('name="crossbar"',
        'name="crossbar" layer_crossing_delay="nan"'), "layer_crossing_delay must")
    run("nested_overflow", original.replace('<pb_type name="ble6" num_pb="1">',
        '<pb_type name="ble6" num_pb="1" instance_layer_offsets="2147483647">'), "offset overflows")

    # Physical pins are distinct from internal sites: layer_offset must stay
    # inside the span.
    tree = ET.fromstring(original)
    tile = tree.find('./tiles/tile[@name="clb"]')
    pinloc = tile.find('./sub_tile/pinlocations')
    pinloc.clear()
    pinloc.set("pattern", "custom")
    ET.SubElement(pinloc, "loc", side="left", layer_offset="2").text = "clb.I clb.O clb.clk"
    run("pins_beyond_span", ET.tostring(tree, encoding="unicode"), "invalid layer offset")

    # With all I/O on layer 1, every net must use layer 1 wires and enter the
    # layer 0 anchor through the CLB's layer_offset pins.
    def upper_io_xml(layer_offset):
        xml = original.replace('<layer die="1" has_prog_routing="false">', '<layer die="1">')
        xml = xml.replace('<connection_block input_switch_name="ipin_cblock"/>',
                          '<connection_block input_switch_name="ipin_cblock" input_inter_die_switch_name="ipin_cblock"/>')
        xml = xml.replace('<mux name="0"/>', '<mux name="0"/>\n      <mux_inter_die name="0"/>')
        io = '<perimeter type="io" priority="10"/>\n        <corners type="EMPTY" priority="20"/>\n'
        xml = xml.replace(io, "", 1)
        xml = xml.replace('<fill type="EMPTY" priority="1"/>\n      </layer>\n    </fixed_layout>',
                          '<fill type="EMPTY" priority="1"/>\n        ' + io + '      </layer>\n    </fixed_layout>')
        offset = f' layer_offset="{layer_offset}"' if layer_offset else ""
        pins = "".join(f'<loc side="{side}"{offset}>{names}</loc>\n' for side, names in (
            ("top", "clb.clk clb.O[0:4] clb.I[0:9]"), ("right", "clb.O[5:9] clb.I[10:19]"),
            ("bottom", "clb.O[10:14] clb.I[20:29]"), ("left", "clb.O[15:19] clb.I[30:39]")))
        start = xml.index('<tile name="clb"')
        return xml[:start] + xml[start:].replace('<pinlocations pattern="spread"/>',
                                                 f'<pinlocations pattern="custom">{pins}</pinlocations>', 1)

    work = run("upper_layer_routing", upper_io_xml(1))
    route = (work / "ten_luts.route").read_text()
    layers = {m.group(1) for m in re.finditer(r"CHAN[XY] \(\d+,\d+,(\d+)\)", route)}
    assert layers == {"1"}, layers
    assert re.search(r"IPIN \(\d+,\d+,0\).*clb\.I", route) and re.search(r"OPIN \(\d+,\d+,0\).*clb\.O", route)
    run("upper_layer_control", upper_io_xml(0), "unroutable")
    equivalent = ET.fromstring(original)
    import copy
    short_tile = copy.deepcopy(equivalent.find('./tiles/tile[@name="clb"]'))
    short_tile.set("name", "short_clb")
    short_tile.set("layer_span", "1")
    equivalent.find("tiles").append(short_tile)
    run("short_equivalent_tile", ET.tostring(equivalent, encoding="unicode"), "exceed layer_span")

    # Reuse the packed circuit but move the whole spanning block to another legal anchor.
    packed = ET.parse(baseline / "ten_luts.net").getroot()
    clb = next(b.get("name") for b in packed.findall("block") if b.get("instance", "").startswith("clb["))
    lines = (baseline / "ten_luts.place").read_text().splitlines()
    for name, layer, x, y, error in [("legal_relocation", 0, 3, 3, None),
                                    ("reserved_upper_placement", 1, 1, 1, "subtile number")]:
        placement = args.output / (name + ".place")
        modified = [f"{clb}\t{x}\t{y}\t0\t{layer}\t#0" if line.split()[:1] == [clb] else line for line in lines]
        placement.write_text("\n".join(modified) + "\n")
        work = run(name, original, error, ("--route", "--net_file", str(baseline / "ten_luts.net"),
                                          "--place_file", str(placement)))
        if not error:
            (work / "ten_luts.net").write_bytes((baseline / "ten_luts.net").read_bytes())
            audit(work)
    legacy = (ROOT / "vtr_flow/arch/timing/k6_frac_N10_mem32K_40nm.xml").read_text()
    run("legacy_2d", legacy)

    # Capacity/occupancy regression: fill both spanning anchors, then attempt
    # to load a placement which puts both CLBs at the same anchor.
    two = args.output / "twenty_inputs" / "ten_luts.blif"
    two.parent.mkdir(exist_ok=True)
    text = Path(circuit).read_text()
    extra_logic = text[text.index(".names"):text.index(".end")]
    extra_logic = re.sub(r"\bn(\d+)\b", lambda m: "n" + str(int(m[1]) + 10), extra_logic)
    text = text.replace(".outputs ", ".outputs " + " ".join("n" + str(i) for i in range(10, 20)) + " ")
    text = text.replace(".end", extra_logic + ".end")
    two.write_text(text)
    def pin_map(upper):
        xml = original.replace('<layer die="1" has_prog_routing="false">', '<layer die="1">')
        xml = xml.replace('<connection_block input_switch_name="ipin_cblock"/>',
                          '<connection_block input_switch_name="ipin_cblock" input_inter_die_switch_name="ipin_cblock"/>')
        xml = xml.replace('<mux name="0"/>', '<mux name="0"/>\n      <mux_inter_die name="0"/>')
        pins = ('<pinlocations pattern="custom">'
                '<loc side="left" pin_layer="0" layer_offset="1">clb.clk clb.O[0:4] clb.I[0:9]</loc>'
                '<loc side="right" pin_layer="0" layer_offset="1">clb.O[10:14] clb.I[10:19]</loc>'
                f'<loc side="left" pin_layer="{upper}" layer_offset="1">clb.O[5:9] clb.I[20:29]</loc>'
                f'<loc side="right" pin_layer="{upper}" layer_offset="1">clb.O[15:19] clb.I[30:39]</loc>'
                '</pinlocations>')
        start = xml.index('<tile name="clb"')
        return xml[:start] + xml[start:].replace('<pinlocations pattern="spread"/>', pins, 1)
    upper_pins = run("upper_layer_pins", pin_map(1))
    route = (upper_pins / "ten_luts.route").read_text()
    layers = {int(m.group(2)) for m in re.finditer(r"OPIN \((\d+,\d+),(\d+)\).*clb\.O\[([5-9])\] ", route)}
    assert layers == {1}, ("upper outputs must sit on layer 1", layers)
    low = {int(m.group(2)) for m in re.finditer(r"OPIN \((\d+,\d+),(\d+)\).*clb\.O\[[0-4]\] ", route)}
    assert low <= {0}, ("lower outputs must sit on the anchor", low)
    graph = upper_pins / "pins_rr.xml"
    run("upper_pins_write_rr", pin_map(1), extra=("--write_rr_graph", str(graph)))
    rr = run("upper_pins_read_rr", pin_map(1), extra=("--read_rr_graph", str(graph)))
    assert re.search(r"OPIN \(\d+,\d+,1\).*clb\.O\[[5-9]\] ", (rr / "ten_luts.route").read_text()), "RR graph lost pin layers"
    run("pin_layer_beyond_span", pin_map(2), "pin_layer lies outside tile layer_span")
    pair = run("two_spanning_clbs", original, circuit_path=two)
    clbs = [b.get("name") for b in ET.parse(pair / "ten_luts.net").getroot().findall("block")
            if b.get("instance", "").startswith("clb[")]
    assert len(clbs) == 2
    lines = (pair / "ten_luts.place").read_text().splitlines()
    colliding = args.output / "colliding.place"
    colliding.write_text("\n".join(f"{line.split()[0]}\t1\t1\t0\t0" if line.split()[:1] and line.split()[0] in clbs
                                     else line for line in lines) + "\n")
    run("occupied_anchor_rejected", original, "occupied anchor", ("--route", "--net_file", str(pair / "ten_luts.net"),
        "--place_file", str(colliding)), circuit_path=two)
    print(f"{count} full-VPR cases passed; split-site and timing audits passed")
    print(f"Illustrative timing only: {critical(baseline)} ns -> {critical(delayed)} ns")


if __name__ == "__main__":
    main()
