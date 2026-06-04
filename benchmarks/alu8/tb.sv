module tb;
  int total_checks;
  int total_errors;
  logic [7:0] a;
  logic [7:0] b;
  logic [2:0] op;
  logic [7:0] y;
  logic zero;

  alu8 dut (
    .a(a),
    .b(b),
    .op(op),
    .y(y),
    .zero(zero)
  );

  task automatic check_case(
    input logic [7:0] a_i,
    input logic [7:0] b_i,
    input logic [2:0] op_i,
    input logic [7:0] expected_y,
    input logic expected_zero,
    input int case_id
  );
    begin
      a = a_i;
      b = b_i;
      op = op_i;
      #1;
      total_checks++;
      if ((y !== expected_y) || (zero !== expected_zero)) begin
        $display("TB_ERROR id=%0d expected=0x%02h actual=0x%02h exp_zero=%0d act_zero=%0d",
          case_id, expected_y, y, expected_zero, zero);
        total_errors++;
      end
    end
  endtask

  initial begin
    check_case(8'h01, 8'h02, 3'b000, 8'h03, 1'b0, 0);
    check_case(8'hFF, 8'h01, 3'b000, 8'h00, 1'b1, 1);
    check_case(8'h10, 8'h20, 3'b001, 8'hF0, 1'b0, 2);
    check_case(8'hAA, 8'h55, 3'b010, 8'h00, 1'b1, 3);
    check_case(8'hAA, 8'h55, 3'b011, 8'hFF, 1'b0, 4);
    check_case(8'h0F, 8'hF0, 3'b100, 8'hFF, 1'b0, 5);
    check_case(8'h00, 8'h00, 3'b101, 8'hFF, 1'b0, 6);
    check_case(8'h80, 8'h00, 3'b110, 8'h00, 1'b1, 7);
    check_case(8'h01, 8'h00, 3'b111, 8'h00, 1'b1, 8);

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
