`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  in_a;
  logic  in_b;
  logic  in_c;
  logic  in_d;
  logic  in_e;
  logic  in_f;
  logic  in_g;
  logic  in_h;
  logic  in_i;
  logic  sum;
  logic  expected_sum;
  logic clk;

  example dut (
    .clk(clk),
    .in_a(in_a),
    .in_b(in_b),
    .in_c(in_c),
    .in_d(in_d),
    .in_e(in_e),
    .in_f(in_f),
    .in_g(in_g),
    .in_h(in_h),
    .in_i(in_i),
    .sum(sum)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    in_a = '0;
    in_b = '0;
    in_c = '0;
    in_d = '0;
    in_e = '0;
    in_f = '0;
    in_g = '0;
    in_h = '0;
    in_i = '0;

    repeat (3) @(posedge clk);
    #1;

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
      rc = $sscanf(line_buf, "%d %d %d %d %d %d %d %d %d %d", in_a, in_b, in_c, in_d, in_e, in_f, in_g, in_h, in_i, expected_sum);
      if (rc != 10) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (sum !== expected_sum) begin
        $display("TB_ERROR line=%0d in_a=%0d in_b=%0d in_c=%0d in_d=%0d in_e=%0d in_f=%0d in_g=%0d in_h=%0d in_i=%0d exp_sum=%0d act_sum=%0d",
                 line_num, in_a, in_b, in_c, in_d, in_e, in_f, in_g, in_h, in_i, expected_sum, sum);
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
