`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  x;
  logic  sel;
  logic [7:0] a;
  logic [7:0] b;
  logic [7:0] result;
  logic [7:0] expected_result;

  example dut (
    .x(x),
    .sel(sel),
    .a(a),
    .b(b),
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
      rc = $sscanf(line_buf, "%d %d %d %d %d", x, sel, a, b, expected_result);
      if (rc != 5) continue;
      #1;
      total_checks = total_checks + 1;
      if (result !== expected_result) begin
        $display("TB_ERROR line=%0d x=%0d sel=%0d a=%0d b=%0d exp_result=%0d act_result=%0d",
                 line_num, x, sel, a, b, expected_result, result);
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
