# Where should hard blocks go in a split-CLB 3D FPGA? (2026-11-09)

Pilot study: 5 Koios designs and 4 placement seeds, with sky130 SPICE delays for the CLBs and
routing. Hard-block delays are estimated (see "What is estimated"). Every number below comes from
the files in `hardblocks/results/`:
- `route_table.txt` and `ideal_table.txt` (hb_table.py);
- `route_paths.txt` and `ideal_paths.txt` (hb_paths.py);
- `compare_configs_check.txt` (compare_configs.py, which gives the same ratios);
- `widths.csv`.

## Answer

**In the split-CLB fabric, put the hard blocks in per-layer columns: LaZagna's homogeneous
layers, RAM over RAM and DSP over DSP. Let the hard blocks' input pins read both layers' tracks.**

Against the 10-LUT 2D fabric with the same hard blocks per LUT (geometric mean over 5 designs,
4 seeds each):

| Split, `columns` | CPD | Designs faster | Footprint (grid cells) | Minimum tracks per layer |
|---|---:|---:|---:|---:|
| Ideal clocks | 0.925 | 4/5 | 0.511 | |
| Routed clocks | 0.900 | 5/5 | 0.511 | 1.054 |

Against LaZagna-style stacked CLBs with the same placement, the CPD ratio is 0.922 with ideal clocks
(5/5 designs) and 0.933 with routed clocks (4/5).

**RAM-under-DSP (`stacked`) ties it.** Against `columns` it is 0.994 with ideal clocks and 1.000
with routed clocks, with the same footprint and tracks. It needs the VPR fix described below, and
one of its 20 routed-clock runs did not route at 1.3x its minimum width.

**A third, hard-block layer (`layer`)** gives the split fabric:
- the best ideal-clock CPD: 0.904 of 2D, and 0.978 of `columns` with 3/5 designs faster;
- the smallest footprint: 0.373 of 2D.

But it ties `columns` with routed clocks (1.001). It needs 1.351 of the 2D tracks per layer and a
third die. For stacked CLBs, the hard-block layer is the clear winner: 0.950 of `columns` with ideal
clocks, 5/5 designs faster.

**Hard blocks split across both layers (`span`, the "split everything" idea) are worst or tied
worst in both fabrics.** Against `columns` they are 0.999 / 1.028 for split CLBs and 1.002 / 1.030
for stacked CLBs (ideal / routed clocks), with 1.21 times the footprint.

The differences between placements are small, 0 to 5%, next to the split CLB's own gain of 7 to 8%
over stacked CLBs. Per-seed ratios between placements vary by up to about 5% either way
(compare_configs_check.txt). Treat the
`columns` vs `stacked` vs `layer` ranking in the split fabric as a tie on speed, decided by tracks
and dies.

## Results

Relaxed routing at 1.3 times each run's minimum width (VTR's method). Geometric means over the 5
designs; a design counts only if it routed on all 4 seeds (1, 2, 3, 4).

- **Ideal clocks:** each routed-clock run re-placed and re-routed at the same width with
  `--clock_modeling ideal`, so the CPD has no clock skew.
- **Routed clocks:** clocks on general routing, as in every earlier sweep. Path 1 then carries 0.7
  to 1.7 ns of skew, and it differs by fabric (2D 1.36 ns mean, stacked CLBs 0.72 to 1.00,
  route_paths.txt). That biases ratios, so the ideal-clock column is the cleaner one.

### Against the 10-LUT 2D fabric

