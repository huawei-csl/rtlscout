module example(
    input [31:0] x,
    output [31:0] y,
    output [31:0] z,
    output [31:0] w
);

assign y = 13 * x ;
assign z = 25 * x ;
assign w = 63 * x ;

endmodule