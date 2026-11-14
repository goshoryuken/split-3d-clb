#!/usr/bin/env python3
"""Check the split two-layer CLB against the original, config chain included.

Runs a ten-LUT design through VPR and OpenFPGA, splits the CLB by layer and adds
crossing drivers, then loads the design's real config bits through the CLB's
scan chain twice, so every bit leaves through ccff_tail after crossing the whole
chain. Both CLBs then get the same random inputs and their outputs are compared
every cycle. Controls hold one crossing at 0: every config chain crossing must
fail, and so must each input or FLE output crossing the design uses. It also
builds a folder for run_equiv_gate.csh, which repeats the check on the routed
gates of both layers, or of the 2D CLB, with their extracted delays.

--fles and --local check bigger CLBs and the layer-local crossbar; the design
then has one LUT per FLE.
"""
import csv
import argparse
import concurrent.futures
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import clb_chain  # noqa: E402
import compare_2d_3d  # noqa: E402
import make_ff_design  # noqa: E402
import run_ff_test as ff  # noqa: E402

ROOT = ff.ROOT
DESIGN = ff.DESIGN
FLE = "logical_tile_clb_mode_default__fle"


def build(work, support, fles, local):
    src = work / "SRC"
    src.mkdir(parents=True, exist_ok=True)
    ff.make_arch(work, 6, False)
    arch = (work / "arch.xml").read_text()
    if fles != 10:
        arch = compare_2d_3d.resize_clb(arch, fles)
    if local:
        arch = compare_2d_3d.local_inputs(arch, fles)
        # The two crossbars need the original crossbar's mux type, or OpenFPGA picks a one-hot mux.
        overlay = work / "support"
        overlay.mkdir(exist_ok=True)
        settings = (support / "openfpga_arch.xml").read_text()
        old = '<interconnect name="crossbar" circuit_model_name="mux_2level"/>'
        assert old in settings, "openfpga_arch.xml has no crossbar annotation"
        (overlay / "openfpga_arch.xml").write_text(settings.replace(old, old.replace('"crossbar"', '"crossbar0"')
                                                                    + old.replace('"crossbar"', '"crossbar1"')))
        shutil.copy(support / "sim.xml", overlay / "sim.xml")
        support = overlay
    (work / "arch.xml").write_text(arch)
    ff.make_place(work, make_ff_design.outputs(fles))
    subprocess.run([sys.executable, "-I", str(HERE / "make_ff_design.py"), "--output", str(work / "design"),
                    "--count", str(fles)], check=True)
    code = ff.run([str(ROOT / "build/vpr/vpr/vpr"), "arch.xml", f"{ROOT}/prototype/ten_luts.blif", "--route_chan_width", "50",
                   "--write_rr_graph", "rr.xml", "--clock_modeling", "route", "--pack"], work, work / "rr.log")
    ff.must(code, "VPR", work / "rr.log")
    (work / "flow.openfpga").write_text(ff.flow_script(work, support, False))
    code = ff.run([str(ROOT / "build/of/openfpga/openfpga"), "-f", "flow.openfpga"], work, work / "flow.log")
    ff.must(code, "OpenFPGA", work / "flow.log")
    code = ff.run([sys.executable, "-I", str(HERE.parent / "split_clb_layers.py"), "--source", "SRC", "--arch", "arch.xml",
                   "--output", "split"], work, work / "split.log")
    ff.must(code, "split", work / "split.log")
    code = ff.run([sys.executable, "-I", str(HERE.parent / "pnr/add_crossing_buffers.py"), "split/clb_split.v",
                   "split/clb_crossings.csv", "split/clb_split.v"], work, work / "buffers.log")
    ff.must(code, "crossing buffers", work / "buffers.log")


