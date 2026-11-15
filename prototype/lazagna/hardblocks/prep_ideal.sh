#!/bin/bash
# Seed ideal-clock run folders with each routed-clock run's arch.xml and width.txt, so the
# ideal-clock rerun routes at the same relaxed width (compare_2d_3d.py skips the width search).
# Usage: prep_ideal.sh SRC_OUT DST_OUT    (both with split/ and stack/)
SRC=$1; DST=$2
for f in split stack; do
  mkdir -p $DST/$f
  for d in $SRC/$f/*_hb*/; do
    n=$(basename $d); case $n in *_clk*) continue;; esac
    [ -s $d/width.txt ] && grep -q "Final critical path delay" $d/run.log 2>/dev/null || continue
    t=$DST/$f/${n}_clkideal; [ -e $t ] && continue
    mkdir -p $t && cp $d/arch.xml $d/width.txt $t/
  done
done
ls -d $DST/*/*_clkideal | wc -l
