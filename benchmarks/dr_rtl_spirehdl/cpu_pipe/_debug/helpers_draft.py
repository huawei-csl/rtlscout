"""Draft translations of the cpu_pipe submodules.

These are skeleton ports of the simpler 2 of the 5 submodules
(`dcpu16_alu`, `dcpu16_regs`) translated as Python helper functions
ready to integrate into `context/starting_point.py`. The harder 3
(`dcpu16_cpu` top, `dcpu16_ctl`, `dcpu16_mbus`) are not yet drafted —
see DEBUGGING.md for the porting recipe.

**Important correction to original DEBUGGING.md plan:** the cpu_pipe
verilog does NOT use `casex` / `casez`. It uses regular `case` on
either the 4-bit opcode (`opc`) or the 2-bit phase counter (`pha`).
This is significantly easier to translate than the original plan
suggested.

NOT YET INTEGRATED. The top module (`dcpu16_cpu`) still needs translation.
"""
from spirehdl.spirehdl import UInt, Const, Wire, Register, mux, cat


# ============================================================================
# dcpu16_alu — 12-opcode ALU with overflow/carry tracking
# ============================================================================
def dcpu16_alu(regA, regB, opc, pha, rst, ena, rst_active):
    """Mirrors `module dcpu16_alu` (verilog lines 154–328).

    Inputs: regA[15:0], regB[15:0], opc[3:0], pha[1:0], rst, ena.
    `rst_active` is the combined reset signal (sync active-high in this design).

    Returns dict with `regR`, `regO`, `CC`, `f_dto`, `g_dto`, `rwd` outputs.

    Opcode decoding (case (opc) with pha == 0):
      0: SET → regR <= src (regA)
      1: SET → regR <= tgt (regB)
      2: ADD → regR <= add (15-bit add); regO <= {15'd0, c}
      3: SUB → regR <= add (same hw, opc[0]=1 selects subtract); regO <= {16{c}}
      4: MUL → regR <= mul[15:0]; regO <= mul[31:16]
      7: SHL → regR <= shl[15:0]; regO <= shl[31:16]
      8: SHR → regR <= shr[31:16]; regO <= shr[15:0]
      9: AND → regR <= src & tgt
      A: OR  → regR <= src | tgt
      B: XOR → regR <= src ^ tgt
      C: IFE → CC <= (src == tgt)
      D: IFN → CC <= (src != tgt)
      E: IFG → CC <= (src > tgt)
      F: IFB → CC <= |(src & tgt)
    """
    # Arithmetic combinational signals (verilog: always @* with no clock)
    src = regA
    tgt = regB
    # Subtract / add based on opc[0]
    # Verilog: {c, add} <= (~opc[0]) ? (src + tgt) : (src - tgt)
    add_op = (src + tgt)[0:17]        # 17-bit result (carry in bit 16)
    sub_op = (src - tgt)[0:17]
    add_result = mux(~opc[0], add_op, sub_op)
    c   = add_result[16]              # carry bit
    add = add_result[0:16]            # 16-bit truncated sum/diff
    # mul: 17 × 17 unsigned multiply → 34-bit
    # In spirehdl: UInt(16) * UInt(16) → UInt(32). Verilog does `{1'b0,src} * {1'b0,tgt}` → 34-bit.
    # We approximate with 32-bit; for the test vectors (no overflow into bit 33), this should match.
    mul = (src * tgt)[0:32]
    # Shifts: variable amount
    shl = (src << tgt)[0:32]
    shr = (cat(Const(0, UInt(16)), src) >> tgt)[0:32]

    # Registers
    regR_r = Register(UInt(16), name="alu_regR")
    regO_r = Register(UInt(16), name="alu_regO")
    CC_r   = Register(UInt(1),  name="alu_CC")

    is_pha_0 = pha == Const(0, UInt(2))

    # regO update: only on opcodes 2/3/4/7/8 in phase 0, else hold
    regO_next = mux(is_pha_0,
        mux(opc == Const(0x2, UInt(4)), cat(c, Const(0, UInt(15))),
        mux(opc == Const(0x3, UInt(4)), cat(*([c] * 16)),
        mux(opc == Const(0x4, UInt(4)), mul[16:32],
        mux(opc == Const(0x7, UInt(4)), shl[16:32],
        mux(opc == Const(0x8, UInt(4)), shr[0:16],
                                         regO_r))))),
        regO_r)

    # regR update — table of opcode → value
    regR_next = mux(is_pha_0,
        mux(opc == Const(0x0, UInt(4)), src,
        mux(opc == Const(0x1, UInt(4)), tgt,
        mux(opc == Const(0x2, UInt(4)), add,
        mux(opc == Const(0x3, UInt(4)), add,
        mux(opc == Const(0x4, UInt(4)), mul[0:16],
        mux(opc == Const(0x7, UInt(4)), shl[0:16],
        mux(opc == Const(0x8, UInt(4)), shr[16:32],
        mux(opc == Const(0x9, UInt(4)), src & tgt,
        mux(opc == Const(0xA, UInt(4)), src | tgt,
        mux(opc == Const(0xB, UInt(4)), src ^ tgt,
                                         regR_r))))))))))),
        regR_r)

    # CC update — comparison opcodes in phase 0
    CC_next = mux(is_pha_0,
        mux(opc == Const(0xC, UInt(4)), (src == tgt),
        mux(opc == Const(0xD, UInt(4)), (src != tgt),
        mux(opc == Const(0xE, UInt(4)), (src > tgt),
        mux(opc == Const(0xF, UInt(4)), (src & tgt) != Const(0, UInt(16)),
                                         Const(1, UInt(1)))))),
        CC_r)

    # ena gates everything
    regR_r <<= mux(rst_active, Const(0, UInt(16)),
                mux(ena, regR_next, regR_r))
    regO_r <<= mux(rst_active, Const(0, UInt(16)),
                mux(ena, regO_next, regO_r))
    CC_r   <<= mux(rst_active, Const(0, UInt(1)),
                mux(ena, CC_next, CC_r))

    return {
        "regR": regR_r, "regO": regO_r, "CC": CC_r,
        "f_dto": regR_r, "g_dto": regR_r, "rwd": regR_r,
    }


