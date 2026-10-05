// Self-checking testbench for pdpu_dot16 — posit dot-product-accumulate unit
// (PDPU, ISCAS 2023 reference architecture).  Reads vectors.dat (hex):
//   operands_a[127:0] operands_b[127:0]  acc[15:0]  expected_result[15:0]
// expected_result is the reference RTL's own output (the unit is
// architecturally inexact vs ideal posit math — ALIGN_WIDTH truncation — so
// the required behavior is bit-exactness to the reference implementation).
module tb;
  int total_checks;
  int total_errors;

  logic [127:0] operands_a;
  logic [127:0] operands_b;
  logic [15:0] acc;
  logic [15:0] result_o;
  logic [15:0] expected;

  pdpu_top dut (
    .operands_a(operands_a),
    .operands_b(operands_b),
    .acc(acc),
    .result_o(result_o)
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
      rc = $sscanf(line_buf, "%h %h %h %h", operands_a, operands_b, acc, expected);
      if (rc != 4) continue;
      #1;
      total_checks = total_checks + 1;
      if (result_o !== expected) begin
        if (total_errors < 20)
          $display("TB_ERROR line=%0d a=%032h b=%032h acc=%04h exp=%04h got=%04h",
                   line_num, operands_a, operands_b, acc, expected, result_o);
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
