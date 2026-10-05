// functional ASAP7 models generated from liberty functions
// (gen_asap7_functional_cells.py -- do not edit by hand)
module AND2x2_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (A & B);
endmodule
module AND2x4_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (A & B);
endmodule
module AND2x6_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (A & B);
endmodule
module AND3x1_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (A & B & C);
endmodule
module AND3x2_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (A & B & C);
endmodule
module AND3x4_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (A & B & C);
endmodule
module AND4x1_ASAP7_75t_R (output Y, input A, input B, input C, input D);
  assign Y = (A & B & C & D);
endmodule
module AND4x2_ASAP7_75t_R (output Y, input A, input B, input C, input D);
  assign Y = (A & B & C & D);
endmodule
module AND5x1_ASAP7_75t_R (output Y, input A, input B, input C, input D, input E);
  assign Y = (A & B & C & D & E);
endmodule
module AND5x2_ASAP7_75t_R (output Y, input A, input B, input C, input D, input E);
  assign Y = (A & B & C & D & E);
endmodule
module FAx1_ASAP7_75t_R (output CON, output SN, input A, input B, input CI);
  assign CON = (~A & ~B) | (~A & ~CI) | (~B & ~CI);
  assign SN = (A & B & ~CI) | (A & ~B & CI) | (~A & B & CI) | (~A & ~B & ~CI);
endmodule
module HAxp5_ASAP7_75t_R (output CON, output SN, input A, input B);
  assign CON = (~A) | (~B);
  assign SN = (A & B) | (~A & ~B);
endmodule
module MAJIxp5_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (~A & ~B) | (~A & ~C) | (~B & ~C);
endmodule
module MAJx2_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (A & B) | (A & C) | (B & C);
endmodule
module MAJx3_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (A & B) | (A & C) | (B & C);
endmodule
module NAND2x1_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (~A) | (~B);
endmodule
module NAND2x1p5_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (~A) | (~B);
endmodule
module NAND2x2_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (~A) | (~B);
endmodule
module NAND2xp33_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (~A) | (~B);
endmodule
module NAND2xp5_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (~A) | (~B);
endmodule
module NAND2xp67_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (~A) | (~B);
endmodule
module NAND3x1_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (~A) | (~B) | (~C);
endmodule
module NAND3x2_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (~A) | (~B) | (~C);
endmodule
module NAND3xp33_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (~A) | (~B) | (~C);
endmodule
module NAND4xp25_ASAP7_75t_R (output Y, input A, input B, input C, input D);
  assign Y = (~A) | (~B) | (~C) | (~D);
endmodule
module NAND4xp75_ASAP7_75t_R (output Y, input A, input B, input C, input D);
  assign Y = (~A) | (~B) | (~C) | (~D);
endmodule
module NAND5xp2_ASAP7_75t_R (output Y, input A, input B, input C, input D, input E);
  assign Y = (~A) | (~B) | (~C) | (~D) | (~E);
endmodule
module NOR2x1_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (~A & ~B);
endmodule
module NOR2x1p5_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (~A & ~B);
endmodule
module NOR2x2_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (~A & ~B);
endmodule
module NOR2xp33_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (~A & ~B);
endmodule
module NOR2xp67_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (~A & ~B);
endmodule
module NOR3x1_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (~A & ~B & ~C);
endmodule
module NOR3x2_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (~A & ~B & ~C);
endmodule
module NOR3xp33_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (~A & ~B & ~C);
endmodule
module NOR4xp25_ASAP7_75t_R (output Y, input A, input B, input C, input D);
  assign Y = (~A & ~B & ~C & ~D);
endmodule
module NOR4xp75_ASAP7_75t_R (output Y, input A, input B, input C, input D);
  assign Y = (~A & ~B & ~C & ~D);
endmodule
module NOR5xp2_ASAP7_75t_R (output Y, input A, input B, input C, input D, input E);
  assign Y = (~A & ~B & ~C & ~D & ~E);
endmodule
module OR2x2_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (A) | (B);
endmodule
module OR2x4_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (A) | (B);
endmodule
module OR2x6_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (A) | (B);
endmodule
module OR3x1_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (A) | (B) | (C);
endmodule
module OR3x2_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (A) | (B) | (C);
endmodule
module OR3x4_ASAP7_75t_R (output Y, input A, input B, input C);
  assign Y = (A) | (B) | (C);
