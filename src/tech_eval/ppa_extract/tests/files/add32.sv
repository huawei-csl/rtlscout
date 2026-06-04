module add32 (
    input  logic [31:0] a,
    input  logic [31:0] b,
    output logic [32:0] y
);
    // Simple behavioral description - let the synthesis tool optimize
    assign y = a + b;
endmodule