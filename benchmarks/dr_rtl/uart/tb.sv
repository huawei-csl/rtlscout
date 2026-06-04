`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [1:0] address;
  logic [31:0] write_data;
  logic  we;
  logic  rx;
  logic  re;
  logic  tx;
  logic  expected_tx;
  logic [7:0] read_data;
  logic [7:0] expected_read_data;
  logic clk;
  logic rst;

  uart_top_design dut (
    .clk(clk),
    .rst(rst),
    .address(address),
    .write_data(write_data),
    .we(we),
    .rx(rx),
    .re(re),
    .tx(tx),
    .read_data(read_data)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    rst = 1'b1;
    address = '0;
    write_data = '0;
    we = '0;
    rx = '0;
    re = '0;

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
      rc = $sscanf(line_buf, "%h %h %h %h %h %h %h", address, write_data, we, rx, re, expected_tx, expected_read_data);
      if (rc != 7) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (tx !== expected_tx || read_data !== expected_read_data) begin
        $display("TB_ERROR line=%0d address=%h write_data=%h we=%h rx=%h re=%h exp_tx=%h act_tx=%h exp_read_data=%h act_read_data=%h",
                 line_num, address, write_data, we, rx, re, expected_tx, tx, expected_read_data, read_data);
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
