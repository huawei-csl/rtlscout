module inefficient_multiplier(
    input [7:0] multiplicandA,
    input [7:0] multiplierB,
    input [7:0] multiplicandC,
    input [7:0] multiplierD,
    input sel,
    output [15:0] product
);
    wire [7:0] a = sel ? multiplicandA : multiplicandC;
    wire [7:0] b = sel ? multiplierB   : multiplierD;
    assign product = a * b;
endmodule
