`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  i_start;
  logic [127:0] i_key;
  logic  o_done;
  logic  expected_o_done;
  logic [1407:0] o_expanded_key;
  logic [1407:0] expected_o_expanded_key;
  logic clk;
  logic rst_async_n;

  key_expansion_128aes dut (
    .clk(clk),
    .rst_async_n(rst_async_n),
    .i_start(i_start),
    .i_key(i_key),
    .o_done(o_done),
    .o_expanded_key(o_expanded_key)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    rst_async_n = 1'b0;
    i_start = '0;
    i_key = '0;

    repeat (3) @(posedge clk);
    #1;
    rst_async_n = 1'b1;

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
      rc = $sscanf(line_buf, "%h %h %h %h", i_start, i_key, expected_o_done, expected_o_expanded_key);
      if (rc != 4) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (o_done !== expected_o_done || o_expanded_key !== expected_o_expanded_key) begin
        $display("TB_ERROR line=%0d i_start=%h i_key=%h exp_o_done=%h act_o_done=%h exp_o_expanded_key=%h act_o_expanded_key=%h",
                 line_num, i_start, i_key, expected_o_done, o_done, expected_o_expanded_key, o_expanded_key);
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
