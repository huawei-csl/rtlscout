module inefficient_multiplier(
    input  [7:0] multiplicandA,
    input  [7:0] multiplierB,
    input  [7:0] multiplicandC,
    input  [7:0] multiplierD,
    input  sel,
    output [15:0] product
);

wire [7:0] op1 = sel ? multiplicandA : multiplicandC;
wire [7:0] op2 = sel ? multiplierB  : multiplierD;

assign product = op1 * op2;

endmodule
