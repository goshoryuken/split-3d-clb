# Technical map

Every code change (section 1), the scripts that produce the results (section 2), and which
file backs each number (section 3).

Paths are relative to `prototype/lazagna/` unless they start with `vpr/`, `libs/` or `~`.

## 0. Where things live

| What | Where |
|---|---|
| VTR/VPR with the changes | this repository, on top of `5abd3acaa` (the VTR version LaZagna pins) |
| The same changes as patches | `vtr-3d-clb.patch`, `vpr-direct-layers.patch`, `vpr-multilayer-check.patch`, `vpr-placer-layers.patch`, `lazagna-vtr-fixes.patch`, `openfpga-lazagna.patch` (see 1.4) |
| LaZagna changes | `lazagna-3d-clb-branch.patch` (see 1.6) |
| Layout flow | `pnr/`, run against a sky130 RTL-to-GDS flow (`$FLOW`), which is not part of this repository |

## 1. C++ and tool changes

### 1.1 VTR architecture library (`libs/libarchfpga`)

Source: `git diff 5abd3acaa HEAD -- libs vpr` (49 files changed, 979+/99-).

| File | Struct / function | What it does |
|---|---|---|
| `src/physical_types.h` | `t_physical_tile_type::layer_span` (int, default 1) | How many layers one tile occupies, upward from its anchor layer. |
| | `t_physical_tile_type::pin_physical_layer` (vector<int>) | Which layer of the tile each pin sits on, relative to the anchor. |
| | `t_pb_type::instance_layer_offsets` (vector<int>) | Which layer each instance of a sub-block (e.g. each FLE) sits on, relative to its parent. Empty = all on 0. |
| | `t_interconnect::layer_crossing_delay` (double, seconds) | Extra delay per layer crossed by a connection inside the CLB (crossbar). |
| | `t_direct_inf::layer_offset` (int = 0) | A `<direct>` link can reach a tile on another layer. |
| | `t_direct_inf::placement_macro` (bool = true) | `false` makes a direct a routing shortcut instead of a carry-chain macro. |
| `src/read_xml_arch_file.cpp` | `ProcessTileProps` | Reads `<tile layer_span="N">`. |
| | `ProcessPinLocations`, `t_pin_locs::pin_layers`, `LoadPinLoc` | Reads `<loc pin_layer="N">` and stores it in `pin_physical_layer`. |
| | `ProcessInstanceLayerOffsets` (new, called from `ProcessPb_Type`) | Reads `instance_layer_offsets="0 0 1 1 ..."`; rejects it on the root CLB, rejects non-digits, requires exactly `num_pb` entries. |
| | `ProcessInterconnect` | Reads `layer_crossing_delay`; must be finite and nonnegative. |
| | `ProcessDirects` | Accepts `layer_offset` and `placement_macro`. |
| | `XmlReadArch` | Validates every tile that sets `layer_span`. |
| `src/pb_type_layers.h/.cpp` (new) | `pb_type_instance_layer_offset`, `pb_graph_node_layer_offset`, `pb_type_max_layer_offset` | Look up a sub-block's layer, adding offsets down the hierarchy (overflow-checked). |
| | `validate_tile_layer_span` | Multi-layer tiles must be 1x1, capacity 1, one sub-tile; every pin and every internal site must fit inside `layer_span`. |
| | `apply_internal_layer_delays` | Adds `layer_crossing_delay` x layers crossed to each CLB-internal edge's min and max delay; root pins use their `pin_layer`. |
| `src/device_grid.h/.cpp` | `t_grid_tile::layer_anchor_offset`; `DeviceGrid::reserve_layer_footprints` (in the constructor) | Marks the cells above a spanning tile as reserved (they must be EMPTY), so nothing else is placed there. |
| | `DeviceGrid::get_layer_anchor_offset`, `DeviceGrid::get_footprint_type` | For any cell, find the multi-layer tile that owns it. Used everywhere `get_physical_type` used to be (below). |
| `src/physical_types_util.h/.cpp` | `get_pin_physical_layer` (new); `is_pin_conencted_to_layer` | Pin connections start from the layer the pin sits on, not the anchor. |
| `src/echo_arch.cpp` | `PrintPb_types_rec` | Prints `instance_layer_offsets` in the architecture echo. |
| `src/arch_util.cpp` | `alloc_and_load_default_child_for_pb_type` | Comment only. |
| `test/test_pb_type_layers.cpp` (new) | 6 `TEST_CASE`s | Offsets, mode envelope, span validation, pin layers, grid reservation, crossing delays. |

### 1.2 VPR (`vpr/src`) and the routing-graph library

