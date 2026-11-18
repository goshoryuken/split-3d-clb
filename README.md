# Split 3D CLB: one FPGA logic block across two layers

**Ryu Tran** · Georgia Tech (SHARC Lab)

Published 3D FPGA architectures keep each logic block (CLB) whole and stack whole blocks on top of each other.
This project splits **one** CLB across two bonded layers: a 20-LUT CLB with 10 LUTs and a small
crossbar on each layer, and signals that cross between the layers *inside* the CLB. To make that
possible, I extended **VTR/VPR**, **OpenFPGA** and **LaZagna** so that a CLB can span layers, with
each LUT and each pin on a chosen layer, then measured it against LaZagna's stacked 3D CLBs and a
2D FPGA.

**Why it helps.** A 20-LUT CLB is no faster than a 10-LUT one in 2D, because its crossbar grows
with the square of its size. Split 10 + 10, each layer's crossbar stays small, and the bigger
cluster means fewer trips between CLBs on the slowest paths. A short pass after packing then puts
the LUTs on each slow path on the same layer, so those paths cross between layers less often.

## Highlights

- **3.3–6.4% lower critical-path delay than LaZagna's stacked 3D CLBs** on 10 Koios
  deep-learning designs with RAM and DSP blocks (10 seeds each, sky130 delays, ideal clocks;
  3.5–5.5% routed). The range runs from the SPICE layer-crossing delay (339 ps) to the harshest
  reading of the layout (549 ps plus that layout's slower input-pin paths). Without the layer pass
  the split is 1.3–4.9% faster (1.8–4.2% routed). At the SPICE crossing delay it is 6.8% faster
  than a 2D FPGA (5.3% without the pass).
- **Layer-aware packing.** VPR's packer chooses which LUTs share a CLB, but not which layer each
  one sits on. A short pass after packing moves LUTs between the CLB's two layers so that the most
  timing-critical connections stay on one layer. Each layer keeps its 10 LUTs and 40 input pins, so
  the hardware is unchanged. At 549 ps it cuts the layer crossings on the critical path from 3.3
  to 1.8 (routed clocks, 7 designs; stacked: 0.6). A control that reshuffles LUTs without changing
  any LUT's layer gives no gain.
- **The gain comes from the CLB.** On identical 3D routing, the split CLB alone is 3.4% faster than
  stacked (2.6% with routed clocks); 3D routing alone (2D to stacked) gives 0.4% (1.4% routed).
- **Not from extra routing.** The split fabric is routed with more tracks than stacked, but giving
  stacked the same tracks doesn't speed it up (0.996x ideal, 0.998x routed), and at equal tracks the
  split is still 4.5% faster (ideal clocks, 9/10 designs; 4.0% routed), 6.0% with the layer pass
  (5.4% routed).
- **Holds at realistic crossing delays.** The first layouts put the in-CLB crossing at 504–760 ps
  versus 339 ps in SPICE. Stage by stage, most of that came from laying out each layer alone with
  no timing at the bond pads, so the tools never treated a crossing as critical; with timing
  budgets on the pads the layout gives 549 ps. With the layer pass the split stays faster than
  stacked up to 3.0x the SPICE crossing delay, the slowest tested, though there it is close to a
  tie (0.986 ideal, 0.993 routed). At LaZagna's default crossing ratio (2.72x) it is 0.966 / 0.979.
  Without the pass, the edge disappears between 2.2x and 2.7x.
- **Real hardware:** the split CLB's generated Verilog is laid out in sky130 with 0 DRC errors and
  passes gate-level equivalence against the original CLB.
- **VTR support for CLBs that span layers** (`layer_span`, `instance_layer_offsets`, `pin_layer`,
  `layer_crossing_delay`), with crossings inside the CLB charged in timing, and OpenFPGA/LaZagna
  generating one Verilog module per layer.

## Results

<p align="center"><img src="docs/cpd_reduction_vs_2d.png" width="820" alt="Critical-path delay reduction vs. a 2D FPGA per Koios design for stacked CLBs, the split CLB on stacked's routing, and the split CLB; geomean 0.7%, 5.6% and 7.0%."></p>

The chart (7 designs, no layer pass) averages each design's 10 runs with a geometric mean (split
CLB 7.0%); the tables below use the plain average of each design's runs.