endmodule
module OR4x1_ASAP7_75t_R (output Y, input A, input B, input C, input D);
  assign Y = (A) | (B) | (C) | (D);
endmodule
module OR4x2_ASAP7_75t_R (output Y, input A, input B, input C, input D);
  assign Y = (A) | (B) | (C) | (D);
endmodule
module OR5x1_ASAP7_75t_R (output Y, input A, input B, input C, input D, input E);
  assign Y = (A) | (B) | (C) | (D) | (E);
endmodule
module OR5x2_ASAP7_75t_R (output Y, input A, input B, input C, input D, input E);
  assign Y = (A) | (B) | (C) | (D) | (E);
endmodule
module TIEHIx1_ASAP7_75t_R (output H);
  assign H = 1;
endmodule
module TIELOx1_ASAP7_75t_R (output L);
  assign L = 0;
endmodule
module XNOR2x1_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (A & B) | (~A & ~B);
endmodule
module XNOR2x2_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (A & B) | (~A & ~B);
endmodule
module XNOR2xp5_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (A & B) | (~A & ~B);
endmodule
module XOR2x1_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (A & ~B) | (~A & B);
endmodule
module XOR2x2_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (A & ~B) | (~A & B);
endmodule
module XOR2xp5_ASAP7_75t_R (output Y, input A, input B);
  assign Y = (A & ~B) | (~A & B);
endmodule
module BUFx10_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module BUFx12_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module BUFx12f_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module BUFx16f_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module BUFx24_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module BUFx2_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module BUFx3_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module BUFx4_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module BUFx4f_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module BUFx5_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module BUFx6f_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module BUFx8_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module CKINVDCx10_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module CKINVDCx11_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module CKINVDCx12_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module CKINVDCx14_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module CKINVDCx16_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module CKINVDCx20_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module CKINVDCx5p33_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module CKINVDCx6p67_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module CKINVDCx8_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module CKINVDCx9p33_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module HB1xp67_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module HB2xp67_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module HB3xp67_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module HB4xp67_ASAP7_75t_R (output Y, input A);
  assign Y = A;
endmodule
module INVx11_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module INVx13_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module INVx1_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module INVx2_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module INVx3_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module INVx4_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module INVx5_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module INVx6_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module INVx8_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module INVxp33_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module INVxp67_ASAP7_75t_R (output Y, input A);
  assign Y = ~A;
endmodule
module A2O1A1Ixp33_ASAP7_75t_R (output Y, input A1, input A2, input B, input C);
  assign Y = (~A1 & ~B) | (~A2 & ~B) | (~C);
endmodule
module A2O1A1O1Ixp25_ASAP7_75t_R (output Y, input A1, input A2, input B, input C, input D);
  assign Y = (~A1 & ~B & ~D) | (~A2 & ~B & ~D) | (~C & ~D);
endmodule
module AO211x2_ASAP7_75t_R (output Y, input A1, input A2, input B, input C);
  assign Y = (A1 & A2) | (B) | (C);
endmodule
module AO21x1_ASAP7_75t_R (output Y, input A1, input A2, input B);
  assign Y = (A1 & A2) | (B);
endmodule
module AO21x2_ASAP7_75t_R (output Y, input A1, input A2, input B);
  assign Y = (A1 & A2) | (B);
endmodule
module AO221x1_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2, input C);
  assign Y = (A1 & A2) | (B1 & B2) | (C);
endmodule
module AO221x2_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2, input C);
  assign Y = (A1 & A2) | (B1 & B2) | (C);
endmodule
module AO222x2_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2, input C1, input C2);
  assign Y = (A1 & A2) | (B1 & B2) | (C1 & C2);
endmodule
module AO22x1_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2);
  assign Y = (A1 & A2) | (B1 & B2);
endmodule
module AO22x2_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2);
  assign Y = (A1 & A2) | (B1 & B2);
endmodule
module AO31x2_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B);
  assign Y = (A1 & A2 & A3) | (B);
endmodule
module AO322x2_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input C1, input C2);
  assign Y = (A1 & A2 & A3) | (B1 & B2) | (C1 & C2);
endmodule
module AO32x1_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2);
  assign Y = (A1 & A2 & A3) | (B1 & B2);
