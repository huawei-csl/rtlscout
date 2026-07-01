`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [31:0] A;
  logic [31:0] B;
  logic [31:0] C;
  logic [31:0] D;
  logic [31:0] E;
  logic [31:0] F;
  logic [31:0] G;
  logic [31:0] H;
  logic [31:0] result1;
  logic [31:0] expected_result1;
  logic [31:0] result2;
  logic [31:0] expected_result2;
  logic [31:0] result3;
  logic [31:0] expected_result3;
  logic [31:0] result4;
  logic [31:0] expected_result4;
  logic [31:0] result5;
  logic [31:0] expected_result5;
  logic [31:0] result6;
  logic [31:0] expected_result6;

  arithmetic_operations dut (
    .A(A),
    .B(B),
    .C(C),
    .D(D),
    .E(E),
    .F(F),
    .G(G),
    .H(H),
    .result1(result1),
    .result2(result2),
    .result3(result3),
    .result4(result4),
    .result5(result5),
    .result6(result6)
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
      rc = $sscanf(line_buf, "%d %d %d %d %d %d %d %d %d %d %d %d %d %d", A, B, C, D, E, F, G, H, expected_result1, expected_result2, expected_result3, expected_result4, expected_result5, expected_result6);
      if (rc != 14) continue;
      #1;
      total_checks = total_checks + 1;
      if (result1 !== expected_result1 || result2 !== expected_result2 || result3 !== expected_result3 || result4 !== expected_result4 || result5 !== expected_result5 || result6 !== expected_result6) begin
        $display("TB_ERROR line=%0d A=%0d B=%0d C=%0d D=%0d E=%0d F=%0d G=%0d H=%0d exp_result1=%0d act_result1=%0d exp_result2=%0d act_result2=%0d exp_result3=%0d act_result3=%0d exp_result4=%0d act_result4=%0d exp_result5=%0d act_result5=%0d exp_result6=%0d act_result6=%0d",
                 line_num, A, B, C, D, E, F, G, H, expected_result1, result1, expected_result2, result2, expected_result3, result3, expected_result4, result4, expected_result5, result5, expected_result6, result6);
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