Every number below comes from a results file named next to it. Ratios are critical-path delay
(CPD) of one fabric over another, geometric mean over designs; **lower is faster**. "Ideal clocks"
assumes no clock skew; "routed clocks" also sends the clock over the general routing.

Koios runs: 10 designs, 10 seeds each, RAM/DSP in per-layer columns. The study began with 7
designs. 3 more (reduction_layer, softmax, tpu_like.small.ws) were added later under a rule
written down before any of them ran: every remaining Koios design whose first run finishes within
30 minutes and 4 GB joins, and all of them are reported
([newdesigns_rule.txt](prototype/lazagna/hardblocks/results/seeds10/layerpass/newdesigns_rule.txt)).
The other 5 Koios designs are larger (the two smallest of them, lstm and dla_like.small, peak at
7.2–7.3 GiB). The split's edge is smaller on the 3 added designs (see the breakdown below). A run
that hits VPR's default 50 router iterations is rerun with 200; runs that had already converged
give identical results at 200, and a run that still fails drops only that seed. Rows marked
"7 designs" have not been rerun with the added 3.

### Split CLB vs LaZagna's stacked CLBs (10 designs, 339 ps SPICE crossing)

| Comparison | Ideal clocks | Routed clocks | Without conv_layer (ideal / routed) |
|---|---|---|---|
| Split over stacked, no pass | 0.951, faster on 9/10 | 0.958, 7/10 | 0.964 / 0.976 |
| Split over stacked, layer pass | **0.936**, 10/10 | **0.945**, 8/10 | 0.948 / 0.961 |
| Ablation: same routing as stacked, only the CLB changes (no pass) | 0.966, 8/10 | 0.974, 7/10 | 0.981 / 0.989 |
| Equal tracks: stacked given the split's track count, no pass | 0.955, 9/10 | 0.960, 6/10 | 0.969 / 0.976 |
| Equal tracks, layer pass | 0.940, 10/10 | 0.946, 9/10 | 0.952 / 0.961 |

The first 7 designs and the 3 added ones, separately (split over stacked):

| Setting | No pass, ideal | Layer pass, ideal | No pass, routed | Layer pass, routed |
|---|---|---|---|---|
| 339 ps (SPICE), all 10 designs | 0.951 | 0.936 | 0.958 | 0.945 |
| 339 ps (SPICE), first 7 | 0.936 | 0.924 | 0.944 | 0.939 |
| 339 ps (SPICE), added 3 | 0.987 | 0.963 | 0.994 | 0.958 |
| 549 ps + slower pin paths, all 10 | 0.987 | 0.967 | 0.982 | 0.965 |
| 549 ps + slower pin paths, first 7 | 0.982 | 0.952 | 0.970 | 0.954 |
| 549 ps + slower pin paths, added 3 | 0.998 | 1.003 | 1.011 | 0.991 |
| 3.0x, all 10 | 1.018 | 0.986 | 1.027 | 0.993 |
| 3.0x, first 7 | 1.018 | 0.980 | 1.017 | 0.979 |
| 3.0x, added 3 | 1.017 | 0.999 | 1.052 | 1.026 |

In the ablation the added 3 get nothing from the CLB alone (1.004 ideal, 0.991 routed; first 7:
0.950 / 0.967). File:
[layerpass_results.txt](prototype/lazagna/hardblocks/results/seeds10/layerpass/layerpass_results.txt),
section E; `tendesigns_table.py --fill` in the same folder prints every 10-design table. The 7-design
tables are [ideal_table.txt](prototype/lazagna/hardblocks/results/seeds10/ideal_table.txt),
[route_table.txt](prototype/lazagna/hardblocks/results/seeds10/route_table.txt),
[ablation_table.txt](prototype/lazagna/hardblocks/results/seeds10/ablation/ablation_table.txt) and
[equal_tracks_table.txt](prototype/lazagna/hardblocks/results/seeds10/equal_tracks/equal_tracks_table.txt).

### Layer-crossing delay (10 designs)

Split over stacked with every layer crossing (inside the CLB and in the routing, in both fabrics)
scaled together. The layouts are compared with SPICE stage by stage in
[crossing_stages_results.txt](prototype/lazagna/pnr/crossing_stages_results.txt).

