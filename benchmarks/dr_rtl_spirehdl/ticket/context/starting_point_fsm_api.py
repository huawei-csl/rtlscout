"""Alternative Spire port of `ticket_machine` using the idiomatic
State / switch_ / case_ / if_ / elif_ FSM API
(see `deps/spire-hdl/docs/README_state_machines.md`).

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
from spire import Component, IORecord, Input, Output, UInt, Register
from spire.state import State, Encoding, state
from spire.control_structures import (
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


class TicketMachine(Component):
    def __init__(self):
        self.io = IORecord(
            clear=Input(UInt(1)),
            ten=Input(UInt(1)),
            twenty=Input(UInt(1)),
            ready=Output(UInt(1)),
            dispense=Output(UInt(1)),
            return_sig=Output(UInt(1)),
            bill=Output(UInt(1)),
        )
        self.elaborate()

    def elaborate(self):
        # alias every port so the original body is unchanged
        clear = self.io.clear
        ten = self.io.ten
        twenty = self.io.twenty
        ready = self.io.ready
        dispense = self.io.dispense
        return_sig = self.io.return_sig
        bill = self.io.bill

        # State register. `init=TicketFSM.RDY` is the t=0 power-on value; the
        # *runtime* sync reset is implemented below as the `if_(clear): ...`
        # branch wrapping the next-state switch.
        state_reg = Register(TicketFSM.typ, init=TicketFSM.RDY, name="State")

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


TicketMachine().to_verilog_file("design.v", name="ticket_machine", with_clock=True)
