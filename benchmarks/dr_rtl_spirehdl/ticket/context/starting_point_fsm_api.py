"""Alternative SpireHDL port of `ticket_machine` using the idiomatic
State / switch_ / case_ / if_ / elif_ FSM API
(see `deps/spire-hdl/README_state_machines.md`).

Functionally equivalent to `starting_point.py` (the mux-cascade variant);
emits the same `design.v` module with the same top-module name and port
list. The difference is purely stylistic — this version reads closer to
the original verilog's three-`always`-block structure:

  1. State register   ← always @(posedge clk) if (clear) ... else ...
  2. Next-state logic ← always @(*) case (State) ...
  3. Output decoders  ← Moore-style assigns from State

Pick whichever variant reads better for the use case. Run framework eval
with the chosen file path:

    python run_eval.py \\
        benchmarks/dr_rtl_spirehdl/ticket/context/starting_point_fsm_api.py \\
        --benchmark benchmarks/dr_rtl_spirehdl/ticket \\
        --language spirehdl --cost-metric yosys_cells
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt
from spirehdl.spirehdl_state import State, Encoding, state
from spirehdl.spirehdl_control_structures import (
    switch_, case_, default, if_, elif_, else_,
)


class TicketFSM(State, encoding=Encoding.ONEHOT):
    """Matches the verilog's `localparam RDY = 6'b000001, ...` one-hot encoding.

    Under `Encoding.ONEHOT`, `TicketFSM.RDY.value == 0b000001 = 1`,
    `TicketFSM.DISP.value == 0b000010 = 2`, and so on — exactly the
    integers the verilog source assigns.
    """
    RDY    = state()
    DISP   = state()
    RTN    = state()
    BILL10 = state()
    BILL20 = state()
    BILL30 = state()


m = Module("ticket_machine", with_clock=True, with_reset=False)

# Inputs
clear  = m.input(UInt(1), "clear")
ten    = m.input(UInt(1), "ten")
twenty = m.input(UInt(1), "twenty")

# Outputs (Moore)
ready      = m.output(UInt(1), "ready")
dispense   = m.output(UInt(1), "dispense")
return_sig = m.output(UInt(1), "return_sig")
bill       = m.output(UInt(1), "bill")

# State register. `init=TicketFSM.RDY` is the t=0 power-on value; the
# *runtime* sync reset is implemented below as the `if_(clear): ...`
# branch wrapping the next-state switch.
state_reg = m.reg(TicketFSM.typ, "State", init=TicketFSM.RDY)


# Next-state logic — sync clear takes priority, else the switch decides.
# Matches verilog:
#     always @(posedge clk) begin
#       if (clear) State <= RDY;
#       else       State <= NextState;
#     end
#     always @(State or ten or twenty) case (State) ... endcase
with if_(clear):
    state_reg <<= TicketFSM.RDY
with else_():
    with switch_(state_reg):
        with case_(TicketFSM.RDY):
            with if_(ten):
                state_reg <<= TicketFSM.BILL10
            with elif_(twenty):
                state_reg <<= TicketFSM.BILL20
            # else: stays in RDY (no assignment → register holds)
        with case_(TicketFSM.BILL10):
            with if_(ten):
                state_reg <<= TicketFSM.BILL20
            with elif_(twenty):
                state_reg <<= TicketFSM.BILL30
        with case_(TicketFSM.BILL20):
            with if_(ten):
                state_reg <<= TicketFSM.BILL30
            with elif_(twenty):
                state_reg <<= TicketFSM.DISP
        with case_(TicketFSM.BILL30):
            with if_(ten):
                state_reg <<= TicketFSM.DISP
            with elif_(twenty):
                state_reg <<= TicketFSM.RTN
        with case_(TicketFSM.DISP):
            state_reg <<= TicketFSM.RDY
        with case_(TicketFSM.RTN):
            state_reg <<= TicketFSM.RDY
        with default():
            state_reg <<= TicketFSM.RDY


# Moore output decode — direct equality on the state register.
# Equivalent to the verilog's output-logic `always @(State)` block.
ready      <<= (state_reg == TicketFSM.RDY)
dispense   <<= (state_reg == TicketFSM.DISP)
return_sig <<= (state_reg == TicketFSM.RTN)
bill       <<= ((state_reg == TicketFSM.BILL10) |
                (state_reg == TicketFSM.BILL20) |
                (state_reg == TicketFSM.BILL30))


m.to_verilog_file("design.v")
