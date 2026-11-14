#include <limits>
#include "catch2/catch_test_macros.hpp"
#include "catch2/catch_approx.hpp"
#include "arch_error.h"
#include "pb_type_layers.h"
#include "device_grid.h"
#include "physical_types_util.h"

TEST_CASE("Internal site offsets follow instance ancestry", "[layers]") {
    t_pb_type root, fle, child;
    root.num_pb = 1;
    fle.num_pb = 2;
    fle.instance_layer_offsets = {0, 1};
    child.num_pb = 1;
    t_pb_graph_node r{}, f{}, c{};
    r.pb_type = &root;
    f.pb_type = &fle;
    f.parent_pb_graph_node = &r;
    f.placement_index = 1;
    c.pb_type = &child;
    c.parent_pb_graph_node = &f;
    REQUIRE(pb_graph_node_layer_offset(r) == 0);
    REQUIRE(pb_graph_node_layer_offset(f) == 1);
    REQUIRE(pb_graph_node_layer_offset(c) == 1); // omitted/generated child
    child.instance_layer_offsets = {2};
    REQUIRE(pb_graph_node_layer_offset(c) == 3);
    f.placement_index = 0;
    REQUIRE(pb_graph_node_layer_offset(c) == 2);
    f.placement_index = 2;
    REQUIRE_THROWS_AS(pb_graph_node_layer_offset(c), ArchFpgaError);
    f.placement_index = -1;
    REQUIRE_THROWS_AS(pb_graph_node_layer_offset(f), ArchFpgaError);
    f.placement_index = 1;
    child.instance_layer_offsets = {std::numeric_limits<int>::max()};
    REQUIRE_THROWS_AS(pb_graph_node_layer_offset(c), ArchFpgaError);
    child.instance_layer_offsets = {-1};
    REQUIRE_THROWS_AS(pb_graph_node_layer_offset(c), ArchFpgaError);
    root.instance_layer_offsets = {0};
    REQUIRE_THROWS_AS(pb_graph_node_layer_offset(r), ArchFpgaError);
}

TEST_CASE("Layer envelope includes every alternative mode", "[layers]") {
    t_pb_type root, children[2], grandchild;
    t_mode modes[2], inner;
    root.num_pb = 1;
    root.modes = modes;
    root.num_modes = 2;
    for (int i = 0; i < 2; ++i) {
        modes[i].pb_type_children = &children[i];
        modes[i].num_pb_type_children = 1;
        children[i].num_pb = 2;
    }
    children[0].instance_layer_offsets = {0, 1};
    children[1].instance_layer_offsets = {0, 4};
    REQUIRE(pb_type_max_layer_offset(root) == 4);
    inner.pb_type_children = &grandchild;
    inner.num_pb_type_children = 1;
    grandchild.num_pb = 1;
    grandchild.instance_layer_offsets = {3};
    children[0].modes = &inner;
    children[0].num_modes = 1;
    REQUIRE(pb_type_max_layer_offset(root) == 4);
    grandchild.instance_layer_offsets = {4};
    REQUIRE(pb_type_max_layer_offset(root) == 5);
    grandchild.instance_layer_offsets = {std::numeric_limits<int>::max()};
    REQUIRE_THROWS_AS(pb_type_max_layer_offset(root), ArchFpgaError);
    children[0].instance_layer_offsets = {0};
    REQUIRE_THROWS_AS(pb_type_max_layer_offset(root), ArchFpgaError);
}

