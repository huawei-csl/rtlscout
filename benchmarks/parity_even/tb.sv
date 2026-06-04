module tb;
  int total_checks;
  int total_errors;
  logic [7:0] data;
  logic parity;

  parity8 dut (
    .data(data),
    .parity(parity)
  );

  task automatic check_case(
    input logic [7:0] data_i,
    input logic expected_i,
    input int case_id
  );
    begin
      data = data_i;
      #1;
      total_checks++;
      if (parity !== expected_i) begin
        $display("TB_ERROR id=%0d expected=%0d actual=%0d", case_id, expected_i, parity);
        total_errors++;
      end
    end
  endtask

  initial begin
    check_case(8'h00, 1'b1, 0);
    check_case(8'h01, 1'b0, 1);
    check_case(8'h03, 1'b1, 2);
    check_case(8'hFF, 1'b1, 3);
    check_case(8'h7F, 1'b0, 4);

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
