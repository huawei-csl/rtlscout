module example (input clk, in_a, in_b, in_c, in_d, in_e, in_f, in_g, in_h, in_i, output reg sum);
    reg r1;
    always@(posedge clk)
        begin
                r1 <= in_a ^ in_b ^ in_c ^ in_d ^ in_e ^ in_f ^ in_g ^ in_h ^ in_i;
                sum <= r1;
        end
endmodule
