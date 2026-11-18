#!/bin/bash
# Experiment A: the 6 runs of the layer-pass comparison that did not route within VPR's default 50
# router iterations (1 overused routing node left each time), rerun with a higher limit,
# --max_router_iterations $ITERS, the same for pass-on, control and pass-off. Each reruns exactly as
# its sweep did (run_layerpass.sh, crossings/run_crossings.sh), at the same track count (--widths
# from the pass-off routed CSV, as the sweeps), with only the iteration limit added.
#   pass-on   k100 routed eltwise_layer s6, k162 routed robot_rl s2,
#             k162pin routed conv_layer s8 and robot_rl s9
#   control   k162 ideal eltwise_layer s10
#   pass-off  k162 ideal eltwise_layer s7 (crossings/k162_ideal)
# K272=1 instead reruns the 2 pass-on runs of the 2.72x sweep (experiment B) that did not route:
# k272 routed spmv s5 and attention_layer s8.
# NEW=DIR instead reruns the 7 runs of experiment C (run_newdesigns.sh output DIR) that did not route
# within 50 iterations, in that flow, at their widths: k100 softmax s2 split routed and ideal, pass-on
# routed and ideal; k100 reduction_layer s6 stacked routed; k162pin reduction_layer s7 split routed
# and ideal. Output: OUT/new/<same layout as DIR>.
# ABL=DIR instead reruns the 3 ablation runs of experiment E (run_newdesigns_e.sh output DIR) that did
# not route within 50 iterations, at their widths: softmax s10 routed, s3 and s5 ideal (abl_*).
# CHECK=1 instead reruns three runs that did route, with the same higher limit, to show it leaves
# converged runs unchanged: pass-on k162 routed spmv s3 (27 router iterations, the most of any
# routed run in the sweep), pass-on k100 ideal spmv s1 (19), and pass-off k162 routed eltwise_layer
# s7 (17, the routed twin of the failed pass-off run). Compare each with its committed row.
# Usage: layerpass/run_failed.sh OUT     Env: VPR, ITERS (default 200), CHECK=1, K272=1, NEW=DIR.
HERE=$(cd "$(dirname "$0")" && pwd)
S10=$(cd "$HERE/.." && pwd)
LZ=$(cd "$HERE/../../../.." && pwd)
OUT=$(mkdir -p "${1:?usage: run_failed.sh OUT}" && cd "$1" && pwd)
VPR=${VPR:-$LZ/../../build/vpr/vpr/vpr}
J=$S10/crossings/delays_crossings.json
ITERS=${ITERS:-200}
one() {  # OUT SET WIDTHS BENCH SEED ARGS...
  out=$1; set=$2; widths=$3; bench=$4; seed=$5; shift 5; mkdir -p "$out"
  python3 compare_2d_3d.py --vpr "$VPR" \
    "--vpr-args= --timing_report_detail detailed --timing_report_npaths 10 --max_router_iterations $ITERS" \
    --timeout 14400 --slim --seeds $seed --bench-dir "$LZ/hardblocks/koios" --w2d 100 --w3d 100 \
    --hard-crossing-ps 339.23 --hard-blocks columns --relax-w 1.3 --hard-inputs both --no-2d --jobs 1 \
    --benches $bench --output "$out" --n3d 20 --local-inputs --wire-spans 4 15 --own-layer-inputs \
    --delays "$J" 2d10_w100 "$set" --widths "$widths" "$@"
}
W100=$S10/route/split/results_columns.csv
W162=$S10/crossings/k162_route/split/results.csv
W162P=$S10/crossings/k162pin_route/split/results.csv
W272=$S10/crossings/k272_route/split/results.csv
IDEAL=(--clock-modeling ideal)
cd "$LZ"
if [ -n "$CHECK" ]; then
  one $OUT/check/on_k162_route_spmv_3 3d20own_w100_k162 $W162 spmv 3 --layer-pass &
  one $OUT/check/on_k100_ideal_spmv_1 3d20own_w100 $W100 spmv 1 --layer-pass "${IDEAL[@]}" &
  one $OUT/check/off_k162_route_eltwise_layer_7 3d20own_w100_k162 $W162 eltwise_layer 7 &
  wait
  exit
