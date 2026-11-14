#!/bin/bash
# VPR under /usr/bin/time -l (macOS): run.log ends with wall time and "maximum resident set size".
# run_hardblocks.sh TIMED=1 sets VPR_REAL to the VPR binary.
exec /usr/bin/time -l "${VPR_REAL:?VPR binary}" "$@"
