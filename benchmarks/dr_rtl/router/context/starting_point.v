module router_top(input clk, resetn, packet_valid, read_enb_0, read_enb_1, read_enb_2,
				  input [7:0]datain, 
				  output vldout_0, vldout_1, vldout_2, err, busy,
				  output [7:0]data_out_0, data_out_1, data_out_2);

wire [2:0]w_enb;
wire [2:0]soft_reset;
wire [2:0]read_enb; 
wire [2:0]empty;
wire [2:0]full;
wire lfd_state_w;
wire [7:0]data_out_temp[2:0];
wire [7:0]dout;

	genvar a;

generate 
for(a=0;a<3;a=a+1)

begin:fifo
	router_fifo f(.clk(clk), .resetn(resetn), .soft_reset(soft_reset[a]),
	.lfd_state(lfd_state_w), .write_enb(w_enb[a]), .datain(dout), .read_enb(read_enb[a]), 
	.full(full[a]), .empty(empty[a]), .dataout(data_out_temp[a]));
end
endgenerate			  

router_reg r1(.clk(clk), .resetn(resetn), .packet_valid(packet_valid), .datain(datain), 
			  .dout(dout), .fifo_full(fifo_full), .detect_add(detect_add), 
			  .ld_state(ld_state),  .laf_state(laf_state), .full_state(full_state), 
			  .lfd_state(lfd_state_w), .rst_int_reg(rst_int_reg),  .err(err), .parity_done(parity_done), .low_packet_valid(low_packet_valid));

router_fsm fsm(.clk(clk), .resetn(resetn), .packet_valid(packet_valid), 
			   .datain(datain[1:0]), .soft_reset_0(soft_reset[0]), .soft_reset_1(soft_reset[1]), .soft_reset_2(soft_reset[2]), 
			   .fifo_full(fifo_full), .fifo_empty_0(empty[0]), .fifo_empty_1(empty[1]), .fifo_empty_2(empty[2]),
			   .parity_done(parity_done), .low_packet_valid(low_packet_valid), .busy(busy), .rst_int_reg(rst_int_reg), 
			   .full_state(full_state), .lfd_state(lfd_state_w), .laf_state(laf_state), .ld_state(ld_state), 
			   .detect_add(detect_add), .write_enb_reg(write_enb_reg));

router_sync s(.clk(clk), .resetn(resetn), .datain(datain[1:0]), .detect_add(detect_add), 
              .full_0(full[0]), .full_1(full[1]), .full_2(full[2]), .read_enb_0(read_enb[0]), 
			  .read_enb_1(read_enb[1]), .read_enb_2(read_enb[2]), .write_enb_reg(write_enb_reg), 
			  .empty_0(empty[0]), .empty_1(empty[1]), .empty_2(empty[2]), .vld_out_0(vldout_0), .vld_out_1(vldout_1), .vld_out_2(vldout_2), 
			  .soft_reset_0(soft_reset[0]), .soft_reset_1(soft_reset[1]), .soft_reset_2(soft_reset[2]), .write_enb(w_enb), .fifo_full(fifo_full));
			  
assign read_enb[0]= read_enb_0;
assign read_enb[1]= read_enb_1;
assign read_enb[2]= read_enb_2;
assign  data_out_0=data_out_temp[0];
assign data_out_1=data_out_temp[1];
assign data_out_2=data_out_temp[2];

endmodule


module router_sync( input clk,resetn,detect_add,write_enb_reg,read_enb_0,read_enb_1,read_enb_2,empty_0,empty_1,empty_2,full_0,full_1,full_2, 
					input [1:0]datain,
					output wire vld_out_0,vld_out_1,vld_out_2,
					output reg [2:0]write_enb, 
					output reg fifo_full, soft_reset_0,soft_reset_1,soft_reset_2);
					
reg [1:0]temp;
reg [4:0]count0,count1,count2;

