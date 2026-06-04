module tb;
  int total_checks;
  int total_errors;
  logic [31:0] a;
  logic [31:0] b;
  logic [63:0] y;

  logic [31:0] lfsr;
  int          rand_i;

  mult32 dut (
    .a(a),
    .b(b),
    .y(y)
  );

  task automatic check_case(
    input logic [31:0] a_i,
    input logic [31:0] b_i,
    input logic [63:0] expected,
    input int          case_id
  );
    begin
      a = a_i;
      b = b_i;
      #1;
      total_checks++;
      if (y !== expected) begin
        $display("TB_ERROR id=%0d expected=0x%016h actual=0x%016h", case_id, expected, y);
        total_errors++;
      end
    end
  endtask

  initial begin
    // --- deterministic cases ---
    check_case(32'h00000000, 32'h00000000, 64'h0000000000000000,  0);  // 0*0 = 0
    check_case(32'h00000001, 32'h00000001, 64'h0000000000000001,  1);  // 1*1 = 1
    check_case(32'h00000002, 32'h00000003, 64'h0000000000000006,  2);  // 2*3 = 6
    check_case(32'h00000003, 32'h00000002, 64'h0000000000000006,  3);  // 3*2 = 6 (commutativity)
    check_case(32'hFFFFFFFF, 32'h00000001, 64'h00000000FFFFFFFF,  4);  // 2^32-1 * 1
    check_case(32'h00000001, 32'hFFFFFFFF, 64'h00000000FFFFFFFF,  5);  // 1 * 2^32-1
    check_case(32'hFFFFFFFF, 32'hFFFFFFFF, 64'hFFFFFFFE00000001,  6);  // (2^32-1)^2
    check_case(32'h00010000, 32'h00010000, 64'h0000000100000000,  7);  // 65536*65536 = 2^32
    check_case(32'h80000000, 32'h00000002, 64'h0000000100000000,  8);  // 2^31 * 2 = 2^32
    check_case(32'h00000000, 32'hFFFFFFFF, 64'h0000000000000000,  9);  // 0 * max = 0
    check_case(32'hFFFFFFFF, 32'h00000000, 64'h0000000000000000, 10);  // max * 0 = 0
    check_case(32'h12345678, 32'h9ABCDEF0, 64'h0B00EA4E242D2080, 11);
    check_case(32'h7FFFFFFF, 32'h7FFFFFFF, 64'h3FFFFFFF00000001, 12);  // (2^31-1)^2
    check_case(32'hDEADBEEF, 32'hCAFEBABE, 64'hB092AB7B88CF5B62, 13);

    // --- 2000 pseudorandom cases (32-bit Fibonacci LFSR, seed=0xDEADBEEF) ---
    lfsr = 32'hDEADBEEF;
    for (rand_i = 0; rand_i < 2000; rand_i++) begin
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      // Use two consecutive LFSR steps for independent a and b
      check_case(lfsr,
                 {lfsr[15:0], lfsr[31:16]},
                 64'(lfsr) * 64'({lfsr[15:0], lfsr[31:16]}),
                 14 + rand_i);
    end

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
