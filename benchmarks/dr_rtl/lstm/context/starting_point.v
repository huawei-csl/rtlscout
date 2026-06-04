module lstm_cell(c_in, h_in, X, c_out, h_out);
	
	// X, c_in and h_in are assumed to be of 1x1. Change dimensions accordingly.
	
	//Parameters
	parameter DATA_WIDTH = 16;
	parameter FRACT_WIDTH = 8;
	
	//input clk, rst;
	
	//c_in : previous cell state 
	//h_in: tanh(o_in)
	input signed [DATA_WIDTH-1:0] c_in , h_in ;
	
        //X: current input
	input signed [DATA_WIDTH-1:0] X;
	
	//Weight arrays : {Wf, Wi ,Wc, Wo} where each element will be of size 2 x 1
	wire signed [DATA_WIDTH-1:0] Wf0, Wf1, Wi0, Wi1, Wc0, Wc1, Wo0, Wo1;
	
	//Bias arrays : {bf, bi ,bc, bo} where each element will be of size 1 x 1
	wire signed [DATA_WIDTH-1:0] bf, bi, bc ,bo;
	
	//Assign weights and biases
	//Random values assigned
	
	assign Wf0=16'h0101;
	assign Wf1=-16'h0101;
	
	assign Wi0=16'h0101;
	assign Wi1=16'h0101;
	
	assign Wc0=-16'h0101;
	assign Wc1=16'h0101;
	
	assign Wo0=16'h0101;
        assign Wo1=-16'h0111;
	
	assign bf=16'h0101;
	assign bi=-16'h0101;	
	assign bc=-16'h0111;
        assign bo=16'h0101;

	//c_out : current cell state
	//h_out : tanh(o_out)
	output wire signed [DATA_WIDTH-1:0] c_out, h_out;
	
	wire signed [DATA_WIDTH-1:0] f, i, iw, ct, cw, ot, out, c_act;
	wire signed [DATA_WIDTH + DATA_WIDTH - 1:0] z1, z2, z3;
	
	//f= Wf*{X h_in} + bf
	ConcatMultAdd A1(X, h_in, Wf0, Wf1, bf, f);
	
	//i= sigmoid(Wi*{X h_in} + bi)
	ConcatMultAdd A2(X, h_in, Wi0, Wi1, bi, iw);
	sigmoid S1(iw, i);
	
	//ct= tanh(Wc*{X h_in} + bc)
	ConcatMultAdd A3(X, h_in, Wc0, Wc1, bc, cw);
	tanh T1(cw, ct);
	
	assign z1 = (f*c_in)>>>FRACT_WIDTH;
	assign z2 = (i*ct)>>>FRACT_WIDTH;
	assign c_out = z1 + z2;
	
	//out=  sigmoid(Wo*{X h_in} + bo)
	ConcatMultAdd A4(X, h_in, Wo0, Wo1, bo, ot);
	sigmoid S2(ot,out);
	
	//h_out =(out*tanh(c_out))
	tanh T2(c_out,c_act);
	assign z3 = (out*c_act)>>>FRACT_WIDTH;
	assign h_out = z3;
	
endmodule


module sigmoid(X,Y);
	parameter DATA_WIDTH = 16;
	parameter FRACT_WIDTH = 8;
	
	input signed [DATA_WIDTH-1:0] X;
	output wire signed [DATA_WIDTH-1:0] Y;
	
	wire signed [DATA_WIDTH-1:0] s1;
	assign s1 = X+16'h0200; 
	
	assign Y = (X[DATA_WIDTH-1]) ? (
		// negative
		(X < -16'h0200)? 16'h0000 : (s1>>>2) ) //if x<2?0:x+2/4
		// positive
		: ( (X>16'h0200) ? 16'h0100: (s1>>>2) );


endmodule


module tanh(X,Y);
// DESCRIPTION: takes 1 input number and returns an approx of tanh as output

// input parameters
	parameter DATA_WIDTH = 16;
	parameter FRACT_WIDTH = 8;
	
// define ports
	input signed [DATA_WIDTH-1:0] X;
	output wire signed [DATA_WIDTH-1:0] Y;
		
	assign Y = (X[DATA_WIDTH-1]) ? (
		// negative
		(X < -16'h0100)? -16'h0100 : X )
		// positive
		: ( (X>16'h0100) ? 16'h0100: X );
endmodule


module ConcatMultAdd(X, h_in, W0, W1, b, out);	
	// Concatenates and Adds
	// incoming data signed and fixed width
	parameter DATA_WIDTH = 16;
	parameter FRACT_WIDTH = 8;
	
	input signed [DATA_WIDTH-1:0] X, h_in;
	input signed [DATA_WIDTH-1:0] W0, W1, b;
	output signed [DATA_WIDTH-1:0] out;

	// internal regs/wires
	wire signed [DATA_WIDTH+DATA_WIDTH-1:0] p1,p2;
	
	// behavior: out = W*{x,h_in} + b where W={W0,W1}
	assign p1 = (W0*X)>>>FRACT_WIDTH; 
	assign p2 = (W1*h_in)>>>FRACT_WIDTH;
	assign out = p1 + p2 + b;

endmodule
