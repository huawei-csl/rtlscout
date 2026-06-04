module tb;
  int total_checks;
  int total_errors;
  logic clk;
  logic rst_n;
  logic en;
  logic [7:0] d;
  logic [7:0] q;

  reg_en dut (
    .clk(clk),
    .rst_n(rst_n),
    .en(en),
    .d(d),
    .q(q)
  );

  always #5 clk = ~clk;

  task automatic step_and_check(
    input logic rst_n_i,
    input logic en_i,
    input logic [7:0] d_i,
    input logic [7:0] expected_i,
    input int case_id
  );
    begin
      rst_n = rst_n_i;
      en = en_i;
      d = d_i;
      @(posedge clk);
      #1;
      total_checks++;
      if (q !== expected_i) begin
        $display("TB_ERROR id=%0d expected=0x%02h actual=0x%02h", case_id, expected_i, q);
        total_errors++;
      end
    end
  endtask

  initial begin
    clk = 1'b0;
    rst_n = 1'b1;
    en = 1'b0;
    d = 8'h00;

    step_and_check(1'b0, 1'b1, 8'hAA, 8'h00, 0);
    step_and_check(1'b1, 1'b1, 8'h12, 8'h12, 1);
    step_and_check(1'b1, 1'b0, 8'h34, 8'h12, 2);
    step_and_check(1'b1, 1'b1, 8'hBE, 8'hBE, 3);
    step_and_check(1'b0, 1'b0, 8'hFF, 8'h00, 4);

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
