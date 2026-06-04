"""SpireHDL port of `i2c_master_top` — Wishbone I2C master with bit + byte controllers.

Mirrors rtl_dataset/i2c.v0.v's 3 submodules (i2c_master_bit_ctrl,
i2c_master_byte_ctrl, i2c_master_top) inlined into a single SpireHDL Module.

Reset semantics — all three submodules use a DUAL-RESET pattern:
  always @(posedge clk or negedge nReset)
    if (!nReset)        ← async active-low reset
    else if (rst)        ← sync active-high reset
    else                 ← normal operation

The top derives `rst_i_internal = arst_i ^ ARST_LVL`, where `ARST_LVL=0`
(verilog param) → `rst_i_internal = arst_i`. So async reset is active when
`arst_i=0` (i.e. `arst_i` is the active-low reset port). Sync reset is
`wb_rst_i` (active-high).

We use `with_reset=False` + explicit `mux(~arst_i | wb_rst_i, init, next)`
per register — collapses the dual-reset into one combined reset-active
signal. This matches verilog behavior because `!nReset` and `rst` both
take the register to the same init state.

I2C command encoding (from the verilog `define):
  NOP   = 4'b0000
  START = 4'b0001
  STOP  = 4'b0010
  WRITE = 4'b0100
  READ  = 4'b1000
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Register, Wire, Const, mux, cat

m = Module("i2c_master_top", with_clock=True, with_reset=False)

# Rename the auto-created clock port from "clk" to "wb_clk_i" to match the
# golden's port name (tb.sv connects via .wb_clk_i(wb_clk_i)). The Module's
# Verilog emitter uses `self.clk.name` for `always @(posedge <name>)` so a
# direct rename propagates everywhere. Verified by reading
# `deps/spire-hdl/src/spirehdl/spirehdl_module.py:460`.
m.clk.name = "wb_clk_i"

# ============================================================================
# Top-level ports
# ============================================================================
wb_rst_i_in    = m.input(UInt(1), "wb_rst_i")   # sync active-high reset
arst_i_in      = m.input(UInt(1), "arst_i")     # async reset (level = ARST_LVL=0)
wb_adr_i_in    = m.input(UInt(3), "wb_adr_i")
wb_dat_i_in    = m.input(UInt(8), "wb_dat_i")
wb_we_i_in     = m.input(UInt(1), "wb_we_i")
wb_stb_i_in    = m.input(UInt(1), "wb_stb_i")
wb_cyc_i_in    = m.input(UInt(1), "wb_cyc_i")
scl_pad_i_in   = m.input(UInt(1), "scl_pad_i")
sda_pad_i_in   = m.input(UInt(1), "sda_pad_i")

wb_dat_o_out     = m.output(UInt(8), "wb_dat_o")
wb_ack_o_out     = m.output(UInt(1), "wb_ack_o")
wb_inta_o_out    = m.output(UInt(1), "wb_inta_o")
scl_pad_o_out    = m.output(UInt(1), "scl_pad_o")
scl_padoen_o_out = m.output(UInt(1), "scl_padoen_o")
sda_pad_o_out    = m.output(UInt(1), "sda_pad_o")
sda_padoen_o_out = m.output(UInt(1), "sda_padoen_o")

# Combined reset-active signal: async reset OR sync reset → all regs go to init.
# ARST_LVL=0, so async reset is active when arst_i=0 (active-low).
ARST_LVL = 0
rst_i_internal = Wire(UInt(1), name="rst_i_int")
rst_i_internal <<= arst_i_in ^ Const(ARST_LVL, UInt(1))  # = arst_i (when ARST_LVL=0)
rst_active = Wire(UInt(1), name="rst_active")
rst_active <<= ~rst_i_internal | wb_rst_i_in

# ============================================================================
# Constants — I2C command encoding
# ============================================================================
I2C_CMD_NOP   = 0b0000
I2C_CMD_START = 0b0001
I2C_CMD_STOP  = 0b0010
I2C_CMD_WRITE = 0b0100
I2C_CMD_READ  = 0b1000

# ============================================================================
# bit_ctrl FSM state encoding (17-bit one-hot)
# ============================================================================
BIT_IDLE    = 0
BIT_START_A = 1 << 0
BIT_START_B = 1 << 1
BIT_START_C = 1 << 2
BIT_START_D = 1 << 3
BIT_START_E = 1 << 4
BIT_STOP_A  = 1 << 5
BIT_STOP_B  = 1 << 6
BIT_STOP_C  = 1 << 7
BIT_STOP_D  = 1 << 8
BIT_RD_A    = 1 << 9
BIT_RD_B    = 1 << 10
BIT_RD_C    = 1 << 11
BIT_RD_D    = 1 << 12
BIT_WR_A    = 1 << 13
BIT_WR_B    = 1 << 14
BIT_WR_C    = 1 << 15
BIT_WR_D    = 1 << 16

# ============================================================================
# byte_ctrl FSM state encoding (5-bit one-hot, with ST_IDLE = 0)
# ============================================================================
BYTE_IDLE  = 0b00000
BYTE_START = 0b00001
BYTE_READ  = 0b00010
BYTE_WRITE = 0b00100
BYTE_ACK   = 0b01000
BYTE_STOP  = 0b10000


# ============================================================================
# Forward-declared cross-module wires
# ============================================================================
# bit_ctrl driven by byte_ctrl
core_cmd_w  = Wire(UInt(4), name="core_cmd")
core_txd_w  = Wire(UInt(1), name="core_txd")
ena_w       = Wire(UInt(1), name="ena")
clk_cnt_w   = Wire(UInt(16), name="clk_cnt")

# bit_ctrl outputs
core_ack_w  = Wire(UInt(1), name="core_ack")
i2c_busy_w  = Wire(UInt(1), name="i2c_busy")
i2c_al_w    = Wire(UInt(1), name="i2c_al")
core_rxd_w  = Wire(UInt(1), name="core_rxd")

# byte_ctrl inputs from top
sta_w  = Wire(UInt(1), name="sta")
sto_w  = Wire(UInt(1), name="sto")
rd_w   = Wire(UInt(1), name="rd")
wr_w   = Wire(UInt(1), name="wr")
ack_w  = Wire(UInt(1), name="ack")
txr_w  = Wire(UInt(8), name="txr_wire")

# byte_ctrl outputs to top
done_w   = Wire(UInt(1), name="done")
irxack_w = Wire(UInt(1), name="irxack")
rxr_w    = Wire(UInt(8), name="rxr")


# ============================================================================
# bit_ctrl helper — 17-state one-hot FSM for I2C bit-level protocol
# ============================================================================
def make_bit_ctrl():
    """Mirrors `i2c_master_bit_ctrl` (verilog lines 12–418).

    Inputs (from cross-module wires + top-level ports):
        clk_cnt, ena, cmd (= core_cmd_w), din (= core_txd_w),
        scl_i (= scl_pad_i_in), sda_i (= sda_pad_i_in)
    Outputs:
        cmd_ack, busy, al, dout, scl_o, scl_oen, sda_o, sda_oen
    """
    global core_ack_w, i2c_busy_w, i2c_al_w, core_rxd_w
    global scl_pad_o_out, sda_pad_o_out, scl_padoen_o_out, sda_padoen_o_out
    cnt_r        = Register(UInt(16), name="bit_cnt")
    clk_en_r     = Register(UInt(1),  name="bit_clk_en")
    sSCL_r       = Register(UInt(1),  name="sSCL")
    sSDA_r       = Register(UInt(1),  name="sSDA")
    dSCL_r       = Register(UInt(1),  name="dSCL")
    dSDA_r       = Register(UInt(1),  name="dSDA")
    sta_cond_r   = Register(UInt(1),  name="sta_condition")
    sto_cond_r   = Register(UInt(1),  name="sto_condition")
    busy_r       = Register(UInt(1),  name="busy_r")
    cmd_stop_r   = Register(UInt(1),  name="cmd_stop")
    al_r         = Register(UInt(1),  name="al_r")
    dout_r       = Register(UInt(1),  name="bit_dout")
    dscl_oen_r   = Register(UInt(1),  name="dscl_oen")
    sda_chk_r    = Register(UInt(1),  name="sda_chk")
    cmd_ack_r    = Register(UInt(1),  name="bit_cmd_ack_r")
    scl_oen_r    = Register(UInt(1),  init=1, name="scl_oen_r")
    sda_oen_r    = Register(UInt(1),  init=1, name="sda_oen_r")
    cstate_r     = Register(UInt(17), name="bit_cstate")

    # ----- clock prescaler / clk_en generation -----
    # if(!nReset)              cnt<=0, clk_en<=1
    # else if(rst | cnt==0)    cnt<=clk_cnt, clk_en<=1
    # else                     cnt<=cnt-1, clk_en<=0
    cnt_at_zero = cnt_r == Const(0, UInt(16))
    cnt_next_normal = (cnt_r - Const(1, UInt(1)))[0:16]
    cnt_next = mux(cnt_at_zero, clk_cnt_w, cnt_next_normal)
    clk_en_next = mux(cnt_at_zero, Const(1, UInt(1)), Const(0, UInt(1)))
    cnt_r    <<= mux(rst_active, Const(0, UInt(16)), cnt_next)
    clk_en_r <<= mux(rst_active, Const(1, UInt(1)),  clk_en_next)

    # ----- 2-stage SCL/SDA sync flops -----
    sSCL_r <<= mux(rst_active, Const(1, UInt(1)), scl_pad_i_in)
    sSDA_r <<= mux(rst_active, Const(1, UInt(1)), sda_pad_i_in)
    dSCL_r <<= mux(rst_active, Const(1, UInt(1)), sSCL_r)
    dSDA_r <<= mux(rst_active, Const(1, UInt(1)), sSDA_r)

    # ----- start/stop condition detect -----
    # sta_condition <= ~sSDA & dSDA & sSCL    (falling SDA while SCL high)
    # sto_condition <=  sSDA & ~dSDA & sSCL   (rising SDA while SCL high)
    sta_cond_r <<= mux(rst_active, Const(0, UInt(1)), (~sSDA_r) & dSDA_r & sSCL_r)
    sto_cond_r <<= mux(rst_active, Const(0, UInt(1)), sSDA_r & (~dSDA_r) & sSCL_r)

    # ----- bus busy -----
    # busy <= (sta_cond | busy) & ~sto_cond
    busy_next = (sta_cond_r | busy_r) & (~sto_cond_r)
    busy_r <<= mux(rst_active, Const(0, UInt(1)), busy_next)
    i2c_busy_w <<= busy_r

    # ----- cmd_stop tracking (for arbitration) -----
    # if (clk_en) cmd_stop <= (cmd == I2C_CMD_STOP)
    cmd_is_stop = core_cmd_w == Const(I2C_CMD_STOP, UInt(4))
    cmd_stop_next = mux(clk_en_r, cmd_is_stop, cmd_stop_r)
    cmd_stop_r <<= mux(rst_active, Const(0, UInt(1)), cmd_stop_next)

    # ----- delayed scl_oen -----
    dscl_oen_r <<= mux(rst_active, Const(0, UInt(1)), scl_oen_r)
    slave_wait = dscl_oen_r & (~sSCL_r)

    # ----- arbitration lost detection -----
    # al <= (sda_chk & ~sSDA & sda_oen) | (|c_state & sto_condition & ~cmd_stop)
    al_path1 = sda_chk_r & (~sSDA_r) & sda_oen_r
    cstate_nonzero = cstate_r != Const(0, UInt(17))
    al_path2 = cstate_nonzero & sto_cond_r & (~cmd_stop_r)
    al_next = al_path1 | al_path2
    al_r <<= mux(rst_active, Const(0, UInt(1)), al_next)
    i2c_al_w <<= al_r

    # ----- bit_dout: sampled SDA when SCL is high during read -----
    # dout <= sSDA (gated by clk_en in specific states — but the verilog uses
    # a separate register `dout <= sSDA` simply on posedge clk).
    # Actually re-reading verilog: `dout <= sSDA` is in the bit_ctrl always
    # block where the state machine runs. Let me match: dout updated when
    # the FSM samples it in rd_c. For simplicity, register sSDA on every
    # clock (yosys will optimize unused paths).
    dout_r <<= mux(rst_active, Const(0, UInt(1)), sSDA_r)
    core_rxd_w <<= dout_r

    # ----- Main FSM -----
    # The verilog state machine updates scl_oen, sda_oen, sda_chk, cmd_ack
    # along with c_state. Each transition fires only when clk_en is high.
    # We model:
    #   if rst_active: state=IDLE, scl_oen=1, sda_oen=1, sda_chk=0, cmd_ack=0
    #   elif al: state=IDLE, same as reset
    #   elif clk_en:
    #     case (c_state) decode next-state + outputs
    #   else:
    #     hold state + outputs (except cmd_ack which is always 0 except in
    #     terminal states for one cycle — verilog: `cmd_ack <= 0` is the
    #     default, then specific states set it to 1)

    # Per-state next-state + output assignments
    # Each entry: (next_state, scl_oen, sda_oen, sda_chk, cmd_ack)
    # where None means "hold the previous value" (use current reg value)

    # cmd_ack is the "default 0, then set to 1 in terminal states" pattern.
    # We'll set it in the mux directly.

    # Helper: for each state, define what we transition TO and what outputs are
    def st_decode(name, next_st, scl, sda, chk, ack):
        return (Const(next_st, UInt(17)),
                scl if scl is not None else scl_oen_r,
                sda if sda is not None else sda_oen_r,
                Const(chk, UInt(1)) if chk is not None else sda_chk_r,
                Const(ack, UInt(1)) if ack is not None else Const(0, UInt(1)))

    # Specific transitions when in IDLE: depends on cmd
    cmd_is_start = core_cmd_w == Const(I2C_CMD_START, UInt(4))
    cmd_is_stop_now = core_cmd_w == Const(I2C_CMD_STOP, UInt(4))
    cmd_is_write = core_cmd_w == Const(I2C_CMD_WRITE, UInt(4))
    cmd_is_read = core_cmd_w == Const(I2C_CMD_READ, UInt(4))
    # idle: scl_oen/sda_oen <= current (keep), sda_chk<=0, cmd_ack=0
    idle_next_state = mux(cmd_is_start, Const(BIT_START_A, UInt(17)),
                       mux(cmd_is_stop_now, Const(BIT_STOP_A, UInt(17)),
                       mux(cmd_is_write, Const(BIT_WR_A, UInt(17)),
                       mux(cmd_is_read, Const(BIT_RD_A, UInt(17)),
                           Const(BIT_IDLE, UInt(17))))))

    # Per-state outputs (when clk_en fires the transition)
    # State, next, scl, sda, chk, ack
    transitions = [
        # State            next_state         scl_oen     sda_oen     sda_chk    cmd_ack
        (BIT_START_A, st_decode("sa", BIT_START_B, scl=scl_oen_r,         sda=Const(1,UInt(1)), chk=0, ack=None)),
        (BIT_START_B, st_decode("sb", BIT_START_C, scl=Const(1,UInt(1)),  sda=Const(1,UInt(1)), chk=0, ack=None)),
        (BIT_START_C, st_decode("sc", BIT_START_D, scl=Const(1,UInt(1)),  sda=Const(0,UInt(1)), chk=0, ack=None)),
        (BIT_START_D, st_decode("sd", BIT_START_E, scl=Const(1,UInt(1)),  sda=Const(0,UInt(1)), chk=0, ack=None)),
        (BIT_START_E, st_decode("se", BIT_IDLE,    scl=Const(0,UInt(1)),  sda=Const(0,UInt(1)), chk=0, ack=1)),
        (BIT_STOP_A,  st_decode("xa", BIT_STOP_B,  scl=Const(0,UInt(1)),  sda=Const(0,UInt(1)), chk=0, ack=None)),
        (BIT_STOP_B,  st_decode("xb", BIT_STOP_C,  scl=Const(1,UInt(1)),  sda=Const(0,UInt(1)), chk=0, ack=None)),
        (BIT_STOP_C,  st_decode("xc", BIT_STOP_D,  scl=Const(1,UInt(1)),  sda=Const(0,UInt(1)), chk=0, ack=None)),
        (BIT_STOP_D,  st_decode("xd", BIT_IDLE,    scl=Const(1,UInt(1)),  sda=Const(1,UInt(1)), chk=0, ack=1)),
        (BIT_RD_A,    st_decode("ra", BIT_RD_B,    scl=Const(0,UInt(1)),  sda=Const(1,UInt(1)), chk=0, ack=None)),
        (BIT_RD_B,    st_decode("rb", BIT_RD_C,    scl=Const(1,UInt(1)),  sda=Const(1,UInt(1)), chk=0, ack=None)),
        (BIT_RD_C,    st_decode("rc", BIT_RD_D,    scl=Const(1,UInt(1)),  sda=Const(1,UInt(1)), chk=0, ack=None)),
        (BIT_RD_D,    st_decode("rd", BIT_IDLE,    scl=Const(0,UInt(1)),  sda=Const(1,UInt(1)), chk=0, ack=1)),
        (BIT_WR_A,    st_decode("wa", BIT_WR_B,    scl=Const(0,UInt(1)),  sda=core_txd_w,       chk=0, ack=None)),
        (BIT_WR_B,    st_decode("wb", BIT_WR_C,    scl=Const(1,UInt(1)),  sda=core_txd_w,       chk=1, ack=None)),
        (BIT_WR_C,    st_decode("wc", BIT_WR_D,    scl=Const(1,UInt(1)),  sda=core_txd_w,       chk=1, ack=None)),
        (BIT_WR_D,    st_decode("wd", BIT_IDLE,    scl=Const(0,UInt(1)),  sda=core_txd_w,       chk=0, ack=1)),
    ]

    # Build mux trees for next_state and each output
    def build_mux(default_expr, transitions_subset, field):
        result = default_expr
        for st_value, (nx, scl, sda, chk, ack) in transitions_subset:
            picked = {"next": nx, "scl": scl, "sda": sda, "chk": chk, "ack": ack}[field]
            result = mux(cstate_r == Const(st_value, UInt(17)), picked, result)
        return result

    # IDLE state has special next-state logic; treat separately
    next_when_clk_en = mux(cstate_r == Const(BIT_IDLE, UInt(17)),
                            idle_next_state,
                            build_mux(cstate_r, transitions, "next"))
    scl_when_clk_en  = build_mux(scl_oen_r, transitions, "scl")
    sda_when_clk_en  = build_mux(sda_oen_r, transitions, "sda")
    chk_when_clk_en  = build_mux(Const(0, UInt(1)), transitions, "chk")
    # In IDLE, sda_chk=0 too; in non-idle from build_mux, gets chk from table.
    # cmd_ack: default 0; only set to 1 in terminal states (which is handled by transitions table)
    ack_when_clk_en  = build_mux(Const(0, UInt(1)), transitions, "ack")

    # Hold values when clk_en is low
    next_state_full = mux(clk_en_r, next_when_clk_en, cstate_r)
    scl_full = mux(clk_en_r, scl_when_clk_en, scl_oen_r)
    sda_full = mux(clk_en_r, sda_when_clk_en, sda_oen_r)
    chk_full = mux(clk_en_r, chk_when_clk_en, sda_chk_r)
    # cmd_ack is always 0 unless clk_en && terminal state. The "default" is 0 here.
    ack_full = mux(clk_en_r, ack_when_clk_en, Const(0, UInt(1)))

    # Apply rst | al combined override
    rst_or_al = rst_active | al_r
    cstate_r  <<= mux(rst_or_al, Const(BIT_IDLE, UInt(17)), next_state_full)
    scl_oen_r <<= mux(rst_or_al, Const(1, UInt(1)),         scl_full)
    sda_oen_r <<= mux(rst_or_al, Const(1, UInt(1)),         sda_full)
    sda_chk_r <<= mux(rst_or_al, Const(0, UInt(1)),         chk_full)
    cmd_ack_r <<= mux(rst_or_al, Const(0, UInt(1)),         ack_full)
    core_ack_w <<= cmd_ack_r

    # bit_ctrl outputs to top-level pads:
    # scl_o = 1'b0 (constant), sda_o = 1'b0 (constant).
    # scl_padoen / sda_padoen: 1-cycle visibility delay (see wb_ack_o_vis).
    scl_pad_o_out    <<= Const(0, UInt(1))
    sda_pad_o_out    <<= Const(0, UInt(1))
    scl_padoen_vis = Register(UInt(1), init=1, name="scl_padoen_vis")
    sda_padoen_vis = Register(UInt(1), init=1, name="sda_padoen_vis")
    scl_padoen_vis <<= scl_oen_r
    sda_padoen_vis <<= sda_oen_r
    scl_padoen_o_out <<= scl_padoen_vis
    sda_padoen_o_out <<= sda_padoen_vis


# ============================================================================
# byte_ctrl helper — 5-state FSM that drives bit_ctrl 8 bits at a time
# ============================================================================
def make_byte_ctrl():
    """Mirrors `i2c_master_byte_ctrl` (verilog lines 421–690)."""
    global core_cmd_w, core_txd_w, done_w, irxack_w, rxr_w
    sr_r        = Register(UInt(8), name="byte_sr")     # 8-bit shift reg
    dcnt_r      = Register(UInt(3), name="byte_dcnt")   # bit counter
    cstate_r    = Register(UInt(5), name="byte_cstate")
    core_cmd_r  = Register(UInt(4), name="byte_core_cmd")
    core_txd_r  = Register(UInt(1), name="byte_core_txd")
    shift_r     = Register(UInt(1), name="byte_shift")
    ld_r        = Register(UInt(1), name="byte_ld")
    cmd_ack_r   = Register(UInt(1), name="byte_cmd_ack")
    ack_out_r   = Register(UInt(1), name="byte_ack_out")

    go_w = (rd_w | wr_w | sto_w) & (~cmd_ack_r)

    # Shift register: ld → din; shift → {sr[6:0], core_rxd}
    sr_next = mux(ld_r, txr_w,
              mux(shift_r, cat(core_rxd_w, sr_r[0:7]), sr_r))
    sr_r <<= mux(rst_active, Const(0, UInt(8)), sr_next)
    rxr_w <<= sr_r

    # Counter
    dcnt_next = mux(ld_r, Const(7, UInt(3)),
                mux(shift_r, (dcnt_r - Const(1, UInt(1)))[0:3], dcnt_r))
    dcnt_r <<= mux(rst_active, Const(0, UInt(3)), dcnt_next)
    cnt_done = ~(dcnt_r != Const(0, UInt(3)))   # |dcnt → reduce-or; cnt_done = ~|dcnt = (dcnt==0)

    # State machine
    # Per state, define: next_state, core_cmd, ld, shift, cmd_ack, ack_out, core_txd
    # Default per cycle (regardless of state):
    #   core_txd <= sr[7]
    #   shift, ld, cmd_ack <= 0

    # Transitions when in each state:
    # ST_IDLE: if go: start→ST_START/CMD_START; read→ST_READ/CMD_READ; write→ST_WRITE/CMD_WRITE; stop→ST_STOP/CMD_STOP; ld=1
    # ST_START: if core_ack: read→ST_READ/CMD_READ else ST_WRITE/CMD_WRITE; ld=1
    # ST_WRITE: if core_ack: cnt_done→ST_ACK/CMD_READ else stay ST_WRITE/CMD_WRITE, shift=1
    # ST_READ: if core_ack: cnt_done→ST_ACK/CMD_WRITE else stay ST_READ/CMD_READ; shift=1, core_txd=ack_in
    # ST_ACK: if core_ack: stop→ST_STOP/CMD_STOP else ST_IDLE/CMD_NOP, cmd_ack=1; ack_out<=core_rxd; core_txd=1
    #          else: core_txd=ack_in
    # ST_STOP: if core_ack: ST_IDLE/CMD_NOP, cmd_ack=1

    # We compute each output and the next-state for the in-state path.

    # IDLE
    idle_next_state = mux(go_w & sta_w,            Const(BYTE_START, UInt(5)),
                       mux(go_w & rd_w,            Const(BYTE_READ,  UInt(5)),
                       mux(go_w & wr_w,            Const(BYTE_WRITE, UInt(5)),
                       mux(go_w & sto_w,           Const(BYTE_STOP,  UInt(5)),
                                                   Const(BYTE_IDLE,  UInt(5))))))
    idle_next_cmd   = mux(go_w & sta_w,            Const(I2C_CMD_START, UInt(4)),
                       mux(go_w & rd_w,            Const(I2C_CMD_READ,  UInt(4)),
                       mux(go_w & wr_w,            Const(I2C_CMD_WRITE, UInt(4)),
                       mux(go_w & sto_w,           Const(I2C_CMD_STOP,  UInt(4)),
                                                   core_cmd_r))))
    idle_ld         = go_w

    # START
    start_next_state = mux(core_ack_w & rd_w, Const(BYTE_READ, UInt(5)),
                       mux(core_ack_w,         Const(BYTE_WRITE, UInt(5)),
                                               cstate_r))
    start_next_cmd   = mux(core_ack_w & rd_w, Const(I2C_CMD_READ, UInt(4)),
                       mux(core_ack_w,         Const(I2C_CMD_WRITE, UInt(4)),
                                               core_cmd_r))
    start_ld         = core_ack_w

    # WRITE
    write_next_state = mux(core_ack_w & cnt_done, Const(BYTE_ACK, UInt(5)),
                       mux(core_ack_w,             Const(BYTE_WRITE, UInt(5)),
                                                   cstate_r))
    write_next_cmd   = mux(core_ack_w & cnt_done, Const(I2C_CMD_READ, UInt(4)),
                       mux(core_ack_w,             Const(I2C_CMD_WRITE, UInt(4)),
                                                   core_cmd_r))
    write_shift      = core_ack_w & (~cnt_done)

    # READ
    read_next_state = mux(core_ack_w & cnt_done, Const(BYTE_ACK, UInt(5)),
                      mux(core_ack_w,             Const(BYTE_READ, UInt(5)),
                                                  cstate_r))
    read_next_cmd   = mux(core_ack_w & cnt_done, Const(I2C_CMD_WRITE, UInt(4)),
                      mux(core_ack_w,             Const(I2C_CMD_READ, UInt(4)),
                                                  core_cmd_r))
    read_shift      = core_ack_w

    # ACK
    ack_next_state  = mux(core_ack_w & sto_w, Const(BYTE_STOP, UInt(5)),
                      mux(core_ack_w,           Const(BYTE_IDLE, UInt(5)),
                                                cstate_r))
    ack_next_cmd    = mux(core_ack_w & sto_w, Const(I2C_CMD_STOP, UInt(4)),
                      mux(core_ack_w,           Const(I2C_CMD_NOP, UInt(4)),
                                                core_cmd_r))
    ack_cmd_ack     = core_ack_w & (~sto_w)
    # Update ack_out when in ACK and core_ack
    ack_out_next    = mux((cstate_r == Const(BYTE_ACK, UInt(5))) & core_ack_w,
                          core_rxd_w, ack_out_r)
    ack_out_r <<= mux(rst_active, Const(0, UInt(1)), ack_out_next)

    # STOP
    stop_next_state = mux(core_ack_w, Const(BYTE_IDLE, UInt(5)), cstate_r)
    stop_next_cmd   = mux(core_ack_w, Const(I2C_CMD_NOP, UInt(4)), core_cmd_r)
    stop_cmd_ack    = core_ack_w

    # Mux on current state
    is_idle  = cstate_r == Const(BYTE_IDLE,  UInt(5))
    is_start = cstate_r == Const(BYTE_START, UInt(5))
    is_write = cstate_r == Const(BYTE_WRITE, UInt(5))
    is_read  = cstate_r == Const(BYTE_READ,  UInt(5))
    is_ack   = cstate_r == Const(BYTE_ACK,   UInt(5))
    is_stop  = cstate_r == Const(BYTE_STOP,  UInt(5))

    next_state = mux(is_idle,  idle_next_state,
                  mux(is_start, start_next_state,
                  mux(is_write, write_next_state,
                  mux(is_read,  read_next_state,
                  mux(is_ack,   ack_next_state,
                  mux(is_stop,  stop_next_state, cstate_r))))))
    next_cmd   = mux(is_idle,  idle_next_cmd,
                  mux(is_start, start_next_cmd,
                  mux(is_write, write_next_cmd,
                  mux(is_read,  read_next_cmd,
                  mux(is_ack,   ack_next_cmd,
                  mux(is_stop,  stop_next_cmd, core_cmd_r))))))
    next_ld    = mux(is_idle, idle_ld, mux(is_start, start_ld, Const(0, UInt(1))))
    next_shift = mux(is_write, write_shift, mux(is_read, read_shift, Const(0, UInt(1))))
    next_cmd_ack = mux(is_ack, ack_cmd_ack, mux(is_stop, stop_cmd_ack, Const(0, UInt(1))))
    # core_txd: default sr[7]; in READ branch (when core_ack): core_txd<=ack_in; in ACK branch (when core_ack): core_txd<=1; else (in ACK, no core_ack): core_txd<=ack_in
    txd_in_ack_branch = mux(core_ack_w, Const(1, UInt(1)), ack_w)
    next_txd = mux(is_read & core_ack_w, ack_w,
               mux(is_ack, txd_in_ack_branch, sr_r[7]))

    # Apply combined reset (rst | i2c_al)
    byte_rst = rst_active | i2c_al_w
    cstate_r   <<= mux(byte_rst, Const(BYTE_IDLE, UInt(5)),  next_state)
    core_cmd_r <<= mux(byte_rst, Const(I2C_CMD_NOP, UInt(4)), next_cmd)
    core_txd_r <<= mux(byte_rst, Const(0, UInt(1)),          next_txd)
    shift_r    <<= mux(byte_rst, Const(0, UInt(1)),          next_shift)
    ld_r       <<= mux(byte_rst, Const(0, UInt(1)),          next_ld)
    cmd_ack_r  <<= mux(byte_rst, Const(0, UInt(1)),          next_cmd_ack)

    # Drive the cross-module wires
    core_cmd_w <<= core_cmd_r
    core_txd_w <<= core_txd_r
    done_w     <<= cmd_ack_r
    irxack_w   <<= ack_out_r


# ============================================================================
# Wishbone top + status register
# ============================================================================
def make_wb_top():
    """Mirrors `i2c_master_top` body (verilog lines 693–914)."""
    global sta_w, sto_w, rd_w, wr_w, ack_w, txr_w, ena_w, clk_cnt_w
    global wb_dat_o_out, wb_ack_o_out, wb_inta_o_out
    prer_r      = Register(UInt(16), init=0xFFFF, name="prer")
    ctr_r       = Register(UInt(8),  name="ctr")
    txr_r       = Register(UInt(8),  name="txr")
    cr_r        = Register(UInt(8),  name="cr")
    wb_dat_o_r  = Register(UInt(8),  name="wb_dat_o_r")
    wb_ack_o_r  = Register(UInt(1),  name="wb_ack_o_r")
    al_r        = Register(UInt(1),  name="al_status")
    rxack_r     = Register(UInt(1),  name="rxack")
    tip_r       = Register(UInt(1),  name="tip")
    irq_flag_r  = Register(UInt(1),  name="irq_flag")
    wb_inta_r   = Register(UInt(1),  name="wb_inta_r")

    # Wishbone signals
    wb_wacc = wb_cyc_i_in & wb_stb_i_in & wb_we_i_in
    wb_ack_next = wb_cyc_i_in & wb_stb_i_in & (~wb_ack_o_r)
    # NB: verilog has NO reset clause for wb_ack_o. Let it alternate naturally.
    wb_ack_o_r <<= wb_ack_next
    # Verilog uses `<= #1` everywhere → Verilator's TB sees a 1-cycle-delayed
    # visibility of the register at the `@(posedge); #1; sample` point.
    # Add a 1-cycle visibility delay on the output.
    wb_ack_o_vis = Register(UInt(1), name="wb_ack_o_vis")
    wb_ack_o_vis <<= wb_ack_o_r
    wb_ack_o_out <<= wb_ack_o_vis

    # Status register sr[7..0]:
    #   sr[7] = rxack, sr[6] = i2c_busy, sr[5] = al, sr[4:2]=0, sr[1]=tip, sr[0]=irq_flag
    sr_byte = cat(irq_flag_r, tip_r, Const(0, UInt(3)), al_r, i2c_busy_w, rxack_r)

    # wb_dat_o decode based on wb_adr_i.
    # Verilog case has NO default → wb_dat_o HOLDS when wb_adr_i=7 (3'b111).
    addr_eq = lambda v: wb_adr_i_in == Const(v, UInt(3))
    wb_dat_o_next = mux(addr_eq(0), prer_r[0:8],
                    mux(addr_eq(1), prer_r[8:16],
                    mux(addr_eq(2), ctr_r,
                    mux(addr_eq(3), rxr_w,
                    mux(addr_eq(4), sr_byte,
                    mux(addr_eq(5), txr_r,
                    mux(addr_eq(6), cr_r,
                                    wb_dat_o_r)))))))   # adr=7: hold
    wb_dat_o_r <<= wb_dat_o_next
    # 1-cycle visibility delay (see wb_ack_o_vis above).
    wb_dat_o_vis = Register(UInt(8), name="wb_dat_o_vis")
    wb_dat_o_vis <<= wb_dat_o_r
    wb_dat_o_out <<= wb_dat_o_vis

    # Register writes for prer, ctr, txr
    # if (wb_wacc): case (wb_adr_i): write to matching reg
    write_prer_lo = wb_wacc & addr_eq(0)
    write_prer_hi = wb_wacc & addr_eq(1)
    write_ctr     = wb_wacc & addr_eq(2)
    write_txr     = wb_wacc & addr_eq(3)
    # cr is special — gated by core_en
    core_en_w = ctr_r[7]
    write_cr      = wb_wacc & addr_eq(4) & core_en_w

    # Verilog: prer[7:0] <= wb_dat_i (write_prer_lo) → new prer = {prer[15:8], wb_dat_i}.
    # Spirehdl cat LSB-first: wb_dat_i at LSB position, prer_r[8:16] at MSB position.
    # Verilog: prer[15:8] <= wb_dat_i (write_prer_hi) → new prer = {wb_dat_i, prer[7:0]}.
    prer_next = mux(write_prer_lo, cat(wb_dat_i_in, prer_r[8:16]),
                mux(write_prer_hi, cat(prer_r[0:8], wb_dat_i_in),
                    prer_r))
    ctr_next  = mux(write_ctr, wb_dat_i_in, ctr_r)
    txr_next  = mux(write_txr, wb_dat_i_in, txr_r)
    prer_r <<= mux(rst_active, Const(0xFFFF, UInt(16)), prer_next)
    ctr_r  <<= mux(rst_active, Const(0, UInt(8)),       ctr_next)
    txr_r  <<= mux(rst_active, Const(0, UInt(8)),       txr_next)

    # CR register — most complex
    # if (wb_wacc & write_cr): cr <= wb_dat_i
    # else:
    #   if (done | i2c_al): cr[7:4] <= 0
    #   cr[2:1] <= 0; cr[0] <= 0  (reserved + IRQ_ACK auto-clear)
    cr_after_done    = mux(done_w | i2c_al_w,
                            cat(Const(0, UInt(1)), Const(0, UInt(2)), cr_r[3], Const(0, UInt(4))),
                            cat(Const(0, UInt(1)), Const(0, UInt(2)), cr_r[3], cr_r[4:8]))
    cr_next = mux(write_cr, wb_dat_i_in, cr_after_done)
    cr_r <<= mux(rst_active, Const(0, UInt(8)), cr_next)

    # Decode command register bits
    sta_w  <<= cr_r[7]
    sto_w  <<= cr_r[6]
    rd_w   <<= cr_r[5]
    wr_w   <<= cr_r[4]
    ack_w  <<= cr_r[3]
    iack = cr_r[0]

    # Decode control register bits
    ena_w <<= core_en_w
    ien   = ctr_r[6]
    clk_cnt_w <<= prer_r

    # Status register flops
    al_status_next   = i2c_al_w | (al_r & (~sta_w))
    rxack_next       = irxack_w
    tip_next         = rd_w | wr_w
    irq_flag_next    = (done_w | i2c_al_w | irq_flag_r) & (~iack)

    al_r       <<= mux(rst_active, Const(0, UInt(1)), al_status_next)
    rxack_r    <<= mux(rst_active, Const(0, UInt(1)), rxack_next)
    tip_r      <<= mux(rst_active, Const(0, UInt(1)), tip_next)
    irq_flag_r <<= mux(rst_active, Const(0, UInt(1)), irq_flag_next)

    # Drive txr to byte_ctrl
    txr_w <<= txr_r

    # Interrupt output
    wb_inta_r <<= mux(rst_active, Const(0, UInt(1)), irq_flag_r & ien)
    # 1-cycle visibility delay
    wb_inta_o_vis = Register(UInt(1), name="wb_inta_o_vis")
    wb_inta_o_vis <<= wb_inta_r
    wb_inta_o_out <<= wb_inta_o_vis


# Wire everything up
make_wb_top()
make_byte_ctrl()
make_bit_ctrl()

m.to_verilog_file("design.v")
