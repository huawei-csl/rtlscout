
module adder_4bit(a,b,cin,clk,sum,cout);

  input  [3:0] a;
  input  [3:0] b;
  input  cin;
  input  clk;
  output [3:0] sum;
  output cout;
  reg  [3:0] sum_reg;
  reg  cout_reg;

  
  always @(posedge clk)
      begin
        sum_reg <= (b+cin)+a;
        cout_reg <= (cin & a[3]) | (b[3] & (cin | a[3]));
      end
  assign sum = sum_reg;
  assign cout = cout_reg;
endmodule