endmodule
module AO32x2_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2);
  assign Y = (A1 & A2 & A3) | (B1 & B2);
endmodule
module AO331x1_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C);
  assign Y = (A1 & A2 & A3) | (B1 & B2 & B3) | (C);
endmodule
module AO331x2_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C);
  assign Y = (A1 & A2 & A3) | (B1 & B2 & B3) | (C);
endmodule
module AO332x1_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1, input C2);
  assign Y = (A1 & A2 & A3) | (B1 & B2 & B3) | (C1 & C2);
endmodule
module AO332x2_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1, input C2);
  assign Y = (A1 & A2 & A3) | (B1 & B2 & B3) | (C1 & C2);
endmodule
module AO333x1_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1, input C2, input C3);
  assign Y = (A1 & A2 & A3) | (B1 & B2 & B3) | (C1 & C2 & C3);
endmodule
module AO333x2_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1, input C2, input C3);
  assign Y = (A1 & A2 & A3) | (B1 & B2 & B3) | (C1 & C2 & C3);
endmodule
module AO33x2_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3);
  assign Y = (A1 & A2 & A3) | (B1 & B2 & B3);
endmodule
module AOI211x1_ASAP7_75t_R (output Y, input A1, input A2, input B, input C);
  assign Y = (~A1 & ~B & ~C) | (~A2 & ~B & ~C);
endmodule
module AOI211xp5_ASAP7_75t_R (output Y, input A1, input A2, input B, input C);
  assign Y = (~A1 & ~B & ~C) | (~A2 & ~B & ~C);
endmodule
module AOI21x1_ASAP7_75t_R (output Y, input A1, input A2, input B);
  assign Y = (~A1 & ~B) | (~A2 & ~B);
endmodule
module AOI21xp33_ASAP7_75t_R (output Y, input A1, input A2, input B);
  assign Y = (~A1 & ~B) | (~A2 & ~B);
endmodule
module AOI21xp5_ASAP7_75t_R (output Y, input A1, input A2, input B);
  assign Y = (~A1 & ~B) | (~A2 & ~B);
endmodule
module AOI221x1_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2, input C);
  assign Y = (~A1 & ~B1 & ~C) | (~A1 & ~B2 & ~C) | (~A2 & ~B1 & ~C) | (~A2 & ~B2 & ~C);
endmodule
module AOI221xp5_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2, input C);
  assign Y = (~A1 & ~B1 & ~C) | (~A1 & ~B2 & ~C) | (~A2 & ~B1 & ~C) | (~A2 & ~B2 & ~C);
endmodule
module AOI222xp33_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2, input C1, input C2);
  assign Y = (~A1 & ~B1 & ~C1) | (~A1 & ~B1 & ~C2) | (~A1 & ~B2 & ~C1) | (~A1 & ~B2 & ~C2) | (~A2 & ~B1 & ~C1) | (~A2 & ~B1 & ~C2) | (~A2 & ~B2 & ~C1) | (~A2 & ~B2 & ~C2);
endmodule
module AOI22x1_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2);
  assign Y = (~A1 & ~B1) | (~A1 & ~B2) | (~A2 & ~B1) | (~A2 & ~B2);
endmodule
module AOI22xp33_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2);
  assign Y = (~A1 & ~B1) | (~A1 & ~B2) | (~A2 & ~B1) | (~A2 & ~B2);
endmodule
module AOI22xp5_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2);
  assign Y = (~A1 & ~B1) | (~A1 & ~B2) | (~A2 & ~B1) | (~A2 & ~B2);
endmodule
module AOI311xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B, input C);
  assign Y = (~A1 & ~B & ~C) | (~A2 & ~B & ~C) | (~A3 & ~B & ~C);
endmodule
module AOI31xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B);
  assign Y = (~A1 & ~B) | (~A2 & ~B) | (~A3 & ~B);
endmodule
module AOI31xp67_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B);
  assign Y = (~A1 & ~B) | (~A2 & ~B) | (~A3 & ~B);
endmodule
module AOI321xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input C);
  assign Y = (~A1 & ~B1 & ~C) | (~A1 & ~B2 & ~C) | (~A2 & ~B1 & ~C) | (~A2 & ~B2 & ~C) | (~A3 & ~B1 & ~C) | (~A3 & ~B2 & ~C);
