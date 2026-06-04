# Debugging the `pcie` SpireHDL port

## Result: PASS 2000/2000 first try, no debug needed

| Final metric | Spire (this port) | Verilog (golden) | Δ |
|---|---:|---:|---|
| cells | 5626 | 2731 | +106% |
| wires | 5589 | 2641 | +112% |
| transistors | — | 0 (*1) | — |

(*1) Verilog-side transistors reported as 0 — same pattern as router /
i2c / fifo where yosys doesn't fully map the inferred cells to liberty.

The ~2× cell overhead vs verilog is much larger than router's +12% and
stems from the encoder/decoder lookup table translation strategy
(see "Translation strategy" below). The design is functionally correct;
the overhead is purely synthesized-shape variance.

## Translation strategy (the easy part)

`pcie.v0.v` has 7 modules with a very clean dataflow:

```
top
├── scrambler   ← 16-bit LFSR, scrambles 8-bit datain
├── encoder     ← 8b/10b lookup (k=0, rd=1 hardcoded by top wiring)
├── piso        ← 10→1 parallel-in-serial-out shifter
├── sipo        ← 1→10 serial-in-parallel-out shifter
├── decoder     ← 10b/8b reverse lookup (k=0, rd=1 hardcoded)
└── descrambler ← same LFSR as scrambler but gated by d_en
```

**Key insight:** the top instantiates encoder/decoder with `rd=1'b1` and
`k=1'b0` HARDCODED. This means only the `(k=0, rd=1)` branch of each
table is reachable — the `if (k) …` branch is dead code under the top's
wiring. So my port only implements the used branch (256 encoder entries
+ 256 decoder entries instead of 268 + 536).

### Table extraction

The encoder/decoder tables are huge (~700 LOC of verilog `case` statements
combined). Rather than hand-transcribing them, I wrote
[`extract_tables.py`](extract_tables.py) which regexes the verilog and
emits Python dict literals. Two passes:

1. Full extraction (all `(k, rd)` branches): 12 enc_k + 256 enc_notk
   entries, 24 dec_k + 512 dec_notk entries.
2. Pinned extraction (only the used branches): 256 encoder + 256
   decoder entries.

The pinned-table output is inlined at the top of `starting_point.py`
as two Python dicts (`ENCODER` and `DECODER`).

### Module-by-module port

All 7 modules inlined as Python helper functions in a single SpireHDL
`Module`. Each helper takes its input signals and returns the output
signal. The top is then 8 lines of helper calls wiring the chain
together.

**Reset semantics** for every flop: `always @(posedge clk or negedge rst)`
— async active-low. Used the same `with_reset=False` + explicit
`mux(rstn_inv, init, next)` pattern as router, with `rstn_inv = ~rst`.

**LFSR unrolling**: scrambler/descrambler each have a `for (i=0; i<8; i++)`
loop that XORs each datain bit with `temp_lfsr[15]` and shifts the LFSR.
In spirehdl I unrolled the loop in Python at module-build time — each
iteration produces one scrambled bit and a new LFSR state, all stitched
together via `cat`.

**Shift registers** (piso, sipo): the verilog uses `{1'b0, temp[WIDTH-1:1]}`
or `{in, temp[width-1:1]}` concat patterns. Translated using LSB-first
`cat(temp_r[1:10], Const(0, UInt(1)))` etc. — careful about ordering
because cat is LSB-first.

**Encoder/decoder lookups**: `for di, code in ENCODER.items(): chain = mux(...)`
— linear mux cascade. yosys+abc can collapse this but produces a
suboptimal shape compared to verilog's `case` statement. This is the
root of the +106% cell overhead.

## Why no bugs surfaced

Three reasons this port worked first-try (vs router's 3-bug saga):

1. **No memory arrays.** pcie has no `reg [W:0] foo [0:N-1]` arrays
   indexed by pointers, so I avoided both the FIFO `full_d` slice bug
   and the blocking-assignment pointer-race bug from router.

2. **Tables extracted automatically.** All 512 lookup entries came
   straight from the verilog source via regex — zero typo risk.

3. **No `cat` ordering pitfalls** beyond the LFSR. The scrambler/
   descrambler `cat(feedback, lfsr[0:15])` was a single carefully-thought
   case; once I got the LSB-first ordering right (with bit-0 in arg 1)
   it worked.

## Spirehdl feature note (revisiting recommendation #1 from router)

The router DEBUGGING.md recommended either renaming `cat` to make
LSB-first ordering explicit, or adding a sibling `cat_msb_first(*parts)`.
This port reinforces that recommendation: the LFSR shift register and
the SIPO/PISO shifters all use small `cat` calls where getting the
order backwards would produce a SUBTLY wrong result (the LFSR would
still appear to function, but with a different feedback polynomial,
so the scrambled output would be wrong but plausible-looking).

A test-time helper like:
```python
assert cat(a, b).bits == [a, b], "cat is LSB-first; first arg goes to LSB"
```
or a printout on the first cat call demonstrating the bit-ordering
would help confirm the user's mental model.

## File structure

```
benchmarks/dr_rtl_spirehdl/pcie/_debug/
├── DEBUGGING.md           # this file
├── extract_tables.py      # regex-extracts encoder/decoder tables from verilog
└── pcie_tables.py         # full extraction output (all k,rd branches) — for reference
```

The actual *pinned* tables (used in starting_point.py) are inlined at
the top of that file rather than imported from `pcie_tables.py`, to
keep the spirehdl benchmark file self-contained.
