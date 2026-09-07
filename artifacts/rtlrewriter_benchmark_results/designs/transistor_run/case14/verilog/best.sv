module mux_tree(
    input wire sel,
    input wire a,
    input wire b,
    input wire c,
    input wire d,
    output wire y
);
    // Redundancy eliminated: y = (sel ? d : c) ? b : a
    wire eff_sel;
    assign eff_sel = sel ? d : c;
    assign y = eff_sel ? b : a;
endmodule
