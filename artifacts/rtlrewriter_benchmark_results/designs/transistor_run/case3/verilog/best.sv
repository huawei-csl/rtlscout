module example(
    input [31:0] x,
    output [31:0] y,
    output [31:0] z,
    output [31:0] w
);

wire [31:0] x_shl3 = {x[28:0], 3'b0};

// y = 9*x = (x<<3) + x
assign y = x_shl3 + x;

// w = 81*x = 9*(9*x) = (y<<3) + y
assign w = {y[28:0], 3'b0} + y;

// z = 23*x = 32*x - 9*x = (x<<5) - y
assign z = {x[26:0], 5'b0} - y;

endmodule