| Fabric / placement | CPD, ideal | CPD, routed | Wirelength, ideal | Min. tracks per layer | Tracks per footprint cell | Footprint | Die cells |
|---|---:|---:|---:|---:|---:|---:|---:|
| split / columns | 0.925 (4/5) | 0.900 (5/5) | 0.895 | 1.054 | 2.107 | 0.511 | 1.023 |
| split / stacked | 0.919 (3/5) | 0.915 (3/4)* | 0.895 | 1.045 | 2.090 | 0.500 | 1.000 |
| split / span | 0.943 (3/4)* | 0.926 (4/5) | 0.951 | 0.942 | 1.884 | 0.618 | 1.237 |
| split / layer | 0.904 (4/5) | 0.902 (4/5) | 0.786 | 1.351 | 4.054 | 0.373 | 1.118 |
| stacked / columns | 1.002 (3/5) | 0.965 (4/5) | 0.843 | 0.781 | 1.563 | 0.511 | 1.023 |
| stacked / stacked | 0.998 (2/5) | 0.971 (4/5) | 0.839 | 0.775 | 1.549 | 0.500 | 1.000 |
| stacked / span | 1.005 (2/5) | 0.995 (4/5) | 0.874 | 0.660 | 1.319 | 0.618 | 1.237 |
| stacked / layer | 0.952 (3/5) | 0.930 (5/5) | 0.804 | 0.755 | 2.265 | 0.373 | 1.118 |

How to read the table:
- CPD and wirelength are 3D over 2D; "(n/m)" is the number of designs faster than 2D.
- Minimum tracks come from the routed-clock width search. 2D has one layer.
- Tracks per footprint cell multiply the minimum tracks by the layers, the hard-block layer included.
- Footprint is (grid - 2)^2 in grid cells, and die cells are footprint times layers, both relative
  to 2D. Tile sizes differ by fabric; see "What is estimated".
- \* A design that failed at 1.3x its minimum width on some seed drops out of that row's mean:
  - split / stacked, routed clocks: tpu_like.small.os seed 2. One node stayed overused at the chip
    edge next to I/O, also with 300 router iterations.
  - split / span, ideal clocks: tpu_like.small.os seeds 2 and 4, also with 300 iterations.

### Between placements, and split against stacked CLBs

| | Ideal clocks | Routed clocks |
|---|---:|---:|
| split: stacked / columns | 0.994 (4/5) | 1.000 (2/4) |
| split: span / columns | 0.999 (2/4) | 1.028 (0/5) |
| split: layer / columns | 0.978 (3/5) | 1.001 (3/5) |
| stacked CLBs: stacked / columns | 0.996 (3/5) | 1.006 (3/5) |
| stacked CLBs: span / columns | 1.002 (3/5) | 1.030 (1/5) |
| stacked CLBs: layer / columns | 0.950 (5/5) | 0.964 (3/5) |
| split / stacked CLBs, columns | 0.922 (5/5) | 0.933 (4/5) |
| split / stacked CLBs, stacked | 0.921 (4/5) | 0.927 (3/4) |
| split / stacked CLBs, span | 0.925 (3/4) | 0.931 (4/5) |
| split / stacked CLBs, layer | 0.950 (3/5) | 0.969 (2/5) |

### Hard-block inputs on their own layer ("own") or both ("both"), split fabric

These are the first own-layer runs that finished: `columns` for attention_layer, eltwise_layer and
spmv, seeds 1 and 2 (hardblocks/results/own_inputs, widths.csv).

CPD is unchanged: both over own is 1.003 (compare_configs.py). The minimum tracks per layer, own
against both:

| Design | Seed 1 | Seed 2 |
|---|---|---|
| attention_layer | 120 against 104 | 116 against 102 |
| spmv | 116 against 94 | 120 against 94 |
| eltwise_layer | 130 against 136 | 144 against 148 |

For comparison, 2D needs 110 and 108 (attention_layer), 86 and 86 (spmv), and 124 and 122
(eltwise_layer).

So own-layer hard-block inputs cost tracks on the RAM-heavy designs: spmv (232 RAMs) and
attention_layer (194). That is
why "both" is the main split result.

### Per design (ideal clocks, mean CPD in ns over 4 seeds; ideal_table.txt)

- **tpu_like.small.os (280 DSP blocks):** the hard-block layer is fastest. 2D 21.16, split
  columns 18.00, split layer 17.40, stacked layer 17.31.
- **conv_layer:** split is 15 to 18% faster than 2D (23.92) at every placement (19.60 for layer
  to 20.46 for span).
- **attention_layer (194 RAMs):** 2D is fastest (22.07), against 22.43 to 22.61 for split and
  23.10 to 23.27 for stacked CLBs.
- **eltwise_layer:** every 3D configuration is within 4% of 2D (14.32).
- **spmv (232 RAMs):** split is 9 to 10% faster than 2D (16.38) at stacked, span and layer
  (14.69 to 14.94). Stacked CLBs are within 4% of 2D either way.

