# Debugging the `router` SpireHDL port

## Result: PASS 2000/2000 after 3 bugs found

| Final metric | Spire (this port) | Verilog (golden) | Δ |
|---|---:|---:|---|
| cells | 1923 | 1707 | +12.7% |
| wires | 1340 | 1240 | +8.1% |
| transistors | 10454 | 0 (*1) | — |

(*1) verilog-side transistors reported as 0 because of yosys cell-mapping for
this design's mixed-clock primitives — same as in `eval_verify.json`.

The +12.7% cell overhead is typical for spirehdl ports because of the
"source structure influences post-yosys AIG topology" effect documented in
`benchmarks/turbo_rtl/README.md:389-413`. yosys+abc finds a different local
optimum on the spirehdl-emitted netlist than on the hand-written verilog.

## Debug methodology

Used the **spirehdl built-in Simulator**
(`deps/spire-hdl/src/spirehdl/spirehdl_simulator.py`) to step the module
cycle-by-cycle with vectors.dat inputs, peeking internal-state registers
by name. In parallel, a separate verilog probe (`verilog_trace.sv`)
drove the same vectors.dat against the golden verilog and `$display`'d
the corresponding signals via hierarchical refs (`dut.fifo[0].f.fifo[1]`,
`dut.fsm.present_state`, etc.). Diffing the two traces side-by-side
pinpointed each divergence to a specific cycle and specific signal.

Files:
- `spire_trace.py` — drives the spirehdl module via `Simulator`,
  dumps named registers + outputs every cycle.
- `verilog_trace.sv` — hand-written probe testbench for the golden
  verilog. Hierarchically references internal signals via `dut.fifo[N].f.…`.
- `spire_trace.log` / `verilog_trace.log` — captured traces.

Each pass through the debug loop took ~15 seconds (spirehdl simulator is
~instant; verilator rebuild + run takes most of the time).

## Building the verilator trace

The verilator side took a few iterations to land. Recipe:

### 1. Wrap the golden verilog in a probe module

Standard verilator clocked-testbench skeleton:

```systemverilog
`timescale 1ns/1ps
module probe;
  logic clk = 0;
  always #5 clk = ~clk;                       // 100 MHz simulated clock

  logic resetn, packet_valid, read_enb_0, read_enb_1, read_enb_2;
  logic [7:0] datain;
  wire vldout_0, vldout_1, vldout_2, err, busy;
  wire [7:0] data_out_0, data_out_1, data_out_2;

  router_top dut (
    .clk(clk), .resetn(resetn), … .datain(datain),
    .vldout_0(vldout_0), … .data_out_2(data_out_2)
  );
  …
endmodule
```

The DUT is instantiated with the name `dut`. That name is what makes
hierarchical references (`dut.fsm.present_state`,
`dut.fifo[0].f.fifo[1]`, …) work for the probe — they reach into the
DUT's internal scope by following the instance hierarchy of the golden's
own submodule wiring.

### 2. Reproduce the framework testbench's reset + input-feeding sequence

The framework's `tb.sv` (in `benchmarks/dr_rtl_spirehdl/router/tb.sv`)
does:
1. Asserts reset for 3 cycles
2. `#1; resetn = 1` (deassert)
3. Opens `vectors.dat`
4. Loops: read line → `$sscanf("%h %h …", inputs, expecteds)` →
   set inputs → `@(posedge clk); #1; compare`

The probe mirrors this exactly:

```systemverilog
initial begin
  resetn = 0; packet_valid = 0;
  read_enb_0 = 0; read_enb_1 = 0; read_enb_2 = 0;
  datain = 0;

  repeat (3) @(posedge clk);                 // 3-cycle reset
  #1;
  resetn = 1;                                 // deassert

  fd = $fopen("../vectors.dat", "r");
  …
  while (!$feof(fd) && i < 80) begin
    void'($fgets(line_buf, fd));
    if (line_buf.len() == 0) continue;
    if (line_buf.substr(0, 0) == "#") continue;
    rc = $sscanf(line_buf, "%h %h %h %h %h %h %h %h %h %h %h %h %h",
      pv, re0, re1, re2, di, exp_v0, …, exp_d2);
    if (rc != 13) begin
      $display("sscanf_fail rc=%0d line=%s", rc, line_buf);
      continue;
    end
    packet_valid = pv; read_enb_0 = re0; …; datain = di;
    @(posedge clk);
    #1;
    dump(i);                                  // ← internal-state dump
    i = i + 1;
  end
end
```

