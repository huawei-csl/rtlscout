`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [14:0] rgb1;
  logic [14:0] rgb2;
  logic  result;
  logic  expected_result;

  DiffCheck dut (
    .rgb1(rgb1),
    .rgb2(rgb2),
    .result(result)
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
      rc = $sscanf(line_buf, "%d %d %d", rgb1, rgb2, expected_result);
      if (rc != 3) continue;
      #1;
      total_checks = total_checks + 1;
      if (result !== expected_result) begin
        $display("TB_ERROR line=%0d rgb1=%0d rgb2=%0d exp_result=%0d act_result=%0d",
                 line_num, rgb1, rgb2, expected_result, result);
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