## Why the winner wins

What a placement changes is mostly the logic, not the hard blocks. With ideal clocks, a hard block
is on the critical path in 4 or 5 of the 20 runs of each configuration (18 for split span;
ideal_paths.txt), so 15 or
16 of every 20 critical paths are CLB-to-CLB. A placement therefore acts through:
- how many columns it takes out of the logic grid;
- what it does to routing between layers.

Mean critical-path inter-block hops, ideal clocks (ideal_paths.txt):

| | 2D | columns | stacked | span | layer |
|---|---:|---:|---:|---:|---:|
| split | 18.6 | 13.4 | 14.1 | 13.9 | 12.9 |
| stacked CLBs | | 16.1 | 16.3 | 16.9 | 14.1 |

- **`columns` and `stacked` take the same share of the logic columns** (1 in 4), so they give the
  same grid (footprint 0.511 and 0.500) and similar hops (13.4 and 14.1 split, 16.1 and 16.3
  stacked). RAM sitting directly under DSP buys
  nothing measurable, because few critical paths go RAM to DSP.
- **`span` takes 2 columns in 5:** each hard block uses a cell on both layers, so there are more
  hard columns per LUT. The logic spreads: footprint 1.21 of `columns`, more hops (13.9 against
  13.4 split, 16.9 against 16.1 stacked), and wirelength 1.06 of `columns`. A RAM's port-2 pins also
  pay a 339 ps crossing in and out. Halving each hard tile's pins per layer is its only win:
  - the fewest tracks: 0.942 of 2D for split, 0.660 for stacked CLBs;
  - partly an artifact of LaZagna's pin-dense 1x1 hard tiles.
- **`layer` takes no logic columns**, so it has the smallest grid (0.373) and the fewest hops.
  For stacked CLBs that is 2.0 fewer hops than `columns` and 0.95 of its ideal-clock CPD. For the
  split CLB it saves only 0.5 hops, and it costs:
  - more layer crossings on the critical path (3.5 against 3.0);
  - 1.351 of the 2D tracks per layer against 1.054 for `columns`.

  The reason is the split CLB's own-layer input pins. Every signal between the hard-block layer and
  the logic must use the middle layer's tracks: VPR joins only adjacent layers, at pins. The
  split CLB's lower half reads only those tracks. The middle layer becomes a funnel. Stacked CLBs,
  whose pins read both layers, do not funnel: 0.755 of 2D tracks.
- **The split CLB beats stacked CLBs by about 7 to 8% at every two-layer placement.** That is more
  than its margin over stacked CLBs in the CLB-only SPICE sweeps (spice/SPICE_RESULTS.md), which used routed
  clocks and smaller designs. Its 20-LUT cluster cuts critical-path hops from 16 to about 13.5 (ideal
  clocks). The hard-block placement does not erode this, except `layer`, where the funnel takes
  half of it (0.950).

Wirelength follows footprint: `layer` is shortest (0.786 split, 0.804 stacked, ideal clocks) and
`span` longest. The split fabric's wirelength is 1.06 to 1.08 of stacked CLBs' at the same
two-layer placement (ideal clocks), from more layer changes.

## Candidates

Each 3D fabric has one RAM and one DSP per 60 LUTs, like 2D, and every tile is 1x1. "Hard columns"
counts grid columns that hold no CLB on the logic layers (LAYOUTS in hardblocks.py).

| Placement | Layer 0 | Layer 1 | Hard columns | Notes |
|---|---|---|---|---|
| 2D | DSP at x=2, RAM at x=4, every 8 | - | 2 of 8 | LaZagna's base pattern |
| `columns` | RAM and DSP columns | the same columns again | split 2 of 8; stacked 2 of 8 | LaZagna's homogeneous layers; RAM over RAM, DSP over DSP |
| `stacked` | RAM column | DSP column above it | split 1 of 4; stacked 1 of 4 (RAM column on layer 0, DSP column on layer 1) | RAM feeds DSP vertically |
| `span` | one hard tile over both layers, half its pins on each | | 2 of 5 | one 18x19 multiplier per layer; RAM core on layer 0, port 2 and upper data cross |
| `layer` | a third layer (die 0) of RAM and DSP columns, one third empty | logic only (layers 1-2) | 0 | logic layers have no hard columns |

