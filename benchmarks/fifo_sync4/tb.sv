module tb;
  int total_checks;
  int total_errors;
  logic clk;
  logic rst_n;
  logic wr_en;
  logic rd_en;
  logic [7:0] din;
  logic [7:0] dout;
  logic full;
  logic empty;
  logic [2:0] count;

  fifo_sync4 dut (
    .clk(clk),
    .rst_n(rst_n),
    .wr_en(wr_en),
    .rd_en(rd_en),
    .din(din),
    .dout(dout),
    .full(full),
    .empty(empty),
    .count(count)
  );

  always #5 clk = ~clk;

  task automatic step(
    input logic wr_i,
    input logic rd_i,
    input logic [7:0] din_i
  );
    begin
      wr_en = wr_i;
      rd_en = rd_i;
      din = din_i;
      @(posedge clk);
      #1;
    end
  endtask

  task automatic check_state(
    input logic [7:0] exp_dout,
    input logic exp_full,
    input logic exp_empty,
    input logic [2:0] exp_count,
    input int case_id
  );
    begin
      total_checks++;
      if ((dout !== exp_dout) || (full !== exp_full) || (empty !== exp_empty) || (count !== exp_count)) begin
        $display("TB_ERROR id=%0d", case_id);
        total_errors++;
      end
    end
  endtask

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    wr_en = 1'b0;
    rd_en = 1'b0;
    din = 8'h00;

    @(posedge clk);
    #1;
    check_state(8'h00, 1'b0, 1'b1, 3'd0, 0);

    rst_n = 1'b1;

    step(1'b1, 1'b0, 8'h11);
    check_state(8'h00, 1'b0, 1'b0, 3'd1, 1);

    step(1'b1, 1'b0, 8'h22);
    check_state(8'h00, 1'b0, 1'b0, 3'd2, 2);

    step(1'b1, 1'b0, 8'h33);
    check_state(8'h00, 1'b0, 1'b0, 3'd3, 3);

    step(1'b1, 1'b0, 8'h44);
    check_state(8'h00, 1'b1, 1'b0, 3'd4, 4);

    // Read one
    step(1'b0, 1'b1, 8'h00);
    check_state(8'h11, 1'b0, 1'b0, 3'd3, 5);

    // Simultaneous read/write (FIFO not full/empty)
    step(1'b1, 1'b1, 8'h55);
    check_state(8'h22, 1'b0, 1'b0, 3'd3, 6);

    // Read remaining
    step(1'b0, 1'b1, 8'h00);
    check_state(8'h33, 1'b0, 1'b0, 3'd2, 7);

    step(1'b0, 1'b1, 8'h00);
    check_state(8'h44, 1'b0, 1'b0, 3'd1, 8);

    step(1'b0, 1'b1, 8'h00);
    check_state(8'h55, 1'b0, 1'b1, 3'd0, 9);

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
