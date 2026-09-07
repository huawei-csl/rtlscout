module example (input clk, in_a, in_b, in_c, in_d, in_e, in_f, in_g, in_h, in_i, output reg sum);
    reg p;
    always @(posedge clk) begin
        p <= in_a ^ in_b ^ in_c ^ in_d ^ in_e ^ in_f ^ in_g ^ in_h ^ in_i;
        sum <= p;
    end
endmodule
