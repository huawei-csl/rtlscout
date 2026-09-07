// Try AOI/OAI based carry for potentially cheaper CMOS mapping
module example(
    input [7:0] a,
    input [7:0] b,
    output [8:0] sum
);

    wire [8:0] c;
    assign c[0] = 1'b0;

    genvar i;
    generate
        for (i = 0; i < 8; i = i + 1) begin : fa
            wire ab = a[i] & b[i];
            wire anb = a[i] | b[i];
            assign sum[i] = a[i] ^ b[i] ^ c[i];
            assign c[i+1] = ~(~(ab) & ~(anb & c[i]));
        end
    endgenerate

    assign sum[8] = c[8];

endmodule
