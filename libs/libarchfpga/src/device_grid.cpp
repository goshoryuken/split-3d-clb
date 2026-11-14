#include "device_grid.h"

#include <utility>
#include <set>
#include <string>
#include "arch_error.h"
#include "pb_type_layers.h"

DeviceGrid::DeviceGrid(std::string grid_name, vtr::NdMatrix<t_grid_tile, 3> grid)
    : name_(std::move(grid_name))
    , grid_(std::move(grid)) {
    reserve_layer_footprints();
    count_instances();
}

void DeviceGrid::reserve_layer_footprints() {
    std::set<t_physical_tile_type_ptr> validated;
    for (int layer = 0; layer < get_num_layers(); ++layer) {
        for (size_t x = 0; x < width(); ++x) {
            for (size_t y = 0; y < height(); ++y) {
                auto& anchor = grid_[layer][x][y];
                auto type = anchor.type;
                if (!type) throw ArchFpgaError("Null tile in device grid");
                if (validated.insert(type).second) validate_tile_layer_span(*type);
                if (type->layer_span == 1) continue;
                if (type->layer_span > get_num_layers() - layer) {
                    throw ArchFpgaError("Tile layer_span extends beyond device layers at anchor ("
                                       + std::to_string(x) + "," + std::to_string(y) + "," + std::to_string(layer) + ")");
                }
                for (int dz = 1; dz < type->layer_span; ++dz) {
                    auto& cell = grid_[layer + dz][x][y];
                    if (!cell.type || cell.type->capacity != 0 || cell.layer_anchor_offset != 0) {
                        throw ArchFpgaError("Multi-layer tile footprint overlaps another tile at ("
                                           + std::to_string(x) + "," + std::to_string(y) + "," + std::to_string(layer + dz) + ")");
                    }
                    cell.layer_anchor_offset = dz;
                }
            }
        }
    }
}

DeviceGrid::DeviceGrid(std::string grid_name,
                       vtr::NdMatrix<t_grid_tile, 3> grid,
                       std::vector<t_logical_block_type_ptr> limiting_res)
    : DeviceGrid(std::move(grid_name), std::move(grid)) {
    limiting_resources_ = std::move(limiting_res);
}

size_t DeviceGrid::num_instances(t_physical_tile_type_ptr type, int layer_num) const {
    size_t count = 0;
    //instance_counts_ is not initialized
    if (instance_counts_.empty()) {
        return 0;
    }

    int num_layers = (int)grid_.dim_size(0);

    if (layer_num == -1) {
        //Count all layers
        for (int curr_layer_num = 0; curr_layer_num < num_layers; ++curr_layer_num) {
            auto iter = instance_counts_[curr_layer_num].find(type);
            if (iter != instance_counts_[curr_layer_num].end()) {
                count += iter->second;
            }
        }
        return count;
    } else {
        auto iter = instance_counts_[layer_num].find(type);
        if (iter != instance_counts_[layer_num].end()) {
            //Return count
            count = iter->second;
        }
    }

    return count;
}

void DeviceGrid::clear() {
    grid_.clear();
    instance_counts_.clear();
}

void DeviceGrid::count_instances() {
    int num_layers = (int)grid_.dim_size(0);
    instance_counts_.clear();
    instance_counts_.resize(num_layers);

    //Initialize the instance counts
    for (int layer_num = 0; layer_num < num_layers; ++layer_num) {
        for (size_t x = 0; x < width(); ++x) {
            for (size_t y = 0; y < height(); ++y) {
                auto type = grid_[layer_num][x][y].type;

                if (grid_[layer_num][x][y].width_offset == 0 && grid_[layer_num][x][y].height_offset == 0) {
                    //Add capacity only if this is the root location
                    instance_counts_[layer_num][type] = 0;
                }
            }
        }
    }

    //Count the number of blocks in the grid
    for (int layer_num = 0; layer_num < num_layers; ++layer_num) {
        for (size_t x = 0; x < width(); ++x) {
            for (size_t y = 0; y < height(); ++y) {
                auto type = grid_[layer_num][x][y].type;

                if (grid_[layer_num][x][y].width_offset == 0 && grid_[layer_num][x][y].height_offset == 0) {
                    //Add capacity only if this is the root location
                    instance_counts_[layer_num][type] += type->capacity;
                }
            }
        }
    }
}
