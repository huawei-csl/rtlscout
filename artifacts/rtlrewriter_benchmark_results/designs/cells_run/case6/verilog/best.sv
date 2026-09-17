module example(
    input [7:0] a,
    input [7:0] b,
    input [7:0] c,
    input [7:0] d,
    output [9:0] sum
);

    // Sum 4 bits per position, carry can be 0,1,2 (2 bits)
    wire [1:0] c0, c1, c2, c3, c4, c5, c6, c7;
    wire [9:0] s;

    assign {c0, s[0]} = a[0] + b[0] + c[0] + d[0];
    assign {c1, s[1]} = a[1] + b[1] + c[1] + d[1] + c0;
    assign {c2, s[2]} = a[2] + b[2] + c[2] + d[2] + c1;
    assign {c3, s[3]} = a[3] + b[3] + c[3] + d[3] + c2;
    assign {c4, s[4]} = a[4] + b[4] + c[4] + d[4] + c3;
    assign {c5, s[5]} = a[5] + b[5] + c[5] + d[5] + c4;
    assign {c6, s[6]} = a[6] + b[6] + c[6] + d[6] + c5;
    assign {c7, s[7]} = a[7] + b[7] + c[7] + d[7] + c6;
    assign s[8] = c7[0];
    assign s[9] = c7[1];

    assign sum = s;

endmodule
