`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [2:0] sel;
  logic [63:0] data_in;
  logic [63:0] data_out;
  logic [63:0] expected_data_out;
  logic  done;
  logic  expected_done;
  logic clk;
  logic reset_n;

  sync_serial_communication_tx_rx dut (
    .clk(clk),
    .reset_n(reset_n),
    .sel(sel),
    .data_in(data_in),
    .data_out(data_out),
    .done(done)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    reset_n = 1'b0;
    sel = '0;
    data_in = '0;

    repeat (3) @(posedge clk);
    #1;
    reset_n = 1'b1;

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
      rc = $sscanf(line_buf, "%h %h %h %h", sel, data_in, expected_data_out, expected_done);
      if (rc != 4) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (data_out !== expected_data_out || done !== expected_done) begin
        $display("TB_ERROR line=%0d sel=%h data_in=%h exp_data_out=%h act_data_out=%h exp_done=%h act_done=%h",
                 line_num, sel, data_in, expected_data_out, data_out, expected_done, done);
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
