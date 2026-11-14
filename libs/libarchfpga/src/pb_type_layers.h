#ifndef PB_TYPE_LAYERS_H
#define PB_TYPE_LAYERS_H

#include <functional>
#include "physical_types.h"

// Architectural offsets only. These functions never store a placed coordinate
// in a shared type or graph. Invalid indices and accumulated overflow throw.
int pb_type_instance_layer_offset(const t_pb_type& type, int instance);
int pb_graph_node_layer_offset(const t_pb_graph_node& node);

// Maximum root-relative offset over every instance and every alternative mode.
// The root itself is on offset zero. Does not require building the routing graph.
int pb_type_max_layer_offset(const t_pb_type& root);

// All equivalent sites and modes must fit; no mode-dependent footprints.
void validate_tile_layer_span(const t_physical_tile_type& tile);

// Apply once, after ordinary timing annotations. Adds to min and max delay.
// root_pin_layer gives the layer of a pin on the root block, which the tile's
// pin_layer can place above the root; by default such pins are on offset zero.
void apply_internal_layer_delays(t_pb_graph_node& root,
                                 const std::function<int(const t_pb_graph_pin&)>& root_pin_layer = nullptr);

#endif
