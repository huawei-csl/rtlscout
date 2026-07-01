`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [7:0] a;
  logic [7:0] b;
  logic [8:0] sum;
  logic [8:0] expected_sum;

  example dut (
    .a(a),
    .b(b),
    .sum(sum)
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
      rc = $sscanf(line_buf, "%d %d %d", a, b, expected_sum);
      if (rc != 3) continue;
      #1;
      total_checks = total_checks + 1;
      if (sum !== expected_sum) begin
        $display("TB_ERROR line=%0d a=%0d b=%0d exp_sum=%0d act_sum=%0d",
                 line_num, a, b, expected_sum, sum);
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
