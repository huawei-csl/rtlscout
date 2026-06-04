module tb;
  int total_checks;
  int total_errors;
  logic [7:0] a;
  logic [7:0] b;
  logic sel;
  logic [7:0] y;

  mux2 dut (
    .a(a),
    .b(b),
    .sel(sel),
    .y(y)
  );

  task automatic check_case(
    input logic [7:0] a_i,
    input logic [7:0] b_i,
    input logic sel_i,
    input logic [7:0] expected_i,
    input int case_id
  );
    begin
      a = a_i;
      b = b_i;
      sel = sel_i;
      #1;
      total_checks++;
      if (y !== expected_i) begin
        $display("TB_ERROR id=%0d expected=0x%02h actual=0x%02h", case_id, expected_i, y);
        total_errors++;
      end
    end
  endtask

  initial begin
    check_case(8'h00, 8'hFF, 1'b0, 8'h00, 0);
    check_case(8'h00, 8'hFF, 1'b1, 8'hFF, 1);
    check_case(8'hAA, 8'h55, 1'b0, 8'hAA, 2);
    check_case(8'hAA, 8'h55, 1'b1, 8'h55, 3);

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
