#!/bin/bash
# Times the joined two-layer CLB and the 2D CLB from the ASAP7 layouts, the same
# way as in sky130, and compares them path by path.
set -e
B="$(cd "$(dirname "$0")/.." && pwd)"
A=${WORK:-/tmp/$USER/asap}
K=${ASAP7:-/tmp/$USER/sc7p5t}
mkdir -p $A/join3d $A/join2d
python3 $B/join_netlist.py ~/3d-clb/pnr_bond/split/clb_split.v $A/join3d $A/clb_layer0/clb_layer0.routed.v $A/clb_layer1/clb_layer1.routed.v
export PNR_LIBS="$(ls $K/LIB/NLDM/*.lib | tr '\n' ' ')" PNR_PERIOD=300 PNR_DRIVE=BUFx2_ASAP7_75t_R PNR_LOAD=3.0
PNR_LAYERS=2 PNR_NETLIST=$A/join3d/joined.v PNR_SPEF="$A/join3d/top.spef $A/clb_layer0/clb_layer0.spef $A/clb_layer1/clb_layer1.spef" \
  tcsh -f $B/run_tempus.csh ~/3d-clb/pnr_fast/clb_half $A/join3d $B/join_timing.tcl > $A/join3d.log 2>&1
PNR_LAYERS=1 PNR_NETLIST=$A/logical_tile_clb_mode_clb_/logical_tile_clb_mode_clb_.routed.v PNR_SPEF=$A/logical_tile_clb_mode_clb_/logical_tile_clb_mode_clb_.spef \
  tcsh -f $B/run_tempus.csh ~/3d-clb/pnr_fast/clb_half $A/join2d $B/join_timing.tcl > $A/join2d.log 2>&1
grep -hE 'JOIN_' $A/join3d.log $A/join2d.log
python3 $B/compare_joined.py $A/join3d/clb_paths.csv $A/join2d/clb_paths.csv
grep -hE 'Slack Time' $A/join3d/worst.txt $A/join2d/worst.txt
