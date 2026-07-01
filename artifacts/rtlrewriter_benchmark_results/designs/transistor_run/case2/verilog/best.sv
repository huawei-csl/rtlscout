module arithmetic_operations(
    input [31:0] A, B, C, D, E, F, G, H,
    output [31:0] result1, result2, result3, result4, result5, result6
);

wire [31:0] ab  = A + B;
wire [31:0] cd  = C * D;
wire [31:0] ef  = E - F;
wire [31:0] gh  = G + H;

assign result1 = cd + ab;
assign result2 = cd + ef;
assign result3 = ab + gh;

// result4 = (cd + E) * ab
// Rewrite: cd + E = cd + ef + F = result2 + F
wire [31:0] cde = cd + E;
assign result4 = cde * ab;

// result5 = cd - A - F  
assign result5 = cd + ~A + ~F + 32'd2;  // cd - A - F using complement

// result6 = (ab + C) * ef
wire [31:0] abc_val = ab + C;
assign result6 = abc_val * ef;

endmodule
