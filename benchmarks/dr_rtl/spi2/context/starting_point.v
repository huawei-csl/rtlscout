module spi (
    input wire clk,
    input wire rst,
    input wire [2:0] addr,
    input wire we,
    input wire [31:0] write_data,
    input wire re,
    output reg [31:0] read_data
);
    
    // Register Interface

    localparam ENABLE = 3'b000;
    localparam COMMAND = 3'b001;
    localparam ADDRESS = 3'b010;
    localparam DATA_IN = 3'b011;
    localparam DATA_OUT = 3'b100;
    
    reg enable;
    reg [7:0] command;
    reg [23:0] address;
    reg [31:0] data_in;
    wire [31:0] data_out;

    always @(*) begin
        if (rst) begin
            enable = 0;
            command = 0;
            address = 0;
            data_in = 0;
        end
        else begin
            case (addr)
                ENABLE: begin
                    if (we == 1'b1) begin
                        enable = write_data[0];
                    end
                end
                COMMAND: begin
                    if (we == 1'b1) begin
                        command = write_data[7:0];
                    end
                end
                ADDRESS: begin
                    if (we == 1'b1) begin
                        address = write_data[23:0];
                    end
                end
                DATA_IN: begin
                    if (we == 1'b1) begin
                        data_in = write_data[31:0];
                    end
                end
                DATA_OUT: begin
                    if (re == 1'b1) begin
                        read_data = data_out;
                    end
                end
                // default: 
            endcase
        end
    end

    // Master Slave Interface

    wire cs;
    wire sck;
    wire mosi;
    wire miso;

    spi_master uut_master (
        .clk (clk),
        .rst (rst),
        .en (enable),
        .cs (cs),
        .sck (sck),
        .ext_command_in (command),
        .ext_address_in (address),
        .ext_data_in (data_in),
        .mosi (mosi),
        .miso (miso),
        .ext_data_out (data_out)
    );

    spi_slave uut_slave (
        .clk (clk),
        .rst (rst),
        .cs (cs),
        .sck (sck),
        .mosi (mosi),
        .miso (miso)
    );

endmodule


module spi_master (
    input wire clk,
    input wire rst,
    // Chip Select
    input wire en,
    output reg cs,
    // Serial Clock
    output reg sck,
    // Master Out Slave In
    input wire [7:0] ext_command_in,
    input wire [23:0] ext_address_in,
    input wire [31:0] ext_data_in,
    output reg mosi,
    // Master In Slave Out
    input wire miso,
    output wire [31:0] ext_data_out
);
    
    // Serial Clock
    localparam IDLE = 2'b00;
    localparam ENABLE = 2'b01;
    localparam DATA = 2'b10;

    reg [1:0] current_state, next_state;
    reg clock_count;

    always @(posedge clk) begin
        if (rst) begin
            clock_count <= 0;
        end
        else begin
            if ((current_state == ENABLE) || (current_state == DATA)) begin
                clock_count <= clock_count + 1;
            end
            else begin
                clock_count <= 0;
            end
        end
    end

    // Master Out Slave In

    reg [63:0] data_save;
    reg [5:0] data_count;
    reg data_end;

    always @(posedge clk) begin
        if (rst) begin
            data_save <= 0;
            data_count <= 0;
            data_end <= 0;
        end
        else begin
            if (current_state == DATA) begin
                if (sck == 1) begin
                    // Command, address and data shifted serially on MOSI line from MSB respectively
                    data_save <= {data_save[62:0],1'b0};
                    if (data_count == 63) begin
                        data_count <= 0;
                        data_end <= 1;
                    end
                    else begin
                        data_count <= data_count + 1;
                        data_end <= 0;
                    end
                end
                else begin
                    data_save <= data_save;
                    data_count <= data_count;
                    data_end <= 0;
                end
            end
            else begin
                // Data being written on command ALL ZEROS
                if (ext_command_in == 8'h00) begin
                    data_save <= {ext_command_in,ext_address_in,ext_data_in};
                    data_count <= 0;
                    data_end <= 0;
                end
                else begin
                    data_save <= {ext_command_in,ext_address_in,32'h0000_0000};
                    data_count <= 0;
                    data_end <= 0;
                end
            end
        end
    end

    // Master In Slave Out

    reg [31:0] data_in;

    always @(posedge clk) begin
        if (rst) begin
            data_in <= 0;
        end
        else begin
            if (current_state == DATA) begin
                if (sck == 0) begin
                    // Data being saved from MISO line from LSB
                    if ((data_count >= 32) && (data_count <= 63)) begin
                        data_in <= {data_in[30:0],miso};
                    end
                    else begin
                        data_in <= data_in;
                    end
                end
                else begin
                    data_in <= data_in;
                end
            end
            else begin
                
            end
        end
    end

    assign ext_data_out = data_in;
    
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
                    cs = 1;
                    sck = 1;
                    mosi = 0;
                    if (en == 1'b1) begin
                        next_state = ENABLE;
                    end
                end
                ENABLE: begin
                    cs = 0;
                    sck = ~clock_count;
                    mosi = 0;
                    next_state = DATA;
                end
                DATA: begin
                    cs = 0;
                    sck = ~clock_count;
                    // Command, address and data shifted serially on MOSI line from MSB respectively
                    mosi = data_save[63];
                    if (data_end == 1'b1) begin
                        sck = 1;
                        next_state = IDLE;
                    end
                end
                default: next_state = IDLE;
            endcase
        end
    end

endmodule

module spi_slave (
    input wire clk,
    input wire rst,
    // Chip Select
    input wire cs,
    // Serial Clock
    input wire sck,
    // Master Out Slave In
    input wire mosi,
    // Master In Slave Out
    output reg miso
);

    reg [5:0] data_count;
    reg data_end;
    localparam IDLE = 2'b00;
    localparam DATA = 2'b10;
    localparam DISABLE = 2'b11;

    reg [1:0] current_state, next_state;

    always @(posedge clk) begin
        if (rst) begin
            data_count <= 0;
            data_end <= 0;
        end
        else begin
            if (current_state == DATA) begin
                if (sck == 1) begin
                    if (data_count == 63) begin
                        data_count <= 0;
                        data_end <= 1;
                    end
                    else begin
                        data_count <= data_count + 1;
                        data_end <= 0;
                    end
                end
                else begin
                    data_count <= data_count;
                    data_end <= 0;
                end
            end
            else begin
                data_count <= 0;
                data_end <= 0;
            end
        end
    end

    // Master Out Slave In

    reg [7:0] command_save;
    reg [23:0] address_save;
    reg [31:0] data_save;

    always @(posedge sck) begin
        if (rst) begin
            command_save <= 0;
            address_save <= 0;
            data_save <= 0;
        end
        else begin
            if (current_state == DATA) begin
                // Command, address and data saved from MOSI line from MSB respectively
                if ((data_count >= 0) && (data_count < 8)) begin
                    command_save <= {command_save[6:0],mosi};
                end
                else if ((data_count >= 8) && (data_count < 32)) begin
                    address_save <= {address_save[22:0],mosi};
                end
                else if ((data_count >= 32) && (data_count <= 63)) begin
                    data_save <= {data_save[30:0],mosi};
                end
                else begin
                    command_save <= command_save;
                    address_save <= address_save;
                    data_save <= data_save;
                end        
            end
            else begin
                command_save <= command_save;
                address_save <= address_save;
                data_save <= data_save;
            end
        end
    end

    // Master In Slave Out

    reg [31:0] data_out;

    always @(negedge sck) begin
        if (rst) begin
            data_out <= 0;
        end
        else begin
            if (current_state == DATA) begin
                if ((data_count > 1) && (data_count < 8)) begin
                    data_out <= data_save;
                end
                else if ((data_count >= 8) && (data_count <= 63)) begin
                    // Data shifted serially on MISO line from MSB respectively
                    if ((data_count > 32) && (data_count <= 63)) begin
                        data_out <= {data_out[30:0],1'b0};
                    end
                    else begin
                        data_out <= data_out;
                    end
                end
                else begin
                    data_out <= data_out;
                end
            end
            else begin
                data_out <= data_out;
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
            case (next_state)
                IDLE: begin
                    miso = 0;
                    if (cs == 1'b0) begin
                        next_state = DATA;
                    end
                end
                DATA: begin
                    if ((data_count >= 32) && (data_count <= 63)) begin
                        // Data shifted serially on MOSI line from MSB respectively on command ALL ONES
                        if (command_save == 8'hff) begin
                            miso = data_out[31];
                        end
                        else begin
                            miso = 0;
                        end
                        
                    end
                    else begin
                        miso = 0;
                    end            
                    
                    if (data_end == 1'b1) begin
                        next_state = DISABLE;
                    end
                end
                DISABLE: begin
                    miso = 0;
                    if (cs == 1'b1) begin
                        next_state = IDLE;
                    end
                end
                default: next_state = IDLE;
            endcase
        end
    end

endmodule