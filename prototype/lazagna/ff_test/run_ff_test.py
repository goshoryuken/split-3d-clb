#!/usr/bin/env python3
"""Simulate flip-flops in the split two-layer CLB, using LaZagna's exact flags.

Runs a clocked design through VPR and OpenFPGA, splits the CLB by layer, and
compares it with a reference model cycle by cycle. Then it repeats with one
crossing held at 0 at a time, to prove the crossings carry what the test needs.

--fles 20 --local --own-layer builds the sweeps' split CLB (20 FLEs, one crossbar per
layer reading only that layer's input pins, input pins on their own layer's tracks;
compare_2d_3d.py --n3d 20 --local-inputs --own-layer-inputs); the design then has one
LUT per FLE. --layer-pass runs layer_pass.py between packing and placement, as
compare_2d_3d.py --layer-pass does, and checks that the packing OpenFPGA builds the
bitstream from is the rewritten one. --plant-fault gives its negative controls, each of
which must fail: "net" moves one FLE input of the rewritten netlist to another FLE's
output (VPR's netlist reader should already refuse it); "lut:NAME" drops one truth-table
row of LUT NAME from the netlist VPR and OpenFPGA implement, not from the reference
model (pick a LUT the pass moves, so the moved FLE's logic is shown to be observed).
"""
import argparse
import concurrent.futures
import csv
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "pnr"))
sys.path.insert(0, str(HERE))
import compare_2d_3d  # noqa: E402
import make_ff_design  # noqa: E402
import make_pnr_rtl  # noqa: E402
import relayer_net  # noqa: E402
DESIGN = "ff_ten"
TB = f"{DESIGN}_top_formal_verification_random_tb"
FLE = "logical_tile_clb_mode_default__fle"
OUTPUTS = [f"q{i}" for i in range(8)] + ["c8", "c9"]


def run(command, cwd, log):
    with open(log, "w") as handle:
        return subprocess.run(command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL).returncode


def must(code, what, log):
    if code:
        sys.exit(f"FAIL: {what} exited with {code}. See {log}")


def make_arch(work, chan_grid, relayer, fles=10, local=False, own=False):
    xml = (HERE.parent / "vtr_3d_clb_arch.xml").read_text()
    if relayer:
        xml = compare_2d_3d.split_inputs(xml)
    # Pads with no reach onto layer 0 make every signal travel on layer 1. With own-layer input pins
    # a layer-0 input could then never be reached, so there the pads keep both layers' tracks (as
    # the sweeps' fabric does).
    if not own:
        xml, count = re.subn(r'(<loc side="\w+") layer_offset="1">(io\.outpad io\.inpad</loc>)', r"\1>\2", xml)
        assert count == 4
    xml, count = re.subn(r'(<fixed_layout[^>]*?)width="\d+" height="\d+"',
                         rf'\1width="{chan_grid}" height="{chan_grid}"', xml, count=1)
    assert count == 1
    if fles != 10:
        xml = compare_2d_3d.resize_clb(xml, fles)
    if local:
        xml = compare_2d_3d.local_inputs(xml, fles)
    if own:
        xml = compare_2d_3d.own_layer_inputs(xml)
    (work / "arch.xml").write_text(xml)


def local_support(work, support):
    """The two crossbars need the original crossbar's mux type, or OpenFPGA picks a one-hot mux
    (as run_clb_equiv.py)."""
    overlay = work / "support"
    overlay.mkdir(exist_ok=True)
    settings = (support / "openfpga_arch.xml").read_text()
    old = '<interconnect name="crossbar" circuit_model_name="mux_2level"/>'
    assert old in settings, "openfpga_arch.xml has no crossbar annotation"
    (overlay / "openfpga_arch.xml").write_text(settings.replace(old, old.replace('"crossbar"', '"crossbar0"')
                                                                + old.replace('"crossbar"', '"crossbar1"')))
    shutil.copy(support / "sim.xml", overlay / "sim.xml")
    (overlay / "h_SRC").mkdir(exist_ok=True)
    shutil.copy(support / "h_SRC/stubs.v", overlay / "h_SRC/stubs.v")
    return overlay


