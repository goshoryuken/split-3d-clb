#!/usr/bin/env python3
"""Simulate flip-flops in the split two-layer CLB, using LaZagna's exact flags.

Runs a clocked design through VPR and OpenFPGA, splits the CLB by layer, and
compares it with a reference model cycle by cycle. Then it repeats with one
crossing held at 0 at a time, to prove the crossings carry what the test needs.
"""
import argparse
import concurrent.futures
import csv
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "pnr"))
import compare_2d_3d  # noqa: E402
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


def make_arch(work, chan_grid, relayer):
    xml = (HERE.parent / "vtr_3d_clb_arch.xml").read_text()
    if relayer:
        xml = compare_2d_3d.split_inputs(xml)
    # Pads with no reach onto layer 0 make every signal travel on layer 1.
    xml, count = re.subn(r'(<loc side="\w+") layer_offset="1">(io\.outpad io\.inpad</loc>)', r"\1>\2", xml)
    assert count == 4
    xml, count = re.subn(r'(<fixed_layout[^>]*?)width="\d+" height="\d+"',
                         rf'\1width="{chan_grid}" height="{chan_grid}"', xml, count=1)
    assert count == 1
    (work / "arch.xml").write_text(xml)


def make_place(work, outputs=OUTPUTS):
    names = list("abcdef") + [f"out:{n}" for n in outputs]
    rows = [(x, s) for x in (1, 3, 2, 4) for s in range(8)]
    (work / "io.place").write_text("".join(f"{n} {x} 0 {s} 1\n" for n, (x, s) in zip(names, rows)))


def flow_script(work, support, relayer):
    src = work / "SRC"
    stages = f" --net_file {work}/relayered.net --place --route --analysis" if relayer else ""
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


def make_cuts(pins):
    """Name -> (path inside the CLB, whether cutting must break the design)."""
    cuts = {"none": (None, False), "set": ("layer1.n_set_0", False),
            "clk": ("layer1.n_clk_0", True), "reset": ("layer1.n_reset_0", True),
            "clb_clk": ("layer1.n_clb_clk_0", None)}
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


def make_control(work, cuts):
    clb = f"{TB}.FPGA_DUT.U0_formal_verification.grid_clb_0_1_1_.logical_tile_clb_mode_clb__0."
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
    args = parser.parse_args()
    work, support = args.work.resolve(), args.support.resolve()
    work.mkdir(parents=True, exist_ok=True)
    (work / "SRC").mkdir(exist_ok=True)
    make_arch(work, 6, args.relayer)
    make_place(work)
    subprocess.run([sys.executable, "-I", str(HERE / "make_ff_design.py"), "--output", str(work / "design")], check=True)

    print("1. Building the routing graph with routed clocks, as LaZagna does", flush=True)
    code = run([str(ROOT / "build/vpr/vpr/vpr"), "arch.xml", f"{ROOT}/prototype/ten_luts.blif", "--route_chan_width", "50",
                "--write_rr_graph", "rr.xml", "--clock_modeling", "route", "--pack"], work, work / "rr.log")
    must(code, "VPR", work / "rr.log")
    print("2. Running VPR and OpenFPGA without them", flush=True)
    if args.relayer:
        code = run([str(ROOT / "build/vpr/vpr/vpr"), "arch.xml", f"design/{DESIGN}.blif", "--route_chan_width", "50",
                    "--pack", "--net_file", "packed.net"], work, work / "pack.log")
        must(code, "packing", work / "pack.log")
        before, after = relayer_net.rearrange(work / "packed.net", work / "relayered.net")
        print(f"   weighted crossings {before:.2f} -> {after:.2f}", flush=True)
    (work / "flow.openfpga").write_text(flow_script(work, support, args.relayer))
    code = run([str(ROOT / "build/of/openfpga/openfpga"), "-f", "flow.openfpga"], work, work / "flow.log")
    must(code, "OpenFPGA", work / "flow.log")
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
    cuts = make_cuts(pins)
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
    print(f"\n6. Long run, 5,000 cycles", flush=True)
    _, long_mismatches, finished = simulate(work, "none", 10000)
    print(f"mismatches: {long_mismatches}")
    if long_mismatches or not finished:
        failed.append("long run")
    print("\nFAIL: " + ", ".join(failed) if failed else "\nPASS: flip-flops work in the split two-layer CLB")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
