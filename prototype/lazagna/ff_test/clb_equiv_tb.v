// Loads one CLB's config through its scan chain, then drives random inputs, and
// checks the device under test against the original single-layer CLB every cycle.
// The device is the split CLB, or the routed gates of both layers with delays (SDF),
// or with FLAT the routed gates of the 2D CLB.
// CHAIN is the chain length, PERIOD the data clock in ns, CYCLES how many to run.
`timescale 1ns/1ps
`ifndef PERIOD
`define PERIOD 20
`endif
`ifndef CYCLES
`define CYCLES 2000
`endif
module clb_equiv_tb;
  reg [0:0] pReset = 0, prog_clk = 0, set = 0, reset = 0, clk = 0, clb_clk = 0, ccff_head = 0;
  reg [0:39] clb_I = 0;
  wire [0:9] want, got;
  wire [0:0] want_tail, got_tail;
  logical_tile_clb_mode_clb_ original (.pReset(pReset), .prog_clk(prog_clk), .set(set), .reset(reset), .clk(clk),
      .clb_I(clb_I), .clb_clk(clb_clk), .ccff_head(ccff_head), .clb_O(want), .ccff_tail(want_tail));
  clb_dut dut (.pReset(pReset), .prog_clk(prog_clk), .set(set), .reset(reset), .clk(clk),
      .clb_I(clb_I), .clb_clk(clb_clk), .ccff_head(ccff_head), .clb_O(got), .ccff_tail(got_tail));
`ifdef SDF
  initial begin
    // The files hold min and max delays with an empty typical value, so take max.
`ifdef FLAT
    $sdf_annotate("clb_2d.sdf", dut, , "sdf2d.log", "MAXIMUM");
`else
    $sdf_annotate("clb_layer0.sdf", dut.layer0, , "sdf0.log", "MAXIMUM");
    $sdf_annotate("clb_layer1.sdf", dut.layer1, , "sdf1.log", "MAXIMUM");
`endif
  end
`endif
`ifdef CUT
  initial force dut.`CUT = 1'b0;
`endif

  // A half-loaded config can make a LUT feed itself through the crossbar and
  // oscillate, so every FLE output is held at 0 while bits shift in.
  // A half-loaded config can make a LUT feed itself through the crossbar and
  // oscillate, so every FLE output is held at 0 while bits shift in.
  task hold(input on);
    begin
      if (on) begin
        force original.logical_tile_clb_mode_default__fle_0.fle_out = 1'b0;
        force original.logical_tile_clb_mode_default__fle_1.fle_out = 1'b0;
        force original.logical_tile_clb_mode_default__fle_2.fle_out = 1'b0;
        force original.logical_tile_clb_mode_default__fle_3.fle_out = 1'b0;
        force original.logical_tile_clb_mode_default__fle_4.fle_out = 1'b0;
        force original.logical_tile_clb_mode_default__fle_5.fle_out = 1'b0;
        force original.logical_tile_clb_mode_default__fle_6.fle_out = 1'b0;
        force original.logical_tile_clb_mode_default__fle_7.fle_out = 1'b0;
        force original.logical_tile_clb_mode_default__fle_8.fle_out = 1'b0;
        force original.logical_tile_clb_mode_default__fle_9.fle_out = 1'b0;
`ifdef FLAT
        force dut.logical_tile_clb_mode_default__fle_0.fle_out = 1'b0;
        force dut.logical_tile_clb_mode_default__fle_1.fle_out = 1'b0;
        force dut.logical_tile_clb_mode_default__fle_2.fle_out = 1'b0;
        force dut.logical_tile_clb_mode_default__fle_3.fle_out = 1'b0;
        force dut.logical_tile_clb_mode_default__fle_4.fle_out = 1'b0;
        force dut.logical_tile_clb_mode_default__fle_5.fle_out = 1'b0;
        force dut.logical_tile_clb_mode_default__fle_6.fle_out = 1'b0;
        force dut.logical_tile_clb_mode_default__fle_7.fle_out = 1'b0;
        force dut.logical_tile_clb_mode_default__fle_8.fle_out = 1'b0;
        force dut.logical_tile_clb_mode_default__fle_9.fle_out = 1'b0;
