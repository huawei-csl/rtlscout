
module mux_tree(
    input wire sel,
    input wire a,
    input wire b,
    input wire c,
    input wire d,
    output wire y
);
    wire x0, x1;
    mux2to1 mux0 (.in0(a), .in1(b), .sel(c), .out(x0));
    mux2to1 mux1 (.in0(a), .in1(b), .sel(d), .out(x1));
    mux2to1 mux2 (.in0(x0), .in1(x1), .sel(sel), .out(y));
endmodule

// 2-to-1 Multiplexer Module
module mux2to1(
    input wire in0,
    input wire in1,
    input wire sel,
    output reg out
);
    always @(*) begin
        out = sel ? in1 : in0; // Use ternary operator for clarity
    end
endmodule