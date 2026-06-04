// Testbench for matmul4: 4×4 × 4×4 unsigned matrix multiply, 4-bit inputs, 10-bit outputs.
//
// Bit-packing: element (r,c) of a/b → bits [(r*4+c)*4 +: 4]
//              element (r,c) of y   → bits [(r*4+c)*10 +: 10]
module tb;
  int total_checks;
  int total_errors;

  logic [63:0]  a;   // 4×4 input matrix A, row-major, 4 bits/element
  logic [63:0]  b;   // 4×4 input matrix B, row-major, 4 bits/element
  logic [159:0] y;   // 4×4 result matrix,  row-major, 10 bits/element

  logic [63:0]  a_rand;
  logic [63:0]  b_rand;
  logic [31:0]  lfsr;
  int           rand_i;

  matmul4 dut (
    .a(a),
    .b(b),
    .y(y)
  );

  // Check one matrix multiply.  Computes expected internally and compares every
  // output element; counts one check (pass/fail) per call.
  task automatic check_matmul(
    input logic [63:0] a_i,
    input logic [63:0] b_i,
    input int          case_id
  );
    logic [3:0] am [0:3][0:3];
    logic [3:0] bm [0:3][0:3];
    int         acc;
    logic [9:0] act;
    logic       all_ok;
    int         r, c, k;
    begin
      a = a_i;
      b = b_i;
      #1;
      // Unpack flat inputs into 2-D arrays
      for (r = 0; r < 4; r++)
        for (c = 0; c < 4; c++) begin
          am[r][c] = a_i[(r*4+c)*4 +: 4];
          bm[r][c] = b_i[(r*4+c)*4 +: 4];
        end
      // Compare every output element against the software reference
      all_ok = 1;
      total_checks++;
      for (r = 0; r < 4; r++)
        for (c = 0; c < 4; c++) begin
          acc = 0;
          for (k = 0; k < 4; k++)
            acc = acc + int'(am[r][k]) * int'(bm[k][c]);
          act = y[(r*4+c)*10 +: 10];
          if (act !== 10'(acc)) begin
            $display("TB_ERROR id=%0d row=%0d col=%0d expected=%0d actual=%0d",
              case_id, r, c, acc, act);
            all_ok = 0;
          end
        end
      if (!all_ok) total_errors++;
    end
  endtask

  initial begin
    // --- deterministic cases ---

    // 0: Zero × Zero = Zero
    check_matmul(64'h0000_0000_0000_0000, 64'h0000_0000_0000_0000, 0);

    // 1: Identity × Identity = Identity
    //    identity encoding: element (r,r)=1, others=0 → 64'h1000_0100_0010_0001
    check_matmul(64'h1000_0100_0010_0001, 64'h1000_0100_0010_0001, 1);

    // 2: All-ones × All-ones = all-fours (Σk 1·1 = 4 per element)
    check_matmul(64'h1111_1111_1111_1111, 64'h1111_1111_1111_1111, 2);

    // 3: All-max × All-max = all-900 (Σk 15·15 = 900 per element)
    check_matmul(64'hFFFF_FFFF_FFFF_FFFF, 64'hFFFF_FFFF_FFFF_FFFF, 3);

    // 4: Zero × All-max = Zero
    check_matmul(64'h0000_0000_0000_0000, 64'hFFFF_FFFF_FFFF_FFFF, 4);

    // 5: All-max × Zero = Zero
    check_matmul(64'hFFFF_FFFF_FFFF_FFFF, 64'h0000_0000_0000_0000, 5);

    // 6: Identity × All-max = All-max (I·A = A)
    check_matmul(64'h1000_0100_0010_0001, 64'hFFFF_FFFF_FFFF_FFFF, 6);

    // 7: All-max × Identity = All-max (A·I = A)
    check_matmul(64'hFFFF_FFFF_FFFF_FFFF, 64'h1000_0100_0010_0001, 7);

    // 8: Diagonal-2 × Identity = Diagonal-2
    check_matmul(64'h2000_0200_0020_0002, 64'h1000_0100_0010_0001, 8);

    // 9: Sequential values [0..15] row-major × reversed [15..0]
    check_matmul(64'hFEDC_BA98_7654_3210, 64'h0123_4567_89AB_CDEF, 9);

    // --- 500 pseudorandom cases (32-bit Fibonacci LFSR, seed=0xDEADBEEF) ---
    lfsr = 32'hDEADBEEF;
    for (rand_i = 0; rand_i < 500; rand_i++) begin
      // Advance LFSR four times to fill 128 bits of randomness (64-bit a, 64-bit b)
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      a_rand[63:32] = lfsr;
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      a_rand[31:0]  = lfsr;
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      b_rand[63:32] = lfsr;
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      b_rand[31:0]  = lfsr;
      check_matmul(a_rand, b_rand, 10 + rand_i);
    end

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