TEST_CASE("Physical span covers every equivalent logical site", "[layers]") {
    t_physical_tile_type tile;
    tile.name = const_cast<char*>("clb");
    tile.width = tile.height = tile.capacity = 1;
    tile.layer_span = 2;
    tile.sub_tiles.resize(1);
    tile.pin_layer_offset = {0, 0};
    t_pb_type roots[2], child;
    t_mode mode;
    t_logical_block_type logical[2];
    for (int i = 0; i < 2; ++i) {
        logical[i].name = const_cast<char*>("logic");
        logical[i].pb_type = &roots[i];
        tile.sub_tiles[0].equivalent_sites.push_back(&logical[i]);
    }
    mode.pb_type_children = &child;
    mode.num_pb_type_children = 1;
    roots[1].modes = &mode;
    roots[1].num_modes = 1;
    child.num_pb = 1;
    child.instance_layer_offsets = {1};
    REQUIRE_NOTHROW(validate_tile_layer_span(tile));
    child.instance_layer_offsets = {2};
    REQUIRE_THROWS_AS(validate_tile_layer_span(tile), ArchFpgaError);
    child.instance_layer_offsets = {1};
    tile.pin_layer_offset = {2};
    REQUIRE_THROWS_AS(validate_tile_layer_span(tile), ArchFpgaError);
    tile.pin_layer_offset = {1};
    REQUIRE_NOTHROW(validate_tile_layer_span(tile));
    tile.pin_layer_offset = {2};
    REQUIRE_THROWS_AS(validate_tile_layer_span(tile), ArchFpgaError);
    tile.pin_layer_offset = {0};
    tile.capacity = 2;
    REQUIRE_THROWS_AS(validate_tile_layer_span(tile), ArchFpgaError);
    tile.capacity = 1;
    tile.layer_span = 1; // a second equivalent tile cannot silently be too short
    REQUIRE_THROWS_AS(validate_tile_layer_span(tile), ArchFpgaError);
}

TEST_CASE("Pins sit on their own layer of a multi-layer tile", "[layers]") {
    t_physical_tile_type tile;
    tile.name = const_cast<char*>("clb");
    tile.width = tile.height = tile.capacity = 1;
    tile.layer_span = 2;
    tile.sub_tiles.resize(1);
    tile.num_pins = 2;
    tile.pin_layer_offset = {0, 0};
    tile.pin_physical_layer = {0, 1};
    const int layers = 2;
    SECTION("each pin reaches only its own layer") {
        REQUIRE(is_pin_conencted_to_layer(&tile, 0, 0, 0, layers));
        REQUIRE_FALSE(is_pin_conencted_to_layer(&tile, 0, 0, 1, layers));
        REQUIRE(is_pin_conencted_to_layer(&tile, 1, 0, 1, layers));
        REQUIRE_FALSE(is_pin_conencted_to_layer(&tile, 1, 0, 0, layers));
    }
    SECTION("layer_offset adds the adjacent layer to where the pin sits") {
        tile.pin_layer_offset = {1, 1};
        REQUIRE(is_pin_conencted_to_layer(&tile, 0, 0, 1, layers));
        REQUIRE(is_pin_conencted_to_layer(&tile, 1, 0, 0, layers));
        REQUIRE(is_pin_conencted_to_layer(&tile, 1, 0, 1, layers));
    }
    SECTION("a pin above the device connects to nothing") {
        REQUIRE_FALSE(is_pin_conencted_to_layer(&tile, 1, 1, 1, layers));
    }
    SECTION("pins default to the anchor") {
        tile.pin_physical_layer.clear();
        REQUIRE(get_pin_physical_layer(&tile, 1) == 0);
    }
    SECTION("pin_layer must fit in the tile") {
        REQUIRE_NOTHROW(validate_tile_layer_span(tile));
        tile.pin_physical_layer = {0, 2};
        REQUIRE_THROWS_AS(validate_tile_layer_span(tile), ArchFpgaError);
        tile.pin_physical_layer = {-1, 0};
        REQUIRE_THROWS_AS(validate_tile_layer_span(tile), ArchFpgaError);
    }
}

