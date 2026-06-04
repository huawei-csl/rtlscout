module arithmetic_operations(
    input [31:0] A, B, C, D, E, F, G, H,
    output [31:0] result1, result2, result3, result4, result5, result6
);

// Original expressions showing potential for optimization via commutativity and associativity
assign result1 = (A + B) + (C * D);
assign result2 = (D * C) + (E - F);
assign result3 = (B + G + A) + H;
assign result4 = (D * C + E) * (B + A);
assign result5 = (C * D + B) - (F + B + A);
assign result6 = (A + C + B) * (E - F);

endmodule