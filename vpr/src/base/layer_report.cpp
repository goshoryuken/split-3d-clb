#include "layer_report.h"

#include <fstream>
#include <memory>
#include <string>
#include "globals.h"
#include "pb_type_layers.h"
#include "vpr_utils.h"
#include "vtr_log.h"
#include "vtr_util.h"

void write_internal_layer_report() {
    const auto& device = g_vpr_ctx.device();
    bool spanning = false;
    for (const auto& tile : device.physical_tile_types) spanning |= tile.layer_span > 1;
    if (!spanning) return;

    const auto& atoms = g_vpr_ctx.atom();
    const auto& clusters = g_vpr_ctx.clustering().clb_nlist;
    const auto& placement = g_vpr_ctx.placement();
    std::string filename = vtr::out_file_prefix + "internal_layers.tsv";
    std::ofstream out(filename);
    if (!out) VPR_THROW(VPR_ERROR_OTHER, "Cannot write %s", filename.c_str());
    out.precision(12);
    out << "# atom: name cluster relative_layer absolute_layer\n"
        << "# footprint: cluster x y layer anchor_layer\n"
        << "# edge: cluster net source_pin sink_pin source_layer sink_layer max_delay_seconds\n";
    for (auto atom : atoms.nlist.blocks()) {
        auto clb = atoms.lookup.atom_clb(atom);
        const auto& loc = placement.block_locs()[clb].loc;
        auto tile = device.grid.get_physical_type({loc.x, loc.y, loc.layer});
        if (tile->layer_span == 1) continue;
        auto pb = atoms.lookup.atom_pb(atom);
        int offset = pb_graph_node_layer_offset(*pb->pb_graph_node);
        if (offset >= tile->layer_span) VPR_THROW(VPR_ERROR_PLACE, "Occupied atom exceeds physical layer span");
        out << "atom\t" << atoms.nlist.block_name(atom) << '\t' << clusters.block_name(clb)
            << '\t' << offset << '\t' << loc.layer + offset << '\n';
    }
    for (auto clb : clusters.blocks()) {
        const auto& loc = placement.block_locs()[clb].loc;
        auto tile = device.grid.get_physical_type({loc.x, loc.y, loc.layer});
        if (tile->layer_span == 1) continue;
        for (int dz = 0; dz < tile->layer_span; ++dz) {
            if (device.grid.get_layer_anchor_offset({loc.x, loc.y, loc.layer + dz}) != dz) {
                VPR_THROW(VPR_ERROR_PLACE, "Occupied CLB has an invalid layer reservation");
            }
            out << "footprint\t" << clusters.block_name(clb) << '\t' << loc.x << '\t' << loc.y
                << '\t' << loc.layer + dz << '\t' << loc.layer << '\n';
        }
        auto type = clusters.block_type(clb);
        std::unique_ptr<t_pb_graph_pin*[]> pins(alloc_and_load_pb_graph_pin_lookup_from_index(type));
        const auto& route = clusters.block_pb(clb)->pb_route;
        for (const auto& entry : route) {
            int sink_id = entry.first;
            int source_id = entry.second.driver_pb_pin_id;
            if (source_id == OPEN || !entry.second.atom_net_id) continue;
            auto source = pins[source_id];
            auto sink = pins[sink_id];
            int from = pb_graph_node_layer_offset(*source->parent_node);
            int to = pb_graph_node_layer_offset(*sink->parent_node);
            if (from == to) continue;
            const t_pb_graph_edge* used_edge = nullptr;
            for (int e = 0; e < source->num_output_edges; ++e) {
                auto edge = source->output_edges[e];
                for (int p = 0; p < edge->num_output_pins; ++p) {
                    if (edge->output_pins[p] == sink) used_edge = edge;
                }
            }
            if (!used_edge) VPR_THROW(VPR_ERROR_ROUTE, "Used cross-layer connection has no architecture graph edge");
            out << "edge\t" << clusters.block_name(clb) << '\t' << atoms.nlist.net_name(entry.second.atom_net_id)
                << '\t' << source_id << '\t' << sink_id << '\t' << loc.layer + from
                << '\t' << loc.layer + to << '\t' << used_edge->delay_max << '\n';
        }
    }
    if (!out) VPR_THROW(VPR_ERROR_OTHER, "Failed writing %s", filename.c_str());
    VTR_LOG("Wrote occupied internal layer and cross-layer routing audit: %s\n", filename.c_str());
}
