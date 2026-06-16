`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  sel;
  logic  a;
  logic  y;
  logic  expected_y;

  mux_tree dut (
    .sel(sel),
    .a(a),
    .y(y)
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
      rc = $sscanf(line_buf, "%d %d %d", sel, a, expected_y);
      if (rc != 3) continue;
      #1;
      total_checks = total_checks + 1;
      if (y !== expected_y) begin
        $display("TB_ERROR line=%0d sel=%0d a=%0d exp_y=%0d act_y=%0d",
                 line_num, sel, a, expected_y, y);
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