endmodule
module AOI322xp5_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input C1, input C2);
  assign Y = (~A1 & ~B1 & ~C1) | (~A1 & ~B1 & ~C2) | (~A1 & ~B2 & ~C1) | (~A1 & ~B2 & ~C2) | (~A2 & ~B1 & ~C1) | (~A2 & ~B1 & ~C2) | (~A2 & ~B2 & ~C1) | (~A2 & ~B2 & ~C2) | (~A3 & ~B1 & ~C1) | (~A3 & ~B1 & ~C2) | (~A3 & ~B2 & ~C1) | (~A3 & ~B2 & ~C2);
endmodule
module AOI32xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2);
  assign Y = (~A1 & ~B1) | (~A1 & ~B2) | (~A2 & ~B1) | (~A2 & ~B2) | (~A3 & ~B1) | (~A3 & ~B2);
endmodule
module AOI331xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1);
  assign Y = (~A1 & ~B1 & ~C1) | (~A1 & ~B2 & ~C1) | (~A1 & ~B3 & ~C1) | (~A2 & ~B1 & ~C1) | (~A2 & ~B2 & ~C1) | (~A2 & ~B3 & ~C1) | (~A3 & ~B1 & ~C1) | (~A3 & ~B2 & ~C1) | (~A3 & ~B3 & ~C1);
endmodule
module AOI332xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1, input C2);
  assign Y = (~A1 & ~B1 & ~C1) | (~A1 & ~B1 & ~C2) | (~A1 & ~B2 & ~C1) | (~A1 & ~B2 & ~C2) | (~A1 & ~B3 & ~C1) | (~A1 & ~B3 & ~C2) | (~A2 & ~B1 & ~C1) | (~A2 & ~B1 & ~C2) | (~A2 & ~B2 & ~C1) | (~A2 & ~B2 & ~C2) | (~A2 & ~B3 & ~C1) | (~A2 & ~B3 & ~C2) | (~A3 & ~B1 & ~C1) | (~A3 & ~B1 & ~C2) | (~A3 & ~B2 & ~C1) | (~A3 & ~B2 & ~C2) | (~A3 & ~B3 & ~C1) | (~A3 & ~B3 & ~C2);
endmodule
module AOI333xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1, input C2, input C3);
  assign Y = (~A1 & ~B1 & ~C1) | (~A1 & ~B1 & ~C2) | (~A1 & ~B1 & ~C3) | (~A1 & ~B2 & ~C1) | (~A1 & ~B2 & ~C2) | (~A1 & ~B2 & ~C3) | (~A1 & ~B3 & ~C1) | (~A1 & ~B3 & ~C2) | (~A1 & ~B3 & ~C3) | (~A2 & ~B1 & ~C1) | (~A2 & ~B1 & ~C2) | (~A2 & ~B1 & ~C3) | (~A2 & ~B2 & ~C1) | (~A2 & ~B2 & ~C2) | (~A2 & ~B2 & ~C3) | (~A2 & ~B3 & ~C1) | (~A2 & ~B3 & ~C2) | (~A2 & ~B3 & ~C3) | (~A3 & ~B1 & ~C1) | (~A3 & ~B1 & ~C2) | (~A3 & ~B1 & ~C3) | (~A3 & ~B2 & ~C1) | (~A3 & ~B2 & ~C2) | (~A3 & ~B2 & ~C3) | (~A3 & ~B3 & ~C1) | (~A3 & ~B3 & ~C2) | (~A3 & ~B3 & ~C3);
endmodule
module AOI33xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3);
  assign Y = (~A1 & ~B1) | (~A1 & ~B2) | (~A1 & ~B3) | (~A2 & ~B1) | (~A2 & ~B2) | (~A2 & ~B3) | (~A3 & ~B1) | (~A3 & ~B2) | (~A3 & ~B3);
endmodule
module O2A1O1Ixp33_ASAP7_75t_R (output Y, input A1, input A2, input B, input C);
  assign Y = (~A1 & ~A2 & ~C) | (~B & ~C);
endmodule
module O2A1O1Ixp5_ASAP7_75t_R (output Y, input A1, input A2, input B, input C);
  assign Y = (~A1 & ~A2 & ~C) | (~B & ~C);
endmodule
module OA211x2_ASAP7_75t_R (output Y, input A1, input A2, input B, input C);
  assign Y = (A1 & B & C) | (A2 & B & C);
