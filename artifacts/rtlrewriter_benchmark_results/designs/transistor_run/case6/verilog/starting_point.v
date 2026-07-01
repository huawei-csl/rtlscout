// This example shows a direct approach to summing four numbers without leveraging intermediate results to optimize or reduce the number of operations.
module example(
    input [7:0] a,
    input [7:0] b,
    input [7:0] c,
    input [7:0] d,
    output [9:0] sum  // Output to accommodate possible overflow
);

    // Direct addition without intermediate sharing
    wire [8:0] sum_ab;    // Sum of a and b
    wire [9:0] sum_abc;   // Sum of a+b and c
    wire [10:0] sum_abcd;  // Final sum of a+b+c+d

    // Calculate sum of a and b
    assign sum_ab = a + b;

    // Calculate sum of a+b and c
    assign sum_abc = sum_ab + c;

    // Calculate final sum of a+b+c and d
    assign sum_abcd = sum_abc + d;

    // Output the final sum
    assign sum = sum_abcd;

endmodule
