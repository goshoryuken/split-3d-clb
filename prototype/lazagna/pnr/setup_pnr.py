#!/usr/bin/env python3
"""Build a copy of the SiliconJackets RTL-to-GDS flow for one CLB block.

The flow targets a chip with SRAM macros and a fixed die. This copies its
scripts, leaves the original alone, and changes what a small block needs: the
top module, clocks, an area-driven floorplan, and no macros. Physical signoff
is off because it needs the macro GDS, and footprint and wires do not need it.
"""
import argparse
from pathlib import Path
import re
import shutil

UTILIZATION = 0.6
FLE = "logical_tile_clb_mode_default__fle"


def edit(path, change):
    text = path.read_text()
    new = change(text)
    if new == text:
        raise SystemExit(f"{path}: nothing changed, the flow scripts may have moved")
    path.write_text(new)


def delete_block(text, start, end):
    """Removes from the line holding start through the line holding end."""
    first = text.index(start)
    first = text.rindex("\n", 0, first) + 1
    last = text.index("\n", text.index(end, first)) + 1
    return text[:first] + text[last:]


def patch_constraints(text, bond_load=0.006, bond_driver="BUFX4", keep_drivers=False):
    start = text.index("if {[sizeof_collection [get_ports clk_i]] > 0} {")
    end = text.index("# ================= #", start)
    clocks = """foreach {name ports} {coreClk {clk n_clk_0} progClk {prog_clk n_prog_clk_0}} {
    foreach port $ports {
        if {[sizeof_collection [get_ports -quiet $port]] > 0} {
            create_clock -name $name -period "$CLOCK_PERIOD" \\
                -waveform "[expr $CLOCK_PERIOD/2] $CLOCK_PERIOD" [get_ports $port]
            set_fix_hold $name
        }
    }
}
# Routing blocks have no data clock, so their paths are timed against a virtual one.
if {[sizeof_collection [get_clocks -quiet coreClk]] == 0} {
    create_clock -name coreClk -period "$CLOCK_PERIOD" -waveform "[expr $CLOCK_PERIOD/2] $CLOCK_PERIOD"
}
if {[sizeof_collection [get_clocks -quiet progClk]] > 0} {
    set_clock_groups -asynchronous -group coreClk -group progClk
}
set_input_delay 0 -clock coreClk [remove_from_collection [all_inputs] [get_ports -quiet {clk n_clk_0 prog_clk n_prog_clk_0}]]
set_output_delay 0 -clock coreClk [all_outputs]
set_false_path -from [get_ports -quiet {reset set pReset n_reset_0 n_set_0 n_pReset_0}]
# Bond pads between layers: what an output port drives across the bond (a pad and a
# receiver, or with direct crossings the other layer's net), and what drives an input port.
if {[sizeof_collection [get_ports -quiet x_*]] > 0} {
    set_load 0.006 [get_ports x_* -filter "direction == out"]
    set_driving_cell -lib_cell BUFX4 [get_ports x_* -filter "direction == in"]
}
"""
    clocks = clocks.replace("set_load 0.006", f"set_load {bond_load}").replace("-lib_cell BUFX4", f"-lib_cell {bond_driver}")
    if keep_drivers:
        # The sending driver is sized for the other layer's net, which neither tool sees. Lock the
        # BUFX16 cells, not the xd_* wrappers: a locked wrapper is never uniquified, and Innovus
        # rejects the netlist (IMPCCOPT-4255).
        clocks += 'set_dont_touch [get_cells -quiet -hierarchical -filter "ref_name == BUFX16"]\n'
    return text[:start] + clocks + text[end:]


KEEP_DRIVERS_APR = """# Crossing drivers stay sized for the other layer's net (setup_pnr.py --keep-crossing-drivers).
set xd [dbGet -e -p top.insts.name *xd_*/buffer]
if {$xd ne ""} { dbSet $xd.dontTouch true }
puts "KEEP_DRIVERS [llength $xd]"
"""


def patch_floorplan(text, core):
    size = f"-adjustToSite -s {core} {core}" if core else f"-r 1.0 {UTILIZATION}"
    text = re.sub(r"floorPlan -site CoreSite -adjustToSite \\\s*\n\s*-s [\d.]+ [\d.]+ \\",
                  f"floorPlan -site CoreSite {size} \\\\", text)
    text = delete_block(text, "set macro_name_1 data_memory/u_sram", "addHaloToBlock {21 21 21 21} $macro_name_2")
    text = delete_block(text, "createInstGroup group_SRAMs", "deselectAll")
    # Bond pads stay out of the edge pins and go where bond_pads() puts them.
    for direction in (0, 1):
        old = f"[dbget [dbget top.terms.isOutput {direction} -p].name]"
        assert old in text
        text = text.replace(old, f'[lsearch -all -inline -not {old} "x_*"]')
    return text.rstrip() + "\nif {[file exists $::config::SCRIPTS/pads.tcl]} {source $::config::SCRIPTS/pads.tcl}\n"