endmodule
module OA21x2_ASAP7_75t_R (output Y, input A1, input A2, input B);
  assign Y = (A1 & B) | (A2 & B);
endmodule
module OA221x2_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2, input C);
  assign Y = (A1 & B1 & C) | (A1 & B2 & C) | (A2 & B1 & C) | (A2 & B2 & C);
endmodule
module OA222x2_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2, input C1, input C2);
  assign Y = (A1 & B1 & C1) | (A1 & B1 & C2) | (A1 & B2 & C1) | (A1 & B2 & C2) | (A2 & B1 & C1) | (A2 & B1 & C2) | (A2 & B2 & C1) | (A2 & B2 & C2);
endmodule
module OA22x2_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2);
  assign Y = (A1 & B1) | (A1 & B2) | (A2 & B1) | (A2 & B2);
endmodule
module OA31x2_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1);
  assign Y = (A1 & B1) | (A2 & B1) | (A3 & B1);
endmodule
module OA331x1_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1);
  assign Y = (A1 & B1 & C1) | (A1 & B2 & C1) | (A1 & B3 & C1) | (A2 & B1 & C1) | (A2 & B2 & C1) | (A2 & B3 & C1) | (A3 & B1 & C1) | (A3 & B2 & C1) | (A3 & B3 & C1);
endmodule
module OA331x2_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1);
  assign Y = (A1 & B1 & C1) | (A1 & B2 & C1) | (A1 & B3 & C1) | (A2 & B1 & C1) | (A2 & B2 & C1) | (A2 & B3 & C1) | (A3 & B1 & C1) | (A3 & B2 & C1) | (A3 & B3 & C1);
endmodule
module OA332x1_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1, input C2);
  assign Y = (A1 & B1 & C1) | (A1 & B1 & C2) | (A1 & B2 & C1) | (A1 & B2 & C2) | (A1 & B3 & C1) | (A1 & B3 & C2) | (A2 & B1 & C1) | (A2 & B1 & C2) | (A2 & B2 & C1) | (A2 & B2 & C2) | (A2 & B3 & C1) | (A2 & B3 & C2) | (A3 & B1 & C1) | (A3 & B1 & C2) | (A3 & B2 & C1) | (A3 & B2 & C2) | (A3 & B3 & C1) | (A3 & B3 & C2);
endmodule
module OA332x2_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1, input C2);
  assign Y = (A1 & B1 & C1) | (A1 & B1 & C2) | (A1 & B2 & C1) | (A1 & B2 & C2) | (A1 & B3 & C1) | (A1 & B3 & C2) | (A2 & B1 & C1) | (A2 & B1 & C2) | (A2 & B2 & C1) | (A2 & B2 & C2) | (A2 & B3 & C1) | (A2 & B3 & C2) | (A3 & B1 & C1) | (A3 & B1 & C2) | (A3 & B2 & C1) | (A3 & B2 & C2) | (A3 & B3 & C1) | (A3 & B3 & C2);
endmodule
module OA333x1_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1, input C2, input C3);
  assign Y = (A1 & B1 & C1) | (A1 & B1 & C2) | (A1 & B1 & C3) | (A1 & B2 & C1) | (A1 & B2 & C2) | (A1 & B2 & C3) | (A1 & B3 & C1) | (A1 & B3 & C2) | (A1 & B3 & C3) | (A2 & B1 & C1) | (A2 & B1 & C2) | (A2 & B1 & C3) | (A2 & B2 & C1) | (A2 & B2 & C2) | (A2 & B2 & C3) | (A2 & B3 & C1) | (A2 & B3 & C2) | (A2 & B3 & C3) | (A3 & B1 & C1) | (A3 & B1 & C2) | (A3 & B1 & C3) | (A3 & B2 & C1) | (A3 & B2 & C2) | (A3 & B2 & C3) | (A3 & B3 & C1) | (A3 & B3 & C2) | (A3 & B3 & C3);
