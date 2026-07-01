module example (input clk, in_a, in_b, in_c, in_d, in_e, in_f, in_g, in_h, in_i, output reg sum);
    reg reg_a, reg_b, reg_c;
    reg reg_d, reg_e, reg_f, reg_g, reg_h, reg_i;  // declared to satisfy verilator; yosys auto-infers these
    always@(posedge clk)
        begin
                reg_a <= in_a;
                reg_b <= in_b;
                reg_c <= in_c;
                reg_d <= in_d;
                reg_e <= in_e;
                reg_f <= in_f;
                reg_g <= in_g;
                reg_h <= in_h;
                reg_i <= in_i;
                sum <= reg_a + reg_b + reg_c + reg_d + reg_e + reg_f + reg_g + reg_h + reg_i;
        end
endmodule