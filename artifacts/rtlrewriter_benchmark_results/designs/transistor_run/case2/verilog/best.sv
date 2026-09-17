module arithmetic_operations(
    input  [31:0] A, B, C, D, E, F, G, H,
    output [31:0] result1, result2, result3, result4, result5, result6
);

    // Common subexpressions
    wire [31:0] sum_AB  = A + B;       // shared: result1, result3, result4, result5, result6
    wire [31:0] mul_CD  = C * D;       // shared: result1, result2, result4, result5
    wire [31:0] sub_EF  = E - F;       // shared: result2, result6

    // Derived subexpressions
    wire [31:0] sum_AB_C = sum_AB + C; // for result6: A + B + C

    assign result1 = sum_AB + mul_CD;                 // (A+B) + (C*D)
    assign result2 = mul_CD + sub_EF;                 // (C*D) + (E-F)
    assign result3 = sum_AB + (G + H);                // (A+B) + G + H
    assign result4 = (mul_CD + E) * sum_AB;           // (C*D + E) * (A+B)
    assign result5 = mul_CD - (A + F);               // (C*D + B) - (F + B + A) = C*D - A - F
    assign result6 = sum_AB_C * sub_EF;               // (A+B+C) * (E-F)

endmodule
