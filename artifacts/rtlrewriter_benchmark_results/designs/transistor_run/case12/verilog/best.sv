module example(
    input [31:0] X, Y, Z, P, Q, R, S, T,
    output [31:0] output1, output2, output3, output4, output5, output6
);

wire [31:0] xy     = X * Y;
wire [31:0] pz     = P + Z;
wire [31:0] qmr    = Q - R;
wire [31:0] xpy    = X + Y;

assign output1 = xy + pz;
assign output2 = pz * qmr;
assign output3 = xpy + (S + T);
wire [31:0] xyq  = Q + xy;
wire [31:0] rpx  = X + R;
assign output4 = xyq * (X + P);
assign output5 = xy - rpx;
wire [31:0] xyp6 = P + xpy;
assign output6 = xyp6 * qmr;

endmodule
