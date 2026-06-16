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

// Key insight: is_sub only matters when op=001, which is grpA_lo with op[0]=1
// In all other paths that use adder1, is_sub=0, so adder1 computes a+c
// Only in the grpA_lo,op[0]=1 path do we need a-b

// Alternative: compute both a+c and a-b, pick in the mux
// But that's 3 adders. Let me see if is_sub can be simplified.

// is_sub = (op == 3'b001) = ~op[2] & ~op[1] & op[0]
// In the context of grpA_lo: op[2]=0 (we're in grpA), op[1]=0 (grpA_lo)
// So is_sub = op[0] when op[2:1]=00
// When op[2]=1 or op[1]=1: adder1 output might still be used (grpB_hi for sel_sum)
// For grpB_hi: op[2]=1, so is_sub=0. OK.
// For grpA_lo with op[0]=0: is_sub=0. OK.

// The is_sub signal: it's just op[0] & ~op[1] & ~op[2]
// Can we change is_sub to just op[0] and compensate elsewhere?
// If is_sub = op[0], then:
//   op=001: adder1 = a + ~b + 1 = a-b (correct)
//   op=011: adder1 = a + ~b + 1 = a-b (but we use grpA_hi = a|b, so doesn't matter)
//   op=101: adder1 = a + ~b + 1 = a-b (but we use grpB_lo = ~a, so doesn't matter)
//   op=111: adder1 = a + ~b + 1 = a-b (but we use grpB_hi = sum_all = adder1+sum_bd = a-b+b+d = a+d != a+b+c+d) WRONG!
// So we can't just use op[0].

// What about is_sub = op[0] & ~op[2]?
//   op=001: is_sub=1 (correct)
//   op=011: is_sub=1, adder1=a-b (but grpA_hi used, doesn't matter)
//   op=101: is_sub=0, adder1=a+c (but grpB_lo used, doesn't matter)
//   op=111: is_sub=0, adder1=a+c, sum_all=a+c+b+d (correct!)
// What about op=110? is_sub=0, adder1=a+c. grpB_hi: op[0]=0, sel?adder1:sum_bd = sel?(a+c):(b+d) (correct!)
// What about op=100? is_sub=0, adder1=a+c. grpB_lo: a^b (correct, adder1 unused)
// What about op=010? is_sub=0, adder1=a+c. grpA_hi: a&b (correct, adder1 unused)
// What about op=000? is_sub=0, adder1=a+c, sum_all=a+c+b+d (correct!)

// Great! is_sub = op[0] & ~op[2] works and saves one gate!

wire is_sub = op[0] & ~op[2];
wire [7:0] adder1_y = is_sub ? ~input_b : input_c;
wire [7:0] adder1_out = input_a + adder1_y + {7'd0, is_sub};

wire [7:0] sum_bd = input_b + input_d;
wire [7:0] sum_all = adder1_out + sum_bd;

wire [7:0] grpB_lo = input_a ^ (op[0] ? 8'hFF : input_b);

wire [7:0] grpA_lo = op[0] ? adder1_out : sum_all;
wire [7:0] grpA_hi = op[0] ? (input_a | input_b) : (input_a & input_b);
wire [7:0] grpA = op[1] ? grpA_hi : grpA_lo;

wire [7:0] grpB_hi = op[0] ? sum_all : (sel ? adder1_out : sum_bd);
wire [7:0] grpB = op[1] ? grpB_hi : grpB_lo;

wire [7:0] res_internal = op[2] ? grpB : grpA;

assign result = opcode[3] ? 8'd0 : res_internal;
assign zero_flag = (result == 8'd0);

endmodule
