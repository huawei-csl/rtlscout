`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [31:0] dataIn;
  logic  insert;
  logic  flush;
  logic  remove;
  logic  clk_out;
  logic  full;
  logic  expected_full;
  logic  empty;
  logic  expected_empty;
  logic [31:0] dataOut;
  logic [31:0] expected_dataOut;
  logic clk_in;
  logic rst;

  fifo dut (
    .clk_in(clk_in),
    .rst(rst),
    .dataIn(dataIn),
    .insert(insert),
    .flush(flush),
    .remove(remove),
    .clk_out(clk_out),
    .full(full),
    .empty(empty),
    .dataOut(dataOut)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk_in = 0;
  always #5 clk_in = ~clk_in;

  initial begin
    total_checks = 0;
    total_errors = 0;
    rst = 1'b0;
    dataIn = '0;
    insert = '0;
    flush = '0;
    remove = '0;
    clk_out = '0;

    repeat (3) @(posedge clk_in);
    #1;
    rst = 1'b1;

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
      rc = $sscanf(line_buf, "%h %h %h %h %h %h %h %h", dataIn, insert, flush, remove, clk_out, expected_full, expected_empty, expected_dataOut);
      if (rc != 8) continue;
      @(posedge clk_in);
      #1;
      total_checks = total_checks + 1;
      if (full !== expected_full || empty !== expected_empty || dataOut !== expected_dataOut) begin
        $display("TB_ERROR line=%0d dataIn=%h insert=%h flush=%h remove=%h clk_out=%h exp_full=%h act_full=%h exp_empty=%h act_empty=%h exp_dataOut=%h act_dataOut=%h",
                 line_num, dataIn, insert, flush, remove, clk_out, expected_full, full, expected_empty, empty, expected_dataOut, dataOut);
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
