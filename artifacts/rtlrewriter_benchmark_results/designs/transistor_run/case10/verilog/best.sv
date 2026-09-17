module example (
    input wire clk,
    input wire reset,
    input wire x,
    output wire output_signal
);

    // output_signal = state[2]
    // S0=100, S1=101, S3=111 (output=1)
    // S2=000, S4=011, S5=010, S6=001 (output=0)
    localparam S0 = 3'b100,
               S1 = 3'b101,
               S2 = 3'b000,
               S3 = 3'b111,
               S4 = 3'b011,
               S5 = 3'b010,
               S6 = 3'b001;

    reg [2:0] next_state;
    reg [2:0] state;

    assign output_signal = state[2];

    always @(posedge clk or posedge reset) begin
        if (reset)
            state <= S0;
        else
            state <= next_state;
    end

    always @(*) begin
        case (state)
            S0:    next_state = x ? S2 : S1;
            S1:    next_state = x ? S5 : S3;
            S2:    next_state = x ? S4 : S5;
            S3:    next_state = x ? S6 : S1;
            S4:    next_state = x ? S2 : S5;
            S5:    next_state = x ? S3 : S4;
            S6:    next_state = x ? S6 : S5;
            default: next_state = S0;
        endcase
    end
endmodule