def bond_pads(rtl, core, center=False):
    """Places one top-metal pad per net between layers, at the same spot on both layers.

    Sites sit between the power stripes, which take 16 of every 40 microns on met4
    and met5. Ports are sorted, so both layers give each net the same site. Pads
    spread evenly over the core, or with center take the sites nearest its middle.
    """
    ports = sorted(set(re.findall(r"^\s*(?:input|output)\s+(x_\w+)\s*;", rtl.read_text(), re.M)))
    origin, offset, step = 9.66, 24.8, 40
    lines = [origin + offset + step * i for i in range(int((core - offset) / step) + 1)]
    sites = [(x, y) for y in lines for x in lines]
    if len(ports) > len(sites):
        raise SystemExit(f"{len(ports)} pads do not fit in {len(sites)} sites")
    if center:
        middle = core / 2
        picked = sorted(sites, key=lambda s: ((s[0] - middle) ** 2 + (s[1] - middle) ** 2, s))[:len(ports)]
    else:
        picked = [sites[i * len(sites) // len(ports)] for i in range(len(ports))]
    return "".join(f"createPhysicalPin {port} -net {port} -layer 5 -rect {x - 1.25:.2f} {y - 1.25:.2f} {x + 1.25:.2f} {y + 1.25:.2f}\n"
                   for port, (x, y) in zip(ports, picked))


def loop_cuts(rtl):
    """Cuts each LUT-to-output path, which every combinational loop runs through.

    Left alone, the tool breaks the loops at arbitrary places and stops seeing
    those paths, differently in each block.
    """
    text = rtl.read_text()
    fles = sorted(set(re.findall(rf"\b{FLE}(?:_tap)?\s+({FLE}_\d+)\s*\(", text)))
    if FLE in text and not fles:
        raise SystemExit(f"{rtl}: no FLEs found")
    return "".join(f"set_disable_timing [get_cells {fle}/{FLE}_mode_n1_lut6__ble6_0/mux_ble6_out_0/INVTX1_1_/*]\n"
                   for fle in fles)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flow", type=Path, required=True, help="onboarding repo")
    parser.add_argument("--rtl", type=Path, required=True)
    parser.add_argument("--top", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--period", type=float, default=15.0)
    parser.add_argument("--core", type=float, help="square core size in microns, so both layers match")
    parser.add_argument("--center-pads", action="store_true", help="bond pads at the sites nearest the core's middle")
    parser.add_argument("--bond-load", type=float, default=0.006, help="pF an output port drives across the bond")
    parser.add_argument("--bond-driver", default="BUFX4", help="cell that drives an input port across the bond")
    parser.add_argument("--keep-crossing-drivers", action="store_true",
                        help="stop synthesis and Innovus resizing the crossing drivers (direct crossings)")
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(args.flow / "scripts", out / "scripts", dirs_exist_ok=True)
    shutil.copy(args.flow / "envsetup", out / "envsetup")
    resources = args.flow / "resources"
    if resources.exists() and not (out / "resources").exists():
        (out / "resources").symlink_to(resources.resolve())
    (out / "inputs/rtl").mkdir(parents=True, exist_ok=True)
    shutil.copy(args.rtl, out / "inputs/rtl" / f"{args.top}.v")

    s = out / "scripts"

    def config(text):
        text = re.sub(r"variable DESIGN\s+chip_top\s*\n", "", text, count=1)
        text = re.sub(r"variable DESIGN\s+chip_top", f"variable DESIGN {args.top}", text)
        text = re.sub(r"variable CLOCK_PERIOD\s+[\d.]+", f"variable CLOCK_PERIOD {args.period}", text)
        return re.sub(r"variable SIGNOFF\s+1", "variable SIGNOFF 0", text)
    edit(s / "config.tcl", config)
    edit(s / "synthesis/steps/step_constraints.tcl", lambda t: patch_constraints(t, args.bond_load, args.bond_driver, args.keep_crossing_drivers))
    edit(s / "synthesis/steps/step_define_library.tcl",
         lambda t: "\n".join(line for line in t.split("\n") if "CF_SRAM" not in line))
    edit(s / "apr/steps/step_init_design.tcl",
         lambda t: "\n".join(line for line in t.split("\n") if "CF_SRAM" not in line)
         .replace("set ::init_top_cell chip_top", "set ::init_top_cell $::config::DESIGN"))
    (s / "loop_cuts.sdc").write_text(loop_cuts(args.rtl))
    sdc = '"$::config::DESIGN_ROOT/outputs/synthesis/$::config::DESIGN.sdc" \\\n'
    edit(s / "apr/steps/step_corners.tcl",
         lambda t: "\n".join(line for line in t.split("\n") if "CF_SRAM" not in line)
         .replace(sdc, sdc + '                 "$::config::SCRIPTS/loop_cuts.sdc" \\\n'))
    edit(s / "apr/steps/step_floorplan.tcl", lambda t: patch_floorplan(t, args.core))
    if args.keep_crossing_drivers:
        # Innovus ignores synthesis's dont_touch and sizes each driver for its own layer only.
        edit(s / "apr/steps/step_place_std_cells.tcl", lambda t: KEEP_DRIVERS_APR + t)
    if args.core:
        (s / "pads.tcl").write_text(bond_pads(args.rtl, args.core, args.center_pads))
    edit(s / "apr/apr.tcl", lambda t: t.replace("if {$::config::INTERACTIVE} {\n\tsj_end_collection",
         "catch {saveDesign $::config::DBS_DIR/$::config::DESIGN.routed.enc}\n"
         "catch {summaryReport -noHtml -outfile $::config::RPT_DIR/summary.rpt}\n"
         "catch {report_timing > $::config::RPT_DIR/final_timing.rpt}\n"
         "if {$::config::INTERACTIVE} {\n\tsj_end_collection"))
    print(f"{out}: flow ready for {args.top}")


if __name__ == "__main__":
    main()
