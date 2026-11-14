// Yosys techmap: $mul cells onto the architecture's hard multipliers (LaZagna's complex_dsp:
// two 18x19 or one 27x27 per block). Operands are sign- or zero-extended to the hard width;
// the product's low Y_WIDTH bits are exact either way. Multipliers with an operand under 5
// bits, or over 27 bits, stay soft logic (_TECHMAP_FAIL_), as parmys' min_hard_mult_size
// would leave small ones soft; synth_koios.sh reports how many of each were made.
(* techmap_celltype = "$mul" *)
module _hb_mul_map (A, B, Y);
  parameter A_SIGNED = 0;
  parameter B_SIGNED = 0;
  parameter A_WIDTH = 1;
  parameter B_WIDTH = 1;
  parameter Y_WIDTH = 1;
  input [A_WIDTH-1:0] A;
  input [B_WIDTH-1:0] B;
  output [Y_WIDTH-1:0] Y;
  localparam SIGNED = A_SIGNED && B_SIGNED;
  localparam M18 = (A_WIDTH <= 18 && B_WIDTH <= 19);
  localparam M18S = !M18 && (A_WIDTH <= 19 && B_WIDTH <= 18);
  localparam M27 = !M18 && !M18S && (A_WIDTH <= 27 && B_WIDTH <= 27);
  wire _TECHMAP_FAIL_ = (A_WIDTH < 5) || (B_WIDTH < 5) || !(M18 || M18S || M27);
  generate
    if (M18 || M18S) begin : m18
      wire [17:0] a;
      wire [18:0] b;
      wire [36:0] y;
      if (M18) begin
        if (SIGNED) begin assign a = $signed(A); assign b = $signed(B); end
        else begin assign a = A; assign b = B; end
      end else begin
        if (SIGNED) begin assign a = $signed(B); assign b = $signed(A); end
        else begin assign a = B; assign b = A; end
      end
      two_mult_18x19 m(.A(a), .B(b), .Y(y));
      if (SIGNED) assign Y = $signed(y); else assign Y = y;
    end else begin : m27
      wire [26:0] a, b;
      wire [53:0] y;
      if (SIGNED) begin assign a = $signed(A); assign b = $signed(B); end
      else begin assign a = A; assign b = B; end
      one_mult_27x27 m(.A(a), .B(b), .Y(y));
      if (SIGNED) assign Y = $signed(y); else assign Y = y;
    end
  endgenerate
endmodule
