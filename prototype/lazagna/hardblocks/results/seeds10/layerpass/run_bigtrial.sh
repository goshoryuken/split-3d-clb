#!/bin/bash
# Experiment E: one trial each of lstm and dla_like.small (about 95k LUTs each; both went over
# newdesigns_rule.txt's 4 GB limit), to tell how long a full sweep of the bigger Koios designs would
# take. C's trial (run_newdesigns.sh TRIAL=1: seed 1, split fabric, pass off, k = 1 SPICE delays,
# routed clocks, VPR's minimum-width search then the route at 1.3x the minimum, VPR under
# /usr/bin/time -l), with each VPR step allowed 8 hours and the whole trial stopped at 8 hours.
# The two designs run at the same time, one VPR each, with no other VPR jobs. Every minute ps records
# each VPR's resident memory (OUT/mem.tsv), so a run stopped at the cap still has its peak memory.
# Usage: layerpass/run_bigtrial.sh OUT    Env: BENCH (required: a folder with lstm.blif and
# dla_like.small.blif, which are not in this repo; hardblocks/synth_koios.sh makes them), VPR, CAP
# (seconds, default 28800)
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$(mkdir -p "${1:?usage: run_bigtrial.sh OUT}" && cd "$1" && pwd)
export BENCH=${BENCH:?folder with lstm.blif and dla_like.small.blif}
CAP=${CAP:-28800}
start=$(date +%s)
echo "start $(date '+%F %T')" > $OUT/trial_times.txt
TRIAL=1 TRIAL_TIMEOUT=$CAP BENCHES="lstm dla_like.small" JOBS=2 "$HERE/run_newdesigns.sh" $OUT &
P=$!
printf 'elapsed_s\tpid\trss_kb\tstep\tdesign\n' > $OUT/mem.tsv
while kill -0 $P 2>/dev/null; do
  now=$(date +%s)
  ps -axo pid=,rss=,command= | awk -v t=$((now - start)) -v o="$OUT/" 'index($0, o) && $3 ~ /\/vpr$/ {
    n = split($5, p, "/"); print t "\t" $1 "\t" $2 "\t" (index($0, "--route_chan_width") ? "route" : "search") "\t" p[n] }' \
    >> $OUT/mem.tsv
  if [ $((now - start)) -ge $CAP ]; then
    echo "stopped at the cap ($CAP s) $(date '+%F %T')" >> $OUT/trial_times.txt
    pkill -f "$OUT/"; sleep 10; pkill -9 -f "$OUT/"
    break
  fi
  sleep 60
done
wait $P
echo "end $(date '+%F %T')" >> $OUT/trial_times.txt
