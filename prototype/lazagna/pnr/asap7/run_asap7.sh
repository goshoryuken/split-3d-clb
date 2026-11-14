#!/bin/bash
# Runs one block through the ASAP7 flow in /tmp, outside the home folder quota.
# Usage: run_asap7.sh <top module> <RTL file> <period in ps> [core size]
set -e
B="$(cd "$(dirname "$0")" && pwd)"
top=$1
rtl=$2
period=$3
core=$4
export ASAP7=${ASAP7:-/tmp/$USER/sc7p5t}
work=${WORK:-/tmp/$USER/asap}/$top
mkdir -p "$work"
sed 's/BUFX4 buffer/BUFx4_ASAP7_75t_R buffer/' "$rtl" > "$work/$top.v"
cat > "$work/run.csh" <<CSH
cd ~/3d-clb/pnr_fast/clb_half
unsetenv ENV_SETUP
source envsetup
eval \`grep '^setenv CDS_LIC_FILE' scripts/SJapr\`
cd $work
setenv ASAP7 $ASAP7
setenv PNR_TOP $top
setenv PNR_RTL $work/$top.v
setenv PNR_PERIOD $period
setenv PNR_SCRIPTS $B
if ("$core" != "") setenv PNR_CORE $core
if (! -f $top.gate.v) nice +19 dc_shell-t -f $B/synth.tcl > synth.log
nice +19 innovus -log pnr.log -init $B/pnr.tcl -legacy_ui -nowin > pnr.out
CSH
tcsh -f "$work/run.csh" > "$work/run.log" 2>&1
grep -E 'ASAP_PNR_' "$work/pnr.out" | cut -c1-200
