module example(
    input [31:0] X, Y, Z, P, Q, R, S, T,
    output [31:0] output1, output2, output3, output4, output5, output6
);

// Common subexpressions  
wire [31:0] xy   = X * Y;
wire [31:0] pz   = P + Z;
wire [31:0] qr   = Q - R;
wire [31:0] px   = P + X;

assign output1 = xy + pz;
assign output2 = pz * qr;
assign output3 = (X + S) + (Y + T);
assign output4 = (xy + Q) * px;

// output5: try (xy - R) - X to see if reordering subtraction matters
assign output5 = (xy - R) - X;

assign output6 = (px + Y) * qr;

endmodule
