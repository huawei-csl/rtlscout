`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  packet_valid;
  logic  read_enb_0;
  logic  read_enb_1;
  logic  read_enb_2;
  logic [7:0] datain;
  logic  vldout_0;
  logic  expected_vldout_0;
  logic  vldout_1;
  logic  expected_vldout_1;
  logic  vldout_2;
  logic  expected_vldout_2;
  logic  err;
  logic  expected_err;
  logic  busy;
  logic  expected_busy;
  logic [7:0] data_out_0;
  logic [7:0] expected_data_out_0;
  logic [7:0] data_out_1;
  logic [7:0] expected_data_out_1;
  logic [7:0] data_out_2;
  logic [7:0] expected_data_out_2;
  logic clk;
  logic resetn;

  router_top dut (
    .clk(clk),
    .resetn(resetn),
    .packet_valid(packet_valid),
    .read_enb_0(read_enb_0),
    .read_enb_1(read_enb_1),
    .read_enb_2(read_enb_2),
    .datain(datain),
    .vldout_0(vldout_0),
    .vldout_1(vldout_1),
    .vldout_2(vldout_2),
    .err(err),
    .busy(busy),
    .data_out_0(data_out_0),
    .data_out_1(data_out_1),
    .data_out_2(data_out_2)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    resetn = 1'b0;
    packet_valid = '0;
    read_enb_0 = '0;
    read_enb_1 = '0;
    read_enb_2 = '0;
    datain = '0;

    repeat (3) @(posedge clk);
    #1;
    resetn = 1'b1;

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
      rc = $sscanf(line_buf, "%h %h %h %h %h %h %h %h %h %h %h %h %h", packet_valid, read_enb_0, read_enb_1, read_enb_2, datain, expected_vldout_0, expected_vldout_1, expected_vldout_2, expected_err, expected_busy, expected_data_out_0, expected_data_out_1, expected_data_out_2);
      if (rc != 13) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (vldout_0 !== expected_vldout_0 || vldout_1 !== expected_vldout_1 || vldout_2 !== expected_vldout_2 || err !== expected_err || busy !== expected_busy || data_out_0 !== expected_data_out_0 || data_out_1 !== expected_data_out_1 || data_out_2 !== expected_data_out_2) begin
        $display("TB_ERROR line=%0d packet_valid=%h read_enb_0=%h read_enb_1=%h read_enb_2=%h datain=%h exp_vldout_0=%h act_vldout_0=%h exp_vldout_1=%h act_vldout_1=%h exp_vldout_2=%h act_vldout_2=%h exp_err=%h act_err=%h exp_busy=%h act_busy=%h exp_data_out_0=%h act_data_out_0=%h exp_data_out_1=%h act_data_out_1=%h exp_data_out_2=%h act_data_out_2=%h",
                 line_num, packet_valid, read_enb_0, read_enb_1, read_enb_2, datain, expected_vldout_0, vldout_0, expected_vldout_1, vldout_1, expected_vldout_2, vldout_2, expected_err, err, expected_busy, busy, expected_data_out_0, data_out_0, expected_data_out_1, data_out_1, expected_data_out_2, data_out_2);
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
