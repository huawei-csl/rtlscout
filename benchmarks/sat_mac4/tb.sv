module tb;
  int total_checks;
  int total_errors;
  logic [3:0] a;
  logic [3:0] b;
  logic [7:0] c;
  logic [7:0] y;

  sat_mac4 dut (
    .a(a),
    .b(b),
    .c(c),
    .y(y)
  );

  task automatic check_case(
    input logic [3:0] a_i,
    input logic [3:0] b_i,
    input logic [7:0] c_i,
    input int case_id
  );
    logic [8:0] sum9;
    logic [7:0] expected;
    begin
      a = a_i;
      b = b_i;
      c = c_i;
      sum9 = 9'(c_i) + 9'(a_i * b_i);
      expected = (sum9 > 9'd255) ? 8'hFF : sum9[7:0];
      #1;
      total_checks++;
      if (y !== expected) begin
        $display("TB_ERROR id=%0d a=%0d b=%0d c=%0d expected=0x%02h actual=0x%02h",
                 case_id, a_i, b_i, c_i, expected, y);
        total_errors++;
      end
    end
  endtask

  initial begin
    int id;
    id = 0;
    // corners
    check_case(4'd0,  4'd0,  8'd0,   id++);
    check_case(4'd15, 4'd15, 8'd255, id++);
    check_case(4'd15, 4'd15, 8'd0,   id++);   // 225, no saturation
    check_case(4'd15, 4'd15, 8'd30,  id++);   // exactly 255
    check_case(4'd15, 4'd15, 8'd31,  id++);   // first saturating sum
    check_case(4'd1,  4'd1,  8'd254, id++);   // exactly 255 via c
    check_case(4'd1,  4'd1,  8'd255, id++);   // saturate via c
    // exhaustive over a,b for a spread of c values
    for (int ai = 0; ai < 16; ai++)
      for (int bi = 0; bi < 16; bi++) begin
        check_case(ai[3:0], bi[3:0], 8'd0,   id++);
        check_case(ai[3:0], bi[3:0], 8'd37,  id++);
        check_case(ai[3:0], bi[3:0], 8'd128, id++);
        check_case(ai[3:0], bi[3:0], 8'd200, id++);
        check_case(ai[3:0], bi[3:0], 8'd255, id++);
      end

    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
