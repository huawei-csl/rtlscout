"""SpireHDL port of `router_top` — 3-channel packet router with FIFO subchannels.

Mirrors rtl_dataset/router.v0.v's 5 submodules (router_top, router_sync,
router_fsm, router_fifo×3, router_reg) inlined into a single SpireHDL
`Module`. The flat netlist is functionally equivalent to the
hierarchical verilog after `flatten`; submodule names disappear but
internal signal names are preserved for debuggability.

Reset semantics: every flop in the verilog is `if(!resetn) ... else ...`
inside `always @(posedge clk)` — synchronous active-low. So:
`with_reset=False`, `resetn` as a regular input, and every register
written as `r <<= mux(~resetn, init, next_val)`.

Submodule layout (each inlined as a Python helper):
  1. router_reg — header-byte hold, parity tracking, dout, err
  2. router_fsm — 8-state main FSM, outputs derived from present_state
  3. router_sync — channel-select temp + 3 soft-reset counters
  4. router_fifo (×3) — 16-entry × 9-bit FIFO with rd/wr pointers

Signal flow (matches verilog router_top instantiations):
  - datain[7:0] → router_reg → dout → router_fifo[*].datain
  - datain[1:0] (channel select) → router_fsm + router_sync
  - router_fifo[i].full → router_sync.full_<i>; muxed by sync.temp into fsm.fifo_full
  - router_fifo[i].empty → router_sync.empty_<i> AND router_fsm.fifo_empty_<i>
  - router_sync.write_enb[i] → router_fifo[i].write_enb
  - top.read_enb_<i> → router_fifo[i].read_enb
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Register, Wire, Const, mux, cat

m = Module("router_top", with_clock=True, with_reset=False)

# === Top-level ports ===
resetn       = m.input(UInt(1), "resetn")
packet_valid = m.input(UInt(1), "packet_valid")
read_enb_0   = m.input(UInt(1), "read_enb_0")
read_enb_1   = m.input(UInt(1), "read_enb_1")
read_enb_2   = m.input(UInt(1), "read_enb_2")
datain       = m.input(UInt(8), "datain")

vldout_0     = m.output(UInt(1), "vldout_0")
vldout_1     = m.output(UInt(1), "vldout_1")
vldout_2     = m.output(UInt(1), "vldout_2")
err_out      = m.output(UInt(1), "err")
busy_out     = m.output(UInt(1), "busy")
data_out_0   = m.output(UInt(8), "data_out_0")
data_out_1   = m.output(UInt(8), "data_out_1")
data_out_2   = m.output(UInt(8), "data_out_2")

# Convenience: ~resetn used everywhere as the reset-active signal
rstn_inv = Wire(UInt(1), name="rstn_inv"); rstn_inv <<= ~resetn

# ---------------------------------------------------------------------------
# Forward-declare cross-module wires so the submodules can hand off signals.
# The verilog router_top wires these between submodules via `wire` decls;
# we declare them up-front here so each helper can assign into them.
# ---------------------------------------------------------------------------
# FSM ↔ everywhere
detect_add    = Wire(UInt(1), name="detect_add")
ld_state      = Wire(UInt(1), name="ld_state")
laf_state     = Wire(UInt(1), name="laf_state")
lfd_state     = Wire(UInt(1), name="lfd_state")
full_state    = Wire(UInt(1), name="full_state")
rst_int_reg   = Wire(UInt(1), name="rst_int_reg")
write_enb_reg = Wire(UInt(1), name="write_enb_reg")
fifo_full     = Wire(UInt(1), name="fifo_full")

# REG outputs
dout             = Wire(UInt(8), name="dout")
parity_done      = Wire(UInt(1), name="parity_done")
low_packet_valid = Wire(UInt(1), name="low_packet_valid")

# SYNC outputs (per-channel)
w_enb_0      = Wire(UInt(1), name="w_enb_0")
w_enb_1      = Wire(UInt(1), name="w_enb_1")
w_enb_2      = Wire(UInt(1), name="w_enb_2")
soft_reset_0 = Wire(UInt(1), name="soft_reset_0")
soft_reset_1 = Wire(UInt(1), name="soft_reset_1")
soft_reset_2 = Wire(UInt(1), name="soft_reset_2")

# FIFO outputs (per-channel)
fifo_full_0  = Wire(UInt(1), name="fifo_full_0")
fifo_full_1  = Wire(UInt(1), name="fifo_full_1")
fifo_full_2  = Wire(UInt(1), name="fifo_full_2")
fifo_empty_0 = Wire(UInt(1), name="fifo_empty_0")
fifo_empty_1 = Wire(UInt(1), name="fifo_empty_1")
fifo_empty_2 = Wire(UInt(1), name="fifo_empty_2")


# ===========================================================================
# router_reg — header-byte hold, parity tracking, dout, err
# ===========================================================================
def make_router_reg():
    """Mirrors verilog module `router_reg` (lines 481-594)."""
    global dout, parity_done, low_packet_valid
    hold_header_byte     = Register(UInt(8), name="hold_header_byte")
    fifo_full_state_byte = Register(UInt(8), name="fifo_full_state_byte")
    internal_parity      = Register(UInt(8), name="internal_parity")
    packet_parity_byte   = Register(UInt(8), name="packet_parity_byte")
    parity_done_r        = Register(UInt(1), name="parity_done_r")
    low_packet_valid_r   = Register(UInt(1), name="low_packet_valid_r")
    dout_r               = Register(UInt(8), name="dout_r")
    err_r                = Register(UInt(1), name="err_r")

    # --- parity_done ---
    # if(!resetn) → 0
    # else if(ld_state && !fifo_full && !packet_valid) → 1
    # else if(laf_state && low_packet_valid && !parity_done) → 1
    # else if(detect_add) → 0
    # else (hold)
    pd_set_1   = (ld_state & ~fifo_full & ~packet_valid) | \
                 (laf_state & low_packet_valid_r & ~parity_done_r)
    pd_set_0   = detect_add  # only takes effect if pd_set_1 didn't fire
    pd_next    = mux(pd_set_1, Const(1, UInt(1)),
                  mux(pd_set_0, Const(0, UInt(1)),
                      parity_done_r))
    parity_done_r <<= mux(rstn_inv, Const(0, UInt(1)), pd_next)

    # --- low_packet_valid ---
    # if(!resetn) → 0
    # else if(rst_int_reg) → 0
    # then (overlay) if(ld_state && !packet_valid) → 1
    # Note: verilog writes both in sequence — both fire in one cycle, last wins.
    lpv_after_rst = mux(rst_int_reg, Const(0, UInt(1)), low_packet_valid_r)
    lpv_next      = mux(ld_state & ~packet_valid, Const(1, UInt(1)), lpv_after_rst)
    low_packet_valid_r <<= mux(rstn_inv, Const(0, UInt(1)), lpv_next)

    # --- hold_header_byte ---
    # if(!resetn) → 0 (implicit by init; verilog doesn't reset it explicitly)
    # else if(detect_add && packet_valid) → datain
    hold_next = mux(detect_add & packet_valid, datain, hold_header_byte)
    hold_header_byte <<= mux(rstn_inv, Const(0, UInt(8)), hold_next)

    # --- fifo_full_state_byte ---
    # only updates when ld_state && fifo_full
    ffsb_next = mux(ld_state & fifo_full, datain, fifo_full_state_byte)
    fifo_full_state_byte <<= mux(rstn_inv, Const(0, UInt(8)), ffsb_next)

    # --- dout ---
    # if(!resetn) → 0
    # else if(detect_add && packet_valid) → hold_header_byte sample (but the
    #   verilog actually writes hold_header_byte<=datain in that branch; dout
    #   only updates in subsequent branches)
    # else if(lfd_state) → hold_header_byte
    # else if(ld_state && !fifo_full) → datain
    # else if(ld_state && fifo_full) → fifo_full_state_byte (no, that writes to ffsb)
    # else if(laf_state) → fifo_full_state_byte
    # else: hold
    dout_next = mux(lfd_state, hold_header_byte,
                mux(ld_state & ~fifo_full, datain,
                mux(laf_state, fifo_full_state_byte,
                    dout_r)))
    dout_r <<= mux(rstn_inv, Const(0, UInt(8)), dout_next)

    # --- internal_parity ---
    # if(!resetn) → 0
    # else if(lfd_state) → internal_parity ^ hold_header_byte
    # else if(ld_state && packet_valid && !full_state) → internal_parity ^ datain
    # else if(detect_add) → 0
    # else: hold
    ip_next = mux(lfd_state, internal_parity ^ hold_header_byte,
              mux(ld_state & packet_valid & ~full_state, internal_parity ^ datain,
              mux(detect_add, Const(0, UInt(8)),
                  internal_parity)))
    internal_parity <<= mux(rstn_inv, Const(0, UInt(8)), ip_next)

    # --- packet_parity_byte ---
    # if(!resetn) → 0
    # else if(!packet_valid && ld_state) → datain
    ppb_next = mux(~packet_valid & ld_state, datain, packet_parity_byte)
    packet_parity_byte <<= mux(rstn_inv, Const(0, UInt(8)), ppb_next)

    # --- err ---
    # if(!resetn) → 0
    # else if(parity_done) → (internal_parity != packet_parity_byte) ? 1 : 0
    # else: hold
    err_when_pd = mux(internal_parity != packet_parity_byte, Const(1, UInt(1)), Const(0, UInt(1)))
    err_next    = mux(parity_done_r, err_when_pd, err_r)
    err_r <<= mux(rstn_inv, Const(0, UInt(1)), err_next)

    # Drive cross-module wires
    dout             <<= dout_r
    parity_done      <<= parity_done_r
    low_packet_valid <<= low_packet_valid_r
    return err_r


# ===========================================================================
# router_fsm — 8-state FSM (binary encoding)
# ===========================================================================
def make_router_fsm():
    """Mirrors verilog module `router_fsm` (lines 192-330).
    Custom binary encoding: decode_address=1, wait_till_empty=2,
    load_first_data=3, load_data=4, load_parity=5, fifo_full_state=6,
    load_after_full=7, check_parity_error=8."""
    global detect_add, ld_state, laf_state, lfd_state, full_state, rst_int_reg, write_enb_reg
    DECODE_ADDR        = 1
    WAIT_TILL_EMPTY    = 2
    LOAD_FIRST_DATA    = 3
    LOAD_DATA          = 4
    LOAD_PARITY        = 5
    FIFO_FULL_STATE    = 6
    LOAD_AFTER_FULL    = 7
    CHECK_PARITY_ERROR = 8

    present_state = Register(UInt(4), name="present_state")
    temp_fsm      = Register(UInt(2), name="temp_fsm")
    datain_lo     = Wire(UInt(2), name="datain_lo"); datain_lo <<= datain[0:2]

    # --- temp_fsm: tracks the active channel ---
    # if(~resetn) → 0
    # else if(detect_add) → datain[1:0]
    temp_next = mux(detect_add, datain_lo, temp_fsm)
    temp_fsm <<= mux(rstn_inv, Const(0, UInt(2)), temp_next)

    # --- next-state logic ---
    # decode_address
    pv = packet_valid
    is_ch0 = datain_lo == Const(0, UInt(2))
    is_ch1 = datain_lo == Const(1, UInt(2))
    is_ch2 = datain_lo == Const(2, UInt(2))
    decode_to_lfd = pv & ((is_ch0 & fifo_empty_0) | (is_ch1 & fifo_empty_1) | (is_ch2 & fifo_empty_2))
    decode_to_wte = pv & ((is_ch0 & ~fifo_empty_0) | (is_ch1 & ~fifo_empty_1) | (is_ch2 & ~fifo_empty_2))
    ns_decode = mux(decode_to_lfd, Const(LOAD_FIRST_DATA, UInt(4)),
                mux(decode_to_wte, Const(WAIT_TILL_EMPTY, UInt(4)),
                    Const(DECODE_ADDR, UInt(4))))

    # wait_till_empty
    is_tch0 = temp_fsm == Const(0, UInt(2))
    is_tch1 = temp_fsm == Const(1, UInt(2))
    is_tch2 = temp_fsm == Const(2, UInt(2))
    wte_to_lfd = (fifo_empty_0 & is_tch0) | (fifo_empty_1 & is_tch1) | (fifo_empty_2 & is_tch2)
    ns_wte = mux(wte_to_lfd, Const(LOAD_FIRST_DATA, UInt(4)), Const(WAIT_TILL_EMPTY, UInt(4)))

    # load_first_data → load_data
    ns_lfd = Const(LOAD_DATA, UInt(4))

    # load_data: full→fifo_full_state; else if !full && !packet_valid → load_parity; else → stay
    ns_ld = mux(fifo_full, Const(FIFO_FULL_STATE, UInt(4)),
            mux(~packet_valid, Const(LOAD_PARITY, UInt(4)),
                Const(LOAD_DATA, UInt(4))))

    # fifo_full_state: !full → load_after_full; else stay
    ns_ffs = mux(~fifo_full, Const(LOAD_AFTER_FULL, UInt(4)), Const(FIFO_FULL_STATE, UInt(4)))

    # load_after_full: priority cascade (verilog uses if/else if/else if)
    # if (!parity_done && low_packet_valid) → load_parity
    # else if (!parity_done && !low_packet_valid) → load_data
    # else if (parity_done == 1) → decode_address
    # else → load_after_full
    ns_laf = mux(~parity_done & low_packet_valid, Const(LOAD_PARITY, UInt(4)),
             mux(~parity_done & ~low_packet_valid, Const(LOAD_DATA, UInt(4)),
             mux(parity_done, Const(DECODE_ADDR, UInt(4)),
                 Const(LOAD_AFTER_FULL, UInt(4)))))

    # load_parity → check_parity_error
    ns_lp = Const(CHECK_PARITY_ERROR, UInt(4))

    # check_parity_error: !full → decode_address; else → fifo_full_state
    ns_cpe = mux(~fifo_full, Const(DECODE_ADDR, UInt(4)), Const(FIFO_FULL_STATE, UInt(4)))

    next_state = Wire(UInt(4), name="next_state")
    next_state <<= mux(present_state == Const(DECODE_ADDR, UInt(4)),        ns_decode,
                  mux(present_state == Const(WAIT_TILL_EMPTY, UInt(4)),     ns_wte,
                  mux(present_state == Const(LOAD_FIRST_DATA, UInt(4)),     ns_lfd,
                  mux(present_state == Const(LOAD_DATA, UInt(4)),           ns_ld,
                  mux(present_state == Const(LOAD_PARITY, UInt(4)),         ns_lp,
                  mux(present_state == Const(FIFO_FULL_STATE, UInt(4)),     ns_ffs,
                  mux(present_state == Const(LOAD_AFTER_FULL, UInt(4)),     ns_laf,
                  mux(present_state == Const(CHECK_PARITY_ERROR, UInt(4)),  ns_cpe,
                      Const(DECODE_ADDR, UInt(4))))))))))  # default

    # present_state transition with sync reset + soft-reset early-out
    # if(!resetn) → decode_address
    # else if (soft_reset matches current channel) → decode_address
    # else → next_state
    soft_reset_match = ((soft_reset_0 & (temp_fsm == Const(0, UInt(2)))) |
                        (soft_reset_1 & (temp_fsm == Const(1, UInt(2)))) |
                        (soft_reset_2 & (temp_fsm == Const(2, UInt(2)))))
    ps_next = mux(soft_reset_match, Const(DECODE_ADDR, UInt(4)), next_state)
    present_state <<= mux(rstn_inv, Const(DECODE_ADDR, UInt(4)), ps_next)

    # --- output decoders (Moore from present_state) ---
    eq_lfd = present_state == Const(LOAD_FIRST_DATA, UInt(4))
    eq_lp  = present_state == Const(LOAD_PARITY, UInt(4))
    eq_ffs = present_state == Const(FIFO_FULL_STATE, UInt(4))
    eq_laf = present_state == Const(LOAD_AFTER_FULL, UInt(4))
    eq_wte = present_state == Const(WAIT_TILL_EMPTY, UInt(4))
    eq_cpe = present_state == Const(CHECK_PARITY_ERROR, UInt(4))
    eq_da  = present_state == Const(DECODE_ADDR, UInt(4))
    eq_ld  = present_state == Const(LOAD_DATA, UInt(4))

    busy_w = Wire(UInt(1), name="busy_w")
    busy_w <<= eq_lfd | eq_lp | eq_ffs | eq_laf | eq_wte | eq_cpe

    detect_add    <<= eq_da
    lfd_state     <<= eq_lfd
    ld_state      <<= eq_ld
    write_enb_reg <<= (eq_ld | eq_laf | eq_lp)
    full_state    <<= eq_ffs
    laf_state     <<= eq_laf
    rst_int_reg   <<= eq_cpe
    return busy_w


# ===========================================================================
# router_sync — channel-select temp + 3 soft-reset counters + write_enb decoder
# ===========================================================================
def make_router_sync():
    """Mirrors verilog module `router_sync` (lines 55-189)."""
    global w_enb_0, w_enb_1, w_enb_2
    global soft_reset_0, soft_reset_1, soft_reset_2
    global fifo_full, vldout_0, vldout_1, vldout_2
    temp_sync = Register(UInt(2), name="temp_sync")
    count0    = Register(UInt(5), name="count0")
    count1    = Register(UInt(5), name="count1")
    count2    = Register(UInt(5), name="count2")
    sreset_0_r = Register(UInt(1), name="soft_reset_0_r")
    sreset_1_r = Register(UInt(1), name="soft_reset_1_r")
    sreset_2_r = Register(UInt(1), name="soft_reset_2_r")

    datain_lo = Wire(UInt(2), name="datain_lo_sync"); datain_lo <<= datain[0:2]

    # --- temp_sync: tracks active channel ---
    # if(!resetn) → 0; else if (detect_add) → datain[1:0]
    temp_next = mux(detect_add, datain_lo, temp_sync)
    temp_sync <<= mux(rstn_inv, Const(0, UInt(2)), temp_next)

    # --- fifo_full mux based on temp_sync ---
    is_t0 = temp_sync == Const(0, UInt(2))
    is_t1 = temp_sync == Const(1, UInt(2))
    # is_t2 = "else" branch in the verilog
    fifo_full <<= mux(is_t0, fifo_full_0,
                  mux(is_t1, fifo_full_1,
                      fifo_full_2))

    # --- write_enb (per-channel) ---
    # if(write_enb_reg) { temp==0→001, temp==1→010, temp==2→100, else→000 }
    # else write_enb=000
    is_t0_we = is_t0 & write_enb_reg
    is_t1_we = is_t1 & write_enb_reg
    is_t2_we = (temp_sync == Const(2, UInt(2))) & write_enb_reg
    w_enb_0 <<= is_t0_we
    w_enb_1 <<= is_t1_we
    w_enb_2 <<= is_t2_we

    # --- vld_out_* (combinational, !empty) ---
    vldout_0 <<= ~fifo_empty_0
    vldout_1 <<= ~fifo_empty_1
    vldout_2 <<= ~fifo_empty_2

    # --- soft-reset counter for each channel ---
    # if(!resetn) count <= 0
    # else if(vld_out) { if(!read_enb) { if(count==30) {soft_reset<=1; count<=0} else count++ }
    #                    else count<=0 }
    # else count<=0
    def make_counter(count_r, sreset_r, vld_out, read_enb):
        thirty = Const(30, UInt(5))
        at_max = count_r == thirty
        cnt_incr = count_r + Const(1, UInt(5))
        # inside vld_out branch, !read_enb branch
        cnt_when_not_read = mux(at_max, Const(0, UInt(5)), cnt_incr[0:5])
        sr_when_not_read  = mux(at_max, Const(1, UInt(1)), Const(0, UInt(1)))
        # vld_out=1, read_enb=0 → cnt_when_not_read; sreset_when_not_read
        # vld_out=1, read_enb=1 → cnt=0; sreset holds previous (verilog only writes sr in the !read_enb branch)
        # vld_out=0 → cnt=0; sreset holds
        cnt_next_inner = mux(read_enb, Const(0, UInt(5)), cnt_when_not_read)
        cnt_next       = mux(vld_out,  cnt_next_inner, Const(0, UInt(5)))
        # soft_reset only updates in the (vld_out & !read_enb) branch; otherwise holds
        sr_next = mux(vld_out & ~read_enb, sr_when_not_read, sreset_r)
        count_r  <<= mux(rstn_inv, Const(0, UInt(5)), cnt_next)
        sreset_r <<= mux(rstn_inv, Const(0, UInt(1)), sr_next)

    make_counter(count0, sreset_0_r, ~fifo_empty_0, read_enb_0)
    make_counter(count1, sreset_1_r, ~fifo_empty_1, read_enb_1)
    make_counter(count2, sreset_2_r, ~fifo_empty_2, read_enb_2)

    soft_reset_0 <<= sreset_0_r
    soft_reset_1 <<= sreset_1_r
    soft_reset_2 <<= sreset_2_r


# ===========================================================================
# router_fifo — 16-entry × 9-bit FIFO with rd/wr pointers
# (instantiated 3× — one per channel)
# ===========================================================================
def make_router_fifo(idx, write_enb, read_enb):
    """Mirrors verilog module `router_fifo` (lines 332-478).
    `idx` is just for naming uniqueness across the 3 instances."""
    # 16 × 9-bit register array
    fifo = [Register(UInt(9), name=f"fifo_{idx}_{i}") for i in range(16)]
    read_ptr     = Register(UInt(4), name=f"read_ptr_{idx}")
    write_ptr    = Register(UInt(4), name=f"write_ptr_{idx}")
    count_r      = Register(UInt(6), name=f"count_{idx}")
    incrementer  = Register(UInt(5), name=f"incrementer_{idx}")
    temp_reg     = Register(UInt(1), name=f"temp_{idx}")
    full_r       = Register(UInt(1), name=f"full_r_{idx}")
    empty_r      = Register(UInt(1), name=f"empty_r_{idx}")
    dataout_r    = Register(UInt(8), name=f"dataout_r_{idx}")

    # Verilog has `if(!resetn || soft_reset)` for some flops — i.e. soft_reset
    # acts as a secondary reset that clears the FIFO contents. Combine:
    pick_idx = {0: soft_reset_0, 1: soft_reset_1, 2: soft_reset_2}
    sreset = pick_idx[idx]
    fifo_rst = rstn_inv | sreset  # either resetn-low or soft_reset clears

    # --- temp: registered lfd_state ---
    # if(!resetn) → 0; else → lfd_state
    temp_reg <<= mux(rstn_inv, Const(0, UInt(1)), lfd_state)

    # --- incrementer ---
    # combinational next:
    #   ((!full & write_enb) && (!empty & read_enb)) → incrementer (no change)
    #   (!full & write_enb)                          → incrementer + 1
    #   (!empty & read_enb)                          → incrementer - 1
    #   else                                          → incrementer
    can_write = ~full_r & write_enb
    can_read  = ~empty_r & read_enb
    incr_plus1  = (incrementer + Const(1, UInt(5)))[0:5]
    incr_minus1 = (incrementer - Const(1, UInt(5)))[0:5]
    next_incr = mux(can_write & can_read, incrementer,
                mux(can_write, incr_plus1,
                mux(can_read,  incr_minus1,
                    incrementer)))
    incrementer <<= mux(rstn_inv, Const(0, UInt(5)), next_incr)

    # --- full_d, empty_d (combinational) ---
    # Verilog: `if(incrementer == 4'b1111) full_d=1;`. The 4-bit literal is
    # *zero-extended* to 5 bits by the comparator, so full_d=1 ONLY when the
    # 5-bit incrementer equals 15 — NOT when its lower 4 bits are 1111
    # (which would also match at incrementer=31, the wrap-around value when
    # a stale `empty_r` lets a 0-1 decrement wrap to 5'b11111).
    # An earlier translation used `incrementer[0:4] == 4'b1111`, which
    # erroneously matched both 15 and 31, causing the FIFO to report full
    # spuriously after a stale-empty decrement.
    empty_d = incrementer == Const(0, UInt(5))
    full_d  = incrementer == Const(15, UInt(5))

    # --- full, empty (registered) ---
    full_r  <<= mux(rstn_inv, Const(0, UInt(1)), full_d)
    empty_r <<= mux(rstn_inv, Const(1, UInt(1)), empty_d)

    # --- pointers ---
    # The verilog uses BLOCKING (=) for write_ptr/read_ptr inside an
    # `always @(posedge clk)` block separate from the `fifo[]<=…` write
    # block (which uses NBA <=). Verilator's posedge scheduling runs the
    # blocking pointer-update block FIRST, so the fifo-write block reads
    # the *post-increment* pointer value. This is a subtle race that
    # functionally shifts every FIFO write/read by +1 (which is fine for
    # circular-buffer behavior — both pointers shift identically).
    # To match the verilog's emergent semantics we use the post-increment
    # pointer value (`wptr_next` / `rptr_next`) as the FIFO array index.
    wptr_next = mux(can_write, (write_ptr + Const(1, UInt(4)))[0:4], write_ptr)
    rptr_next = mux(can_read,  (read_ptr  + Const(1, UInt(4)))[0:4], read_ptr)
    write_ptr <<= mux(fifo_rst, Const(0, UInt(4)), wptr_next)
    read_ptr  <<= mux(fifo_rst, Const(0, UInt(4)), rptr_next)

    # --- fifo array writes (use POST-increment write_ptr) ---
    written_word = cat(dout[0:8], temp_reg)  # cat is LSB-first → emits {temp_reg, dout[7:0]}
    for i in range(16):
        write_match = (wptr_next == Const(i, UInt(4))) & can_write
        fifo[i] <<= mux(fifo_rst, Const(0, UInt(9)),
                    mux(write_match, written_word, fifo[i]))

    # --- count register (payload length tracker) ---
    # Uses POST-increment read_ptr same as fifo write (same race).
    fifo_read_word = Wire(UInt(9), name=f"fifo_read_word_{idx}")
    sel = rptr_next
    chosen = fifo[15]
    for i in reversed(range(15)):
        chosen = mux(sel == Const(i, UInt(4)), fifo[i], chosen)
    fifo_read_word <<= chosen

    # count logic:
    # if(read_enb && !empty) {
    #   if (fifo[read_ptr][8])           // header byte
    #     count <= fifo[read_ptr][7:2] + 1
    #   else if (count != 0)
    #     count <= count - 1
    # }
    is_header = fifo_read_word[8]
    # Verilog: count <= fifo[read_ptr][7:2] + 1'b1
    # fifo_read_word[2:8] is the 6-bit field bits [7:2]; +1 widens to 7 bits,
    # truncate back to 6 to match the count register width.
    # The earlier `cat(Const(0,UInt(2)), fifo_read_word[2:8])` was WRONG —
    # cat is LSB-first so the zeros went to the LSB, effectively left-shifting
    # the payload by 2 bits before the add.
    payload_len = (fifo_read_word[2:8] + Const(1, UInt(1)))[0:6]
    count_decr  = (count_r - Const(1, UInt(6)))[0:6]
    count_next  = mux(can_read,
                      mux(is_header, payload_len,
                          mux(count_r != Const(0, UInt(6)), count_decr, count_r)),
                      count_r)
    count_r <<= mux(rstn_inv, Const(0, UInt(6)), count_next)

    # --- dataout (registered output) ---
    # if(!resetn) → 0
    # else if(soft_reset) → 0
    # else {
    #   if(read_enb && !empty) dataout <= fifo[read_ptr][7:0]
    #   if(count == 0)         dataout <= 0   // verilog: this overlays the previous
    # }
    # Last write wins — verilog evaluates both `if` statements sequentially within
    # the always block, so `count==0 → dataout<=0` overrides `read+!empty → fifo[..]`.
    dout_when_active = mux(count_r == Const(0, UInt(6)),
                            Const(0, UInt(8)),
                            mux(can_read, fifo_read_word[0:8], dataout_r))
    dataout_next = mux(sreset, Const(0, UInt(8)), dout_when_active)
    dataout_r <<= mux(rstn_inv, Const(0, UInt(8)), dataout_next)

    return full_r, empty_r, dataout_r


# ---------------------------------------------------------------------------
# Wire up the 4 (well, 6 instances counting 3 FIFOs) submodules.
# ---------------------------------------------------------------------------
# 1. router_reg drives `dout`, `parity_done`, `low_packet_valid`, and `err`
err_signal = make_router_reg()
err_out <<= err_signal

# 2. router_fsm drives all the state-related wires + `busy`
busy_signal = make_router_fsm()
busy_out <<= busy_signal

# 3. router_sync drives soft_reset_*, w_enb_*, fifo_full, vldout_*
make_router_sync()

# 4. router_fifo × 3 — each takes its channel's write_enb + read_enb,
#    drives its channel's full/empty/dataout
f0_full, f0_empty, f0_dout = make_router_fifo(0, w_enb_0, read_enb_0)
f1_full, f1_empty, f1_dout = make_router_fifo(1, w_enb_1, read_enb_1)
f2_full, f2_empty, f2_dout = make_router_fifo(2, w_enb_2, read_enb_2)

fifo_full_0  <<= f0_full
fifo_full_1  <<= f1_full
fifo_full_2  <<= f2_full
fifo_empty_0 <<= f0_empty
fifo_empty_1 <<= f1_empty
fifo_empty_2 <<= f2_empty

# Top outputs
data_out_0 <<= f0_dout
data_out_1 <<= f1_dout
data_out_2 <<= f2_dout

m.to_verilog_file("design.v")