Critical match-points with `tb.sv`:
- **Same reset duration (3 cycles).** Off-by-one here would make every
  trace cycle compare to the wrong vector.
- **Inputs assigned BEFORE `@(posedge clk)`.** Combinational `=`
  assignments take effect immediately; the FF samples on the edge.
- **`#1` AFTER the edge, BEFORE the dump.** Lets non-blocking updates
  settle so the dump reads the post-edge register values.
- **`continue` skips `i++`.** If the line is empty / a comment / fails
  to parse, we don't advance the cycle counter — the next `dump(i)` is
  still at the same logical cycle index.
- **Path `"../vectors.dat"`** is relative to where `obj_dir/probe_exe`
  runs, which is `router/_debug/`. The vectors live one dir up at
  `router/vectors.dat`.

### 3. Build the dump task with hierarchical refs to internals

The `dump(input int cyc)` task `$display`s a single line per cycle with
all the signals of interest:

```systemverilog
task dump(input int cyc);
  $display("cyc=%0d IN[pv=%0d re0=%0d di=%02x] ps=%0d e0=%0d f0=%0d incr0=%0d rp0=%0d wp0=%0d cnt0=%0d d0r=%02x w_enb0=%0d dout=%02x fifo0[0]=%03x fifo0[1]=%03x fifo0[2]=%03x fifo0[3]=%03x",
    cyc,
    packet_valid, read_enb_0, datain,
    dut.fsm.present_state,                   // hierarchical ref into router_fsm
    dut.fifo[0].f.empty,                     // fifo is a `generate for` block → indexed
    dut.fifo[0].f.full,
    dut.fifo[0].f.incrementer,
    dut.fifo[0].f.read_ptr,
    dut.fifo[0].f.write_ptr,
    dut.fifo[0].f.count,
    dut.fifo[0].f.dataout,
    dut.s.write_enb[0],
    dut.r1.dout,
    dut.fifo[0].f.fifo[0],                   // memory-array entry
    dut.fifo[0].f.fifo[1],
    dut.fifo[0].f.fifo[2],
    dut.fifo[0].f.fifo[3]
  );
endtask
```

Resolving the hierarchical names requires reading `router.v0.v`:
- The top instantiates submodules with names `r1` (router_reg), `s`
  (router_sync), `fsm` (router_fsm).
- The 3-channel FIFO is generated:
  ```verilog
  generate for (a=0; a<3; a=a+1) begin: fifo
    router_fifo f(.clk(clk), …);
  end endgenerate
  ```
  Verilog block name `fifo` + instance name `f` + generate index `[a]`
  gives the access path `dut.fifo[N].f.<inner_signal>`.

### 4. Compile + run

```bash
verilator --binary --top-module probe -Wno-fatal -Wno-WIDTH -Wno-UNOPTFLAT \
  -Wno-LATCH -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-CASEINCOMPLETE \
  -Wno-SELRANGE -Wno-COMBDLY -Wno-MULTIDRIVEN -Wno-IMPLICIT \
  -Wno-SYNCASYNCNET -j 0 -o probe_exe \
  /workspaces/rtl_scout/benchmarks/dr_rtl/router/context/starting_point.v \
  verilog_trace.sv

./obj_dir/probe_exe > verilog_trace.log
```

The `-Wno-*` flags suppress the warnings that the golden source would
otherwise emit (latches, multi-driven nets in the patched tri-state
lines, etc.). `--binary` makes verilator emit a directly-runnable
executable.

### Gotchas hit during construction

Two non-obvious bugs in the probe itself, both surfaced as
"this-can't-be-right" data in the trace:

**(a) Comment line continuations look like verilator pragmas.** My
first version had a multi-line `//` header at the top of
`verilog_trace.sv` using `\` line continuations for shell-style
readability:

```systemverilog
// Compile:
//   verilator --binary … \
//             -o probe_exe \
//             … verilog_trace.sv
```

Verilator's preprocessor saw the `\` at end of `//` lines and joined
them, producing the single token `// verilator --binary --top-module …`
which it interpreted as a verilator-pragma comment, emitted
`BADVLTPRAGMA`, and refused to compile. **Fix**: removed the multi-line
shell-style comment header; moved the build/run instructions into this
markdown instead.