In the split fabric, a split CLB fills both logic layers' cells. The stacked fabric has a whole CLB
on each layer, and its `span` reserves layer 1 above each spanning hard tile.

**Hard-block input pins, split fabric.** The split CLB's input pins read only their own layer's
tracks (own-layer pins), which was the faster split CLB in the CLB-only sweeps. A hard block's input pins can
follow the same rule ("own") or read both layers ("both"); the second costs a bigger connection
block on the hard blocks only. `both` is the main split result here, because:
- `own` raises the minimum width for RAM-heavy designs (see Results);
- the `own` runs were much slower to route, so only part of them ran.

In the `layer` placement, hard-block inputs reach the middle layer either way.
The stacked fabric's pins all reach both layers, as in LaZagna.

## Prior work: is this question already studied?

Checked on 2026-11-09 against the public arXiv pages (abstract and HTML text) of the three
readable papers in LITERATURE.md. Items marked (summary) come from a summary of the paper, not
its full text.

- **LaZagna** (arXiv 2505.05579) supports DSP and BRAM blocks. Its "homogeneous" layers repeat the
  same columns on every layer, which is our `columns` placement. Its "logic heterogeneous" layers
  allow a different mix per layer. The text gives one example: DSPs only on the top layer. It does
  not compare hard-block placements; its only placement comparison is of 3D switch-block patterns
  (summary).
- **Escaping Flatland** (arXiv 2604.01078) places Koios designs with DSPs and BRAMs. Its partitioner
  assigns each placeable block, hard blocks included, to a layer. It does not compare fabric layouts
  of hard blocks (summary).
- **Poolad et al., multi-die routing** (arXiv 2606.06421): two identical dice. Neither the readable
  text nor the summary describes hard blocks.
- **Boutros et al., FPT 2023**: the PDF could not be read here.

None of these papers splits a CLB across layers. None asks where the hard blocks should go relative
to a split CLB. The questions specific to a split CLB are:
- a hard block can be split across layers as the CLB is (`span`);
- the CLB's own-layer pins decide which layer's tracks a hard block can read.

Comparing hard-block placements in a 3D fabric at all looks new against these four papers. A full
IEEE/ACM search has not been done (LITERATURE.md, "Still to do").

## Method

**Fabrics.** All three use the sky130 SPICE delays for routing, CLB and crossings
(`spice/delays_tt_all.json`, crossings as laid out). The delay sets were simulated at 100 tracks per
layer, and each run here routes at its own relaxed width with those same delays. The fabrics are
those of run_spice_delays.sh (OWN=1) and run_stacked_spice.sh.

- **2D:** 10-LUT CLB, set `2d10_w100`. It is the faster 2D size with these delays (spice/SPICE_RESULTS.md).
- **Split:** 20-LUT CLB, 10 LUTs per layer, with layer-local crossbars and own-layer input pins.
  Set `3d20own_w100`, wire spans 4 and 15.
- **Stacked:** LaZagna-style stacked 10-LUT CLBs, one whole CLB per layer, all pins reaching
  both layers. Set `3d10stack_w100`.

**Hard blocks** (hardblocks.py). The RAM is VTR's 20 Kb block `mem20K`: 512x40, 1024x20 and
2048x10 single port; 1024x20 and 2048x10 dual port. The DSP is LaZagna's `complex_dsp`: one 27x27
multiplier or two 18x19 multipliers. Every hard tile is 1x1, as in LaZagna's base architecture;
VPR's multi-layer tiles must be 1x1 anyway.

Every fabric has one RAM site and one DSP site per 60 LUTs (LaZagna's ratio: 6 CLB columns per RAM
column and per DSP column). `hardblocks.check_ratios()` returns exactly 60 LUTs per RAM site and per
DSP site for all nine layouts. At the actual grid sizes, edge effects move this a little; hb_table.py
prints the values.

**Grid.** Each run gets the smallest square grid that fits its LUTs at 70% and its RAMs and DSPs at
80% (`hardblocks.grid_for`). Every design here is limited by LUTs except spmv, which is limited by
RAMs.

