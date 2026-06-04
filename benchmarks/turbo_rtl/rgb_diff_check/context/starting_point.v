
module DiffCheck(input  [14:0] rgb1,
                 input  [14:0] rgb2,
                 output result);

  wire [5:0]  r = rgb1[4:0]-rgb2[4:0];
  wire [5:0]  g = rgb1[9:5]-rgb2[9:5];
  wire [5:0]  b = rgb1[14:10]-rgb2[14:10];
  wire [6:0]  t = $signed(r)+$signed(b);
  wire [6:0]  gx = {g[5],g};
  wire [7:0]  y = $signed(gx)+$signed(t);
  wire [6:0]  u = $signed(r)-$signed(b);
  wire [7:0]  v = $signed({g,1'b0})-$signed(t);
  wire  y_inside = (y < 8'h18) || (y >= 8'he8);
  wire  u_inside = (u < 7'h4) || (u >= 7'h7c);
  wire  v_inside = (v < 8'h6) || (v >= 8'hfA);

  assign result = !(u_inside && v_inside && y_inside);
endmodule

