# Writes a routed block's netlist, wire parasitics and delays to outputs/paths,
# for joined timing across both layers and for post-layout simulation.
if {[catch {
    set top [string map {.gate.v {}} [file tail [lindex [glob ../synthesis/*.gate.v] 0]]]
    restoreDesign [lindex [glob ../apr/DBS/*.routed.enc.dat routed.enc.dat] 0] $top
    setMultiCpuUsage -localCpu 2
    setExtractRCMode -engine postRoute
    extractRC
    rcOut -spef $top.spef -rc_corner typical_rc
    saveNetlist $top.routed.v
    # Delays through the arcs cut for timing still belong in the simulation.
    set_interactive_constraint_modes [all_constraint_modes -active]
    foreach leaf [dbGet top.insts.name */mux_ble6_out_0/INVTX1_1_/*] { reset_disable_timing [get_cells $leaf] }
    write_sdf -recompute_delay_calc -precision 4 $top.sdf
    puts "EXPORT_DONE $top"
} failure]} {
    puts "EXPORT_FAILED: $failure"
}
exit
