// Hard-block wrappers for synthesizing Koios designs with plain Yosys (no parmys).
//
// Koios instantiates VTR's parameterized `single_port_ram` / `dual_port_ram` primitives
// (vtr_flow/primitives.v) when `hard_mem` is defined. Yosys cannot keep a parameterized
// blackbox at its instantiated width, so these wrappers split each memory into the fixed
// 20 Kb blocks our architecture offers (the VTR mem20K modes: 512x40 / 1024x20 / 2048x10
// single port, 1024x20 / 2048x10 dual port): width-wise by slicing the data bus, and
// depth-wise (addresses wider than 11 bits) with registered high address bits selecting
// the output. fix_blif.py renames the fixed blocks back to the VTR model names
// single_port_ram / dual_port_ram that the architecture's memory pb_type declares.

(* blackbox *) module dp_bram_1024x20(input clk, input [9:0] addr1, input [9:0] addr2,
  input [19:0] data1, input [19:0] data2, input we1, input we2,
  output [19:0] out1, output [19:0] out2); endmodule
(* blackbox *) module dp_bram_2048x10(input clk, input [10:0] addr1, input [10:0] addr2,
  input [9:0] data1, input [9:0] data2, input we1, input we2,
  output [9:0] out1, output [9:0] out2); endmodule
(* blackbox *) module sp_bram_512x40(input clk, input [8:0] addr, input [39:0] data, input we,
  output [39:0] out); endmodule
(* blackbox *) module sp_bram_1024x20(input clk, input [9:0] addr, input [19:0] data, input we,
  output [19:0] out); endmodule
(* blackbox *) module sp_bram_2048x10(input clk, input [10:0] addr, input [9:0] data, input we,
  output [9:0] out); endmodule
// The architecture's DSP block: one 27x27 or two 18x19 multipliers (LaZagna's complex_dsp).
(* blackbox *) module two_mult_18x19(input [17:0] A, input [18:0] B, output [36:0] Y); endmodule
(* blackbox *) module one_mult_27x27(input [26:0] A, input [26:0] B, output [53:0] Y); endmodule

module dual_port_ram #(parameter ADDR_WIDTH = 1, parameter DATA_WIDTH = 1) (
  input clk,
  input [ADDR_WIDTH-1:0] addr1, input [ADDR_WIDTH-1:0] addr2,
  input [DATA_WIDTH-1:0] data1, input [DATA_WIDTH-1:0] data2,
  input we1, input we2,
  output [DATA_WIDTH-1:0] out1, output [DATA_WIDTH-1:0] out2);
  localparam BA = (ADDR_WIDTH <= 10) ? 10 : 11;          // address bits of one block
  localparam BW = (ADDR_WIDTH <= 10) ? 20 : 10;          // data bits of one block
  localparam NW = (DATA_WIDTH + BW - 1) / BW;            // width slices
  localparam DB = (ADDR_WIDTH > 11) ? ADDR_WIDTH - 11 : 0; // depth-select bits
  localparam ND = 1 << DB;                               // depth slices
  wire [NW*BW-1:0] d1 = data1, d2 = data2;
  wire [BA-1:0] a1 = addr1, a2 = addr2;
  wire [DB:0] h1 = addr1 >> 11, h2 = addr2 >> 11;
  reg [DB:0] h1_r, h2_r;
  always @(posedge clk) begin h1_r <= h1; h2_r <= h2; end
  wire [ND*NW*BW-1:0] o1, o2;
  genvar i, j;
  generate for (i = 0; i < ND; i = i + 1) begin : dep
    wire s1 = (h1 == i), s2 = (h2 == i);
    for (j = 0; j < NW; j = j + 1) begin : wid
      if (BW == 20) dp_bram_1024x20 b(.clk(clk), .addr1(a1), .addr2(a2),
        .data1(d1[j*BW +: BW]), .data2(d2[j*BW +: BW]), .we1(we1 & s1), .we2(we2 & s2),
        .out1(o1[(i*NW+j)*BW +: BW]), .out2(o2[(i*NW+j)*BW +: BW]));
      else dp_bram_2048x10 b(.clk(clk), .addr1(a1), .addr2(a2),
        .data1(d1[j*BW +: BW]), .data2(d2[j*BW +: BW]), .we1(we1 & s1), .we2(we2 & s2),
        .out1(o1[(i*NW+j)*BW +: BW]), .out2(o2[(i*NW+j)*BW +: BW]));
    end
  end endgenerate
  wire [NW*BW-1:0] r1 = o1[h1_r*NW*BW +: NW*BW], r2 = o2[h2_r*NW*BW +: NW*BW];
  assign out1 = r1[DATA_WIDTH-1:0];
  assign out2 = r2[DATA_WIDTH-1:0];
endmodule

module single_port_ram #(parameter ADDR_WIDTH = 1, parameter DATA_WIDTH = 1) (
  input clk, input [ADDR_WIDTH-1:0] addr, input [DATA_WIDTH-1:0] data, input we,
  output [DATA_WIDTH-1:0] out);
  localparam BA = (ADDR_WIDTH <= 9) ? 9 : (ADDR_WIDTH <= 10) ? 10 : 11;
  localparam BW = (ADDR_WIDTH <= 9) ? 40 : (ADDR_WIDTH <= 10) ? 20 : 10;
  localparam NW = (DATA_WIDTH + BW - 1) / BW;
  localparam DB = (ADDR_WIDTH > 11) ? ADDR_WIDTH - 11 : 0;
  localparam ND = 1 << DB;
  wire [NW*BW-1:0] d = data;
  wire [BA-1:0] a = addr;
  wire [DB:0] h = addr >> 11;
  reg [DB:0] h_r;
  always @(posedge clk) h_r <= h;
  wire [ND*NW*BW-1:0] o;
  genvar i, j;
  generate for (i = 0; i < ND; i = i + 1) begin : dep
    wire s = (h == i);
    for (j = 0; j < NW; j = j + 1) begin : wid
      if (BW == 40) sp_bram_512x40 b(.clk(clk), .addr(a), .data(d[j*BW +: BW]), .we(we & s), .out(o[(i*NW+j)*BW +: BW]));
      else if (BW == 20) sp_bram_1024x20 b(.clk(clk), .addr(a), .data(d[j*BW +: BW]), .we(we & s), .out(o[(i*NW+j)*BW +: BW]));
      else sp_bram_2048x10 b(.clk(clk), .addr(a), .data(d[j*BW +: BW]), .we(we & s), .out(o[(i*NW+j)*BW +: BW]));
    end
  end endgenerate
  wire [NW*BW-1:0] r = o[h_r*NW*BW +: NW*BW];
  assign out = r[DATA_WIDTH-1:0];
endmodule
