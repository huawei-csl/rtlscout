module tb;
  int total_checks;
  int total_errors;
  logic [3:0] a;
  logic [3:0] b;
  logic [7:0] y;

  logic [31:0] lfsr;
  int          rand_i;

  mult4 dut (
    .a(a),
    .b(b),
    .y(y)
  );

  task automatic check_case(
    input logic [3:0] a_i,
    input logic [3:0] b_i,
    input logic [7:0] expected,
    input int         case_id
  );
    begin
      a = a_i;
      b = b_i;
      #1;
      total_checks++;
      if (y !== expected) begin
        $display("TB_ERROR id=%0d expected=0x%02h actual=0x%02h", case_id, expected, y);
        total_errors++;
      end
    end
  endtask

  initial begin
    // --- deterministic cases ---
    check_case(4'h0, 4'h0, 8'h00,  0);  // 0*0 = 0
    check_case(4'h1, 4'h1, 8'h01,  1);  // 1*1 = 1
    check_case(4'h2, 4'h3, 8'h06,  2);  // 2*3 = 6
    check_case(4'h3, 4'h2, 8'h06,  3);  // 3*2 = 6 (commutativity)
    check_case(4'hF, 4'h1, 8'h0F,  4);  // 15*1 = 15
    check_case(4'h1, 4'hF, 8'h0F,  5);  // 1*15 = 15
    check_case(4'hF, 4'hF, 8'hE1,  6);  // 15*15 = 225
    check_case(4'h7, 4'h3, 8'h15,  7);  // 7*3 = 21
    check_case(4'h8, 4'h8, 8'h40,  8);  // 8*8 = 64
    check_case(4'hA, 4'h5, 8'h32,  9);  // 10*5 = 50
    check_case(4'h0, 4'hF, 8'h00, 10);  // 0*15 = 0
    check_case(4'hF, 4'h0, 8'h00, 11);  // 15*0 = 0

    // --- 2000 pseudorandom cases (32-bit Fibonacci LFSR, seed=0xDEADBEEF) ---
    lfsr = 32'hDEADBEEF;
    for (rand_i = 0; rand_i < 2000; rand_i++) begin
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      check_case(lfsr[3:0], lfsr[7:4],
                 8'(lfsr[3:0]) * 8'(lfsr[7:4]),
                 12 + rand_i);
    end

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
