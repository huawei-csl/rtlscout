module ticket_machine #(
    parameter ON  = 1'b1,
    parameter OFF = 1'b0
) (
    input  clk, clear, ten, twenty,
    output reg ready, dispense, return_sig, bill
);

    // use one-hot encoding to define states
    localparam RDY    = 6'b000001,
               DISP   = 6'b000010,
               RTN    = 6'b000100,
               BILL10 = 6'b001000,
               BILL20 = 6'b010000,
               BILL30 = 6'b100000;

    reg [5:0] State, NextState;

    // update state on clock rising edge
    always @(posedge clk) begin 
        if (clear)
            State <= RDY;
        else
            State <= NextState;
    end

    // output logic based on current state (Moore state machine)
    always @(State) begin
        case (State)
            RDY:    begin
                ready     = ON;
                bill      = OFF;
                dispense  = OFF;
                return_sig = OFF;
            end

            DISP:   begin
                ready     = OFF;
                bill      = OFF;
                dispense  = ON;
                return_sig = OFF;
            end

            RTN:    begin
                ready     = OFF;
                bill      = OFF;
                dispense  = OFF;
                return_sig = ON;
            end

            BILL10: begin
                ready     = OFF;
                bill      = ON;
                dispense  = OFF;
                return_sig = OFF;
            end

            BILL20: begin
                ready     = OFF;
                bill      = ON;
                dispense  = OFF;
                return_sig = OFF;
            end

            BILL30: begin
                ready     = OFF;
                bill      = ON;
                dispense  = OFF;
                return_sig = OFF;
            end

            default: begin
                ready     = OFF;
                bill      = OFF;
                dispense  = OFF;
                return_sig = OFF;
            end
        endcase
    end

    // next state logic
    always @(State or ten or twenty) begin
        case (State)
            RDY:    begin
                if (ten)
                    NextState = BILL10;
                else if (twenty)
                    NextState = BILL20;
                else
                    NextState = RDY;
            end

            BILL10: begin
                if (ten)
                    NextState = BILL20;
                else if (twenty)
                    NextState = BILL30;
                else
                    NextState = BILL10;
            end

            BILL20: begin
                if (ten)
                    NextState = BILL30;
                else if (twenty)
                    NextState = DISP;
                else
                    NextState = BILL20;
            end

            BILL30: begin
                if (ten)
                    NextState = DISP;
                else if (twenty)
                    NextState = RTN;
                else
                    NextState = BILL30;
            end

            DISP:   begin
                    NextState = RDY;
            end

            RTN:    begin
                    NextState = RDY;
            end

            default: begin
                    NextState = RDY;
            end
        endcase
    end

endmodule