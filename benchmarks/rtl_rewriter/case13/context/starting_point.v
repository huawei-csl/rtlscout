module mux_tree(
    input wire sel,
    input wire a,
    output wire y
);
    mux2to1 mux0 (.in0(a), .in1(1), .sel(sel), .out(y));
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