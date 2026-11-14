#!/bin/tcsh -f
# Checks routed gates against the original CLB for one case, in the folder that
# run_clb_equiv.py builds:
# a clock period, with or without extracted delays, and an optional wire held at 0.
# Usage: tcsh -f run_equiv_gate.csh <package folder> <bonded layout folder> <block folder for the tool setup> <period> <SDF|NONE> <cut net or none>
set here = `dirname $0`
set here = `realpath $here`
set package = `realpath $1`
set layout = `realpath $2`
set period = $4
set mode = $5
set cut = $6
cd $3
unsetenv ENV_SETUP
source envsetup
eval `grep '^setenv CDS_LIC_FILE' scripts/SJapr`
set cells = `realpath resources`/cadence_sky130/sky130_scl_9T_0.1.2
cd $package
# A layout folder holding clb_2d/ is the flat 2D CLB; otherwise the two bonded layers.
set flat = ""
set dut = gate_dut.v
if (-d $layout/clb_2d) then
  set flat = "+define+FLAT"
  set dut = gate_2d.v
  if (! -f $dut) then
    cp $layout/clb_2d/outputs/paths/logical_tile_clb_mode_clb_.sdf clb_2d.sdf
    python3 $here/rename_netlist.py $layout/clb_2d/outputs/paths/logical_tile_clb_mode_clb_.routed.v $dut g2_
  endif
else if (! -f $dut) then
  cp $layout/clb_half0/outputs/paths/clb_layer0.sdf $layout/clb_half1/outputs/paths/clb_layer1.sdf .
  sed 's/^module logical_tile_clb_mode_clb_(/module clb_dut(/' $layout/join3d/joined.v > $dut
endif
set chain = `wc -l < clb_config.txt`
set define = "+define+PERIOD=$period +define+CHAIN=$chain +define+CYCLES=1000 $flat"
if ($mode == SDF) set define = "$define +define+SDF"
if ($cut != none) set define = "$define +define+CUT=$cut"
set name = gate${flat:s/+define+FLAT/2d/}_${period}_${mode}_`echo $cut | rev | cut -c1-28 | rev`
nice +19 xrun -64bit -sv -q -timescale 1ns/1ps -top clb_equiv_tb $define +incdir+. \
  orig_netlists.v $dut clb_equiv_tb.v $cells/sky130_scl_9T/verilog/sky130_scl_9T.v \
  $cells/sky130_scl_9T_HS/verilog/sky130_scl_9T_HS.v -xmlibdirname xc_$name -l $name.log >& /dev/null
rm -rf xc_$name
echo "${name}: `grep -E '^EQUIV' $name.log`"
