module example(
    input [31:0] x,
    output [31:0] y,
    output [31:0] z,
    output [31:0] w
);

// ---- x9 = (x<<3) + x using g-p carry chain ----
wire [31:0] x9;
wire [32:0] cx;
assign x9[0] = x[0];
assign x9[1] = x[1];
assign x9[2] = x[2];
assign cx[3] = 1'b0;

genvar i;
generate
    for (i = 3; i < 32; i = i + 1) begin : x9_bits
        wire a = x[i-3];
        wire b = x[i];
        wire g = a & b;
        wire p = a ^ b;
        assign x9[i] = p ^ cx[i];
        assign cx[i+1] = g | (p & cx[i]);
    end
endgenerate

// ---- y = 13x = x9 + (x<<2) using g-p carry chain ----
wire [31:0] y_out;
wire [32:0] cy;
assign y_out[0] = x[0];
assign y_out[1] = x[1];
assign cy[2] = 1'b0;

generate
    for (i = 2; i < 32; i = i + 1) begin : y_bits
        wire a = x9[i];
        wire b = x[i-2];
        wire g = a & b;
        wire p = a ^ b;
        assign y_out[i] = p ^ cy[i];
        assign cy[i+1] = g | (p & cy[i]);
    end
endgenerate

assign y = y_out;

// ---- z = 25x = x9 + (x<<4) using g-p carry chain ----
wire [31:0] z_out;
wire [32:0] cz;
assign z_out[0] = x[0];
assign z_out[1] = x[1];
assign z_out[2] = x[2];
assign z_out[3] = x9[3];
assign cz[4] = 1'b0;

generate
    for (i = 4; i < 32; i = i + 1) begin : z_bits
        wire a = x9[i];
        wire b = x[i-4];
        wire g = a & b;
        wire p = a ^ b;
        assign z_out[i] = p ^ cz[i];
        assign cz[i+1] = g | (p & cz[i]);
    end
endgenerate

assign z = z_out;

// ---- w = 63x = (x<<6) - x using g-p carry chain ----
wire [31:0] w_out;
wire [31:0] nx = ~x;
wire [32:0] cw;
assign cw[0] = 1'b1;

generate
    for (i = 0; i < 6; i = i + 1) begin : w_lo
        assign w_out[i] = nx[i] ^ cw[i];
        assign cw[i+1] = nx[i] & cw[i];
    end
    for (i = 6; i < 32; i = i + 1) begin : w_hi
        wire a = x[i-6];
        wire b = nx[i];
        wire g = a & b;
        wire p = a ^ b;
        assign w_out[i] = p ^ cw[i];
        assign cw[i+1] = g | (p & cw[i]);
    end
endgenerate

assign w = w_out;

endmodule
