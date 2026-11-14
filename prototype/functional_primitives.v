// Functional-only models for the two primitives in ten_luts_post_synthesis.v.
// No SDF, physical delay, or configurable FPGA fabric is modeled here.
module LUT_K #(parameter K=1, parameter [2**K-1:0] LUT_MASK=0)
    (input [K-1:0] in, output out);
    assign out = LUT_MASK[in];
endmodule

module fpga_interconnect(input datain, output dataout);
    assign dataout = datain;
endmodule