fi
new() {  # OUT BENCH SEED ARGS... (run_newdesigns.sh's flow)
  out=$1; bench=$2; seed=$3; shift 3; mkdir -p "$out"
  python3 compare_2d_3d.py --vpr "$VPR" \
    "--vpr-args= --timing_report_detail detailed --timing_report_npaths 10 --max_router_iterations $ITERS" \
    --timeout 14400 --slim --seeds $seed --bench-dir "${BENCH:-$LZ/hardblocks/koios}" --w2d 100 --w3d 100 \
    --hard-crossing-ps 339.23 --hard-blocks columns --relax-w 1.3 --hard-inputs both --no-2d --jobs 1 \
    --benches $bench --output "$out" "$@"
}
if [ -n "$NEW" ]; then
  N=$(cd "$NEW" && pwd); O=$OUT/new
  SPLIT=(--n3d 20 --local-inputs --wire-spans 4 15 --own-layer-inputs)
  K100=(--delays $J 2d10_w100 3d20own_w100 --widths $N/k100_route/split/results.csv)
  KPIN=(--delays $J 2d10_w100 3d20own_w100_k162pin --widths $N/k162pin_route/split/results.csv)
  new $O/k100_route/split softmax 2 "${SPLIT[@]}" "${K100[@]}" &
  new $O/k100_ideal/split softmax 2 "${SPLIT[@]}" "${K100[@]}" "${IDEAL[@]}" &
  new $O/on/k100_route/split softmax 2 "${SPLIT[@]}" "${K100[@]}" --layer-pass &
  new $O/on/k100_ideal/split softmax 2 "${SPLIT[@]}" "${K100[@]}" --layer-pass "${IDEAL[@]}" &
  new $O/k100_route/stack reduction_layer 6 --stacked --delays $J 2d10_w100 3d10stack_w100 \
    --widths $N/k100_route/stack/results.csv &
  new $O/k162pin_route/split reduction_layer 7 "${SPLIT[@]}" "${KPIN[@]}" &
  new $O/k162pin_ideal/split reduction_layer 7 "${SPLIT[@]}" "${KPIN[@]}" "${IDEAL[@]}" &
  wait
  exit
fi
if [ -n "$ABL" ]; then
  N=$(cd "$ABL" && pwd); O=$OUT/new
  A=(--n3d 20 --local-inputs --delays $S10/ablation/delays_ablation.json 2d10_w100 3d20_stackroute
     --widths $N/abl_route/split/results.csv)
  new $O/abl_route/split softmax 10 "${A[@]}" &
  new $O/abl_ideal/split softmax "3 5" "${A[@]}" "${IDEAL[@]}" &
  wait
  exit
fi
if [ -n "$K272" ]; then
  one $OUT/k272_route/split 3d20own_w100_k272 $W272 spmv 5 --layer-pass &
  one $OUT/k272_route_b/split 3d20own_w100_k272 $W272 attention_layer 8 --layer-pass &
  wait
  exit
fi
one $OUT/k100_route/split 3d20own_w100 $W100 eltwise_layer 6 --layer-pass &
one $OUT/k162_route/split 3d20own_w100_k162 $W162 robot_rl 2 --layer-pass &
one $OUT/k162pin_route/split 3d20own_w100_k162pin $W162P conv_layer 8 --layer-pass &
one $OUT/k162pin_route_b/split 3d20own_w100_k162pin $W162P robot_rl 9 --layer-pass &
one $OUT/control_k162_ideal/split 3d20own_w100_k162 $W162 eltwise_layer 10 --layer-pass \
  --layer-pass-args=--control "${IDEAL[@]}" &
one $OUT/off_k162_ideal/split 3d20own_w100_k162 $W162 eltwise_layer 7 "${IDEAL[@]}" &
wait
