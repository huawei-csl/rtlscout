module example (
    input wire clk,
    input wire reset,
    input wire x,
    output reg output_signal
);

    // State encoding
    localparam S0 = 3'b000,
               S1 = 3'b001,
               S2 = 3'b010,
               S3 = 3'b011,
               S4 = 3'b100,
               S5 = 3'b101,
               S6 = 3'b110;

    reg [2:0] next_state;
    reg [2:0] state;  // 3-bit state representation for S0 to S6

    // Sequential logic for state transitions
    always @(posedge clk or posedge reset) begin
        if (reset) begin
            state <= S0;  // Reset to state S0
        end else begin
            state <= next_state;
        end
    end

    // Combinational logic for next state and output
    always @(*) begin
        case (state)
            S0: begin
                next_state = x ? S2 : S1;
                output_signal = 1'b1;
            end
            S1: begin
                next_state = x ? S5 : S3;
                output_signal = 1'b1;
            end
            S2: begin
                next_state = x ? S4 : S5;
                output_signal = 1'b0;
            end
            S3: begin
                next_state = x ? S6 : S1;
                output_signal = 1'b1;
            end
            S4: begin
                next_state = x ? S2 : S5;
                output_signal = 1'b0;
            end
            S5: begin
                next_state = x ? S3 : S4;
                output_signal = 1'b0;
            end
            S6: begin
                next_state = x ? S6 : S5;
                output_signal = 1'b0;
            end
            default: begin
                next_state = S0;  // Default to state S0 if an undefined state is encountered
                output_signal = 1'b0;
            end
        endcase
    end
endmodule
