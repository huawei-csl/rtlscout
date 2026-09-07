module example(
    input wire clk,
    input wire reset,
    input wire [1:0] input_signal,
    output wire output_signal
);

    // Encoding: A=01, B=00, C=11, D=10, output=state[0]
    // Use 1-lut state encoding trick: encode states so output is a state bit
    // and transition logic is minimal.
    // Trying: A=01, B=00, C=11, D=10 with assign-based next_state
    reg [1:0] state;
    wire i1 = input_signal[1];
    wire i0 = input_signal[0];
    wire s1 = state[1];
    wire s0 = state[0];

    // ns1: A=i1, B=i0, C=i0^i1, D=i0&i1
    // Factor: when s0=1 (A,C): ns1 = s1 ? (i0^i1) : i1
    //         when s0=0 (B,D): ns1 = s1 ? (i0&i1) : i0
    wire ns1 = s0 ? (s1 ? (i0 ^ i1) : i1)
                  : (s1 ? (i0 & i1) : i0);

    // ns0: A=~i0, B=~i0&~i1, C=i1, D=i0^i1
    // Factor: when s0=1 (A,C): ns0 = s1 ? i1 : ~i0
    //         when s0=0 (B,D): ns0 = s1 ? (i0^i1) : (~i0&~i1)
    wire ns0 = s0 ? (s1 ? i1 : ~i0)
                  : (s1 ? (i0 ^ i1) : (~i0 & ~i1));

    always @(posedge clk or posedge reset) begin
        if (reset)
            state <= 2'b01; // A
        else
            state <= {ns1, ns0};
    end

    assign output_signal = state[0];

endmodule
