module inefficient_multiplier(
    input [7:0] multiplicandA,
    input [7:0] multiplierB,
    input [7:0] multiplicandC,
    input [7:0] multiplierD,
    input sel,
    output [15:0] product
);

wire [7:0] op1 = sel ? multiplicandA : multiplicandC;
wire [7:0] op2 = sel ? multiplierB : multiplierD;

wire [3:0] op1_lo = op1[3:0];
wire [3:0] op1_hi = op1[7:4];

wire [11:0] pp_lo = op1_lo * op2;   // 4*8 = 12 bits, occupies bits [11:0]
wire [11:0] pp_hi = op1_hi * op2;   // 4*8 = 12 bits, shifted by 4 -> bits [15:4]

// Low 4 bits of product come directly from pp_lo
// The add only needs to be 12 bits (bits [15:4])
wire [11:0] lo_part = pp_lo[11:0];

// pp_hi << 4 occupies [15:4], pp_lo occupies [15:0]
// We add pp_hi<<4 + pp_lo. The low 4 bits are just pp_lo[3:0].
// The add of bits [15:4] = pp_lo[11:4] + pp_hi + carry from bit 3 (0)
wire [11:0] add_in_lo = {pp_lo[11:4]};
wire [11:0] add_in_hi = pp_hi;
wire [12:0] add_out = {1'b0, add_in_lo} + {1'b0, add_in_hi};

assign product = {add_out[11:0], pp_lo[3:0]};

endmodule
