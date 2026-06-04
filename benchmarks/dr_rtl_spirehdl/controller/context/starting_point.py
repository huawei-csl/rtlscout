"""SpireHDL port of `controller` — AES control unit FSM (545 LOC, 1 module).

The control unit is a 16-state FSM that orchestrates AES round operations
for ECB/CBC/CTR modes with encryption/decryption/key-derivation. Per cycle,
it emits ~14 control outputs (sbox_sel, rk_sel, col_sel, col_en, key_en,
etc.) selected by the current state.

Reset semantics: `always @(posedge clk, negedge rst_n)` — async active-low
rst_n. Standard `with_reset=False` + `mux(rst_active, init, next)` pattern.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Register, Wire, Const, mux

m = Module("control_unit", with_clock=True, with_reset=False)

# ============================================================================
# Top-level ports
# ============================================================================
operation_mode_in  = m.input(UInt(2), "operation_mode")
aes_mode_in        = m.input(UInt(2), "aes_mode")
start_in           = m.input(UInt(1), "start")
disable_core_in    = m.input(UInt(1), "disable_core")
rst_n_in           = m.input(UInt(1), "rst_n")

sbox_sel_out          = m.output(UInt(3), "sbox_sel")
rk_sel_out            = m.output(UInt(2), "rk_sel")
key_out_sel_out       = m.output(UInt(2), "key_out_sel")
col_sel_out           = m.output(UInt(2), "col_sel")
key_en_out            = m.output(UInt(4), "key_en")
col_en_out            = m.output(UInt(4), "col_en")
round_out             = m.output(UInt(4), "round")
bypass_rk_out         = m.output(UInt(1), "bypass_rk")
bypass_key_en_out     = m.output(UInt(1), "bypass_key_en")
key_sel_out           = m.output(UInt(1), "key_sel")
iv_cnt_en_out         = m.output(UInt(1), "iv_cnt_en")
iv_cnt_sel_out        = m.output(UInt(1), "iv_cnt_sel")
key_derivation_en_out = m.output(UInt(1), "key_derivation_en")
end_comp_out          = m.output(UInt(1), "end_comp")
key_init_out          = m.output(UInt(1), "key_init")
key_gen_out           = m.output(UInt(1), "key_gen")
mode_ctr_out          = m.output(UInt(1), "mode_ctr")
mode_cbc_out          = m.output(UInt(1), "mode_cbc")
last_round_out        = m.output(UInt(1), "last_round")
encrypt_decrypt_out   = m.output(UInt(1), "encrypt_decrypt")

# Async active-low reset → combine into active-high rst_active
rst_active = Wire(UInt(1), name="rst_active"); rst_active <<= ~rst_n_in

# ============================================================================
# Localparams (verbatim from verilog)
# ============================================================================
# operation_mode
ENCRYPTION     = 0b00
KEY_DERIVATION = 0b01
DECRYPTION     = 0b10
DECRYP_W_DERIV = 0b11

# aes_mode
ECB = 0b00
CBC = 0b01
CTR = 0b10

# sbox_sel
COL_0      = 0b000
COL_1      = 0b001
COL_2      = 0b010
COL_3      = 0b011
G_FUNCTION = 0b100

# rk_sel
COL_RK      = 0b00      # localparam COL = 2'b00 in verilog
MIXCOL_IN   = 0b01
MIXCOL_OUT  = 0b10

# key_out_sel / key_sel_rd
KEY_0 = 0b00
KEY_1 = 0b01
KEY_2 = 0b10
KEY_3 = 0b11

# col_sel
SHIFT_ROWS = 0b00
ADD_RK_OUT = 0b01
INPUT_SEL  = 0b10   # localparam INPUT = 2'b10

# key_sel
KEY_HOST = 0b0
KEY_OUT  = 0b1

# key_en (4-bit one-hot)
KEY_DIS  = 0b0000
EN_KEY_0 = 0b0001
EN_KEY_1 = 0b0010
EN_KEY_2 = 0b0100
EN_KEY_3 = 0b1000
KEY_ALL  = 0b1111

# col_en
COL_DIS  = 0b0000
EN_COL_0 = 0b0001
EN_COL_1 = 0b0010
EN_COL_2 = 0b0100
EN_COL_3 = 0b1000
COL_ALL  = 0b1111

# iv_cnt_sel
IV_CNT = 0b1
IV_BUS = 0b0

ENABLE  = 0b1
DISABLE = 0b0

NUMBER_ROUND      = 10
NUMBER_ROUND_INC  = 11
INITIAL_ROUND     = 0

# FSM states
IDLE        = 0
ROUND0_COL0 = 1
ROUND0_COL1 = 2
ROUND0_COL2 = 3
ROUND0_COL3 = 4
ROUND_KEY0  = 5
ROUND_COL0  = 6
ROUND_COL1  = 7
ROUND_COL2  = 8
ROUND_COL3  = 9
READY       = 10
GEN_KEY0    = 11
GEN_KEY1    = 12
GEN_KEY2    = 13
GEN_KEY3    = 14
NOP         = 15

# ============================================================================
# Sequential state register (with async active-low reset)
# ============================================================================
state_r    = Register(UInt(4), name="state")
rd_count_r = Register(UInt(4), name="rd_count")

state_w    = Wire(UInt(4), name="state_wire");    state_w    <<= state_r
rd_count_w = Wire(UInt(4), name="rd_count_wire"); rd_count_w <<= rd_count_r

# ============================================================================
# Combinational top-level signals
# ============================================================================
# op_mode = (mode_ctr) ? ENCRYPTION : operation_mode
mode_ctr_w = aes_mode_in == Const(CTR, UInt(2))
mode_cbc_w = aes_mode_in == Const(CBC, UInt(2))
op_mode = mux(mode_ctr_w, Const(ENCRYPTION, UInt(2)), operation_mode_in)
op_key_derivation = op_mode == Const(KEY_DERIVATION, UInt(2))

# encrypt_decrypt logic
state_in_genkey = ((state_w == Const(GEN_KEY0, UInt(4))) |
                   (state_w == Const(GEN_KEY1, UInt(4))) |
                   (state_w == Const(GEN_KEY2, UInt(4))) |
                   (state_w == Const(GEN_KEY3, UInt(4))))
encrypt_decrypt_w = ((op_mode == Const(ENCRYPTION, UInt(2))) |
                     (op_mode == Const(KEY_DERIVATION, UInt(2))) |
                     state_in_genkey)
enc_dec_w = encrypt_decrypt_w | mode_ctr_w
not_enc_dec = ~enc_dec_w

key_gen_w = state_w == Const(ROUND_KEY0, UInt(4))

# round counter & derived
first_round_w = rd_count_w == Const(INITIAL_ROUND, UInt(4))
last_round_w  = ((rd_count_w == Const(NUMBER_ROUND,     UInt(4))) |
                 (rd_count_w == Const(NUMBER_ROUND_INC, UInt(4))))
not_last_round = ~last_round_w

# Pre-computed intermediates (mirror verilog v0.3 optimizations)
last_round_and_enc_dec        = last_round_w & enc_dec_w
not_last_round_and_enc_dec    = not_last_round & enc_dec_w
last_round_and_mode_cbc_and_not_enc_dec = last_round_w & mode_cbc_w & not_enc_dec
last_round_and_mode_ctr       = last_round_w & mode_ctr_w
last_round_special_case       = last_round_and_mode_cbc_and_not_enc_dec | last_round_and_mode_ctr

# ============================================================================
# Next-state logic (combinational)
# ============================================================================
# Default: next_state = state.
# Use cascading mux on state, with inner cascading muxes for state-specific logic.
def _state_eq(s):
    return state_w == Const(s, UInt(4))

# IDLE: if !start: stay IDLE. Else: case(op_mode): ENC→ROUND0_COL0, DEC→ROUND0_COL3, KEY_DERIV/DECRYP_W_DERIV→GEN_KEY0
idle_dispatch = mux(op_mode == Const(ENCRYPTION,    UInt(2)), Const(ROUND0_COL0, UInt(4)),
                mux(op_mode == Const(DECRYPTION,    UInt(2)), Const(ROUND0_COL3, UInt(4)),
                mux(op_mode == Const(KEY_DERIVATION, UInt(2)), Const(GEN_KEY0,    UInt(4)),
                mux(op_mode == Const(DECRYP_W_DERIV, UInt(2)), Const(GEN_KEY0,    UInt(4)),
                                                                Const(IDLE,        UInt(4))))))
next_state_idle = mux(start_in, idle_dispatch, Const(IDLE, UInt(4)))

# ROUND0_COL0..3: ternary on enc_dec
next_state_round0_col0 = mux(enc_dec_w, Const(ROUND0_COL1, UInt(4)), Const(ROUND_KEY0,  UInt(4)))
next_state_round0_col1 = mux(enc_dec_w, Const(ROUND0_COL2, UInt(4)), Const(ROUND0_COL0, UInt(4)))
next_state_round0_col2 = mux(enc_dec_w, Const(ROUND0_COL3, UInt(4)), Const(ROUND0_COL1, UInt(4)))
next_state_round0_col3 = mux(enc_dec_w, Const(ROUND_KEY0,  UInt(4)), Const(ROUND0_COL2, UInt(4)))

# ROUND_KEY0: if !first_round: (last_round ? READY : NOP). Else: (enc_dec ? ROUND_COL0 : ROUND_COL3)
next_state_round_key0 = mux(first_round_w,
                            mux(enc_dec_w, Const(ROUND_COL0, UInt(4)), Const(ROUND_COL3, UInt(4))),
                            mux(last_round_w, Const(READY, UInt(4)), Const(NOP, UInt(4))))

# NOP: same as ROUND_KEY0's "first_round" branch
next_state_nop = mux(enc_dec_w, Const(ROUND_COL0, UInt(4)), Const(ROUND_COL3, UInt(4)))

# ROUND_COL0..2
next_state_round_col0 = mux(enc_dec_w, Const(ROUND_COL1, UInt(4)), Const(ROUND_KEY0, UInt(4)))
next_state_round_col1 = mux(enc_dec_w, Const(ROUND_COL2, UInt(4)), Const(ROUND_COL0, UInt(4)))
next_state_round_col2 = mux(enc_dec_w, Const(ROUND_COL3, UInt(4)), Const(ROUND_COL1, UInt(4)))

# ROUND_COL3: if last_round_and_enc_dec → READY; else (enc_dec ? ROUND_KEY0 : ROUND_COL2)
next_state_round_col3 = mux(last_round_and_enc_dec,
                            Const(READY, UInt(4)),
                            mux(enc_dec_w, Const(ROUND_KEY0, UInt(4)), Const(ROUND_COL2, UInt(4))))

# GEN_KEY0,1,2: → GEN_KEY1,2,3
# GEN_KEY3: if last_round: (op_key_derivation ? READY : ROUND0_COL3); else GEN_KEY0
next_state_gen_key3 = mux(last_round_w,
                          mux(op_key_derivation, Const(READY, UInt(4)), Const(ROUND0_COL3, UInt(4))),
                          Const(GEN_KEY0, UInt(4)))

# Build next_state via cascading mux on state value
next_state = mux(_state_eq(IDLE),        next_state_idle,
             mux(_state_eq(ROUND0_COL0), next_state_round0_col0,
             mux(_state_eq(ROUND0_COL1), next_state_round0_col1,
             mux(_state_eq(ROUND0_COL2), next_state_round0_col2,
             mux(_state_eq(ROUND0_COL3), next_state_round0_col3,
             mux(_state_eq(ROUND_KEY0),  next_state_round_key0,
             mux(_state_eq(NOP),         next_state_nop,
             mux(_state_eq(ROUND_COL0),  next_state_round_col0,
             mux(_state_eq(ROUND_COL1),  next_state_round_col1,
             mux(_state_eq(ROUND_COL2),  next_state_round_col2,
             mux(_state_eq(ROUND_COL3),  next_state_round_col3,
             mux(_state_eq(GEN_KEY0),    Const(GEN_KEY1, UInt(4)),
             mux(_state_eq(GEN_KEY1),    Const(GEN_KEY2, UInt(4)),
             mux(_state_eq(GEN_KEY2),    Const(GEN_KEY3, UInt(4)),
             mux(_state_eq(GEN_KEY3),    next_state_gen_key3,
             mux(_state_eq(READY),       Const(IDLE, UInt(4)),
                                          state_w)))))))))))))))) # default: hold

# State register update
state_r <<= mux(rst_active, Const(IDLE, UInt(4)),
            mux(disable_core_in, Const(IDLE, UInt(4)), next_state))

# ============================================================================
# Output logic (combinational, large case on state with defaults)
#
# Verilog defaults at top of always block:
#   sbox_sel=COL_0, rk_sel=COL, bypass_rk=DIS, key_out_sel=KEY_0,
#   col_sel=INPUT, key_sel=KEY_HOST, key_en=KEY_DIS, col_en=COL_DIS,
#   rd_count_en=DIS, iv_cnt_en=DIS, iv_cnt_sel=IV_BUS, bypass_key_en=DIS,
#   key_derivation_en=DIS
# Then each case overrides specific signals.
# ============================================================================

# Defaults
d_sbox_sel      = Const(COL_0,    UInt(3))
d_rk_sel        = Const(COL_RK,   UInt(2))
d_bypass_rk     = Const(DISABLE,  UInt(1))
d_key_out_sel   = Const(KEY_0,    UInt(2))
d_col_sel       = Const(INPUT_SEL, UInt(2))
d_key_sel       = Const(KEY_HOST, UInt(1))
d_key_en        = Const(KEY_DIS,  UInt(4))
d_col_en        = Const(COL_DIS,  UInt(4))
d_rd_count_en   = Const(DISABLE,  UInt(1))
d_iv_cnt_en     = Const(DISABLE,  UInt(1))
d_iv_cnt_sel    = Const(IV_BUS,   UInt(1))
d_bypass_key_en = Const(DISABLE,  UInt(1))
d_key_deriv_en  = Const(DISABLE,  UInt(1))


def out_per_state():
    """Return a dict state_value -> dict of {output_name: spirehdl wire}.

    Each state's dict only contains the signals that the state OVERRIDES.
    Signals not in the dict default to their defaults above.
    """
    # ROUND0_COL0
    r0c0 = {
        'sbox_sel':       Const(COL_0, UInt(3)),
        'rk_sel':         Const(COL_RK, UInt(2)),
        'bypass_rk':      Const(ENABLE, UInt(1)),
        'bypass_key_en':  Const(ENABLE, UInt(1)),
        'key_out_sel':    Const(KEY_0, UInt(2)),
        'col_sel':        mux(enc_dec_w, Const(ADD_RK_OUT, UInt(2)), Const(SHIFT_ROWS, UInt(2))),
        'col_en':         mux(enc_dec_w, Const(EN_COL_0, UInt(4)), Const(COL_ALL, UInt(4))),
    }
    # ROUND0_COL1
    r0c1_inner_key_sel = mux(not_enc_dec, Const(KEY_OUT, UInt(1)), Const(KEY_HOST, UInt(1)))
    r0c1_inner_key_en  = mux(not_enc_dec, Const(EN_KEY_1, UInt(4)), Const(KEY_DIS, UInt(4)))
    r0c1 = {
        'sbox_sel':       Const(COL_1, UInt(3)),
        'rk_sel':         Const(COL_RK, UInt(2)),
        'bypass_rk':      Const(ENABLE, UInt(1)),
        'bypass_key_en':  Const(ENABLE, UInt(1)),
        'key_out_sel':    Const(KEY_1, UInt(2)),
        'col_sel':        Const(ADD_RK_OUT, UInt(2)),
        'col_en':         Const(EN_COL_1, UInt(4)),
        'key_sel':        r0c1_inner_key_sel,
        'key_en':         r0c1_inner_key_en,
    }
    # ROUND0_COL2
    r0c2_inner_key_sel = mux(not_enc_dec, Const(KEY_OUT, UInt(1)), Const(KEY_HOST, UInt(1)))
    r0c2_inner_key_en  = mux(not_enc_dec, Const(EN_KEY_2, UInt(4)), Const(KEY_DIS, UInt(4)))
    r0c2 = {
        'sbox_sel':       Const(COL_2, UInt(3)),
        'rk_sel':         Const(COL_RK, UInt(2)),
        'bypass_rk':      Const(ENABLE, UInt(1)),
        'bypass_key_en':  Const(ENABLE, UInt(1)),
        'key_out_sel':    Const(KEY_2, UInt(2)),
        'col_sel':        Const(ADD_RK_OUT, UInt(2)),
        'col_en':         Const(EN_COL_2, UInt(4)),
        'key_sel':        r0c2_inner_key_sel,
        'key_en':         r0c2_inner_key_en,
    }
    # ROUND0_COL3
    r0c3_inner_key_sel = mux(not_enc_dec, Const(KEY_OUT, UInt(1)), Const(KEY_HOST, UInt(1)))
    r0c3_inner_key_en  = mux(not_enc_dec, Const(EN_KEY_3, UInt(4)), Const(KEY_DIS, UInt(4)))
    r0c3 = {
        'sbox_sel':       Const(COL_3, UInt(3)),
        'rk_sel':         Const(COL_RK, UInt(2)),
        'bypass_key_en':  Const(ENABLE, UInt(1)),
        'key_out_sel':    Const(KEY_3, UInt(2)),
        'col_sel':        mux(enc_dec_w, Const(SHIFT_ROWS, UInt(2)), Const(ADD_RK_OUT, UInt(2))),
        'col_en':         mux(enc_dec_w, Const(COL_ALL, UInt(4)), Const(EN_COL_3, UInt(4))),
        'bypass_rk':      Const(ENABLE, UInt(1)),
        'key_sel':        r0c3_inner_key_sel,
        'key_en':         r0c3_inner_key_en,
    }
    # ROUND_KEY0
    rk0 = {
        'sbox_sel':     Const(G_FUNCTION, UInt(3)),
        'key_sel':      Const(KEY_OUT, UInt(1)),
        'key_en':       Const(EN_KEY_0, UInt(4)),
        'rd_count_en':  Const(ENABLE, UInt(1)),
    }
    # ROUND_COL0
    rc0_col_sel = mux(last_round_special_case, Const(INPUT_SEL, UInt(2)),
                  mux(not_enc_dec,
                      mux(last_round_w, Const(ADD_RK_OUT, UInt(2)), Const(SHIFT_ROWS, UInt(2))),
                      Const(ADD_RK_OUT, UInt(2))))
    rc0_col_en  = mux(enc_dec_w, Const(EN_COL_0, UInt(4)),
                      mux(last_round_w, Const(EN_COL_0, UInt(4)), Const(COL_ALL, UInt(4))))
    rc0_key_en  = mux(enc_dec_w, Const(EN_KEY_1, UInt(4)), Const(KEY_DIS, UInt(4)))
    rc0 = {
        'sbox_sel':    Const(COL_0, UInt(3)),
        'rk_sel':      mux(last_round_w, Const(MIXCOL_IN, UInt(2)), Const(MIXCOL_OUT, UInt(2))),
        'key_out_sel': Const(KEY_0, UInt(2)),
        'key_sel':     Const(KEY_OUT, UInt(1)),
        'key_en':      rc0_key_en,
        'col_sel':     rc0_col_sel,
        'col_en':      rc0_col_en,
    }
    # ROUND_COL1
    rc1_col_sel = mux(last_round_special_case, Const(INPUT_SEL, UInt(2)), Const(ADD_RK_OUT, UInt(2)))
    rc1_key_en  = mux(enc_dec_w, Const(EN_KEY_2, UInt(4)), Const(EN_KEY_1, UInt(4)))
    rc1 = {
        'sbox_sel':    Const(COL_1, UInt(3)),
        'rk_sel':      mux(last_round_w, Const(MIXCOL_IN, UInt(2)), Const(MIXCOL_OUT, UInt(2))),
        'key_out_sel': Const(KEY_1, UInt(2)),
        'key_sel':     Const(KEY_OUT, UInt(1)),
        'key_en':      rc1_key_en,
        'col_sel':     rc1_col_sel,
        'col_en':      Const(EN_COL_1, UInt(4)),
    }
    # ROUND_COL2
    rc2_col_sel = mux(last_round_special_case, Const(INPUT_SEL, UInt(2)), Const(ADD_RK_OUT, UInt(2)))
    rc2_key_en  = mux(enc_dec_w, Const(EN_KEY_3, UInt(4)), Const(EN_KEY_2, UInt(4)))
    rc2 = {
        'sbox_sel':    Const(COL_2, UInt(3)),
        'rk_sel':      mux(last_round_w, Const(MIXCOL_IN, UInt(2)), Const(MIXCOL_OUT, UInt(2))),
        'key_out_sel': Const(KEY_2, UInt(2)),
        'key_sel':     Const(KEY_OUT, UInt(1)),
        'key_en':      rc2_key_en,
        'col_sel':     rc2_col_sel,
        'col_en':      Const(EN_COL_2, UInt(4)),
    }
    # ROUND_COL3
    rc3_key_en  = mux(not_enc_dec, Const(EN_KEY_3, UInt(4)), Const(KEY_DIS, UInt(4)))
    rc3_col_sel_else = mux(enc_dec_w,
                           mux(last_round_w, Const(ADD_RK_OUT, UInt(2)), Const(SHIFT_ROWS, UInt(2))),
                           Const(ADD_RK_OUT, UInt(2)))
    rc3_col_sel = mux(last_round_special_case, Const(INPUT_SEL, UInt(2)), rc3_col_sel_else)
    rc3_col_en  = mux(enc_dec_w,
                      mux(last_round_w, Const(EN_COL_3, UInt(4)), Const(COL_ALL, UInt(4))),
                      Const(EN_COL_3, UInt(4)))
    rc3_iv_cnt_en  = mux(last_round_and_mode_ctr, Const(ENABLE, UInt(1)), Const(DISABLE, UInt(1)))
    rc3_iv_cnt_sel = mux(last_round_and_mode_ctr, Const(IV_CNT, UInt(1)), Const(IV_BUS, UInt(1)))
    rc3 = {
        'sbox_sel':    Const(COL_3, UInt(3)),
        'rk_sel':      mux(last_round_w, Const(MIXCOL_IN, UInt(2)), Const(MIXCOL_OUT, UInt(2))),
        'key_out_sel': Const(KEY_3, UInt(2)),
        'key_sel':     Const(KEY_OUT, UInt(1)),
        'key_en':      rc3_key_en,
        'col_sel':     rc3_col_sel,
        'col_en':      rc3_col_en,
        'iv_cnt_en':   rc3_iv_cnt_en,
        'iv_cnt_sel':  rc3_iv_cnt_sel,
    }
    # GEN_KEY0
    gk0 = {
        'sbox_sel':    Const(G_FUNCTION, UInt(3)),
        'rd_count_en': Const(ENABLE, UInt(1)),
    }
    # GEN_KEY1
    gk1 = {
        'key_en':        Const(EN_KEY_1 | EN_KEY_0, UInt(4)),
        'key_sel':       Const(KEY_OUT, UInt(1)),
        'bypass_key_en': Const(ENABLE, UInt(1)),
    }
    # GEN_KEY2
    gk2 = {
        'key_en':        Const(EN_KEY_2, UInt(4)),
        'key_sel':       Const(KEY_OUT, UInt(1)),
        'bypass_key_en': Const(ENABLE, UInt(1)),
    }
    # GEN_KEY3
    gk3 = {
        'key_en':        Const(EN_KEY_3, UInt(4)),
        'key_sel':       Const(KEY_OUT, UInt(1)),
        'bypass_key_en': Const(ENABLE, UInt(1)),
    }
    # READY
    ready_kd_en = mux(op_mode == Const(KEY_DERIVATION, UInt(2)),
                      Const(ENABLE, UInt(1)), Const(DISABLE, UInt(1)))
    ready = {
        'key_derivation_en': ready_kd_en,
    }

    return {
        ROUND0_COL0: r0c0, ROUND0_COL1: r0c1, ROUND0_COL2: r0c2, ROUND0_COL3: r0c3,
        ROUND_KEY0:  rk0,
        ROUND_COL0:  rc0,  ROUND_COL1:  rc1,  ROUND_COL2:  rc2,  ROUND_COL3:  rc3,
        GEN_KEY0:    gk0,  GEN_KEY1:    gk1,  GEN_KEY2:    gk2,  GEN_KEY3:    gk3,
        READY:       ready,
    }


_per_state = out_per_state()
_signal_names = ['sbox_sel', 'rk_sel', 'bypass_rk', 'key_out_sel', 'col_sel',
                 'key_sel', 'key_en', 'col_en', 'rd_count_en', 'iv_cnt_en',
                 'iv_cnt_sel', 'bypass_key_en', 'key_derivation_en']
_defaults = {
    'sbox_sel': d_sbox_sel, 'rk_sel': d_rk_sel, 'bypass_rk': d_bypass_rk,
    'key_out_sel': d_key_out_sel, 'col_sel': d_col_sel, 'key_sel': d_key_sel,
    'key_en': d_key_en, 'col_en': d_col_en, 'rd_count_en': d_rd_count_en,
    'iv_cnt_en': d_iv_cnt_en, 'iv_cnt_sel': d_iv_cnt_sel,
    'bypass_key_en': d_bypass_key_en, 'key_derivation_en': d_key_deriv_en,
}


def _select(signal_name):
    """Build a mux cascade selecting `signal_name` based on state value."""
    out = _defaults[signal_name]
    # Iterate in reverse so the innermost mux is the highest state value.
    for sv, overrides in sorted(_per_state.items()):
        if signal_name in overrides:
            out = mux(_state_eq(sv), overrides[signal_name], out)
    return out


sbox_sel_w        = _select('sbox_sel')
rk_sel_w          = _select('rk_sel')
bypass_rk_w       = _select('bypass_rk')
key_out_sel_w     = _select('key_out_sel')
col_sel_w         = _select('col_sel')
key_sel_w         = _select('key_sel')
key_en_w          = _select('key_en')
col_en_w          = _select('col_en')
rd_count_en_w     = _select('rd_count_en')
iv_cnt_en_w       = _select('iv_cnt_en')
iv_cnt_sel_w      = _select('iv_cnt_sel')
bypass_key_en_w   = _select('bypass_key_en')
key_derivation_en_w = _select('key_derivation_en')

# ============================================================================
# Round counter
# ============================================================================
# if (state == IDLE || (state == GEN_KEY3 && last_round)): rd_count = INITIAL_ROUND
# else if (rd_count_en): rd_count <= rd_count + 1
# else: hold
rd_count_clear = _state_eq(IDLE) | (_state_eq(GEN_KEY3) & last_round_w)
rd_count_inc   = (rd_count_r + Const(1, UInt(1)))[0:4]
rd_count_next  = mux(rd_count_clear, Const(INITIAL_ROUND, UInt(4)),
                 mux(rd_count_en_w, rd_count_inc, rd_count_r))
rd_count_r <<= mux(rst_active, Const(INITIAL_ROUND, UInt(4)), rd_count_next)

# ============================================================================
# Output assignments
# ============================================================================
sbox_sel_out          <<= sbox_sel_w
rk_sel_out            <<= rk_sel_w
key_out_sel_out       <<= key_out_sel_w
col_sel_out           <<= col_sel_w
key_en_out            <<= key_en_w
col_en_out            <<= col_en_w
round_out             <<= rd_count_w
bypass_rk_out         <<= bypass_rk_w
bypass_key_en_out     <<= bypass_key_en_w
key_sel_out           <<= key_sel_w
iv_cnt_en_out         <<= iv_cnt_en_w
iv_cnt_sel_out        <<= iv_cnt_sel_w
key_derivation_en_out <<= key_derivation_en_w
end_comp_out          <<= mux(_state_eq(READY), Const(ENABLE, UInt(1)), Const(DISABLE, UInt(1)))
key_init_out          <<= start_in
key_gen_out           <<= key_gen_w
mode_ctr_out          <<= mode_ctr_w
mode_cbc_out          <<= mode_cbc_w
last_round_out        <<= last_round_w
encrypt_decrypt_out   <<= encrypt_decrypt_w

m.to_verilog_file("design.v")
