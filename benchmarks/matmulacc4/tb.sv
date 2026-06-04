// Testbench for matmulacc4: Y = A·B + C
// A, B: 4×4 matrix, 4-bit unsigned elements (64-bit flat)
// C:    4×4 matrix, 10-bit unsigned elements (160-bit flat)
// Y:    4×4 matrix, 11-bit unsigned elements (176-bit flat)
//
// Bit-packing: element (r,c) of a/b → [(r*4+c)*4  +: 4]
//              element (r,c) of c   → [(r*4+c)*10 +: 10]
//              element (r,c) of y   → [(r*4+c)*11 +: 11]
module tb;
  int total_checks;
  int total_errors;

  logic [63:0]  a;
  logic [63:0]  b;
  logic [159:0] c;
  logic [175:0] y;

  logic [63:0]  a_rand;
  logic [63:0]  b_rand;
  logic [159:0] c_rand;
  logic [31:0]  lfsr;
  int           rand_i;

  matmulacc4 dut (
    .a(a),
    .b(b),
    .c(c),
    .y(y)
  );

  task automatic check_matmulacc(
    input logic [63:0]  a_i,
    input logic [63:0]  b_i,
    input logic [159:0] c_i,
    input int           case_id
  );
    logic [3:0]  am [0:3][0:3];
    logic [3:0]  bm [0:3][0:3];
    logic [9:0]  cm [0:3][0:3];
    int          acc;
    logic [10:0] act;
    logic        all_ok;
    int          r, cc, k;
    begin
      a = a_i;
      b = b_i;
      c = c_i;
      #1;
      for (r = 0; r < 4; r++)
        for (cc = 0; cc < 4; cc++) begin
          am[r][cc] = a_i[(r*4+cc)*4  +: 4];
          bm[r][cc] = b_i[(r*4+cc)*4  +: 4];
          cm[r][cc] = c_i[(r*4+cc)*10 +: 10];
        end
      all_ok = 1;
      total_checks++;
      for (r = 0; r < 4; r++)
        for (cc = 0; cc < 4; cc++) begin
          acc = int'(cm[r][cc]);
          for (k = 0; k < 4; k++)
            acc = acc + int'(am[r][k]) * int'(bm[k][cc]);
          act = y[(r*4+cc)*11 +: 11];
          if (act !== 11'(acc)) begin
            $display("TB_ERROR id=%0d row=%0d col=%0d expected=%0d actual=%0d",
              case_id, r, cc, acc, act);
            all_ok = 0;
          end
        end
      if (!all_ok) total_errors++;
    end
  endtask

  initial begin
    // --- deterministic cases ---

    // 0: A=0, B=0, C=0 → Y=0
    check_matmulacc(64'h0, 64'h0, 160'h0, 0);

    // 1: A=I, B=I, C=0 → Y=I  (identity × identity + 0 = identity)
    check_matmulacc(64'h1000_0100_0010_0001, 64'h1000_0100_0010_0001, 160'h0, 1);

    // 2: A=0, B=0, C=all-ones (every 10-bit element = 1) → Y=C
    check_matmulacc(64'h0, 64'h0,
      {16{10'd1}},   // 16 elements, each = 1 (packed as 10 bits)
      2);

    // 3: A=all-max, B=all-max, C=0 → Y=all-900 (same as matmul4 case)
    check_matmulacc(64'hFFFF_FFFF_FFFF_FFFF, 64'hFFFF_FFFF_FFFF_FFFF, 160'h0, 3);

    // 4: A=all-max, B=all-max, C=all-max (every 10-bit element=1023) → Y=all-1923
    check_matmulacc(64'hFFFF_FFFF_FFFF_FFFF, 64'hFFFF_FFFF_FFFF_FFFF,
      {16{10'd1023}},
      4);

    // 5: A=I, B=all-max, C=0 → Y=all-max (I·A = A)
    check_matmulacc(64'h1000_0100_0010_0001, 64'hFFFF_FFFF_FFFF_FFFF, 160'h0, 5);

    // 6: A=all-max, B=I, C=0 → Y=all-max (A·I = A)
    check_matmulacc(64'hFFFF_FFFF_FFFF_FFFF, 64'h1000_0100_0010_0001, 160'h0, 6);

    // 7: A=0, B=all-max, C=all-512 → Y=all-512 (0·B + C = C)
    check_matmulacc(64'h0, 64'hFFFF_FFFF_FFFF_FFFF,
      {16{10'd512}},
      7);

    // 8: A=I, B=I, C=all-ones → Y = I + all-ones
    check_matmulacc(64'h1000_0100_0010_0001, 64'h1000_0100_0010_0001,
      {16{10'd1}},
      8);

    // 9: Sequential A × reversed B + diagonal-C
    check_matmulacc(64'hFEDC_BA98_7654_3210, 64'h0123_4567_89AB_CDEF,
      160'h0,
      9);

    // --- 500 pseudorandom cases (32-bit Fibonacci LFSR, seed=0xCAFEBABE) ---
    lfsr = 32'hCAFEBABE;
    for (rand_i = 0; rand_i < 500; rand_i++) begin
      // 2 steps → 64-bit a
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      a_rand[63:32] = lfsr;
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      a_rand[31:0]  = lfsr;
      // 2 steps → 64-bit b
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      b_rand[63:32] = lfsr;
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      b_rand[31:0]  = lfsr;
      // 5 steps → 160-bit c (each 10-bit element, mask to 10 bits via packing)
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      c_rand[159:128] = lfsr;
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      c_rand[127:96]  = lfsr;
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      c_rand[95:64]   = lfsr;
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      c_rand[63:32]   = lfsr;
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      c_rand[31:0]    = lfsr;
      // Mask each 10-bit slot to stay in range (clamp upper 2 bits of each nibble-pair)
      // Elements are extracted as 10-bit slices; overflow beyond 10 bits is masked by the
      // testbench's 10'() cast in the check task, so raw LFSR bits are fine here.
      check_matmulacc(a_rand, b_rand, c_rand, 10 + rand_i);
    end

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
