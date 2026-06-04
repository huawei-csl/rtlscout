`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [7:0] opMode;
  logic  CEA;
  logic  CEB;
  logic  CEC;
  logic  CECarryIn;
  logic  CED;
  logic  CEM;
  logic  CEOpMode;
  logic  CEP;
  logic  rstA;
  logic  rstB;
  logic  rstC;
  logic  rstCarryIn;
  logic  rstD;
  logic  rstM;
  logic  rstOpMode;
  logic  rstP;
  logic [17:0] A;
  logic [17:0] B;
  logic [17:0] D;
  logic [47:0] C;
  logic  carryIn;
  logic [17:0] BCIn;
  logic [47:0] PCIn;
  logic [17:0] BCOut;
  logic [17:0] expected_BCOut;
  logic [47:0] PCOut;
  logic [47:0] expected_PCOut;
  logic [47:0] P;
  logic [47:0] expected_P;
  logic [35:0] M;
  logic [35:0] expected_M;
  logic  carryOut;
  logic  expected_carryOut;
  logic  carryOutF;
  logic  expected_carryOutF;
  logic clk;

  DSP dut (
    .clk(clk),
    .opMode(opMode),
    .CEA(CEA),
    .CEB(CEB),
    .CEC(CEC),
    .CECarryIn(CECarryIn),
    .CED(CED),
    .CEM(CEM),
    .CEOpMode(CEOpMode),
    .CEP(CEP),
    .rstA(rstA),
    .rstB(rstB),
    .rstC(rstC),
    .rstCarryIn(rstCarryIn),
    .rstD(rstD),
    .rstM(rstM),
    .rstOpMode(rstOpMode),
    .rstP(rstP),
    .A(A),
    .B(B),
    .D(D),
    .C(C),
    .carryIn(carryIn),
    .BCIn(BCIn),
    .PCIn(PCIn),
    .BCOut(BCOut),
    .PCOut(PCOut),
    .P(P),
    .M(M),
    .carryOut(carryOut),
    .carryOutF(carryOutF)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    opMode = '0;
    CEA = '0;
    CEB = '0;
    CEC = '0;
    CECarryIn = '0;
    CED = '0;
    CEM = '0;
    CEOpMode = '0;
    CEP = '0;
    rstA = '0;
    rstB = '0;
    rstC = '0;
    rstCarryIn = '0;
    rstD = '0;
    rstM = '0;
    rstOpMode = '0;
    rstP = '0;
    A = '0;
    B = '0;
    D = '0;
    C = '0;
    carryIn = '0;
    BCIn = '0;
    PCIn = '0;

    repeat (3) @(posedge clk);
    #1;

    fd = $fopen("vectors.dat", "r");
    if (fd == 0) begin
      $display("ERROR: cannot open vectors.dat");
      $fatal(1);
    end
    line_num = 0;
    while (!$feof(fd)) begin
      line_num = line_num + 1;
      void'($fgets(line_buf, fd));
      if (line_buf.len() == 0) continue;
      if (line_buf.substr(0, 0) == "#") continue;
      rc = $sscanf(line_buf, "%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h", opMode, CEA, CEB, CEC, CECarryIn, CED, CEM, CEOpMode, CEP, rstA, rstB, rstC, rstCarryIn, rstD, rstM, rstOpMode, rstP, A, B, D, C, carryIn, BCIn, PCIn, expected_BCOut, expected_PCOut, expected_P, expected_M, expected_carryOut, expected_carryOutF);
      if (rc != 30) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (BCOut !== expected_BCOut || PCOut !== expected_PCOut || P !== expected_P || M !== expected_M || carryOut !== expected_carryOut || carryOutF !== expected_carryOutF) begin
        $display("TB_ERROR line=%0d opMode=%h CEA=%h CEB=%h CEC=%h CECarryIn=%h CED=%h CEM=%h CEOpMode=%h CEP=%h rstA=%h rstB=%h rstC=%h rstCarryIn=%h rstD=%h rstM=%h rstOpMode=%h rstP=%h A=%h B=%h D=%h C=%h carryIn=%h BCIn=%h PCIn=%h exp_BCOut=%h act_BCOut=%h exp_PCOut=%h act_PCOut=%h exp_P=%h act_P=%h exp_M=%h act_M=%h exp_carryOut=%h act_carryOut=%h exp_carryOutF=%h act_carryOutF=%h",
                 line_num, opMode, CEA, CEB, CEC, CECarryIn, CED, CEM, CEOpMode, CEP, rstA, rstB, rstC, rstCarryIn, rstD, rstM, rstOpMode, rstP, A, B, D, C, carryIn, BCIn, PCIn, expected_BCOut, BCOut, expected_PCOut, PCOut, expected_P, P, expected_M, M, expected_carryOut, carryOut, expected_carryOutF, carryOutF);
        total_errors = total_errors + 1;
      end
    end
    $fclose(fd);
    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