| In-CLB crossing | No pass, ideal | No pass, routed | Layer pass, ideal | Layer pass, routed |
|---|---|---|---|---|
| 339 ps, SPICE (1.0x) | 0.951, 9/10 | 0.958, 7/10 | 0.936, 10/10 | 0.945, 8/10 |
| 549 ps, layout with timing budgets (1.62x) | 0.972, 7/10 | 0.965, 8/10 | 0.954, 7/10 | 0.945, 8/10 |
| 549 ps, plus that layout's slower input-pin paths | 0.987, 7/10 | 0.982, 6/10 | 0.967, 7/10 | 0.965, 6/10 |
| 760 ps, first layout (2.24x) | 0.991, 5/10 | 0.984, 6/10 | 0.963, 7/10 | 0.962, 8/10 |
| LaZagna's default crossing ratio (2.72x) | 1.016, 3/10 | 1.009, 5/10 | 0.966, 7/10 | 0.979, 6/10 |
| 3.0x | 1.018, 3/10 | 1.027, 3/10 | 0.986, 6/10 | 0.993, 5/10 |

Without conv_layer, the layer pass at 3.0x gives 1.000 / 1.006. The control (7 designs: the same
rewrite, but no LUT changes layer) gives 1.006 / 1.000 of the no-pass split at 1.62x and
0.997 / 0.999 at 2.72x, so the gain comes from the layer choices.
Files: [crossings_table.txt](prototype/lazagna/hardblocks/results/seeds10/crossings/crossings_table.txt) (7 designs, also 1.36x to 2.0x),
[layerpass_results.txt](prototype/lazagna/hardblocks/results/seeds10/layerpass/layerpass_results.txt) (sections A, B, C and E).

### Against a 2D FPGA (10 designs; 10-LUT CLBs, the fastest 2D size with these delays)

| Fabric over 2D | Ideal clocks | Routed clocks |
|---|---|---|
| Stacked CLBs (3D routing only) | 0.996, 6/10 | 0.986, 6/10 |
| Split CLB, no pass | 0.947, 8/10 | 0.944, 8/10 |
| Split CLB, layer pass | **0.932**, 8/10 | **0.931**, 9/10 |

Minimum tracks per layer over 2D (7 designs): stacked 0.789, split 1.042. Both 3D fabrics use 0.509
of the 2D footprint and 1.018 of its die area (grid cells times layers; 7 designs).
Files: [layerpass_results.txt](prototype/lazagna/hardblocks/results/seeds10/layerpass/layerpass_results.txt) (section E),
[ideal_table.txt](prototype/lazagna/hardblocks/results/seeds10/ideal_table.txt), [route_table.txt](prototype/lazagna/hardblocks/results/seeds10/route_table.txt) (7 designs).

### Other benchmarks (split over stacked, 10 seeds)

| Benchmarks | sky130 | 7 nm (ASAP7) |
|---|---|---|
| 7 bigger VTR designs | 0.971, 4/7 | 0.963, 6/7 |
| 16 small MCNC designs | 1.008 | 0.999 |

File: [SPICE_RESULTS.md](prototype/lazagna/spice/SPICE_RESULTS.md). Small designs gain nothing.

### Layout

- Area as laid out (own-layer pins, 66 tracks): 1.036 of 2D's silicon per LUT and 0.518 of its
  footprint per LUT ([tile_results_relaxed_tracks.txt](prototype/lazagna/pnr/tile_results_relaxed_tracks.txt)).
- Gate-level equivalence: random inputs compared with the original CLB every cycle, and cutting a
  used layer crossing makes it fail ([direct_crossing_results.txt](prototype/lazagna/pnr/direct_crossing_results.txt), [ff_test/](prototype/lazagna/ff_test)).
- The layer pass's rewritten packing goes through OpenFPGA, and the configured fabric matches a
  reference model in simulation. A fault planted in a moved LUT is caught. This was checked on one
  20-LUT test design and covers function, not timing
  ([hwcheck/](prototype/lazagna/hardblocks/results/seeds10/layerpass/hwcheck)).

## What I built

### Architecture file

