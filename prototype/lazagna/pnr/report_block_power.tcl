# Writes a routed block's power at one fixed activity to outputs/paths/power.rpt.
# The activity is a default, so compare blocks with each other, not with silicon.
if {[catch {
    set top [string map {.gate.v {}} [file tail [lindex [glob ../synthesis/*.gate.v] 0]]]
    restoreDesign [lindex [glob ../apr/DBS/*.routed.enc.dat routed.enc.dat] 0] $top
    setMultiCpuUsage -localCpu 2
    set_default_switching_activity -input_activity 0.2 -seq_activity 0.1
    report_power -outfile power.rpt
    puts "POWER_DONE $top"
} failure]} {
    puts "POWER_FAILED: $failure"
}
exit
