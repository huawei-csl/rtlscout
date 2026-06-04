// Testbench for smult8acc: y = a*b + c*d  (signed 8x8 + 8x8 -> signed 17)
module tb;
  int total_checks;
  int total_errors;

  logic signed [7:0]  a;
  logic signed [7:0]  b;
  logic signed [7:0]  c;
  logic signed [7:0]  d;
  logic signed [16:0] y;

  logic [31:0] lfsr;
  int          rand_i;
  int          exp_i;

  smult8acc dut (
    .a(a),
    .b(b),
    .c(c),
    .d(d),
    .y(y)
  );

  task automatic check_case(
    input logic signed [7:0] a_i,
    input logic signed [7:0] b_i,
    input logic signed [7:0] c_i,
    input logic signed [7:0] d_i,
    input int                expected,
    input int                case_id
  );
    logic signed [16:0] exp17;
    begin
      a = a_i;
      b = b_i;
      c = c_i;
      d = d_i;
      exp17 = 17'(expected);
      #1;
      total_checks++;
      if (y !== exp17) begin
        $display("TB_ERROR id=%0d a=%0d b=%0d c=%0d d=%0d expected=%0d actual=%0d",
                 case_id, a_i, b_i, c_i, d_i, expected, $signed(y));
        total_errors++;
      end
    end
  endtask

  initial begin
    // --- deterministic cases ---
    check_case(   0,    0,    0,    0,       0,  0);  // 0+0
    check_case(   1,    1,    1,    1,       2,  1);  // 1+1
    check_case(   2,    3,    4,    5,      26,  2);  // 6+20
    check_case( 127,  127,    0,    0,   16129,  3);  // 127*127
    check_case(-128, -128,    0,    0,   16384,  4);  // -128*-128
    check_case( 127,  127,  127,  127,   32258,  5);  // 2*16129
    check_case(-128, -128, -128, -128,   32768,  6);  // 2*16384 (requires 17-bit signed)
    check_case(-128,  127, -128,  127,  -32512,  7);  // 2*(-16256)  — lower bound
    check_case(  50,   10,   30,  -20,    -100,  8);  // 500 + (-600)
    check_case(  -1,   -1,    1,    1,       2,  9);  // 1 + 1
    check_case(  -2,    3,    4,    5,      14, 10);  // -6 + 20
    check_case(-128,  127,    0,    1,  -16256, 11);  // single neg product
    check_case( 127, -128,  127, -128,  -32512, 12);  // two neg products
    check_case(   0,   42,  -17,    0,       0, 13);  // zero terms
    check_case(  13,  -21,    8,   -9,    -345, 14);  // -273 + (-72)

    // --- 2000 pseudorandom cases (32-bit Fibonacci LFSR, seed=0xDEADBEEF) ---
    lfsr = 32'hDEADBEEF;
    for (rand_i = 0; rand_i < 2000; rand_i++) begin
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      // Interpret four LFSR bytes as signed 8-bit operands
      exp_i = int'($signed(lfsr[7:0]))   * int'($signed(lfsr[15:8]))
            + int'($signed(lfsr[23:16])) * int'($signed(lfsr[31:24]));
      check_case($signed(lfsr[7:0]),   $signed(lfsr[15:8]),
                 $signed(lfsr[23:16]), $signed(lfsr[31:24]),
                 exp_i, 15 + rand_i);
    end

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
