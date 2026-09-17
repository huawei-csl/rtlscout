module example(
    input  [31:0] x,
    output [31:0] y,
    output [31:0] z,
    output [31:0] w
);

// neg = ~x (for two's complement subtraction: A - x = A + ~x + 1)
wire [31:0] nx = ~x;

// t = 5*x = x + (x<<2)
wire [31:0] t = x + (x << 2);

// y = 13*x = (x<<3) + t
assign y = (x << 3) + t;

// z = 25*x = 2*13*x - x = (y<<1) + ~x + 1  (using two's complement)
assign z = (y << 1) + nx + 1'b1;

// w = 63*x = (x<<6) - x = (x<<6) + ~x + 1
assign w = (x << 6) + nx + 1'b1;

endmodule
