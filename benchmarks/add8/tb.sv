module tb;
  int total_checks;
  int total_errors;
  logic [7:0] a;
  logic [7:0] b;
  logic [8:0] y;

  logic [31:0] lfsr;
  int          rand_i;

  add8 dut (
    .a(a),
    .b(b),
    .y(y)
  );

  task automatic check_case(
    input logic [7:0] a_i,
    input logic [7:0] b_i,
    input logic [8:0] expected,
    input int         case_id
  );
    begin
      a = a_i;
      b = b_i;
      #1;
      total_checks++;
      if (y !== expected) begin
        $display("TB_ERROR id=%0d expected=0x%03h actual=0x%03h", case_id, expected, y);
        total_errors++;
      end
    end
  endtask

  initial begin
    // --- deterministic cases ---
    check_case(8'h00, 8'h00, 9'h000,  0);
    check_case(8'h01, 8'h02, 9'h003,  1);
    check_case(8'hFF, 8'h01, 9'h100,  2);
    check_case(8'hFF, 8'hFF, 9'h1FE,  3);
    check_case(8'h7F, 8'h01, 9'h080,  4);
    check_case(8'h80, 8'h80, 9'h100,  5);
    check_case(8'hAB, 8'h55, 9'h100,  6);
    check_case(8'h0F, 8'h0F, 9'h01E,  7);
    check_case(8'h55, 8'h55, 9'h0AA,  8);
    check_case(8'hF0, 8'h0F, 9'h0FF,  9);
    check_case(8'hFE, 8'hFE, 9'h1FC, 10);
    check_case(8'h80, 8'h7F, 9'h0FF, 11);

    // --- 2000 pseudorandom cases (32-bit Fibonacci LFSR, seed=0xDEADBEEF) ---
    lfsr = 32'hDEADBEEF;
    for (rand_i = 0; rand_i < 2000; rand_i++) begin
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      check_case(lfsr[7:0], lfsr[15:8],
                 9'(lfsr[7:0]) + 9'(lfsr[15:8]),
                 12 + rand_i);
    end

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
