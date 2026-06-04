`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  en;
  logic  imem_we;
  logic [7:0] imem_addr;
  logic [15:0] imem_wdata;
  logic  rf_we;
  logic [1:0] rf_addr;
  logic [7:0] rf_wdata;
  logic [7:0] PC;
  logic [7:0] expected_PC;
  logic  halt;
  logic  expected_halt;
  logic [7:0] dbg_r0;
  logic [7:0] expected_dbg_r0;
  logic [7:0] dbg_r1;
  logic [7:0] expected_dbg_r1;
  logic [7:0] dbg_r2;
  logic [7:0] expected_dbg_r2;
  logic [7:0] dbg_r3;
  logic [7:0] expected_dbg_r3;
  logic [2:0] dbg_state;
  logic [2:0] expected_dbg_state;
  logic clk;
  logic rst;

  mini_cpu dut (
    .clk(clk),
    .rst(rst),
    .en(en),
    .imem_we(imem_we),
    .imem_addr(imem_addr),
    .imem_wdata(imem_wdata),
    .rf_we(rf_we),
    .rf_addr(rf_addr),
    .rf_wdata(rf_wdata),
    .PC(PC),
    .halt(halt),
    .dbg_r0(dbg_r0),
    .dbg_r1(dbg_r1),
    .dbg_r2(dbg_r2),
    .dbg_r3(dbg_r3),
    .dbg_state(dbg_state)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    rst = 1'b1;
    en = '0;
    imem_we = '0;
    imem_addr = '0;
    imem_wdata = '0;
    rf_we = '0;
    rf_addr = '0;
    rf_wdata = '0;

    repeat (3) @(posedge clk);
    #1;
    rst = 1'b0;

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
      rc = $sscanf(line_buf, "%h %h %h %h %h %h %h %h %h %h %h %h %h %h", en, imem_we, imem_addr, imem_wdata, rf_we, rf_addr, rf_wdata, expected_PC, expected_halt, expected_dbg_r0, expected_dbg_r1, expected_dbg_r2, expected_dbg_r3, expected_dbg_state);
      if (rc != 14) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (PC !== expected_PC || halt !== expected_halt || dbg_r0 !== expected_dbg_r0 || dbg_r1 !== expected_dbg_r1 || dbg_r2 !== expected_dbg_r2 || dbg_r3 !== expected_dbg_r3 || dbg_state !== expected_dbg_state) begin
        $display("TB_ERROR line=%0d en=%h imem_we=%h imem_addr=%h imem_wdata=%h rf_we=%h rf_addr=%h rf_wdata=%h exp_PC=%h act_PC=%h exp_halt=%h act_halt=%h exp_dbg_r0=%h act_dbg_r0=%h exp_dbg_r1=%h act_dbg_r1=%h exp_dbg_r2=%h act_dbg_r2=%h exp_dbg_r3=%h act_dbg_r3=%h exp_dbg_state=%h act_dbg_state=%h",
                 line_num, en, imem_we, imem_addr, imem_wdata, rf_we, rf_addr, rf_wdata, expected_PC, PC, expected_halt, halt, expected_dbg_r0, dbg_r0, expected_dbg_r1, dbg_r1, expected_dbg_r2, dbg_r2, expected_dbg_r3, dbg_r3, expected_dbg_state, dbg_state);
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
