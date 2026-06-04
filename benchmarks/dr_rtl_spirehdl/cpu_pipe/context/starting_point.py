"""SpireHDL port of `cpu_pipe` — DCPU-16 CPU pipeline (926 LOC, 5 modules).

All 5 verilog submodules (`dcpu16_cpu` top, `dcpu16_alu`, `dcpu16_ctl`,
`dcpu16_mbus`, `dcpu16_regs`) inlined into one SpireHDL `Module`.

Reset semantics: sync active-high `rst` inside `always @(posedge clk)`.
Use `with_reset=False`, declare `rst` as input, `r <<= mux(rst, init, next)`
per register. No async edges.

Pipeline: 2-bit phase counter `pha` (incrementing 0→1→2→3→0…). Many
always blocks switch on `pha`.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, SInt, Register, Wire, Const, mux, cat

m = Module("dcpu16_cpu", with_clock=True, with_reset=False)

# ============================================================================
# Top-level ports (mirror verilog dcpu16_cpu port list)
# ============================================================================
g_dti = m.input(UInt(16), "g_dti")
g_ack = m.input(UInt(1),  "g_ack")
f_dti = m.input(UInt(16), "f_dti")
f_ack = m.input(UInt(1),  "f_ack")
rst   = m.input(UInt(1),  "rst")

g_adr = m.output(UInt(16), "g_adr")
g_stb = m.output(UInt(1),  "g_stb")
g_wre = m.output(UInt(1),  "g_wre")
g_dto = m.output(UInt(16), "g_dto")
f_adr = m.output(UInt(16), "f_adr")
f_stb = m.output(UInt(1),  "f_stb")
f_wre = m.output(UInt(1),  "f_wre")
f_dto = m.output(UInt(16), "f_dto")

# ============================================================================
# === ALU registers and wires ===
# ============================================================================
regR_r = Register(UInt(16), name="regR")
regO_r = Register(UInt(16), name="regO")
CC_r   = Register(UInt(1),  name="CC")

regA_r = Register(UInt(16), name="regA")
regB_r = Register(UInt(16), name="regB")

# === CTL registers ===
pha_r  = Register(UInt(2),  name="pha")
ireg_r = Register(UInt(16), name="ireg")
opc_r  = Register(UInt(4),  name="opc")
_bra_r = Register(UInt(1),  name="_bra")
bra_r  = Register(UInt(1),  name="bra")
_rwa_r = Register(UInt(3),  name="_rwa")
_rwe_r = Register(UInt(1),  name="_rwe")
rra_r  = Register(UInt(3),  name="rra")
rwa_r  = Register(UInt(3),  name="rwa")
rwe_r  = Register(UInt(1),  name="rwe")

# === MBUS registers ===
regPC_r        = Register(UInt(16), name="regPC")
wpc_r          = Register(UInt(1),  name="wpc")
regSP_r        = Register(UInt(16), init=0xFFFF, name="regSP")
_rSP_r         = Register(UInt(16), name="_rSP")
wsp_r          = Register(UInt(1),  name="wsp")
ea_r           = Register(UInt(16), name="ea")
eb_r           = Register(UInt(16), name="eb")
g_adr_r        = Register(UInt(16), name="g_adr_r")
g_stb_r        = Register(UInt(1),  name="g_stb_r")
g_stb_ena_r    = Register(UInt(1),  name="g_stb_ena_r")
g_stb_fbus_r   = Register(UInt(1),  name="g_stb_fbus_r")
_adr_r         = Register(UInt(16), name="_adr")
_stb_r         = Register(UInt(1),  name="_stb")
_wre_r         = Register(UInt(1),  name="_wre")
f_adr_r        = Register(UInt(16), name="f_adr_r")
f_stb_r        = Register(UInt(1),  name="f_stb_r")
f_wre_r        = Register(UInt(1),  name="f_wre_r")
_rd_r          = Register(UInt(1),  name="_rd")
regA_w         = regA_r  # alias for clarity
regB_w         = regB_r

# === REG FILE ===
rf = [Register(UInt(16), name=f"rf_{i}") for i in range(8)]

# ============================================================================
# === Combinational wires forward-declared ===
# ============================================================================
ireg_w     = Wire(UInt(16), name="ireg_wire");     ireg_w     <<= ireg_r
opc_w      = Wire(UInt(4),  name="opc_wire");      opc_w      <<= opc_r
pha_w      = Wire(UInt(2),  name="pha_wire");      pha_w      <<= pha_r
bra_w      = Wire(UInt(1),  name="bra_wire");      bra_w      <<= bra_r
rra_w      = Wire(UInt(3),  name="rra_wire");      rra_w      <<= rra_r
rwa_w      = Wire(UInt(3),  name="rwa_wire");      rwa_w      <<= rwa_r
rwe_w      = Wire(UInt(1),  name="rwe_wire");      rwe_w      <<= rwe_r
CC_w       = Wire(UInt(1),  name="CC_wire");       CC_w       <<= CC_r
regR_w     = Wire(UInt(16), name="regR_wire");     regR_w     <<= regR_r
regO_w     = Wire(UInt(16), name="regO_wire");     regO_w     <<= regO_r

# rrd combinational from register file via rra.
# NB: tried the bit-tree pattern (see router/datapath/pcie for the optimisation)
# here too, but on this 8-entry table it actually REGRESSED ADP by ~25%
# (delay 753→960ps). Likely because yosys-abc's optimisation already finds a
# good MUX2/MUX4 structure for 8 leaves, and forcing a specific bit-tree shape
# blocks that. The linear cascade below stays for cpu_pipe.
rrd_w = Wire(UInt(16), name="rrd")
chain = rf[7]
for i in reversed(range(7)):
    chain = mux(rra_w == Const(i, UInt(3)), rf[i], chain)
rrd_w <<= chain

# ena combinational
# verilog: assign ena = (f_stb ~^ f_ack) & (g_stb_for_ena ~^ g_ack)
ena_w = Wire(UInt(1), name="ena_wire")
ena_w <<= (~(f_stb_r ^ f_ack)) & (~(g_stb_ena_r ^ g_ack))

# ============================================================================
# === CTL: decoded fields from ireg ===
# verilog: assign {decB, decA, decO} = ireg;  →  decB=ireg[15:10], decA=ireg[9:4], decO=ireg[3:0]
# ============================================================================
decB_w = ireg_w[10:16]   # UInt(6)
decA_w = ireg_w[4:10]    # UInt(6)
decO_w = ireg_w[0:4]     # UInt(4)
_skp_w = decO_w == Const(0, UInt(4))
Fbra_w = ireg_w[0:5] == Const(0x10, UInt(5))

# === CTL: ALU outputs feed back through these comb wires ===
# (alu writes regR_r, regO_r, CC_r)

# ============================================================================
# === ALU body ===
# Inputs: regA, regB, opc, pha, rst, ena
# Outputs: regR, regO, CC, f_dto=regR, g_dto=regR, rwd=regR
# ============================================================================
src = regA_r
tgt = regB_r

# Combinational arithmetic — cat is LSB-first, so zero-extend by putting
# the zero at the MSB end (verilog `{1'b0, src}` → spirehdl `cat(src, 0)`).
add_full = (cat(src, Const(0, UInt(1))) + cat(tgt, Const(0, UInt(1))))[0:17]
sub_full = (cat(src, Const(0, UInt(1))) - cat(tgt, Const(0, UInt(1))))[0:17]
arith_full = mux(opc_w[0], sub_full, add_full)
c_w   = arith_full[16]
add_w = arith_full[0:16]

# Verilog: assign mul/shl/shr to 32-bit regs. The 16-bit src zero-extends in the 32-bit context.
mul_w = (src * tgt)[0:32]                               # UInt(32) — natural product width
src_32 = cat(src, Const(0, UInt(16)))                   # zero-extend src to 32 bits
shl_w = (src_32 << tgt)[0:32]
shr_w = (src_32 >> tgt)[0:32]

is_pha_0 = pha_w == Const(0, UInt(2))

# regO update: only on opcodes 2/3/4/7/8 in phase 0
regO_next = mux(is_pha_0,
    mux(opc_w == Const(0x2, UInt(4)), cat(Const(0, UInt(15)), c_w),
    mux(opc_w == Const(0x3, UInt(4)), cat(*([c_w] * 16)),
    mux(opc_w == Const(0x4, UInt(4)), mul_w[16:32],
    mux(opc_w == Const(0x7, UInt(4)), shl_w[16:32],
    mux(opc_w == Const(0x8, UInt(4)), shr_w[0:16],
                                       regO_r))))),
    regO_r)

# regR update: default 16'hX in verilog → 0 in Verilator 2-state sim.
# Note: at phase!=0, the always block doesn't update regR at all → it HOLDS.
# At phase==0, default arm sets regR to X → 0.
regR_next = mux(is_pha_0,
    mux(opc_w == Const(0x0, UInt(4)), src,
    mux(opc_w == Const(0x1, UInt(4)), tgt,
    mux(opc_w == Const(0x2, UInt(4)), add_w,
    mux(opc_w == Const(0x3, UInt(4)), add_w,
    mux(opc_w == Const(0x4, UInt(4)), mul_w[0:16],
    mux(opc_w == Const(0x7, UInt(4)), shl_w[0:16],
    mux(opc_w == Const(0x8, UInt(4)), shr_w[16:32],
    mux(opc_w == Const(0x9, UInt(4)), src & tgt,
    mux(opc_w == Const(0xA, UInt(4)), src | tgt,
    mux(opc_w == Const(0xB, UInt(4)), src ^ tgt,
                                       Const(0, UInt(16)))))))))))),
    regR_r)

# CC update — comparison opcodes (C/D/E/F) in phase 0
CC_next = mux(is_pha_0,
    mux(opc_w == Const(0xC, UInt(4)), (src == tgt),
    mux(opc_w == Const(0xD, UInt(4)), (src != tgt),
    mux(opc_w == Const(0xE, UInt(4)), (src > tgt),
    mux(opc_w == Const(0xF, UInt(4)), (src & tgt) != Const(0, UInt(16)),
                                       Const(1, UInt(1)))))),
    CC_r)

regR_r <<= mux(rst, Const(0, UInt(16)), mux(ena_w, regR_next, regR_r))
regO_r <<= mux(rst, Const(0, UInt(16)), mux(ena_w, regO_next, regO_r))
CC_r   <<= mux(rst, Const(0, UInt(1)),  mux(ena_w, CC_next,   CC_r))

# ============================================================================
# === CTL body ===
# ============================================================================

# phase counter
pha_r <<= mux(rst, Const(0, UInt(2)),
          mux(ena_w, (pha_r + Const(1, UInt(1)))[0:2], pha_r))

# IREG LATCH: case(pha) 2'o2: ireg <= (wpc | Fbra) ? nop : f_dti; default: hold
nop_w = Const(1, UInt(16))  # SET A, A
ireg_next_at_2 = mux(wpc_r | Fbra_w, nop_w, f_dti)
ireg_next = mux(pha_r == Const(2, UInt(2)), ireg_next_at_2, ireg_r)
ireg_r <<= mux(rst, Const(0, UInt(16)),
           mux(ena_w, ireg_next, ireg_r))

# opc latch: case(pha) 2'o2: opc <= ireg[3:0]; default: hold
opc_next = mux(pha_r == Const(2, UInt(2)), ireg_r[0:4], opc_r)
opc_r <<= mux(rst, Const(0, UInt(4)),
          mux(ena_w, opc_next, opc_r))

# BRANCH CONTROL
# case (pha)
#   2'o0: {bra, _bra} <= {_bra & CC, (ireg[5:0] == 5'h10)};  // bra<-_bra & CC, _bra <- new
#   default: {bra, _bra} <= {1'b0, _bra};
# Note verilog uses ireg[5:0] but compares to 5'h10 — actually 6 bits compared to 5-bit literal, MSB pads with 0
# Effective: (ireg[5:0] == 6'h10) → ireg[5:0] == 6'b010000
new_bra_seed = ireg_r[0:6] == Const(0x10, UInt(6))  # ireg[5:0] == 5'h10 (width-promoted)
bra_next  = mux(pha_r == Const(0, UInt(2)), _bra_r & CC_r, Const(0, UInt(1)))
_bra_next = mux(pha_r == Const(0, UInt(2)), new_bra_seed,  _bra_r)
bra_r  <<= mux(rst, Const(0, UInt(1)), mux(ena_w, bra_next,  bra_r))
_bra_r <<= mux(rst, Const(0, UInt(1)), mux(ena_w, _bra_next, _bra_r))

# REGISTER FILE addressing — pha-driven mux on decA/decB low 3 bits
rra_next = mux(pha_r == Const(0, UInt(2)), decB_w[0:3],
           mux(pha_r == Const(1, UInt(2)), decA_w[0:3],
           mux(pha_r == Const(2, UInt(2)), decB_w[0:3],
                                             decA_w[0:3])))
rra_r <<= mux(rst, Const(0, UInt(3)), mux(ena_w, rra_next, rra_r))

# rwe: case(pha) 2'o0: rwe <= _rwe & CC & (opc[3:2] != 2'o3); default: rwe <= 0
opc_high2_w = opc_r[2:4]
opc_high_nz3 = opc_high2_w != Const(3, UInt(2))
rwe_next = mux(pha_r == Const(0, UInt(2)),
                _rwe_r & CC_r & opc_high_nz3,
                Const(0, UInt(1)))
rwe_r <<= mux(rst, Const(0, UInt(1)), mux(ena_w, rwe_next, rwe_r))

# rwa: case(pha) 2'o1: rwa <= _rwa; default: rwa <= rwa
rwa_next = mux(pha_r == Const(1, UInt(2)), _rwa_r, rwa_r)
rwa_r <<= mux(rst, Const(0, UInt(3)), mux(ena_w, rwa_next, rwa_r))

# _rwa, _rwe: case(pha) 2'o0: _rwa <= decA[2:0]; _rwe <= (decA[5:3]==0) & !_skp
_rwe_at0 = (decA_w[3:6] == Const(0, UInt(3))) & ~_skp_w
_rwa_next = mux(pha_r == Const(0, UInt(2)), decA_w[0:3], _rwa_r)
_rwe_next = mux(pha_r == Const(0, UInt(2)), _rwe_at0,    _rwe_r)
_rwa_r <<= mux(rst, Const(0, UInt(3)), mux(ena_w, _rwa_next, _rwa_r))
_rwe_r <<= mux(rst, Const(0, UInt(1)), mux(ena_w, _rwe_next, _rwe_r))

# ============================================================================
# === MBUS body ===
# ============================================================================

# Repeated decoder from ireg
Fjsr_w = ireg_r[0:5] == Const(0x10, UInt(5))

ed_w = mux(pha_r[0], decB_w, decA_w)
Eind_w = ed_w[3:6] == Const(1, UInt(3))
Enwr_w = ed_w[3:6] == Const(2, UInt(3))
Epop_w = ed_w == Const(0x18, UInt(6))
Epek_w = ed_w == Const(0x19, UInt(6))
Epsh_w = ed_w == Const(0x1A, UInt(6))
Ersp_w = ed_w == Const(0x1B, UInt(6))
Erpc_w = ed_w == Const(0x1C, UInt(6))
Erro_w = ed_w == Const(0x1D, UInt(6))
Enwi_w = ed_w == Const(0x1E, UInt(6))
Esht_w = ed_w[5]

fg_w = mux(pha_r[0], decA_w, decB_w)
Fdir_w = fg_w[3:6] == Const(0, UInt(3))
Find_w = fg_w[3:6] == Const(1, UInt(3))
Fnwr_w = fg_w[3:6] == Const(2, UInt(3))
Fspi_w = fg_w == Const(0x18, UInt(6))
Fspr_w = fg_w == Const(0x19, UInt(6))
Fspd_w = fg_w == Const(0x1A, UInt(6))
Frsp_w = fg_w == Const(0x1B, UInt(6))
Frpc_w = fg_w == Const(0x1C, UInt(6))
Fnwi_w = fg_w == Const(0x1E, UInt(6))
Fnwl_w = fg_w == Const(0x1F, UInt(6))

# PROGRAMME COUNTER
rpc_sel_wpc_w = wpc_r
rpc_sel_bra_w = ~wpc_r & bra_r
rpc_sel_default_w = ~wpc_r & ~bra_r

# rpc / lpc are combinational
rpc_at_1 = (cat(*([rpc_sel_wpc_w] * 16)) & regR_r) | \
           (cat(*([rpc_sel_bra_w] * 16)) & regB_r) | \
           (cat(*([rpc_sel_default_w] * 16)) & regPC_r)
rpc_w = mux(pha_r == Const(1, UInt(2)), rpc_at_1, regPC_r)

lpc_w = mux(pha_r == Const(0, UInt(2)), ~(Fnwr_w | Fnwi_w | Fnwl_w),
        mux(pha_r == Const(1, UInt(2)), Const(1, UInt(1)),
        mux(pha_r == Const(3, UInt(2)), ~(Fnwr_w | Fnwi_w | Fnwl_w),
                                          Const(0, UInt(1)))))

regPC_next = mux(lpc_w, rpc_w, (regPC_r + Const(1, UInt(1)))[0:16])
regPC_r <<= mux(rst, Const(0, UInt(16)), mux(ena_w, regPC_next, regPC_r))

wpc_next = mux(pha_r == Const(1, UInt(2)), Frpc_w & CC_r, wpc_r)
wpc_r <<= mux(rst, Const(0, UInt(1)), mux(ena_w, wpc_next, wpc_r))

# STACK POINTER
sp_val_inc_w = (regSP_r + Const(1, UInt(1)))[0:16]
sp_val_dec_w = (regSP_r - Const(1, UInt(1)))[0:16]

# Combinational lsp and rsp
lsp_w = mux(pha_r == Const(0, UInt(2)), ~(Fspi_w | Fspd_w),
        mux(pha_r == Const(3, UInt(2)), ~(Fspi_w | Fspd_w | Fjsr_w),
                                          Const(1, UInt(1))))
rsp_w = mux(pha_r == Const(1, UInt(2)), mux(wsp_r, regR_r, regSP_r), regSP_r)

sp_sel_load_w = lsp_w & wsp_r
sp_sel_dec_w  = mux(lsp_w, Const(0, UInt(1)), fg_w[1] | Fjsr_w)
sp_sel_w = cat(sp_sel_load_w, sp_sel_dec_w)  # {sp_sel_dec, sp_sel_load} but cat LSB-first: {dec, load} → cat(load, dec)

# Wait — verilog: assign sp_sel = {sp_sel_dec, sp_sel_load} → sp_sel[1]=dec, sp_sel[0]=load
# In spirehdl cat LSB-first: cat(low, high). So sp_sel = cat(load, dec)
regSP_next = mux(sp_sel_w == Const(0, UInt(2)), sp_val_inc_w,
            mux(sp_sel_w == Const(1, UInt(2)), rsp_w,
            mux(sp_sel_w == Const(2, UInt(2)), sp_val_dec_w,
                                                sp_val_dec_w)))
regSP_r <<= mux(rst, Const(0xFFFF, UInt(16)), mux(ena_w, regSP_next, regSP_r))

_rSP_r <<= mux(rst, Const(0, UInt(16)), mux(ena_w, regSP_r, _rSP_r))

wsp_next = mux(pha_r == Const(1, UInt(2)), Frsp_w & CC_r, wsp_r)
wsp_r <<= mux(rst, Const(0, UInt(1)), mux(ena_w, wsp_next, wsp_r))

# EA CALCULATOR
ec_sel_Eind_w = Eind_w
ec_sel_Enwr_w = ~Eind_w & Enwr_w
ec_sel_Epsh_w = ~Eind_w & ~Enwr_w & Epsh_w
ec_sel_Epop_w = ~Eind_w & ~Enwr_w & ~Epsh_w & (Epop_w | Epek_w)
ec_sel_Enwi_w = ~Eind_w & ~Enwr_w & ~Epsh_w & ~(Epop_w | Epek_w) & Enwi_w
nwr_w = (rrd_w + g_dti)[0:16]
ec_w = (cat(*([ec_sel_Eind_w] * 16)) & rrd_w) | \
       (cat(*([ec_sel_Enwr_w] * 16)) & nwr_w) | \
       (cat(*([ec_sel_Epsh_w] * 16)) & regSP_r) | \
       (cat(*([ec_sel_Epop_w] * 16)) & _rSP_r) | \
       (cat(*([ec_sel_Enwi_w] * 16)) & g_dti)

ea_next = mux(pha_r == Const(0, UInt(2)),
              mux(Fjsr_w, regSP_r, ec_w), ea_r)
eb_next = mux(pha_r == Const(1, UInt(2)), ec_w, eb_r)
ea_r <<= mux(rst, Const(0, UInt(16)), mux(ena_w, ea_next, ea_r))
eb_r <<= mux(rst, Const(0, UInt(16)), mux(ena_w, eb_next, eb_r))

# G-BUS
g_wre <<= Const(0, UInt(1))

g_adr_next = mux(pha_r == Const(1, UInt(2)), ea_r,
             mux(pha_r == Const(2, UInt(2)), eb_r, regPC_r))
g_adr_r <<= mux(rst, Const(0, UInt(16)), mux(ena_w, g_adr_next, g_adr_r))

g_stb_at_3_or_0 = Fnwr_w | Fnwi_w | Fnwl_w
g_stb_at_1_or_2 = Find_w | Fnwr_w | Fspr_w | Fspi_w | Fspd_w | Fnwi_w
g_stb_next = mux((pha_r == Const(3, UInt(2))) | (pha_r == Const(0, UInt(2))),
                  g_stb_at_3_or_0, g_stb_at_1_or_2)
g_stb_r       <<= mux(rst, Const(0, UInt(1)), mux(ena_w, g_stb_next, g_stb_r))
g_stb_ena_r   <<= mux(rst, Const(0, UInt(1)), mux(ena_w, g_stb_next, g_stb_ena_r))
g_stb_fbus_r  <<= mux(rst, Const(0, UInt(1)), mux(ena_w, g_stb_next, g_stb_fbus_r))

# F-BUS
_adr_next = mux(pha_r == Const(2, UInt(2)), g_adr_r, _adr_r)
_stb_next = mux(pha_r == Const(2, UInt(2)), g_stb_r | Fjsr_w, _stb_r)
_wre_next = mux(pha_r == Const(1, UInt(2)),
                Find_w | Fnwr_w | Fspr_w | Fspi_w | Fspd_w | Fnwi_w | Fjsr_w,
                _wre_r)
_adr_r <<= mux(rst, Const(0, UInt(16)), mux(ena_w, _adr_next, _adr_r))
_stb_r <<= mux(rst, Const(0, UInt(1)),  mux(ena_w, _stb_next, _stb_r))
_wre_r <<= mux(rst, Const(0, UInt(1)),  mux(ena_w, _wre_next, _wre_r))

f_rpc_sel_wpc_w     = wpc_r
f_rpc_sel_bra_w     = ~wpc_r & bra_r
f_rpc_sel_default_w = ~wpc_r & ~bra_r

f_adr_at_1 = (cat(*([f_rpc_sel_wpc_w] * 16)) & regR_r) | \
             (cat(*([f_rpc_sel_bra_w] * 16)) & regB_r) | \
             (cat(*([f_rpc_sel_default_w] * 16)) & regPC_r)
f_adr_next = mux(pha_r == Const(1, UInt(2)), f_adr_at_1,
             mux(pha_r == Const(0, UInt(2)), _adr_r,
                                                Const(0, UInt(16))))
f_adr_r <<= mux(rst, Const(0, UInt(16)), mux(ena_w, f_adr_next, f_adr_r))

# f_stb / f_wre joint case
# case (pha)
#   2'o1: {f_stb,f_wre} <= (Fjsr) ? 2'o0 : 2'o2;
#   2'o0: {f_stb,f_wre} <= {_stb, _wre & CC};
#   default: {f_stb,f_wre} <= 2'o0;
# Verilog {f_stb, f_wre} — f_stb is MSB, f_wre is LSB. 2'o2 = 0b10 → f_stb=1, f_wre=0.
f_stb_wre_at1 = mux(Fjsr_w, Const(0, UInt(2)), Const(2, UInt(2)))  # {f_stb=1, f_wre=0}
f_stb_wre_at0 = cat(_wre_r & CC_r, _stb_r)  # cat LSB-first: cat(wre, stb)
# Wait verilog: {f_stb, f_wre} = {_stb, _wre & CC} → MSB=_stb (matches f_stb), LSB=_wre & CC (matches f_wre)
# So f_stb <= _stb; f_wre <= _wre & CC.

f_stb_at1 = mux(Fjsr_w, Const(0, UInt(1)), Const(1, UInt(1)))
f_wre_at1 = Const(0, UInt(1))
f_stb_at0 = _stb_r
f_wre_at0 = _wre_r & CC_r

f_stb_next = mux(pha_r == Const(1, UInt(2)), f_stb_at1,
             mux(pha_r == Const(0, UInt(2)), f_stb_at0, Const(0, UInt(1))))
f_wre_next = mux(pha_r == Const(1, UInt(2)), f_wre_at1,
             mux(pha_r == Const(0, UInt(2)), f_wre_at0, Const(0, UInt(1))))
f_stb_r <<= mux(rst, Const(0, UInt(1)), mux(ena_w, f_stb_next, f_stb_r))
f_wre_r <<= mux(rst, Const(0, UInt(1)), mux(ena_w, f_wre_next, f_wre_r))

# REG-A / REG-B
_rd_next = mux(pha_r == Const(1, UInt(2)), Fdir_w,
           mux(pha_r == Const(2, UInt(2)), Fdir_w, Const(0, UInt(1))))
_rd_r <<= mux(rst, Const(0, UInt(1)), mux(ena_w, _rd_next, _rd_r))

# opr combinational mux
opr_sel_g_stb_w = g_stb_r
opr_sel_Ersp_w  = ~g_stb_r & Ersp_w
opr_sel_Erpc_w  = ~g_stb_r & ~Ersp_w & Erpc_w
opr_sel_Erro_w  = ~g_stb_r & ~Ersp_w & ~Erpc_w & Erro_w
opr_sel_Esht_w  = ~g_stb_r & ~Ersp_w & ~Erpc_w & ~Erro_w & Esht_w
opr_w = (cat(*([opr_sel_g_stb_w] * 16)) & g_dti) | \
        (cat(*([opr_sel_Ersp_w] * 16))  & regSP_r) | \
        (cat(*([opr_sel_Erpc_w] * 16))  & regPC_r) | \
        (cat(*([opr_sel_Erro_w] * 16))  & regO_r) | \
        (cat(*([opr_sel_Esht_w] * 16))  & cat(ed_w[0:5], Const(0, UInt(11))))

# regA muxing
regA_sel_g_stb_w = g_stb_r
regA_sel_Fjsr_w  = ~g_stb_r & Fjsr_w
regA_sel_rd_w    = ~g_stb_r & ~Fjsr_w & _rd_r
regA_other_w     = ~(regA_sel_g_stb_w | regA_sel_Fjsr_w | regA_sel_rd_w)

regA_at_2 = (cat(*([regA_sel_g_stb_w] * 16)) & g_dti) | \
            (cat(*([regA_sel_Fjsr_w]  * 16)) & regPC_r) | \
            (cat(*([regA_sel_rd_w]    * 16)) & rrd_w) | \
            (cat(*([regA_other_w]     * 16)) & regA_r)

regA_next = mux(pha_r == Const(0, UInt(2)), opr_w,
            mux(pha_r == Const(2, UInt(2)), regA_at_2, regA_r))
regA_r <<= mux(rst, Const(0, UInt(16)), mux(ena_w, regA_next, regA_r))

regB_sel_g_stb_w = g_stb_r
regB_sel_rd_w    = ~g_stb_r & _rd_r
regB_other_w     = ~(regB_sel_g_stb_w | regB_sel_rd_w)

regB_at_3 = (cat(*([regB_sel_g_stb_w] * 16)) & g_dti) | \
            (cat(*([regB_sel_rd_w]    * 16)) & rrd_w) | \
            (cat(*([regB_other_w]     * 16)) & regB_r)

regB_next = mux(pha_r == Const(1, UInt(2)), opr_w,
            mux(pha_r == Const(3, UInt(2)), regB_at_3, regB_r))
regB_r <<= mux(rst, Const(0, UInt(16)), mux(ena_w, regB_next, regB_r))

# ============================================================================
# === REG FILE ===
# ============================================================================
# rwd = regR (per alu)
rwd_w = regR_r
for i in range(8):
    match = (rwa_w == Const(i, UInt(3))) & rwe_w
    rf[i] <<= mux(ena_w & match, rwd_w, rf[i])
    # Note: verilog `always @(posedge clk) if (ena) ...` — no rst clause on rf
    # So rf doesn't reset. Spirehdl default init is 0 which matches 2-state startup.

# ============================================================================
# === Output assignments ===
# ============================================================================
g_adr <<= g_adr_r
g_stb <<= g_stb_r
g_dto <<= regR_r
f_adr <<= f_adr_r
f_stb <<= f_stb_r
f_wre <<= f_wre_r
f_dto <<= regR_r

m.to_verilog_file("design.v")
