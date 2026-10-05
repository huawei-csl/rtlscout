module tb;
  int total_checks;
  int total_errors;
  logic [7:0] a;
  logic [7:0] b;
  logic [7:0] sum;

  adder dut (
    .a(a),
    .b(b),
    .sum(sum)
  );

  task automatic check_case(
    input logic [7:0] a_i,
    input logic [7:0] b_i,
    input logic [7:0] expected_i,
    input int case_id
  );
    begin
      a = a_i;
      b = b_i;
      #1;
      total_checks++;
      if (sum !== expected_i) begin
        $display("TB_ERROR id=%0d expected=0x%02h actual=0x%02h", case_id, expected_i, sum);
        total_errors++;
      end
    end
  endtask

  initial begin
    check_case(8'h00, 8'h00, 8'h00, 0);
    check_case(8'h01, 8'h02, 8'h03, 1);
    check_case(8'hFF, 8'h01, 8'h00, 2);

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
