// Inefficient RTL Example: Unnecessary Wide Bit Width
// This module calculates the sum of two 8-bit numbers but uses a 128-bit register to store the result, which is unnecessary and inefficient for the given operation.

module example(
    input [7:0] a,  // 8-bit input
    input [7:0] b,  // 8-bit input
    output reg [8:0] sum  // Excessively wide output
);

    // Use of a 128-bit register to store an 8-bit operation result
    reg [127:0] internal_sum;

    always @(a or b) begin
        internal_sum = a + b;  // Result will never use more than 9 bits
        sum = internal_sum[8:0];
    end

endmodule