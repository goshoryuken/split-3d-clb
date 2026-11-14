# Transistor-level delays of the 3D CLB (sky130, Spectre)

Every number below is read from `delays_tt.json`, `delays_ss.json` or a
`compare_results_spice_*.csv` file in this repo, recomputed with `compare_configs.py`.

## Setup

* **Simulator and models**: Cadence Spectre 24.1 on the SiliconJackets server (loaded by a
  block's `envsetup`), with the course kit's sky130 models (`sky130.lib.spice`, corners `tt`
  and `ss`, 1.8 V, 27 C). Devices are `nfet_01v8` / `pfet_01v8`, L = 0.15 um.
* **Model check** (`fo4.sp`, `cal.sp`): fan-out-of-4 inverter 54.5 ps falling / 62.2 ps
  rising; saturation current 501 uA/um (n) and 201 uA/um (p); gate charge over 0-1.8 V
  2.26 fC/um (n) and 1.98 fC/um (p). The same FO4 with explicit and parameterized widths agrees.
* **Circuits** (`make_spice.py`): OpenFPGA's circuit models, the ones LaZagna's RTL instantiates
  (`task/designs/openfpga_arch.xml`): two-level transmission-gate muxes with an inverter on each
  input (routing and connection blocks: three-stage output buffer; crossbar: one inverter out),
  a 64-leaf transmission-gate LUT with true and complement select rails, static config bits.
  Pass gates keep OpenFPGA's sizes (n 0.42 um, p 0.84 um). Every buffer that drives a long net
  is a tapered chain sized for its load (stage effort about 4), the same rule in 2D and 3D;
  routing and connection-block buffers keep OpenFPGA's three stages.
* **Fabric sizes**: mux sizes and loads per track are averages over one interior tile of the
  RTL LaZagna generated; CLB and tile sizes from the layouts (`pnr/tile_results_*.txt`, the
  20-LUT layer core 520 x 520 um). Fabrics marked *est.* were not generated or laid out
  (`2d12_w110` from `cluster_size_model.py`; `3d20own_w100` scaled from the 66-track layout).
* **Wires**: RC ladders; R and C per micron from the kit's tech LEF at run time (not stored
  here). Routing L4 on met3/met4 at minimum width, L16 at double width and spacing, CLB nets on
  met2. Assumed: ground capacitance x2 for neighbours at minimum spacing (x1.5 for L16).
* **Layer crossing**, two versions:
  * *as laid out*: a driver, a wire to a 2.5 um met5 pad, via stacks, pads and bond, and a
    receiver sized for the net on the other layer (the layout put BUFX4 cells on both sides);
  * *direct*: the bond used as a via. One driver, sized for both layers' nets, reaches the
    other layer through the via stacks and pads with no receiver; in routing, the wire end goes
    straight into the next mux's input inverter.
  * Assumed bond: 0.5 ohm and 1 fF at the interface; via stacks from the LEF cut resistances.
