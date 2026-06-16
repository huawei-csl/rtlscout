module example(
    input [31:0] X, Y, Z, P, Q, R, S, T,
    output [31:0] output1, output2, output3, output4, output5, output6
);

wire [31:0] XY = X * Y;
wire [31:0] PZ = P + Z;
wire [31:0] QR = Q - R;
wire [31:0] PX = P + X;
wire [31:0] XYP = PX + Y;
wire [31:0] XYmR = XY - R;
wire [31:0] XYQ = XY + Q;

assign output1 = XY + PZ;
assign output2 = PZ * QR;
assign output3 = (Y + S) + (X + T);
assign output4 = XYQ * PX;
assign output5 = XYmR - X;
assign output6 = XYP * QR;

endmodule
