// 2:1 mux with one input tied to constant 1: y = sel ? 1 : a  =>  y = sel | a
module mux_tree(
    input wire sel,
    input wire a,
    output wire y
);
    assign y = sel | a;
endmodule