* **What each delay is** (VPR's `Tdel`, wires have R = C = 0 in these architectures):
  `l4`/`l16` one hop, from a switch-block mux input to the next one (mux, driver, wire and every
  load on it); `cb` track to CLB input pin driver; `xbar_pin` / `xbar_fb` pin or FLE output net
  to the LUT input (the net's wire and fanout, the crossbar mux); `ble` LUT output to FLE output
  (output mux and its driver); `lut0`-`lut5` each LUT input; `clb_crossing` extra delay of a
  feedback path to the other layer; `route_crossing` extra delay of a routing hop that changes
  layer. Flip-flop timing keeps VPR's template values.

## Delays, typical corner (ps)

| Fabric | L4 hop | L16 hop | Conn. block | Crossbar from pin | Crossbar from feedback | FLE output | LUT slowest / fastest input | Crossing in CLB | Crossing in routing | Routing crossing / L4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2D 10-LUT, 100 tracks (`2d10_w100`) | 460 | 880 | 353 | 260 | 252 | 301 | 474 / 126 | | | |
| 2D 12-LUT, 110 tracks (`2d12_w110`, est.) | 483 | 857 | 365 | 283 | 274 | 304 | 474 / 127 | | | |
| 20-LUT split, 100 tracks, as laid out (`3d20_w100`) | 494 | 907 | 381 | 270 | 262 | 302 | 474 / 127 | 339 | 133 | 0.270 |
| same, direct crossing | 494 | 907 | 381 | 270 | 264 | 322 | 474 / 127 | 16 | 0.08 | 0.000 |
| 20-LUT split, own-layer pins, 100 tracks (`3d20own_w100`, est.) | 480 | 883 | 357 | 270 | 262 | 302 | 474 / 127 | 339 | 131 | 0.272 |
| same, direct crossing | 480 | 883 | 357 | 270 | 264 | 322 | 474 / 127 | 16 | 0.08 | 0.000 |
| 2D 10-LUT, 84 tracks (`2d10_w84`) | 457 | 866 | 344 | 260 | 252 | 300 | 474 / 126 | | | |
| 20-LUT split, own-layer pins, 66 tracks (`3d20own_w66`) | 470 | 898 | 346 | 270 | 262 | 300 | 474 / 127 | 339 | 129 | 0.274 |

Slow corner (`delays_ss.json`): every delay about 1.4 to 1.6 times the typical one; the
crossing as laid out is 487 ps in the CLB and 0.29 of an L4 hop in routing; direct, 17 ps.

What the table says:

* **Compared with LaZagna's default**: LaZagna charges a layer crossing 0.739 times an L4
  driver (Boutros et al., 7 nm). In sky130, a crossing with its own driver and receiver costs
  0.27 to 0.29 of an L4 hop (the hop includes 2.3 to 2.5 mm of wire), and a bond used as a via costs
  nothing measurable in routing (0.08 ps) and 16 ps inside the CLB.
* **The crossing as laid out is expensive inside the CLB** (339 ps): driving a pad and then
  re-buffering for a whole layer's crossbar adds about six inverter stages. A single driver
  sized for both layers' nets costs 20 ps more at the FLE output and 16 ps per crossing.
* **The split CLB pays for its size elsewhere**: its tile is 7.8% wider at 100 tracks, so an
  L4 hop is 7% slower (494 vs 460 ps); input pins reaching both layers double its
  connection-block muxes (26 vs 13 inputs), 8% slower (381 vs 353 ps). With pins on their own
  layer the connection block is back to 2D's (357 ps) and the L4 hop 4% slower. Its 60-input
  crossbar muxes are 4% slower than 2D's 50-input ones.

## Speed with these delays (VPR, 10 seeds)

`run_spice_delays.sh` (with `OWN=1` for own-layer pins; `run_spice_seeds10.sh` runs both over
ten seeds): same fabrics, tracks and wire spans as the template-delay runs (`run_seeds.sh`),
VPR's default placement delay model, server VPR. Files `compare_results_spice10_*.csv`
(the 3-seed `compare_results_spice_*.csv` are their first three seeds). Every run routed.

Over the 10-LUT 2D CLB, the faster 2D size with these delays (3D / 2D, lower is faster):

| Fabric | 7 bigger designs | Faster on | Per-seed range | 16 small designs | Faster on | Per-seed range |
|---|---:|---:|---|---:|---:|---|
| 2D 12-LUT | 1.035 | 1/7 | 0.997-1.075 | 1.011 | 4/16 | 0.999-1.027 |
| 20-LUT split, crossing as laid out | 0.985 | 4/7 | 0.958-1.032 | 1.007 | 9/16 | 0.993-1.028 |
| 20-LUT split, direct crossing | 0.961 | 4/7 | 0.941-0.984 | 0.986 | 10/16 | 0.966-1.002 |
| own-layer pins, crossing as laid out | 0.969 | 4/7 | 0.950-0.991 | 0.987 | 11/16 | 0.974-1.004 |
| **own-layer pins, direct crossing** | **0.942** | **7/7** | 0.918-0.996 | **0.961** | **13/16** | 0.941-0.970 |

Against the 12-LUT 2D CLB, own-layer pins with direct crossings are 0.910 (bigger, 6/7) and
0.951 (small, 14/16).

So with transistor-level delays the 3D CLB still beats the best 2D CLB on every seed: 5.8% on
the bigger designs and 3.9% on the small ones, against 7.4% and 5.7% in the template model
(`ceil_*_seeds_split.csv`, 10 seeds). That needs input pins on their own layer and the bond
used as a via; with the crossing as laid out (driver and receiver) the gain is 3% at most,
and the plain split is no faster than 2D on the small designs.

## Layout check: the bond as a via

The 20-LUT split CLB (pads mid-core) laid out again with one BUFX16 sending driver per
crossing and no receiver (`pnr/run_bond.sh DIRECT=1`; drivers kept from resizing in
synthesis and Innovus), timed with both layers joined in Tempus at 2 ns. FLE output to
crossbar mux output, mean of 1,200 paths each (`pnr/compare_joined.py`, files in `pnr/`):

| Layout | Same layer | Crossing | 2D 10-LUT |
|---|---:|---:|---:|
| driver and receiver (`clb_paths_local20_center_2ns.csv`) | 0.932 | 1.692 | 0.910 |
| bond as a via (`clb_paths_local20_center_direct_2ns.csv`) | 0.915 | 1.582 | 0.910 |

* Without the receiver a crossing is 6.5% faster on average; 13 of 20 sending FLEs are faster
  and the slowest path drops from 2.502 to 2.262 ns.
* One path stage by stage (`crossing_path_local20_center*.txt`, FLE 0 to layer 1): from the
  FLE's output driver to the far crossbar's input inverter, 0.999 ns with driver and
  receiver, 0.566 ns direct, where one BUFX16 drives the bond and all 49 loads on the far layer.
* It is still not the 16 ps SPICE gives. Here the crossing driver hangs off the FLE's
  output net (0.58 pF), after the layer's own output driver, so it adds a stage (0.358 ns)
  and takes a slow edge. SPICE's direct crossing is one driver at the FLE output sized for
  both layers' nets. Laying that out needs a second output from the FLE module.
* Hardware check (`direct_crossing_results.txt`): passes at 7 ns and slower, fails at 6 and
  5 ns, the same as with receivers; all three cut cases fail as they must.
* The tools undo a direct crossing unless told not to: synthesis made the bare wire a
  CLKBUFX4 driving 0.96 pF (crossing 2.288 ns), and Innovus ignores synthesis's dont_touch
  (BUFX16 shrunk to BUFX4_HS, 1.950 ns).

## Layout check: the crossing driver inside the FLE (tap)

The same CLB laid out with the crossing driver inside the FLE, in parallel with its output
driver (`pnr_local20i`, the topology SPICE's direct crossing models). Paths from
`compare_joined.py pnr/clb_paths_local20_center_tap_2ns.csv pnr/clb_paths_2d_2ns.csv 20`:

| Layout | Same layer | Crossing | Pin (same layer) | 2D 10-LUT |
|---|---:|---:|---:|---:|
| driver and receiver | 0.932 | 1.692 | | 0.910 |
| bond as a via, driver after the FLE | 0.915 | 1.582 | | 0.910 |
| **driver inside the FLE** | 0.931 | **1.435** | 1.285 | 0.910 (pin 1.231) |

* The fastest crossing laid out so far, 15% below driver and receiver, but still 0.5 ns over
  same layer: far from SPICE's 16 ps. The layout's crossing still drives the far layer's whole
  crossbar input net through a BUFX16 (`crossing_path_local20_center_tap.txt`).
* Hardware check (`pnr/direct_crossing_results.txt`, `chain/equiv20i`): passes at 20, 10
  and 8 ns, fails at 7 (69 errors), 6 and 5; the three cut cases fail as they must. The
  driver-after-FLE layout passed at 7 ns, so this one is one step slower in that check. The
  no-delay run (`gate_20_NONE_none`) never finished: it ran until the server's shutdown.

## Speed with the crossing as laid out (tap layout)

`run_layout_delays.sh` turns the tap layout's crossing into VPR delays (`layout_delays.py`):
r = (crossing - same layer) / same layer = 0.541; the CLB crossing is r x the crossbar
feedback delay (low, 142.5 ps) or r x (BLE + crossbar feedback) (high, 316.5 ps); the
routing crossing stays SPICE's as laid out (130.77 ps). Own-layer pins, 10 seeds, the same
2D runs as above. Files `compare_results_layout_{small,big}_{low,high}.csv`.

| Over the 10-LUT 2D CLB | 7 bigger designs | Faster on | Per-seed range | 16 small designs | Faster on | Per-seed range |
|---|---:|---:|---|---:|---:|---|
| crossing as laid out, SPICE (above) | 0.969 | 4/7 | 0.950-0.991 | 0.987 | 11/16 | 0.974-1.004 |
| tap layout, low | 0.964 | 4/7 | 0.937-0.987 | 0.992 | 10/16 | 0.974-1.005 |
| tap layout, high | 0.977 | 4/7 | 0.951-0.996 | 0.995 | 9/16 | 0.975-1.008 |
| direct crossing, SPICE (above) | 0.942 | 7/7 | 0.918-0.996 | 0.961 | 13/16 | 0.941-0.970 |

So with the crossing measured on the best layout so far, the split CLB is 2-4% faster than
2D on the bigger designs and about even (0.5-1%) on the small ones. The 4-6% of the direct
crossing needs a crossing close to SPICE's, which no layout has reached yet.

## Split against stacked CLBs

`run_stacked_spice.sh`: stacked 10-LUT CLBs (stock LaZagna 3D, `compare_2d_3d.py --stacked`)
with their own SPICE set, `3d10stack_w100`. Its muxes and loads come from LaZagna's stacked
RTL (`make_spice.py` comment), and its tile is as laid out. Its CLB delays equal 2D's; its
routing is slower than 2D's (L4 486 vs 460 ps, CB 378 vs 353) from the wider tile and pins
loading both layers. Its routing crossing is 131.9 ps as laid out and 0.08 ps as a via. Ten
seeds, the same 2D runs. Every run routed. Files
`compare_results_spice10_stacked_{small,big}_{laid,direct}.csv`.

| Over the 10-LUT 2D CLB | 7 bigger designs | Faster on | Per-seed range | 16 small designs | Faster on | Per-seed range |
|---|---:|---:|---|---:|---:|---|
| stacked, crossing as laid out | 0.999 | 3/7 | 0.968-1.039 | 0.979 | 12/16 | 0.966-0.988 |
| stacked, bond as a via | 0.971 | 7/7 | 0.945-0.993 | 0.955 | 15/16 | 0.942-0.974 |
| split (own-layer pins), crossing as laid out | 0.969 | 4/7 | 0.950-0.991 | 0.987 | 11/16 | 0.974-1.004 |
| split, tap layout low / high | 0.964 / 0.977 | 4/7 | | 0.992 / 0.995 | 10/16, 9/16 | |
| split, bond as a via | 0.942 | 7/7 | 0.918-0.996 | 0.961 | 13/16 | 0.941-0.970 |

Split over stacked, like for like:

| | 7 bigger designs | Faster on | Per-seed range | 16 small designs | Faster on | Per-seed range |
|---|---:|---:|---|---:|---:|---|
| both as laid out | 0.971 | 4/7 | 0.952-1.000 | 1.008 | 9/16 | 0.991-1.023 |
| split tap low / high, stacked as laid out | 0.965 / 0.978 | 4/7, 3/7 | | 1.013 / 1.016 | 8/16 | |
| both bond as a via | 0.970 | 3/7 | 0.944-1.014 | 1.007 | 8/16 | 0.984-1.032 |

* With transistor-level delays the split CLB is about 3% faster than stacked on the bigger
  designs but about 1% slower on the small ones. With template delays it was 4% and 2%
  faster.
* It depends on the design. On the bigger ones, split over stacked as laid out, mean CPD per
  design: blob_merge 0.848, stereovision0 0.906, sha 0.975, diffeq2 1.000, stereovision1
  1.022, stereovision2 1.026, bgm 1.036. On the small ones split loses most on bigkey
  (1.153), dsip (1.144) and des (1.064), and wins on 9 of 16.
* Stacked CLBs change layers only in the routing, where VPR's placement delay model is
  weakest (TECHNICAL_MAP.md 1.5, Escaping Flatland). A better 3D placer could help either
  fabric; not tested.

## 7 nm (ASAP7)

`run_7nm.sh`: the same circuits, fabrics, tracks, wire spans, benchmarks and ten seeds, with
ASAP7 (an open predictive 7 nm FinFET kit; the kit Waqar et al. use). Set-up, in
`make_spice.py`:

* RVT devices at 0.7 V, one fin per unit inverter and per pass gate (`cal7.sp`: one-fin nfet
  37.3 uA, pfet 32.0 uA, FO4 7.9 / 8.1 ps).
* Wire R and C per layer from OpenROAD's ASAP7 setup: CLB nets M2/M3, L4 tracks M4/M5, L16 the
  same at double width.
* Every length scaled from sky130 by the 2D CLB's side in the ASAP7 layout (S7 = 0.101).
  Routing tiles were not laid out at 7 nm, so all 7 nm fabrics are marked estimated.
* Bond: hybrid, 1 um pitch, 0.5 um pads (capacitance assumed).
* Flip-flop from the ASAP7 library (clock to Q 64.7 ps, setup 12.5 ps) instead of VPR's
  template.

Delays (`delays_7nm_tt.json`, ps):

| | L4 hop | L16 hop | CB | crossbar from pin | LUT input 0 | routing crossing | CLB crossing (direct) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2D 10-LUT | 149.45 | 679.54 | 69.23 | 42.81 | 55.93 | | |
| split, own-layer pins | 162.04 | 671.36 | 70.95 | 44.78 | 55.96 | 41.32 | 53.07 (15.30) |
| stacked 10-LUT | 164.9 | 736.2 | 75.87 | 42.82 | 55.93 | 42.33 | |

At 7 nm the wires dominate: an L4 hop is 2.7 LUT delays (about 1 in sky130). L16 has no
repeaters, so per tile it is slower than L4 here (in sky130 it was faster).

Speed, 10 seeds, every run routed (`compare_results_7nm_{small,big}_*.csv`):

| Over the 10-LUT 2D CLB | 7 bigger designs | Faster on | Per-seed range | 16 small designs | Faster on | Per-seed range |
|---|---:|---:|---|---:|---:|---|
| 2D 12-LUT | 1.052 | 1/7 | 1.014-1.107 | 1.081 | 0/16 | 1.045-1.095 |
| split, crossing as laid out | **0.934** | 6/7 | 0.892-0.993 | 1.006 | 9/16 | 0.987-1.025 |
| split, bond as a via | **0.908** | 7/7 | 0.865-0.957 | 0.983 | 12/16 | 0.960-1.007 |
| stacked, crossing as laid out | 0.970 | 5/7 | 0.922-1.010 | 1.007 | 6/16 | 0.987-1.029 |
| stacked, bond as a via | 0.925 | 5/7 | 0.890-0.992 | 0.975 | 13/16 | 0.945-0.993 |

| Split over stacked | 7 bigger designs | Faster on | Per-seed range | 16 small designs | Faster on | Per-seed range |
|---|---:|---:|---|---:|---:|---|
| both as laid out | 0.963 | 6/7 | 0.925-1.029 | 0.999 | 8/16 | 0.984-1.025 |
| both bond as a via | 0.982 | 3/7 | 0.961-1.020 | 1.008 | 9/16 | 0.988-1.034 |

* On the bigger designs the 3D gain grows at 7 nm. Split vs 2D goes from 0.969 to 0.934 as
  laid out, and from 0.942 to 0.908 with the bond as a via. Split over stacked goes from 0.971
  (4/7) to 0.963 (6/7). The 2D 10-LUT CLB is still the best 2D size.
* On the small designs 3D gives nothing at 7 nm: split 1.006 as laid out, 0.983 as a via. The
  same three designs lose most: des 1.141, dsip 1.096, bigkey 1.076 (split as laid out).
* Per design, split as laid out over 2D, bigger designs: blob_merge 0.878, bgm 0.883,
  stereovision0 0.885, stereovision1 0.917, diffeq2 0.971, stereovision2 0.973, sha 1.045.
* Against Waqar et al. (LITERATURE.md): they give 11.9-30% lower CPD (27% in the abstract) with
  oxide-transistor routing above the CLBs, overdriven at 1.2 V, and about 8% at equal voltage
  for one tile. Ours, 7-9% on the bigger designs, needs no new devices. Baselines,
  architectures and benchmarks differ, so this is not a head-to-head result.

## Limits

* Pass-gate sizes are OpenFPGA's; only buffers are sized. No COFFE-style search over
  transistor sizes, so absolute delays are not optimized, in either fabric.
* Wire coupling factors and the bond's R and C are assumptions; the via stack and metal values
  come from the kit. Two fabrics (`est.`) have estimated tile and mux sizes.
* Flip-flop timing is VPR's 40 nm template in the sky130 sets (it adds the same to both
  fabrics), ASAP7's in the 7 nm sets.
* 7 nm: ASAP7 is a predictive kit (2016 models), not a foundry process. Tiles are scaled from
  the CLB, not laid out. L16 wires have no repeaters.
* The server VPR runs the simple placement delay model (TECHNICAL_MAP.md 1.5).

## Files

`make_spice.py` (decks, Spectre runs, delay sets), `delays_tt.json`, `delays_ss.json`,
`fo4.sp` and `cal.sp` (model checks; `MODELS` stands for the kit's models folder),
`layout_delays.py`, `../run_spice_delays.sh`, `../run_layout_delays.sh`,
`../run_stacked_spice.sh`, `../compare_results_spice*_*.csv`, `../compare_results_layout_*.csv`.
7 nm: `cal7.sp`, `delays_7nm_tt.json`, `../run_7nm.sh`, `../compare_results_7nm_*.csv`; the
ASAP7 model file is not stored here (github.com/The-OpenROAD-Project/asap7_pdk_r1p7,
models/hspice/7nm_TT_160803.pm, BSD; on the server in ~/3d-clb/asap7_models).