**(b) `$display` format-spec / argument count mismatch silently shifts
values.** While iterating on the dump task I accidentally duplicated
the `cyc` argument:

```systemverilog
$display("cyc=%0d IN[pv=%0d re=%0d%0d%0d di=%02x] ps=%0d …",
  cyc,
  packet_valid, read_enb_0, read_enb_1, read_enb_2, datain,
  cyc,                                       // ← typo, repeated!
  dut.fsm.present_state,
  …
);
```

The extra `cyc` slid every subsequent value one slot left. The output
became `ps=60 temp_fsm=4 temp_sync=2 …`, which initially looked like a
DUT bug (`present_state=60` is impossible for a 4-bit reg, and `4` is
out of range for a 2-bit `temp`). What clued me in was that the values
matched real-but-unrelated signals — `present_state=60` was the
`cyc=60` value being printed at the `ps` slot. **Fix**: removed the
duplicate; **lesson**: when a probe trace produces obviously-impossible
register values, suspect the format string before the DUT. A quick
sanity check is `./obj_dir/probe_exe | head -1 | tr ' ' '\n' | head -50`
which lays out one field per line for visual inspection.

**(c) `int` is 32-bit in SystemVerilog, but the field widths in the
testbench are smaller** — `packet_valid` is 1 bit, `datain` is 8 bits.
When you read into `int pv, di, …` and then assign `datain = di`,
Verilog truncates to the LHS width. That's fine — no fix needed — but
worth knowing so the probe doesn't accidentally `$display("%h", di)`
expecting `0x79` but seeing `0x00000079`. The `%02x` format in the dump
keeps things readable.

### Diffing the two traces

`spire_trace.log` columns are `key=value` separated; `verilog_trace.log`
uses the same format. To find the first divergence:

```bash
diff <(awk '/^.cyc/ {print}' spire_trace.log) \
     <(awk '/^cyc=/  {print}' verilog_trace.log)
```

or for a specific signal pair (here `count_0` in spire / `cnt0` in verilog):

```bash
paste \
  <(grep -oE "cyc=[ ]*[0-9]+|count_0=[0-9]+" spire_trace.log | paste -d' ' - -) \
  <(grep -oE "cyc=[0-9]+|cnt0=[0-9]+" verilog_trace.log | paste -d' ' - -)
```

The first cycle where the signal columns disagree is where to focus.

## Bugs found and fixed (in order)

### Bug 1: FIFO `full_d` slice mistake (22/2000 → 1837/2000)

**Symptom:** FSM diverged at cyc=19 — `present_state` advanced to
`FIFO_FULL_STATE` because my `fifo_full_2` reported `1` while the verilog
reported `0`.

**Root cause:** Verilog says
```verilog
if (incrementer == 4'b1111) full_d = 1;
```
The 5-bit `incrementer` is compared against the 4-bit literal `4'b1111`,
which Verilator zero-extends to `5'b01111`. So `full_d = 1` ONLY when
`incrementer == 15` exactly. **NOT** when `incrementer` has all lower-4
bits set (which would also match at `incrementer == 31`, the wrap-around
value when a stale `empty_r` lets a 0-1 decrement wrap to `5'b11111`).

My spirehdl translation was:
```python
full_d = incrementer[0:4] == Const(0b1111, UInt(4))
```
which **does** match at `incrementer == 31` (lower 4 bits = 1111). So my
FIFO spuriously reported `full` after a stale-empty decrement.

**Fix:**
```python
full_d = incrementer == Const(15, UInt(5))
```
Compare the full 5-bit value to 15. ✓

### Bug 2: FIFO write/read uses POST-increment pointer (didn't change count, but uncovered Bug 3)

**Symptom:** With Bug 1 fixed, framework eval got to 1837/2000. The first
failing vector had `data_out_0` mismatching: expected 0xc0, my spire gave
0x00. Side-by-side trace at cyc=32 showed verilog wrote the first FIFO
entry to `fifo[1]` (not `fifo[0]`!) while my spire wrote to `fifo[0]`.