def make_place(work, outputs=OUTPUTS):
    names = list("abcdef") + [f"out:{n}" for n in outputs]
    rows = [(x, s) for x in (1, 3, 2, 4) for s in range(8)]
    (work / "io.place").write_text("".join(f"{n} {x} 0 {s} 1\n" for n, (x, s) in zip(names, rows)))


def flow_script(work, support, net):
    """net: True for relayer_net.py's relayered.net, or a packed netlist to place and route."""
    src = work / "SRC"
    net = work / "relayered.net" if net is True else net
    stages = f" --net_file {net} --place --route --analysis" if net else ""
    return "\n".join([
        f"vpr {work}/arch.xml {work}/design/{DESIGN}.blif --route_chan_width 50 --place_bounding_box_mode cube_bb"
        f" --read_rr_graph {work}/rr.xml --seed 1 --fix_clusters {work}/io.place" + stages,
        f"read_openfpga_arch -f {support}/openfpga_arch.xml",
        f"read_openfpga_simulation_setting -f {support}/sim.xml",
        "link_openfpga_arch --3d_sb",
        "check_netlist_naming_conflict --fix --report ./netlist_renaming.xml",
        "pb_pin_fixup", "lut_truth_table_fixup", "build_fabric --compress_routing",
        f"write_fabric_verilog --file {src} --explicit_port_mapping", "repack",
        f"build_architecture_bitstream --write_file {work}/arch_bits.xml", "build_fabric_bitstream",
        f"write_fabric_bitstream --file {src}/fabric_bitstream.bit --format plain_text",
        f"write_preconfigured_fabric_wrapper --file {src} --embed_bitstream iverilog",
        f"write_preconfigured_testbench --file {src} --reference_benchmark_file_path {work}/design/{DESIGN}.v",
        "exit",
    ]) + "\n"


def used_inputs(route):
    pins = {}
    for match in re.finditer(r"IPIN \(\d+,\d+,(\d)\).*clb\.(I\d?)\[(\d+)\]", route):
        pins[(match.group(2), int(match.group(3)))] = int(match.group(1))
    return pins


def make_cuts(pins, fles=10, crossings=None):
    """Name -> (path inside the CLB, whether cutting must break the design).
    With crossings (split/clb_crossings.csv of a layer-local CLB, whose input pins never cross),
    the FLE output cuts come from that list."""
    cuts = {"none": (None, False), "set": ("layer1.n_set_0", False),
            "clk": ("layer1.n_clk_0", True), "reset": ("layer1.n_reset_0", True),
            "clb_clk": ("layer1.n_clb_clk_0", None)}
    if crossings:
        for row in csv.DictReader(open(crossings)):
            found = re.fullmatch(rf"{FLE}_(\d+)_fle_out", row["signal"])
            if row["type"] == "FLE output" and found:
                cuts[f"F{found.group(1)}"] = (f"layer{row['to_layer']}.n_{row['signal']}_{row['bit']}", None)
        return cuts
    for (port, pin), layer in sorted(pins.items()):
        cuts[f"{port}_{pin}"] = (f"layer{1 - layer}.n_clb_{port}_{pin}", None)
    port = next(iter(pins))[0]
    if port == "I":
        unused = ("I", next(i for i in range(20, 40) if ("I", i) not in pins))
    else:
        unused = ("I1", next(i for i in range(20) if ("I1", i) not in pins))
    cuts[f"{unused[0]}_{unused[1]}"] = (f"layer0.n_clb_{unused[0]}_{unused[1]}", False)
    for fle in range(10):
        cuts[f"F{fle}"] = (f"layer{1 if fle < 5 else 0}.n_{FLE}_{fle}_fle_out_0", None)
    return cuts


