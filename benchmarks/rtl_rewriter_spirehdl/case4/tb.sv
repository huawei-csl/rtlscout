`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [31:0] x;
  logic [31:0] y;
  logic [31:0] expected_y;
  logic [31:0] z;
  logic [31:0] expected_z;
  logic [31:0] w;
  logic [31:0] expected_w;

  example dut (
    .x(x),
    .y(y),
    .z(z),
    .w(w)
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
      rc = $sscanf(line_buf, "%d %d %d %d", x, expected_y, expected_z, expected_w);
      if (rc != 4) continue;
      #1;
      total_checks = total_checks + 1;
      if (y !== expected_y || z !== expected_z || w !== expected_w) begin
        $display("TB_ERROR line=%0d x=%0d exp_y=%0d act_y=%0d exp_z=%0d act_z=%0d exp_w=%0d act_w=%0d",
                 line_num, x, expected_y, y, expected_z, z, expected_w, w);
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
