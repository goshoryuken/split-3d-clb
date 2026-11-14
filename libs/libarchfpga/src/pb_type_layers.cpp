#include "pb_type_layers.h"

#include <algorithm>
#include <limits>
#include <cmath>
#include <functional>
#include <string>
#include <unordered_set>
#include "arch_error.h"

namespace {
int checked_add(int parent, int child) {
    if (parent < 0 || child < 0 || child > std::numeric_limits<int>::max() - parent) {
        throw ArchFpgaError("Accumulated internal layer offset overflows int");
    }
    return parent + child;
}

int descendants_max(const t_pb_type& type) {
    int maximum = 0;
    for (int m = 0; m < type.num_modes; ++m) {
        const auto& mode = type.modes[m];
        for (int c = 0; c < mode.num_pb_type_children; ++c) {
            const auto& child = mode.pb_type_children[c];
            int local_max = 0;
            for (int i = 0; i < child.num_pb; ++i) {
                local_max = std::max(local_max, pb_type_instance_layer_offset(child, i));
            }
            maximum = std::max(maximum, checked_add(local_max, descendants_max(child)));
        }
    }
    return maximum;
}
} // namespace

int pb_type_instance_layer_offset(const t_pb_type& type, int instance) {
    if (instance < 0 || instance >= type.num_pb) {
        throw ArchFpgaError("Internal layer instance index outside num_pb");
    }
    const auto& offsets = type.instance_layer_offsets;
    if (offsets.empty()) return 0;
    if (offsets.size() != static_cast<size_t>(type.num_pb) || offsets[instance] < 0) {
        throw ArchFpgaError("Invalid internal instance_layer_offsets vector");
    }
    return offsets[instance];
}

int pb_graph_node_layer_offset(const t_pb_graph_node& node) {
    int offset = 0;
    for (auto current = &node; current; current = current->parent_pb_graph_node) {
        if (!current->pb_type) throw ArchFpgaError("Internal layer node has no pb_type");
        if (!current->parent_pb_graph_node) {
            if (!current->pb_type->instance_layer_offsets.empty()) {
                throw ArchFpgaError("Root cannot have instance_layer_offsets");
            }
            break;
        }
        offset = checked_add(offset, pb_type_instance_layer_offset(*current->pb_type, current->placement_index));
    }
    return offset;
}

int pb_type_max_layer_offset(const t_pb_type& root) {
    if (!root.instance_layer_offsets.empty()) {
        throw ArchFpgaError("Root cannot have instance_layer_offsets");
    }
    return descendants_max(root);
}

void validate_tile_layer_span(const t_physical_tile_type& tile) {
    if (tile.layer_span < 1) throw ArchFpgaError("Tile layer_span must be positive");
    if (tile.layer_span > 1) {
        if (tile.width != 1 || tile.height != 1 || tile.capacity != 1 || tile.sub_tiles.size() != 1) {
            throw ArchFpgaError("Multi-layer tiles currently require width=height=capacity=1 and one sub_tile");
        }
        for (int offset : tile.pin_layer_offset) {
            if (offset < 0 || offset >= tile.layer_span) {
                throw ArchFpgaError("Physical pin lies outside tile layer_span");
            }
        }
    }
    for (int pin_layer : tile.pin_physical_layer) {
        if (pin_layer < 0 || pin_layer >= tile.layer_span) {
            throw ArchFpgaError("pin_layer lies outside tile layer_span");
        }
    }
    for (const auto& sub : tile.sub_tiles) {
        for (auto logical : sub.equivalent_sites) {
            if (!logical || !logical->pb_type) {
                if (tile.layer_span > 1) throw ArchFpgaError("Multi-layer equivalent site has no pb_type");
                continue;
            }
            if (pb_type_max_layer_offset(*logical->pb_type) >= tile.layer_span) {
                throw ArchFpgaError(std::string("Internal sites of '") + logical->name
                                   + "' exceed layer_span of equivalent tile '" + tile.name + "'");
            }
        }
    }
}

void apply_internal_layer_delays(t_pb_graph_node& root,
                                 const std::function<int(const t_pb_graph_pin&)>& root_pin_layer) {
    auto pin_layer = [&](const t_pb_graph_pin& pin) {
        if (root_pin_layer && pin.parent_node == &root) return root_pin_layer(pin);
        return pb_graph_node_layer_offset(*pin.parent_node);
    };
    std::unordered_set<t_pb_graph_edge*> visited;
    std::function<void(t_pb_graph_node&)> visit = [&](t_pb_graph_node& node) {
        auto visit_ports = [&](t_pb_graph_pin** ports, int count, int* sizes) {
            for (int p = 0; p < count; ++p) {
                for (int i = 0; i < sizes[p]; ++i) {
                    auto& pin = ports[p][i];
                    for (int e = 0; e < pin.num_output_edges; ++e) {
                        auto edge = pin.output_edges[e];
                        if (!visited.insert(edge).second || !edge->interconnect) continue;
                        double per_layer = edge->interconnect->layer_crossing_delay;
                        if (per_layer == 0.) continue;
                        if (edge->num_input_pins != 1 || edge->num_output_pins != 1) {
                            throw ArchFpgaError("layer_crossing_delay requires single-source single-sink graph edges");
                        }
                        int from = pin_layer(*edge->input_pins[0]);
                        int to = pin_layer(*edge->output_pins[0]);
                        double delta = per_layer * std::abs(from - to);
                        double max_delay = edge->delay_max + delta;
                        double min_delay = edge->delay_min + delta;
                        if (!std::isfinite(delta) || delta < 0. || !std::isfinite(max_delay)
                            || !std::isfinite(min_delay) || max_delay > std::numeric_limits<float>::max()
                            || min_delay > std::numeric_limits<float>::max()) {
                            throw ArchFpgaError("Internal layer crossing delay overflows finite timing storage");
                        }
                        edge->delay_max = max_delay;
                        edge->delay_min = min_delay;
                    }
                }
            }
        };
        visit_ports(node.input_pins, node.num_input_ports, node.num_input_pins);
        visit_ports(node.output_pins, node.num_output_ports, node.num_output_pins);
        visit_ports(node.clock_pins, node.num_clock_ports, node.num_clock_pins);
        for (int m = 0; m < node.pb_type->num_modes; ++m)
            for (int c = 0; c < node.pb_type->modes[m].num_pb_type_children; ++c)
                for (int i = 0; i < node.pb_type->modes[m].pb_type_children[c].num_pb; ++i)
                    visit(node.child_pb_graph_nodes[m][c][i]);
    };
    visit(root);
}
