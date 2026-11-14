#!/bin/bash
# Big sparse layer-local CLBs (compare_2d_3d.py --sparse, --span): each LUT input reaches half
# of its crossbar's sources, as in VTR's 7 nm COFFE architecture, so the crossbar stops growing
# with the square of the CLB size. 2D baselines get the same sparse crossbar and sizes. Sizes,
# wire spans and crossbar delays from cluster_size_model.general(). Custom switch blocks with
# vertical links, delta placement delay model, crossings 45 ps (63 ps per layer inside a CLB),
# 3 seeds. Rebuilds the server's VPR first (vpr-multilayer-check.patch). Run in tmux.
B=~/3d-clb/lazagna-bundle
V=~/3d-clb/LaZagna/OpenFPGA/build/vtr-verilog-to-routing/vpr/vpr
MCNC=~/3d-clb/LaZagna/OpenFPGA/vtr-verilog-to-routing/vtr_flow/benchmarks/blif/6
OUT=/tmp/$USER/sparse
mkdir -p $OUT
(cd ~/3d-clb/LaZagna/OpenFPGA/build && nice -n 10 make vpr -j8 > $OUT/vprbuild.log 2>&1) || { echo "STOP: VPR build failed"; exit 1; }
cd $B
COMMON=(--vpr $V "--vpr-args=--max_router_iterations 300 --place_delay_model delta" --timeout 21600 --jobs ${JOBS:-12}
        --slim --scales 1.0 --crossings 45 --clb-crossing 63 --seeds 1 2 3 --switchblocks custom --vertical dense)
LOCAL=(--local-inputs)
for set in small big; do
  if [ $set = big ]; then SET=(--bench-dir /tmp/$USER/ceil/bench --benches stereovision2 bgm stereovision1 stereovision0 blob_merge diffeq2 sha)
  else SET=(--bench-dir $MCNC); fi
  run() { name=$1; shift; nice -n 10 python3 compare_2d_3d.py "${COMMON[@]}" "${SET[@]}" --output $OUT/$set "$@" \
          > $OUT/${set}_$name.log 2>&1; cp $OUT/$set/results.csv $OUT/${set}_$name.csv; }
  # 2D 10 full + 20-LUT split, full crossbar (the reference pair)
  run ref   "${LOCAL[@]}" --n3d 20 --w3d 100 --wire-spans 4 15 --crossbar-scale 1.043 1.023
  # 2D 12 full + 20-LUT split, sparse
  run s20   "${LOCAL[@]}" --n3d 20 --w3d 100 --wire-spans 4 16 --crossbar-scale 0.911 0.893 --sparse 0.5 \
            --n2d 12 --w2d 110 --wire-spans-2d 4 14 --crossbar-scale-2d 1.044 1.073
  # 2D 12 sparse + 30-LUT split over 2 layers, sparse
  run s30   "${LOCAL[@]}" --n3d 30 --w3d 110 --wire-spans 3 13 --crossbar-scale 1.054 1.084 --sparse 0.5 \
            --n2d 12 --w2d 110 --wire-spans-2d 4 16 --crossbar-scale-2d 0.912 0.936 --sparse-2d 0.5
  # 2D 16 sparse + 40-LUT CLB over 4 layers (10 per layer), sparse
  run s40x4 "${LOCAL[@]}" --n3d 40 --span 4 --layers 4 --w3d 100 --wire-spans 4 16 --crossbar-scale 0.972 0.950 --sparse 0.5 \
            --n2d 16 --w2d 126 --wire-spans-2d 3 13 --crossbar-scale-2d 1.027 1.088 --sparse-2d 0.5
  # 2D 20 sparse + 60-LUT CLB over 4 layers (15 per layer), sparse
  run s60x4 "${LOCAL[@]}" --n3d 60 --span 4 --layers 4 --w3d 110 --wire-spans 3 13 --crossbar-scale 1.125 1.156 --sparse 0.5 \
            --n2d 20 --w2d 140 --wire-spans-2d 3 12 --crossbar-scale-2d 1.141 1.236 --sparse-2d 0.5
done
echo SPARSE_DONE
