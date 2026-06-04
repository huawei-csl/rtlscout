module tb;
  int total_checks;
  int total_errors;
  logic [31:0] a;
  logic [31:0] b;
  logic [32:0] y;

  logic [31:0] lfsr;
  logic [31:0] rand_a;
  int          rand_i;

  add32 dut (
    .a(a),
    .b(b),
    .y(y)
  );

  task automatic check_case(
    input logic [31:0] a_i,
    input logic [31:0] b_i,
    input logic [32:0] expected,
    input int          case_id
  );
    begin
      a = a_i;
      b = b_i;
      #1;
      total_checks++;
      if (y !== expected) begin
        $display("TB_ERROR id=%0d expected=0x%09h actual=0x%09h", case_id, expected, y);
        total_errors++;
      end
    end
  endtask

  initial begin
    // --- deterministic cases ---
    check_case(32'h00000000, 32'h00000000, 33'h000000000,  0);
    check_case(32'h00000001, 32'h00000002, 33'h000000003,  1);
    check_case(32'hFFFFFFFF, 32'h00000001, 33'h100000000,  2);
    check_case(32'hFFFFFFFF, 32'hFFFFFFFF, 33'h1FFFFFFFE,  3);
    check_case(32'h7FFFFFFF, 32'h00000001, 33'h080000000,  4);
    check_case(32'h80000000, 32'h80000000, 33'h100000000,  5);
    check_case(32'hABCDEF01, 32'h543210FF, 33'h100000000,  6);
    check_case(32'h0000FFFF, 32'h0000FFFF, 33'h00001FFFE,  7);
    check_case(32'h55555555, 32'h55555555, 33'h0AAAAAAAA,  8);
    check_case(32'hFFFF0000, 32'h0000FFFF, 33'h0FFFFFFFF,  9);
    check_case(32'hFFFFFFFE, 32'hFFFFFFFE, 33'h1FFFFFFFC, 10);
    check_case(32'h80000000, 32'h7FFFFFFF, 33'h0FFFFFFFF, 11);

    // --- 2000 pseudorandom cases (32-bit Fibonacci LFSR, seed=0xDEADBEEF) ---
    // Two LFSR advances per iteration: first gives a, second gives b.
    lfsr = 32'hDEADBEEF;
    for (rand_i = 0; rand_i < 2000; rand_i++) begin
      lfsr   = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      rand_a = lfsr;
      lfsr   = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      check_case(rand_a, lfsr,
                 {1'b0, rand_a} + {1'b0, lfsr},
                 12 + rand_i);
    end

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
