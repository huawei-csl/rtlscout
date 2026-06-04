"""SpireHDL starting point for `ticket_machine` — vending-machine ticket FSM.

Mirrors rtl_dataset/ticket_machine.v0.v one-for-one:

  - 6-state one-hot FSM (RDY / DISP / RTN / BILL10 / BILL20 / BILL30) over
    `ten`/`twenty` coin inputs.
  - Sync active-high `clear` reset (inside `always @(posedge clk)`).
  - 4 × 1-bit Moore outputs decoded from State:
        ready=1       only in RDY
        dispense=1    only in DISP
        return_sig=1  only in RTN
        bill=1        in BILL10/BILL20/BILL30

`with_reset=False` + explicit `mux(clear, RDY, NextState)` because the
reset port is named `clear`, not `rst`, and the verilog uses sync (not
async) reset semantics — per the `with_reset` decision tree in
benchmarks/turbo_rtl/README.md:281-318.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Register, Wire, mux

m = Module("ticket_machine", with_clock=True, with_reset=False)

# Inputs
clear  = m.input(UInt(1), "clear")
ten    = m.input(UInt(1), "ten")
twenty = m.input(UInt(1), "twenty")

# Outputs (Moore — each is a function of State alone)
ready      = m.output(UInt(1), "ready")
dispense   = m.output(UInt(1), "dispense")
return_sig = m.output(UInt(1), "return_sig")
bill       = m.output(UInt(1), "bill")

# One-hot state encoding (matches the verilog `localparam` values verbatim)
RDY    = 0b000001
DISP   = 0b000010
RTN    = 0b000100
BILL10 = 0b001000
BILL20 = 0b010000
BILL30 = 0b100000

State = Register(UInt(6), name="State")

# Next-state logic per current state. RDY/BILL10/BILL20/BILL30 cases test
# `ten` first, then `twenty`, then hold (matching the verilog `if (ten) ...
# else if (twenty) ... else <hold>` priority encoding).
ns_from_rdy    = mux(ten, BILL10, mux(twenty, BILL20, RDY))
ns_from_bill10 = mux(ten, BILL20, mux(twenty, BILL30, BILL10))
ns_from_bill20 = mux(ten, BILL30, mux(twenty, DISP,   BILL20))
ns_from_bill30 = mux(ten, DISP,   mux(twenty, RTN,    BILL30))

# Cascaded mux over State equality. yosys+abc will collapse this to a 6:1 mux
# during opt. Order doesn't matter because the predicates are mutually
# exclusive (one-hot state).
NextState = Wire(UInt(6), name="NextState")
NextState <<= mux(State == RDY,    ns_from_rdy,
              mux(State == BILL10, ns_from_bill10,
              mux(State == BILL20, ns_from_bill20,
              mux(State == BILL30, ns_from_bill30,
              mux(State == DISP,   RDY,
              mux(State == RTN,    RDY,
                                   RDY))))))  # default: RDY (matches verilog)

# Sync clear: State <= clear ? RDY : NextState
State <<= mux(clear, RDY, NextState)

# Moore output decoders — each output is a single equality on State, except
# `bill` which OR's the three BILL10/20/30 states.
ready      <<= (State == RDY)
dispense   <<= (State == DISP)
return_sig <<= (State == RTN)
bill       <<= ((State == BILL10) | (State == BILL20) | (State == BILL30))

m.to_verilog_file("design.v")
