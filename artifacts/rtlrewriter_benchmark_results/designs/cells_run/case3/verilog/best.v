module example(
    input [31:0] x,
    output [31:0] y,
    output [31:0] z,
    output [31:0] w
);

// y = 9x = x + (x<<3); low 3 bits = x[2:0], high 29 = x[28:0] + x[31:3]
wire [28:0] yhi = x[28:0] + x[31:3];
wire [31:0] y_val = {yhi, x[2:0]};
assign y = y_val;

// z = 32x - 9x; z[4:0] = -y[4:0]; z[31:5] = x[26:0] - y[31:5] - borrow
// borrow = (y[4:0] != 0)
// Compute -y[4:0] = ~y[4:0]+1 ignoring upper
wire [4:0] zlo = -y_val[4:0];
wire borrow = |y_val[4:0];
wire [26:0] zhi = x[26:0] + ~y_val[31:5] + (borrow ? 1'b0 : 1'b1);
assign z = {zhi, zlo};

// w = 9*y = y + (y<<3)
wire [28:0] whi = y_val[28:0] + y_val[31:3];
assign w = {whi, y_val[2:0]};

endmodule
