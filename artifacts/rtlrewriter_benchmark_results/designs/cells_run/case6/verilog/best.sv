module example(
    input  [7:0] a,
    input  [7:0] b,
    input  [7:0] c,
    input  [7:0] d,
    output [9:0] sum
);
    // 4:2 compressor approach using two CSA layers
    // Layer 1: CSA(a,b,c) -> s1, c1
    wire [7:0] s1 = a ^ b ^ c;
    wire [7:0] c1 = (a & b) | ((a ^ b) & c);
    // Layer 2: CSA(s1, c1<<1, d) -> s2, c2
    wire [8:0] c1s = {c1, 1'b0};
    wire [8:0] s1e = {1'b0, s1};
    wire [8:0] de  = {1'b0, d};
    wire [8:0] s2 = s1e ^ c1s ^ de;
    wire [8:0] c2 = (s1e & c1s) | ((s1e ^ c1s) & de);
    assign sum = {1'b0, s2} + {c2, 1'b0};
endmodule