TEST_CASE("Grid reserves upper cells without creating extra CLB capacity", "[layers]") {
    t_physical_tile_type empty, clb, other;
    clb.name = const_cast<char*>("clb");
    clb.width = clb.height = clb.capacity = 1;
    clb.layer_span = 2;
    clb.sub_tiles.resize(1);
    other.capacity = 1;
    vtr::NdMatrix<t_grid_tile, 3> cells;
    cells.resize({3, 2, 2});
    for (int z = 0; z < 3; ++z)
        for (int x = 0; x < 2; ++x)
            for (int y = 0; y < 2; ++y) cells[z][x][y].type = &empty;
    cells[1][0][0].type = &clb; // highest legal anchor
    DeviceGrid legal("legal", cells);
    REQUIRE(legal.num_instances(&clb, -1) == 1);
    REQUIRE(legal.num_instances(&clb, 2) == 0);
    REQUIRE(legal.get_layer_anchor_offset({0, 0, 2}) == 1);
    REQUIRE(legal.get_physical_type({0, 0, 2})->capacity == 0);
    REQUIRE(legal.get_footprint_type({0, 0, 2}) == &clb);
    REQUIRE(legal.get_footprint_type({1, 1, 2}) == &empty);
    cells[2][0][0].type = &other;
    REQUIRE_THROWS_AS(DeviceGrid("overlap", cells), ArchFpgaError);
    cells[2][0][0].type = &clb;
    REQUIRE_THROWS_AS(DeviceGrid("overlapping anchors", cells), ArchFpgaError);
    cells[1][0][0].type = &empty;
    REQUIRE_THROWS_AS(DeviceGrid("past top", cells), ArchFpgaError);
    cells[2][0][0].type = &empty;
    cells[0][0][0].type = &clb;
    cells[0][1][0].type = &clb;
    REQUIRE(DeviceGrid("two anchors", cells).num_instances(&clb, -1) == 2);
}

TEST_CASE("Internal crossing delay reaches graph timing", "[layers]") {
    t_pb_type root, child;
    root.num_pb = child.num_pb = 1;
    child.instance_layer_offsets = {1};
    t_pb_graph_node r{}, c{};
    r.pb_type = &root;
    c.pb_type = &child;
    c.parent_pb_graph_node = &r;
    t_pb_graph_pin source{}, sink{};
    source.parent_node = &r;
    sink.parent_node = &c;
    t_pb_graph_pin* inputs[] = {&source};
    t_pb_graph_pin* outputs[] = {&sink};
    t_interconnect interconnect;
    interconnect.layer_crossing_delay = 4.e-11;
    t_pb_graph_edge edge{};
    edge.input_pins = inputs;
    edge.output_pins = outputs;
    edge.num_input_pins = edge.num_output_pins = 1;
    edge.interconnect = &interconnect;
    edge.delay_min = 1.e-10;
    edge.delay_max = 2.e-10;
    source.output_edges = {&edge, &edge}; // visit one edge only once
    source.num_output_edges = 2;
    int size = 1;
    r.input_pins = inputs;
    r.num_input_pins = &size;
    r.num_input_ports = 1;
    SECTION("one crossing updates min and max") {
        apply_internal_layer_delays(r);
        REQUIRE(edge.delay_min == Catch::Approx(1.4e-10));
        REQUIRE(edge.delay_max == Catch::Approx(2.4e-10));
    }
    SECTION("a root pin on the child's layer does not cross") {
        apply_internal_layer_delays(r, [](const t_pb_graph_pin&) { return 1; });
        REQUIRE(edge.delay_max == Catch::Approx(2.e-10));
    }
    SECTION("a root pin above a child on the anchor crosses") {
        child.instance_layer_offsets = {0};
        apply_internal_layer_delays(r, [](const t_pb_graph_pin&) { return 1; });
        REQUIRE(edge.delay_max == Catch::Approx(2.4e-10));
    }
    SECTION("same-layer edge unchanged") {
        child.instance_layer_offsets = {0};
        apply_internal_layer_delays(r);
        REQUIRE(edge.delay_max == Catch::Approx(2.e-10));
    }
    SECTION("omitted parameter unchanged") {
        interconnect.layer_crossing_delay = 0.;
        apply_internal_layer_delays(r);
        REQUIRE(edge.delay_max == Catch::Approx(2.e-10));
    }
    SECTION("multiple layers scale the delay") {
        child.instance_layer_offsets = {3};
        apply_internal_layer_delays(r);
        REQUIRE(edge.delay_max == Catch::Approx(3.2e-10));
    }
    SECTION("overflow is rejected") {
        interconnect.layer_crossing_delay = std::numeric_limits<double>::max();
        REQUIRE_THROWS_AS(apply_internal_layer_delays(r), ArchFpgaError);
    }
}
