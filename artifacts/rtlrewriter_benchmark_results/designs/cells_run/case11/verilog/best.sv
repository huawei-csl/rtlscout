module example(
    input  wire       x,
    input  wire       sel,
    input  wire [7:0] a,
    input  wire [7:0] b,
    output wire [7:0] result
);

    assign result = x ? (a & b) : (a | b);

endmodule