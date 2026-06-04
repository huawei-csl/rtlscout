`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [7:0] in_8b;
  logic  dataK;
  logic [9:0] out_10b;
  logic [9:0] expected_out_10b;

  encoder dut (
    .in_8b(in_8b),
    .dataK(dataK),
    .out_10b(out_10b)
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
      rc = $sscanf(line_buf, "%d %d %d", in_8b, dataK, expected_out_10b);
      if (rc != 3) continue;
      #1;
      total_checks = total_checks + 1;
      if (out_10b !== expected_out_10b) begin
        $display("TB_ERROR line=%0d in_8b=%0d dataK=%0d exp_out_10b=%0d act_out_10b=%0d",
                 line_num, in_8b, dataK, expected_out_10b, out_10b);
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
