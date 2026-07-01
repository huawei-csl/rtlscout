`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [7:0] input_a;
  logic [7:0] input_b;
  logic [7:0] input_c;
  logic [7:0] input_d;
  logic [3:0] opcode;
  logic  sel;
  logic [7:0] result;
  logic [7:0] expected_result;
  logic  zero_flag;
  logic  expected_zero_flag;

  example dut (
    .input_a(input_a),
    .input_b(input_b),
    .input_c(input_c),
    .input_d(input_d),
    .opcode(opcode),
    .sel(sel),
    .result(result),
    .zero_flag(zero_flag)
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
      rc = $sscanf(line_buf, "%d %d %d %d %d %d %d %d", input_a, input_b, input_c, input_d, opcode, sel, expected_result, expected_zero_flag);
      if (rc != 8) continue;
      #1;
      total_checks = total_checks + 1;
      if (result !== expected_result || zero_flag !== expected_zero_flag) begin
        $display("TB_ERROR line=%0d input_a=%0d input_b=%0d input_c=%0d input_d=%0d opcode=%0d sel=%0d exp_result=%0d act_result=%0d exp_zero_flag=%0d act_zero_flag=%0d",
                 line_num, input_a, input_b, input_c, input_d, opcode, sel, expected_result, result, expected_zero_flag, zero_flag);
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
