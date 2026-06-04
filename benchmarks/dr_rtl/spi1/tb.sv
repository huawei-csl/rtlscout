`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  cyc_i;
  logic  stb_i;
  logic [1:0] adr_i;
  logic  we_i;
  logic [7:0] dat_i;
  logic  miso_i;
  logic [7:0] dat_o;
  logic [7:0] expected_dat_o;
  logic  ack_o;
  logic  expected_ack_o;
  logic  inta_o;
  logic  expected_inta_o;
  logic  sck_o;
  logic  expected_sck_o;
  logic  mosi_o;
  logic  expected_mosi_o;
  logic clk_i;
  logic rst_i;

  simple_spi_top dut (
    .clk_i(clk_i),
    .rst_i(rst_i),
    .cyc_i(cyc_i),
    .stb_i(stb_i),
    .adr_i(adr_i),
    .we_i(we_i),
    .dat_i(dat_i),
    .miso_i(miso_i),
    .dat_o(dat_o),
    .ack_o(ack_o),
    .inta_o(inta_o),
    .sck_o(sck_o),
    .mosi_o(mosi_o)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk_i = 0;
  always #5 clk_i = ~clk_i;

  initial begin
    total_checks = 0;
    total_errors = 0;
    rst_i = 1'b0;
    cyc_i = '0;
    stb_i = '0;
    adr_i = '0;
    we_i = '0;
    dat_i = '0;
    miso_i = '0;

    repeat (3) @(posedge clk_i);
    #1;
    rst_i = 1'b1;

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
      rc = $sscanf(line_buf, "%h %h %h %h %h %h %h %h %h %h %h", cyc_i, stb_i, adr_i, we_i, dat_i, miso_i, expected_dat_o, expected_ack_o, expected_inta_o, expected_sck_o, expected_mosi_o);
      if (rc != 11) continue;
      @(posedge clk_i);
      #1;
      total_checks = total_checks + 1;
      if (dat_o !== expected_dat_o || ack_o !== expected_ack_o || inta_o !== expected_inta_o || sck_o !== expected_sck_o || mosi_o !== expected_mosi_o) begin
        $display("TB_ERROR line=%0d cyc_i=%h stb_i=%h adr_i=%h we_i=%h dat_i=%h miso_i=%h exp_dat_o=%h act_dat_o=%h exp_ack_o=%h act_ack_o=%h exp_inta_o=%h act_inta_o=%h exp_sck_o=%h act_sck_o=%h exp_mosi_o=%h act_mosi_o=%h",
                 line_num, cyc_i, stb_i, adr_i, we_i, dat_i, miso_i, expected_dat_o, dat_o, expected_ack_o, ack_o, expected_inta_o, inta_o, expected_sck_o, sck_o, expected_mosi_o, mosi_o);
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