```xml
<tile name="clb" layer_span="2">                            <!-- the CLB occupies 2 layers -->
<loc side="left" pin_layer="1">...</loc>                    <!-- pins on the upper layer -->
<loc side="left" pin_layer="0" layer_offset="1">...</loc>   <!-- pins that also reach the layer above -->
<pb_type name="fle" num_pb="20"
         instance_layer_offsets="0 0 0 0 0 0 0 0 0 0 1 1 1 1 1 1 1 1 1 1">  <!-- layer of each LUT -->
<complete name="crossbar0" input="clb.I0 fle[19:0].out" output="fle[9:0].in"
          layer_crossing_delay="339.23e-12">                <!-- delay per layer crossed -->
<direct ... layer_offset="1" placement_macro="false"/>      <!-- a direct link to another layer -->
```

Each change stays in the section of the architecture file whose job it is:

| Section | What it describes | What changed |
|---|---|---|
| `<layout>` | where each block sits on the grid | nothing new: the cell above a spanning CLB is left `EMPTY`, and VPR reserves it |
| `<models>` | the primitives' interfaces (for packing) | nothing: LUTs, flip-flops, RAM and DSP are unchanged |
| `<tiles>` | each block's size and pins (for routing) | `layer_span` (next to the existing `width`/`height`), `pin_layer` on `<loc>` |
| `<complexblocklist>` | what is inside a block and its timing | `instance_layer_offsets`, `layer_crossing_delay`, one crossbar per layer |
| `<directlist>` | fixed links between blocks | `layer_offset`, `placement_macro` |
| `<device>`, `<segmentlist>`, `<switchlist>` | routing and its timing | no new attributes |

Offsets are relative to the parent block, so a block keeps its internal layout wherever it is
reused. VPR never stores absolute layers in the shared CLB graph; it adds the placed CLB's anchor
layer when needed.

### Tools

Full list with every function: [TECHNICAL_MAP.md](prototype/lazagna/TECHNICAL_MAP.md), section 1.

- **VTR/VPR** (this repository, on top of VTR `5abd3acaa`, the version LaZagna pins): new
  [`pb_type_layers.cpp`](libs/libarchfpga/src/pb_type_layers.cpp) (each LUT's layer, span checks,
  crossing delays) and [`layer_report.cpp`](vpr/src/base/layer_report.cpp) (per-layer report after
  routing), two new test files, and changes across architecture reading, the device grid,
  placement, the routing graph (each pin on its own layer), the router lookahead and the placement
  delay model. Also available as patches in [`prototype/lazagna/`](prototype/lazagna).
- **OpenFPGA** ([openfpga-lazagna.patch](prototype/lazagna/openfpga-lazagna.patch), 21 files):
  labels every LUT, crossbar mux, configuration bit and wire with its layer in the generated Verilog.
- **LaZagna** ([lazagna-3d-clb-branch.patch](prototype/lazagna/lazagna-3d-clb-branch.patch)): a
  `clb_3d: split_layers: true` setup option, and `split_clb_layers.py`, which cuts each CLB's
  Verilog into one module per layer.
- **Experiment flow** ([prototype/lazagna/](prototype/lazagna)): `compare_2d_3d.py` (builds each
  fabric's architecture, runs VPR per design and seed), `compare_configs.py` (ratios),
  `spice/make_spice.py` (transistor-level delays in Spectre, sky130 and ASAP7), `pnr/` (layout and
  timing), `ff_test/` (hardware equivalence checks), `hardblocks.py` (RAM/DSP placement study).
- **Layer pass** ([`layer_pass.py`](prototype/lazagna/layer_pass.py), VPR option
  `--pack_criticality_file`): after packing, moves LUTs between a split CLB's two layers to cut
  timing-weighted layer crossings, keeping each layer's 10 LUTs and 40 input pins. Its weights are
  the packer's own timing estimates, from before placement. It is off by default
  (`compare_2d_3d.py --layer-pass`).

## How the numbers are made

1. **SPICE.** `spice/make_spice.py` builds transistor-level copies of OpenFPGA's circuits (muxes,
   LUT, buffers, RC wires, and the layer crossing: driver, bond, receiver) for each fabric and
   times them in Spectre. Output: one delay per part.
2. **Architecture and VPR.** `compare_2d_3d.py` writes those delays into each fabric's
   architecture file, picks the smallest square grid that fits the design (LUTs at 70%, RAM/DSP
   at 80%, the same rule for every fabric), finds the minimum tracks, then routes at 1.3x that.
