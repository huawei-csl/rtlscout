module example(
    input x,
    input sel,
    input [7:0] a,
    input [7:0] b,
    output [7:0] result
);
    assign result = x ? (a & b) : (a | b);
endmodule
