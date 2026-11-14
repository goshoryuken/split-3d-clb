#!/bin/bash
# Ten seeds of the SPICE-delay comparison: own-layer pins first, then the split CLB, sharing 2D runs.
cd ~/3d-clb/lazagna-bundle
export SEEDS="1 2 3 4 5 6 7 8 9 10" JOBS=${JOBS:-12} DELAYS=/tmp/$USER/spice/delays_tt_all.json
OWN=1 OUT=/tmp/$USER/spicesweep_own bash run_spice_delays.sh > /tmp/$USER/seeds10_own.log 2>&1
for s in small big; do
  for d in /tmp/$USER/spicesweep_own/$s/2d_*; do
    [ -e /tmp/$USER/spicesweep/$s/$(basename $d) ] || cp -r $d /tmp/$USER/spicesweep/$s/
  done
done
OUT=/tmp/$USER/spicesweep bash run_spice_delays.sh > /tmp/$USER/seeds10_split.log 2>&1
echo SEEDS10_DONE >> /tmp/$USER/seeds10_split.log
