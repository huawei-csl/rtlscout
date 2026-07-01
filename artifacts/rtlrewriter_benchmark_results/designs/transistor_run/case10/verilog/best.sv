module example (
    input wire clk,
    input wire reset,
    input wire x,
    output wire output_signal
);

    reg [2:0] state;
    assign output_signal = state[0];

    wire s2 = state[2], s1 = state[1], s0 = state[0];
    wire [2:0] ns;

    // Encoding: S0=101, S1=011, S2=100, S3=001, S4=110, S5=000, S6=010
    // Unused: 111
    
    // Try ALL x-mux form:
    // ns2: x ? s2 : (~s2&~s1&~s0)
    // ns1: x ? (s2&~s1&~s0 | ~s2&s0&~s1 | ~s2&~s0&s1) : (~s1&~s2 | ~s1&s0)
    // Simplify ns1(x=1): s2&~s1&~s0 | ~s2&(s0^s1)
    // Simplify ns1(x=0): ~s1&(~s2|s0)
    // ns0: x ? (~s2&~s1&~s0) : s0
    
    // What if I express ns1 differently:
    // ns1(x=1) = s2&~s1&~s0 | ~s2&s0&~s1 | ~s2&~s0&s1
    //          = ~s1&~s0&s2 | ~s1&s0&~s2 | s1&~s0&~s2  
    //          = ~s0&(~s1&s2|s1&~s2) | ~s1&s0&~s2
    //          = ~s0&(s1^s2) | ~s1&s0&~s2
    //          = ~s0&s1&~s2 | ~s0&~s1&s2 | s0&~s1&~s2
    //          = ~s2&(~s0&s1|s0&~s1) | ~s0&~s1&s2
    //          = ~s2&(s0^s1) | s2&~s1&~s0
    
    // The function is: exactly one of {s0,s1,s2} is 1 OR (s2=1,s1=0,s0=0)
    // Actually s2&~s1&~s0 is "only s2 is 1", ~s2&s0&~s1 is "only s0", ~s2&~s0&s1 is "only s1"
    // So it's exactly popcount(s)=1.
    // With Don't Care at s=111: popcount(111)=3≠1. So DC=0 for this.
    // Can we express popcount==1 compactly?
    // (s0^s1^s2) & ~(s0&s1) & ~(s0&s2) & ~(s1&s2)
    // = (s0^s1^s2) & ~(s0&s1 | s0&s2 | s1&s2)
    // Not simpler. The XOR-based form is probably not better for synthesis.
    
    // Let me try a different factoring of ns1:
    // ns1 = ~s1 & (x ? (~s2&s0|s2&~s0) : (~s2|s0)) | s1&x&~s2&~s0
    // = ~s1 & (x ? (s0^s2) : (~s2|s0)) | s1&x&~s2&~s0
    // This separates the s1=1 contribution.

    // Or try writing everything with NAND-style:
    // ns2 = x & s2 | ~x & ~(s2|s1|s0) -- this is basically the same
    
    // Let me try: what if reset value changes? S0=101 requires two set bits.
    // What if S0=001? That's only one set bit.
    // Then we need: S0=001(odd), and reassign other states.
    // S0=001, S1=?, S3=? (odd: from 011,101,111 pick 2)
    // S2,S4,S5,S6 (even: 000,010,100,110)
    
    // Try: S0=001, S1=011, S3=101
    // S2=000, S4=010, S5=100, S6=110  
    // Unused: 111
    // This is the same as the original v30 encoding! (S0=001=S3 in v30, etc - wait no)
    // In v30: S0=101, S1=011, S2=000, S3=001, S4=010, S5=100, S6=110
    // This would be: S0=001, S1=011, S2=000, S3=101, S4=010, S5=100, S6=110
    // Different from v30 (S0 and S3 swapped)
    
    // Try: S0=001, S1=011, S3=101, S2=100, S4=110, S5=000, S6=010
    // Same as design_v48 encoding but with S0=001 and S3=101 swapped? No wait...
    // design_v48 had S0=101, S1=011, S2=100, S3=001, S4=110, S5=000, S6=010
    // If we swap S0<->S3: S0=001, S1=011, S2=100, S3=101, S4=110, S5=000, S6=010
    // This swaps the roles of S0 and S3 in the encoding. The transition table changes!
    
    // Actually, let me just try: can the SAME encoding with a different reset state give lower cost?
    // No, reset state = S0 is fixed by the spec.
    
    // Let me try yet another approach: maybe I can combine ns[2] and ns[0] since they 
    // share the same expression for x=1:
    // ns[2] = x ? s2 : zero_state
    // ns[0] = x ? zero_state : s0
    // where zero_state = ~s2&~s1&~s0
    // These two could share the computation of zero_state.
    // Yosys likely already does this. Let me see if I can restructure.
    
    // What if I try a completely different encoding that makes ns even simpler?
    // Let me try S0=101, S1=001, S2=100, S3=011, S4=110, S5=000, S6=010
    // (Swapped S1 and S3 from v48)
    // Output=1: S0(101), S1(001), S3(011) - odd ✓
    // Output=0: S2(100), S4(110), S5(000), S6(010) - even ✓
    // Unused: 111

    // Transitions with new encoding:
    // S0(101): x=0->S1(001), x=1->S2(100)
    // S1(001): x=0->S3(011), x=1->S5(000)
    // S2(100): x=0->S5(000), x=1->S4(110)
    // S3(011): x=0->S1(001), x=1->S6(010)
    // S4(110): x=0->S5(000), x=1->S2(100)
    // S5(000): x=0->S4(110), x=1->S3(011)
    // S6(010): x=0->S5(000), x=1->S6(010)
    
    // Truth table:
    // s2 s1 s0 x | ns2 ns1 ns0
    // 0  0  0  0 |  1   1   0   S5->S4(110)
    // 0  0  0  1 |  0   1   1   S5->S3(011)
    // 0  0  1  0 |  0   1   1   S1->S3(011)
    // 0  0  1  1 |  0   0   0   S1->S5(000)
    // 0  1  0  0 |  0   0   0   S6->S5(000)
    // 0  1  0  1 |  0   1   0   S6->S6(010)
    // 0  1  1  0 |  0   0   1   S3->S1(001)
    // 0  1  1  1 |  0   1   0   S3->S6(010)
    // 1  0  0  0 |  0   0   0   S2->S5(000)
    // 1  0  0  1 |  1   1   0   S2->S4(110)
    // 1  0  1  0 |  0   0   1   S0->S1(001)
    // 1  0  1  1 |  1   0   0   S0->S2(100)
    // 1  1  0  0 |  0   0   0   S4->S5(000)
    // 1  1  0  1 |  1   0   0   S4->S2(100)
    // 1  1  1  x |  x   x   x   unused
    
    // ns2: ones={0,9,11,13} DC{14,15}
    // Same as v48! Because S0<->S3 swap doesn't affect ns2 for these entries.
    // Wait, let me check. In v48, ns2 ones were {0,9,11,13}.
    // Here: 0: S5->S4(110)=✓, 9: S2->S4(110)=✓, 11: S0->S2(100)=✓, 13: S4->S2(100)=✓
    // Same! ns2 = x ? s2 : (~s2&~s1&~s0) -- same formula
    
    // ns1: ones={0,1,2,5,7,9} DC{14,15}
    //  0: ~s2&~s1&~s0&~x -> 1
    //  1: ~s2&~s1&~s0&x -> 1
    //  2: ~s2&~s1&s0&~x -> 1
    //  5: ~s2&s1&~s0&x -> 1
    //  7: ~s2&s1&s0&x -> 1
    //  9: s2&~s1&~s0&x -> 1
    // {0,1}: ~s2&~s1&~s0
    // {2}: ~s2&~s1&s0&~x
    // {0,1,2}: ~s2&~s1&(~s0|~x) = ~s2&~s1&~(s0&x)
    // {5,7}: ~s2&s1&x
    // {9}: s2&~s1&~s0&x
    // ns1 = ~s2&~s1&~(s0&x) | ~s2&s1&x | s2&~s1&~s0&x
    //      = ~s2&(~s1&~(s0&x) | s1&x) | s2&~s1&~s0&x
    //      = ~s2&(~s1&~s0 | ~s1&~x | s1&x) | s2&~s1&~s0&x
    //      = ~s2&(~s1&~s0 | (s1?x:~x) ... hmm) 
    // Actually: ~s1&~(s0&x) | s1&x = ~s1&~s0 | ~s1&~x | s1&x
    //   = ~s1&~s0 | (~s1&~x | s1&x) = ~s1&~s0 | (s1 XNOR ~x) = ~s1&~s0 | (s1^~x)
    //   Wait: ~s1&~x | s1&x = ~(s1^x). So: ~s1&~s0 | ~(s1^x)
    // So ns1 = ~s2&(~s1&~s0 | ~(s1^x)) | s2&~s1&~s0&x
    //        = ~s2&(~s1&~s0 | s1&x | ~s1&~x) | s2&~s1&~s0&x  
    //        Hmm: ~s1&~s0 | ~(s1^x) = ~s1&~s0 | s1&x | ~s1&~x
    //        = ~s1&(~s0|~x) | s1&x = ~s1&~(s0&x) | s1&x
    //        Going in circles. Let me try mux:
    // x=0: ones={0,2}. ~s2&~s1 (all s0 for x=0: {0,2,4,6,8,10}: ~s2&~s1 = entries 0,2 ✓)
    // x=1: ones={1,5,7,9}. 
    //   1: ~s2&~s1&~s0
    //   5: ~s2&s1&~s0
    //   7: ~s2&s1&s0
    //   9: s2&~s1&~s0
    //   {1,5}: ~s2&~s0
    //   {7}: ~s2&s1&s0
    //   {1,5,7}: ~s2&(~s0|s1&s0) = ~s2&(~s0|s1) -- absorption
    //   {9}: s2&~s1&~s0
    //   Full x=1: ~s2&(~s0|s1) | s2&~s1&~s0 = ~s0&(~s2|s2&~s1) | ~s2&s1 = ~s0&(~s2|~s1) | ~s2&s1
    //     absorption: ~s2|~s1 covers ~s2. So ~s0&(~s2|~s1)|~s2&s1 = ~s0&~s1 | ~s0&~s2 | ~s2&s1
    //     = ~s0&~s1 | ~s2&(~s0|s1) = ~s0&~s1 | ~s2&(s1|~s0) -- same as ~s0&~s1 | ~s2&s1 | ~s2&~s0
    //     = ~s0&(~s1|~s2) | ~s2&s1 = ~(s0&(s1|s2)) | ~s2&s1 -- hmm
    //   Or: ~s2&(~s0|s1) | s2&~s1&~s0 = (s1|~s0)&(~s2|~s1) -- maybe
    //   Let me verify: (s1|~s0)&(~s2|~s1) = s1&~s2 | s1&~s1 | ~s0&~s2 | ~s0&~s1 = s1&~s2 | ~s0&~s2 | ~s0&~s1
    //     = ~s2&(s1|~s0) | ~s0&~s1 -- yes this matches!
    //   But product of sums: (s1|~s0)&(~s2|~s1) = ~(~s1&s0) & ~(s2&s1) = NAND form
    //   = ~((~s1&s0) | (s2&s1)) -- De Morgan
    //   Hmm: ns1(x=1) = ~(~s1&s0 | s2&s1) -- let me verify:
    //   1(~s2,~s1,~s0): ~(1&0|0)=~0=1 ✓
    //   3(~s2,~s1,s0): ~(1&1|0)=~1=0. But ns1=0 for entry 3 ✓ (S1->S5)
    //   5(~s2,s1,~s0): ~(0|0)=1 ✓ 
    //   7(~s2,s1,s0): ~(0|0)=1 ✓
    //   9(s2,~s1,~s0): ~(1&0|0)=1 ✓
    //   11(s2,~s1,s0): ~(1|0)=0 ✓
    //   13(s2,s1,~s0): ~(0|1)=0 ✓
    //   So ns1(x=1) = ~(~s1&s0 | s2&s1) = ~(s0&~s1) & ~(s2&s1) -- two NANDs + AND!
    //   = NOR(NAND(~s1,s0), NAND(~s2,~s1))... hmm, it's NOR(s0&~s1, s2&s1)
    //   Or equivalently: NAND(s0,~s1) AND NAND(s2,s1)... which is AND of two NANDs
    //   
    // ns1 = x ? ~(~s1&s0 | s2&s1) : (~s2&~s1)
    //   = x ? ~(s0&~s1 | s2&s1) : ~(s2|s1)
    //   Hmm interesting - both arms use NOR/NAND-like structures.
    
    // ns0: ones={1,2,6,10} DC{14,15}
    // Same as before? 2:~s2&~s1&s0&~x, 6:~s2&s1&s0&~x, 10:s2&~s1&s0&~x, 1:~s2&~s1&~s0&x
    // Wait: entry 1 is S5(000)->S3(011). ns0=1.
    //       entry 2 is S1(001)->S3(011). ns0=1.
    //       entry 6 is S3(011)->S1(001). ns0=1.
    //       entry 10 is S0(101)->S1(001). ns0=1.
    // {2,6,10}: s0&~x (with DC14: s0&~x covers 14 too) ✓
    // {1}: ~s2&~s1&~s0&x
    // ns0 = s0&~x | ~s2&~s1&~s0&x = x ? (~s2&~s1&~s0) : s0 -- same as v48!
    
    // So this encoding gives EXACTLY the same logic as v48 for ns2 and ns0,
    // but different ns1. Let me see if this ns1 is better.
    
    // ns1 = x ? ~(s0&~s1 | s2&s1) : ~s2&~s1
    // Hmm, ~s2&~s1 = ~(s2|s1) = NOR(s2,s1)
    // ns1 = x ? ~(s0&~s1 | s2&s1) : ~(s2|s1)

    assign ns[2] = x ? s2 : ~s2 & ~s1 & ~s0;
    assign ns[1] = x ? ~(s0 & ~s1 | s2 & s1) : ~s2 & ~s1;
    assign ns[0] = x ? ~s2 & ~s1 & ~s0 : s0;

    always @(posedge clk or posedge reset) begin
        if (reset)
            state <= 3'b101;
        else
            state <= ns;
    end
endmodule
