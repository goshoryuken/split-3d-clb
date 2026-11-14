`timescale 1ns/1ps
module ten_luts_tb;
    reg [5:0] inputs;
    wire [9:0] outputs;
    reg [9:0] expected;
    integer vector_index;
    integer stage;
    ten_luts dut(.a(inputs[0]), .b(inputs[1]), .c(inputs[2]),
                 .d(inputs[3]), .e(inputs[4]), .f(inputs[5]),
                 .n0(outputs[0]), .n1(outputs[1]), .n2(outputs[2]),
                 .n3(outputs[3]), .n4(outputs[4]), .n5(outputs[5]),
                 .n6(outputs[6]), .n7(outputs[7]), .n8(outputs[8]), .n9(outputs[9]));
    initial begin
        for (vector_index = 0; vector_index < 64; vector_index = vector_index + 1) begin
            inputs = vector_index;
            expected[0] = ^inputs;
            for (stage = 1; stage < 10; stage = stage + 1)
                expected[stage] = expected[stage - 1] ^ (^inputs[5:1]);
            #1;
            if (outputs !== expected) $fatal(1, "Mismatch at input %d", vector_index);
        end
        $display("PASS: all 64 input vectors match all 10 outputs");
        $finish;
    end
endmodule