| File | Struct / function | What it does |
|---|---|---|
| `base/SetupVPR.cpp` | `SetupVPR` | Validates every tile; a multi-layer CLB with flat routing, analytical placement or power analysis is an error. |
| | `SetupPlacerOpts` | Sets `delay_model_inferred` when the user did not pass `--place_delay_model`. |
| `base/vpr_types.h` | `t_placer_opts::delay_model_inferred` | See `compute_place_delay_model`. |
| `base/SetupGrid.cpp` | `calculate_device_utilization` | A spanning tile counts `width x height x layer_span`; reserved cells are not counted again. |
| `base/blk_loc_registry.cpp` | `BlkLocRegistry::set_block_location` | Rejects out-of-range layers and a second block on an occupied anchor. |
| `base/layer_report.h/.cpp` (new) | `write_internal_layer_report` | After a successful route, writes `<prefix>internal_layers.tsv`: each LUT's layer, each CLB's footprint, and each used cross-layer crossbar edge with its delay. Called from `vpr_flow` (`base/vpr_api.cpp`). |
| `base/netlist_writer.cpp` | `LutInst` (new `relative_layer_`, `absolute_layer_`) | Post-route Verilog LUTs carry `(* vtr_relative_layer = .., vtr_absolute_layer = .. *)`. |
| `base/read_route.cpp` | `process_nodes`, `print_route` | Read and print routes whose pins are on an upper layer of a tile. |
| `base/hyper_graph.h`, `base/partitioning_engine.h/.cpp`, `base/vpr_types.cpp`, `util/vpr_utils.cpp` (`sync_grid_to_blocks`) | | Build fixes for LaZagna's VTR (reference parameters defaulting to `nullptr`, missing `<sstream>`, `std::string` passed to printf). Also in `lazagna-vtr-fixes.patch`. |
| `pack/pb_type_graph.cpp` | `alloc_and_load_all_pb_graphs`, `alloc_and_load_pb_graph`, `echo_pb_rec` | Applies the crossing delays to the CLB graph; validates each node's layer; prints it. |
| `pack/post_routing_pb_pin_fixup.cpp` | `update_cluster_pin_with_post_routing_results` | Finds each pin's routing node on the pin's own layer. |
| `place/timing_place_lookup.cpp` | `compute_place_delay_model` | If the user did not choose a model and the device has more than one layer, uses `delta` instead of `simple` (logs why). **Not in the server's VPR** (1.5). |
| | `find_direct_connect_sample_locations` | Skips directs with a `layer_offset` (the delta model routes them). |
| `place/place_macro.cpp` | `PlaceMacros::alloc_and_load_idirect_from_blk_pin_` | Directs with `placement_macro="false"` never form macros. |
| `place/place_delay_model.cpp` | `comp_td_single_connection_delay` | Ignores a `VprError` from LaZagna's debug write of `delay_model.txt` ("some delay models cannot be written in every build", per the code comment). |
| `place/initial_placement.cpp` | `init_blk_types_empty_locations`, `try_place_macro_randomly` | Skip layers where a block type has no sites. |
| `place/compressed_grid.h` | `grid_loc_to_compressed_loc_approx` | Returns `OPEN` for a layer with no sites. |
| `route/rr_graph.cpp` | `get_layers_of_physical_types` | A spanning tile counts on every layer it covers. |
| | `add_pins_rr_graph`, `build_bidir_rr_opins`, `build_unidir_rr_opins` | Pin nodes go on anchor layer + `pin_physical_layer`. |
| | `get_opin_direct_connections` | Directs reach `layer + layer_offset`, skip reserved cells, and enter the target pin's own layer. |
| `route/rr_graph2.cpp` | `add_pins_spatial_lookup`, `get_track_to_pins` | Pin lookup on every covered layer; a track feeding a pin on another layer uses the inter-die switch. |
| `route/check_route.cpp` | `check_adjacent` | SOURCE->OPIN and IPIN->SINK may be up to `layer_span - 1` layers apart (needed for 4-layer CLBs). |
| `route/connection_router.cpp` | `timing_driven_route_connection_from_heap` | Target bounding box covers every layer of the sink's tile. |
| `route/route_common.cpp` | `load_net_route_bb` | Net bounding box covers every layer of its tiles. |
| `route/router_lookahead_map.cpp` | `MapLookahead::get_expected_delay_and_cong` | For a sink of a spanning tile, estimates to the layer where that sink's pins are (the current layer if one is there). **The server has an older version** (1.5). |
| `route/router_lookahead_map_utils.cpp` | `compute_router_src_opin_lookahead`, `dijkstra_flood_to_ipins` | Sample output pins on every layer of a spanning tile. |
| `route/overuse_report.cpp`, `tileable_rr_graph/rr_graph_view_util.cpp`, `util/vpr_utils.cpp` (`rr_node_arch_name`, `is_inter_cluster_node`, `get_rr_node_max_ptc`, `get_pin_rr_node_id`), `libs/librrgraph/src/base/check_rr_graph.cpp`, `libs/librrgraph/src/utils/describe_rr_node.cpp` | | `get_physical_type` -> `get_footprint_type` so upper-layer pins resolve to their tile; `get_pin_rr_node_id` looks on the pin's layer. |
| `libs/librrgraph/src/base/rr_graph_storage.cpp` | `count_rr_switches`, `remap_rr_node_switch_indices` | Signed/unsigned casts (build warnings). |
| `vpr/test/test_layer_utilization.cpp` (new), `vpr/test/test_compressed_grid.cpp` | | Utilization counts each layer once; empty layers have no compressed location. |
| Build files | `libs/EXTERNAL/libezgl/CMakeLists.txt` (+ example), `utils/route_diag/CMakeLists.txt`, `libs/EXTERNAL/libtatum/libtatum/tatum/TimingReporter.hpp`, `vtr_flow/scripts/python_libs/vtr/util.py` | CMake 3.9 -> 3.10; absolute include paths -> relative; table alignment. |
| `pack/cluster_util.cpp` (branch `layer-pass`) | `calc_init_packing_timing` | With `--pack_criticality_file FILE` (default empty: off, nothing written, packing unchanged) writes every atom connection's setup criticality from the packer's own timing analysis (driver block, sink block, criticality), for `layer_pass.py`. Option: `base/read_options.cpp/.h`, `t_packer_opts::pack_criticality_file` (`base/vpr_types.h`), `base/SetupVPR.cpp`. |

### 1.3 OpenFPGA (`openfpga-lazagna.patch`, 21 files)

Same changed lines as `patches/3d_clb/openfpga.patch` in the LaZagna branch (checked by
diffing the +/- lines). Applied to the server's `~/3d-clb/LaZagna/OpenFPGA` (its submodule
shows local changes).

| File | Struct / function | What it does |
|---|---|---|
| `fabric/module_manager.h/.cpp` | `ModuleManager::instance_layer_offset`, `set_instance_layer_offset`, member `instance_layer_offsets_` | Remembers a layer for each (parent, child, instance) module instance. |
| `fabric/build_grid_modules.cpp` | `find_pb_graph_pin_interc_layer_offset` (new), `add_module_pb_graph_pin_interc`, `rec_build_logical_tile_modules` | Labels each FLE with its `instance_layer_offsets`, and each crossbar mux, its config memory and each wire with the layer of the FLE it feeds. |
| `fpga_verilog/verilog_module_writer.cpp` | `write_verilog_instance_to_file` | Writes `(* vtr_parent_relative_layer_offset = N *)` before each labeled instance: **the label `split_clb_layers.py` cuts on.** |
| `fabric/build_top_module_connection.cpp` | `find_pin_grid_layer` (new) | Connects an upper-layer pin's routing to the tile instance on its anchor layer. |
| `fabric/build_top_module_vertical_connection.cpp` | | Connection-block nets keyed on the output channel only. |
| `utils/rr_gsb_utils.cpp` | `is_cb_mirror` | Connection blocks are only "the same" if their inter-layer channel widths match. |
| `annotation/annotate_rr_graph.cpp` | `find_interlayer_*` | Footprint lookups; ignored pins (clock) have no connection block. |
| `annotation/openfpga_annotate_routing.cpp`, `base/openfpga_pb_pin_fixup.cpp` | | Find pin nodes on the pin's layer. |
| `annotation/vpr_placement_annotation.cpp` | `VprPlacementAnnotation::init_mapped_blocks` | Sized by layer count; capacity per layer. |
| `fabric/build_3d_switch_block_module_utils.cpp`, `fabric/build_routing_module_utils.cpp`, `fabric/build_tile_modules.cpp` | | `get_footprint_type`. |
| `fpga_spice/spice_grid.cpp`, `fpga_verilog/verilog_grid.cpp`, `fabric/build_fabric_io_location_map.cpp`, `repack/lb_router.cpp`, `tile_direct/build_tile_direct.cpp`, `utils/check_tile_annotation.cpp`, `utils/openfpga_physical_tile_utils.cpp` | | `.c_str()` on `std::string` names passed to printf-style calls (build fixes). |

### 1.4 The patch files

`git apply --cached` of these onto `5abd3acaa` in a scratch index, then `git diff`
against `HEAD`:

| Patch | Files | Contents |
|---|---:|---|
| `vtr-3d-clb.patch` | 47 | Core multi-layer CLB support (1.1, most of 1.2). |
| `vpr-direct-layers.patch` | 6 | `layer_offset` / `placement_macro` directs, delta sampling skip, `delay_model.txt` try/catch. |
| `vpr-multilayer-check.patch` | 1 | `check_route.cpp` `max_layer_step`. |
| `vpr-placer-layers.patch` | 3 | Auto delta model (`SetupVPR.cpp`, `vpr_types.h`, `timing_place_lookup.cpp`). |
| `lazagna-vtr-fixes.patch` | 5 | Build fixes only (used by `apply_and_run.sh` when the 3D patch is not applied). |

The first four together reproduce this repo's VPR **except `router_lookahead_map.cpp`**:
the patch has the older lookahead (any covered layer counts as the target layer); the
repository has the pin-layer version.

### 1.5 Which VPR produced which results

| Change | This repository | VPR used for the server sweeps | LaZagna patch (`patches/3d_clb/vtr.patch`) |
|---|---|---|---|
| `max_layer_step` route check | yes | yes | yes |
| `placement_macro` directs | yes | yes | yes |
| Auto delta placement model (`delay_model_inferred`) | yes | **no** | **no** |
| Pin-layer sink lookahead | yes | **no** (older version) | **no** (older version) |
| `vtr/util.py` table fix | yes | not checked | no |