def clb_instance(work):
    """The design's one CLB, from VPR's placement (grid_clb_<layer>_<x>_<y>_)."""
    for line in (work / f"{DESIGN}.place").read_text().splitlines():
        fields = line.split()
        if len(fields) >= 5 and not line.startswith("#") and fields[0] not in list("abcdef") + ["clk"] \
                and not fields[0].startswith("out:") and fields[1].isdigit():
            return f"grid_clb_{fields[4]}_{fields[1]}_{fields[2]}_"
    raise SystemExit("no CLB in the placement")


def fle_slots(net_file):
    """{atom name: FLE index} for every LUT and flip-flop in a packed netlist."""
    slots = {}

    def walk(block, fle):
        inst = block.get("instance", "")
        if inst.startswith("fle["):
            fle = int(inst[4:-1])
        children = block.findall("block")
        if not children and block.get("name") not in (None, "open") and fle is not None:
            slots[block.get("name")] = fle
        for child in children:
            walk(child, fle)
    for clb in ET.parse(net_file).getroot().findall("block"):
        walk(clb, None)
    return slots


def flip_lut(blif, name):
    """Drop the first truth-table row of LUT NAME (the minterm then gives 0). Returns what changed."""
    lines = Path(blif).read_text().split("\n")
    head = next(i for i, l in enumerate(lines) if l.startswith(".names ") and l.split()[-1] == name)
    row = lines.pop(head + 1)
    assert row.endswith(" 1"), row
    Path(blif).write_text("\n".join(lines))
    return f"LUT {name}: row {row.split()[0]} (output 1) dropped from the BLIF, not from the reference"


def plant_fault(net_file):
    """Negative control: the netlist's first FLE input that reads another FLE's output through
    layer 1's crossbar reads a different FLE's output instead (fle[0], or fle[1] if it was fle[0]).
    Returns what changed."""
    text = Path(net_file).read_text()
    for found in re.finditer(r"fle\[(\d+)\]\.out\[0\]-&gt;crossbar1", text):
        new = 0 if found.group(1) != "0" else 1
        planted = text[:found.start()] + f"fle[{new}].out[0]-&gt;crossbar1" + text[found.end():]
        Path(net_file).write_text(planted)
        line = text.count("\n", 0, found.start()) + 1
        return f"line {line}: fle[{found.group(1)}].out[0]->crossbar1 -> fle[{new}].out[0]->crossbar1"
    raise SystemExit("plant_fault: no FLE output feeds crossbar1")


def make_control(work, cuts):
    clb = f"{TB}.FPGA_DUT.U0_formal_verification.{clb_instance(work)}.logical_tile_clb_mode_clb__0."
    lines = ["module crossing_ctl;", "  reg [8*8:1] c;", "  integer t;", "  initial begin",
             '    c="none"; t=2000;', '    if ($value$plusargs("cut=%s",c)) ;',
             '    if ($value$plusargs("t=%d",t)) ;']
    lines += [f"    if (c==\"{k}\") force {clb}{p} = 1'b0;" for k, (p, _) in cuts.items() if p]
    # The flip-flops power up unknown. Pulse reset before the first clock edge.
    lines += [f"    #0.1 force {TB}.FPGA_DUT.reset_fm[0] = 1'b1;", f"    #0.5 release {TB}.FPGA_DUT.reset_fm[0];",
              "    #(t-0.6) $display(\"CTL cut=%0s errors=%0d\",c," + TB + ".nb_error);", "    $finish;",
              "  end", "endmodule", ""]
    (work / "SRC/crossing_ctl.v").write_text("\n".join(lines))


