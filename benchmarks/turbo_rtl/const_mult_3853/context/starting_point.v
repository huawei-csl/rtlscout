
module multiplier_block(i_data0,o_data0);

  input  [31:0] i_data0;
  output [31:0] o_data0;
  wire [31:0] w1,w256,w257,w2,w259,w4112,w3853;

  assign w1 = i_data0;
  assign w2 = w1<<1;
  assign w256 = w1<<8;
  assign w257 = w256+w1;
  assign w259 = w257+w2;
  assign w3853 = w4112-w259;
  assign w4112 = w257<<4;
  assign o_data0 = w3853;
endmodule

