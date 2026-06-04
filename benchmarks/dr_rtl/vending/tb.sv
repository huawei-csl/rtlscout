`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  condition;
  logic  sel;
  logic [1023:0] discountA;
  logic [1023:0] discountB;
  logic [1023:0] discountC;
  logic [1023:0] discountD;
  logic [1023:0] total_discount;
  logic [1023:0] expected_total_discount;
  logic  sell_signal;
  logic  expected_sell_signal;
  logic clk;
  logic reset;

  vending_machine dut (
    .clk(clk),
    .reset(reset),
    .condition(condition),
    .sel(sel),
    .discountA(discountA),
    .discountB(discountB),
    .discountC(discountC),
    .discountD(discountD),
    .total_discount(total_discount),
    .sell_signal(sell_signal)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    reset = 1'b1;
    condition = '0;
    sel = '0;
    discountA = '0;
    discountB = '0;
    discountC = '0;
    discountD = '0;

    repeat (3) @(posedge clk);
    #1;
    reset = 1'b0;

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
      rc = $sscanf(line_buf, "%h %h %h %h %h %h %h %h", condition, sel, discountA, discountB, discountC, discountD, expected_total_discount, expected_sell_signal);
      if (rc != 8) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (total_discount !== expected_total_discount || sell_signal !== expected_sell_signal) begin
        $display("TB_ERROR line=%0d condition=%h sel=%h discountA=%h discountB=%h discountC=%h discountD=%h exp_total_discount=%h act_total_discount=%h exp_sell_signal=%h act_sell_signal=%h",
                 line_num, condition, sel, discountA, discountB, discountC, discountD, expected_total_discount, total_discount, expected_sell_signal, sell_signal);
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