def prepare_sim(work, support):
    src = work / "SRC"
    layer = {r["instance"]: r["layer"] for r in csv.DictReader(open(work / "split/instance_layers.csv"))}
    formal = (src / f"{DESIGN}_top_formal_verification.v").read_text()
    formal = re.sub(r"logical_tile_clb_mode_clb__0\.(\w+)\.",
                    lambda m: f"logical_tile_clb_mode_clb__0.layer{layer[m.group(1)]}.{m.group(1)}.", formal)
    (src / "split_formal.v").write_text(formal)
    shutil.copy(support / "h_SRC/stubs.v", src / "stubs.v")
    fab = (src / "fabric_netlists.v").read_text()
    fab, count = re.subn(r'`include "[^"]*lb/logical_tile_clb_mode_clb_\.v"\n',
                         f'`include "{work}/split/clb_split.v"\n', fab)
    assert count == 1
    fab = re.sub(r'`include "[^"]*designs/complex_dsp\.v"\n', f'`include "{src}/stubs.v"\n', fab)
    fab = re.sub(r'`include "[^"]*designs/spram\.v"\n', "", fab)
    (src / "fabric_netlists.v").write_text(fab)
    tb = (src / f"{DESIGN}_formal_random_top_tb.v").read_text()
    tb = re.sub(r".*\$dump(file|vars).*\n", "", tb)
    (src / "ctl_tb.v").write_text(tb)
    top = (src / f"{DESIGN}_include_netlists.v").read_text()
    top = top.replace(f"{src.name}/{DESIGN}_formal_random_top_tb.v", f"{src.name}/ctl_tb.v")
    top = top.replace(f"{src}/{DESIGN}_formal_random_top_tb.v", f"{src}/ctl_tb.v")
    top = top.replace(f"{src}/{DESIGN}_top_formal_verification.v", f"{src}/split_formal.v")
    top = top.replace(f"{src.name}/{DESIGN}_top_formal_verification.v", f"{src.name}/split_formal.v")
    (src / "ctl_include.v").write_text(top + f'`include "{src}/crossing_ctl.v"\n')


def use_synthesizable_cells(work):
    """Swaps pass-gate mux primitives for the logic that goes to layout."""
    for name in ("mux_primitives.v", "inv_buf_passgate.v"):
        path = work / "SRC/sub_module" / name
        parts = [make_pnr_rtl.synthesizable(body) for _, body in make_pnr_rtl.modules_in(path.read_text())]
        path.write_text("\n".join(p + "endmodule\n" for p in parts if p is not None))


