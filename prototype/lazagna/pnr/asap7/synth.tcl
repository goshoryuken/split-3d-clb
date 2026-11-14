# Synthesizes one block in ASAP7 with Design Compiler. Same constraints as the
# sky130 flow: a clock neither block meets, reset excluded, bond pads lightly loaded.
set top $::env(PNR_TOP)
set period $::env(PNR_PERIOD)
set kit $::env(ASAP7)
set suffix _ASAP7_75t_R
set target_library [glob $kit/db/*.db]
set link_library [concat * $target_library]
define_design_lib WORK -path ./WORK
analyze -format verilog $::env(PNR_RTL)
elaborate $top
current_design $top
link
foreach {name port} {coreClk {clk n_clk_0} progClk {prog_clk n_prog_clk_0}} {
    foreach p $port {
        if {[sizeof_collection [get_ports -quiet $p]] > 0} {
            create_clock -name $name -period $period -waveform [list [expr {$period/2.0}] $period] [get_ports $p]
        }
    }
}
if {[sizeof_collection [get_clocks -quiet coreClk]] == 0} {
    create_clock -name coreClk -period $period -waveform [list [expr {$period/2.0}] $period]
}
if {[sizeof_collection [get_clocks -quiet progClk]] > 0} {
    set_clock_groups -asynchronous -group coreClk -group progClk
}
set data [remove_from_collection [all_inputs] [get_ports -quiet {clk n_clk_0 prog_clk n_prog_clk_0}]]
set_driving_cell -lib_cell BUFx2$suffix $data
set_load 3.0 [all_outputs]
set_input_delay 0 -clock coreClk $data
set_output_delay 0 -clock coreClk [all_outputs]
set_false_path -from [get_ports -quiet {reset set pReset n_reset_0 n_set_0 n_pReset_0}]
if {[sizeof_collection [get_ports -quiet x_*]] > 0} {
    set_load 1.0 [get_ports x_* -filter "direction == out"]
    set_driving_cell -lib_cell BUFx4$suffix [get_ports x_* -filter "direction == in"]
}
set_dont_use [get_lib_cells */*x1p*$suffix]
set_dont_use [get_lib_cells */*xp*$suffix]
set_dont_use [get_lib_cells */SDF*]
set_dont_use [get_lib_cells */ICG*]
set_fix_multiple_port_nets -all -buffer_constants
compile_ultra -no_autoungroup -no_boundary_optimization
# The same loop cuts as the sky130 flow, so the layout tool sees the same paths.
set cuts [get_cells -quiet -hierarchical -filter "full_name =~ */mux_ble6_out_0/INVTX1_1_/*"]
if {[sizeof_collection $cuts] > 0} { set_disable_timing $cuts }
report_area > area.rpt
report_timing > timing.rpt
write -format verilog -hierarchy -output $top.gate.v
write_sdc $top.sdc
exit