So every sweep run on the server used VPR's **simple** placement delay model unless its script passes
`--place_delay_model delta` (only `run_links.sh`, `run_links2.sh`, `run_best.sh`,
`run_big4.sh`, `run_sparse.sh` do). `run_ceilings.sh`, `run_baselines.sh`, `run_seeds.sh`,
`run_ownlayer.sh`, `run_process.sh`, `run_switchblocks.sh` and `run_sizes.sh` ran with
the simple model. The Koios runs (`hardblocks/results/`) used this repository's VPR.

### 1.6 LaZagna (`lazagna-3d-clb-branch.patch`)

| File | What it does |
|---|---|
| `lazagna/clb_3d.py` | `crossbar_names`, `annotate_layer_crossbars` (gives every per-layer crossbar the mux type OpenFPGA's settings give `crossbar`, in the job's own copy), `split_task` (runs `split_clb_layers.py` on a finished job into `<task>/clb_layers`). |
| `lazagna/split_clb_layers.py` | Identical to this folder's `split_clb_layers.py` (diffed). |
| `lazagna/run_interface.py` | `run_one_benchmark` gets `clb_split_arch`; calls the two `clb_3d` hooks. |
| `lazagna/yaml_file_processing_v2.py` | `params["split_clb_layers"]` from `clb_3d.split_layers` in the setup YAML. |
| `lazagna/main.py` | 1 line. |
| `arch_files/3d_clb/vtr_3d_clb_arch.xml`, `vtr_3d_clb_local20_arch.xml` | 10-LUT split (5+5) and 20-LUT layer-local split (10+10). |
| `setup_files/3d_clb_split.yaml`, `3d_clb_local20_split.yaml` | Setups using them, `clb_3d: split_layers: true`. |
| `patches/3d_clb/vtr.patch`, `openfpga.patch`; `scripts/apply_3d_clb.sh` | The tool patches and a script that applies them (skipping applied ones) and rebuilds. |
| `docs/3d_clb.md` | How to use it. |

## 2. Script pipeline

### 2.1 Architecture to RTL to one module per layer

