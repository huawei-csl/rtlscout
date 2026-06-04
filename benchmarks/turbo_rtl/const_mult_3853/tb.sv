`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [31:0] i_data0;
  logic [31:0] o_data0;
  logic [31:0] expected_o_data0;

  multiplier_block dut (
    .i_data0(i_data0),
    .o_data0(o_data0)
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
      rc = $sscanf(line_buf, "%d %d", i_data0, expected_o_data0);
      if (rc != 2) continue;
      #1;
      total_checks = total_checks + 1;
      if (o_data0 !== expected_o_data0) begin
        $display("TB_ERROR line=%0d i_data0=%0d exp_o_data0=%0d act_o_data0=%0d",
                 line_num, i_data0, expected_o_data0, o_data0);
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
