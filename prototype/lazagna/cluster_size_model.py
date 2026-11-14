#!/usr/bin/env python3
"""Estimate CLB area, tile size, wire spans and crossbar delay for bigger CLBs.

Calibrated on the synthesized 10-FLE 2D CLB (sky130, Design Compiler):
crossbar muxes 44,969 um2 (60 muxes of 50 inputs), their config bits 42,917
(960 bits), the ten FLEs 55,164, clock and other buffers 3,824, total cell
area 146,874; core area 245,887 and routing 86,591 per tile at 100 tracks.
The model reproduces the measured layers of the split CLB (0.50 of the 2D CLB)
and of the layer-local CLB (0.40).

Crossbar delay over the 10-FLE 2D crossbar: 66% of the CLB-input path and 43% of
the feedback path is mux logic, the rest is wire, from the measured half-layer
ratios (0.902 and 0.837 at half the area). Logic grows with each mux level's
fan-in, wire with the square root of the layer's area.

Every number here is an estimate to choose which CLB to lay out, not a result.
"""
import math

MUX_INPUT = 44969 / (60 * 50)      # um2 per crossbar mux input
CONFIG_BIT = 42917 / 960           # um2 per crossbar config bit, with its inverters
FLE = 55164 / 10                   # um2 per FLE: LUT, its 64 bits, flip-flop, output mux
OTHER = 3824 / 10                  # um2 of clock and other buffers per FLE
UTILIZATION = 146874 / 245887      # cell area over core area
CLB_2D = 245887
ROUTING = 86591                    # um2 per layer per tile at 100 tracks and 50 CLB pins
PIN_WEIGHT = 0.00375               # routing area per pin per layer, fitted to the split tile
PIN_LOGIC, FEEDBACK_LOGIC = 0.66, 0.43


def crossbar_cells(fles, mux_inputs):
    """Cell area of 6 muxes per FLE, each mux_inputs wide, two levels of one-hot bits."""
    bits = 2 * math.ceil(math.sqrt(mux_inputs))
    return 6 * fles * (mux_inputs * MUX_INPUT + bits * CONFIG_BIT)


def layer_cells(fles, local):
    """Cell area of the FLEs on one layer and the crossbar that feeds them.

    fles is the CLB's FLE count; split CLBs put half on each layer with half the
    pins. local is None for a flat 2D CLB, "flat" for a flat CLB built from the
    layer-local crossbar's two halves, and True or False for a split CLB with or
    without the layer-local crossbar (each layer's FLEs read only its pins).
    """
    inputs = 4 * fles
    half = fles // 2
    if local is None:   # flat 2D CLB, full crossbar
        return crossbar_cells(fles, inputs + fles) + fles * (FLE + OTHER)
    if local == "flat":  # flat 2D CLB with the layer-local crossbar's two halves
        return 2 * crossbar_cells(half, inputs // 2 + fles) + fles * (FLE + OTHER)
    if local:
        return crossbar_cells(half, inputs // 2 + fles) + half * (FLE + OTHER)
    return (crossbar_cells(fles, inputs + fles) + fles * (FLE + OTHER)) / 2


def routing(tracks, pins):
    return ROUTING * tracks / 100 * (1 + PIN_WEIGHT * pins) / (1 + PIN_WEIGHT * 50)


def describe(name, fles, local, tracks, pins, mux_inputs):
    cells = layer_cells(fles, local)
    core = cells / UTILIZATION
    tile = core + routing(tracks, pins)
    ref_tile = CLB_2D + ROUTING
    width = math.sqrt(tile / ref_tile)
    level = math.ceil(math.sqrt(mux_inputs)) / math.ceil(math.sqrt(50))
    logic = 1 + 0.5 * (level - 1)
    wire = math.sqrt(core / CLB_2D)
    pin = PIN_LOGIC * logic + (1 - PIN_LOGIC) * wire
    feedback = FEEDBACK_LOGIC * logic + (1 - FEEDBACK_LOGIC) * wire
    print(f"{name:28} layer CLB {core / CLB_2D:5.2f}  tile {tile / ref_tile:5.2f}  width {width:5.3f}  "
          f"spans {4 / width:4.1f} {16 / width:5.1f}  crossbar pins {pin:5.3f} feedback {feedback:5.3f}  "
          f"LUTs per 2D-tile area {fles / (tile / ref_tile):5.1f}")


if __name__ == "__main__":
    describe("2D, 10 FLEs", 10, None, 100, 50, 50)
    describe("split, 10 FLEs", 10, False, 80, 25, 50)
    describe("split local, 10 FLEs", 10, True, 66, 25, 30)
    describe("2D, 20 FLEs", 20, None, 141, 100, 100)
    describe("2D local, 20 FLEs", 20, "flat", 141, 100, 60)
    describe("split, 20 FLEs", 20, False, 100, 50, 100)
    describe("split local, 20 FLEs", 20, True, 100, 50, 60)


ROUTING_3D = 116502 / 86591   # measured 20-LUT split tile routing over the model's, per layer
MEASURED_PIN, MEASURED_FEEDBACK = 1.043 / 1.010, 1.023 / 1.017   # 20-LUT layout over its estimate


def general(name, fles, span, sparse, tracks, local=True):
    """Any CLB: fles FLEs over span layers (span 1 is flat 2D), a crossbar reaching sparse of its sources.

    Returns the layer CLB, tile and width over the 10-LUT 2D CLB's, the wire spans, and the
    crossbar delays over the 10-LUT 2D crossbar's, corrected by the 20-LUT layout's measurement.
    """
    per_layer = fles // span
    inputs = 4 * fles
    if span == 1:
        mux_inputs = (inputs + fles) * sparse
    else:
        mux_inputs = ((inputs // span if local else inputs) + fles) * sparse
    cells = crossbar_cells(per_layer, mux_inputs) + per_layer * (FLE + OTHER)
    core = cells / UTILIZATION
    pins = inputs // span + per_layer
    route = routing(tracks, pins) * (ROUTING_3D if span > 1 else 1.0)
    tile = core + route
    ref_tile = CLB_2D + ROUTING
    width = math.sqrt(tile / ref_tile)
    level = math.ceil(math.sqrt(mux_inputs)) / math.ceil(math.sqrt(50))
    logic = 1 + 0.5 * (level - 1)
    wire = math.sqrt(core / CLB_2D)
    pin = PIN_LOGIC * logic + (1 - PIN_LOGIC) * wire
    feedback = FEEDBACK_LOGIC * logic + (1 - FEEDBACK_LOGIC) * wire
    if span > 1:
        pin, feedback = pin * MEASURED_PIN, feedback * MEASURED_FEEDBACK
    result = dict(core=core / CLB_2D, tile=tile / ref_tile, width=width, l4=round(4 / width), l16=round(16 / width),
                  pin=round(pin, 3), feedback=round(feedback, 3), silicon=span * tile / ref_tile / fles * 10)
    print(f"{name:34} layer CLB {result['core']:5.2f} tile {result['tile']:5.2f} width {width:5.3f} "
          f"spans {4 / width:4.1f} {16 / width:5.1f} -> {result['l4']} {result['l16']}  crossbar {result['pin']:5.3f} "
          f"{result['feedback']:5.3f}  silicon per LUT {result['silicon']:4.2f}")
    return result
