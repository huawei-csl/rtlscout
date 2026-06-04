`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [7:0] multiplicandA;
  logic [7:0] multiplierB;
  logic [7:0] multiplicandC;
  logic [7:0] multiplierD;
  logic  sel;
  logic [15:0] product;
  logic [15:0] expected_product;

  inefficient_multiplier dut (
    .multiplicandA(multiplicandA),
    .multiplierB(multiplierB),
    .multiplicandC(multiplicandC),
    .multiplierD(multiplierD),
    .sel(sel),
    .product(product)
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
      rc = $sscanf(line_buf, "%d %d %d %d %d %d", multiplicandA, multiplierB, multiplicandC, multiplierD, sel, expected_product);
      if (rc != 6) continue;
      #1;
      total_checks = total_checks + 1;
      if (product !== expected_product) begin
        $display("TB_ERROR line=%0d multiplicandA=%0d multiplierB=%0d multiplicandC=%0d multiplierD=%0d sel=%0d exp_product=%0d act_product=%0d",
                 line_num, multiplicandA, multiplierB, multiplicandC, multiplierD, sel, expected_product, product);
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
