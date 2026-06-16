module example(
    input [31:0] X, Y, Z, P, Q, R, S, T,
    output [31:0] output1, output2, output3, output4, output5, output6
);

// Original expressions showing potential for optimization via commutativity and associativity
assign output1 = (X * Y) + (Z + P);
assign output2 = (P + Z) * (Q - R);
assign output3 = (Y + S + X) + T;
assign output4 = (Y * X + Q) * (P + X);
assign output5 = (X * Y + P) - (R + P + X);
assign output6 = (X + Y + P) * (Q - R);

endmodule