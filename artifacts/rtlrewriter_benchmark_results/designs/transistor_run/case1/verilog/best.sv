// Ultimate reduction: XOR all 9 into a single register
// Stage 1: 1 FF (XOR of all inputs)
// Stage 2: just pass through to output FF
// Wait - this collapses to 1 cycle latency effectively
// We need 2 cycle latency. Let's use 1 intermediate FF.

module example (input clk, in_a, in_b, in_c, in_d, in_e, in_f, in_g, in_h, in_i, output reg sum);
    reg r0;
    always @(posedge clk) begin
        r0 <= in_a ^ in_b ^ in_c ^ in_d ^ in_e ^ in_f ^ in_g ^ in_h ^ in_i;
        sum <= r0;
    end
endmodule
