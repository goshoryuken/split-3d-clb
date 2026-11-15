#!/bin/bash
# Equal-track wrapper for compare_2d_3d.py. A routing run (has --route_chan_width) goes to VPR
# unchanged. The minimum-width search instead reports the split fabric's minimum width for this
# design and seed (split_widths.tsv), so compare_2d_3d.py routes the stacked fabric at exactly the
# split fabric's relaxed track count (2 x ceil(1.3 x min / 2)).
HERE=$(cd "$(dirname "$0")" && pwd)
REAL=${VPR_REAL:?path to VPR}
LOOKUP=${EQ_LOOKUP:-$HERE/split_widths.tsv}
for a in "$@"; do [ "$a" = "--route_chan_width" ] && exec "$REAL" "$@"; done
bench=$(basename "$2" .blif); seed=""; prev=""
for a in "$@"; do [ "$prev" = "--seed" ] && seed=$a; prev=$a; done
n=$(awk -F'\t' -v b="$bench" -v s="$seed" '$1==b && $2==s {print $3}' "$LOOKUP")
[ -n "$n" ] || { echo "no split width for $bench seed $seed" >&2; exit 1; }
echo "Equal-track run: minimum-width search skipped, using the split fabric's."
echo "Best routing used a channel width factor of $n"
