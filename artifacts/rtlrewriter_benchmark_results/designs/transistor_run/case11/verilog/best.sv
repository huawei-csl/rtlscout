module example(
    input x,
    input sel,
    input [7:0] a,
    input [7:0] b,
    output [7:0] result
);
    genvar i;
    generate
        for (i = 0; i < 8; i = i + 1) begin : bit_logic
            // f = (a^b) ? ~x : a
            assign result[i] = (a[i] ^ b[i]) ? ~x : a[i];
        end
    endgenerate
endmodule
