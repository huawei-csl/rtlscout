module example(
    input [31:0] x,
    output [31:0] y,
    output [31:0] z,
    output [31:0] w
);

assign y = (x << 3) + (x << 2) + x;  // 13x
assign z = y + y - x;                 // 25x
assign w = (x << 6) - x;              // 63x

endmodule
