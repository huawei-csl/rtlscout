module arithmetic_operations(
    input  [31:0] A, B, C, D, E, F, G, H,
    output [31:0] result1, result2, result3, result4, result5, result6
);

// Try: result3 = AB + G + H. Can we write as (A+B+G)+H or (A+B+H)+G? 
// Try: share (A+G) with result5? result5 = CD - A - F. No.
// Try: result5 = CD + ~A + ~F (using two's complement: -x = ~x + 1)
// CD - A - F = CD + (~A + 1) + (~F + 1) = CD + ~A + ~F + 2
// Not sure if this helps Yosys. Let's try.
wire [31:0] CD  = C * D;
wire [31:0] AB  = A + B;
wire [31:0] CDE = CD + E;
wire [31:0] ABC = AB + C;
wire [31:0] EF  = E - F;
wire [31:0] AF  = A + F;

assign result1 = AB + CD;
assign result2 = CD + EF;
assign result3 = (G + H) + AB;
assign result4 = CDE * AB;
assign result5 = CD - AF;
assign result6 = ABC * EF;

endmodule
