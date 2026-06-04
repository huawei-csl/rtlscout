`timescale 1ns/1ps
module encoder(in_8b,dataK,out_10b);

  input  wire [7:0] in_8b;
  input  wire dataK;
  wire S,L03,L30,L12,L21;
  wire A,B,C,D,E,F,G,H;
  output [9:0] out_10b;

  assign A = in_8b[0];
  assign B = in_8b[1];
  assign C = in_8b[2];
  assign D = in_8b[3];
  assign E = in_8b[4];
  assign F = in_8b[5];
  assign G = in_8b[6];
  assign H = in_8b[7];
  assign S = 0;
  assign L03 = (~C & ~A) & ~B;
  assign L30 = (B & A) & C;
  assign L12 = (~A & (~C & B)) || 
               (((~B & ~A) & C) || ((A & ~C) & ~B));
  assign L21 = ((A & ~B) & C) || (~A & (C & B)) || (A & (~C & B));
  assign out_10b[9] = A;
  assign out_10b[8] = (~D & L03) || (~(L30 & D) & B);
  assign out_10b[7] = (L03 & (E+~D)) || C;
  assign out_10b[6] = D & ~(L30 & D);
  assign out_10b[5] = ((D & L03) & ~E) || (L12 & (~E & ~D)) || (E & ~(D & L03));
  assign out_10b[4] = ((~D & L30) & E) || 
                      (((((E & ~D) || (D & ~E))+dataK) & L12) || 
((L21 & ~E) & ~D)) || (L30 & (D & E));
  assign out_10b[3] = ~((H & (G & F)) & (dataK || S)) & F;
  assign out_10b[2] = G || (~H & ~F);
  assign out_10b[1] = H;
  assign out_10b[0] = ((H & (G & F)) & (dataK || S)) || (~H & (~F & G)) || 
                      (~G & F);
endmodule

