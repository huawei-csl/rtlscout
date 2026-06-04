`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [7:0] a;
  logic [7:0] b;
  logic [7:0] c;
  logic [7:0] d;
  logic [7:0] average;
  logic [7:0] expected_average;
  logic clk;
  logic reset;

  average_module dut (
    .clk(clk),
    .reset(reset),
    .a(a),
    .b(b),
    .c(c),
    .d(d),
    .average(average)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    reset = 1'b1;
    a = '0;
    b = '0;
    c = '0;
    d = '0;

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
      rc = $sscanf(line_buf, "%d %d %d %d %d", a, b, c, d, expected_average);
      if (rc != 5) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (average !== expected_average) begin
        $display("TB_ERROR line=%0d a=%0d b=%0d c=%0d d=%0d exp_average=%0d act_average=%0d",
                 line_num, a, b, c, d, expected_average, average);
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
