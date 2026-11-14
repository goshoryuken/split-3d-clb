#!/bin/tcsh -f
# Runs one Tcl file in Tempus, in a block's flow environment, from a work folder.
# Usage: tcsh -f run_tempus.csh <block folder> <work folder> <tcl file>
set tcl = `realpath $3`
set work = $2
mkdir -p $work
set work = `realpath $work`
cd $1
unsetenv ENV_SETUP
source envsetup
eval `grep '^setenv CDS_LIC_FILE' scripts/SJapr`
setenv RESOURCES `realpath resources`
cd $work
nice +19 tempus -no_gui -log tempus.log -files $tcl
