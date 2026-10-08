// 16-bit unsigned multiplier with Wallace tree reduction
// Produces 32-bit output product

module Mul16(
    input  logic [15:0] a,
    input  logic [15:0] b,
    output logic [31:0] p
);

    // Generate partial products
    // Each row i is a[15:0] & b[i]
    logic [15:0] pp [16:0];
    
    genvar i, j;
    generate
        for (i = 0; i < 16; i++) begin : gen_pp
            for (j = 0; j < 16; j++) begin : gen_pp_bits
                assign pp[i][j] = a[j] & b[i];
            end
        end
    endgenerate
    
    // Arrange partial products with proper shifting
    // pp[i] is shifted left by i bits
    logic [31:0] pp_shifted [16:0];
    generate
        for (i = 0; i < 16; i++) begin : gen_shift
            assign pp_shifted[i] = {16'b0, pp[i]} << i;
        end
    endgenerate
    
    // Wallace tree reduction - 4:2 compressors in stages
    // Stage 1: Reduce 16 rows to 8 rows
    logic [31:0] stage1 [7:0];
    
    // First 8 partial products (0-7)
    generate
        for (j = 0; j < 8; j++) begin : stage1_rows
            logic [31:0] sum;
            logic cout;
            assign {cout, sum} = pp_shifted[j][31:0] + pp_shifted[j+8][31:0];
            assign stage1[j] = sum;
            // Note: cout would need to be handled for higher bits
        end
    endgenerate
    
    // Stage 2: Reduce 8 rows to 4 rows  
    logic [31:0] stage2 [3:0];
    generate
        for (j = 0; j < 4; j++) begin : stage2_rows
            logic [31:0] sum;
            logic cout;
            assign {cout, sum} = stage1[j][31:0] + stage1[j+4][31:0];
            assign stage2[j] = sum;
        end
    endgenerate
    
    // Stage 3: Reduce 4 rows to 2 rows
    logic [31:0] stage3 [1:0];
    generate
        for (j = 0; j < 2; j++) begin : stage3_rows
            logic [31:0] sum;
            logic cout;
            assign {cout, sum} = stage2[j][31:0] + stage2[j+2][31:0];
            assign stage3[j] = sum;
        end
    endgenerate
    
    // Final addition
    logic [31:0] sum_final;
    logic cout_final;
    assign {cout_final, sum_final} = stage3[0][31:0] + stage3[1][31:0];
    
    assign p = sum_final;

endmodule