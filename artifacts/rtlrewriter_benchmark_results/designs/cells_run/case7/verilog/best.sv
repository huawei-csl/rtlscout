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

// Merge sel_sum and sum4: sum4 = ac + bd, sel_sum = sel ? ac : bd.
// Alternative: when sel=1, sel_sum = ac, sum4 = ac + bd.
//              when sel=0, sel_sum = bd, sum4 = ac + bd.
// sum4 is the same regardless of sel.
// Can we compute sel_sum and sum4 from a shared adder?
// sum4 = ac + bd, sel_sum = sel ? ac : bd.
// If we compute sel_sum = sel ? ac : bd, then the "other" value is sel ? bd : ac.
// sum4 = sel_sum + (sel ? bd : ac) = sel_sum + (~sel ? bd : ac).
// So sum4 = sel_sum + other, where other = sel ? bd : ac.
// That doesn't help - we still need both ac and bd, and a mux + add.

// Let's try: avoid computing sum4 as a separate 8-bit add.
// Instead, compute sum4 only from the partial sums without a third adder.
// sum4 = a+b+c+d. We can do (a+b) + (c+d) instead of (a+c) + (b+d).
// But sel_sum needs (a+c) and (b+d). So the partial sums must be ac and bd.

// Try: compute sum4 as (a+b+c+d) directly (a single 4-input add), and sel_sum separately.
// A 4-input add might be cheaper than 3 two-input adds? Unlikely.

// Let's try a different tactic: optimize the mux tree by using opcode bits more cleverly.
// Current best is 257 with the mux structure from v19.
// Let's try removing the explicit sub_mode compare and use opcode bits.

wire [7:0] not_b = ~input_b;
// sub_mode: opcode = 0001. ac_mode: opcode[2:0] != 001 or opcode[3]=1 (but then ac unused)
// Actually, ac_or_sub is used in: sum4 (000, 111), sel_sum (110), sub (001)
// For 000, 111, 110: we need ac (adder1_b = c, cin = 0)
// For 001: we need sub (adder1_b = ~b, cin = 1)
// sub_mode = ~opcode[3] & (opcode[2:0] == 3'b001)

// Try using simpler condition: only op[2:0] matters since when op[3]=1, result=0 anyway.
// sub_mode = (op[2:0] == 3'b001) since op[3]=1 gives result=0, ac_or_sub value doesn't matter.
// So we can use just op[2:0]:
wire sub_mode2 = (opcode[2:0] == 3'b001);
wire [7:0] adder1_b = sub_mode2 ? not_b : input_c;
wire [7:0] ac_or_sub = input_a + adder1_b + sub_mode2;

wire [7:0] bd = input_b + input_d;
wire [7:0] sum4 = ac_or_sub + bd;
wire [7:0] sel_sum = sel ? ac_or_sub : bd;

wire op_high = opcode[3];
wire [2:0] op = opcode[2:0];

wire [7:0] lo = op[1] ? (op[0] ? (input_a | input_b) : (input_a & input_b))
                       : (op[0] ? ac_or_sub : sum4);
wire [7:0] hi = op[1] ? (op[0] ? sum4 : sel_sum)
                       : (op[0] ? (~input_a) : (input_a ^ input_b));
wire [7:0] alu_result = op[2] ? hi : lo;

assign result = op_high ? 8'b0 : alu_result;
assign zero_flag = ~(|result);

endmodule
