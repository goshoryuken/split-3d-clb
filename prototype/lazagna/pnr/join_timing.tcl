# Times every CLB input and FLE feedback path through the crossbar of a routed
# CLB and writes clb_paths.csv. With PNR_LAYERS=2 it times the two layers joined
# into one circuit, so a pin carries its real load on both layers. Otherwise it
# times the flat 2D CLB the same way.

proc points_of {path} {
    set points {}
    foreach_in_collection point [get_property $path timing_points] {
        lappend points [get_object_name [get_property $point pin]] [get_property $point arrival]
    }
    return $points
}

proc last_arrival {points pattern} {
    set arrival ""
    foreach {pin time} $points {
        if {[string match $pattern $pin]} { set arrival $time }
    }
    return $arrival
}

proc write_path {fh kind start mux path start_pattern} {
    if {[sizeof_collection $path] == 0} {
        puts $fh "$kind,$start,$mux,,,,,"
        return
    }
    set points [points_of $path]
    set begin [lindex $points 1]
    if {$start_pattern ne ""} { set begin [last_arrival $points $start_pattern] }
    puts $fh [join [list $kind $start $mux \
        [get_property $path launching_clock_open_edge_time] \
        [get_property $path drive_adjustment] \
        $begin [last_arrival $points "$mux/*"] [get_property $path arrival]] ,]
}

set FLE logical_tile_clb_mode_default__fle
set two [expr {$::env(PNR_LAYERS) == 2}]
# PNR_FLES sets the CLB size, 10 by default; each CLB has four inputs per FLE.
set fles [expr {[info exists ::env(PNR_FLES)] ? $::env(PNR_FLES) : 10}]
set half [expr {$fles / 2}]
proc inside {two fle} { return [expr {$two ? "layer[expr {$fle >= $::half}]/" : ""}] }

if {[catch {
    # Defaults are sky130; PNR_LIBS, PNR_PERIOD, PNR_DRIVE and PNR_LOAD change the kit.
    set lib $::env(RESOURCES)/cadence_sky130/sky130_scl_9T_0.1.2
    set libs [list $lib/sky130_scl_9T/lib/sky130_tt_1.8_25_nldm.lib $lib/sky130_scl_9T_HS/lib/sky130_tt_1.8_25_nldm.lib]
    if {[info exists ::env(PNR_LIBS)]} { set libs $::env(PNR_LIBS) }
    read_lib $libs
    read_verilog $::env(PNR_NETLIST)
    set_top_module logical_tile_clb_mode_clb_
    read_spef $::env(PNR_SPEF)

    set period [expr {[info exists ::env(PNR_PERIOD)] ? $::env(PNR_PERIOD) : 2.0}]
    set drive [expr {[info exists ::env(PNR_DRIVE)] ? $::env(PNR_DRIVE) : "BUFX2"}]
    set load [expr {[info exists ::env(PNR_LOAD)] ? $::env(PNR_LOAD) : 0.033442}]
    foreach {name port} {coreClk clk progClk prog_clk} {
        create_clock -name $name -period $period -waveform [list [expr {$period/2}] $period] [get_ports $port]
    }
    set_clock_groups -asynchronous -group coreClk -group progClk
    set_propagated_clock [all_clocks]
    set data [remove_from_collection [all_inputs] [get_ports {clk prog_clk}]]
    set_input_delay 0 -clock coreClk $data
    set_output_delay 0 -clock coreClk [all_outputs]
    set_driving_cell -lib_cell $drive $data
    set_load -pin_load $load [all_outputs]
    set_false_path -from [get_ports {reset set pReset}]

    set muxes {}
    set flops {}
    for {set fle 0} {$fle < $fles} {incr fle} {
        set path [inside $two $fle]
        set ble ${path}${FLE}_$fle/${FLE}_mode_n1_lut6__ble6_0
        set_disable_timing [get_cells $ble/mux_ble6_out_0/INVTX1_1_/*]
        lappend flops $ble/${FLE}_mode_n1_lut6__ble6_mode_default__ff_0/DFFSRQ_0_/q_reg_reg
        for {set in 0} {$in < 6} {incr in} { lappend muxes ${path}mux_fle_${fle}_in_$in }
    }
    check_timing -verbose > loops.txt
    report_annotated_parasitics > parasitics.txt

    set fh [open clb_paths.csv w]
    puts $fh "kind,start,mux,edge,drive,begin,mid,end"
    set pins [expr {4 * $fles}]
    set layer_pins [expr {$pins / 2}]
    for {set i 0} {$i < $pins} {incr i} {
        # Local-pin CLBs have one input port per layer, and each reaches its own layer.
        set local [sizeof_collection [get_ports -quiet {clb_I0[0]}]]
        if {$local} {
            set port [get_ports "clb_I[expr {$i >= $layer_pins}]\[[expr {$i % $layer_pins}]\]"]
        } else {
            set port [get_ports "clb_I\[$i\]"]
        }
        foreach mux $muxes {
            if {$local && ([string match layer1/* $mux] != ($i >= $layer_pins))} { continue }
            write_path $fh pin clb_I$i $mux [report_timing -collection -from $port -through [get_pins $mux/out*]] ""
        }
    }
    foreach flop $flops {
        foreach mux $muxes {
            # sky130 names the flip-flop clock pin CK, ASAP7 names it CLK.
            set clock_pin [get_pins -quiet $flop/CK]
            if {[sizeof_collection $clock_pin] == 0} { set clock_pin [get_pins $flop/CLK] }
            write_path $fh feedback $flop $mux [report_timing -collection -from $clock_pin -through [get_pins $mux/out*]] "*/mux_ble6_out_0/*"
        }
    }
    close $fh
    report_timing > worst.txt
    puts "JOIN_DONE"
} failure]} {
    puts "JOIN_FAILED: $failure"
}
exit
