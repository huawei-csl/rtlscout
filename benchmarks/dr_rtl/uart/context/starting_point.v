module uart_top_design (
    input wire clk,
    input wire rst,
    input wire [1:0] address,
    input wire [31:0] write_data,
    input wire we,
    output wire tx,
    input wire rx,
    input wire re,
    output reg [7:0] read_data
);
    
    // Register Interface

    localparam BAUD_DATA = 0;
    localparam ENABLE = 1;
    localparam TX_DATA = 2;
    localparam RX_DATA = 3;

    reg [31:0] baud_division;
    reg enable;
    reg [7:0] data_out;
    wire [7:0] data_in;

    always @(*) begin
        if (rst) begin
            baud_division <= 0;
            enable <= 0;
            data_out <= 0;
        end
        else begin
            casex (address)
                BAUD_DATA: begin
                    if (we) begin
                        baud_division <= write_data;
                    end
                end
                ENABLE: begin
                    if (we) begin
                        enable <= write_data[0];
                    end
                end
                TX_DATA: begin
                    if (we) begin
                        data_out <= write_data[7:0];
                    end
                end
                RX_DATA: begin
                    if (re) begin
                        read_data <= data_in;
                    end
                end
                // default: 
            endcase
        end
    end

    // Baud Rate Generator

    wire baud_tick;

    uart_baud_rate uut_baud_rate (
        .clk (clk),
        .rst (rst),
        .baud_division (baud_division),
        .en (enable),
        .baud_tick (baud_tick)
    );

    // Transmitter

    uart_tx uut_tx (
        .clk (clk),
        .rst (rst),
        .baud_tick (baud_tick),
        .ext_data_in (data_out),
        .en (enable),
        .tx (tx)
    );

    // Receiver

    uart_rx uut_rx (
        .clk (clk),
        .rst (rst),
        .baud_tick (baud_tick),
        .rx (rx),
        .ext_data_out (data_in)
    );
    
endmodule



module uart_baud_rate (
    input wire clk,
    input wire rst,
    input wire [31:0] baud_division,
    input wire en,
    output reg baud_tick
);

    /*
    Clock Frequency: f  = 20 MHz
    Baud Rate:       Bd = 9600 bit/s
    
    Baud Division = ____f____
                     16 x Bd
    */

    reg temp_en;
    reg delayed_en;

    always @(posedge clk) begin
        if (rst) begin
            temp_en <= 0;
            delayed_en <= 0;
        end
        else begin
            if ((en == 0) || (en == 1)) begin
                temp_en <= en;
                delayed_en <= temp_en;
            end
            else begin
                temp_en <= temp_en;
                delayed_en <= delayed_en;
            end
        end
    end
    
    reg [31:0] baud_count;

    always @(posedge clk) begin
        if (rst) begin
            baud_count <= 0;
            baud_tick <= 0;
        end
        else begin
            if (baud_division != 0) begin
                if ((en == 1) && (delayed_en == 0)) begin
                    baud_count <= 1;
                    baud_tick <= baud_tick;
                end
                else if (baud_count == baud_division) begin
                    baud_count <= 0;
                    baud_tick <= 1;
                end
                else begin
                    baud_count <= baud_count + 1;
                    baud_tick <= 0;
                end
            end
            else begin
                baud_count <= 0;
                baud_tick <= 0;
            end
        end
    end
    
endmodule



