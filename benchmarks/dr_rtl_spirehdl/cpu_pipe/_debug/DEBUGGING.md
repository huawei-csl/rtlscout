# `cpu_pipe` port — porting log

## Status: PASS 2000/2000

Full top-module port in [`context/starting_point.py`](../context/starting_point.py).
All 5 verilog submodules inlined into one SpireHDL Module.
Final: **2000/2000 PASS, 4023 yosys_cells (-3.2% vs verilog 4155)**.

## Bugs found and fixed

### Bug 1: `cat` LSB-first zero-extension (DOMINANT bug)

The verilog 17-bit add for carry detection:
```verilog
{c, add} <= (~opc[0]) ? (src + tgt) : (src - tgt);
```
where `src`, `tgt` are 16-bit and `{c, add}` is 17-bit. Verilog
implicitly zero-extends `src` and `tgt` to 17 bits before the add.

I translated this as:
```python
add_full = (cat(Const(0, UInt(1)), src) + cat(Const(0, UInt(1)), tgt))[0:17]
```

**This is wrong.** Spirehdl `cat` is LSB-first: `cat(low, high)`. So
`cat(Const(0, UInt(1)), src)` puts `Const(0)` at the LSB and `src` at
positions 1..16 — i.e., it's `src << 1`. Result: my add was computing
`(2×src) + (2×tgt)`, doubling the answer.

The diagnostic was clean: `regR = 0x2c` when expected `0x16`. Since
`0x2c = 2 × 0x16`, the ALU was producing 2× the expected result.

Fix:
```python
# cat is LSB-first; put zero at MSB end for zero-extension
add_full = (cat(src, Const(0, UInt(1))) + cat(tgt, Const(0, UInt(1))))[0:17]
```

### Bug 2: `16'hX` defaults → 0 in Verilator 2-state

The verilog ALU has:
```verilog
case (opc)
  4'h0: regR <= src;
  ...
  default: regR <= 16'hX;
endcase
```

For opcodes that don't match (5, 6, C-F), verilog assigns `X`. In
Verilator's 2-state simulation, `X` becomes 0. My port defaulted to
"hold previous value" (`regR_r`), which doesn't match Verilator.

Fix: default to `Const(0, UInt(16))`.

This bug contributed ~280 vector failures (1105 → 1486 pass on its
own).

### Bug 3: `<<` shift widening

SpireHDL's `<<` does NOT widen the source operand when the shift
amount is variable. Verilog `shl <= src << tgt` where `shl` is 32-bit
and `src` is 16-bit implicitly zero-extends src to 32 bits.

Fix:
```python
src_32 = cat(src, Const(0, UInt(16)))   # explicit zero-extend
shl_w = (src_32 << tgt)[0:32]
shr_w = (src_32 >> tgt)[0:32]
```

(Caught at compile time — `ValueError: Index 32 out of range for width 16`.)

## Module-by-module translation notes

### `dcpu16_alu` (165 LOC)

Inlined. The verilog has a commented-out alternative `{regO, regR} <= ...`
joint assignment style that I did NOT follow — the active version uses
separate case statements per regO/regR/CC.

### `dcpu16_ctl` (140 LOC)

Mechanical port. The decoder slicing `{decB, decA, decO} = ireg` →
`decB=ireg[10:16], decA=ireg[4:10], decO=ireg[0:4]` (LSB-first
indexing per spirehdl). The `_skp` / `Fbra` / `Fjsr` predicates port
1:1.

### `dcpu16_mbus` (420 LOC)

The largest sub-module. Translated the many `always @(posedge clk)
case (pha) 2'o?: ... default: hold` blocks into nested `mux` chains.
The one-hot `({16{sel}} & val) | ({16{sel2}} & val2) | ...` pattern
translates to spirehdl as
`(cat(*([sel] * 16)) & val) | (cat(*([sel2] * 16)) & val2)`.

Watch the `sp_sel` packing: verilog `sp_sel = {sp_sel_dec, sp_sel_load}`
puts `_dec` at MSB. In spirehdl LSB-first `cat`: `sp_sel = cat(load, dec)`.

### `dcpu16_regs` (30 LOC)

8 × 16-bit register file (NOT 16 — verilog `reg [15:0] file [0:7]`).
Mux-tree read on `rra`. Write: per-register `mux(ena & match, rwd, rf[i])`.
No reset clause in verilog, so I don't reset rf either. Initial value
0 matches 2-state startup.

## Recommendations for the spirehdl library

- A `case_(selector, dict_of_cases, default)` helper would prevent the
  paren-counting errors that plague long mux cascades and make the
  intent clearer.
- A `zero_extend(x, width)` / `sign_extend(x, width)` helper would
  prevent the dominant `cat` LSB-first bug, since the common case is
  "make x wider with zeros at MSB end". `cat(x, Const(0, n))` doesn't
  scream "zero-extend" to the reader.
- A debug warning when `cat(small_const, wider_signal)` is used in an
  arithmetic context — strongly suggests a misintended shift-left.
