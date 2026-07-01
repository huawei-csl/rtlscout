module example(
    input [31:0] x,
    output [31:0] y,
    output [31:0] z,
    output [31:0] w
);

wire [31:0] nine_x;
times9 t9_1(.a(x), .r(nine_x));
assign y = nine_x;

negate_sub nsub(.a_hi(x[26:0]), .b_lo(x[2:0]), .b_mid(nine_x[4:3]), .b_hi(nine_x[31:5]), .r(z));

times9 t9_2(.a(nine_x), .r(w));

endmodule

module times9(
    input [31:0] a,
    output [31:0] r
);
    assign r[2:0] = a[2:0];
    // r[31:3] = a[31:3] + a[28:0]  (29-bit add)
    // Split into 4 parts: 8+7+7+7 = 29
    wire [8:0] s0 = {1'b0, a[10:3]} + {1'b0, a[7:0]};
    wire [7:0] s1 = a[17:11] + a[14:8] + {7'd0, s0[8]};  // 7-bit + carry
    wire [7:0] s2 = a[24:18] + a[21:15] + {7'd0, s1[7]};
    wire [6:0] s3 = a[31:25] + a[28:22] + {6'd0, s2[7]};
    assign r[10:3] = s0[7:0];
    assign r[17:11] = s1[6:0];
    assign r[24:18] = s2[6:0];
    assign r[31:25] = s3[6:0];
endmodule

module negate_sub(
    input [26:0] a_hi,
    input [2:0] b_lo,
    input [1:0] b_mid,
    input [26:0] b_hi,
    output [31:0] r
);
    assign r[2:0] = ~b_lo + 3'd1;
    wire borrow3 = |b_lo;
    
    wire [2:0] mid_sub = 3'd0 - {1'b0, b_mid} - {2'b0, borrow3};
    assign r[4:3] = mid_sub[1:0];
    wire borrow5 = mid_sub[2];
    
    // Upper 27 bits: a_hi + ~b_hi + ~borrow5
    // Split into 4 parts: 7+7+7+6 = 27
    wire carry_in = ~borrow5;
    wire [7:0] t0 = {1'b0, a_hi[6:0]} + {1'b0, ~b_hi[6:0]} + {7'd0, carry_in};
    wire [7:0] t1 = {1'b0, a_hi[13:7]} + {1'b0, ~b_hi[13:7]} + {7'd0, t0[7]};
    wire [7:0] t2 = {1'b0, a_hi[20:14]} + {1'b0, ~b_hi[20:14]} + {7'd0, t1[7]};
    wire [5:0] t3 = a_hi[26:21] + ~b_hi[26:21] + {5'd0, t2[7]};
    assign r[11:5] = t0[6:0];
    assign r[18:12] = t1[6:0];
    assign r[25:19] = t2[6:0];
    assign r[31:26] = t3[5:0];
endmodule