def make_tb(fles, local):
    """The testbench for a CLB of this size and input ports, from clb_equiv_tb.v."""
    tb = (HERE / "clb_equiv_tb.v").read_text()
    half = fles // 2
    if local:
        tb = tb.replace("  reg [0:39] clb_I = 0;", f"  reg [0:{2 * fles - 1}] clb_I0 = 0, clb_I1 = 0;")
        tb = tb.replace(".clb_I(clb_I)", ".clb_I0(clb_I0), .clb_I1(clb_I1)")
        words = ", ".join(["$random"] * -(-2 * fles // 32))
        tb = tb.replace("clb_I = {$random, $random};", f"clb_I0 = {{{words}}}; clb_I1 = {{{words}}};")
    else:
        tb = tb.replace("  reg [0:39] clb_I = 0;", f"  reg [0:{4 * fles - 1}] clb_I = 0;")
        words = ", ".join(["$random"] * -(-4 * fles // 32))
        tb = tb.replace("clb_I = {$random, $random};", f"clb_I = {{{words}}};")
    tb = tb.replace("  wire [0:9] want, got;", f"  wire [0:{fles - 1}] want, got;")
    tb = tb.replace("for (v = 0; v < 10; v = v + 1)", f"for (v = 0; v < {fles}; v = v + 1)")

    def lines(verb, value):
        out = [f"        {verb} original.{FLE}_{i}.fle_out{value};" for i in range(fles)]
        out += ["`ifdef FLAT"] + [f"        {verb} dut.{FLE}_{i}.fle_out{value};" for i in range(fles)] + ["`else"]
        out += [f"        {verb} dut.layer{int(i >= half)}.{FLE}_{i}.fle_out{value};" for i in range(fles)] + ["`endif"]
        return "\n".join(out)
    body = re.search(r"(  task hold\(input on\);\n.*?)  endtask", tb, re.S).group(1)
    head = body.split("\n")[:3]
    assert head[1].strip().startswith("begin") and head[2].strip().startswith("if (on)"), head
    new = "\n".join(head) + "\n" + lines("force", " = 1'b0") + "\n      end else begin\n" + lines("release", "") + "\n      end\n    end\n"
    return tb.replace(body, new)


def config_path(work):
    """The CLB instance the design was placed in, from VPR's placement (one CLB, block 0)."""
    for line in (work / f"{DESIGN}.place").read_text().splitlines():
        fields = line.split()
        if len(fields) >= 5 and not line.startswith("#") and fields[0] not in list("abcdef") + ["clk"] \
                and not fields[0].startswith("out:") and fields[1].isdigit():
            x, y, layer = fields[1], fields[2], fields[4]
            return f"grid_clb_{layer}_{x}_{y}_.logical_tile_clb_mode_clb__0"
    raise SystemExit("no CLB in the placement")


def package(work, support, folder, fles=10, layer_local=False):
    """A copy that does not depend on paths on this computer."""
    if folder.exists():
        shutil.rmtree(folder)
    shutil.copytree(work / "SRC", folder / "SRC")
    shutil.copytree(work / "split", folder / "split")
    shutil.copy(support / "h_SRC/stubs.v", folder / "SRC/stubs.v")
    (folder / "cells").mkdir()

    def local(match):
        path = Path(match.group(1))
        if not path.is_absolute():
            return match.group(0)
        if work in path.parents:
            return f'`include "{path.relative_to(work)}"'
        shutil.copy(path, folder / "cells" / path.name)
        return f'`include "cells/{path.name}"'

    fabric = (folder / "SRC/fabric_netlists.v").read_text()
    fabric = re.sub(r'`include "[^"]*designs/complex_dsp\.v"\n', '`include "SRC/stubs.v"\n', fabric)
    fabric = re.sub(r'`include "[^"]*designs/spram\.v"\n', "", fabric)
    (folder / "orig_netlists.v").write_text(re.sub(r'`include "([^"]+)"', local, fabric))
    split = (folder / "split/clb_split.v").read_text()
    (folder / "split_dut.v").write_text(re.sub(r"^module logical_tile_clb_mode_clb_\(", "module clb_dut(", split, flags=re.M))
    (folder / "clb_equiv_tb.v").write_text(make_tb(fles, layer_local))
    sys.argv = ["clb_chain.py", str(work / "SRC"), config_path(work), str(folder / "clb_config.txt")]
    clb_chain.main()


def cut_cases(folder):
    """One case per crossing that carries config bits or logic, named by the net to hold at 0."""
    dut = (folder / "split_dut.v").read_text()
    cases = {}
    for row in csv.DictReader(open(folder / "split/clb_crossings.csv")):
        if row["type"] not in ("config chain", "input pin", "FLE output"):
            continue
        for net in (f"x_{row['signal']}_{row['bit']}", f"n_{row['signal']}_{row['bit']}"):
            if re.search(rf"\b{re.escape(net)}\b", dut):
                cases[f"{row['type']} {row['signal'].replace(FLE + '_', 'fle_')}[{row['bit']}]"] = net
                break
        else:
            raise SystemExit(f"no net for crossing {row['signal']}[{row['bit']}]")
    return cases


def simulate(folder, name, cut):
    define = [f"-DCUT={cut}"] if cut else []
    binary = folder / f"eq_{re.sub(r'[^A-Za-z0-9]+', '_', name)}.vvp"
    chain = len((folder / "clb_config.txt").read_text().split())
    code = subprocess.run(["iverilog", "-g2012", f"-DCHAIN={chain}", "-DCYCLES=1000", *define, "-s", "clb_equiv_tb",
                           "-o", str(binary), "-I.", "orig_netlists.v", "split_dut.v", "clb_equiv_tb.v"],
                          cwd=folder, capture_output=True, text=True).returncode
    if code:
        return name, None
    out = subprocess.run(["vvp", str(binary)], cwd=folder, capture_output=True, text=True).stdout
    binary.unlink()
    found = re.search(r"chain_errors=(\d+) compared=(\d+) errors=(\d+) unknown=(\d+)", out)
    return name, tuple(map(int, found.groups())) if found else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=ROOT / "build/of/try/equiv_run")
    parser.add_argument("--support", type=Path, default=ROOT / "build/of/try")
    parser.add_argument("--package", type=Path, required=True, help="folder for the checks, also copied to the server")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--fles", type=int, default=10, help="FLEs in the CLB, half on each layer")
    parser.add_argument("--local", action="store_true", help="each layer's FLEs read only that layer's pins")
    args = parser.parse_args()
    work, support, folder = args.work.resolve(), args.support.resolve(), args.package.resolve()
    print("1. Building the design, splitting the CLB and adding crossing drivers", flush=True)
    build(work, support, args.fles, args.local)
    package(work, support, folder, args.fles, args.local)
    cases = {"none": None, **cut_cases(folder)}
    print(f"2. Simulating {len(cases)} cases", flush=True)
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = dict(pool.map(lambda kv: simulate(folder, *kv), cases.items()))
    failed = []
    for name, result in results.items():
        if result is None:
            failed.append(name)
            continue
        chain_errors, compared, errors, unknown = result
        broken = chain_errors or errors or unknown
        if name == "none" and broken or name.startswith("config chain") and not chain_errors:
            failed.append(name)
        if not name.startswith(("none", "config chain")) and not broken:
            continue
        print(f"{name:34s} chain errors {chain_errors:5d}  output errors {errors:5d} of {compared}")
    logic = [n for n in results if not n.startswith(("none", "config chain"))]
    used = [n for n in logic if results[n] and results[n][2]]
    print(f"logic crossings the design uses, caught when cut: {len(used)} of {len(logic)}")
    if not used:
        failed.append("no logic crossing was caught")
    print("\nFAIL: " + ", ".join(failed) if failed else "\nPASS: the split CLB matches the original, config chain included")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
