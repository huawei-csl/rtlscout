module tb;
  int total_checks;
  int total_errors;
  logic clk;
  logic rst_n;
  logic in;
  logic match;

  seq_det dut (
    .clk(clk),
    .rst_n(rst_n),
    .in(in),
    .match(match)
  );

  always #5 clk = ~clk;

  task automatic drive_and_check(
    input logic in_i,
    input logic expected_match,
    input int case_id
  );
    begin
      in = in_i;
      @(posedge clk);
      #1;
      total_checks++;
      if (match !== expected_match) begin
        $display("TB_ERROR id=%0d expected=%0d actual=%0d", case_id, expected_match, match);
        total_errors++;
      end
    end
  endtask

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    in = 1'b0;
    @(posedge clk);
    rst_n = 1'b1;

    // Stream: 1 0 1 1 0 1 1 (matches at positions 4 and 7, overlapping allowed)
    drive_and_check(1'b1, 1'b0, 0);
    drive_and_check(1'b0, 1'b0, 1);
    drive_and_check(1'b1, 1'b0, 2);
    drive_and_check(1'b1, 1'b1, 3);
    drive_and_check(1'b0, 1'b0, 4);
    drive_and_check(1'b1, 1'b0, 5);
    drive_and_check(1'b1, 1'b1, 6);

    // Reset behavior
    rst_n = 1'b0;
    drive_and_check(1'b1, 1'b0, 7);
    rst_n = 1'b1;
    drive_and_check(1'b0, 1'b0, 8);

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
