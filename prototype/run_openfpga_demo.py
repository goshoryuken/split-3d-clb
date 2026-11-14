#!/usr/bin/env python3
"""Generate and verify a restricted spanning-CLB fabric with patched OpenFPGA.

Simulation is functional only. During serial programming, mux/FLE outputs are
held at zero to prevent transient combinational loops. All holds are released
before exhaustive output checking. No physical timing is simulated.
"""
import argparse
from collections import Counter
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openfpga", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument("--elaborate-only", action="store_true")
    parser.add_argument("--circuit", choices=("ten_luts", "asymmetric_ten_luts"), default="ten_luts")
    parser.add_argument("--check-output-swap", action="store_true")
    args = parser.parse_args()
    circuit = args.circuit
    reference = ROOT / "prototype" / (circuit + "_reference.v")
    source, work = args.source.resolve(), args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)

    def execute(command, log, timeout=120, expect_failure=False):
        with (work / "commands.txt").open("a") as stream:
            stream.write(repr(command) + "\n")
        try:
            result = subprocess.run(command, cwd=work, text=True, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            (work / log).write_bytes((error.stdout or b"") + (error.stderr or b"") + b"\nTIMEOUT\n")
            (work / (log + ".status")).write_text("TIMEOUT\n")
            raise
        output = result.stdout + result.stderr
        (work / log).write_text(output)
        (work / (log + ".status")).write_text(str(result.returncode) + "\n")
        if expect_failure:
            assert result.returncode == 1 and "Configured fabric mismatch at" in output, output[-2000:]
            assert "Unknown configured output" not in output
            assert "PASS: configured fabric" not in output
            return output
        if result.returncode:
            raise RuntimeError(f"Exit {result.returncode}; inspect {work / log}\n{output[-2000:]}")
        return output

    arch = (source / "openfpga_flow/vpr_arch/k6_frac_N10_tileable_40nm.xml"
            if args.legacy else ROOT / "prototype/openfpga_split_fle.xml")
    device_name = ET.parse(arch).getroot().find("./layout/fixed_layout").get("name")
    companion = source / "openfpga_flow/openfpga_arch/k6_frac_N10_behavioral_40nm_openfpga.xml"
    (work / "openfpga_arch.xml").write_text(companion.read_text().replace("${OPENFPGA_PATH}", str(source)))
    settings = source / "openfpga_flow/openfpga_simulation_settings/auto_sim_openfpga.xml"
    # These are illustrative testbench settings, not target physical frequencies.
    (work / "simulation.xml").write_text(settings.read_text().replace(
        'frequency="auto" num_cycles="auto"', 'frequency="100e6" num_cycles="70"'))
    commands = [
        f"vpr {arch} {ROOT}/prototype/{circuit}.blif --device {device_name} --route_chan_width 100 --disp off --seed {args.seed}",
        f"read_openfpga_arch -f {work}/openfpga_arch.xml",
        f"read_openfpga_simulation_setting -f {work}/simulation.xml",
        "link_openfpga_arch",
        "check_netlist_naming_conflict --fix --report netlist_renaming.xml",
        "pb_pin_fixup", "lut_truth_table_fixup",
        # Compression is not validated for layers without physical pin sites.
        "build_fabric",
        "write_fabric_hierarchy --file fabric_hierarchy.txt",
        "write_fabric_verilog --file fabric --explicit_port_mapping",
        "repack",
        "build_architecture_bitstream --write_file fabric_independent_bitstream.xml",
        "build_fabric_bitstream",
        "write_fabric_bitstream --format plain_text --file fabric.bit",
        f"write_full_testbench --file testbench --reference_benchmark_file_path {reference} --explicit_port_mapping --bitstream fabric.bit",
        "exit",
    ]
    (work / "run.openfpga").write_text("\n".join(commands) + "\n")
    log = execute([str(args.openfpga.resolve()), "-batch", "-f", "run.openfpga"], "run.log")
    assert "Finish execution with 0 errors" in log
    clb = (work / "fabric/lb/logical_tile_clb_mode_clb_.v").read_text()
    offsets = Counter(re.findall(r"vtr_parent_relative_layer_offset = (\d+)", clb))
    assert offsets == ({} if args.legacy else {"0": 5, "1": 5}), offsets
    bits = sum(len(line) for line in (work / "fabric.bit").read_text().splitlines()
               if re.fullmatch("[01]+", line))
    assert bits > 0
    if not args.legacy:
        rows = (work / "internal_layers.tsv").read_text().splitlines()
        atoms = [line.split("\t") for line in rows
                 if line.startswith("atom\t")]
        assert len(atoms) == 10 and len({r[2] for r in atoms}) == 1
        assert Counter(r[3] for r in atoms) == {"0": 5, "1": 5}
        edges = [line.split("\t") for line in rows if line.startswith("edge\t")]
        assert any(r[2].startswith("n") and r[5] != r[6] for r in edges), "No used LUT-output crossing"
    execute(["iverilog", "-g2012", "-s", "fpga_top", "-o", "fabric_elaborated", "fabric/fabric_netlists.v"], "elaboration.log")
    print(f"PASS: fabric generated and elaborated; {bits} configuration bits; offsets {dict(offsets)}", flush=True)
    if args.elaborate_only:
        return

    tb = work / "testbench" / (circuit + "_autocheck_top_tb.v")
    text = tb.read_text()
    # This behavioral bench uses a five-tick half-period: #1 settling is
    # strictly between opposite clock edges. Fail if the generator changes it.
    assert re.search(r"#5\s+__op_clock___reg__\[0\] = ~__op_clock___reg__\[0\];", text)
    assert "always@(negedge __op_clock__[0])" in text
    assert re.search(r"#20\s+__greset__\[0\] = 1'b0;", text)
    text, replaced = re.subn(r"always@\(negedge __op_clock__\[0\]\) begin\s+a_shared_input <= \$random;.*?f_shared_input <= \$random;\s+end",
                            "", text, count=1, flags=re.S)
    assert replaced == 1, "Unexpected generated stimulus; do not silently modify a different testbench"
    # The generated bench otherwise runs indefinitely after printing success.
    text = text.replace('$display("Simulation Succeed");', '$fatal(1, "Exhaustive checker did not finish");')
    text = text.replace('$display("Simulation Failed with %d error(s)", nb_error);', '$fatal(1, "Generated checker failed: %d", nb_error);')
    # Discover mux instance paths in the emitted hierarchy. The generator's
    # --include_signal_init references transistor instances absent from this
    # behavioral library, so initialize the actual emitted mux outputs instead.
    modules = {}
    for file in (work / "fabric").rglob("*.v"):
        modules.update(re.findall(r"^\s*module\s+(\w+)\b(.*?)^\s*endmodule", file.read_text(), re.S | re.M))
    held_paths = []

    def visit(kind, path):
        if "basis_" in kind:
            held_paths.append(path + ".out")
            return
        if kind == "logical_tile_clb_mode_default__fle":
            held_paths.append(path + ".fle_out")
        for child, instance in re.findall(r"^\s*(\w+)\s+(\w+)\s*\(", modules.get(kind, ""), re.M):
            if child in modules:
                visit(child, path + "." + instance)

    visit("fpga_top", "FPGA_DUT")
    assert held_paths and len(set(held_paths)) == len(held_paths)
    holds = "reg holds_released = 1'b0;\ninitial begin\n" + "".join(f"force {path} = '0;\n" for path in held_paths)
    holds += "wait(__config_all_done__ === 1'b1);\n"
    holds += "".join(f"release {path};\n" for path in held_paths) + "holds_released = 1'b1;\nend\n"
    inputs = "{" + ",".join(c + "_shared_input" for c in "fedcba") + "}"
    actual = "{" + ",".join(f"n{i}_fpga" for i in reversed(range(10))) + "}"
    expected = "{" + ",".join(f"n{i}_benchmark" for i in reversed(range(10))) + "}"
    marker = "PASS: configured fabric matches all 64 input vectors on all 10 outputs"
    check = f"""
integer checked_vector;
integer checked_count = 0;
initial begin
    wait(holds_released === 1'b1);
    wait(__greset__[0] === 1'b0);
    // Let the generated checker consume its initialization-only falling edge.
    @(negedge __op_clock__[0]);
    for (checked_vector=0; checked_vector<64; checked_vector=checked_vector+1) begin
        @(posedge __op_clock__[0]);
        {inputs} = checked_vector;
        #1;
        if ((^{actual} === 1'bx) || (^{expected} === 1'bx))
            $fatal(1, "Unknown configured output at %d", checked_vector);
        if ({actual} !== {expected})
            $fatal(1, "Configured fabric mismatch at %d: actual=%b expected=%b", checked_vector, {actual}, {expected});
        // Preserve the generated checker and allow its NBA flag/error updates
        // to finish before proceeding or declaring success on the final vector.
        @(negedge __op_clock__[0]);
        #1;
        if (nb_error !== 0) $fatal(1, "Generated checker failed: %d", nb_error);
        checked_count = checked_count + 1;
    end
    if (checked_count != 64) $fatal(1, "Incomplete exhaustive coverage: %d", checked_count);
    $display("CHECKED: %0d vectors, 10 outputs each; generated checker errors=%0d", checked_count, nb_error);
    $display("{marker}");
    $finish;
end
"""
    final_text = text.replace("endmodule", holds + check + "\nendmodule", 1)
    assert len(re.findall(r"^force ", final_text, re.M)) == len(held_paths)
    assert len(re.findall(r"^release ", final_text, re.M)) == len(held_paths)
    tb.write_text(final_text)
    print(f"PASS: {len(held_paths)} programming holds have matching releases; checker waits for release completion", flush=True)
    execute(["iverilog", "-g2012", "-s", circuit + "_autocheck_top_tb", "-o", "fabric_sim",
             "fabric/fabric_netlists.v", str(tb), str(reference)], "simulation-compile.log")
    output = execute(["vvp", "fabric_sim"], "simulation.log", timeout=120)
    assert output.count(marker) == 1
    assert "CHECKED: 64 vectors, 10 outputs each; generated checker errors=0" in output
    assert not re.search(r"\b(mismatch|fatal|error|unknown)\b", output, re.I), output
    print(marker)
    if args.check_output_swap:
        # Swap only the pad-to-output assignments; reference/checker stay intact.
        swapped, count = re.subn(r"(assign n)([02])(_fpga\[0\] =)",
                                lambda m: m[1] + ("2" if m[2] == "0" else "0") + m[3], final_text)
        assert count == 2
        mutant = work / "testbench" / "output_swap.v"
        mutant.write_text(swapped)
        execute(["iverilog", "-g2012", "-s", circuit + "_autocheck_top_tb", "-o", "fabric_swap_sim",
                 "fabric/fabric_netlists.v", str(mutant), str(reference)], "output-swap-compile.log")
        execute(["vvp", "fabric_swap_sim"], "output-swap.log", expect_failure=True)
        print("PASS: intentional n0/n2 output swap rejected by configured-fabric checker")


if __name__ == "__main__":
    main()
