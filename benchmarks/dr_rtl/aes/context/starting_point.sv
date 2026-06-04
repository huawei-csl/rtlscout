module key_expansion_128aes #(
    parameter NBW_KEY = 'd128,
    parameter NBW_OUT = 'd1408
) (
    input  logic               clk,
    input  logic               rst_async_n,
    input  logic               i_start,
    input  logic [NBW_KEY-1:0] i_key,
    output logic               o_done,
    output logic [NBW_OUT-1:0] o_expanded_key
);

localparam NBW_BYTE = 'd8;
localparam STEPS = 'd10;
localparam NBW_WORD = 'd32;

// Auxiliary wires
logic [NBW_BYTE-1:0] Rcon   [STEPS];
logic [NBW_KEY-1:0] valid_key;
logic [NBW_KEY-1:0] step_key[STEPS];
logic [NBW_OUT-1:0] expanded_key_nx;
logic [NBW_OUT-1:0] expanded_key_ff;

logic [STEPS:0] steps_ff;

logic [3:0] count_ff;
logic [3:0] count_nx;

always_ff @(posedge clk or negedge rst_async_n) begin : reset_regs
    if(~rst_async_n) begin
        expanded_key_ff <= {NBW_OUT{1'b0}};
        steps_ff <= 11'h400;
    end else begin
        expanded_key_ff <= expanded_key_nx;
        if(i_start || (|steps_ff[9:0])) begin
            steps_ff <= {steps_ff[STEPS-1:0], (i_start & o_done)};
        end
    end
end

assign o_done = steps_ff[STEPS];
assign o_expanded_key = expanded_key_ff;

assign Rcon[0] = 8'h01;
assign Rcon[1] = 8'h02;
assign Rcon[2] = 8'h04;
assign Rcon[3] = 8'h08;
assign Rcon[4] = 8'h10;
assign Rcon[5] = 8'h20;
assign Rcon[6] = 8'h40;
assign Rcon[7] = 8'h80;
assign Rcon[8] = 8'h1b;
assign Rcon[9] = 8'h36;

generate
    for(genvar i = 0; i < STEPS; i++) begin : steps
        logic [NBW_WORD-1:0] RotWord;
        logic [NBW_WORD-1:0] SubWord;
        logic [NBW_WORD-1:0] RconXor;

        sbox uu_sbox0 (
            .i_data(RotWord[31:24]),
            .o_data(SubWord[31:24])
        );

        sbox uu_sbox1 (
            .i_data(RotWord[23:16]),
            .o_data(SubWord[23:16])
        );

        sbox uu_sbox2 (
            .i_data(RotWord[15:8]),
            .o_data(SubWord[15:8])
        );

        sbox uu_sbox3 (
            .i_data(RotWord[7:0]),
            .o_data(SubWord[7:0])
        );

        always_comb begin
            RotWord = {expanded_key_ff[NBW_OUT-(i+1)*NBW_KEY+NBW_WORD-NBW_BYTE-1-:(NBW_WORD-NBW_BYTE)], expanded_key_ff[NBW_OUT-(i+1)*NBW_KEY+NBW_WORD-1-:NBW_BYTE]};
            RconXor = {SubWord[31:24]^Rcon[i], SubWord[23:0]};

            step_key[i][127:96] = expanded_key_ff[NBW_OUT-(4*i  )*NBW_WORD-1-:NBW_WORD] ^ RconXor;
            step_key[i][95 :64] = expanded_key_ff[NBW_OUT-(4*i+1)*NBW_WORD-1-:NBW_WORD] ^ step_key[i][127:96];
            step_key[i][63 :32] = expanded_key_ff[NBW_OUT-(4*i+2)*NBW_WORD-1-:NBW_WORD] ^ step_key[i][95 :64];
            step_key[i][31 :0 ] = expanded_key_ff[NBW_OUT-(4*i+3)*NBW_WORD-1-:NBW_WORD] ^ step_key[i][63 :32];
        end
    end
endgenerate

assign expanded_key_nx = {valid_key  , step_key[0], step_key[1], step_key[2],
                          step_key[3], step_key[4], step_key[5], step_key[6],
                          step_key[7], step_key[8], step_key[9]};

always_comb begin
    if (i_start & o_done) begin
        valid_key = i_key;
    end else begin
        valid_key = expanded_key_ff[NBW_OUT-1-:NBW_KEY];
    end
end

endmodule : key_expansion_128aes

module sbox (
    input  logic [7:0] i_data,
    output logic [7:0] o_data
);

always_comb begin
    case (i_data)
        8'h00: o_data = 8'h63;
        8'h01: o_data = 8'h7C;
        8'h02: o_data = 8'h77;
        8'h03: o_data = 8'h7B;
        8'h04: o_data = 8'hF2;
        8'h05: o_data = 8'h6B;
        8'h06: o_data = 8'h6F;
        8'h07: o_data = 8'hC5;
        8'h08: o_data = 8'h30;
        8'h09: o_data = 8'h01;
        8'h0A: o_data = 8'h67;
        8'h0B: o_data = 8'h2B;
        8'h0C: o_data = 8'hFE;
        8'h0D: o_data = 8'hD7;
        8'h0E: o_data = 8'hAB;
        8'h0F: o_data = 8'h76;
        8'h10: o_data = 8'hCA;
        8'h11: o_data = 8'h82;
        8'h12: o_data = 8'hC9;
        8'h13: o_data = 8'h7D;
        8'h14: o_data = 8'hFA;
        8'h15: o_data = 8'h59;
        8'h16: o_data = 8'h47;
        8'h17: o_data = 8'hF0;
        8'h18: o_data = 8'hAD;
        8'h19: o_data = 8'hD4;
        8'h1A: o_data = 8'hA2;
        8'h1B: o_data = 8'hAF;
        8'h1C: o_data = 8'h9C;
        8'h1D: o_data = 8'hA4;
        8'h1E: o_data = 8'h72;
        8'h1F: o_data = 8'hC0;
        8'h20: o_data = 8'hB7;
        8'h21: o_data = 8'hFD;
        8'h22: o_data = 8'h93;
        8'h23: o_data = 8'h26;
        8'h24: o_data = 8'h36;
        8'h25: o_data = 8'h3F;
        8'h26: o_data = 8'hF7;
        8'h27: o_data = 8'hCC;
        8'h28: o_data = 8'h34;
        8'h29: o_data = 8'hA5;
        8'h2A: o_data = 8'hE5;
        8'h2B: o_data = 8'hF1;
        8'h2C: o_data = 8'h71;
        8'h2D: o_data = 8'hD8;
        8'h2E: o_data = 8'h31;
        8'h2F: o_data = 8'h15;
        8'h30: o_data = 8'h04;
        8'h31: o_data = 8'hC7;
        8'h32: o_data = 8'h23;
        8'h33: o_data = 8'hC3;
        8'h34: o_data = 8'h18;
        8'h35: o_data = 8'h96;
        8'h36: o_data = 8'h05;
        8'h37: o_data = 8'h9A;
        8'h38: o_data = 8'h07;
        8'h39: o_data = 8'h12;
        8'h3A: o_data = 8'h80;
        8'h3B: o_data = 8'hE2;
        8'h3C: o_data = 8'hEB;
        8'h3D: o_data = 8'h27;
        8'h3E: o_data = 8'hB2;
        8'h3F: o_data = 8'h75;
        8'h40: o_data = 8'h09;
        8'h41: o_data = 8'h83;
        8'h42: o_data = 8'h2C;
        8'h43: o_data = 8'h1A;
        8'h44: o_data = 8'h1B;
        8'h45: o_data = 8'h6E;
        8'h46: o_data = 8'h5A;
        8'h47: o_data = 8'hA0;
        8'h48: o_data = 8'h52;
        8'h49: o_data = 8'h3B;
        8'h4A: o_data = 8'hD6;
        8'h4B: o_data = 8'hB3;
        8'h4C: o_data = 8'h29;
        8'h4D: o_data = 8'hE3;
        8'h4E: o_data = 8'h2F;
        8'h4F: o_data = 8'h84;
        8'h50: o_data = 8'h53;
        8'h51: o_data = 8'hD1;
        8'h52: o_data = 8'h00;
        8'h53: o_data = 8'hED;
        8'h54: o_data = 8'h20;
        8'h55: o_data = 8'hFC;
        8'h56: o_data = 8'hB1;
        8'h57: o_data = 8'h5B;
        8'h58: o_data = 8'h6A;
        8'h59: o_data = 8'hCB;
        8'h5A: o_data = 8'hBE;
        8'h5B: o_data = 8'h39;
        8'h5C: o_data = 8'h4A;
        8'h5D: o_data = 8'h4C;
        8'h5E: o_data = 8'h58;
        8'h5F: o_data = 8'hCF;
        8'h60: o_data = 8'hD0;
        8'h61: o_data = 8'hEF;
        8'h62: o_data = 8'hAA;
        8'h63: o_data = 8'hFB;
        8'h64: o_data = 8'h43;
        8'h65: o_data = 8'h4D;
        8'h66: o_data = 8'h33;
        8'h67: o_data = 8'h85;
        8'h68: o_data = 8'h45;
        8'h69: o_data = 8'hF9;
        8'h6A: o_data = 8'h02;
        8'h6B: o_data = 8'h7F;
        8'h6C: o_data = 8'h50;
        8'h6D: o_data = 8'h3C;
        8'h6E: o_data = 8'h9F;
        8'h6F: o_data = 8'hA8;
        8'h70: o_data = 8'h51;
        8'h71: o_data = 8'hA3;
        8'h72: o_data = 8'h40;
        8'h73: o_data = 8'h8F;
        8'h74: o_data = 8'h92;
        8'h75: o_data = 8'h9D;
        8'h76: o_data = 8'h38;
        8'h77: o_data = 8'hF5;
        8'h78: o_data = 8'hBC;
        8'h79: o_data = 8'hB6;
        8'h7A: o_data = 8'hDA;
        8'h7B: o_data = 8'h21;
        8'h7C: o_data = 8'h10;
        8'h7D: o_data = 8'hFF;
        8'h7E: o_data = 8'hF3;
        8'h7F: o_data = 8'hD2;
        8'h80: o_data = 8'hCD;
        8'h81: o_data = 8'h0C;
        8'h82: o_data = 8'h13;
        8'h83: o_data = 8'hEC;
        8'h84: o_data = 8'h5F;
        8'h85: o_data = 8'h97;
        8'h86: o_data = 8'h44;
        8'h87: o_data = 8'h17;
        8'h88: o_data = 8'hC4;
        8'h89: o_data = 8'hA7;
        8'h8A: o_data = 8'h7E;
        8'h8B: o_data = 8'h3D;
        8'h8C: o_data = 8'h64;
        8'h8D: o_data = 8'h5D;
        8'h8E: o_data = 8'h19;
        8'h8F: o_data = 8'h73;
        8'h90: o_data = 8'h60;
        8'h91: o_data = 8'h81;
        8'h92: o_data = 8'h4F;
        8'h93: o_data = 8'hDC;
        8'h94: o_data = 8'h22;
        8'h95: o_data = 8'h2A;
        8'h96: o_data = 8'h90;
        8'h97: o_data = 8'h88;
        8'h98: o_data = 8'h46;
        8'h99: o_data = 8'hEE;
        8'h9A: o_data = 8'hB8;
        8'h9B: o_data = 8'h14;
        8'h9C: o_data = 8'hDE;
        8'h9D: o_data = 8'h5E;
        8'h9E: o_data = 8'h0B;
        8'h9F: o_data = 8'hDB;
        8'hA0: o_data = 8'hE0;
        8'hA1: o_data = 8'h32;
        8'hA2: o_data = 8'h3A;
        8'hA3: o_data = 8'h0A;
        8'hA4: o_data = 8'h49;
        8'hA5: o_data = 8'h06;
        8'hA6: o_data = 8'h24;
        8'hA7: o_data = 8'h5C;
        8'hA8: o_data = 8'hC2;
        8'hA9: o_data = 8'hD3;
        8'hAA: o_data = 8'hAC;
        8'hAB: o_data = 8'h62;
        8'hAC: o_data = 8'h91;
        8'hAD: o_data = 8'h95;
        8'hAE: o_data = 8'hE4;
        8'hAF: o_data = 8'h79;
        8'hB0: o_data = 8'hE7;
        8'hB1: o_data = 8'hC8;
        8'hB2: o_data = 8'h37;
        8'hB3: o_data = 8'h6D;
        8'hB4: o_data = 8'h8D;
        8'hB5: o_data = 8'hD5;
        8'hB6: o_data = 8'h4E;
        8'hB7: o_data = 8'hA9;
        8'hB8: o_data = 8'h6C;
        8'hB9: o_data = 8'h56;
        8'hBA: o_data = 8'hF4;
        8'hBB: o_data = 8'hEA;
        8'hBC: o_data = 8'h65;
        8'hBD: o_data = 8'h7A;
        8'hBE: o_data = 8'hAE;
        8'hBF: o_data = 8'h08;
        8'hC0: o_data = 8'hBA;
        8'hC1: o_data = 8'h78;
        8'hC2: o_data = 8'h25;
        8'hC3: o_data = 8'h2E;
        8'hC4: o_data = 8'h1C;
        8'hC5: o_data = 8'hA6;
        8'hC6: o_data = 8'hB4;
        8'hC7: o_data = 8'hC6;
        8'hC8: o_data = 8'hE8;
        8'hC9: o_data = 8'hDD;
        8'hCA: o_data = 8'h74;
        8'hCB: o_data = 8'h1F;
        8'hCC: o_data = 8'h4B;
        8'hCD: o_data = 8'hBD;
        8'hCE: o_data = 8'h8B;
        8'hCF: o_data = 8'h8A;
        8'hD0: o_data = 8'h70;
        8'hD1: o_data = 8'h3E;
        8'hD2: o_data = 8'hB5;
        8'hD3: o_data = 8'h66;
        8'hD4: o_data = 8'h48;
        8'hD5: o_data = 8'h03;
        8'hD6: o_data = 8'hF6;
        8'hD7: o_data = 8'h0E;
        8'hD8: o_data = 8'h61;
        8'hD9: o_data = 8'h35;
        8'hDA: o_data = 8'h57;
        8'hDB: o_data = 8'hB9;
        8'hDC: o_data = 8'h86;
        8'hDD: o_data = 8'hC1;
        8'hDE: o_data = 8'h1D;
        8'hDF: o_data = 8'h9E;
        8'hE0: o_data = 8'hE1;
        8'hE1: o_data = 8'hF8;
        8'hE2: o_data = 8'h98;
        8'hE3: o_data = 8'h11;
        8'hE4: o_data = 8'h69;
        8'hE5: o_data = 8'hD9;
        8'hE6: o_data = 8'h8E;
        8'hE7: o_data = 8'h94;
        8'hE8: o_data = 8'h9B;
        8'hE9: o_data = 8'h1E;
        8'hEA: o_data = 8'h87;
        8'hEB: o_data = 8'hE9;
        8'hEC: o_data = 8'hCE;
        8'hED: o_data = 8'h55;
        8'hEE: o_data = 8'h28;
        8'hEF: o_data = 8'hDF;
        8'hF0: o_data = 8'h8C;
        8'hF1: o_data = 8'hA1;
        8'hF2: o_data = 8'h89;
        8'hF3: o_data = 8'h0D;
        8'hF4: o_data = 8'hBF;
        8'hF5: o_data = 8'hE6;
        8'hF6: o_data = 8'h42;
        8'hF7: o_data = 8'h68;
        8'hF8: o_data = 8'h41;
        8'hF9: o_data = 8'h99;
        8'hFA: o_data = 8'h2D;
        8'hFB: o_data = 8'h0F;
        8'hFC: o_data = 8'hB0;
        8'hFD: o_data = 8'h54;
        8'hFE: o_data = 8'hBB;
        8'hFF: o_data = 8'h16;
        default: o_data = 8'h00;
    endcase
end

endmodule : sbox
