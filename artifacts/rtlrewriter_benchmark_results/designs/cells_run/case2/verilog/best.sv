module arithmetic_operations(
    input [31:0] A, B, C, D, E, F, G, H,
    output [31:0] result1, result2, result3, result4, result5, result6
);

wire [31:0] CD = C * D;
wire [31:0] AB = A + B;
wire [31:0] EF = E - F;
wire [31:0] CDE = CD + E;
wire [31:0] ABC = AB + C;

assign result1 = AB + CD;
assign result2 = CD + EF;
assign result3 = AB + G + H;
assign result4 = CDE * AB;
assign result5 = CD - (A + F);
assign result6 = ABC * EF;

endmodule