**Root cause:** Subtle verilog blocking-assignment race. The verilog has
the pointer update in a SEPARATE always block from the FIFO array write:
```verilog
// Block A — pointer update, BLOCKING assignment
always @(posedge clk) begin
  if (write_enb && !full) write_ptr = write_ptr + 1'b1;
  if (read_enb  && !empty) read_ptr  = read_ptr  + 1'b1;
end

// Block B — FIFO write, NON-BLOCKING assignment
always @(posedge clk) begin
  if (write_enb && !full)
    {fifo[write_ptr[3:0]][8], fifo[write_ptr[3:0]][7:0]} <= {temp, datain};
end
```
Both fire at the same posedge clk. Verilator's scheduler runs the BLOCKING
pointer-update block FIRST, so when Block B reads `write_ptr` for its
index, it sees the **post-increment** value. Same applies to read_ptr in
the FIFO read logic.

This is an artifact of the original verilog code (probably unintentional;
the author likely thought `<=` semantics applied), but the captured
vectors.dat was generated by exactly this verilog, so to match it we
need to reproduce the race.

**Fix:** index FIFO with the post-increment pointer value
(`(write_ptr+1)[0:4]` when can_write, else `write_ptr`):
```python
wptr_next = mux(can_write, (write_ptr + Const(1, UInt(4)))[0:4], write_ptr)
rptr_next = mux(can_read,  (read_ptr  + Const(1, UInt(4)))[0:4], read_ptr)
# FIFO writes:
write_match = (wptr_next == Const(i, UInt(4))) & can_write
# FIFO reads:
sel = rptr_next   # was: sel = read_ptr
```

After this fix, my spire's `fifo_0_1` became `0x1c0` at cyc=32 — matches verilog.

### Bug 3: `cat` LSB-first ordering in payload_length extraction (1837/2000 → 2000/2000)

**Symptom:** Even with the pointers correctly post-incremented, the
`count` register loaded the wrong value when reading a header byte.
Verilog cnt0 = 49 (0x31), my spire count_0 = 1.

**Root cause:** I wrote
```python
payload_len = (cat(Const(0, UInt(2)), fifo_read_word[2:8]) + Const(1, UInt(8)))[0:6]
```
intending to extract `fifo[read_ptr][7:2] + 1`. But `cat` is **LSB-first**
in spirehdl — `cat(zeros, bits)` produces `{bits, zeros}` in verilog
notation, i.e. the bits get **left-shifted by 2** instead of being
zero-padded as a 6-bit value. The result was 48 << 2 = 0xc0, then +1 = 0xc1,
truncated to 6 bits = 0x01 (= the LSBs of 0xc1).

**Fix:** add `1` directly to the 6-bit slice; the +1 widens to 7 bits,
slice back to 6.
```python
payload_len = (fifo_read_word[2:8] + Const(1, UInt(1)))[0:6]
```

After this fix, my spire's `count_0 = 49` at cyc=35 matches verilog. The
testbench passes 2000/2000.

## Lessons learned

1. **The Simulator is fantastic for stepping cycle-by-cycle and reading
   any named register/wire.** `sim.set("input", v); sim.step(); sim.get("reg")`
   is much faster than running verilator (~15 seconds round-trip) and
   gives Python-native access to internal state. Use it before reaching
   for verilator.

2. **Side-by-side traces beat one-side debugging.** Both my port and the
   golden need their internals dumped. Verilator hierarchical refs
   (`dut.fifo[N].f.fifo[K]`) let you reach any signal in the golden;
   `sim.get("name")` does the same for the spirehdl port.

3. **Verilator + #$display races: count format specs carefully.** My
   first verilog probe had a duplicate `cyc,` argument that shifted every
   subsequent value by one slot, producing nonsensical traces. Always
   pretty-print the first failing line with `... | sed 's/ /\n/g'` to
   visually verify field alignment.

4. **`cat` is LSB-first in spirehdl.** Easy to get backwards when
   translating verilog `{msb, ..., lsb}` concats. Add a small unit test
   per design that prints `cat(a, b)` width and value to confirm.

5. **Blocking-vs-non-blocking races in the verilog source can leak into
   the spirehdl port.** The router's `write_ptr = write_ptr + 1` (blocking)
   in one block + `fifo[write_ptr] <= ...` (non-blocking) in another is
   technically a race in verilog. Verilator picks a deterministic order
   that effectively post-increments the pointer before the FIFO write.
   When translating, **diff signal-by-signal against the captured
   vectors** rather than trusting the verilog source's apparent
   semantics.

