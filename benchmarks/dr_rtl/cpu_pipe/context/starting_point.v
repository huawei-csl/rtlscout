
/*
 
DCPU16 PIPELINE
===============

Consists of the following stages:

- Fetch (FE): fetches instructions from the FBUS.
- Decode (DE): decodes instructions.
- EA A (EA) : calculates EA for A
- EA B (EB) : calculates EA for B
- Load A (LA): loads operand A from ABUS.
- Load B (LB): loads operand B from ABUS.
- Execute (EX): performs the ALU operation.
- Save A (SA): saves operand A to the FBUS.

 0| 1| 2| 3| 0| 1| 2| 3| 0| 1| 2| 3
      FE|DE|EA|EB|LA|LB|EX|SA
                  FE|DE|EA|EB|LA|LB|EX|SA
                               FE|DE|EA|EB|LA|LB|EX|SA
 */

module dcpu16_cpu (/*AUTOARG*/
   // Outputs
   g_wre, g_stb, g_dto, g_adr, f_wre, f_stb, f_dto, f_adr,
   // Inputs
   rst, g_dti, g_ack, f_dti, f_ack, clk
   );

   /*AUTOOUTPUT*/
   // Beginning of automatic outputs (from unused autoinst outputs)
   output [15:0]	f_adr;			// From m0 of dcpu16_mbus.v
   output [15:0]	f_dto;			// From x0 of dcpu16_alu.v
   output		f_stb;			// From m0 of dcpu16_mbus.v
   output		f_wre;			// From m0 of dcpu16_mbus.v
   output [15:0]	g_adr;			// From m0 of dcpu16_mbus.v
   output [15:0]	g_dto;			// From x0 of dcpu16_alu.v
   output		g_stb;			// From m0 of dcpu16_mbus.v
   output		g_wre;			// From m0 of dcpu16_mbus.v
   // End of automatics
   /*AUTOINPUT*/
   // Beginning of automatic inputs (from unused autoinst inputs)
   input		clk;			// To c0 of dcpu16_ctl.v, ...
   input		f_ack;			// To c0 of dcpu16_ctl.v, ...
   input [15:0]		f_dti;			// To c0 of dcpu16_ctl.v, ...
   input		g_ack;			// To m0 of dcpu16_mbus.v
   input [15:0]		g_dti;			// To m0 of dcpu16_mbus.v
   input		rst;			// To c0 of dcpu16_ctl.v, ...
   // End of automatics
   /*AUTOWIRE*/
   // Beginning of automatic wires (for undeclared instantiated-module outputs)
   wire			CC;			// From x0 of dcpu16_alu.v
   wire			bra;			// From c0 of dcpu16_ctl.v
   wire			ena;			// From m0 of dcpu16_mbus.v
   wire [15:0]		ireg;			// From c0 of dcpu16_ctl.v
   wire [3:0]		opc;			// From c0 of dcpu16_ctl.v
   wire [1:0]		pha;			// From c0 of dcpu16_ctl.v
   wire [15:0]		regA;			// From m0 of dcpu16_mbus.v
   wire [15:0]		regB;			// From m0 of dcpu16_mbus.v
   wire [15:0]		regO;			// From x0 of dcpu16_alu.v
   wire [15:0]		regR;			// From x0 of dcpu16_alu.v
   wire [2:0]		rra;			// From c0 of dcpu16_ctl.v
   wire [15:0]		rrd;			// From r0 of dcpu16_regs.v
   wire [2:0]		rwa;			// From c0 of dcpu16_ctl.v
   wire [15:0]		rwd;			// From x0 of dcpu16_alu.v
   wire			rwe;			// From c0 of dcpu16_ctl.v
   wire			wpc;			// From m0 of dcpu16_mbus.v
   // End of automatics
   /*AUTOREG*/

   dcpu16_ctl
     c0 (/*AUTOINST*/
	 // Outputs
	 .ireg				(ireg[15:0]),
	 .pha				(pha[1:0]),
	 .opc				(opc[3:0]),
	 .rra				(rra[2:0]),
	 .rwa				(rwa[2:0]),
	 .rwe				(rwe),
	 .bra				(bra),
	 // Inputs
	 .CC				(CC),
	 .wpc				(wpc),
	 .f_dti				(f_dti[15:0]),
	 .f_ack				(f_ack),
	 .clk				(clk),
	 .ena				(ena),
	 .rst				(rst));   

   dcpu16_mbus
     m0 (/*AUTOINST*/
	 // Outputs
	 .g_adr				(g_adr[15:0]),
	 .g_stb				(g_stb),
	 .g_wre				(g_wre),
	 .f_adr				(f_adr[15:0]),
	 .f_stb				(f_stb),
	 .f_wre				(f_wre),
	 .ena				(ena),
	 .wpc				(wpc),
	 .regA				(regA[15:0]),
	 .regB				(regB[15:0]),
	 // Inputs
	 .g_dti				(g_dti[15:0]),
	 .g_ack				(g_ack),
	 .f_dti				(f_dti[15:0]),
	 .f_ack				(f_ack),
	 .bra				(bra),
	 .CC				(CC),
	 .regR				(regR[15:0]),
	 .rrd				(rrd[15:0]),
	 .ireg				(ireg[15:0]),
	 .regO				(regO[15:0]),
	 .pha				(pha[1:0]),
	 .clk				(clk),
	 .rst				(rst));
   
   dcpu16_alu
     x0 (/*AUTOINST*/
	 // Outputs
	 .f_dto				(f_dto[15:0]),
	 .g_dto				(g_dto[15:0]),
	 .rwd				(rwd[15:0]),
	 .regR				(regR[15:0]),
	 .regO				(regO[15:0]),
	 .CC				(CC),
	 // Inputs
	 .regA				(regA[15:0]),
	 .regB				(regB[15:0]),
	 .opc				(opc[3:0]),
	 .clk				(clk),
	 .rst				(rst),
	 .ena				(ena),
	 .pha				(pha[1:0]));
   
   
   dcpu16_regs
     r0 (/*AUTOINST*/
	 // Outputs
	 .rrd				(rrd[15:0]),
	 // Inputs
	 .rwd				(rwd[15:0]),
	 .rra				(rra[2:0]),
	 .rwa				(rwa[2:0]),
	 .rwe				(rwe),
	 .rst				(rst),
	 .ena				(ena),
	 .clk				(clk));
   
