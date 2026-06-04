module example(
    input x,
    input sel,
    input [7:0] a,        // 8-bit input operand A
    input [7:0] b,        // 8-bit input operand B
    output reg [7:0] result   // 9-bit result to accommodate potential carry or borrow
);

// Instantiate separate adder and subtractor
wire [7:0] sum_resullt, diff_result, and_result, or_result, alu_result;

and_bitwise and_module(
    .a(a),
    .b(b),
    .and_result(and_result)
);

or_bitwise or_module(
    .a(a),
    .b(b),
    .or_result(or_result)
);

adder add_module(
    .a(a),
    .b(b),
    .sum_result(sum_result)
);

subtractor subtract_module(
    .a(a),
    .b(b),
    .diff_result(diff_result)
);

alu alu_module(
    .a(a),
    .b(b),
    .alu_result(alu_result)
);

always @(*) begin
    if (x)  begin
        if (x | sel)  begin
            // And bitwise module
            result = and_result;
        end
        else begin
            // Or bitwise module
            result = or_result;
        end
    end
    else  begin
        if (x)  begin
            result = sum_result + diff_result + alu_result;
        end else begin 
            result = or_result;
        end
    end
end
endmodule

// Module for ALU
module alu( 
    input [7:0] a,
    input [7:0] b,
    output [7:0] alu_result
);
    assign alu_result = a + b + (a - b);
endmodule

// Module for addition
module adder(
  input [7:0] a,
  input [7:0] b,
  output [7:0] sum_result
);
  assign sum_result = a + b;
endmodule

// Module for subtraction
module subtractor(
  input [7:0] a,
  input [7:0] b,
  output [7:0] diff_result
);
  assign diff_result = a - b;
endmodule

// Module for and
module and_bitwise(
  input [7:0] a,
  input [7:0] b,
  output [7:0] and_result
);
  assign and_result = a & b;
endmodule

// Module for or
module or_bitwise(
  input [7:0] a,
  input [7:0] b,
  output [7:0] or_result
);
  assign or_result = a | b;
endmodule