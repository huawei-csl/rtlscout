`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  ten;
  logic  twenty;
  logic  ready;
  logic  expected_ready;
  logic  dispense;
  logic  expected_dispense;
  logic  return_sig;
  logic  expected_return_sig;
  logic  bill;
  logic  expected_bill;
  logic clk;
  logic clear;

  ticket_machine dut (
    .clk(clk),
    .clear(clear),
    .ten(ten),
    .twenty(twenty),
    .ready(ready),
    .dispense(dispense),
    .return_sig(return_sig),
    .bill(bill)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    clear = 1'b1;
    ten = '0;
    twenty = '0;

    repeat (3) @(posedge clk);
    #1;
    clear = 1'b0;

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
      rc = $sscanf(line_buf, "%h %h %h %h %h %h", ten, twenty, expected_ready, expected_dispense, expected_return_sig, expected_bill);
      if (rc != 6) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (ready !== expected_ready || dispense !== expected_dispense || return_sig !== expected_return_sig || bill !== expected_bill) begin
        $display("TB_ERROR line=%0d ten=%h twenty=%h exp_ready=%h act_ready=%h exp_dispense=%h act_dispense=%h exp_return_sig=%h act_return_sig=%h exp_bill=%h act_bill=%h",
                 line_num, ten, twenty, expected_ready, ready, expected_dispense, dispense, expected_return_sig, return_sig, expected_bill, bill);
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
