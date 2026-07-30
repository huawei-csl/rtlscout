module tb;
  int total_checks;
  int total_errors;

  logic [15:0] a;
  logic [15:0] b;
  logic [15:0] y;
  logic [15:0] expected_y;

  fp_mul_e5f10 dut (.a(a), .b(b), .y(y));

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
      rc = $sscanf(line_buf, "%d %d %d", a, b, expected_y);
      if (rc != 3) continue;
      #1;
      total_checks = total_checks + 1;
      if (y !== expected_y) begin
        $display("TB_ERROR line=%0d expected_y=%0d actual_y=%0d", line_num, expected_y, y);
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
