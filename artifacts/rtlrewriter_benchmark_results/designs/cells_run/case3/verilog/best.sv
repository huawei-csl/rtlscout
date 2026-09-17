module example(
    input  [31:0] x,
    output [31:0] y,
    output [31:0] z,
    output [31:0] w
);
    // y: narrow adder
    wire [2:0] y_low = x[2:0];
    wire [28:0] y_high = x[28:0] + x[31:3];
    assign y = {y_high, y_low};
    
    // z = (x<<5) - y. Full 32-bit subtract as add.
    // But try narrowing: z = s5 + ~y + 1.
    // s5[4:0] = 0. So z[4:0] = ~y[4:0] + 1 (mod 32).
    // The carry from bit 4: c4 = carry_out of (~y[4:0] + 1).
    // z[31:5] = s5[31:5] + ~y[31:5] + c4.
    // c4 = 1 if ~y[4:0] + 1 >= 32, i.e., if ~y[4:0] >= 31, i.e., y[4:0] <= 0, i.e., y[4:0] == 0.
    // So c4 = (y[4:0] == 0) = ~|y[4:0].
    wire c4 = ~|y[4:0];
    assign z[4:0] = ~y[4:0] + 1'b1;
    assign z[31:5] = x[26:0] + (~y[31:5]) + c4;
    
    // w: narrow
    assign w = {y_high + y[28:0], y_low};
endmodule
