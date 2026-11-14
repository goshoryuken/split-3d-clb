#include <map>
#include "catch2/catch_test_macros.hpp"
#include "catch2/catch_approx.hpp"
#include "SetupGrid.h"
#include "device_grid.h"

TEST_CASE("Device utilization counts each physical layer cell once", "[layers]") {
    t_physical_tile_type empty, clb;
    empty.width = empty.height = 1;
    clb.width = clb.height = clb.capacity = 1;
    clb.sub_tiles.resize(1);
    t_logical_block_type logical;
    logical.equivalent_tiles.push_back(&clb);
    std::map<t_logical_block_type_ptr, size_t> used = {{&logical, 1}};
    int layers = 2;
    int width = 1;
    float expected = 1.f;
    clb.layer_span = 2;
    SECTION("one spanning CLB fills both cells") {}
    SECTION("unreserved empty space still contributes") {
        width = 3; // two occupied cells and four ordinary empty cells
        expected = 1.f / 3.f;
    }
    SECTION("ordinary 2D full device") {
        layers = clb.layer_span = 1;
    }
    SECTION("ordinary 2D with empty space") {
        layers = clb.layer_span = 1;
        width = 2;
        expected = .5f;
    }
    vtr::NdMatrix<t_grid_tile, 3> cells;
    cells.resize({static_cast<size_t>(layers), static_cast<size_t>(width), 1});
    for (int z = 0; z < layers; ++z)
        for (int x = 0; x < width; ++x) cells[z][x][0].type = &empty;
    cells[0][0][0].type = &clb;
    DeviceGrid grid("utilization", cells);
    REQUIRE(grid.num_instances(&clb, -1) == 1);
    REQUIRE(calculate_device_utilization(grid, used) == Catch::Approx(expected));
    REQUIRE(calculate_device_utilization(grid, {}) == 0.f);
}
