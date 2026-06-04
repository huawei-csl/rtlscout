`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [15:0] c_in;
  logic [15:0] h_in;
  logic [15:0] X;
  logic [15:0] c_out;
  logic [15:0] expected_c_out;
  logic [15:0] h_out;
  logic [15:0] expected_h_out;

  lstm_cell dut (
    .c_in(c_in),
    .h_in(h_in),
    .X(X),
    .c_out(c_out),
    .h_out(h_out)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial begin
    total_checks = 0;
    total_errors = 0;
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
      rc = $sscanf(line_buf, "%h %h %h %h %h", c_in, h_in, X, expected_c_out, expected_h_out);
      if (rc != 5) continue;
      #1;
      total_checks = total_checks + 1;
      if (c_out !== expected_c_out || h_out !== expected_h_out) begin
        $display("TB_ERROR line=%0d c_in=%h h_in=%h X=%h exp_c_out=%h act_c_out=%h exp_h_out=%h act_h_out=%h",
                 line_num, c_in, h_in, X, expected_c_out, c_out, expected_h_out, h_out);
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
