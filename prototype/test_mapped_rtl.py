#!/usr/bin/env python3
"""Exhaustively check the ten-LUT VPR netlist using functional primitive models."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--netlist", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--circuit", choices=("ten_luts", "asymmetric_ten_luts"), default="ten_luts")
parser.add_argument("--check-output-swap", action="store_true")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
reference_files = []
tb_text = (ROOT / "ten_luts_tb.v").read_text()
if args.circuit == "asymmetric_ten_luts":
    reference = args.output.resolve() / "reference.v"
    reference.write_text((ROOT / "asymmetric_ten_luts_reference.v").read_text().replace(
        "module asymmetric_ten_luts(", "module reference("))
    reference_files.append(str(reference))
    tb_text = tb_text.replace("ten_luts dut", "asymmetric_ten_luts dut")
    tb_text = tb_text.replace("reg [9:0] expected;", "wire [9:0] expected;")
    start = tb_text.index("            expected[0]")
    end = tb_text.index("            #1;", start)
    tb_text = tb_text[:start] + tb_text[end:]
    instance = tb_text[tb_text.index("    asymmetric_ten_luts dut"):tb_text.index("    initial begin")]
    tb_text = tb_text.replace("    initial begin", instance.replace("asymmetric_ten_luts dut", "reference ref_dut").replace("outputs[", "expected[") + "    initial begin", 1)

def simulate(text, name, expect_failure=False):
    tb = args.output.resolve() / (name + ".v")
    tb.write_text(text)
    binary = args.output.resolve() / name
    command = ["iverilog", "-g2012", "-s", "ten_luts_tb", "-o", str(binary),
               str(args.netlist.resolve()), str(ROOT / "functional_primitives.v"), str(tb), *reference_files]
    compile_result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (args.output / (name + "-compile.log")).write_text(compile_result.stdout + compile_result.stderr)
    compile_result.check_returncode()
    result = subprocess.run(["vvp", str(binary)], capture_output=True, text=True, timeout=60)
    (args.output / (name + ".log")).write_text(result.stdout + result.stderr)
    if expect_failure:
        assert result.returncode != 0 and "Mismatch at input" in result.stdout
        assert "PASS: all 64" not in result.stdout
        print("PASS: intentional n0/n2 output swap rejected by mapped checker")
    else:
        result.check_returncode()
        assert "PASS: all 64 input vectors match all 10 outputs" in result.stdout
        print(result.stdout, end="")

simulate(tb_text, "simulation")
if args.check_output_swap:
    # Swap only DUT connections, leaving the reference and checker unchanged.
    swapped = tb_text.replace(".n0(outputs[0])", ".n0(outputs[2])").replace(".n2(outputs[2])", ".n2(outputs[0])")
    assert swapped != tb_text
    simulate(swapped, "output-swap", expect_failure=True)