endmodule
module OA333x2_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1, input C2, input C3);
  assign Y = (A1 & B1 & C1) | (A1 & B1 & C2) | (A1 & B1 & C3) | (A1 & B2 & C1) | (A1 & B2 & C2) | (A1 & B2 & C3) | (A1 & B3 & C1) | (A1 & B3 & C2) | (A1 & B3 & C3) | (A2 & B1 & C1) | (A2 & B1 & C2) | (A2 & B1 & C3) | (A2 & B2 & C1) | (A2 & B2 & C2) | (A2 & B2 & C3) | (A2 & B3 & C1) | (A2 & B3 & C2) | (A2 & B3 & C3) | (A3 & B1 & C1) | (A3 & B1 & C2) | (A3 & B1 & C3) | (A3 & B2 & C1) | (A3 & B2 & C2) | (A3 & B2 & C3) | (A3 & B3 & C1) | (A3 & B3 & C2) | (A3 & B3 & C3);
endmodule
module OA33x2_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3);
  assign Y = (A1 & B1) | (A1 & B2) | (A1 & B3) | (A2 & B1) | (A2 & B2) | (A2 & B3) | (A3 & B1) | (A3 & B2) | (A3 & B3);
endmodule
module OAI211xp5_ASAP7_75t_R (output Y, input A1, input A2, input B, input C);
  assign Y = (~A1 & ~A2) | (~B) | (~C);
endmodule
module OAI21x1_ASAP7_75t_R (output Y, input A1, input A2, input B);
  assign Y = (~A1 & ~A2) | (~B);
endmodule
module OAI21xp33_ASAP7_75t_R (output Y, input A1, input A2, input B);
  assign Y = (~A1 & ~A2) | (~B);
endmodule
module OAI21xp5_ASAP7_75t_R (output Y, input A1, input A2, input B);
  assign Y = (~A1 & ~A2) | (~B);
endmodule
module OAI221xp5_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2, input C);
  assign Y = (~A1 & ~A2) | (~B1 & ~B2) | (~C);
endmodule
module OAI222xp33_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2, input C1, input C2);
  assign Y = (~A1 & ~A2) | (~B1 & ~B2) | (~C1 & ~C2);
endmodule
module OAI22x1_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2);
  assign Y = (~A1 & ~A2) | (~B1 & ~B2);
endmodule
module OAI22xp33_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2);
  assign Y = (~A1 & ~A2) | (~B1 & ~B2);
endmodule
module OAI22xp5_ASAP7_75t_R (output Y, input A1, input A2, input B1, input B2);
  assign Y = (~A1 & ~A2) | (~B1 & ~B2);
endmodule
module OAI311xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input C1);
  assign Y = (~A1 & ~A2 & ~A3) | (~B1) | (~C1);
endmodule
module OAI31xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B);
  assign Y = (~A1 & ~A2 & ~A3) | (~B);
endmodule
module OAI31xp67_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B);
  assign Y = (~A1 & ~A2 & ~A3) | (~B);
endmodule
module OAI321xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input C);
  assign Y = (~A1 & ~A2 & ~A3) | (~B1 & ~B2) | (~C);
endmodule
module OAI322xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input C1, input C2);
  assign Y = (~A1 & ~A2 & ~A3) | (~B1 & ~B2) | (~C1 & ~C2);
endmodule
module OAI32xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2);
  assign Y = (~A1 & ~A2 & ~A3) | (~B1 & ~B2);
endmodule
module OAI331xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1);
  assign Y = (~A1 & ~A2 & ~A3) | (~B1 & ~B2 & ~B3) | (~C1);
endmodule
module OAI332xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1, input C2);
  assign Y = (~A1 & ~A2 & ~A3) | (~B1 & ~B2 & ~B3) | (~C1 & ~C2);
endmodule
module OAI333xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3, input C1, input C2, input C3);
  assign Y = (~A1 & ~A2 & ~A3) | (~B1 & ~B2 & ~B3) | (~C1 & ~C2 & ~C3);
endmodule
module OAI33xp33_ASAP7_75t_R (output Y, input A1, input A2, input A3, input B1, input B2, input B3);
  assign Y = (~A1 & ~A2 & ~A3) | (~B1 & ~B2 & ~B3);
endmodule
module DFFHQNx1_ASAP7_75t_R (output reg QN, input D, input CLK);
  always @(posedge CLK) QN <= ~D;
endmodule
module DFFHQNx2_ASAP7_75t_R (output reg QN, input D, input CLK);
  always @(posedge CLK) QN <= ~D;
endmodule
module DFFHQNx3_ASAP7_75t_R (output reg QN, input D, input CLK);
  always @(posedge CLK) QN <= ~D;
endmodule
