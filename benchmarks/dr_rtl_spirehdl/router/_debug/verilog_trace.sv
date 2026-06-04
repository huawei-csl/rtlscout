// Probe testbench: drives the verilog router_top with vectors.dat inputs
// and $displays its internal FSM/FIFO state every cycle.
// See _debug/DEBUGGING.md for build + run instructions.

`timescale 1ns/1ps
module probe;
  logic clk = 0;
  always #5 clk = ~clk;

  logic resetn, packet_valid, read_enb_0, read_enb_1, read_enb_2;
  logic [7:0] datain;
  wire vldout_0, vldout_1, vldout_2, err, busy;
  wire [7:0] data_out_0, data_out_1, data_out_2;

  router_top dut (
    .clk(clk), .resetn(resetn),
    .packet_valid(packet_valid),
    .read_enb_0(read_enb_0), .read_enb_1(read_enb_1), .read_enb_2(read_enb_2),
    .datain(datain),
    .vldout_0(vldout_0), .vldout_1(vldout_1), .vldout_2(vldout_2),
    .err(err), .busy(busy),
    .data_out_0(data_out_0), .data_out_1(data_out_1), .data_out_2(data_out_2)
  );

  integer fd, rc, i;
  string line_buf;
  int    pv, re0, re1, re2, di, exp_v0, exp_v1, exp_v2, exp_err, exp_busy, exp_d0, exp_d1, exp_d2;

  task dump(input int cyc);
    $display("cyc=%0d IN[pv=%0d re0=%0d di=%02x] ps=%0d e0=%0d f0=%0d incr0=%0d rp0=%0d wp0=%0d cnt0=%0d d0r=%02x w_enb0=%0d dout=%02x fifo0[0]=%03x fifo0[1]=%03x fifo0[2]=%03x fifo0[3]=%03x",
      cyc,
      packet_valid, read_enb_0, datain,
      dut.fsm.present_state,
      dut.fifo[0].f.empty,
      dut.fifo[0].f.full,
      dut.fifo[0].f.incrementer,
      dut.fifo[0].f.read_ptr,
      dut.fifo[0].f.write_ptr,
      dut.fifo[0].f.count,
      dut.fifo[0].f.dataout,
      dut.s.write_enb[0],
      dut.r1.dout,
      dut.fifo[0].f.fifo[0],
      dut.fifo[0].f.fifo[1],
      dut.fifo[0].f.fifo[2],
      dut.fifo[0].f.fifo[3]
    );
  endtask

  initial begin
    resetn = 0; packet_valid = 0;
    read_enb_0 = 0; read_enb_1 = 0; read_enb_2 = 0;
    datain = 0;

    // 3-cycle reset
    repeat (3) @(posedge clk);
    #1;
    resetn = 1;

    fd = $fopen("../vectors.dat", "r");
    if (fd == 0) begin
      $display("ERROR cannot open vectors.dat");
      $finish;
    end
    i = 0;
    while (!$feof(fd) && i < 80) begin
      void'($fgets(line_buf, fd));
      if (line_buf.len() == 0) continue;
      if (line_buf.substr(0, 0) == "#") continue;
      rc = $sscanf(line_buf, "%h %h %h %h %h %h %h %h %h %h %h %h %h",
        pv, re0, re1, re2, di, exp_v0, exp_v1, exp_v2, exp_err, exp_busy, exp_d0, exp_d1, exp_d2);
      if (rc != 13) begin
        $display("sscanf_fail rc=%0d line=%s", rc, line_buf);
        continue;
      end
      packet_valid = pv;
      read_enb_0 = re0; read_enb_1 = re1; read_enb_2 = re2;
      datain = di;
      @(posedge clk);
      #1;
      dump(i);
      i = i + 1;
    end
    $fclose(fd);
    $finish;
  end
endmodule