3. **Results.** VPR reports each run's critical path; `compare_configs.py` turns the CSVs into
   ratios.

Recompute the headline from the committed CSVs:

```bash
cd prototype/lazagna
S=hardblocks/results/seeds10
python3 compare_configs.py $S/ideal/stack/results_columns.csv:3d split=$S/ideal/split/results_columns.csv:3d
python3 compare_configs.py $S/ideal/stack/results_columns.csv:3d ablation=$S/ablation/strict_ideal/results_columns.csv:3d
python3 $S/layerpass/tendesigns_table.py --fill   # every 10-design table, with and without the pass
```

## Build

Tested from a fresh clone on macOS (Apple Silicon, Homebrew `cmake bison flex openssl@3 python`):

```bash
git clone https://github.com/goshoryuken/split-3d-clb.git
cd split-3d-clb
git submodule update --init libs/EXTERNAL/libcatch2
cmake -S prototype -B build/vpr -DCMAKE_BUILD_TYPE=Release -DPROTOTYPE_BUILD_VPR=ON \
      -DOPENSSL_ROOT_DIR=/opt/homebrew/opt/openssl@3 \
      -DBISON_EXECUTABLE=/opt/homebrew/opt/bison/bin/bison \
      -DFLEX_EXECUTABLE=/opt/homebrew/opt/flex/bin/flex \
      -DCMAKE_POLICY_VERSION_MINIMUM=3.5
make -C build/vpr -j6 vpr
```

On macOS the Homebrew bison and flex are needed (the system bison is too old). On Linux, drop the four Homebrew paths. The experiment scripts need only Python 3 (standard library).

## Reproduce

After the build, from the repository root:

```bash
QUICK=1 prototype/lazagna/reproduce_koios.sh out-quick   # spmv, seed 1: a few minutes
prototype/lazagna/reproduce_koios.sh out                 # all 7 designs x 10 seeds
ABLATION=1 prototype/lazagna/reproduce_koios.sh out      # also the split CLB on stacked's routing
```

The script runs 2D, stacked and split fabrics with routed clocks, then ideal clocks at the same
track counts, and prints the same ratios as
[ideal_table.txt](prototype/lazagna/hardblocks/results/seeds10/ideal_table.txt). `JOBS` sets the
parallel VPR runs per 3D fabric (default 4); each run needs about 1.5 GB of memory, and the full
sweep (about 420 VPR runs) took about 1 h 20 min with 12 runs at a time on an Apple Silicon Mac.

- **Layer pass:** the scripts in
  [`hardblocks/results/seeds10/layerpass/`](prototype/lazagna/hardblocks/results/seeds10/layerpass)
  rerun it: `run_layerpass.sh` (the 7 designs), `run_newdesigns.sh` and `run_newdesigns_e.sh` (the
  3 added designs, every fabric), `run_failed.sh` (failed runs at 200 router iterations). Each
  script's header says what it runs.
- **Netlists:** the 10 Koios designs are in
  [`hardblocks/koios/`](prototype/lazagna/hardblocks/koios), synthesized from VTR's Koios Verilog
  with [`synth_koios.sh`](prototype/lazagna/hardblocks/synth_koios.sh) (regenerating them needs
  Yosys).
- **Delays:** the SPICE delay sets are committed
  ([`spice/delays_tt_all.json`](prototype/lazagna/spice/delays_tt_all.json)), so reruns need no
  SPICE. Re-deriving them needs Cadence Spectre and the sky130 PDK; the layout needs Innovus and a
  sky130 RTL-to-GDS flow. Neither is included.
- **Records:** the `run_*.sh` scripts next to each result record how it was made (with the folders
  they ran in).

## Limitations

- **The gain depends on the design.** On the 3 later-added designs the split without the pass is
  only 1.3% faster than stacked (0.6% routed), against 6.4% (5.6%) on the first 7, and its edge on
  them disappears between 1.62x and 2.24x the SPICE crossing delay. On stacked's exact routing the
  split CLB alone gives them nothing. The layer pass brings them to 3.7% (4.2% routed) at the SPICE
  delay, but from 549 ps with the slower pin paths up it leaves them within 1% of stacked, and 2.6%
  slower at 3.0x with routed clocks. In the ablation (all 10), conv_layer is 16% faster than
  stacked and two designs (three with routed clocks) are slightly slower; without conv_layer the
  CLB-only gain is 1.9% (ideal clocks) and 1.1% (routed). Small designs gain nothing.