1. **Architecture**: `vtr_3d_clb_arch.xml` (10-LUT split) is the base. `compare_2d_3d.py`
   functions rewrite it: `resize_clb(xml, n)` (N FLEs, 4N inputs, `pin_layer`),
   `local_inputs` (each layer's FLEs read only that layer's pins), `own_layer_inputs`
   (input pins reach only their own layer's tracks), `stack_clbs`, `stretch_wires`.
2. **LaZagna** (`python3 lazagna/main.py -f setup_files/<name>.yaml -v`) runs VPR and
   OpenFPGA; RTL lands in `tasks_run/<experiment>/task_*/task/run001/verilog/SRC`.
   With layer-local crossbars, `task/designs/openfpga_arch.xml` must map `crossbar0`/
   `crossbar1` to `mux_2level` (`pnr/run_local.sh` and `pnr/run_tile.sh` do this with
   `sed` and restore the file; the LaZagna branch does it per job in `clb_3d.py`).
3. **`split_clb_layers.py --source SRC --arch ARCH --output DIR`** reads the
   `vtr_parent_relative_layer_offset` labels and pin layers and writes:
   `clb_split.v` (same module name and ports as `logical_tile_clb_mode_clb_`, with
   `clb_layer0`, `clb_layer1`), `clb_crossings.csv` (`signal,bit,type,from_layer,to_layer`)
   and `instance_layers.csv` (`instance,module,layer`). Stops if a child has no label.

### 2.2 Layout and timing (`pnr/`, SiliconJackets sky130 flow on the server)

`pnr/run_local.sh` (FLES, CORE, default `CORE=312`) does 2.1 for the layer-local CLB, then
calls `pnr/run_bond.sh` (FLES, CENTER_PADS, PERIOD default 2 ns, CORE default 354):

1. `add_crossing_buffers.py clb_split.v clb_crossings.csv OUT [--direct]` - a driver and receiver on each crossing; with `--direct` (`run_bond.sh DIRECT=1`) one `crossing_driver` on the sending layer and none on the other.
2. `make_pnr_rtl.py --top clb_layer{0,1}` - one synthesizable file per layer (drops `TGATE`, maps `crossing_buffer` to `BUFX4` and `crossing_driver` to `BUFX16`, strips simulation-only code).
3. `setup_pnr.py --period --core [--center-pads] [--bond-load --bond-driver --keep-crossing-drivers]` - a copy of the SiliconJackets flow per layer, with bond pads (`bond_pads`); `DIRECT=1` passes a 1 pF bond load, a BUFX16 driving cell, and dont_touch on the BUFX16 cells in synthesis and in Innovus (`KEEP_DRIVERS_APR`). Opt-in, for the crossing study: `--bond-loads CSV` (`run_bond.sh BOND_LOADS`; one `set_load` per bond output port), `--keep-crossing-nets clb_crossings.csv` (`KEEP_NETS=1`; dont_touch on the crossing nets before placement, so Innovus inserts no buffers on them), `--bond-delays IN OUT` (`BOND_DELAYS`; input and output delay on the bond ports instead of 0).
4. `run_block.csh` - synthesis and place and route; `run_innovus.csh ... export_layout.tcl` - routed netlist, SPEF, SDF.
5. `join_netlist.py` - both layers' routed netlists into `join3d/joined.v` (+ `top.spef`).
6. `run_tempus.csh ... join_timing.tcl` (env `PNR_LAYERS=2`, `PNR_FLES`, `PNR_NETLIST`, `PNR_SPEF`) - times every CLB-input and feedback path through the crossbar, writes `clb_paths.csv` (last column `mux_in`: arrival at the crossbar mux's first pin; older files lack it). `PNR_CROSSING_PATH=1` (set by `run_bond.sh`) also writes `crossing_path.txt`, FLE 0 to layer 1 mux 15 input 2.
7. `compare_joined.py joined.csv flat.csv [FLES]` - path-by-path against the 2D CLB (`pnr_fast/join2d/clb_paths.csv`).

Other `pnr/` scripts: `run_pnr.sh` (first per-layer crossbar timing at a clock neither
meets; `report_paths.tcl` -> `crossbar_paths.csv`; `compare_paths.py`), `route_saved.tcl`,
`run_tile.sh` (switch and connection blocks of one tile: `tile_blocks.py` picks the
modules, then `make_pnr_rtl.py`/`setup_pnr.py`/`run_block.csh` per module; env WIDTH,
SPAN4, SPAN16, FLES, LOCAL, OWN, STACKED, WIDTH2D), `tile_area.py` (adds CLB and routing
into a tile), `report_block_power.tcl`, and `asap7/` (`run_asap7.sh`, `synth.tcl`,
`pnr.tcl`, `mmmc.tcl`, `make_db.tcl`, `join_asap7.sh`) for the ASAP7 repeat.

In-CLB crossing study (`crossing_stages_results.txt`): `bond_net_loads.py` (what each bond output
port drives on the other layer, from SPEF, routed netlist and liberty), `run_crossing_fix.sh`
(`pnr_local20c` again with one change: RUNS `s` real bond loads, `t` also no inserted buffers on
crossing nets, `u` real loads and bond-port timing budgets), `retime_joined.sh` (finished layouts
timed again with the current `join_timing.tcl`), `crossing_stages_layout.py` (the stage tables).
The SPICE side is `../spice/crossing_stages.py` (`run_crossing_stages.sh`): make_spice.py's
feedback deck with a measure per stage, moved one change at a time toward the layout's worst
crossing path, with the kit's standard cells read from its CDL.

### 2.3 Hardware checks (`ff_test/`)

1. `make_ff_design.py [--count]` - a test design: 10 LUTs, outputs `q0`-`q7` registered and `c8`, `c9` combinational (`OUTPUTS` in `run_ff_test.py`), BLIF plus a reference Verilog model.
2. `run_ff_test.py` - VPR with routed clocks, OpenFPGA, `split_clb_layers.py`, optionally `add_crossing_buffers.py` (`--crossing-buffers`), `--relayer` (`relayer_net.py`), `--synth-cells`; Icarus simulation of 1,000 cycles per case with one crossing held at 0 per case, then 5,000 cycles. Branch `layer-pass` adds `--fles 20 --local --own-layer` (the sweeps' split CLB: 20 FLEs, one crossbar per layer, own-layer input pins; pads then reach both layers) and `--layer-pass [--pass-args=--control]` (packs with `--pack_criticality_file`, runs `layer_pass.py`, places and routes the rewritten `.net` inside OpenFPGA, and checks that the routed packing is the rewritten one); cuts then come from `clb_crossings.csv`. `--plant-fault net` (an FLE input moved to another FLE's output; VPR's netlist reader refuses it) and `--plant-fault lut:NAME` (one truth-table row dropped from the implemented netlist, not the reference) must fail. `--vpr`, `--openfpga` name the binaries. Results: `hardblocks/results/seeds10/layerpass/hwcheck/`.
3. `run_clb_equiv.py [--fles N --local] --package DIR` - builds the design, splits the CLB and adds crossing drivers, gets the real config bits (`clb_chain.py` follows the scan chain from `ccff_head`), and writes a package: testbench from `clb_equiv_tb.v` (shifts the config in twice, then random inputs, compares with the original CLB every cycle), cases from `clb_crossings.csv` (`cut_cases`). Rules: no cut must pass; every config-chain cut must fail; at least one used logic crossing must fail.
4. `run_equiv_gate.csh PKG LAYOUT BLOCK PERIOD SDF|NONE CUT` (server, tcsh) - the same check on routed gates (`rename_netlist.py` renames each netlist), with or without SDF delays. Chain length from `wc -l < clb_config.txt`.

`ff_test/clb_config_ff_ten.txt` is a 1,630-line file of 0/1 bits (the 10-LUT CLB's chain).

### 2.4 Speed sweeps

1. `synth_bench.sh OUT bench...` - Yosys/ABC, 6-LUT BLIFs of the bigger VTR designs (server copy in `/tmp/$USER/ceil/bench`). Small set: VTR's MCNC `vtr_flow/benchmarks/blif/6`.
2. `compare_2d_3d.py` - writes each fabric's architecture (`make_arch` and the functions in 2.1, plus `add_layers`, `custom_switchblocks` from `switchblocks.xml`, `add_links`, `sparse_crossbars`, `split_inputs`, `set_span`, `scale_crossbar`), runs VPR per design and seed (cached by architecture text), writes `<output>/results.csv` with columns `fabric,fles,chan_width,wire_scale,crossing_ps,bench,luts,grid,seed,routed,cpd_ns,wirelength` (`result_row`). Older files lack `fles` (all 10).
3. `run_*.sh` - each run copies `results.csv` to `$OUT/${set}_${name}.csv` on the server; those were copied into this folder as `compare_results_<group>_<set>_<name>.csv`, where the group roughly follows the output folder (`ceil`, `sb` for `ceil_sb`, `links`, `proc_kK`, `best`, `big4`, `sparse`). Table 3.1 gives the script for each file.
4. `compare_configs.py BASE:FABRIC LABEL=FILE:FABRIC...` - ratios across files on shared seeds and designs; `ledger.py` - section 3's table.
5. `cluster_size_model.py` - area/delay **estimates** (calibrated on the synthesized 10-LUT CLB) that set `--w3d`, `--wire-spans` and `--crossbar-scale`; not results.
6. `layer_pass.py NET CRITICALITY ARCH` (branch `layer-pass`) - post-pack pass for split CLBs: moves FLEs between the CLB's two layers (10 slots and 40 input pins per layer kept) to cut timing-weighted crossings, weights from `--pack_criticality_file`, crossing delays from the arch, and rewrites the `.net`. Run by `compare_2d_3d.py --layer-pass` (pack, pass, then place and route; off by default) with `--widths CSV` to reuse each pass-off run's track count. Sweep and tables: `hardblocks/results/seeds10/layerpass/` (`run_layerpass.sh` with `SETS` and `CONTROL=1 CK=`; `run_failed.sh`: failed runs rerun at 200 router iterations, `iter200/`, `layerpass_table.py --fill`; `run_newdesigns.sh` and `newdesigns_table.py`: Koios designs outside the 7, picked by `newdesigns_rule.txt`; `run_newdesigns_e.sh` and `tendesigns_table.py`: those 3 designs at every other setting, so every table has all 10; `run_bigtrial.sh`: the lstm and dla_like.small trial, `newdesigns/bigtrial.txt`). When `compare_2d_3d.py` reuses a finished run, a log that says "Routing failed" now counts as failed: with `--analysis` (`--layer-pass`, `--relayer`) VPR prints a critical path delay even after a failed route, which the reuse used to record as routed (found 2026-11-17; it hit only a rerun of experiment C, fixed before its results).

## 3. Data ledger

### 3.1 Which script made which sweep file

| Files (`compare_results_` + ...) | Made by |
|---|---|
| `.csv`, `relayer.csv` | `compare_2d_3d.py` 10-LUT split, 2 wire scales x 3 crossings, W50; `--relayer` |
| `geometry.csv`, `geometry_relayer.csv` | tile-span model, W70 |
| `tile_l5.csv`, `tile_l6.csv` | 3D tile sized from laid-out routing (W74) |
| `crossbar_measured.csv`, `crossbar_careful.csv` | measured crossbar delays |
| `bonded.csv`, `no_clb_crossing.csv` | bonded 10-LUT layout delays |
| `local_inputs.csv`, `local_both.csv`, `local_tile.csv`, `stacked.csv`, `stacked_tile.csv` | layer-local crossbar and stacked CLBs (10-LUT) |
| `small_n10.csv`, `big_split80.csv`, `big_stacked.csv` | bigger designs, 10-LUT |
| `{big,small}_n20_{local,full}.csv`, `big_n20_pessimistic.csv` | 20-LUT estimates (2D rows are a **20-LUT** 2D CLB, W140) |
| `{big,small}_n20_{measured,center}.csv` | 20-LUT with laid-out delays (2D rows 20-LUT, W140) |
| `ceil_*_{measured,free_clb,free_all,stacked,stacked10,measured45,stacked45}.csv` | `run_ceilings.sh` |
| `ceil_*_{n24,n30}.csv` | `run_sizes.sh` |
| `ceil_*_{n2d8,n2d12}.csv` | `run_baselines.sh` |
| `ceil_*_seeds_{split,stacked,n2d8,n2d12}.csv` | `run_seeds.sh` (10 seeds) |
| `{big,small}_relax_{split,stacked,n2d8,n2d12}.csv` | `run_seeds.sh` with `RELAX=1.3 TAG=relax SEEDS="1 2 3"` |
| `ceil_*_ownlayer.csv` | `run_ownlayer.sh` (10 seeds) |
| `proc_k{1.5,2,3}_*_{split,n2d12}.csv` | `run_process.sh` |
| `sb_*.csv` | `run_switchblocks.sh` |
| `links_*_{w_*,c_*}.csv` | `run_links.sh`, `run_links2.sh` (delta model) |
| `links_*_w10_split_hlink.csv` | `run_best.sh` part 1 (10 seeds, delta) |
| `best_*_{all45,all10}.csv` | `run_best.sh` part 2 (delta) |
| `big4_*_f40x4.csv` | `run_big4.sh` (delta) |
| `sparse_*_{ref,s20}.csv` | `run_sparse.sh` (delta); its `s30`, `s40x4`, `s60x4` runs are not in the repo |### 3.2 Every sweep file (generated by `python3 ledger.py`)

N = LUTs per CLB, W = tracks per channel (a range for `--relax-w` runs), cross = layer
crossing cost. The last column compares the file's own 3D rows with its own 2D rows,
which are not always the 10-LUT 2D CLB: read N.

| File | Rows | Designs | Seeds | Contents per fabric | 3D/2D in file |
|---|---:|---:|---|---|---|
| `compare_results.csv` | 336 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=50, scale=0.85/1.0, cross=10.0/138.5/50.0 ps, 288/288 routed | scale 0.85, cross 10.0: 0.924 (16/16 faster); scale 0.85, cross 138.5: 1.021 (4/16 faster); scale 0.85, cross 50.0: 0.967 (11/16 faster); scale 1.0, cross 10.0: 1.008 (6/16 faster); scale 1.0, cross 138.5: 1.114 (0/16 faster); scale 1.0, cross 50.0: 1.041 (3/16 faster) |
| `compare_results_best_big_all10.csv` | 42 | 7 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=10.0 ps, 21/21 routed | 0.950 (5/7 faster) |
| `compare_results_best_big_all45.csv` | 42 | 7 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.986 (5/7 faster) |
| `compare_results_best_small_all10.csv` | 96 | 16 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=10.0 ps, 48/48 routed | 0.958 (13/16 faster) |
| `compare_results_best_small_all45.csv` | 96 | 16 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.981 (12/16 faster) |
| `compare_results_big4_big_f40x4.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=40, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.917 (7/7 faster) |
| `compare_results_big4_small_f40x4.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=40, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.964 (11/16 faster) |
| `compare_results_big_n20_center.csv` | 42 | 7 | 1,2,3 | 2d: N=20, W=140, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=73.0 ps, 21/21 routed | 0.943 (6/7 faster) |
| `compare_results_big_n20_full.csv` | 42 | 7 | 1,2,3 | 2d: N=20, W=140, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=73.0 ps, 21/21 routed | 0.960 (7/7 faster) |
| `compare_results_big_n20_local.csv` | 42 | 7 | 1,2,3 | 2d: N=20, W=140, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=73.0 ps, 21/21 routed | 0.926 (7/7 faster) |
| `compare_results_big_n20_measured.csv` | 42 | 7 | 1,2,3 | 2d: N=20, W=140, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=73.0 ps, 21/21 routed | 0.943 (6/7 faster) |
| `compare_results_big_n20_pessimistic.csv` | 42 | 7 | 1,2,3 | 2d: N=20, W=140, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=73.0 ps, 21/21 routed | 0.984 (5/7 faster) |
| `compare_results_big_relax_n2d12.csv` | 42 | 7 | 1,2,3 | 2d: N=12, W=64-104, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=58-76, scale=1.0, cross=45.0 ps, 21/21 routed | 0.967 (6/7 faster) |
| `compare_results_big_relax_n2d8.csv` | 42 | 7 | 1,2,3 | 2d: N=8, W=60-100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=58-76, scale=1.0, cross=45.0 ps, 21/21 routed | 0.947 (6/7 faster) |
| `compare_results_big_relax_split.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=60-100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=58-76, scale=1.0, cross=45.0 ps, 21/21 routed | 0.942 (6/7 faster) |
| `compare_results_big_relax_stacked.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=60-100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=10, W=52-82, scale=1.041, cross=45.0 ps, 20/21 routed | 0.969 (5/7 faster) |
| `compare_results_big_split80.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=10, W=80, scale=1.0, cross=73.0 ps, 21/21 routed | 1.000 (2/7 faster) |
| `compare_results_big_stacked.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=10, W=100, scale=1.041, cross=73.0 ps, 21/21 routed | 0.987 (5/7 faster) |
| `compare_results_bonded.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=70, scale=1.0, cross=73.0 ps, 48/48 routed | 0.984 (11/16 faster) |
| `compare_results_ceil_big_free_all.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=10.0 ps, 21/21 routed | 0.917 (5/7 faster) |
| `compare_results_ceil_big_free_clb.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=73.0 ps, 21/21 routed | 0.945 (6/7 faster) |
| `compare_results_ceil_big_measured.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=73.0 ps, 21/21 routed | 0.949 (5/7 faster) |
| `compare_results_ceil_big_measured45.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.924 (6/7 faster) |
| `compare_results_ceil_big_n24.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=24, W=104, scale=1.0, cross=73.0 ps, 21/21 routed | 0.956 (4/7 faster) |
| `compare_results_ceil_big_n2d12.csv` | 42 | 7 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.954 (4/7 faster) |
| `compare_results_ceil_big_n2d8.csv` | 42 | 7 | 1,2,3 | 2d: N=8, W=90, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.942 (5/7 faster) |
| `compare_results_ceil_big_n30.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=30, W=116, scale=1.0, cross=73.0 ps, 21/21 routed | 0.963 (4/7 faster) |
| `compare_results_ceil_big_ownlayer.csv` | 140 | 7 | 1,2,3,4,5,6,7,8,9,10 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 70/70 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 70/70 routed | 0.938 (6/7 faster) |
| `compare_results_ceil_big_seeds_n2d12.csv` | 140 | 7 | 1,2,3,4,5,6,7,8,9,10 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 70/70 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 70/70 routed | 0.948 (7/7 faster) |
| `compare_results_ceil_big_seeds_n2d8.csv` | 140 | 7 | 1,2,3,4,5,6,7,8,9,10 | 2d: N=8, W=90, scale=1.0, cross=0.0 ps, 70/70 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 70/70 routed | 0.938 (6/7 faster) |
| `compare_results_ceil_big_seeds_split.csv` | 140 | 7 | 1,2,3,4,5,6,7,8,9,10 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 70/70 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 70/70 routed | 0.926 (6/7 faster) |
| `compare_results_ceil_big_seeds_stacked.csv` | 140 | 7 | 1,2,3,4,5,6,7,8,9,10 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 70/70 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 70/70 routed | 0.969 (6/7 faster) |
| `compare_results_ceil_big_stacked.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=10, W=100, scale=1.041, cross=73.0 ps, 21/21 routed | 0.978 (6/7 faster) |
| `compare_results_ceil_big_stacked10.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=10, W=100, scale=1.041, cross=10.0 ps, 21/21 routed | 0.970 (5/7 faster) |
| `compare_results_ceil_big_stacked45.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 21/21 routed | 0.962 (6/7 faster) |
| `compare_results_ceil_small_free_all.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=10.0 ps, 48/48 routed | 0.919 (15/16 faster) |
| `compare_results_ceil_small_free_clb.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=73.0 ps, 48/48 routed | 0.954 (13/16 faster) |
| `compare_results_ceil_small_measured.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=73.0 ps, 48/48 routed | 0.961 (12/16 faster) |
| `compare_results_ceil_small_measured45.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.937 (13/16 faster) |
| `compare_results_ceil_small_n24.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=24, W=104, scale=1.0, cross=73.0 ps, 48/48 routed | 1.014 (8/16 faster) |
| `compare_results_ceil_small_n2d12.csv` | 96 | 16 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.961 (14/16 faster) |
| `compare_results_ceil_small_n2d8.csv` | 96 | 16 | 1,2,3 | 2d: N=8, W=90, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.959 (11/16 faster) |
| `compare_results_ceil_small_n30.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=30, W=116, scale=1.0, cross=73.0 ps, 48/48 routed | 1.004 (11/16 faster) |
| `compare_results_ceil_small_ownlayer.csv` | 320 | 16 | 1,2,3,4,5,6,7,8,9,10 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 160/160 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 160/160 routed | 0.943 (14/16 faster) |
| `compare_results_ceil_small_seeds_n2d12.csv` | 320 | 16 | 1,2,3,4,5,6,7,8,9,10 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 160/160 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 160/160 routed | 0.970 (12/16 faster) |
| `compare_results_ceil_small_seeds_n2d8.csv` | 320 | 16 | 1,2,3,4,5,6,7,8,9,10 | 2d: N=8, W=90, scale=1.0, cross=0.0 ps, 160/160 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 160/160 routed | 0.962 (12/16 faster) |
| `compare_results_ceil_small_seeds_split.csv` | 320 | 16 | 1,2,3,4,5,6,7,8,9,10 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 160/160 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 160/160 routed | 0.943 (13/16 faster) |
| `compare_results_ceil_small_seeds_stacked.csv` | 320 | 16 | 1,2,3,4,5,6,7,8,9,10 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 160/160 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 160/160 routed | 0.959 (13/16 faster) |
| `compare_results_ceil_small_stacked.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=100, scale=1.041, cross=73.0 ps, 48/48 routed | 0.967 (11/16 faster) |
| `compare_results_ceil_small_stacked10.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=100, scale=1.041, cross=10.0 ps, 48/48 routed | 0.944 (16/16 faster) |
| `compare_results_ceil_small_stacked45.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 48/48 routed | 0.958 (14/16 faster) |
| `compare_results_crossbar_careful.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=70, scale=1.0, cross=73.0 ps, 48/48 routed | 1.005 (8/16 faster) |
| `compare_results_crossbar_measured.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=70, scale=1.0, cross=73.0 ps, 48/48 routed | 0.997 (9/16 faster) |
| `compare_results_geometry.csv` | 144 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=70, scale=1.0, cross=137.3/73.0 ps, 96/96 routed | scale 1.0, cross 137.3: 1.078 (0/16 faster); scale 1.0, cross 73.0: 1.010 (9/16 faster) |
| `compare_results_geometry_relayer.csv` | 144 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=70, scale=1.0, cross=137.3/73.0 ps, 96/96 routed | scale 1.0, cross 137.3: 1.045 (3/16 faster); scale 1.0, cross 73.0: 1.015 (7/16 faster) |
| `compare_results_links_big_c_2d10_link.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.960 (5/7 faster) |
| `compare_results_links_big_c_split2.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.941 (6/7 faster) |
| `compare_results_links_big_c_split4.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.925 (7/7 faster) |
| `compare_results_links_big_c_split4_link.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.928 (6/7 faster) |
| `compare_results_links_big_w10_split_hlink.csv` | 140 | 7 | 1,2,3,4,5,6,7,8,9,10 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 70/70 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 70/70 routed | 0.971 (5/7 faster) |
| `compare_results_links_big_w_2d10_link.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 21/21 routed | 0.995 (4/7 faster) |
| `compare_results_links_big_w_2d12.csv` | 42 | 7 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 21/21 routed | 0.980 (4/7 faster) |
| `compare_results_links_big_w_2d12_link.csv` | 42 | 7 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 21/21 routed | 1.015 (3/7 faster) |
| `compare_results_links_big_w_split.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.921 (6/7 faster) |
| `compare_results_links_big_w_split_hlink.csv` | 42 | 7 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.961 (7/7 faster) |
| `compare_results_links_big_w_split_hlink196.csv` | 42 | 7 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.975 (6/7 faster) |
| `compare_results_links_big_w_stacked.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 21/21 routed | 0.966 (6/7 faster) |
| `compare_results_links_big_w_stacked_link.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 21/21 routed | 0.951 (7/7 faster) |
| `compare_results_links_small_c_2d10_link.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.975 (10/16 faster) |
| `compare_results_links_small_c_split2.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.941 (14/16 faster) |
| `compare_results_links_small_c_split4.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.957 (12/16 faster) |
| `compare_results_links_small_c_split4_link.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.954 (12/16 faster) |
| `compare_results_links_small_w10_split_hlink.csv` | 320 | 16 | 1,2,3,4,5,6,7,8,9,10 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 160/160 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 160/160 routed | 0.978 (12/16 faster) |
| `compare_results_links_small_w_2d10_link.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 48/48 routed | 0.976 (11/16 faster) |
| `compare_results_links_small_w_2d12.csv` | 96 | 16 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 48/48 routed | 0.981 (9/16 faster) |
| `compare_results_links_small_w_2d12_link.csv` | 96 | 16 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 48/48 routed | 1.000 (9/16 faster) |
| `compare_results_links_small_w_split.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.950 (13/16 faster) |
| `compare_results_links_small_w_split_hlink.csv` | 96 | 16 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.971 (11/16 faster) |
| `compare_results_links_small_w_split_hlink196.csv` | 96 | 16 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.963 (14/16 faster) |
| `compare_results_links_small_w_stacked.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 48/48 routed | 0.971 (13/16 faster) |
| `compare_results_links_small_w_stacked_link.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 48/48 routed | 0.963 (14/16 faster) |
| `compare_results_local_both.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=66, scale=1.0, cross=73.0 ps, 48/48 routed | 0.990 (7/16 faster) |
| `compare_results_local_inputs.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=70, scale=1.0, cross=73.0 ps, 48/48 routed | 1.011 (4/16 faster) |
| `compare_results_local_tile.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=66, scale=1.0, cross=73.0 ps, 48/48 routed | 1.009 (6/16 faster) |
| `compare_results_no_clb_crossing.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=70, scale=1.0, cross=73.0 ps, 48/48 routed | 0.966 (13/16 faster) |
| `compare_results_proc_k1.5_big_n2d12.csv` | 42 | 7 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.950 (5/7 faster) |
| `compare_results_proc_k1.5_big_split.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.919 (5/7 faster) |
| `compare_results_proc_k1.5_small_n2d12.csv` | 96 | 16 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.955 (13/16 faster) |
| `compare_results_proc_k1.5_small_split.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.939 (13/16 faster) |
| `compare_results_proc_k2_big_n2d12.csv` | 42 | 7 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.954 (6/7 faster) |
| `compare_results_proc_k2_big_split.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.917 (6/7 faster) |
| `compare_results_proc_k2_small_n2d12.csv` | 96 | 16 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.956 (12/16 faster) |
| `compare_results_proc_k2_small_split.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.928 (13/16 faster) |
| `compare_results_proc_k3_big_n2d12.csv` | 42 | 7 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.904 (7/7 faster) |
| `compare_results_proc_k3_big_split.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.892 (7/7 faster) |
| `compare_results_proc_k3_small_n2d12.csv` | 96 | 16 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.950 (13/16 faster) |
| `compare_results_proc_k3_small_split.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.923 (14/16 faster) |
| `compare_results_relayer.csv` | 336 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=50, scale=0.85/1.0, cross=10.0/138.5/50.0 ps, 288/288 routed | scale 0.85, cross 10.0: 0.944 (15/16 faster); scale 0.85, cross 138.5: 1.020 (6/16 faster); scale 0.85, cross 50.0: 0.961 (16/16 faster); scale 1.0, cross 10.0: 1.027 (3/16 faster); scale 1.0, cross 138.5: 1.086 (0/16 faster); scale 1.0, cross 50.0: 1.043 (4/16 faster) |
| `compare_results_sb_big_split4_dense.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.971 (4/7 faster) |
| `compare_results_sb_big_split_dense.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.941 (7/7 faster) |
| `compare_results_sb_big_split_planar.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.955 (5/7 faster) |
| `compare_results_sb_big_split_sparse.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.964 (4/7 faster) |
| `compare_results_sb_big_stacked4_dense.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 21/21 routed | 0.971 (5/7 faster) |
| `compare_results_sb_big_stacked_dense.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 21/21 routed | 0.986 (4/7 faster) |
| `compare_results_sb_small_split4_dense.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.957 (13/16 faster) |
| `compare_results_sb_small_split_dense.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.946 (14/16 faster) |
| `compare_results_sb_small_split_planar.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.957 (11/16 faster) |
| `compare_results_sb_small_split_sparse.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.953 (12/16 faster) |
| `compare_results_sb_small_stacked4_dense.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 48/48 routed | 0.946 (13/16 faster) |
| `compare_results_sb_small_stacked_dense.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=100, scale=1.041, cross=45.0 ps, 48/48 routed | 0.959 (13/16 faster) |
| `compare_results_small_n10.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=80, scale=1.0, cross=73.0 ps, 48/48 routed | 0.983 (10/16 faster) |
| `compare_results_small_n20_center.csv` | 96 | 16 | 1,2,3 | 2d: N=20, W=140, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=73.0 ps, 48/48 routed | 0.947 (15/16 faster) |
| `compare_results_small_n20_full.csv` | 96 | 16 | 1,2,3 | 2d: N=20, W=140, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=73.0 ps, 48/48 routed | 0.955 (16/16 faster) |
| `compare_results_small_n20_local.csv` | 96 | 16 | 1,2,3 | 2d: N=20, W=140, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=73.0 ps, 48/48 routed | 0.940 (16/16 faster) |
| `compare_results_small_n20_measured.csv` | 96 | 16 | 1,2,3 | 2d: N=20, W=140, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=73.0 ps, 48/48 routed | 0.955 (15/16 faster) |
| `compare_results_small_relax_n2d12.csv` | 96 | 16 | 1,2,3 | 2d: N=12, W=40-104, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=32-78, scale=1.0, cross=45.0 ps, 44/48 routed | 0.967 (12/16 faster) |
| `compare_results_small_relax_n2d8.csv` | 96 | 16 | 1,2,3 | 2d: N=8, W=42-100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=32-78, scale=1.0, cross=45.0 ps, 44/48 routed | 0.959 (12/16 faster) |
| `compare_results_small_relax_split.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=40-100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=32-78, scale=1.0, cross=45.0 ps, 44/48 routed | 0.937 (13/16 faster) |
| `compare_results_small_relax_stacked.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=40-100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=32-82, scale=1.041, cross=45.0 ps, 44/48 routed | 0.960 (12/16 faster) |
| `compare_results_sparse_big_ref.csv` | 42 | 7 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 21/21 routed | 0.941 (6/7 faster) |
| `compare_results_sparse_big_s20.csv` | 42 | 7 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 21/21 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 15/21 routed | 1.106 (1/5 faster) |
| `compare_results_sparse_small_ref.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 0.941 (14/16 faster) |
| `compare_results_sparse_small_s20.csv` | 96 | 16 | 1,2,3 | 2d: N=12, W=110, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=20, W=100, scale=1.0, cross=45.0 ps, 48/48 routed | 1.071 (0/16 faster) |
| `compare_results_stacked.csv` | 144 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=100, scale=1.0, cross=137.3/73.0 ps, 96/96 routed | scale 1.0, cross 137.3: 0.966 (13/16 faster); scale 1.0, cross 73.0: 0.951 (15/16 faster) |
| `compare_results_stacked_tile.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=100, scale=1.041, cross=73.0 ps, 48/48 routed | 0.967 (14/16 faster) |
| `compare_results_tile_l5.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=74, scale=1.0, cross=73.0 ps, 48/48 routed | 0.992 (9/16 faster) |
| `compare_results_tile_l6.csv` | 96 | 16 | 1,2,3 | 2d: N=10, W=100, scale=1.0, cross=0.0 ps, 48/48 routed; 3d: N=10, W=74, scale=1.0, cross=73.0 ps, 48/48 routed | 0.993 (9/16 faster) |

### 3.3 Headline comparisons across files (recomputed with `compare_configs.py`)

Command form: `python3 compare_configs.py BASE.csv:2d "LABEL=FILE.csv:3d"`. Ratio < 1 = faster.

| Candidate | Baseline | Bigger 7 | Faster on | Per-seed range | Small 16 | Faster on | Per-seed range |
|---|---|---:|---:|---|---:|---:|---|
| 20-LUT split, `ceil_*_seeds_split.csv:3d` (10 seeds) | 12-LUT 2D, `ceil_*_seeds_n2d12.csv:2d` | 0.948 | 7/7 | 0.933-0.968 | 0.970 | 12/16 | 0.951-0.986 |
| same | 10-LUT 2D, `ceil_*_seeds_split.csv:2d` | 0.926 | 6/7 | | 0.943 | 13/16 | |
| same | stacked 10-LUT, `ceil_*_seeds_stacked.csv:3d` | 0.956 | 6/7 | 0.938-0.978 | 0.984 | 10/16 | 0.969-0.994 |
| own-layer inputs, `ceil_*_ownlayer.csv:3d` (10 seeds) | 12-LUT 2D (10 seeds) | 0.961 | 7/7 | 0.933-1.000 | 0.969 | 13/16 | 0.955-0.994 |
| split + links, `links_*_w10_split_hlink.csv:3d` (10 seeds, delta) | 12-LUT 2D + links, same file `:2d` | 0.971 | 5/7 | 0.937-1.000 | 0.978 | 12/16 | 0.964-0.996 |
| 40-LUT, 4 layers, `big4_*_f40x4.csv:3d` (3 seeds, delta) | 12-LUT 2D, `sparse_*_s20.csv:2d` (delta, custom SB) | 0.955 | 5/7 | 0.946-0.966 | 0.991 | 10/16 | 0.978-1.008 |
| split, routing x1.5, `proc_k1.5_*_split.csv:3d` | `proc_k1.5_*_n2d12.csv:2d` | 0.950 | 5/7 | | 0.955 | 13/16 | |
| split, routing x2 | `proc_k2_*_n2d12.csv:2d` | 0.954 | 6/7 | | 0.956 | 12/16 | |
| split, routing x3 | `proc_k3_*_n2d12.csv:2d` | 0.904 | 7/7 | | 0.950 | 13/16 | |
| split, tracks 1.3 x own minimum, `*_relax_split.csv:3d` | `*_relax_n2d12.csv:2d` | 0.967 | 6/7 | | 0.957 | 10/13 (4 3D runs failed) | |
| 20-LUT split, laid-out delays, pads mid-core, `*_n20_center.csv:3d` | 10-LUT 2D (`big_split80.csv:2d`, `small_n10.csv:2d`) | 0.960 | 6/7 | 0.952-0.967 | 0.965 | 11/16 | 0.963-0.966 |
| everything, 45 ps (`best_*_all45.csv`, in file) | 12-LUT 2D + links | 0.986 | 5/7 | | 0.981 | 12/16 | |
| everything, 10 ps (`best_*_all10.csv`, in file) | 12-LUT 2D + links | 0.950 | 5/7 | | 0.958 | 13/16 | |
| sparse 20-LUT split (`sparse_*_s20.csv`, in file) | 12-LUT 2D, full crossbar | 1.106 | 1/5 (6 3D runs failed) | | 1.071 | 0/16 | |

Minimum tracks (`compare_configs.py --column chan_width`: routed width at 1.3 x each run's
minimum, averaged over 3 seeds per design, over the 10-LUT 2D's, geometric mean over designs
that routed every seed; from `*_relax_*.csv`): 20-LUT split 0.781 (bigger) / 0.782 (small, 13
of 16 designs); stacked 0.787 (6 of 7) / 0.775 (12 of 16); 12-LUT 2D 1.039 / 1.033; 8-LUT 2D
1.016 / 1.089. The earlier 0.822, 0.799 and 0.826 came from an uncommitted calculation that
could not be reproduced (2026-11-09). Mean routed width on the bigger designs:
split 66.4, 10-LUT 2D 85.5.

Placement delay model, same configuration with only the model changed (`links_*_c_*`
delta over `sb_*` simple; all on the server VPR): 4-layer split 0.965 bigger / 0.995
small; 2-layer split 1.013 / 0.990; 10-LUT 2D with custom switch blocks 1.013 / 0.995.

### 3.4 Layout files (`pnr/`)

Path timing, recomputed with `compare_joined.py JOINED FLAT [FLES]` and
`compare_paths.py HALF FULL` (ns, sky130 at 2 ns unless ASAP7 = ps):

| File(s) | Made by | Verified numbers (3D over 2D mean path delay) |
|---|---|---|
| `crossbar_paths_half_2ns.csv` (1,675 rows), `crossbar_paths_half1_2ns.csv` (1,675), `crossbar_paths_2d_2ns.csv` (3,100) | `run_pnr.sh` + `report_paths.tcl`, each 5-FLE layer alone | layer 0: pin crossbar 0.872, feedback 0.789, output 0.722; layer 1: 0.884, 0.807, 0.855 |
| `clb_paths_bonded_2ns.csv` vs `clb_paths_2d_2ns.csv` (3,000 rows each) | `run_bond.sh` (10-LUT split, joined) | pin same layer 0.902, pin crossing 1.345, feedback same layer 0.837, feedback crossing 1.455, after crossbar 0.924 |
| `clb_paths_bonded_asap7.csv` vs `clb_paths_2d_asap7.csv` (3,000 each) | `asap7/` | pin same layer 0.896, crossing 1.459; feedback same 0.865, crossing 1.545; after crossbar 0.975 |
| `clb_paths_local_2ns.csv` (1,800) | layer-local 10-LUT | pin (same layer only) 0.781; feedback same 0.769, crossing 1.549 |
| `clb_paths_local20_2ns.csv` (7,200), `FLES=20` | `run_local.sh` 20-LUT, pads spread | pin same layer 1.041; feedback same 1.017, crossing 1.999 (3D mean 1.820 vs 0.910) |
| `clb_paths_local20_center_2ns.csv` (7,200), `FLES=20` | same, `CENTER_PADS=1` | pin same layer 1.043; feedback same 1.023, crossing 1.859 (3D mean 1.692) |
| `clb_paths_local20_center_direct_2ns.csv` (7,200), `FLES=20` | same, `DIRECT=1` (bond as a via, `pnr_local20g`) | pin same layer 1.018; feedback same 1.005, crossing 1.737 (3D mean 1.582) |
| `clb_paths_local20_center_tap_2ns.csv` (7,200), `FLES=20` | same, crossing driver inside the FLE in parallel (tap, `pnr_local20i`) | pin same layer 1.044; feedback same 1.023, crossing 1.576 (3D mean 1.435) |
| `direct_crossing_results.txt` | three `DIRECT=1` tries (`pnr_local20d/f/g`) and the gate check of the last; then the tap layout (`pnr_local20i`) and its gate check | crossing 2.288 / 1.950 / 1.582; 20g gate check passes at 20, 10, 8, 7 ns, fails at 6 and 5; 20i (tap, 1.435) passes at 20, 10, 8, fails at 7, 6, 5; all cut cases fail |
| `clb_paths_local20_center_loaded_2ns.csv`, `_nobuf_`, `_budget_` (7,200 each), `FLES=20` | `run_crossing_fix.sh` runs s, t, u (`pnr_local20s/t/u`) | s: pin same layer 1.023; feedback same 1.025, crossing 1.831 (3D mean 1.668). t: 1.062; 1.154, 1.978 (1.801). u: 1.108; 1.024, 1.627 (1.481) |
| `crossing_stages_results.txt` | `crossing_stages_layout.py` (+ header, run log lines) | crossing over same layer 0.761 (20c), 0.735 (s), 0.750 (t), 0.549 (u); SPICE base 339.3, with the layout's cells, loads and buffers 582.9 |
| `crossing_path_local20_center.txt`, `crossing_path_local20_center_direct.txt` | `explain_crossing`-style Tempus report, FLE 0 to layer 1 mux 15 input 2 | FLE output driver to far mux input inverter 0.999 vs 0.566 ns; direct BUFX16 stage 0.358 ns |

Tile area (`run_tile.sh`; core um2, sky130, 0.5 ns clock; arithmetic checked):

| File | What | Verified numbers |
|---|---|---|
| `tile_results_w70_l6.txt` | 10-LUT split, W70, spans 6/23 vs 2D W100 | 3D sb/cbx/cby per layer 25,401/15,243/15,132 and 25,546/14,024/14,580; 2D 42,365/22,129/22,419; all 0 DRC |
| `tile_results_w74_l5.txt` | 10-LUT split, W74, span 5 | 3D 28,566/15,243/15,243 and 28,261/14,856/15,022; 0 DRC |
| `tile_results_stacked_w100.txt` | stacked 10-LUT, W100 | 3D 45,066/34,272/34,793 and 45,066/34,607/35,136 (DRC 13, 2, 14 in CBs); 2D sum 86,913 |
| `tile_results_n20_local_w100.txt` | 20-LUT layer-local, W100, spans 4/15 | routing per layer 116,502 (DRC 27, 7, 11, 41 in CBs); tile 386,902 = 1.163 of 2D (332,799); silicon per LUT 1.16x, footprint 0.58 |
| `tile_results_relaxed_tracks.txt` | 20-LUT own-layer inputs at W66 vs 2D at W84, all 0 DRC | routing per layer 63,510 / 63,569 vs 76,449 (0.83); tile 333,940 (20 LUTs, two layers) vs 322,336 (10 LUTs); silicon per LUT 1.036 (1.009 at equal cell density); footprint per LUT 0.518 |

From the layout logs (no CSV in this repository): 20-LUT cell area
156,287 um2 per layer (model 155,896); crossing cost in model units 74 ps (pads spread) /
63 ps (mid-core); hardware check with the 3,260-bit chain: 0 chain errors, 0 of 20,000
output errors in RTL, passes on routed gates with SDF to 7 ns.

## 4. Reading the files

1. Read the 2D baseline's N and W before quoting an in-file ratio. `*_n20_*.csv` compare
   against a 20-LUT 2D CLB; `ceil_*_n2d12.csv` and `links_*_w10_*` against 12 LUTs.
2. Files with several 3D settings (`compare_results.csv`, `relayer`, `geometry*`,
   `stacked.csv`) need one ratio per setting; a single pooled number is meaningless.
3. Count failed runs (`routed=False`); a ratio over fewer designs is not comparable.
4. Check which VPR ran a sweep (1.5): the server sweeps used the simple placement delay model
   unless the script passes `--place_delay_model delta`.
5. Model numbers (`cluster_size_model.py`) are estimates, not results.
