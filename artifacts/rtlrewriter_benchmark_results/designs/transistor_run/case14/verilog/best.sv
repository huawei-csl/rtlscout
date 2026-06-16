module mux_tree(
    input wire sel,
    input wire a,
    input wire b,
    input wire c,
    input wire d,
    output wire y
);
    wire s;
    // s = sel ? d : c
    assign s = (sel & d) | (~sel & c);
    // y = s ? b : a
    assign y = (s & b) | (~s & a);
endmodule