def simulate(work, cut, time):
    log = work / f"sim_{cut}.log"
    run(["vvp", "sim.vvp", f"+cut={cut}", f"+t={time}"], work, log)
    text = log.read_text()
    return cut, text.count("Mismatch"), "CTL cut=" in text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=ROOT / "build/of/try/ff_run")
    parser.add_argument("--support", type=Path, default=ROOT / "build/of/try")
    parser.add_argument("--jobs", type=int, default=5)
    parser.add_argument("--relayer", action="store_true", help="assign FLEs and input nets to layers after packing")
    parser.add_argument("--synth-cells", action="store_true", help="simulate the logic that goes to layout")
    parser.add_argument("--crossing-buffers", action="store_true", help="add a driver and receiver to each crossing")
    parser.add_argument("--vpr", type=Path, default=ROOT / "build/vpr/vpr/vpr")
    parser.add_argument("--openfpga", type=Path, default=ROOT / "build/of/openfpga/openfpga")
    parser.add_argument("--fles", type=int, default=10, help="FLEs in the CLB, half on each layer; one LUT per FLE")
    parser.add_argument("--local", action="store_true", help="one crossbar per layer, reading that layer's input pins")
    parser.add_argument("--own-layer", action="store_true", help="CLB input pins reach only their own layer's tracks")
    parser.add_argument("--layer-pass", action="store_true", help="layer_pass.py between packing and placement")
    parser.add_argument("--pass-args", default="", help="extra layer_pass.py options, e.g. --control (every FLE "
                        "gets a random slot of its own layer, so every FLE is renumbered)")
    parser.add_argument("--plant-fault", default="",
                        help="negative control for --layer-pass, must fail: 'net' (one FLE input of the rewritten "
                             "netlist moved to another FLE's output) or 'lut:NAME' (one truth-table row of LUT NAME "
                             "dropped from the implemented netlist, not from the reference)")
    args = parser.parse_args()
    assert not args.layer_pass or args.local, "the layer pass needs --local"
    assert not args.plant_fault or args.layer_pass, "--plant-fault goes with --layer-pass"
    work, support = args.work.resolve(), args.support.resolve()
    vpr, openfpga = str(args.vpr.resolve()), str(args.openfpga.resolve())
    work.mkdir(parents=True, exist_ok=True)
    (work / "SRC").mkdir(exist_ok=True)
    make_arch(work, 6, args.relayer, args.fles, args.local, args.own_layer)
    if args.local:
        support = local_support(work, support)
    make_place(work, make_ff_design.outputs(args.fles))
    count = ["--count", str(args.fles)] if args.fles != 10 else []
    subprocess.run([sys.executable, "-I", str(HERE / "make_ff_design.py"), "--output", str(work / "design")] + count,
                   check=True)
    assert args.plant_fault in ("", "net") or args.plant_fault.startswith("lut:"), args.plant_fault
    if args.plant_fault.startswith("lut:"):
        print("   planted fault: " + flip_lut(work / "design" / f"{DESIGN}.blif", args.plant_fault[4:]), flush=True)

    print("1. Building the routing graph with routed clocks, as LaZagna does", flush=True)
    code = run([vpr, "arch.xml", f"{ROOT}/prototype/ten_luts.blif", "--route_chan_width", "50",
                "--write_rr_graph", "rr.xml", "--clock_modeling", "route", "--pack"], work, work / "rr.log")
    must(code, "VPR", work / "rr.log")
    print("2. Running VPR and OpenFPGA without them", flush=True)
    if args.relayer:
        code = run([vpr, "arch.xml", f"design/{DESIGN}.blif", "--route_chan_width", "50",
                    "--pack", "--net_file", "packed.net"], work, work / "pack.log")
        must(code, "packing", work / "pack.log")
        before, after = relayer_net.rearrange(work / "packed.net", work / "relayered.net")
        print(f"   weighted crossings {before:.2f} -> {after:.2f}", flush=True)
    net, moved = args.relayer, []
    if args.layer_pass:
        code = run([vpr, "arch.xml", f"design/{DESIGN}.blif", "--route_chan_width", "50", "--pack", "--net_file",
                    "packed.net", "--pack_criticality_file", "pack_criticality.tsv"], work, work / "pack.log")
        must(code, "packing", work / "pack.log")
        code = run([sys.executable, "-I", str(HERE.parent / "layer_pass.py"), "packed.net", "pack_criticality.tsv",
                    "arch.xml", "-o", "passed.net"] + args.pass_args.split(), work, work / "layer_pass.log")
        must(code, "layer pass", work / "layer_pass.log")
        for line in (work / "layer_pass.log").read_text().splitlines():
            if line.startswith("layer_pass:"):
                print("   " + line, flush=True)
        half = args.fles // 2
        packed, passed = fle_slots(work / "packed.net"), fle_slots(work / "passed.net")
        moved = sorted((a for a in packed if (packed[a] >= half) != (passed[a] >= half)), key=lambda a: passed[a])
        print(f"   atoms in another FLE slot after the pass: {sum(packed[a] != passed[a] for a in packed)}, "
              f"on the other layer: {len(moved)} (of {len(packed)})", flush=True)
        for a in moved:
            print(f"     {a}: fle[{packed[a]}] (layer {int(packed[a] >= half)}) -> fle[{passed[a]}] "
                  f"(layer {int(passed[a] >= half)})")
        if args.plant_fault == "net":
            print("   planted fault: " + plant_fault(work / "passed.net"), flush=True)
        if args.plant_fault.startswith("lut:"):
            lut = args.plant_fault[4:]
            print(f"   the faulty LUT {lut} is {'on the other layer after the pass' if lut in moved else 'NOT moved'}")
        net = work / "passed.net"
    (work / "flow.openfpga").write_text(flow_script(work, support, net))
    code = run([openfpga, "-f", "flow.openfpga"], work, work / "flow.log")
    check = "set_atom_pin_mapping: Assertion 'pb_route->atom_net_id == atom_ctx.nlist.pin_net(atom_pin)' failed"
    if code and args.plant_fault == "net" and check in (work / "flow.log").read_text():
        print(f"\nPASS: the planted fault was caught before simulation, by VPR's netlist reader:\n  {check}")
        sys.exit(0)
    must(code, "OpenFPGA", work / "flow.log")
    if args.layer_pass:
        post = next(p for p in (Path(f"{net}.post_routing"), work / f"{DESIGN}.net.post_routing") if p.exists())
        same = fle_slots(post) == fle_slots(net)
        print(f"   the packing OpenFPGA placed, routed and built the bitstream from ({post.name}) "
              f"{'is' if same else 'is NOT'} the rewritten one", flush=True)
        if not same:
            sys.exit("FAIL: OpenFPGA did not use the rewritten packing")
    print("3. Splitting the CLB by layer", flush=True)
    code = run([sys.executable, "-I", str(HERE.parent / "split_clb_layers.py"), "--source", "SRC", "--arch", "arch.xml",
                "--output", "split"], work, work / "split.log")
    must(code, "split", work / "split.log")
    if args.crossing_buffers:
        code = run([sys.executable, "-I", str(HERE.parent / "pnr/add_crossing_buffers.py"), "split/clb_split.v",
                    "split/clb_crossings.csv", "split/clb_split.v"], work, work / "buffers.log")
        must(code, "crossing buffers", work / "buffers.log")
    route = (work / f"{DESIGN}.route").read_text()
    pins = used_inputs(route)
    cuts = make_cuts(pins, args.fles, work / "split/clb_crossings.csv" if args.local else None)
    if args.plant_fault:
        cuts = {"none": (None, True)}
    make_control(work, cuts)
    prepare_sim(work, support)
    if args.synth_cells:
        use_synthesizable_cells(work)
    print("4. Compiling the simulation, about 2 minutes", flush=True)
    code = run(["iverilog", "-g2012", "-s", TB, "-s", "crossing_ctl", "-o", "sim.vvp", "-I.", "SRC/ctl_include.v"],
               work, work / "iverilog.log")
    must(code, "iverilog", work / "iverilog.log")

    print("5. Simulating 1,000 cycles per case\n", flush=True)
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(lambda c: simulate(work, c, 2000), cuts))
    failed = []
    print(f"{'cut':10s}{'mismatches':>12s}  expected")
    for cut, mismatches, finished in results:
        want = cuts[cut][1]
        label = {True: "must fail", False: "must pass", None: "either"}[want]
        print(f"{cut:10s}{mismatches:>12d}  {label}")
        if not finished or (want is True and mismatches == 0) or (want is False and mismatches != 0):
            failed.append(cut)
    if args.local and not args.plant_fault:
        fle_cuts = {c: m for c, m, _ in results if c.startswith("F")}
        caught = sorted((c for c, m in fle_cuts.items() if m), key=lambda c: int(c[1:]))
        print(f"\nFLE output crossings the design uses, caught when cut: {len(caught)} of {len(fle_cuts)}")
        if not caught:
            failed.append("no FLE output crossing was caught")
        if moved:
            slots = fle_slots(net)
            cut_names = sorted({f"F{slots[a]}" for a in moved}, key=lambda c: int(c[1:]))
            hits = [c for c in cut_names if fle_cuts.get(c)]
            print(f"of them, outputs of FLEs the pass moved to the other layer: {len(hits)} of {len(cut_names)} "
                  f"({' '.join(hits)})")
    print(f"\n6. Long run, 5,000 cycles", flush=True)
    _, long_mismatches, finished = simulate(work, "none", 10000)
    print(f"mismatches: {long_mismatches}")
    if not finished or (long_mismatches == 0) == bool(args.plant_fault):
        failed.append("long run")
    if args.plant_fault:
        print("\nFAIL: " + ", ".join(failed) if failed else "\nPASS: the planted fault was caught")
    else:
        print("\nFAIL: " + ", ".join(failed) if failed else "\nPASS: flip-flops work in the split two-layer CLB")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