`else
        force dut.layer0.logical_tile_clb_mode_default__fle_0.fle_out = 1'b0;
        force dut.layer0.logical_tile_clb_mode_default__fle_1.fle_out = 1'b0;
        force dut.layer0.logical_tile_clb_mode_default__fle_2.fle_out = 1'b0;
        force dut.layer0.logical_tile_clb_mode_default__fle_3.fle_out = 1'b0;
        force dut.layer0.logical_tile_clb_mode_default__fle_4.fle_out = 1'b0;
        force dut.layer1.logical_tile_clb_mode_default__fle_5.fle_out = 1'b0;
        force dut.layer1.logical_tile_clb_mode_default__fle_6.fle_out = 1'b0;
        force dut.layer1.logical_tile_clb_mode_default__fle_7.fle_out = 1'b0;
        force dut.layer1.logical_tile_clb_mode_default__fle_8.fle_out = 1'b0;
        force dut.layer1.logical_tile_clb_mode_default__fle_9.fle_out = 1'b0;
`endif
      end else begin
        release original.logical_tile_clb_mode_default__fle_0.fle_out;
        release original.logical_tile_clb_mode_default__fle_1.fle_out;
        release original.logical_tile_clb_mode_default__fle_2.fle_out;
        release original.logical_tile_clb_mode_default__fle_3.fle_out;
        release original.logical_tile_clb_mode_default__fle_4.fle_out;
        release original.logical_tile_clb_mode_default__fle_5.fle_out;
        release original.logical_tile_clb_mode_default__fle_6.fle_out;
        release original.logical_tile_clb_mode_default__fle_7.fle_out;
        release original.logical_tile_clb_mode_default__fle_8.fle_out;
        release original.logical_tile_clb_mode_default__fle_9.fle_out;
`ifdef FLAT
        release dut.logical_tile_clb_mode_default__fle_0.fle_out;
        release dut.logical_tile_clb_mode_default__fle_1.fle_out;
        release dut.logical_tile_clb_mode_default__fle_2.fle_out;
        release dut.logical_tile_clb_mode_default__fle_3.fle_out;
        release dut.logical_tile_clb_mode_default__fle_4.fle_out;
        release dut.logical_tile_clb_mode_default__fle_5.fle_out;
        release dut.logical_tile_clb_mode_default__fle_6.fle_out;
        release dut.logical_tile_clb_mode_default__fle_7.fle_out;
        release dut.logical_tile_clb_mode_default__fle_8.fle_out;
        release dut.logical_tile_clb_mode_default__fle_9.fle_out;
`else
        release dut.layer0.logical_tile_clb_mode_default__fle_0.fle_out;
        release dut.layer0.logical_tile_clb_mode_default__fle_1.fle_out;
        release dut.layer0.logical_tile_clb_mode_default__fle_2.fle_out;
        release dut.layer0.logical_tile_clb_mode_default__fle_3.fle_out;
        release dut.layer0.logical_tile_clb_mode_default__fle_4.fle_out;
        release dut.layer1.logical_tile_clb_mode_default__fle_5.fle_out;
        release dut.layer1.logical_tile_clb_mode_default__fle_6.fle_out;
        release dut.layer1.logical_tile_clb_mode_default__fle_7.fle_out;
        release dut.layer1.logical_tile_clb_mode_default__fle_8.fle_out;
        release dut.layer1.logical_tile_clb_mode_default__fle_9.fle_out;
`endif
      end
    end
  endtask

  reg bits [0:`CHAIN-1];
  integer i, v, k, errors = 0, unknown = 0, tail_errors = 0, compared = 0;
  initial begin
    $readmemb("clb_config.txt", bits);
    hold(1);
    pReset = 1;
    #100 pReset = 0;
    #100;
    // Two passes: the second pushes the first one out of ccff_tail, so every bit
    // is checked after crossing the whole chain, and the config ends the same.
    for (i = 0; i < 2 * `CHAIN; i = i + 1) begin
      ccff_head = bits[i % `CHAIN];
      #20 prog_clk = 1;
      #18 if (i >= `CHAIN && got_tail !== want_tail) tail_errors = tail_errors + 1;
      #2 prog_clk = 0;
    end
    #100 hold(0);
    reset = 1;
    #20 clk = 1; #20 clk = 0; #20 reset = 0;
    for (k = 0; k < `CYCLES; k = k + 1) begin
      // Inputs change a quarter period after one rising edge, clear of the clock
      // tree's delay, and outputs are checked just before the next edge.
      #(`PERIOD / 4.0) clb_I = {$random, $random};
      #(`PERIOD / 4.0) clk = 0;
      #(`PERIOD / 2.0 - 0.05);
      for (v = 0; v < 10; v = v + 1) begin
        if (want[v] !== 1'bx) begin
          compared = compared + 1;
          if (got[v] === 1'bx) unknown = unknown + 1;
          if (got[v] !== want[v]) begin
            if (errors < 8) $display("MISMATCH cycle=%0d output=%0d got=%b want=%b", k, v, got[v], want[v]);
            errors = errors + 1;
          end
        end
      end
      #0.05 clk = 1;
    end
    $display("EQUIV period=%0d chain_errors=%0d compared=%0d errors=%0d unknown=%0d", `PERIOD, tail_errors, compared, errors, unknown);
    $finish;
  end
endmodule