**Benchmarks.** Koios designs synthesized with plain Yosys (hardblocks/synth_koios.sh, not VTR's
parmys). `koios_hb.v` cuts each RAM into 20 Kb blocks. `mulmap.v` maps multipliers of 5 to 27 bits
onto the DSP's multipliers; the DSP's floating-point modes are not modeled. LUT counts therefore
differ from published Koios numbers.

VPR packs every RAM into a `memory` block: in the 2D seed-1 runs, the netlist memory block count
equals the BLIF RAM count (72 for eltwise_layer, 232 for spmv). Spare DSP sites and unrelated
clustering left off mean most multipliers get a DSP block of their own: 84 blocks for conv_layer's
84 multipliers, 280 for tpu_like.small.os's 288.

**VPR.** Clocks are routed (`--clock_modeling route`, as in every earlier sweep), and the
placement delay model is delta for multi-layer devices. Each run first finds its own minimum channel
width, then routes at 1.3 times that width: VTR's relaxed routing, `--relax-w 1.3`, with VPR's
default 50 router iterations.

The fixed 100 tracks per layer used by the CLB-only sweeps does not work here. In a pilot
(eltwise_layer, seed 1), only the spanning placement routed at 100. 2D, per-layer columns and
RAM-under-DSP were still overused after 300 iterations. LaZagna's 1x1 hard tiles put 105 RAM pins and
148 DSP pins on one CLB-sized tile.

Each routed-clock run is then re-placed and re-routed with ideal clocks at the same width
(`--clock-modeling ideal`; the run's arch.xml and width.txt seed the ideal run's folder). Routed
clocks add skew that differs by fabric (Results). Detailed timing reports, which list every routing
node with its layer, feed hb_paths.py.

## What VPR could not express, and what was done

1. **An input pin of a type placed on one layer only could not read another layer's tracks.**
   `rr_graph.cpp` builds each pin's connection-block pattern indexed by the track's layer, but only
   for layers where the type has instances (`get_layers_of_physical_types`). So `layer_offset` on
   inputs silently did nothing for RAM-under-DSP and for the hard-block layer. Outputs were
   unaffected: `build_unidir_rr_opins` does not use that list.

   Effect on the hard-block layer: DSP input sinks on layer 0 could not be reached from any layer-2
   output pin. A reverse search of the written RR graph found sources on layers 0 and 1 only, and
   VPR's delta-delay sampler logged "No routing path" for them.

   Fix (this branch, `vpr-cb-layers.patch`): the list also includes every layer a pin of the type
   connects to. A VPR built with it gives identical CPD and wirelength to the existing binary on:
   - split-CLB (alu4) and stacked-CLB (tseng) CLB-only runs;
   - hard-block 2D and per-layer-column runs (eltwise_layer).

   All results here use that build.
2. **Pins join only adjacent layers** (`is_pin_conencted_to_layer`, maximum offset 1). In the
   hard-block layer placement, the top logic layer is two bonds from the hard blocks, so the middle
   layer's tracks carry every signal between them. Hard-block pins, inputs included, reach the
   middle layer. With own-layer CLB inputs, the upper logic layer's input pins also read the middle
   layer; that is the only change to the CLB, and only in this placement. Proposed VPR fix for a real
   two-bond reach: a per-pin maximum offset (or through-silicon vias as routing nodes) instead of the
   hard-coded 1.
3. **Multi-layer tiles must be 1x1** (`validate_tile_layer_span`). VTR's Koios architecture makes RAM
   and DSP tiles 2 and 4 CLBs tall (`k6FracN10LB_mem20K_complexDSP_customSB_22nm.xml`), so every placement uses LaZagna's 1x1 hard tiles. A 1x1
   tile packs 105 RAM pins or 148 DSP pins into one tile's channels. That exaggerates pin congestion
   at hard blocks, and so the value of a placement that gives hard blocks more pin access (`span`).
   Proposed fix: allow `layer_span` tiles taller than one row (`validate_tile_layer_span`, the grid
   reservation in `DeviceGrid::reserve_layer_footprints`, and pin lookups by height offset).