## Recommendations for spirehdl features

The bugs above point to small library additions that would have caught
them sooner:

### 1. A `slice_msb_down` helper or rename `cat` to clarify LSB ordering

Verilog programmers translating to spirehdl will write `cat(msb, ..., lsb)`
out of habit (matching verilog `{}` syntax), get the bit order reversed,
and produce subtle bugs. Either:
- Rename `cat` → `cat_lsb_first(...)` to make the order explicit.
- Add a sibling `cat_msb_first(*parts)` that emits in verilog order
  for readability.

### 2. Native `Memory` / `MemArray` primitive

The router's FIFO array (`reg [8:0] fifo [15:0]`) is a 16×9 memory. I
translated it as `list[Register]` + a 16-deep mux tree on read. yosys
collapses this fine, but the source is ugly (~50 LOC for the FIFO
array logic) and the mux tree is the bit that creates the +12.7% cell
overhead vs verilog. A native `MemArray(depth=16, width=9)` primitive with
named index ports would:
- Be 5x shorter to write
- Emit a verilog `reg [W:0] foo [0:D-1]` array directly, matching the
  golden's structure 1:1 and avoiding the AIG-shape divergence.

### 3. Built-in `to_post_increment(pointer)` helper

Cycling pointers in FIFO-style designs is common. A helper that returns
"this pointer's value at this clock edge AFTER its conditional
increment" (without changing the register's actual value) would have
saved me the second debug round. e.g.:
```python
read_ptr = Register(UInt(4), name="read_ptr")
read_ptr_next = post_increment(read_ptr, can_read)  # returns rp+1 if can_read else rp
# Use read_ptr_next as the FIFO index — matches the verilog blocking-race semantics.
```

### 4. Probe-mode for the Simulator

`sim.step()` returns immediately. For debugging, it'd help to have:
```python
sim.step_with_probe(["present_state", "fifo_0_1", "count_0"])
```
that returns the post-step values of the named signals as a dict. Saves
the 16 lines of `sim.get(name) for name in [...]` boilerplate per cycle.

### 5. A `probe_against(verilog_path, vectors_path)` end-to-end test

Spirehdl already has a verilator-output mode. A standardized "co-simulate
this Python module against this verilog with these vectors and report
the first cycle where any output diverges" workflow would be the
fastest debug path. The two-file dance I used (`spire_trace.py` +
`verilog_trace.sv`) is recreatable but every translation hits it.

## File structure (kept for future debug runs)

```
benchmarks/dr_rtl_spirehdl/router/_debug/
├── DEBUGGING.md          # this file
├── spire_trace.py        # spirehdl Simulator harness, dumps named signals
├── verilog_trace.sv      # verilator probe harness, dumps hierarchical refs
├── spire_trace.log       # latest spire trace
├── verilog_trace.log     # latest verilog trace
└── obj_dir/              # verilator build artifacts
```

To rerun:
```bash
cd benchmarks/dr_rtl_spirehdl/router/_debug

# Spire side
python spire_trace.py > spire_trace.log

# Verilog side
verilator --binary --top-module probe -Wno-fatal -Wno-WIDTH -Wno-UNOPTFLAT \
  -Wno-LATCH -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-CASEINCOMPLETE \
  -Wno-SELRANGE -Wno-COMBDLY -Wno-MULTIDRIVEN -Wno-IMPLICIT \
  -Wno-SYNCASYNCNET -j 0 -o probe_exe \
  /workspaces/rtl_scout/benchmarks/dr_rtl/router/context/starting_point.v \
  verilog_trace.sv
./obj_dir/probe_exe > verilog_trace.log

# Compare
diff <(grep -oE "cyc=[0-9]+|count_0=[0-9]+|incr0=[0-9]+" spire_trace.log) \
     <(grep -oE "cyc=[0-9]+|cnt0=[0-9]+|incr0=[0-9]+" verilog_trace.log)
```

The `_debug/` directory is excluded from agent workspaces by the
`_*` filename convention; `core/runner.py` and
`core/benchmarks.py:discover_benchmarks` both skip paths whose segments
start with `_`.
