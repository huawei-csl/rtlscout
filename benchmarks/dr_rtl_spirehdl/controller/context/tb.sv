`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic [1:0] operation_mode;
  logic [1:0] aes_mode;
  logic  start;
  logic  disable_core;
  logic [2:0] sbox_sel;
  logic [2:0] expected_sbox_sel;
  logic [1:0] rk_sel;
  logic [1:0] expected_rk_sel;
  logic [1:0] key_out_sel;
  logic [1:0] expected_key_out_sel;
  logic [1:0] col_sel;
  logic [1:0] expected_col_sel;
  logic [3:0] key_en;
  logic [3:0] expected_key_en;
  logic [3:0] col_en;
  logic [3:0] expected_col_en;
  logic [3:0] round;
  logic [3:0] expected_round;
  logic  bypass_rk;
  logic  expected_bypass_rk;
  logic  bypass_key_en;
  logic  expected_bypass_key_en;
  logic  key_sel;
  logic  expected_key_sel;
  logic  iv_cnt_en;
  logic  expected_iv_cnt_en;
  logic  iv_cnt_sel;
  logic  expected_iv_cnt_sel;
  logic  key_derivation_en;
  logic  expected_key_derivation_en;
  logic  end_comp;
  logic  expected_end_comp;
  logic  key_init;
  logic  expected_key_init;
  logic  key_gen;
  logic  expected_key_gen;
  logic  mode_ctr;
  logic  expected_mode_ctr;
  logic  mode_cbc;
  logic  expected_mode_cbc;
  logic  last_round;
  logic  expected_last_round;
  logic  encrypt_decrypt;
  logic  expected_encrypt_decrypt;
  logic clk;
  logic rst_n;

  control_unit dut (
    .clk(clk),
    .rst_n(rst_n),
    .operation_mode(operation_mode),
    .aes_mode(aes_mode),
    .start(start),
    .disable_core(disable_core),
    .sbox_sel(sbox_sel),
    .rk_sel(rk_sel),
    .key_out_sel(key_out_sel),
    .col_sel(col_sel),
    .key_en(key_en),
    .col_en(col_en),
    .round(round),
    .bypass_rk(bypass_rk),
    .bypass_key_en(bypass_key_en),
    .key_sel(key_sel),
    .iv_cnt_en(iv_cnt_en),
    .iv_cnt_sel(iv_cnt_sel),
    .key_derivation_en(key_derivation_en),
    .end_comp(end_comp),
    .key_init(key_init),
    .key_gen(key_gen),
    .mode_ctr(mode_ctr),
    .mode_cbc(mode_cbc),
    .last_round(last_round),
    .encrypt_decrypt(encrypt_decrypt)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    rst_n = 1'b0;
    operation_mode = '0;
    aes_mode = '0;
    start = '0;
    disable_core = '0;

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
      rc = $sscanf(line_buf, "%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h", operation_mode, aes_mode, start, disable_core, expected_sbox_sel, expected_rk_sel, expected_key_out_sel, expected_col_sel, expected_key_en, expected_col_en, expected_round, expected_bypass_rk, expected_bypass_key_en, expected_key_sel, expected_iv_cnt_en, expected_iv_cnt_sel, expected_key_derivation_en, expected_end_comp, expected_key_init, expected_key_gen, expected_mode_ctr, expected_mode_cbc, expected_last_round, expected_encrypt_decrypt);
      if (rc != 24) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (sbox_sel !== expected_sbox_sel || rk_sel !== expected_rk_sel || key_out_sel !== expected_key_out_sel || col_sel !== expected_col_sel || key_en !== expected_key_en || col_en !== expected_col_en || round !== expected_round || bypass_rk !== expected_bypass_rk || bypass_key_en !== expected_bypass_key_en || key_sel !== expected_key_sel || iv_cnt_en !== expected_iv_cnt_en || iv_cnt_sel !== expected_iv_cnt_sel || key_derivation_en !== expected_key_derivation_en || end_comp !== expected_end_comp || key_init !== expected_key_init || key_gen !== expected_key_gen || mode_ctr !== expected_mode_ctr || mode_cbc !== expected_mode_cbc || last_round !== expected_last_round || encrypt_decrypt !== expected_encrypt_decrypt) begin
        $display("TB_ERROR line=%0d operation_mode=%h aes_mode=%h start=%h disable_core=%h exp_sbox_sel=%h act_sbox_sel=%h exp_rk_sel=%h act_rk_sel=%h exp_key_out_sel=%h act_key_out_sel=%h exp_col_sel=%h act_col_sel=%h exp_key_en=%h act_key_en=%h exp_col_en=%h act_col_en=%h exp_round=%h act_round=%h exp_bypass_rk=%h act_bypass_rk=%h exp_bypass_key_en=%h act_bypass_key_en=%h exp_key_sel=%h act_key_sel=%h exp_iv_cnt_en=%h act_iv_cnt_en=%h exp_iv_cnt_sel=%h act_iv_cnt_sel=%h exp_key_derivation_en=%h act_key_derivation_en=%h exp_end_comp=%h act_end_comp=%h exp_key_init=%h act_key_init=%h exp_key_gen=%h act_key_gen=%h exp_mode_ctr=%h act_mode_ctr=%h exp_mode_cbc=%h act_mode_cbc=%h exp_last_round=%h act_last_round=%h exp_encrypt_decrypt=%h act_encrypt_decrypt=%h",
                 line_num, operation_mode, aes_mode, start, disable_core, expected_sbox_sel, sbox_sel, expected_rk_sel, rk_sel, expected_key_out_sel, key_out_sel, expected_col_sel, col_sel, expected_key_en, key_en, expected_col_en, col_en, expected_round, round, expected_bypass_rk, bypass_rk, expected_bypass_key_en, bypass_key_en, expected_key_sel, key_sel, expected_iv_cnt_en, iv_cnt_en, expected_iv_cnt_sel, iv_cnt_sel, expected_key_derivation_en, key_derivation_en, expected_end_comp, end_comp, expected_key_init, key_init, expected_key_gen, key_gen, expected_mode_ctr, mode_ctr, expected_mode_cbc, mode_cbc, expected_last_round, last_round, expected_encrypt_decrypt, encrypt_decrypt);
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
