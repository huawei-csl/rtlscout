
module average_module(input  clk,
                      input  reset,
                      input  [7:0] a,
                      input  [7:0] b,
                      input  [7:0] c,
                      input  [7:0] d,
                      output reg [7:0] average);

  reg  [7:0] sum;
  reg  [3:0] carry;

  
  always @(posedge clk)
      begin
        if (reset) 
          begin
            sum <= 8'b0;
            carry <= 4'b0;
            average <= 8'b0;
          end
        else 
          begin
            {sum,carry} <= ((b+{4{carry}})+d)+(c+a);
            average <= sum>>2;
          end
      end
endmodule

