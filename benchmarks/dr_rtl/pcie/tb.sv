`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  s_en;
  logic  d_en;
  logic  m_piso;
  logic  m_sipo;
  logic [7:0] datain;
  logic [7:0] dataout;
  logic [7:0] expected_dataout;
  logic clk;
  logic rst;

  top dut (
    .clk(clk),
    .rst(rst),
    .s_en(s_en),
    .d_en(d_en),
    .m_piso(m_piso),
    .m_sipo(m_sipo),
    .datain(datain),
    .dataout(dataout)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    rst = 1'b0;
    s_en = '0;
    d_en = '0;
    m_piso = '0;
    m_sipo = '0;
    datain = '0;

    repeat (3) @(posedge clk);
    #1;
    rst = 1'b1;

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
      rc = $sscanf(line_buf, "%h %h %h %h %h %h", s_en, d_en, m_piso, m_sipo, datain, expected_dataout);
      if (rc != 6) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (dataout !== expected_dataout) begin
        $display("TB_ERROR line=%0d s_en=%h d_en=%h m_piso=%h m_sipo=%h datain=%h exp_dataout=%h act_dataout=%h",
                 line_num, s_en, d_en, m_piso, m_sipo, datain, expected_dataout, dataout);
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
