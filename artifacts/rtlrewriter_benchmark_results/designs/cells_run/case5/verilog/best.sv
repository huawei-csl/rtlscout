module example(input [7:0] a, input [7:0] b, output [8:0] sum);
    wire [3:0] s0 = a[2:0] + b[2:0];
    wire [3:0] s1 = a[5:3] + b[5:3] + s0[3];
    wire [2:0] s2 = a[7:6] + b[7:6] + s1[3];
    assign sum = {s2, s1[2:0], s0[2:0]};
endmodule
