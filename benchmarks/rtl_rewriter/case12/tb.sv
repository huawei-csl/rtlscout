`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [31:0] X;
  logic [31:0] Y;
  logic [31:0] Z;
  logic [31:0] P;
  logic [31:0] Q;
  logic [31:0] R;
  logic [31:0] S;
  logic [31:0] T;
  logic [31:0] output1;
  logic [31:0] expected_output1;
  logic [31:0] output2;
  logic [31:0] expected_output2;
  logic [31:0] output3;
  logic [31:0] expected_output3;
  logic [31:0] output4;
  logic [31:0] expected_output4;
  logic [31:0] output5;
  logic [31:0] expected_output5;
  logic [31:0] output6;
  logic [31:0] expected_output6;

  example dut (
    .X(X),
    .Y(Y),
    .Z(Z),
    .P(P),
    .Q(Q),
    .R(R),
    .S(S),
    .T(T),
    .output1(output1),
    .output2(output2),
    .output3(output3),
    .output4(output4),
    .output5(output5),
    .output6(output6)
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
      rc = $sscanf(line_buf, "%d %d %d %d %d %d %d %d %d %d %d %d %d %d", X, Y, Z, P, Q, R, S, T, expected_output1, expected_output2, expected_output3, expected_output4, expected_output5, expected_output6);
      if (rc != 14) continue;
      #1;
      total_checks = total_checks + 1;
      if (output1 !== expected_output1 || output2 !== expected_output2 || output3 !== expected_output3 || output4 !== expected_output4 || output5 !== expected_output5 || output6 !== expected_output6) begin
        $display("TB_ERROR line=%0d X=%0d Y=%0d Z=%0d P=%0d Q=%0d R=%0d S=%0d T=%0d exp_output1=%0d act_output1=%0d exp_output2=%0d act_output2=%0d exp_output3=%0d act_output3=%0d exp_output4=%0d act_output4=%0d exp_output5=%0d act_output5=%0d exp_output6=%0d act_output6=%0d",
                 line_num, X, Y, Z, P, Q, R, S, T, expected_output1, output1, expected_output2, output2, expected_output3, output3, expected_output4, output4, expected_output5, output5, expected_output6, output6);
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
