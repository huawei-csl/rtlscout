module example(
    input [31:0] X, Y, Z, P, Q, R, S, T,
    output [31:0] output1, output2, output3, output4, output5, output6
);

// Shared subexpressions
wire [31:0] XY  = X * Y;       // output1, output4, output5
wire [31:0] PZ  = P + Z;       // output1, output2
wire [31:0] QR  = Q - R;       // output2, output6
wire [31:0] XP  = X + P;       // output4, output6

assign output1 = XY + PZ;
assign output2 = PZ * QR;
assign output3 = (Y + X) + (S + T);
assign output4 = (XY + Q) * XP;
assign output5 = (XY - X) - R;
assign output6 = (XP + Y) * QR;

endmodule
