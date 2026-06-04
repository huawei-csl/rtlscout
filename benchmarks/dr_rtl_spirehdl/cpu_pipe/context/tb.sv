`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  f_ack;
  logic [15:0] f_dti;
  logic  g_ack;
  logic [15:0] g_dti;
  logic [15:0] f_adr;
  logic [15:0] expected_f_adr;
  logic [15:0] f_dto;
  logic [15:0] expected_f_dto;
  logic  f_stb;
  logic  expected_f_stb;
  logic  f_wre;
  logic  expected_f_wre;
  logic [15:0] g_adr;
  logic [15:0] expected_g_adr;
  logic [15:0] g_dto;
  logic [15:0] expected_g_dto;
  logic  g_stb;
  logic  expected_g_stb;
  logic  g_wre;
  logic  expected_g_wre;
  logic clk;
  logic rst;

  dcpu16_cpu dut (
    .clk(clk),
    .rst(rst),
    .f_ack(f_ack),
    .f_dti(f_dti),
    .g_ack(g_ack),
    .g_dti(g_dti),
    .f_adr(f_adr),
    .f_dto(f_dto),
    .f_stb(f_stb),
    .f_wre(f_wre),
    .g_adr(g_adr),
    .g_dto(g_dto),
    .g_stb(g_stb),
    .g_wre(g_wre)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    rst = 1'b1;
    f_ack = '0;
    f_dti = '0;
    g_ack = '0;
    g_dti = '0;

    repeat (3) @(posedge clk);
    #1;
    rst = 1'b0;

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
      rc = $sscanf(line_buf, "%h %h %h %h %h %h %h %h %h %h %h %h", f_ack, f_dti, g_ack, g_dti, expected_f_adr, expected_f_dto, expected_f_stb, expected_f_wre, expected_g_adr, expected_g_dto, expected_g_stb, expected_g_wre);
      if (rc != 12) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (f_adr !== expected_f_adr || f_dto !== expected_f_dto || f_stb !== expected_f_stb || f_wre !== expected_f_wre || g_adr !== expected_g_adr || g_dto !== expected_g_dto || g_stb !== expected_g_stb || g_wre !== expected_g_wre) begin
        $display("TB_ERROR line=%0d f_ack=%h f_dti=%h g_ack=%h g_dti=%h exp_f_adr=%h act_f_adr=%h exp_f_dto=%h act_f_dto=%h exp_f_stb=%h act_f_stb=%h exp_f_wre=%h act_f_wre=%h exp_g_adr=%h act_g_adr=%h exp_g_dto=%h act_g_dto=%h exp_g_stb=%h act_g_stb=%h exp_g_wre=%h act_g_wre=%h",
                 line_num, f_ack, f_dti, g_ack, g_dti, expected_f_adr, f_adr, expected_f_dto, f_dto, expected_f_stb, f_stb, expected_f_wre, f_wre, expected_g_adr, g_adr, expected_g_dto, g_dto, expected_g_stb, g_stb, expected_g_wre, g_wre);
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
