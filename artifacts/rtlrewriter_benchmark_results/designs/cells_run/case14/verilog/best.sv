module mux_tree(
    input wire sel,
    input wire a,
    input wire b,
    input wire c,
    input wire d,
    output wire y
);
    wire s;
    assign s = sel ? d : c;
    assign y = s ? b : a;
endmodule
