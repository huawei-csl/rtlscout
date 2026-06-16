module mux_tree(input sel, input a, output y);
    assign y = sel | a;
endmodule