module uart_rx (
    input clk,
    input rst,
    input baud_tick,
    input rx,
    output reg [7:0] ext_data_out
);
    
    reg [3:0] count_16;
    reg count_16_indication;
    localparam IDLE = 0;
    localparam START = 1;
    localparam DATA = 2;
    localparam STOP = 3;

    reg [1:0] current_state, next_state;

    always @(posedge clk) begin
        if (rst) begin
            count_16 <= 0;
            count_16_indication <= 0;
        end
        else begin
            if (baud_tick == 1) begin
                if (current_state == START) begin
                    if (count_16 == 7) begin
                        count_16 <= 0;
                        count_16_indication <= 1;
                    end
                    else begin
                        count_16 <= count_16 + 1;
                        count_16_indication <= 0;
                    end
                end
                else if ((current_state == DATA) || (current_state == STOP)) begin
                    if (count_16 == 15) begin
                        count_16 <= 0;
                        count_16_indication <= 1;
                    end
                    else begin
                        count_16 <= count_16 + 1;
                        count_16_indication <= 0;
                    end
                end
                else begin
                    count_16 <= 0;
                    count_16_indication <= 0;
                end
            end
            else begin
                count_16 <= count_16;
                count_16_indication <= 0;
            end
        end
    end

    reg [2:0] count_8;
    reg count_8_indication;
    reg [7:0] data_save;

    always @(posedge clk) begin
        if (rst) begin
            count_8 <= 0;
            count_8_indication <= 0;
            data_save <= 0;
        end
        else begin
            if (current_state == DATA) begin
                if ((baud_tick == 1) && (count_16 == 15)) begin
                    if (count_8 == 7) begin
                        count_8 <= 0;
                        count_8_indication <= 1;
                        data_save <= {data_save[6:0],rx};
                    end
                    else begin
                        count_8 <= count_8 + 1;
                        count_8_indication <= 0;
                        data_save <= {data_save[6:0],rx};
                    end
                end
                else begin
                    count_8 <= count_8;
                    count_8_indication <= 0;
                    data_save <= data_save;
                end
            end
            else begin
                count_8 <= 0;
                count_8_indication <= 0;
                data_save <= data_save;
            end
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            ext_data_out <= 0;
        end
        else begin
            ext_data_out <= data_save;
        end
    end

    // Finite State Machine

    

    always @(posedge clk) begin
        if (rst) begin
            current_state <= 0;
        end
        else begin
            current_state <= next_state;
        end
    end

    always @(*) begin
        if (rst) begin
            next_state = 0;
        end
        else begin
            case (current_state)
                IDLE: begin
                    if (rx == 0) begin
                        next_state = START;
                    end
                end
                START: begin
                    if ((count_16_indication == 1) && (rx == 0)) begin
                        next_state = DATA;
                    end
                end
                DATA: begin
                    if (count_8_indication == 1) begin
                        next_state = STOP;
                    end
                end
                STOP: begin
                    if ((count_16_indication == 1) && (rx == 1)) begin
                        next_state = IDLE;
                    end
                end
                default: next_state = IDLE;
            endcase
        end
    end

endmodule


module uart_tx (
    input wire clk,
    input wire rst,
    input wire baud_tick,
    input wire [7:0] ext_data_in,
    input wire en,
    output reg tx
);

    reg [3:0] count_16;
    reg count_16_indication;
    localparam IDLE = 0;
    localparam START = 1;
    localparam DATA = 2;
    localparam STOP = 3;

    reg [1:0] current_state, next_state;

    always @(posedge clk) begin
        if (rst) begin
            count_16 <= 0;
            count_16_indication <= 0;
        end
        else begin
            if (baud_tick == 1) begin
                if (current_state != IDLE) begin
                    if (count_16 == 15) begin
                        count_16 <= 0;
                        count_16_indication <= 1;
                    end
                    else begin
                        count_16 <= count_16 + 1;
                        count_16_indication <= 0;
                    end
                end
                else begin
                    count_16 <= 0;
                    count_16_indication <= 0;
                end
            end
            else begin
                count_16 <= count_16;
                count_16_indication <= 0;
            end
        end
    end

    reg [2:0] count_8;
    reg count_8_indication;
    reg [7:0] data_save;

    always @(posedge clk) begin
        if (rst) begin
            count_8 <= 0;
            count_8_indication <= 0;
            data_save <= 0;
        end
        else begin
            if (current_state == DATA) begin
                if ((baud_tick == 1) && (count_16 == 15)) begin
                    if (count_8 == 7) begin
                        count_8 <= 0;
                        count_8_indication <= 1;
                        data_save <= data_save;
                    end
                    else begin
                        count_8 <= count_8 + 1;
                        count_8_indication <= 0;
                        data_save <= {data_save[6:0],1'b0};
                    end
                end
                else begin
                    count_8 <= count_8;
                    count_8_indication <= 0;
                    data_save <= data_save;
                end
            end
            else begin
                count_8 <= 0;
                count_8_indication <= 0;
                data_save <= ext_data_in;
            end
        end
    end
    
    // Finite State Machine

    

    always @(posedge clk) begin
        if (rst) begin
            current_state <= 0;
        end
        else begin
            current_state <= next_state;
        end
    end

    always @(*) begin
        if (rst) begin
            next_state = 0;
        end
        else begin
            case (current_state)
                IDLE: begin
                    tx = 1;
                    if (en == 1) begin
                        next_state = START;
                    end
                end
                START: begin
                    tx = 0;
                    if (count_16_indication == 1) begin
                        next_state = DATA;
                    end
                end
                DATA: begin
                    tx = data_save[7];
                    if (count_8_indication == 1) begin
                        next_state = STOP;
                    end
                end
                STOP: begin
                    tx = 1;
                    if (count_16_indication == 1) begin
                        next_state = IDLE;
                    end
                end
                default: next_state = IDLE;
            endcase
        end
    end

endmodule