endmodule // dcpu16


module dcpu16_alu (/*AUTOARG*/
   // Outputs
   f_dto, g_dto, rwd, regR, regO, CC,
   // Inputs
   regA, regB, opc, clk, rst, ena, pha
   );

   output [15:0] f_dto,
		 g_dto,
		 rwd;
   
   output [15:0] regR,
		 regO;
   output 	 CC;   
   
   input [15:0]  regA,
		 regB;   
   
   input [3:0] 	 opc;
   
   input 	 clk,
		 rst,
		 ena;

   input [1:0] 	 pha;   

   wire [15:0] 	 src, // a
		 tgt; // b

   // P03: Signal duplication for fanout reduction within ALU
   // Partition operands by operation group to reduce net capacitance
   wire [15:0]	src_arith, // for add, mul operations
		src_logic, // for AND, OR, XOR operations
		src_compare, // for comparison operations
		tgt_arith, // for add, mul operations
		tgt_logic, // for AND, OR, XOR operations
		tgt_compare; // for comparison operations

   /*AUTOREG*/
   // Beginning of automatic regs (for this module's undeclared outputs)
   reg			CC;
   reg [15:0]		regO;
   reg [15:0]		regR;
   // End of automatics

   reg 		c;
   reg [15:0] 	add;
   reg [33:0] 	mul;
   reg [31:0] 	shl,
		shr;

   assign f_dto = regR;
   assign g_dto = regR;
   assign rwd = regR;

   assign src = regA;
   assign tgt = regB;

   // P03: Duplicate src/tgt to partition fanout
   // Each duplicate carries the same value but drives a subset of operations
   assign src_arith = regA;
   assign src_logic = regA;
   assign src_compare = regA;
   assign tgt_arith = regB;
   assign tgt_logic = regB;
   assign tgt_compare = regB;   

   // adder - P03: use duplicated signals to partition fanout
   always @(/*AUTOSENSE*/opc or src_arith or tgt_arith) begin
      {c,add} <= (~opc[0]) ? (src_arith + tgt_arith) : (src_arith - tgt_arith);
      mul <= {1'b0,src_arith} * {1'b0,tgt_arith};
      shl <= src_arith << tgt_arith;
      shr <= src_arith >> tgt_arith;
   end

   
   always @(posedge clk)
     if (rst) begin
	/*AUTORESET*/
	// Beginning of autoreset for uninitialized flops
	CC <= 1'h0;
	regO <= 16'h0;
	regR <= 16'h0;
	// End of automatics
     end else if (ena) begin

	// 0x1: SET a, b - sets a to b
	// 0x2: ADD a, b - sets a to a+b, sets O to 0x0001 if there's an overflow, 0x0 otherwise
	// 0x3: SUB a, b - sets a to a-b, sets O to 0xffff if there's an underflow, 0x0 otherwise
	// 0x4: MUL a, b - sets a to a*b, sets O to ((a*b)>>16)&0xffff
	// 0x5: DIV a, b - sets a to a/b, sets O to ((a<<16)/b)&0xffff. if b==0, sets a and O to 0 instead.
	// 0x6: MOD a, b - sets a to a%b. if b==0, sets a to 0 instead.
	// 0x7: SHL a, b - sets a to a<<b, sets O to ((a<<b)>>16)&0xffff
	// 0x8: SHR a, b - sets a to a>>b, sets O to ((a<<16)>>b)&0xffff	 
	// 0x9: AND a, b - sets a to a&b
	// 0xa: BOR a, b - sets a to a|b
	// 0xb: XOR a, b - sets a to a^b

	if (pha == 2'o0)
	  case (opc)
	    4'h2: regO <= {15'd0,c};
	    4'h3: regO <= {(16){c}};
	    4'h4: regO <= mul[31:16];
	    4'h7: regO <= shl[31:16];
	    4'h8: regO <= shr[15:0];
	    default: regO <= regO;	    
	  endcase // case (opc)

	if (pha == 2'o0)
	  case (opc)
	    4'h0: regR <= src;
	    4'h1: regR <= tgt;
	    4'h2: regR <= add;
	    4'h3: regR <= add;
	    4'h4: regR <= mul[15:0];
	    4'h7: regR <= shl[15:0];
	    4'h8: regR <= shr[31:16];
	    4'h9: regR <= src_logic & tgt_logic;
	    4'hA: regR <= src_logic | tgt_logic;
	    4'hB: regR <= src_logic ^ tgt_logic;
	    default: regR <= 16'hX;
	  endcase // case (opc)	
	
	/*
	if (pha == 2'o0)
	case (opc)

	  4'h0: {regO, regR} <= {regO, src};	  

	  // 0x1: SET a, b - sets a to b
	  4'h1: {regO, regR} <= {regO, tgt};

	  // 0x2: ADD a, b - sets a to a+b, sets O to 0x0001 if there's an overflow, 0x0 otherwise
	  // 0x3: SUB a, b - sets a to a-b, sets O to 0xffff if there's an underflow, 0x0 otherwise
	  // 0x4: MUL a, b - sets a to a*b, sets O to ((a*b)>>16)&0xffff
	  // 0x5: DIV a, b - sets a to a/b, sets O to ((a<<16)/b)&0xffff. if b==0, sets a and O to 0 instead.
	  // 0x6: MOD a, b - sets a to a%b. if b==0, sets a to 0 instead.
	  4'h2, 4'h3: {regO, regR} <= (opc[0]) ? 
				      {{(16){c}},as} : 
				      {15'd0,c,as};	  
	  4'h4: {regO, regR} <= {1'b0,src} * {1'b0,tgt}; // force 17x17 unsigned

	  // 0x7: SHL a, b - sets a to a<<b, sets O to ((a<<b)>>16)&0xffff
	  // 0x8: SHR a, b - sets a to a>>b, sets O to ((a<<16)>>b)&0xffff	 
	  4'h7: {regO, regR} <= src << tgt;
	  4'h8: {regR, regO} <= {src,16'h0} >> tgt;
	  
	  // 0x9: AND a, b - sets a to a&b
	  // 0xa: BOR a, b - sets a to a|b
	  // 0xb: XOR a, b - sets a to a^b
	  4'h9: {regO, regR} <= {regO, src & tgt};
	  4'hA: {regO, regR} <= {regO, src | tgt};
	  4'hB: {regO, regR} <= {regO, src ^ tgt};	  

	  default: {regO, regR} <= {regO, 16'hX};	  
	endcase // case (opc)
	 */
	
	// 0xc: IFE a, b - performs next instruction only if a==b
	// 0xd: IFN a, b - performs next instruction only if a!=b
	// 0xe: IFG a, b - performs next instruction only if a>b
	// 0xf: IFB a, b - performs next instruction only if (a&b)!=0	  	  
	  
	if (pha == 2'o0)
	  case (opc)
	    4'hC: CC <= (src_compare == tgt_compare);
	    4'hD: CC <= (src_compare != tgt_compare);
	    4'hE: CC <= (src_compare > tgt_compare);
	    4'hF: CC <= |(src_compare & tgt_compare);
	    default: CC <= 1'b1;
	  endcase // case (opc)
	
     end
   
endmodule // dcpu16_alu


module dcpu16_ctl (/*AUTOARG*/
   // Outputs
   ireg, pha, opc, rra, rwa, rwe, bra,
   // Inputs
   CC, wpc, f_dti, f_ack, clk, ena, rst
   );

   output [15:0] ireg;   
   output [1:0]  pha;

   // shared
   output [3:0]  opc;
   output [2:0]  rra,
		 rwa;
   output 	 rwe;
   output 	 bra;

   input 	 CC;   
   input 	 wpc;
   
   input [15:0]  f_dti;   
   input 	 f_ack;   
  
   // system
   input 	 clk,
		 ena,
		 rst;

   /*AUTOREG*/
   // Beginning of automatic regs (for this module's undeclared outputs)
   reg			bra;
   reg [15:0]		ireg;
   reg [3:0]		opc;
   reg [1:0]		pha;
   reg [2:0]		rra;
   reg [2:0]		rwa;
   reg			rwe;
   // End of automatics

   // repeated decoder
   wire [5:0] 		decA, decB;
   wire [3:0] 		decO;   
   assign {decB, decA, decO} = ireg;   

   wire 		nop = 16'd1; // NOP = SET A, A   
   wire 		_skp = (decO == 4'h0);

   wire 		Fbra = (ireg[4:0] == 5'h10);   
   
   // PHASE CALCULATOR
   always @(posedge clk)
     if (rst) begin
	/*AUTORESET*/
	// Beginning of autoreset for uninitialized flops
	pha <= 2'h0;
	// End of automatics
     end else if (ena) begin
	pha <= pha + 1;		
     end

   // IREG LATCH
   always @(posedge clk)
     if (rst) begin
	/*AUTORESET*/
	// Beginning of autoreset for uninitialized flops
	ireg <= 16'h0;
	opc <= 4'h0;
	// End of automatics
     end else if (ena) begin
	case (pha)
	  2'o2: ireg <= (wpc | Fbra) ? nop : f_dti; // latch instruction only on PHA2
	  default: ireg <= ireg;	  
	endcase // case (pha)

	case (pha)
	  2'o2: opc <= ireg[3:0];	  
	  default: opc <= opc;
	endcase // case (pha)
	
     end

   // BRANCH CONTROL
   reg _bra;   
   always @(posedge clk)
     if (rst) begin
	/*AUTORESET*/
	// Beginning of autoreset for uninitialized flops
	_bra <= 1'h0;
	bra <= 1'h0;
	// End of automatics
     end else if (ena) begin
	case (pha)
	  2'o0: {bra, _bra} <= {_bra & CC, (ireg[5:0] == 5'h10)};	  
	  default: {bra, _bra} <= {1'b0, _bra};	  
	endcase // case (pha)
     end
   
   // REGISTER FILE
   reg [2:0] _rwa;
   reg 	     _rwe;   
   always @(posedge clk)
     if (rst) begin
	/*AUTORESET*/
	// Beginning of autoreset for uninitialized flops
	_rwa <= 3'h0;
	_rwe <= 1'h0;
	rra <= 3'h0;
	rwa <= 3'h0;
	rwe <= 1'h0;
	// End of automatics
     end else if (ena) begin
	case (pha)
	  2'o3: rra <= decA[2:0];
	  2'o1: rra <= decA[2:0];
	  2'o2: rra <= decB[2:0];
	  2'o0: rra <= decB[2:0];	  
	  //default: rra <= 3'oX;	  
	endcase // case (pha)

	case (pha)
	  2'o0: {rwe} <= _rwe & CC & (opc[3:2] != 2'o3);	  
	  default: {rwe} <= {1'b0};	  
	endcase // case (pha)
	
	case (pha)
	  2'o1: {rwa} <= {_rwa};	  
	  default: {rwa} <= {rwa};	  
	endcase // case (pha)
	
	case (pha)
	  2'o0: begin
	     _rwa <= decA[2:0];
	     _rwe <= (decA[5:3] == 3'o0) & !_skp;	     
	  end
	  default: {_rwa, _rwe} <= {_rwa, _rwe};	  
	endcase // case (pha)
	
     end
   
endmodule // dcpu16_ctl


module dcpu16_mbus (/*AUTOARG*/
   // Outputs
   g_adr, g_stb, g_wre, f_adr, f_stb, f_wre, ena, wpc, regA, regB,
   // Inputs
   g_dti, g_ack, f_dti, f_ack, bra, CC, regR, rrd, ireg, regO, pha,
   clk, rst
   );

   // Simplified Wishbone
   output [15:0] g_adr;
   output 	 g_stb,
		 g_wre;
   input [15:0]  g_dti;
   input 	 g_ack;   

   // Simplified Wishbone
   output [15:0] f_adr;
   output 	 f_stb,
		 f_wre;
   input [15:0]  f_dti;
   input 	 f_ack;   
   
   // internal
   output 	 ena;
   output 	 wpc;   
   output [15:0] regA,
		 regB;

   input 	 bra;
   input 	 CC;   
   input [15:0]  regR;   
   input [15:0]  rrd;
   input [15:0]  ireg;   
   input [15:0]  regO;   

   input [1:0] 	 pha;   
   input 	 clk,
		 rst;

   /*AUTOREG*/
   // Beginning of automatic regs (for this module's undeclared outputs)
   reg [15:0]		f_adr;
   reg			f_stb;
   reg			f_wre;
   reg [15:0]		g_adr;
   reg			g_stb;
   reg			g_stb_for_ena;  // P03: duplicate for enable path fanout reduction
   reg			g_stb_for_fbus; // P03: duplicate for F-bus control fanout reduction
   reg [15:0]		regA;
   reg [15:0]		regB;
   reg			wpc;
   // End of automatics

   reg 			wsp;   
   reg [15:0] 		regSP,
			regPC;
   
   assign ena = (f_stb ~^ f_ack) & (g_stb_for_ena ~^ g_ack); // pipe stall (P03: use duplicate for fanout)
   
   // repeated decoder
   wire [5:0] 		decA, decB;
   wire [3:0] 		decO;   
   assign {decB, decA, decO} = ireg;   
  
   /*
    0x00-0x07: register (A, B, C, X, Y, Z, I or J, in that order)
    0x08-0x0f: [register]
`    0x10-0x17: [next word + register]
         0x18: POP / [SP++]
         0x19: PEEK / [SP]
         0x1a: PUSH / [--SP]
         0x1b: SP
         0x1c: PC
         0x1d: O
         0x1e: [next word]
         0x1f: next word (literal)
    0x20-0x3f: literal value 0x00-0x1f (literal)
    */

   // decode EA     
   wire 		Fjsr = (ireg [4:0] == 5'h10);   

   wire [5:0] 		ed = (pha[0]) ? decB : decA;   

   wire 		Eind = (ed[5:3] == 3'o1); // [R]
   wire 		Enwr = (ed[5:3] == 3'o2); // [[PC++] + R]
   wire 		Epop = (ed[5:0] == 6'h18); // [SP++]
   wire 		Epek = (ed[5:0] == 6'h19); // [SP]
   wire 		Epsh = (ed[5:0] == 6'h1A); // [--SP]
   wire 		Ersp = (ed[5:0] == 6'h1B); // SP
   wire 		Erpc = (ed[5:0] == 6'h1C); // PC
   wire 		Erro = (ed[5:0] == 6'h1D); // O
   wire 		Enwi = (ed[5:0] == 6'h1E); // [PC++]
   wire 		Esht = ed[5]; // xXX

   wire [5:0] 		fg = (pha[0]) ? decA : decB;   

   wire 		Fdir = (fg[5:3] == 3'o0); // R
   wire 		Find = (fg[5:3] == 3'o1); // [R]
   wire 		Fnwr = (fg[5:3] == 3'o2); // [[PC++] + R]
   wire 		Fspi = (fg[5:0] == 6'h18); // [SP++]
   wire 		Fspr = (fg[5:0] == 6'h19); // [SP]
   wire 		Fspd = (fg[5:0] == 6'h1A); // [--SP]  
   wire 		Frsp = (fg[5:0] == 6'h1B); // SP
   wire 		Frpc = (fg[5:0] == 6'h1C); // PC
   wire 		Fnwi = (fg[5:0] == 6'h1E); // [PC++]
   wire 		Fnwl = (fg[5:0] == 6'h1F); // PC++   
   
   // PROGRAMME COUNTER - loadable binary up counter
   reg [15:0] 		rpc;
   reg 			lpc;

   // P02: rpc mux optimization - pre-compute priority selects
   wire 		rpc_sel_wpc = wpc;
   wire 		rpc_sel_bra = ~wpc & bra;
   wire 		rpc_sel_default = ~wpc & ~bra;

   always @(posedge clk)
     if (rst) begin
	/*AUTORESET*/
	// Beginning of autoreset for uninitialized flops
	regPC <= 16'h0;
	wpc <= 1'h0;
	// End of automatics
     end else if (ena) begin
	if (lpc)
	  regPC <= rpc;
	else
	  regPC <= regPC + 1;

       	case (pha)
	  2'o1: wpc <= Frpc & CC;
	  default: wpc <= wpc;	  
	endcase // case (pha)
     end // if (ena)

   always @(/*AUTOSENSE*/Fnwi or Fnwl or Fnwr or bra or pha or regB
	    or regPC or regR or wpc) begin      
      case (pha)
	2'o1: rpc <= ({16{rpc_sel_wpc}} & regR) |
	           ({16{rpc_sel_bra}} & regB) |
	           ({16{rpc_sel_default}} & regPC);
	default: rpc <= regPC;
      endcase // case (pha)
      case (pha)
	2'o3: lpc <= ~(Fnwr | Fnwi | Fnwl);
	2'o0: lpc <= ~(Fnwr | Fnwi | Fnwl);
	2'o1: lpc <= 1'b1;	
	default: lpc <= 1'b0;	
      endcase // case (pha)
   end // always @ (...
   
   // STACK POINTER - loadable binary up/down counter
   reg [15:0] _rSP;
   reg 	      lsp;
   reg [15:0] rsp;

   // P02: regSP update optimization - pre-compute all 4 candidates
   wire [15:0] sp_val_inc = regSP + 1;
   wire [15:0] sp_val_dec = regSP - 1;
   wire [1:0] sp_sel;
   wire sp_sel_load = lsp & wsp;
   wire sp_sel_dec = lsp ? 1'b0 : (fg[1] | Fjsr);
   assign sp_sel = {sp_sel_dec, sp_sel_load};

   always @(posedge clk)
     if (rst) begin
	regSP <= 16'hFFFF;
	/*AUTORESET*/
	// Beginning of autoreset for uninitialized flops
	_rSP <= 16'h0;
	wsp <= 1'h0;
	// End of automatics
     end else if (ena) begin
	_rSP <= regSP; // backup SP

	// P02: Single 4-to-1 mux for SP update
	case (sp_sel)
	  2'b00: regSP <= sp_val_inc;
	  2'b01: regSP <= rsp;		// load from rsp (which holds wsp ? regR : regSP)
	  2'b10: regSP <= sp_val_dec;
	  2'b11: regSP <= sp_val_dec;	// Default: decrement
	endcase

	case (pha) // write to SP
	  2'o1: wsp <= Frsp & CC;	  
	  default: wsp <= wsp;	  
	endcase // case (pha)
     end // if (ena)

   always @(/*AUTOSENSE*/Fjsr or Fspd or Fspi or pha or regR or regSP
	    or wsp) begin
      case (pha)
	2'o3: lsp <= ~(Fspi | Fspd | Fjsr);	
	2'o0: lsp <= ~(Fspi | Fspd);
	default: lsp <= 1'b1;	
      endcase // case (pha)
      
      case (pha)
	2'o1: rsp <= (wsp) ? regR :
		     regSP;	
	default: rsp <= regSP;	
      endcase // case (pha)
   end // always @ (...

   // EA CALCULATOR
   wire [15:0] 		nwr = rrd + g_dti;   
   reg [15:0] 		ea, 
			eb;
   reg [15:0] 		ec; // Calculated EA
 
   always @(posedge clk)
     if (rst) begin
	/*AUTORESET*/
	// Beginning of autoreset for uninitialized flops
	ea <= 16'h0;
	eb <= 16'h0;
	// End of automatics
     end else if (ena) begin
	case (pha)
	  2'o0: ea <= (Fjsr) ? regSP : ec;	  
	  default: ea <= ea;	  
	endcase // case (pha)

	case (pha)
	  2'o1: eb <= ec;	  
	  default: eb <= eb;	  
	endcase // case (pha)
     end // if (ena)
  
   // P02: ec mux optimization - convert 6-way cascaded to one-hot parallel
   // Pre-compute one-hot select signals for ec mux
   wire 		ec_sel_Eind = Eind;
   wire 		ec_sel_Enwr = ~Eind & Enwr;
   wire 		ec_sel_Epsh = ~Eind & ~Enwr & Epsh;
   wire 		ec_sel_Epop = ~Eind & ~Enwr & ~Epsh & (Epop | Epek);
   wire 		ec_sel_Enwi = ~Eind & ~Enwr & ~Epsh & ~(Epop | Epek) & Enwi;

   always @(/*AUTOSENSE*/Eind or Enwi or Enwr or Epek or Epop or Epsh
	    or _rSP or g_dti or nwr or regSP or rrd) begin
      ec <= ({16{ec_sel_Eind}} & rrd) |
	    ({16{ec_sel_Enwr}} & nwr) |
	    ({16{ec_sel_Epsh}} & regSP) |
	    ({16{ec_sel_Epop}} & _rSP) |
	    ({16{ec_sel_Enwi}} & g_dti);
   end
   
   // G-BUS
   assign g_wre = 1'b0;

   always @(posedge clk)
     if (rst) begin
	/*AUTORESET*/
	// Beginning of autoreset for uninitialized flops
	g_adr <= 16'h0;
	g_stb <= 1'h0;
	g_stb_for_ena <= 1'h0;  // P03: initialize duplicate
	g_stb_for_fbus <= 1'h0; // P03: initialize F-bus duplicate
	// End of automatics
     end else if (ena) begin
	case (pha)
	  2'o1: g_adr <= ea;
	  2'o2: g_adr <= eb;
	  default: g_adr <= regPC;
	endcase // case (pha)

	case (pha)
	  2'o3: begin
	    g_stb <= Fnwr | Fnwi | Fnwl;
	    g_stb_for_ena <= Fnwr | Fnwi | Fnwl;  // P03: keep duplicate synchronized
	    g_stb_for_fbus <= Fnwr | Fnwi | Fnwl; // P03: keep F-bus duplicate synchronized
	  end
	  2'o0: begin
	    g_stb <= Fnwr | Fnwi | Fnwl;
	    g_stb_for_ena <= Fnwr | Fnwi | Fnwl;  // P03: keep duplicate synchronized
	    g_stb_for_fbus <= Fnwr | Fnwi | Fnwl; // P03: keep F-bus duplicate synchronized
	  end
	  2'o1: begin
	    g_stb <= Find | Fnwr | Fspr | Fspi | Fspd | Fnwi;
	    g_stb_for_ena <= Find | Fnwr | Fspr | Fspi | Fspd | Fnwi;  // P03: keep duplicate synchronized
	    g_stb_for_fbus <= Find | Fnwr | Fspr | Fspi | Fspd | Fnwi; // P03: keep F-bus duplicate synchronized
	  end
	  2'o2: begin
	    g_stb <= Find | Fnwr | Fspr | Fspi | Fspd | Fnwi;
	    g_stb_for_ena <= Find | Fnwr | Fspr | Fspi | Fspd | Fnwi;  // P03: keep duplicate synchronized
	    g_stb_for_fbus <= Find | Fnwr | Fspr | Fspi | Fspd | Fnwi; // P03: keep F-bus duplicate synchronized
	  end
	endcase // case (pha)
     end // if (ena)
   

   // F-BUS
   reg [15:0] _adr;
   reg 	      _stb, _wre;   
   always @(posedge clk)
     if (rst) begin
	/*AUTORESET*/
	// Beginning of autoreset for uninitialized flops
	_adr <= 16'h0;
	_stb <= 1'h0;
	_wre <= 1'h0;
	// End of automatics
     end else if (ena) begin
	case (pha)
	  2'o2: begin
	     _adr <= g_adr;
	     _stb <= g_stb | Fjsr;
	  end
	  default:begin
	     _adr <= _adr;
	     _stb <= _stb;	     
	  end
	endcase // case (pha)

	case (pha)
	  2'o1: _wre <= Find | Fnwr | Fspr | Fspi | Fspd | Fnwi | Fjsr;	     
	  default: _wre <= _wre;	  
	endcase // case (pha)
	
     end // if (ena)

   always @(posedge clk)
     if (rst) begin
	/*AUTORESET*/
	// Beginning of autoreset for uninitialized flops
	f_adr <= 16'h0;
	f_stb <= 1'h0;
	f_wre <= 1'h0;
	// End of automatics
     end else if (ena) begin

	case (pha)
	  2'o1: f_adr <= ({16{f_rpc_sel_wpc}} & regR) |
		        ({16{f_rpc_sel_bra}} & regB) |
		        ({16{f_rpc_sel_default}} & regPC);
	  2'o0: f_adr <= _adr;
	  default: f_adr <= 16'hX;
	endcase // case (pha)

	case (pha)
	  2'o1: {f_stb,f_wre} <= (Fjsr) ? 2'o0 : 2'o2;
	  2'o0: {f_stb,f_wre} <= {_stb, _wre & CC};
	  default: {f_stb,f_wre} <= 2'o0;
	endcase // case (pha)

     end // if (ena)
   
   // REG-A/REG-B
   reg 			_rd;
   reg [15:0] 		opr;

   // P02: Pre-compute select signals for register load muxes
   wire 		regA_sel_g_stb = g_stb;
   wire 		regA_sel_Fjsr = ~g_stb & Fjsr;
   wire 		regA_sel_rd = ~g_stb & ~Fjsr & _rd;

   wire 		regB_sel_g_stb = g_stb;
   wire 		regB_sel_rd = ~g_stb & _rd;

   wire 		opr_sel_g_stb = g_stb;
   wire 		opr_sel_Ersp = ~g_stb & Ersp;
   wire 		opr_sel_Erpc = ~g_stb & ~Ersp & Erpc;
   wire 		opr_sel_Erro = ~g_stb & ~Ersp & ~Erpc & Erro;
   wire 		opr_sel_Esht = ~g_stb & ~Ersp & ~Erpc & ~Erro & Esht;

   // P03: Pre-compute select signals for F-bus control using duplicated signal
   wire 		f_rpc_sel_wpc = wpc;
   wire 		f_rpc_sel_bra = ~wpc & bra;
   wire 		f_rpc_sel_default = ~wpc & ~bra;

   always @(posedge clk)
     if (rst) begin
	/*AUTORESET*/
	// Beginning of autoreset for uninitialized flops
	_rd <= 1'h0;
	// End of automatics
     end else if (ena)
       	case (pha)
	  2'o1: _rd <= Fdir;
	  2'o2: _rd <= Fdir;	  
	  default: _rd <= 1'b0;	  
	endcase // case (pha)

   always @(posedge clk)
     if (rst) begin
	/*AUTORESET*/
	// Beginning of autoreset for uninitialized flops
	regA <= 16'h0;
	regB <= 16'h0;
	// End of automatics
     end else if (ena) begin
	case (pha)
	  2'o0: regA <= opr;
	  2'o2: regA <= ({16{regA_sel_g_stb}} & g_dti) |
		        ({16{regA_sel_Fjsr}} & regPC) |
		        ({16{regA_sel_rd}} & rrd) |
		        ({16{~(regA_sel_g_stb | regA_sel_Fjsr | regA_sel_rd)}} & regA);
	  default: regA <= regA;
	endcase // case (pha)
	
	case (pha)
	  2'o1: regB <= opr;
	  2'o3: regB <= ({16{regB_sel_g_stb}} & g_dti) |
		        ({16{regB_sel_rd}} & rrd) |
		        ({16{~(regB_sel_g_stb | regB_sel_rd)}} & regB);
	  default: regB <= regB;
	endcase // case (pha)
     end // if (ena)

   always @(/*AUTOSENSE*/Erpc or Erro or Ersp or Esht or ed or g_dti
	    or g_stb or regO or regPC or regSP) begin
      // P02: opr mux optimization - parallel one-hot selection
      opr <= ({16{opr_sel_g_stb}} & g_dti) |
	     ({16{opr_sel_Ersp}} & regSP) |
	     ({16{opr_sel_Erpc}} & regPC) |
	     ({16{opr_sel_Erro}} & regO) |
	     ({16{opr_sel_Esht}} & {11'd0,ed[4:0]});
   end
   
endmodule // dcpu16_mbus


module dcpu16_regs (/*AUTOARG*/
   // Outputs
   rrd,
   // Inputs
   rwd, rra, rwa, rwe, rst, ena, clk
   );

   output [15:0] rrd; // read data
   input [15:0]  rwd; // write data
   input [2:0] 	 rra, // read address
		 rwa; // write address   
   input 	 rwe; // write-enable
   
   input 	 rst,
		 ena,
		 clk;      
   
   reg [15:0] 	 file [0:7]; // A, B, C, X, Y, Z, I, J

   reg [2:0] 	 r;

   assign rrd = file[rra];   
   
   always @(posedge clk)
     if (ena) begin
	r <= rra;	
	
	if (rwe) begin
	   file[rwa] <= rwd;	
	end
     end
        
endmodule // dcpu16_regs