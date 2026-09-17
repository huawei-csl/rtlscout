module example(
    input wire clk,
    input wire reset,
    input wire [1:0] input_signal,
    output reg output_signal
);

    parameter S0 = 3'b000, S1 = 3'b001, S2 = 3'b010,
              S3 = 3'b011, S4 = 3'b100, S5 = 3'b101;

    reg [2:0] current_state, next_state;

    always @(current_state) begin
        output_signal = 0;
        case (current_state)
            S0: output_signal = 1;
            S2: output_signal = 1;
            S4: output_signal = 1;
            default: output_signal = 0;
        endcase
    end

    always @(posedge clk or posedge reset) begin
        if (reset)
            current_state <= S0;
        else
            current_state <= next_state;
    end

    always @(*) begin
        next_state = current_state;
        case (current_state)
            S0: case (input_signal)
                2'b00: next_state = S0;
                2'b01: next_state = S1;
                2'b10: next_state = S2;
                2'b11: next_state = S3;
            endcase
            S1: case (input_signal)
                2'b00: next_state = S0;
                2'b01: next_state = S3;
                2'b10: next_state = S1;
                2'b11: next_state = S5;
            endcase
            S2: case (input_signal)
                2'b00: next_state = S1;
                2'b01: next_state = S3;
                2'b10: next_state = S2;
                2'b11: next_state = S4;
            endcase
            S3: case (input_signal)
                2'b00: next_state = S1;
                2'b01: next_state = S0;
                2'b10: next_state = S4;
                2'b11: next_state = S5;
            endcase
            S4: case (input_signal)
                2'b00: next_state = S0;
                2'b01: next_state = S1;
                2'b10: next_state = S2;
                2'b11: next_state = S5;
            endcase
            S5: case (input_signal)
                2'b00: next_state = S1;
                2'b01: next_state = S4;
                2'b10: next_state = S0;
                2'b11: next_state = S5;
            endcase
        endcase
    end
endmodule
