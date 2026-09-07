module example(
    input  [31:0] x,
    output [31:0] y,
    output [31:0] z,
    output [31:0] w
);

wire [31:0] x17 = x + (x << 4);    // 17x

assign y = x17 - (x << 2);         // 13x = 17x - 4x
assign z = x17 + (x << 3);         // 25x = 17x + 8x
assign w = (z + y) + z;           // 63x = 25+13+25 = 63

endmodule