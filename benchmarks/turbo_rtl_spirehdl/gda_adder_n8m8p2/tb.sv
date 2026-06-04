`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [7:0] in1;
  logic [7:0] in2;
  logic [8:0] res;
  logic [8:0] expected_res;

  GDA_St_N8_M8_P2 dut (
    .in1(in1),
    .in2(in2),
    .res(res)
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
      rc = $sscanf(line_buf, "%d %d %d", in1, in2, expected_res);
      if (rc != 3) continue;
      #1;
      total_checks = total_checks + 1;
      if (res !== expected_res) begin
        $display("TB_ERROR line=%0d in1=%0d in2=%0d exp_res=%0d act_res=%0d",
                 line_num, in1, in2, expected_res, res);
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
