module inefficient_multiplier(
    input [7:0] multiplicandA,
    input [7:0] multiplierB,
    input [7:0] multiplicandC,
    input [7:0] multiplierD,
    input sel,
    output [15:0] product
);

wire [7:0] mux_a = sel ? multiplicandA : multiplicandC;
wire [7:0] mux_b = sel ? multiplierB : multiplierD;

assign product = mux_a * mux_b;

endmodule
