module example(
    input [7:0] a,
    input [7:0] b,
    input [7:0] c,
    input [7:0] d,
    output [9:0] sum
);
    // Attempt: optimize the generate function
    // For a+b, instead of computing g=a&b and p=a^b separately,
    // note that the carry can also be expressed as:
    // c[i+1] = (a[i] & b[i]) | ((a[i] ^ b[i]) & c[i])
    //        = (a[i] & b[i]) | (a[i] & c[i]) | (b[i] & c[i]) - a[i] & b[i] & c[i]
    // Wait, that's not right. Let me recalculate:
    // (a&b) | ((a^b) & c) = (a&b) | ((a&~b | ~a&b) & c)
    // = a&b | a&~b&c | ~a&b&c
    // = a&b | a&c&(~b) | b&c&(~a)
    // = a&(b | c&~b) | b&c&~a
    // = a&(b|c) | b&c&~a
    // = a&b | a&c | b&c&~a
    // = a&b | a&c | b&c - a&b&c... hmm
    // Actually: (a&b)|(a^b)&c = a&b | (a⊕b)&c
    // For carry: this IS the standard formula and equals majority(a,b,c).
    // majority(a,b,c) = (a&b)|(a&c)|(b&c)
    
    // So carry[i+1] = maj(a[i], b[i], c[i])
    // This is provably identical to g|(p&c).
    // The question is just how Yosys maps it.
    
    // Let me try yet another approach: what if we provide the carry
    // in a different form that helps Yosys?
    
    // Try: express carry as (a|b) & (a|c) & (b|c)
    // = (a|b)&(a|c)&(b|c)
    // This is the same as majority but expressed with ORs and ANDs.
    // It might map to OAI/AOI cells differently.
    
    // OK, I've been trying many things. Let me try one more completely different
    // structural idea: use a single wide adder by treating all 4 inputs as
    // a single 32-bit value and using slice-based addition.
    
    // Actually, let me try to use the synthesizer more effectively.
    // What if we help Yosys by breaking the design into smaller modules?
    
    wire [8:0] ab_sum;
    wire [8:0] cd_sum;
    
    adder8 add_ab(.a(a), .b(b), .s(ab_sum));
    adder8 add_cd(.a(c), .b(d), .s(cd_sum));
    
    // Final 9-bit addition
    wire [8:0] f_g = ab_sum & cd_sum;
    wire [8:0] f_p = ab_sum ^ cd_sum;
    wire [9:0] f_c;
    assign f_c[0] = 1'b0;
    genvar i;
    generate for (i = 0; i < 9; i = i+1) begin : fc
        assign f_c[i+1] = f_g[i] | (f_p[i] & f_c[i]);
    end endgenerate
    assign sum[8:0] = f_p ^ f_c[8:0];
    assign sum[9] = f_c[9];
endmodule

module adder8(
    input [7:0] a,
    input [7:0] b,
    output [8:0] s
);
    wire [7:0] g = a & b;
    wire [7:0] p = a ^ b;
    wire [8:0] c;
    assign c[0] = 1'b0;
    genvar i;
    generate for (i = 0; i < 8; i = i+1) begin : carry
        assign c[i+1] = g[i] | (p[i] & c[i]);
    end endgenerate
    assign s[7:0] = p ^ c[7:0];
    assign s[8] = c[8];
endmodule
