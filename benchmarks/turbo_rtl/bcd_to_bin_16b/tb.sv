`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [19:0] numeros;
  logic [15:0] operador;
  logic [15:0] expected_operador;

  conversor_num_16b dut (
    .numeros(numeros),
    .operador(operador)
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
      rc = $sscanf(line_buf, "%d %d", numeros, expected_operador);
      if (rc != 2) continue;
      #1;
      total_checks = total_checks + 1;
      if (operador !== expected_operador) begin
        $display("TB_ERROR line=%0d numeros=%0d exp_operador=%0d act_operador=%0d",
                 line_num, numeros, expected_operador, operador);
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
