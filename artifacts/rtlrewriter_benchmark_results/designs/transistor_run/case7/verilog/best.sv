module example(
    input [7:0] input_a,
    input [7:0] input_b,
    input [7:0] input_c,
    input [7:0] input_d,
    input [3:0] opcode,
    input sel,
    output reg [7:0] result,
    output zero_flag
);

// Shared adder for a+c (opcode 6 sel=1) and a-b (opcode 1)
// a-b = a + ~b + 1
wire use_sub = (opcode == 4'b0001);
wire [7:0] add1_b = use_sub ? ~input_b : input_c;
wire [7:0] sum_ac_sub = input_a + add1_b + use_sub;

// b+d for opcode 6 sel=0
wire [7:0] sum_bd = input_b + input_d;

// total = (a+c) + (b+d) = a+b+c+d
wire [7:0] sum_all = sum_ac_sub + sum_bd;

always @(*) begin
    case (opcode)
        4'b0000: result = sum_all;
        4'b0001: result = sum_ac_sub;
        4'b0010: result = input_a & input_b;
        4'b0011: result = input_a | input_b;
        4'b0100: result = input_a ^ input_b;
        4'b0101: result = ~input_a;
        4'b0110: result = sel ? sum_ac_sub : sum_bd;
        4'b0111: result = sum_all;
        default: result = 8'b0;
    endcase
end

assign zero_flag = ~|result;

endmodule
