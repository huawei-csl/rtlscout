`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  cpu_en;
  logic [31:0] ram_rdata;
  logic [31:0] rom_data;
  logic [31:0] ram_addr;
  logic [31:0] expected_ram_addr;
  logic  ram_cen;
  logic  expected_ram_cen;
  logic [3:0] ram_flag;
  logic [3:0] expected_ram_flag;
  logic [31:0] ram_wdata;
  logic [31:0] expected_ram_wdata;
  logic  ram_wen;
  logic  expected_ram_wen;
  logic [31:0] rom_addr;
  logic [31:0] expected_rom_addr;
  logic  rom_en;
  logic  expected_rom_en;
  logic clk;
  logic rst;

  risclite_mx dut (
    .clk(clk),
    .rst(rst),
    .cpu_en(cpu_en),
    .ram_rdata(ram_rdata),
    .rom_data(rom_data),
    .ram_addr(ram_addr),
    .ram_cen(ram_cen),
    .ram_flag(ram_flag),
    .ram_wdata(ram_wdata),
    .ram_wen(ram_wen),
    .rom_addr(rom_addr),
    .rom_en(rom_en)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    rst = 1'b1;
    cpu_en = '0;
    ram_rdata = '0;
    rom_data = '0;

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
      rc = $sscanf(line_buf, "%h %h %h %h %h %h %h %h %h %h", cpu_en, ram_rdata, rom_data, expected_ram_addr, expected_ram_cen, expected_ram_flag, expected_ram_wdata, expected_ram_wen, expected_rom_addr, expected_rom_en);
      if (rc != 10) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (ram_addr !== expected_ram_addr || ram_cen !== expected_ram_cen || ram_flag !== expected_ram_flag || ram_wdata !== expected_ram_wdata || ram_wen !== expected_ram_wen || rom_addr !== expected_rom_addr || rom_en !== expected_rom_en) begin
        $display("TB_ERROR line=%0d cpu_en=%h ram_rdata=%h rom_data=%h exp_ram_addr=%h act_ram_addr=%h exp_ram_cen=%h act_ram_cen=%h exp_ram_flag=%h act_ram_flag=%h exp_ram_wdata=%h act_ram_wdata=%h exp_ram_wen=%h act_ram_wen=%h exp_rom_addr=%h act_rom_addr=%h exp_rom_en=%h act_rom_en=%h",
                 line_num, cpu_en, ram_rdata, rom_data, expected_ram_addr, ram_addr, expected_ram_cen, ram_cen, expected_ram_flag, ram_flag, expected_ram_wdata, ram_wdata, expected_ram_wen, ram_wen, expected_rom_addr, rom_addr, expected_rom_en, rom_en);
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
