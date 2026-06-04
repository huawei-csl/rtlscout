module tb;
  int total_checks;
  int total_errors;
  logic [7:0]  a;
  logic [7:0]  b;
  logic [15:0] y;

  logic [31:0] lfsr;
  int          rand_i;

  mult8 dut (
    .a(a),
    .b(b),
    .y(y)
  );

  task automatic check_case(
    input logic [7:0]  a_i,
    input logic [7:0]  b_i,
    input logic [15:0] expected,
    input int          case_id
  );
    begin
      a = a_i;
      b = b_i;
      #1;
      total_checks++;
      if (y !== expected) begin
        $display("TB_ERROR id=%0d expected=0x%04h actual=0x%04h", case_id, expected, y);
        total_errors++;
      end
    end
  endtask

  initial begin
    // --- deterministic cases ---
    check_case(8'h00, 8'h00, 16'h0000,  0);  // 0*0 = 0
    check_case(8'h01, 8'h01, 16'h0001,  1);  // 1*1 = 1
    check_case(8'h02, 8'h03, 16'h0006,  2);  // 2*3 = 6
    check_case(8'h03, 8'h02, 16'h0006,  3);  // 3*2 = 6 (commutativity)
    check_case(8'hFF, 8'h01, 16'h00FF,  4);  // 255*1 = 255
    check_case(8'h01, 8'hFF, 16'h00FF,  5);  // 1*255 = 255
    check_case(8'hFF, 8'hFF, 16'hFE01,  6);  // 255*255 = 65025
    check_case(8'h10, 8'h10, 16'h0100,  7);  // 16*16 = 256
    check_case(8'h0A, 8'h0B, 16'h006E,  8);  // 10*11 = 110
    check_case(8'h80, 8'h02, 16'h0100,  9);  // 128*2 = 256
    check_case(8'h00, 8'hFF, 16'h0000, 10);  // 0*255 = 0
    check_case(8'hFF, 8'h00, 16'h0000, 11);  // 255*0 = 0
    check_case(8'h7F, 8'h7F, 16'h3F01, 12);  // 127*127 = 16129
    check_case(8'hAB, 8'hCD, 16'h88EF, 13);  // 171*205 = 35055

    // --- 2000 pseudorandom cases (32-bit Fibonacci LFSR, seed=0xDEADBEEF) ---
    lfsr = 32'hDEADBEEF;
    for (rand_i = 0; rand_i < 2000; rand_i++) begin
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      check_case(lfsr[7:0], lfsr[15:8],
                 16'(lfsr[7:0]) * 16'(lfsr[15:8]),
                 14 + rand_i);
    end

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
