`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [31:0] bus_in;
  logic [1:0] data_type;
  logic [1:0] rk_sel;
  logic [1:0] key_out_sel;
  logic [3:0] round;
  logic [2:0] sbox_sel;
  logic [3:0] iv_en;
  logic [3:0] iv_sel_rd;
  logic [3:0] col_en_host;
  logic [3:0] col_en_cnt_unit;
  logic [3:0] key_host_en;
  logic [3:0] key_en;
  logic [1:0] key_sel_rd;
  logic [1:0] col_sel;
  logic [1:0] col_sel_host;
  logic  end_comp;
  logic  key_sel;
  logic  key_init;
  logic  bypass_rk;
  logic  bypass_key_en;
  logic  first_block;
  logic  last_round;
  logic  iv_cnt_en;
  logic  iv_cnt_sel;
  logic  enc_dec;
  logic  mode_ctr;
  logic  mode_cbc;
  logic  key_gen;
  logic  key_derivation_en;
  logic [31:0] col_bus;
  logic [31:0] expected_col_bus;
  logic [31:0] key_bus;
  logic [31:0] expected_key_bus;
  logic [31:0] iv_bus;
  logic [31:0] expected_iv_bus;
  logic  end_aes;
  logic  expected_end_aes;
  logic clk;
  logic rst_n;

  datapath dut (
    .clk(clk),
    .rst_n(rst_n),
    .bus_in(bus_in),
    .data_type(data_type),
    .rk_sel(rk_sel),
    .key_out_sel(key_out_sel),
    .round(round),
    .sbox_sel(sbox_sel),
    .iv_en(iv_en),
    .iv_sel_rd(iv_sel_rd),
    .col_en_host(col_en_host),
    .col_en_cnt_unit(col_en_cnt_unit),
    .key_host_en(key_host_en),
    .key_en(key_en),
    .key_sel_rd(key_sel_rd),
    .col_sel(col_sel),
    .col_sel_host(col_sel_host),
    .end_comp(end_comp),
    .key_sel(key_sel),
    .key_init(key_init),
    .bypass_rk(bypass_rk),
    .bypass_key_en(bypass_key_en),
    .first_block(first_block),
    .last_round(last_round),
    .iv_cnt_en(iv_cnt_en),
    .iv_cnt_sel(iv_cnt_sel),
    .enc_dec(enc_dec),
    .mode_ctr(mode_ctr),
    .mode_cbc(mode_cbc),
    .key_gen(key_gen),
    .key_derivation_en(key_derivation_en),
    .col_bus(col_bus),
    .key_bus(key_bus),
    .iv_bus(iv_bus),
    .end_aes(end_aes)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    rst_n = 1'b0;
    bus_in = '0;
    data_type = '0;
    rk_sel = '0;
    key_out_sel = '0;
    round = '0;
    sbox_sel = '0;
    iv_en = '0;
    iv_sel_rd = '0;
    col_en_host = '0;
    col_en_cnt_unit = '0;
    key_host_en = '0;
    key_en = '0;
    key_sel_rd = '0;
    col_sel = '0;
    col_sel_host = '0;
    end_comp = '0;
    key_sel = '0;
    key_init = '0;
    bypass_rk = '0;
    bypass_key_en = '0;
    first_block = '0;
    last_round = '0;
    iv_cnt_en = '0;
    iv_cnt_sel = '0;
    enc_dec = '0;
    mode_ctr = '0;
    mode_cbc = '0;
    key_gen = '0;
    key_derivation_en = '0;

    repeat (3) @(posedge clk);
    #1;
    rst_n = 1'b1;

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
      rc = $sscanf(line_buf, "%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h", bus_in, data_type, rk_sel, key_out_sel, round, sbox_sel, iv_en, iv_sel_rd, col_en_host, col_en_cnt_unit, key_host_en, key_en, key_sel_rd, col_sel, col_sel_host, end_comp, key_sel, key_init, bypass_rk, bypass_key_en, first_block, last_round, iv_cnt_en, iv_cnt_sel, enc_dec, mode_ctr, mode_cbc, key_gen, key_derivation_en, expected_col_bus, expected_key_bus, expected_iv_bus, expected_end_aes);
      if (rc != 33) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (col_bus !== expected_col_bus || key_bus !== expected_key_bus || iv_bus !== expected_iv_bus || end_aes !== expected_end_aes) begin
        $display("TB_ERROR line=%0d bus_in=%h data_type=%h rk_sel=%h key_out_sel=%h round=%h sbox_sel=%h iv_en=%h iv_sel_rd=%h col_en_host=%h col_en_cnt_unit=%h key_host_en=%h key_en=%h key_sel_rd=%h col_sel=%h col_sel_host=%h end_comp=%h key_sel=%h key_init=%h bypass_rk=%h bypass_key_en=%h first_block=%h last_round=%h iv_cnt_en=%h iv_cnt_sel=%h enc_dec=%h mode_ctr=%h mode_cbc=%h key_gen=%h key_derivation_en=%h exp_col_bus=%h act_col_bus=%h exp_key_bus=%h act_key_bus=%h exp_iv_bus=%h act_iv_bus=%h exp_end_aes=%h act_end_aes=%h",
                 line_num, bus_in, data_type, rk_sel, key_out_sel, round, sbox_sel, iv_en, iv_sel_rd, col_en_host, col_en_cnt_unit, key_host_en, key_en, key_sel_rd, col_sel, col_sel_host, end_comp, key_sel, key_init, bypass_rk, bypass_key_en, first_block, last_round, iv_cnt_en, iv_cnt_sel, enc_dec, mode_ctr, mode_cbc, key_gen, key_derivation_en, expected_col_bus, col_bus, expected_key_bus, key_bus, expected_iv_bus, iv_bus, expected_end_aes, end_aes);
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
