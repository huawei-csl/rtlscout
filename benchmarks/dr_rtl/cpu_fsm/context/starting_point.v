`timescale 1ns/1ps

module mini_cpu(

	input  wire		   clk,
	input  wire		   rst,
	input  wire		   en,
					   
	input wire 		   imem_we,
	input wire  [7:0]  imem_addr,
	input wire  [15:0] imem_wdata,
					   
	input wire 		   rf_we,
	input wire  [1:0]  rf_addr,
	input wire  [7:0]  rf_wdata,
					   
	output reg  [7:0]  PC,
	output wire	 	   halt,
	output wire [7:0]  dbg_r0,
	output wire [7:0]  dbg_r1,
	output wire [7:0]  dbg_r2,
	output wire [7:0]  dbg_r3,
	output wire [2:0]  dbg_state
	);


// Registers
reg [15:0] IR;
reg [7:0] regis [0:3];

// Instruction Memory
reg [15:0] imem [0:255];
reg [7:0] rs_data	   ;
reg [7:0] rd_data	   ;

  
// DECODE
wire [3:0] opcode;
wire [1:0] rd	 ;
wire [1:0] rs	 ;
wire [7:0] imm8  ;

assign opcode 	 = IR[15:12];
assign rd	   	 = IR[11:10];
assign rs     	 = IR[9:8]	;
assign imm8   	 = IR[7:0]	;

  
// FSM Parameters
localparam FETCH  = 0;
localparam DECODE = 1;
localparam EXEC   = 2;
localparam WB 	  = 3;
localparam HALT   = 4;

reg [2:0] state, nst ;

  
// Memory Assignments
assign dbg_r0 = regis[0];
assign dbg_r1 = regis[1];
assign dbg_r2 = regis[2];
assign dbg_r3 = regis[3];

assign dbg_state = state;

  
// Control Unit
reg  reg_write  	   ;
reg  [2:0] alu_op      ;
reg  alu_src_imm	   ;
reg  [7:0] ALU_OUT     ;
wire [7:0] alu_inA 	   ;
wire [7:0] alu_inB 	   ;
reg  [7:0] alu_result  ;
reg  zero_flag		   ;
reg  zero_en		   ;
reg  branch_en		   ;


// Opcodes
localparam [3:0] OP_BEQ  = 4'H8;
localparam [3:0] OP_BNE  = 4'H9;
localparam [3:0] OP_ADD  = 4'hA;
localparam [3:0] OP_ADDI = 4'hB;
localparam [3:0] OP_SUB  = 4'hC;
localparam [3:0] OP_CMP  = 4'HD;
localparam [3:0] OP_JMP  = 4'HE;
localparam [3:0] OP_HALT = 4'hF;


//ALU Operation codes
localparam [2:0] ALU_ADD = 3'b001;
localparam [2:0] ALU_SUB = 3'b010;


// Sync Main Logic
always @(posedge clk)
begin
    if (rst)
		begin
			PC        <= 8'd0;
			state     <= FETCH;
			IR        <= 16'h0000;
	
			regis[0]  <= 8'h11;
			regis[1]  <= 8'h22;
			regis[2]  <= 8'h33;
			regis[3]  <= 8'h44;
	
			zero_flag <= 1'b0;
			ALU_OUT   <= 8'h00;
		end
	
	else if (!en)
		begin
			// Load mode(init):
			if (rf_we)
        begin
				  regis[rf_addr] <= rf_wdata;
        end
			state <= state;
		end
	
    else
		begin
			
			state <= nst;
	
			case (state)
	
				FETCH:
					begin
						IR <= imem[PC];
						PC <= PC + 1;
					end
	
				EXEC:
					begin
						ALU_OUT <= alu_result;
		
						if (zero_en)
							zero_flag <= (alu_result == 8'h00);
		
						if (opcode == OP_BEQ && alu_result == 8'h00)
							PC <= PC + $signed(imm8);
		
						else if (opcode == OP_BNE && alu_result != 8'h00)
							PC <= PC + $signed(imm8);
		
						else if (opcode == OP_JMP)
							PC <= PC + $signed(imm8);
					end
	
				WB:
					begin
						if (reg_write)
							regis[rd] <= ALU_OUT;
					end
	
				HALT:
					begin
						// stay here forever, no actions
					end
	
				default:
					begin
						// do nothing
					end
	
			endcase
		end
end



// Instruction memory init
always @(posedge clk)
begin
	if (!en && imem_we)
		imem[imem_addr] <= imem_wdata;
end

assign halt = (state == HALT);

//MUX block for regis and rs_data
always @(*)
begin
rs_data = 8'h00;
	if (rs == 2'b00)
		rs_data = regis[0];
	else if (rs == 2'b01)
		rs_data = regis[1];
	else if (rs == 2'b10)
		rs_data = regis[2];
	else
		rs_data = regis[3];
end

//MUX block for regis and rd_data
always @(*)
begin

	rd_data = 8'h00;
	
	if (rd == 2'b00)
		rd_data = regis[0];
	else if (rd == 2'b01)
		rd_data = regis[1];
	else if (rd == 2'b10)
		rd_data = regis[2];
	else
		rd_data = regis[3];
end


//MUX for source of the ADD params
assign alu_inB = (alu_src_imm ? imm8 : rs_data);

// rd_data assignment to alu_inA
assign alu_inA = rd_data;


// ALU Operation Logic
always @(*)
begin
	reg_write 	= 1'b0	;
	alu_src_imm = 1'b0	;
	alu_op		= 3'b000;
	alu_result  = 8'h00 ;
	zero_en     = 1'b0  ;
	branch_en   = 1'b0  ;
	
	case(opcode)
	
		OP_ADD: 
      begin
			  reg_write   = 1'b1   ;
			  alu_src_imm = 1'b0   ;
			  alu_op      = ALU_ADD;
			  zero_en     = 1'b1   ;
			end
		
		OP_HALT:
      begin
			  reg_write 	= 1'b0;		
			end
			
		OP_ADDI :
      begin
			  reg_write 	= 1'b1	 ;
			  alu_src_imm = 1'b1	 ;
			  alu_op      = ALU_ADD;
			  zero_en     = 1'b1	 ;
			end
			
		OP_SUB :
      begin
			  reg_write 	= 1'b1	 ;
			  alu_src_imm = 1'b0	 ;
			  alu_op      = ALU_SUB;
			  zero_en     = 1'b1	 ;
			end
			
		OP_CMP:
      begin
			  reg_write 	= 1'b0	 ;
			  alu_src_imm = 1'b0	 ;
			  alu_op      = ALU_SUB;
			  zero_en     = 1'b1	 ;
			end
			
		OP_BEQ :
      begin
			  reg_write = 1'b0;
			  alu_src_imm = 1'b0	 ;
			  alu_op      = ALU_SUB;
			  branch_en     = 1'b1 ;
			  zero_en     = 1'b0	 ;
			end
			
		OP_BNE :
      begin
			  reg_write 	= 1'b0	 ;
			  alu_src_imm = 1'b0	 ;
			  alu_op      = ALU_SUB;
			  branch_en   = 1'b1 	 ;
			  zero_en     = 1'b0	 ;
			end
			
		OP_JMP :
      begin
			  reg_write   = 1'b0;
			  zero_en     = 1'b0;
			end
			
		default : 
      begin
			  // Do nothing
      end
	endcase
		
	case(alu_op)
		
		ALU_ADD : 
      begin
			  alu_result = alu_inA + alu_inB;
			end
			
		ALU_SUB :
      begin
			  alu_result = alu_inA - alu_inB;
			end
			
		default : 
      begin
			  // Do nothing.
      end
	endcase
end




always @(*)
begin

	nst = state;
	case (state)
	
		FETCH:
			nst = DECODE;
		DECODE :
      begin
			  if (opcode == OP_HALT)
				  nst = HALT;
			  else
				  nst = EXEC;
			end
		EXEC:
			nst = WB;
		WB:
			nst = FETCH;
		HALT:
			nst = HALT;
	
		default:
      begin
        nst = FETCH;
      end	
  endcase
end
		
endmodule