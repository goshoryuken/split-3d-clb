#!/bin/tcsh -f
# Runs the SiliconJackets flow in one block's folder, in a fresh environment.
cd $1
unsetenv ENV_SETUP
# The tools' temporary files are large, and the home folder has a quota.
mkdir -p /tmp/$USER
setenv TMPDIR /tmp/$USER
source envsetup
nice +19 SJapr flow
