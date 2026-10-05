module add16 (
    input  logic [15:0] a,
    input  logic [15:0] b,
    output logic [16:0] y
);

    // Ripple-carry adder implementation for minimal area
    // Use explicit carry chain
    
    logic [15:0] sum;
    logic [16:0] carry;
    
    assign carry[0] = 1'b0;
    
    // Generate sum bits using full adder behavior
    // sum[i] = a[i] ^ b[i] ^ carry[i]
    // carry[i+1] = (a[i] & b[i]) | (carry[i] & (a[i] ^ b[i]))
    
    genvar i;
    generate
        for (i = 0; i < 16; i++) begin : adder_stage
            // Sum: a XOR b XOR carry_in
            assign sum[i] = a[i] ^ b[i] ^ carry[i];
            
            // Carry out: (a AND b) OR (carry_in AND (a XOR b))
            assign carry[i+1] = (a[i] & b[i]) | (carry[i] & (a[i] ^ b[i]));
        end
    endgenerate
    
    assign y = {carry[16], sum};

endmodule