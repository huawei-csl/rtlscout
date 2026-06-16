// Optimized carry chain using generate/propagate
module example(
    input [7:0] a,
    input [7:0] b,
    output [8:0] sum
);
    wire [7:0] g = a & b;  // generate
    wire [7:0] p = a ^ b;  // propagate
    wire [8:0] c;           // carry
    
    assign c[0] = 1'b0;
    
    genvar i;
    generate
        for (i = 0; i < 8; i = i + 1) begin : carry
            assign c[i+1] = g[i] | (p[i] & c[i]);
        end
    endgenerate
    
    assign sum[7:0] = p ^ c[7:0];
    assign sum[8] = c[8];
endmodule