// One-hot pre-decode wires for temp address selector to reduce fanout on critical paths
wire temp_is_0, temp_is_1, temp_is_2;
assign temp_is_0 = (temp == 2'b00);
assign temp_is_1 = (temp == 2'b01);
assign temp_is_2 = (temp == 2'b10);

//------------------------------------------------------------------------------------------------------------------------------------------------
always@(posedge clk)
	begin
		if(!resetn)
			temp <= 2'd0;
		else if(detect_add)
			temp<=datain;
	end

//----------------------------------------------------------------------------------------------------------------------------------------------
//for fifo full - using one-hot pre-decoded signals to reduce fanout
always@(*)
	begin
		if(temp_is_0)
			fifo_full=full_0;
		else if(temp_is_1)
			fifo_full=full_1;
		else
			fifo_full=full_2;
	end
//------------------------------------------------------------------------------------------------------------------------------------------------
//write enable - using one-hot pre-decoded signals to reduce fanout
always@(*)
	begin
				if(write_enb_reg)
				begin
					if(temp_is_0)
						write_enb=3'b001;
					else if(temp_is_1)
						write_enb=3'b010;
					else if(temp_is_2)
						write_enb=3'b100;
					else
						write_enb=3'b000;
				end
				else
					write_enb = 3'b000;
	end
//------------------------------------------------------------------------------------------------------------------------------------------------

//valid out
assign vld_out_0 = !empty_0;
assign vld_out_1 = !empty_1;
assign vld_out_2 = !empty_2;
//--------------------------------------------------------------------------------------------------------------------------------------------------
//soft reset counter 
always@(posedge clk)
	begin
		if(!resetn)
			count0<=5'b0;
		else if(vld_out_0)
			begin
				if(!read_enb_0)
					begin
						if(count0==5'b11110)	
							begin
								soft_reset_0<=1'b1;
								count0<=1'b0;
							end
						else
							begin
								count0<=count0+1'b1;
								soft_reset_0<=1'b0;
							end
					end
				else count0<=5'd0;
			end
		else count0<=5'd0;
	end
	
always@(posedge clk)
	begin
		if(!resetn)
			count1<=5'b0;
		else if(vld_out_1)
			begin
				if(!read_enb_1)
					begin
						if(count1==5'b11110)	
							begin
								soft_reset_1<=1'b1;
								count1<=1'b0;
							end
						else
							begin
								count1<=count1+1'b1;
								soft_reset_1<=1'b0;
							end
					end
				else count1<=5'd0;
			end
		else count1<=5'd0;
	end
	
always@(posedge clk)
	begin
		if(!resetn)
			count2<=5'b0;
		else if(vld_out_2)
			begin
				if(!read_enb_2)
					begin
						if(count2==5'b11110)	
							begin
								soft_reset_2<=1'b1;
								count2<=1'b0;
							end
						else
							begin
								count2<=count2+1'b1;
								soft_reset_2<=1'b0;
							end
					end
				else count2<=5'd0;
			end
		else count2<=5'd0;
	end
	
	
endmodule


module router_fsm(input clk,resetn,packet_valid,
				  input [1:0] datain,
				  input fifo_full,fifo_empty_0,fifo_empty_1,fifo_empty_2,soft_reset_0,soft_reset_1,soft_reset_2,parity_done, low_packet_valid, 
				  output write_enb_reg,detect_add,ld_state,laf_state,lfd_state,full_state,rst_int_reg,busy);
				  
 parameter  decode_address		=	4'b0001,
			wait_till_empty		=	4'b0010,
			load_first_data		=	4'b0011,
			load_data			=	4'b0100,
			load_parity			=	4'b0101,
			fifo_full_state		=	4'b0110,
			load_after_full		=	4'b0111,
			check_parity_error	=	4'b1000;
			
reg [3:0] present_state, next_state;
reg [1:0] temp;
//-------------------------------------------------------------------------------------------------------------------------------------------
//temp logic
always@(posedge clk)
	begin
		if(~resetn)
			temp<=2'b0;
		else if(detect_add)          // decides the address of out channel
		 	temp<=datain;
	end
//--------------------------------------------------------------------------------------------------------------------------------------------
// reset logic for states
always@(posedge clk)
	begin
		if(!resetn)
				present_state<=decode_address;  // hard reset
		else if (((soft_reset_0) && (temp==2'b00)) || ((soft_reset_1) && (temp==2'b01)) || ((soft_reset_2) && (temp==2'b10)))		//if there is soft_reset and also using same channel so we do here and opertion
				present_state<=decode_address;
		else
				present_state<=next_state;
	end
//-------------------------------------------------------------------------------------------------------------------------------------------	
//state machine logic 

always@(*)
	begin
		case(present_state)
		decode_address:   // decode address state 
		begin
			if((packet_valid && (datain==2'b00) && fifo_empty_0)|| (packet_valid && (datain==2'b01) && fifo_empty_1)|| (packet_valid && (datain==2'b10) && fifo_empty_2))

					next_state<=load_first_data;   //lfd_state

			else if((packet_valid && (datain==2'b00) && !fifo_empty_0)||(packet_valid && (datain==2'b01) && !fifo_empty_1)||(packet_valid && (datain==2'b10) && !fifo_empty_2))
					next_state<=wait_till_empty;  //wait till empty state
				
			else 
				next_state<=decode_address;	   // same state
		end
//------------------------------------------------------------------------------------------------------------------------------------------
		load_first_data: 			// load first data state
		begin	
			next_state<=load_data;
		end
//-----------------------------------------------------------------------------------------------------------------------------------------
		wait_till_empty:          //wait till empty state
		begin
			if((fifo_empty_0 && (temp==2'b00))||(fifo_empty_1 && (temp==2'b01))||(fifo_empty_2 && (temp==2'b10))) //fifo is empty and were using same fifo
					next_state<=load_first_data;
	
				else
					next_state<=wait_till_empty;
			end
//-----------------------------------------------------------------------------------------------------------------------------------------
		load_data:                        //load data
		begin
			if(fifo_full==1'b1) 
					next_state<=fifo_full_state;
			else 
					begin
						if (!fifo_full && !packet_valid)
							next_state<=load_parity;
						else
							next_state<=load_data;
					end
		end
//--------------------------------------------------------------------------------------------------------------------------------------------
			fifo_full_state:			//fifo full state
			begin
				if(fifo_full==0)
					next_state<=load_after_full;
				else 
					next_state<=fifo_full_state;
			end
//-------------------------------------------------------------------------------------------------------------------------------------------
			load_after_full:         	// load after full state
			begin
				if(!parity_done && low_packet_valid)
					next_state<=load_parity;
				else if(!parity_done && !low_packet_valid)
					next_state<=load_data;
	
				else 
					begin 
						if(parity_done==1'b1)
							next_state<=decode_address;
						else
							next_state<=load_after_full;
					end
				
			end
//-------------------------------------------------------------------------------------------------------------------------------------------
			load_parity:                 // load parity state
			begin
				next_state<=check_parity_error;
			end
//-------------------------------------------------------------------------------------------------------------------------------------------
			check_parity_error:			// check parity error
			begin
				if(!fifo_full)
					next_state<=decode_address;
				else
					next_state<=fifo_full_state;
			end
//--------------------------------------------------------------------------------------------------------------------------------------------
			default:					//default state
				next_state<=decode_address; 

		endcase																					// state machine completed
	end
//----------------------------------------------------------------------------------------------------------------------------------------
// output logic


assign busy=((present_state==load_first_data)||(present_state==load_parity)||(present_state==fifo_full_state)||(present_state==load_after_full)||(present_state==wait_till_empty)||(present_state==check_parity_error))?1:0;
assign detect_add=((present_state==decode_address))?1:0;
assign lfd_state=((present_state==load_first_data))?1:0;
assign ld_state=((present_state==load_data))?1:0;
assign write_enb_reg=((present_state==load_data)||(present_state==load_after_full)||(present_state==load_parity))?1:0;
assign full_state=((present_state==fifo_full_state))?1:0;
assign laf_state=((present_state==load_after_full))?1:0;
assign rst_int_reg=((present_state==check_parity_error))?1:0;

endmodule

module router_fifo(clk,resetn,soft_reset,write_enb,read_enb,lfd_state,datain,full,empty,dataout);
//INPUT,OUTPUT
input clk,resetn,soft_reset,write_enb,read_enb,lfd_state;
input [7:0]datain;
output reg full,empty;
output reg [7:0]dataout;
//internal Data types
reg [3:0]read_ptr,write_ptr;
reg [5:0]count;
reg [8:0]fifo[15:0];//9 BIT DATA WIDTH 1 BIT EXTRA FOR HEADER AND 16 DEPTH SIZE
integer i;
reg temp;
reg [4:0] incrementer;

//------------------------------------------------------------------------------
//lfd_state
always@(posedge clk)
	begin
		if(!resetn)
			temp<=1'b0;
		else 
			temp<=lfd_state;
	end 


//-------------------------------------------------------------------------------------------------------------------
//Incrementer - optimized with registered full/empty flags to break self-loop path

// Combinational computation of next incrementer value
wire [4:0] next_incrementer;
assign next_incrementer = ((!full && write_enb) && (!empty && read_enb)) ? incrementer :
                          (!full && write_enb) ? (incrementer + 1) :
                          (!empty && read_enb) ? (incrementer - 1) :
                          incrementer;

always @(posedge clk )
begin
   if( !resetn )
       incrementer <= 0;
   else
       incrementer <= next_incrementer;
end

//full and empty logic - registered to break self-loop timing
reg full_d, empty_d;

always @(incrementer)
begin
  if(incrementer==0)
    empty_d = 1;
  else
    empty_d = 0;

  if(incrementer==4'b1111)
    full_d = 1;
  else
    full_d = 0;
end

// Register the full and empty signals to break combinational self-loop
always @(posedge clk)
begin
  if(!resetn)
  begin
    full <= 0;
    empty <= 1;
  end
  else
  begin
    full <= full_d;
    empty <= empty_d;
  end
end 
//-----------------------------------------------------------------------------------------------------

//------------------------------------------------------------------------------------------------------------------------
//Fifo write logic
always@(posedge clk)
	begin
		if(!resetn || soft_reset)
			begin
				for(i=0;i<16;i=i+1)
					fifo[i]<=0; 
			end
		
		else if(write_enb && !full)
				{fifo[write_ptr[3:0]][8],fifo[write_ptr[3:0]][7:0]}<={temp,datain}; //temp=1 for header data and 0 for other data
	
	end

//
//----------------------------------------------------------------------------------------------------------------------------------------
//FIFO READ logic
always@(posedge clk)
	begin
		if(!resetn)
			dataout<=8'd0;

		else if(soft_reset)
			dataout<=8'd0; // patched from 8'bzz
		
		else
			begin 
				if(read_enb && !empty)
					dataout<=fifo[read_ptr[3:0]];
				if(count==0) // COMPLETELY READ
					dataout<=8'd0; // patched from 8'bz
			end
	end
//------------------------------------------------------------------------------------------------------------------------------------
//counter logic
always@(posedge clk)
	begin
		
		 if(read_enb && !empty)
			begin
				if(fifo[read_ptr[3:0]][8])                          //a header byte is read, an internal counter is loaded with the payload
                                                               //length of the packet plus(parity byte) and starts decrementing every clock till it reached 
					count<=fifo[read_ptr[3:0]][7:2]+1'b1;

				else if(count!=6'd0)
					count<=count-1'b1;
				
			end
	
	end
//---------------------------------------------------------------------------------------------------------------
//pointer logic
always@(posedge clk)
	begin
		if(!resetn || soft_reset)
			begin
				read_ptr=5'd0;
				write_ptr=5'd0;
			end

		else 
			begin
				if(write_enb && !full)
					write_ptr=write_ptr+1'b1;

				if(read_enb && !empty)
					read_ptr=read_ptr+1'b1;
			end
	end

endmodule


module router_reg(input clk,resetn,packet_valid,
				  input [7:0] datain,
				  input fifo_full,detect_add,ld_state,laf_state,full_state,lfd_state,rst_int_reg,
				  output reg err,parity_done,low_packet_valid,
				  output reg [7:0] dout);
				  
reg [7:0] hold_header_byte,fifo_full_state_byte,internal_parity,packet_parity_byte;
//--------------------------------------------------------------------------------------------------------------
//parity done
always@(posedge clk)
	begin
		if(!resetn)
			begin
				parity_done<=1'b0;
			end
	
		else 
			begin
				if(ld_state && !fifo_full && !packet_valid)
						parity_done<=1'b1;
				else if(laf_state && low_packet_valid && !parity_done)
						parity_done<=1'b1;
				else
					begin
						if(detect_add)
							parity_done<=1'b0;
					end
			end
	end
//--------------------------------------------------------------------------------------------------------------------
//low_packet valid
always@(posedge clk)
	begin
		if(!resetn)
			low_packet_valid<=1'b0;
		else 
			begin
				if(rst_int_reg)
					low_packet_valid<=1'b0;
				if(ld_state==1'b1 && packet_valid==1'b0)
					low_packet_valid<=1'b1;
			end
	end
//----------------------------------------------------------------------------------------------------------
//dout
always@(posedge clk)

	begin
		if(!resetn)
			dout<=8'b0;
		else
		begin
			if(detect_add && packet_valid)
				hold_header_byte<=datain;
			else if(lfd_state)
				dout<=hold_header_byte;
			else if(ld_state && !fifo_full)
				dout<=datain;
			else if(ld_state && fifo_full)
				fifo_full_state_byte<=datain;
			else 
				begin
					if(laf_state)
						dout<=fifo_full_state_byte;
				end
		end
	end
//-----------------------------------------------------------------------------------------------------
// internal parity
always@(posedge clk)
	begin
		if(!resetn)
			internal_parity<=8'b0;
		else if(lfd_state)
			internal_parity<=internal_parity ^ hold_header_byte;
		else if(ld_state && packet_valid && !full_state)
			internal_parity<=internal_parity ^ datain;
		else 
			begin	
				if (detect_add)
					internal_parity<=8'b0;
			end
	end
//--------------------------------------------------------------------------------------------------------	
//error and packet_
always@(posedge clk)
	begin
		if(!resetn)
			packet_parity_byte<=8'b0;
		else 
			begin
				if(!packet_valid && ld_state)
					packet_parity_byte<=datain;
			end
	end
//-------------------------------------------------------------------------------------------------------------------------------------
//error
always@(posedge clk)
	begin
		if(!resetn)
			err<=1'b0;
		else 
			begin
				if(parity_done)
				begin
					if(internal_parity!=packet_parity_byte)
						err<=1'b1;
					else
						err<=1'b0;
				end
			end
	end

endmodule 
