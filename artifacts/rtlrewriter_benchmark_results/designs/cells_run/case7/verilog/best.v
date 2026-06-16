module example(
    input [7:0] input_a,
    input [7:0] input_b,
    input [7:0] input_c,
    input [7:0] input_d,
    input [3:0] opcode,
    input sel,
    output [7:0] result,
    output zero_flag
);

wire [2:0] op = opcode[2:0];
wire is_sub = (op == 3'd1);
wire is_sel6 = (op == 3'd6);
wire is_add4 = (op == 3'd0) | (op == 3'd7);
wire use_adder = is_sub | is_sel6 | is_add4;

// x_pre: a unless sel6&!sel where it's b
wire x_sel_b = is_sel6 & ~sel;
wire [7:0] x_pre = x_sel_b ? input_b : input_a;
// x = x_pre + (is_add4 ? b : 0). But we feed into the main adder.

// y_pre: 
//   add4 → c (and then we add d)
//   sub → ~b
//   sel6&sel → c
//   sel6&~sel → d
wire [7:0] y_pre = is_sub ? ~input_b : 
                   (is_sel6 & ~sel) ? input_d : input_c;

// total: x_pre + y_pre + (add4 ? (b+d) : 0) + is_sub
// That's a 3-input adder. Too expensive.

// Stick with mux:
wire [7:0] x = is_add4 ? (input_a + input_b) : x_pre;
wire [7:0] y = is_add4 ? (input_c + input_d) : y_pre;
wire [7:0] addout = x + y + {7'b0, is_sub};

wire [7:0] logicout = (op == 3'd2) ? (input_a & input_b) :
                      (op == 3'd3) ? (input_a | input_b) :
                      (op == 3'd4) ? (input_a ^ input_b) :
                                     ~input_a;

wire [7:0] r = use_adder ? addout : logicout;
assign result = opcode[3] ? 8'b0 : r;
assign zero_flag = (result == 8'b0);

endmodule
