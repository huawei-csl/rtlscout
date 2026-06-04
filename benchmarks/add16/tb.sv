module tb;
  int total_checks;
  int total_errors;
  logic [15:0] a;
  logic [15:0] b;
  logic [16:0] y;

  logic [31:0] lfsr;
  int          rand_i;

  add16 dut (
    .a(a),
    .b(b),
    .y(y)
  );

  task automatic check_case(
    input logic [15:0] a_i,
    input logic [15:0] b_i,
    input logic [16:0] expected,
    input int          case_id
  );
    begin
      a = a_i;
      b = b_i;
      #1;
      total_checks++;
      if (y !== expected) begin
        $display("TB_ERROR id=%0d expected=0x%05h actual=0x%05h", case_id, expected, y);
        total_errors++;
      end
    end
  endtask

  initial begin
    // --- deterministic cases ---
    check_case(16'h0000, 16'h0000, 17'h00000,  0);
    check_case(16'h0001, 16'h0002, 17'h00003,  1);
    check_case(16'hFFFF, 16'h0001, 17'h10000,  2);
    check_case(16'hFFFF, 16'hFFFF, 17'h1FFFE,  3);
    check_case(16'h7FFF, 16'h0001, 17'h08000,  4);
    check_case(16'h8000, 16'h8000, 17'h10000,  5);
    check_case(16'hABCD, 16'h5433, 17'h10000,  6);
    check_case(16'h00FF, 16'h00FF, 17'h001FE,  7);
    check_case(16'h5555, 16'h5555, 17'h0AAAA,  8);
    check_case(16'hFF00, 16'h00FF, 17'h0FFFF,  9);
    check_case(16'hFFFE, 16'hFFFE, 17'h1FFFC, 10);
    check_case(16'h8000, 16'h7FFF, 17'h0FFFF, 11);

    // --- 2000 pseudorandom cases (32-bit Fibonacci LFSR, seed=0xDEADBEEF) ---
    lfsr = 32'hDEADBEEF;
    for (rand_i = 0; rand_i < 2000; rand_i++) begin
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      check_case(lfsr[15:0], lfsr[31:16],
                 17'(lfsr[15:0]) + 17'(lfsr[31:16]),
                 12 + rand_i);
    end

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
