module example(
    input [31:0] x,
    output [31:0] y,
    output [31:0] z,
    output [31:0] w
);

assign y = 9 * x ;
assign z = 23 * x ;
assign w = 81 * x ;

endmodule