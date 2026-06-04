module DSP (clk, opMode, CEA, CEB, CEC, CECarryIn, CED, CEM, CEOpMode, CEP,
                rstA, rstB, rstC, rstCarryIn, rstD, rstM, rstOpMode, rstP,
                A, B, D, C, carryIn, BCIn, PCIn,
                BCOut, PCOut, P, M, carryOut, carryOutF);
    parameter A0REG = 0;
    parameter A1REG = 1;
    parameter B0REG = 0;
    parameter B1REG = 1;

    parameter CREG = 1;
    parameter DREG = 1;
    parameter MREG = 1;
    parameter PREG = 1;
    parameter CARRYINREG = 1;
    parameter CARRYOUTREG = 1;
    parameter OPMODEREG = 1;

    parameter CARRYINSEL = "OPMODE5";
    parameter B_INPUT = "DIRECT";
    parameter RSTTYPE = "SYNC";

    input clk, carryIn, rstA, rstB, rstC, rstCarryIn, rstD, rstM, rstOpMode, rstP,
            CEA, CEB, CEC, CECarryIn, CED, CEM, CEOpMode, CEP;
    input [17:0] A, B, D, BCIn;
    input [47:0] C, PCIn;
    input [7:0] opMode;

    output carryOut, carryOutF;
    output [17:0] BCOut;
    output [47:0] PCOut, P;
    output [35:0] M;

    wire [7:0] opModeRegOut;
    wire [17:0] dRegOut, bIn, b0RegOut, a0RegOut, PreASOut, b1RegIn,
                b1RegOut, a1RegOut;
    wire [35:0] mulOut;
    wire carryInRegIn, carryInRegOut, carryOutRegIn;
    wire [47:0] cRegOut, Z, X, pRegIn;

    RegMux #(8, RSTTYPE, OPMODEREG) opReg (clk, CEOpMode, rstOpMode, opMode, opModeRegOut);
    RegMux #(18, RSTTYPE, DREG) dReg (clk, CED, rstD, D, dRegOut);
    RegMux #(18, RSTTYPE, B0REG) b0Reg (clk, CEB, rstB, bIn, b0RegOut);
    RegMux #(18, RSTTYPE, A0REG) a0Reg (clk, CEA, rstA, A, a0RegOut);
    RegMux #(48, RSTTYPE, CREG) cReg (clk, CEC, rstC, C, cRegOut);

    PreAddSub PreAS (opModeRegOut[6], dRegOut, b0RegOut, PreASOut);

    RegMux #(18, RSTTYPE, B1REG) b1Reg (clk, CEB, rstB, b1RegIn, b1RegOut);
    RegMux #(18, RSTTYPE, A1REG) a1Reg (clk, CEA, rstA, a0RegOut, a1RegOut);

    Mul mul (b1RegOut, a1RegOut, mulOut);

    RegMux #(36, RSTTYPE, MREG) mulReg (clk, CEM, rstM, mulOut, M);
    RegMux #(1, RSTTYPE, CARRYINREG) carryInReg (clk, CECarryIn, rstCarryIn, carryInRegIn, carryInRegOut);

    PostAddSub PostAS (opModeRegOut[7], X, Z, carryInRegOut, pRegIn, carryOutRegIn);

    RegMux #(1, RSTTYPE, CARRYOUTREG) carryOutReg (clk, CECarryIn, rstCarryIn, carryOutRegIn, carryOut);
    RegMux #(48, RSTTYPE, PREG) pReg (clk, CEP, rstP, pRegIn, P);

    generate
        if (B_INPUT == "DIRECT") begin
            assign bIn = B;
        end else if (B_INPUT == "CASCADE") begin
            assign bIn = BCIn;
        end else begin
            assign bIn = 0;
        end
    endgenerate

    assign b1RegIn = (opModeRegOut[4] == 0)? b0RegOut : PreASOut;

    generate
        if (CARRYINSEL == "OPMODE5") begin
            assign carryInRegIn = opModeRegOut[5];
        end else if (CARRYINSEL == "CARRYIN") begin
            assign carryInRegIn = carryIn;
        end else begin
            assign carryInRegIn = 0;
        end
    endgenerate

    assign Z = (opModeRegOut[3:2] == 0)? 0 : (opModeRegOut[3:2] == 1)? PCIn :
                (opModeRegOut[3:2] == 2)? P : cRegOut;

    assign X = (opModeRegOut[1:0] == 0)? 0 : (opModeRegOut[1:0] == 1)? M :
                (opModeRegOut[1:0] == 2)? P : {dRegOut, a1RegOut, b1RegOut};

    assign BCOut = b1RegOut;
    assign carryOutF = carryOut;
    assign PCOut = P;
endmodule


module Mul (in0, in1, out);
    input [17:0] in0, in1;

    output [35:0] out;

    assign out = in0 * in1;
endmodule


module PostAddSub (mode, in0, in1, cin, out, carryOut);
    input mode, cin;
    input [47:0] in0, in1;

    output [47:0] out;
    output carryOut;

    assign {carryOut, out} = (mode == 0)? in0 + in1 + cin : in1 - in0 - cin;
endmodule

module PreAddSub (mode, in0, in1, out);
    input mode;
    input [17:0] in0, in1;

    output [17:0] out;

    assign out = (mode == 0)? in0 + in1 : in0 - in1;
endmodule


module RegMux (clk, CE, rst, data, out);
    parameter N = 18;
    parameter RSTTYPE = "SYNC";
    parameter DATAREG = 0;
    
    input clk, CE, rst;
    input [N - 1 : 0] data;

    output [N - 1 : 0] out;

    reg [N - 1 : 0] data_reg;

    generate
        if (DATAREG) begin
            if (RSTTYPE == "SYNC") begin
                always @(posedge clk) begin
                    if (rst) begin
                        data_reg <= 0;
                    end else if (CE) begin
                        data_reg <= data;
                    end
                end
            end else begin
                always @(posedge clk or posedge rst) begin
                    if (rst) begin
                        data_reg <= 0;
                    end else if (CE) begin
                        data_reg <= data;
                    end
                end
            end
        end
    endgenerate

    generate
        if (DATAREG) begin
            assign out = data_reg;
        end else begin
            assign out = data;
        end
    endgenerate
endmodule