## What is estimated

- **Hard-block delays: estimated, not simulated.** They are LaZagna's 40 nm template values,
  scaled by the sky130 over template delay of the CLB path (crossbar input + mean LUT + LUT to BLE
  output). From `spice/delays_tt_all.json` set `2d10_w100` against the template's 95 + 261 + 25 ps,
  that scale is 2.327 (`hardblocks.delay_scale`). The generated arch.xml files then have:
  - an 18x19 or 27x27 multiply of 6.436 ns;
  - a RAM clock-to-Q of 1.620 ns;
  - a RAM setup of -0.153 ns.
  A real sky130 multiplier and RAM macro would differ.
- **Crossing inside a spanning hard block:** 339.2 ps per crossing, the split CLB's laid-out
  crossing (driver, bond, receiver; set `3d20own_w100`). A RAM's port-2 and upper data pins pay it
  in and out; an 18x19 multiplier pays nothing, since it sits on its own pins' layer.
- **Hard-block area and footprint:** every hard tile is one grid cell, as in LaZagna's base
  architecture, although its `area` attributes say a RAM is 2.6 and a DSP 4.7 CLB tiles. Footprints
  here are in grid cells. Converting them to um2 also needs each fabric's tile size; a split tile at
  100 tracks per layer, with input pins reaching both layers, is 1.163 of the 2D tile
  (pnr/tile_results_n20_local_w100.txt). Own-layer pins shrink its connection blocks; that variant
  was not laid out at 100 tracks.
- **Hard-block-layer and RAM-under-DSP connection blocks:** a hard block whose inputs read two
  layers' tracks needs a bigger connection block. That is not in its delay or area. With own-layer
  CLB inputs, the upper logic layer's input pins also read the middle layer in the layer placement,
  but keep the own-layer connection-block delay (356.6 ps against 380.9 ps for pins reaching both
  layers, sets `3d20own_w100` and `3d20_w100`).
- Flip-flops keep the template's timing, as in every sky130 sweep.
- Routing and connection-block delays are the sets' 100-track values at every width. A run at a
  wider relaxed width has larger muxes than simulated, and a narrower one smaller. Split / layer,
  at 1.351 of the 2D tracks per layer, is the most affected.

## Implementation notes

Fixed during development:
- `compare_2d_3d.py run()` used `log_file` without defining it, so every run raised `NameError`.
- The RAM clock pin kept LaZagna's Fc 0. With routed clocks, VPR found no path to it: every early pilot
  run failed with "Cannot route ... to memory[0].clk[0] -- no possible path".
- The hard-block layer placement had no path between an upper-layer FLE and a hard block: own-layer
  inputs, adjacent-layer pins, and the VPR bug above.
- In `span`, LaZagna's DSP wrapper sits on layer 0. The layer-1 multiplier's signals therefore crossed
  down and back up: 0.678 ns (2 x 339 ps) of "intra complex_dsp routing" each way in a detailed
  timing report. The multipliers are now wired straight to their own layer's pins (0 ns).
- The stacked-CLB `span` was not spanning: it put separate columns on both layers. That layout is now
  `columns`, a placement of its own, and `span` spans for both fabrics.
- The crossing inside a spanning hard block differed by fabric (339 ps split, 132 ps stacked). Both
  now use the split CLB's laid-out 339.2 ps (`--hard-crossing-ps`).
- RAM address ports were pinned whole on one side; they are now spread bit by bit.
- run_hardblocks.sh had fixed 100 tracks, which do not route (see Method).

Checked and kept:
- the synthesis flow (koios_hb.v, mulmap.v, fix_blif.py);
- the mem20K modes;
- the RAM timing model. VPR times LaZagna's sequential-plus-`combinational_sink_ports` pattern as
  registered inputs and outputs with an internal register-to-register path, not as a path through
  the RAM (`timing_graph_builder.cpp`);
- grid sizing;
- the SPICE-to-template delay scaling;
- `--hard-blocks none` output: byte-identical to the CLB-only generator for 36 architectures (template, split,
  stacked, 4-layer with links), results.csv included.

## Cost of a full 10-seed sweep

