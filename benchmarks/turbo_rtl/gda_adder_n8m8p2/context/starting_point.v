
module GDA_St_N8_M8_P2(input  [7:0] in1,
                       input  [7:0] in2,
                       output [8:0] res);

  wire [2:0] temp1,temp2,temp3,temp4,temp5,temp6,temp7,temp8;
  wire 
      p0,
      p1,
      p2,
      p3,
      p4,
      p5,
      p6,
      g0,
      g1,
      g2,
      g3,
      g4,
      g5,
      g6,
      c1,
      c2,
      c3,
      c4,
      c5,
      c6,
      c7;
  wire p1c1,p2c2,p3c3,p4c4,p5c5,p6c6;
  wire 
      carry_pred_1,
      carry_pred_2,
      carry_pred_3,
      carry_pred_4,
      carry_pred_5,
      carry_pred_6;

  and and_0(g0,in1[0],in2[0]);
  and and_1(g1,in1[1],in2[1]);
  and and_2(g2,in1[2],in2[2]);
  and and_3(g3,in1[3],in2[3]);
  and and_4(g4,in1[4],in2[4]);
  and and_5(g5,in1[5],in2[5]);
  and and_6(g6,in1[6],in2[6]);
  xor xor_0(p0,in1[0],in2[0]);
  xor xor_1(p1,in1[1],in2[1]);
  xor xor_2(p2,in1[2],in2[2]);
  xor xor_3(p3,in1[3],in2[3]);
  xor xor_4(p4,in1[4],in2[4]);
  xor xor_5(p5,in1[5],in2[5]);
  xor xor_6(p6,in1[6],in2[6]);
  assign c1 = g0;
  assign c2 = g1;
  and and_7(p1c1,p1,c1);
  or or_0(carry_pred_1,c2,p1c1);
  assign c3 = g2;
  and and_8(p2c2,p2,c2);
  or or_2(carry_pred_2,c3,p2c2);
  assign c4 = g3;
  and and_10(p3c3,p3,c3);
  or or_5(carry_pred_3,c4,p3c3);
  assign c5 = g4;
  and and_13(p4c4,p4,c4);
  or or_9(carry_pred_4,c5,p4c4);
  assign c6 = g5;
  and and_17(p5c5,p5,c5);
  or or_14(carry_pred_5,c6,p5c5);
  assign c7 = g6;
  and and_22(p6c6,p6,c6);
  or or_20(carry_pred_6,c7,p6c6);
  assign temp1[1:0] = in1[0]+in2[0];
  assign temp2[1:0] = (in1[1]+c1)+in2[1];
  assign temp3[1:0] = (carry_pred_1+in1[2])+in2[2];
  assign temp4[1:0] = (carry_pred_2+in2[3])+in1[3];
  assign temp5[1:0] = (carry_pred_3+in1[4])+in2[4];
  assign temp6[1:0] = (in2[5]+carry_pred_4)+in1[5];
  assign temp7[1:0] = (in2[6]+carry_pred_5)+in1[6];
  assign temp8[1:0] = in1[7]+(in2[7]+carry_pred_6);
  assign res[8:0] = {temp8[1:0],temp7[0],temp6[0],temp5[0],temp4[0],temp3[0],temp2[0],temp1[0]};
endmodule

