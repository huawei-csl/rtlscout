module example (
    input wire clk,
    input wire reset,
    input wire x,
    output wire output_signal
);
    reg [1:0] s;
    // S03=11, S1=01, S5=10, S246=00. Output = s[0].
    // ns1: 00:~x, 01:1, 10:x, 11:0
    // ns0: 00:0, 01:~x, 10:x, 11:~x
    wire ns1 = s[1] ? (~s[0] & x) : (s[0] | ~x);
    wire ns0 = (s[0] & ~x) | (s[1] & ~s[0] & x);

    always @(posedge clk or posedge reset) begin
        if (reset) s <= 2'b11;
        else begin s[1] <= ns1; s[0] <= ns0; end
    end

    assign output_signal = s[0];
endmodule
