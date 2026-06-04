
// To implement the ALU without subexpression sharing, each operation will be independently computed, avoiding any use of shared intermediate results or computations. This approach leads to simpler individual operation logic but can potentially increase the total amount of logic required and the complexity of the overall design.

module example(
    input [7:0] input_a,    // 8-bit input operand A
    input [7:0] input_b,    // 8-bit input operand B
    input [7:0] input_c,    // 8-bit input operand C
    input [7:0] input_d,    // 8-bit input operand D
    input [3:0] opcode,     // Operation code
    input sel,
    output reg [7:0] result,  // Result of the ALU operation
    output zero_flag        // Flag indicating result is zero
);

// Define opcode constants for clarity
localparam ADD  = 3'b000;
localparam ADDReverse  = 3'b111;
localparam SUB  = 3'b001;
localparam AND  = 3'b010;
localparam OR   = 3'b011;
localparam XOR  = 3'b100;
localparam NOT  = 3'b101;
localparam SEL_SUM = 3'b110;

reg [7:0] sum;
always @(*) begin
    case (opcode)
        ADD:
            begin
                sum = input_a + input_b + input_c + input_d;
                result = sum;
            end
        ADDReverse:  // Perform addition without sharing any subexpression
            result = input_d + input_c + input_b + input_a;
        SUB:  // Perform subtraction
            result = input_a - input_b;
        AND:  // Perform bitwise AND
            result = input_a & input_b;
        OR:   // Perform bitwise OR
            result = input_a | input_b;
        XOR:  // Perform bitwise XOR
            result = input_a ^ input_b;
        NOT:  // Perform bitwise NOT only on input A
            result = ~input_a;
        SEL_SUM:
            begin
                if (sel)
                    result = input_a + input_c;
                else
                    result = input_b + input_d;
            end
        default: result = 8'b0;  // Default result is zero
    endcase
end

// Set the zero flag if the result is zero
assign zero_flag = (result == 0);

endmodule