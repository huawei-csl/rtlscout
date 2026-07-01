// Resource Waste: The unnecessary extension of bit widths results in increased usage of logic elements and registers, which can be critical in resource-constrained environments (e.g., FPGA, ASIC).
// Performance Impact: Larger bit widths can lead to longer propagation delays in combinational logic, potentially decreasing the system's overall performance.
// Power Consumption: Larger registers and wider data paths can lead to higher power consumption due to increased switching activity and capacitance.

module inefficient_multiplier(
    input [7:0] multiplicandA,  // 8-bit multiplicand
    input [7:0] multiplierB,    // 8-bit multiplier
    input [7:0] multiplicandC,  // 8-bit multiplicand
    input [7:0] multiplierD,    // 8-bit multiplier
    input sel,
    output reg [15:0] product      // Excessively wide 16-bit product output
);

// Internal variables with unnecessary 32-bit width
reg [31:0] internal_multiplicand;
reg [31:0] internal_multiplier;
reg [31:0] internal_product;

always @(*) begin
    if (sel) begin
        // Extend multiplicand and multiplier to 32 bits unnecessarily
        internal_multiplicand = {24'b0, multiplicandA};  // Zero-extend to 32 bits
        internal_multiplier = {24'b0, multiplierB};      // Zero-extend to 32 bits
    end else begin
        internal_multiplicand = {24'b0, multiplicandC};  // Zero-extend to 32 bits
        internal_multiplier = {24'b0, multiplierD};      // Zero-extend to 32 bits
    end

    if (sel) begin
        // Perform multiplication using 32-bit registers
        internal_product = internal_multiplicand * internal_multiplier;
        // Assign the unnecessarily large internal product to output
        product = internal_product[15:0];
    end else begin
        internal_product = internal_multiplicand * internal_multiplier;
        // Assign the unnecessarily large internal product to output
        product = internal_product[15:0];
    end
end

endmodule