- **These are VPR timing results** with delays from SPICE models of OpenFPGA's circuits, not
  measurements of a fabricated chip. RAM and DSP delays are estimated.
- **The edge depends on the layer-crossing delay.** At 549 ps the split's critical path still
  crosses layers 1.8 times with the layer pass (3.3 without) versus 0.6 for stacked (routed
  clocks, 7 designs). At the harshest reading of the layout, the split is 3.3% faster than stacked
  with the pass and 1.3% without (ideal clocks). Without conv_layer that is 1.8% with the pass and
  a tie without it (1.000). At 3.0x, the slowest tested, the pass leaves it 1.4% faster (0.7%
  routed), and a tie without conv_layer (1.000 / 1.006).
- **Packing is still mostly layer-blind.** The layer pass only moves LUTs between the two layers of
  a CLB: which LUTs share a CLB is still chosen without regard to layers, and the pass ignores
  RAM/DSP and IO connections. On the first 7, netlists rewritten by the pass hit VPR's 50 router
  iterations more often (5 of 560 runs, against 1 of 420 without it); all of them route with 200.
  On the added 3, a run with the pass failed only where the same run without it failed too.
- With RAM/DSP, the split fabric needs 4.2% more tracks per layer than 2D and 32% more than
  stacked (7 designs). That is an area cost; it is not where the speed comes from (equal-track
  rerun above).
- A 40-LUT CLB over 4 layers loses; this works for 2 layers.

## Repository layout

| Path | Contents |
|---|---|
| [`prototype/lazagna/`](prototype/lazagna) | Experiment scripts, patches, results and technical docs |
| [`prototype/lazagna/hardblocks/results/seeds10/`](prototype/lazagna/hardblocks/results/seeds10) | Koios results: headline, ablation, layout crossing, bond pitch, layer pass |
| [`prototype/lazagna/spice/`](prototype/lazagna/spice) | SPICE generator, delay sets and SPICE results |
| [`prototype/lazagna/pnr/`](prototype/lazagna/pnr) | Layout flow scripts and layout results |
| [`prototype/lazagna/ff_test/`](prototype/lazagna/ff_test) | Hardware equivalence checks |
| `prototype/` (other files) | The first prototype (below) |
| `libs/`, `vpr/` | VTR with the multi-layer CLB changes |
| [`VTR_README.md`](VTR_README.md) | VTR's own README |

Further reading: [TECHNICAL_MAP.md](prototype/lazagna/TECHNICAL_MAP.md) (every code change and
which file backs each number), [HARDBLOCKS.md](prototype/lazagna/HARDBLOCKS.md) (the Koios study
with RAM/DSP), [SPICE_RESULTS.md](prototype/lazagna/spice/SPICE_RESULTS.md),
[LITERATURE.md](prototype/lazagna/LITERATURE.md) (related work).

## First prototype

The idea was first built on a 3D VTR fork: one 10-LUT CLB with 5 LUTs on each layer, packed,
placed, routed and timed by VPR, with OpenFPGA tagging each LUT's layer in the generated Verilog
and the configured fabric checked in simulation. Its files are in `prototype/`:
`physical_split_fle.xml` and `openfpga_split_fle.xml` (architectures), the `ten_luts*` and
`asymmetric_ten_luts*` test circuits, and `test_physical_layers.py` (24-case VPR suite),
`test_mapped_rtl.py` and `run_openfpga_demo.py` (post-route and configured-fabric simulation).

## Built on

[VTR](https://github.com/verilog-to-routing/vtr-verilog-to-routing),
[OpenFPGA](https://github.com/lnis-uofu/OpenFPGA) and
[LaZagna](https://github.com/sharc-lab/LaZagna) (Youssef, Yang and Hao, ICCAD 2025); benchmarks
from Koios, VTR and MCNC; the SkyWater sky130 and ASAP7 process kits. Their licenses and
generated-file headers are kept; VTR's license is in [LICENSE.md](LICENSE.md).
