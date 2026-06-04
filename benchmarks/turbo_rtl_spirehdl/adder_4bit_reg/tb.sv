`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [3:0] a;
  logic [3:0] b;
  logic  cin;
  logic [3:0] sum;
  logic [3:0] expected_sum;
  logic  cout;
  logic  expected_cout;
  logic clk;

  adder_4bit dut (
    .clk(clk),
    .a(a),
    .b(b),
    .cin(cin),
    .sum(sum),
    .cout(cout)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    a = '0;
    b = '0;
    cin = '0;

    repeat (3) @(posedge clk);
    #1;

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
      rc = $sscanf(line_buf, "%d %d %d %d %d", a, b, cin, expected_sum, expected_cout);
      if (rc != 5) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (sum !== expected_sum || cout !== expected_cout) begin
        $display("TB_ERROR line=%0d a=%0d b=%0d cin=%0d exp_sum=%0d act_sum=%0d exp_cout=%0d act_cout=%0d",
                 line_num, a, b, cin, expected_sum, sum, expected_cout, cout);
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
