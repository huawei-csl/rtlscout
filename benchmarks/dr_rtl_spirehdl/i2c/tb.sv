`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  arst_i;
  logic [2:0] wb_adr_i;
  logic [7:0] wb_dat_i;
  logic  wb_we_i;
  logic  wb_stb_i;
  logic  wb_cyc_i;
  logic  scl_pad_i;
  logic  sda_pad_i;
  logic [7:0] wb_dat_o;
  logic [7:0] expected_wb_dat_o;
  logic  wb_ack_o;
  logic  expected_wb_ack_o;
  logic  wb_inta_o;
  logic  expected_wb_inta_o;
  logic  scl_pad_o;
  logic  expected_scl_pad_o;
  logic  scl_padoen_o;
  logic  expected_scl_padoen_o;
  logic  sda_pad_o;
  logic  expected_sda_pad_o;
  logic  sda_padoen_o;
  logic  expected_sda_padoen_o;
  logic wb_clk_i;
  logic wb_rst_i;

  i2c_master_top dut (
    .wb_clk_i(wb_clk_i),
    .wb_rst_i(wb_rst_i),
    .arst_i(arst_i),
    .wb_adr_i(wb_adr_i),
    .wb_dat_i(wb_dat_i),
    .wb_we_i(wb_we_i),
    .wb_stb_i(wb_stb_i),
    .wb_cyc_i(wb_cyc_i),
    .scl_pad_i(scl_pad_i),
    .sda_pad_i(sda_pad_i),
    .wb_dat_o(wb_dat_o),
    .wb_ack_o(wb_ack_o),
    .wb_inta_o(wb_inta_o),
    .scl_pad_o(scl_pad_o),
    .scl_padoen_o(scl_padoen_o),
    .sda_pad_o(sda_pad_o),
    .sda_padoen_o(sda_padoen_o)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial wb_clk_i = 0;
  always #5 wb_clk_i = ~wb_clk_i;

  initial begin
    total_checks = 0;
    total_errors = 0;
    wb_rst_i = 1'b1;
    arst_i = '0;
    wb_adr_i = '0;
    wb_dat_i = '0;
    wb_we_i = '0;
    wb_stb_i = '0;
    wb_cyc_i = '0;
    scl_pad_i = '0;
    sda_pad_i = '0;

    repeat (3) @(posedge wb_clk_i);
    #1;
    wb_rst_i = 1'b0;

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
      rc = $sscanf(line_buf, "%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h", arst_i, wb_adr_i, wb_dat_i, wb_we_i, wb_stb_i, wb_cyc_i, scl_pad_i, sda_pad_i, expected_wb_dat_o, expected_wb_ack_o, expected_wb_inta_o, expected_scl_pad_o, expected_scl_padoen_o, expected_sda_pad_o, expected_sda_padoen_o);
      if (rc != 15) continue;
      @(posedge wb_clk_i);
      #1;
      total_checks = total_checks + 1;
      if (wb_dat_o !== expected_wb_dat_o || wb_ack_o !== expected_wb_ack_o || wb_inta_o !== expected_wb_inta_o || scl_pad_o !== expected_scl_pad_o || scl_padoen_o !== expected_scl_padoen_o || sda_pad_o !== expected_sda_pad_o || sda_padoen_o !== expected_sda_padoen_o) begin
        $display("TB_ERROR line=%0d arst_i=%h wb_adr_i=%h wb_dat_i=%h wb_we_i=%h wb_stb_i=%h wb_cyc_i=%h scl_pad_i=%h sda_pad_i=%h exp_wb_dat_o=%h act_wb_dat_o=%h exp_wb_ack_o=%h act_wb_ack_o=%h exp_wb_inta_o=%h act_wb_inta_o=%h exp_scl_pad_o=%h act_scl_pad_o=%h exp_scl_padoen_o=%h act_scl_padoen_o=%h exp_sda_pad_o=%h act_sda_pad_o=%h exp_sda_padoen_o=%h act_sda_padoen_o=%h",
                 line_num, arst_i, wb_adr_i, wb_dat_i, wb_we_i, wb_stb_i, wb_cyc_i, scl_pad_i, sda_pad_i, expected_wb_dat_o, wb_dat_o, expected_wb_ack_o, wb_ack_o, expected_wb_inta_o, wb_inta_o, expected_scl_pad_o, scl_pad_o, expected_scl_padoen_o, scl_padoen_o, expected_sda_pad_o, sda_pad_o, expected_sda_padoen_o, sda_padoen_o);
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
