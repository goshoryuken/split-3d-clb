cmake_minimum_required(VERSION 3.16)
project(instance_layer_prototype LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(VTR_ASSERT_LEVEL 2)
add_compile_definitions(VTR_ASSERT_LEVEL=${VTR_ASSERT_LEVEL})
set(VTR_ENABLE_CAPNPROTO OFF)
set(VTR_ENABLE_VERSION OFF)
get_filename_component(VTR_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)
include("${VTR_ROOT}/cmake/modules/FilesToDirs.cmake")
enable_testing()

find_package(OpenSSL REQUIRED COMPONENTS Crypto)
find_package(Python3 REQUIRED COMPONENTS Interpreter)

add_subdirectory("${VTR_ROOT}/libs/EXTERNAL/libcatch2" catch2 EXCLUDE_FROM_ALL)
add_subdirectory("${VTR_ROOT}/libs/EXTERNAL/libpugixml" pugixml EXCLUDE_FROM_ALL)
add_subdirectory("${VTR_ROOT}/libs/liblog" log EXCLUDE_FROM_ALL)
add_subdirectory("${VTR_ROOT}/libs/libvtrutil" vtrutil EXCLUDE_FROM_ALL)

# This fork's XML utilities reference Decryption even for a plain XML build.
# Compile its unchanged source with CMake's OpenSSL discovery. Do not import
# private_key.pem/config.txt or alter the repository's normal decryption build.
# This standalone build supports ordinary .xml input only; .xmle is unsupported.
add_library(libdecrypt STATIC "${VTR_ROOT}/libs/libdecrypt/src/decryption.cpp")
target_include_directories(libdecrypt PUBLIC "${VTR_ROOT}/libs/libdecrypt/src")
target_link_libraries(libdecrypt PUBLIC libpugixml OpenSSL::Crypto)

add_subdirectory("${VTR_ROOT}/libs/libpugiutil" pugiutil EXCLUDE_FROM_ALL)
add_subdirectory("${VTR_ROOT}/libs/libarchfpga" archfpga)

add_test(NAME instance_layers
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_instance_layers.py"
            --reader $<TARGET_FILE:read_arch>)

option(PROTOTYPE_BUILD_VPR "Build the full serial, headless VPR executable" OFF)
if(PROTOTYPE_BUILD_VPR)
    set(VPR_USE_EZGL off)
    set(VPR_USE_SERVER OFF)
    set(VPR_EXECUTION_ENGINE serial)
    set(TATUM_EXECUTION_ENGINE serial)
    add_subdirectory("${VTR_ROOT}/libs/EXTERNAL/libblifparse" blifparse EXCLUDE_FROM_ALL)
    add_subdirectory("${VTR_ROOT}/libs/EXTERNAL/libsdcparse" sdcparse EXCLUDE_FROM_ALL)
    add_subdirectory("${VTR_ROOT}/libs/EXTERNAL/libtatum" tatum EXCLUDE_FROM_ALL)
    add_subdirectory("${VTR_ROOT}/libs/EXTERNAL/libargparse" argparse EXCLUDE_FROM_ALL)
    add_subdirectory("${VTR_ROOT}/libs/librrgraph" rrgraph EXCLUDE_FROM_ALL)
    add_subdirectory("${VTR_ROOT}/vpr" vpr EXCLUDE_FROM_ALL)
    add_executable(test_layer_placement "${VTR_ROOT}/vpr/test/test_compressed_grid.cpp"
        "${VTR_ROOT}/vpr/test/test_layer_utilization.cpp")
    target_link_libraries(test_layer_placement PRIVATE libvpr Catch2::Catch2WithMain)
    add_test(NAME layer_placement COMMAND test_layer_placement --colour-mode none)
    add_test(NAME physical_layers
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_physical_layers.py"
                --vpr $<TARGET_FILE:vpr> --output "${CMAKE_CURRENT_BINARY_DIR}/physical_checks")

    set(PROTOTYPE_OPENFPGA_ROOT "" CACHE PATH "Optional public OpenFPGA checkout for compatibility testing")
    if(PROTOTYPE_OPENFPGA_ROOT)
        set(OPENFPGA_WITH_SWIG OFF)
        set(OPENFPGA_WITH_TEST OFF)
        set(OPENFPGA_WITH_VERSION OFF)
        list(APPEND CMAKE_MODULE_PATH "${PROTOTYPE_OPENFPGA_ROOT}/cmake/modules")
        add_subdirectory("${PROTOTYPE_OPENFPGA_ROOT}/libs" openfpga_libs EXCLUDE_FROM_ALL)
        target_sources(libini PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/openfpga_ini.cpp")
        add_subdirectory("${PROTOTYPE_OPENFPGA_ROOT}/openfpga" openfpga EXCLUDE_FROM_ALL)
        if(CMAKE_CXX_COMPILER_ID STREQUAL "AppleClang")
            # This pinned OpenFPGA revision still uses the pre-C++17 API.
            target_compile_definitions(libopenfpga PRIVATE _LIBCPP_ENABLE_CXX17_REMOVED_RANDOM_SHUFFLE)
        endif()
    endif()
endif()
