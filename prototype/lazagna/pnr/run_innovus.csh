#!/bin/tcsh -f
# Runs one Tcl file in Innovus, in a block's flow environment, from outputs/paths.
# Usage: tcsh -f run_innovus.csh <block folder> <tcl file>
set tcl = `realpath $2`
cd $1
unsetenv ENV_SETUP
# The tools' temporary files are large, and the home folder has a quota.
mkdir -p /tmp/$USER
setenv TMPDIR /tmp/$USER
source envsetup
setenv SCRIPTS `realpath scripts`
eval `grep '^setenv CDS_LIC_FILE' scripts/SJapr`
mkdir -p outputs/paths
cd outputs/paths
nice +19 innovus -log paths.log -init $tcl -legacy_ui -nowin
