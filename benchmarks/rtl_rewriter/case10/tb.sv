`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  x;
  logic  output_signal;
  logic  expected_output_signal;
  logic clk;
  logic reset;

  example dut (
    .clk(clk),
    .reset(reset),
    .x(x),
    .output_signal(output_signal)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    reset = 1'b1;
    x = '0;

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
      rc = $sscanf(line_buf, "%d %d", x, expected_output_signal);
      if (rc != 2) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (output_signal !== expected_output_signal) begin
        $display("TB_ERROR line=%0d x=%0d exp_output_signal=%0d act_output_signal=%0d",
                 line_num, x, expected_output_signal, output_signal);
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