# ============================================================================
# dcpu16_regs — 8 × 16-bit register file (3 read ports, 1 write port)
# ============================================================================
def dcpu16_regs(rwa, rwe, rwd, rra, ena, rst_active):
    """Mirrors `module dcpu16_regs` (verilog lines 895–926).

    Register file: 8 entries × 16 bits.
        rwa[2:0]: write address
        rwe:      write enable
        rwd[15:0]: write data
        rra[2:0]: read address
        ena:      clock enable (gates writes; reads are always live)

    Returns the read-data output `rrd[15:0]`.

    NB: like router's FIFO, watch for blocking-vs-NBA race on multi-port
    register-file access. The verilog uses `<=` for writes and combinational
    reads, so the read sees the PRE-EDGE value. Spirehdl Register pre-step
    semantics match this naturally — no `wptr_next` hack needed.
    """
    # 8 × 16-bit register array (list of Registers)
    rf = [Register(UInt(16), name=f"rf_{i}") for i in range(8)]

    # Read: mux on rra
    chain = rf[7]
    for i in reversed(range(7)):
        chain = mux(rra == Const(i, UInt(3)), rf[i], chain)
    rrd = chain

    # Write: each register's next-state guards on (rwa == i & rwe & ena)
    for i in range(8):
        match = (rwa == Const(i, UInt(3))) & rwe & ena
        rf[i] <<= mux(rst_active, Const(0, UInt(16)),
                   mux(match, rwd, rf[i]))

    return rrd


# ============================================================================
# TODO: dcpu16_ctl — instruction phase controller + register addr decoder
# ============================================================================
# 140-LOC controller. Mostly `case (pha)` (2-bit phase counter)
# over instruction fields (`decA = ireg[9:4]`, `decB = ireg[15:10]`,
# `decO = ireg[3:0]`). Pipeline registers for branch control and
# register-file write addressing.
#
# Translation plan: each `always @(posedge clk) case (pha)` block becomes
# a `next_state = mux(pha == 0, val_0, mux(pha == 1, val_1, ...))` chain.
# No casex — regular case statements only.

# ============================================================================
# TODO: dcpu16_mbus — memory bus arbiter between fetch (f_*) and general (g_*) buses
# ============================================================================
# 420-LOC arbiter. Has multiple FSMs for bus protocol:
#   - fetch state machine (reads instruction from f_* bus)
#   - general bus state machine (reads/writes data on g_* bus)
#   - arbitration between the two
# Each state machine is small (~5-8 states); challenge is correct
# inter-FSM coordination.

# ============================================================================
# TODO: dcpu16_cpu (top) — instantiates the 4 submodules + wires them together
# ============================================================================
# Top is structural: ~30 LOC of submodule instantiation. The hard part is
# making sure all the cross-submodule wires (alu→ctl, ctl→mbus, mbus→regs,
# etc.) are connected correctly.