Measured with /usr/bin/time on this Mac (route_table.txt, ideal_table.txt). Up to about 16 VPR jobs
ran at once on 18 cores, so these wall times per run are pessimistic:

- **Routed-clock runs (width search plus relaxed route):** 180 runs (5 designs x 4 seeds x 9
  configurations) took 11.3 VPR-hours (the sum of each run's wall time). Mean per run is 2.7 to 4.7 minutes by configuration; the
  slowest single run took 13.1 minutes (stacked / span, attention_layer).
- **Ideal-clock reruns (one place and route at a known width):** 180 runs, 1.4 VPR-hours.
- **Peak memory:** 1.72 GB per run (split / layer, the 3-layer device); at most 1.43 GB for the
  others.

A 10-seed sweep of the same 5 designs is 2.5 times this:
- (11.3 + 1.4) x 2.5 = 31.8 VPR-hours;
- about 4.0 hours wall time at 8 jobs here (8 x 1.72 = 13.8 GB);
- about 8 hours at the server's 4-job limit.

More designs scale linearly; the next ones by size are robot_rl (15k LUTs) and bwave_like.fixed.small
(27k LUTs, 170 RAMs, 280 multipliers). The own-layer hard-input split runs were much slower to
route, which is one reason "both" is the main result.

## Commands

```bash
# Koios BLIFs (Yosys from this repo's build; 4 designs at a time)
hardblocks/synth_koios.sh $KOIOS eltwise_layer spmv conv_layer attention_layer tpu_like.small.os

# VPR with vpr-cb-layers.patch: the prototype CMake project needs the libcatch2 submodule
cmake -S ../ -B $BUILD -DCMAKE_BUILD_TYPE=Release -DPROTOTYPE_BUILD_VPR=ON \
      -DOPENSSL_ROOT_DIR=/opt/homebrew/opt/openssl@3 && make -C $BUILD -j6 vpr

# Default sweep: 2D, split (own-layer hard inputs) and stacked fabrics, four placements
VPR=$BUILD/vpr/vpr RELAX=1.3 TIMED=1 BENCH=$KOIOS SEEDS="1 2" ./run_hardblocks.sh $OUT

# As run here: the split fabric with hard-block inputs on both layers (with 2D), stacked CLBs
VPR=$BUILD/vpr/vpr RELAX=1.3 TIMED=1 BENCH=$KOIOS SEEDS="1 2 3 4" HARD_INPUTS=both FABRICS=split \
    JOBS_SPLIT=6 ./run_hardblocks.sh $OUT_BOTH
VPR=$BUILD/vpr/vpr RELAX=1.3 TIMED=1 BENCH=$KOIOS SEEDS="1 2 3 4" FABRICS=stack JOBS_STACK=4 \
    ./run_hardblocks.sh $OUT
# Ideal-clock reruns at the same widths: copy each finished run's arch.xml and width.txt into
# <name>_clkideal folders of a new OUT, then the same command with CLOCK=ideal
# Relaxed routes that failed were retried once with --max_router_iterations 300 (all still failed)

python3 hb_table.py $OUT --per-bench --cost     # ratios, Wmin, footprint, cost
python3 hb_paths.py $OUT                        # what the critical paths go through
python3 compare_configs.py $OUT/split/results_columns.csv:2d \
    split_columns=$OUT/split/results_columns.csv:3d stack_columns=$OUT/stack/results_columns.csv:3d
```

## Files

- `hardblocks.py`: layouts, hard-block architecture and the layer rules.
- `compare_2d_3d.py`: `--hard-blocks`, `--hard-inputs`, `--hard-crossing-ps`, `--hard-delay-scale`,
  `--clock-modeling`, `--no-2d`.
- `run_hardblocks.sh`: the sweep.
- `hb_table.py`, `hb_paths.py`: tables and critical paths.
- `hardblocks/`: synthesis (synth_koios.sh, koios_hb.v, mulmap.v, fix_blif.py), vpr_timed.sh, and
  the results (CSV per fabric and placement, `widths.csv`, tables).
- `vpr-cb-layers.patch`: the VPR fix, also committed in `vpr/src/route/rr_graph.cpp`.
- `spice/delays_tt_all.json`: the sky130 sets, including the stacked fabric's.

