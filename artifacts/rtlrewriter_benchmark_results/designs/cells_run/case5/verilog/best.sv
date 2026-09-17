// Inverted carry chain: nc = ~c, np = ~p (XNOR)
// c[i+1] = p[i] ? c[i] : a[i]
// nc[i+1] = ~c[i+1] = p[i] ? ~c[i] : ~a[i] = p[i] ? nc[i] : ~a[i]
// sum[i] = p[i] ^ c[i] = (~np[i]) ^ (~nc[i]) = np[i] ^ nc[i]
// sum[8] = c[8] = ~nc[8]
module example(
    input  [7:0] a,
    input  [7:0] b,
    output [8:0] sum
);
    wire [7:0] p = a ^ b;
    wire [7:0] np = ~p;  // XNOR
    wire [8:0] nc;       // inverted carry
    assign nc[0] = 1'b1;
    genvar i;
    generate
        for (i = 0; i < 8; i = i + 1)
            assign nc[i+1] = p[i] ? nc[i] : ~a[i];
    endgenerate
    assign sum = {~nc[8], np ^ nc[7:0]};
endmodule
