# The flow saves its final design only at signoff, which these blocks skip, so
# this routes the clock tree save again and keeps the result for timing reports.
if {[catch {
    set db [lindex [glob ../apr/*.postCts.dat.dat] 0]
    set top [file rootname [file rootname [file rootname [file tail $db]]]]
    restoreDesign $db $top
    setMultiCpuUsage -localCpu 8
    source $::env(SCRIPTS)/apr/steps/step_route.tcl
    saveDesign routed.enc
    summaryReport -noHtml -outfile summary.rpt
} failure]} {
    puts "ROUTE_FAILED: $failure"
}
exit
