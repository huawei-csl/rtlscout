`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

  logic  cen;
  logic  wait_n;
  logic  int_n;
  logic  nmi_n;
  logic  busrq_n;
  logic [7:0] dinst;
  logic [7:0] di;
  logic  m1_n;
  logic  expected_m1_n;
  logic  iorq;
  logic  expected_iorq;
  logic  no_read;
  logic  expected_no_read;
  logic  write;
  logic  expected_write;
  logic  rfsh_n;
  logic  expected_rfsh_n;
  logic  halt_n;
  logic  expected_halt_n;
  logic  busak_n;
  logic  expected_busak_n;
  logic [15:0] A;
  logic [15:0] expected_A;
  logic [7:0] d_o;
  logic [7:0] expected_d_o;
  logic [2:0] mc;
  logic [2:0] expected_mc;
  logic [2:0] ts;
  logic [2:0] expected_ts;
  logic  intcycle_n;
  logic  expected_intcycle_n;
  logic  IntE;
  logic  expected_IntE;
  logic  stop;
  logic  expected_stop;
  logic clk;
  logic reset_n;

  tv80_core dut (
    .clk(clk),
    .reset_n(reset_n),
    .cen(cen),
    .wait_n(wait_n),
    .int_n(int_n),
    .nmi_n(nmi_n),
    .busrq_n(busrq_n),
    .dinst(dinst),
    .di(di),
    .m1_n(m1_n),
    .iorq(iorq),
    .no_read(no_read),
    .write(write),
    .rfsh_n(rfsh_n),
    .halt_n(halt_n),
    .busak_n(busak_n),
    .A(A),
    .d_o(d_o),
    .mc(mc),
    .ts(ts),
    .intcycle_n(intcycle_n),
    .IntE(IntE),
    .stop(stop)
  );

  integer fd, rc, line_num;
  string line_buf;

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    total_checks = 0;
    total_errors = 0;
    reset_n = 1'b0;
    cen = '0;
    wait_n = '0;
    int_n = '0;
    nmi_n = '0;
    busrq_n = '0;
    dinst = '0;
    di = '0;

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
      rc = $sscanf(line_buf, "%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h", cen, wait_n, int_n, nmi_n, busrq_n, dinst, di, expected_m1_n, expected_iorq, expected_no_read, expected_write, expected_rfsh_n, expected_halt_n, expected_busak_n, expected_A, expected_d_o, expected_mc, expected_ts, expected_intcycle_n, expected_IntE, expected_stop);
      if (rc != 21) continue;
      @(posedge clk);
      #1;
      total_checks = total_checks + 1;
      if (m1_n !== expected_m1_n || iorq !== expected_iorq || no_read !== expected_no_read || write !== expected_write || rfsh_n !== expected_rfsh_n || halt_n !== expected_halt_n || busak_n !== expected_busak_n || A !== expected_A || d_o !== expected_d_o || mc !== expected_mc || ts !== expected_ts || intcycle_n !== expected_intcycle_n || IntE !== expected_IntE || stop !== expected_stop) begin
        $display("TB_ERROR line=%0d cen=%h wait_n=%h int_n=%h nmi_n=%h busrq_n=%h dinst=%h di=%h exp_m1_n=%h act_m1_n=%h exp_iorq=%h act_iorq=%h exp_no_read=%h act_no_read=%h exp_write=%h act_write=%h exp_rfsh_n=%h act_rfsh_n=%h exp_halt_n=%h act_halt_n=%h exp_busak_n=%h act_busak_n=%h exp_A=%h act_A=%h exp_d_o=%h act_d_o=%h exp_mc=%h act_mc=%h exp_ts=%h act_ts=%h exp_intcycle_n=%h act_intcycle_n=%h exp_IntE=%h act_IntE=%h exp_stop=%h act_stop=%h",
                 line_num, cen, wait_n, int_n, nmi_n, busrq_n, dinst, di, expected_m1_n, m1_n, expected_iorq, iorq, expected_no_read, no_read, expected_write, write, expected_rfsh_n, rfsh_n, expected_halt_n, halt_n, expected_busak_n, busak_n, expected_A, A, expected_d_o, d_o, expected_mc, mc, expected_ts, ts, expected_intcycle_n, intcycle_n, expected_IntE, IntE, expected_stop, stop);
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
