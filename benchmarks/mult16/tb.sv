module tb;
  int total_checks;
  int total_errors;
  logic [15:0] a;
  logic [15:0] b;
  logic [31:0] y;

  logic [31:0] lfsr;
  int          rand_i;

  mult16 dut (
    .a(a),
    .b(b),
    .y(y)
  );

  task automatic check_case(
    input logic [15:0] a_i,
    input logic [15:0] b_i,
    input logic [31:0] expected,
    input int          case_id
  );
    begin
      a = a_i;
      b = b_i;
      #1;
      total_checks++;
      if (y !== expected) begin
        $display("TB_ERROR id=%0d expected=0x%08h actual=0x%08h", case_id, expected, y);
        total_errors++;
      end
    end
  endtask

  initial begin
    // --- deterministic cases ---
    check_case(16'h0000, 16'h0000, 32'h00000000,  0);  // 0*0 = 0
    check_case(16'h0001, 16'h0001, 32'h00000001,  1);  // 1*1 = 1
    check_case(16'h0002, 16'h0003, 32'h00000006,  2);  // 2*3 = 6
    check_case(16'h00FF, 16'h00FF, 32'h0000FE01,  3);  // 255*255 = 65025
    check_case(16'hFFFF, 16'h0001, 32'h0000FFFF,  4);  // 65535*1 = 65535
    check_case(16'h0001, 16'hFFFF, 32'h0000FFFF,  5);  // 1*65535 = 65535
    check_case(16'hFFFF, 16'hFFFF, 32'hFFFE0001,  6);  // 65535*65535 = 4294836225
    check_case(16'h1234, 16'h5678, 32'h06260060,  7);  // 4660*22136 = 103152736
    check_case(16'h8000, 16'h0002, 32'h00010000,  8);  // 32768*2 = 65536
    check_case(16'h0100, 16'h0100, 32'h00010000,  9);  // 256*256 = 65536
    check_case(16'h0000, 16'hFFFF, 32'h00000000, 10);  // 0*65535 = 0
    check_case(16'hFFFF, 16'h0000, 32'h00000000, 11);  // 65535*0 = 0
    check_case(16'hABCD, 16'h0010, 32'h000ABCD0, 12);  // 43981*16 = 703696
    check_case(16'h7FFF, 16'h7FFF, 32'h3FFF0001, 13);  // 32767*32767 = 1073676289

    // --- 2000 pseudorandom cases (32-bit Fibonacci LFSR, seed=0xDEADBEEF) ---
    lfsr = 32'hDEADBEEF;
    for (rand_i = 0; rand_i < 2000; rand_i++) begin
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      check_case(lfsr[15:0], lfsr[31:16],
                 32'(lfsr[15:0]) * 32'(lfsr[31:16]),
                 14 + rand_i);
    end

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
