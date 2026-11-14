// Fixed truth-table lookup reference; index bit 0 is the preceding stage.
module asymmetric_ten_luts(input a,b,c,d,e,f, output n0,n1,n2,n3,n4,n5,n6,n7,n8,n9);
  localparam [63:0] LUT0 = 64'h0ddce92c2cb31a1d;
  assign n0 = LUT0[{f,e,d,c,b,a}];
  localparam [63:0] LUT1 = 64'h4d82c616c12ba2e7;
  assign n1 = LUT1[{f,e,d,c,b,n0}];
  localparam [63:0] LUT2 = 64'h4640aba06491d4ce;
  assign n2 = LUT2[{f,e,d,c,b,n1}];
  localparam [63:0] LUT3 = 64'h30d2e06e85ed1b46;
  assign n3 = LUT3[{f,e,d,c,b,n2}];
  localparam [63:0] LUT4 = 64'hbe466ae1d3efbbac;
  assign n4 = LUT4[{f,e,d,c,b,n3}];
  localparam [63:0] LUT5 = 64'habe25052b4a7d8f0;
  assign n5 = LUT5[{f,e,d,c,b,n4}];
  localparam [63:0] LUT6 = 64'h79db88a92072874b;
  assign n6 = LUT6[{f,e,d,c,b,n5}];
  localparam [63:0] LUT7 = 64'hf20f7fbd25154b6e;
  assign n7 = LUT7[{f,e,d,c,b,n6}];
  localparam [63:0] LUT8 = 64'h98d0d92c64be4ff0;
  assign n8 = LUT8[{f,e,d,c,b,n7}];
  localparam [63:0] LUT9 = 64'h354a09465c067c5a;
  assign n9 = LUT9[{f,e,d,c,b,n8}];
endmodule
