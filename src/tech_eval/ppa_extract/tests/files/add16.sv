module add16 (
    input  logic [15:0] a,
    input  logic [15:0] b,
    output logic [16:0] y
);
    // Simple behavioral description - let the synthesis tool optimize
    assign y = a + b;
endmodule