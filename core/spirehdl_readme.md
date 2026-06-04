# SpireHDL

A Python EDSL that compiles concise, composable hardware descriptions to synthesizable Verilog and AIG/AAG netlists, with a cycle-accurate simulator built in.

- Bit-precise types (`Bool`, `UInt`, `SInt`), shared-expression caching, overloaded operators that read like an HDL.
- `Module` builds ports, wires, and registers and emits Verilog; `Component` packages reusable sub-designs.
- A lightweight Python simulator drives inputs, ticks clocks, and inspects any expression or probe.

## Core modules

- `spirehdl/spirehdl.py` — the expression DSL: types, operators, expression caching.
- `spirehdl/spirehdl_module.py` — structural modeling: `Module`, `Component`, port/wire/register construction, Verilog emission, `IOCollector` for rebuilding packed ports from bit-level signals.
- `spirehdl/spirehdl_simulator.py` — the Python simulator: drive inputs, tick clocks, inspect outputs/internals, capture probes.

## Quick start

### 1. Describe a module

```python
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import Bool, UInt, mux, cat

m = Module("LogicDemo", with_clock=False, with_reset=False)
a = m.input(UInt(8), "a")
b = m.input(UInt(8), "b")
sel = m.input(Bool(), "sel")
sum_ = m.output(UInt(9), "sum")
mask = m.output(UInt(4), "mask")
out = m.output(UInt(8), "out")

sum_ <<= a + b              # automatic width growth
top_bits = cat(a[7], b[7])
mask <<= top_bits           # concatenate slices
a_and_b = a & b
b_or_a = a | b
out <<= mux(sel, a_and_b, b_or_a)

print(m.to_verilog())
```

`Module` checks that every output has a driver and every register has a next-state assignment before emitting Verilog.

**Registers** are created via the standalone `Register` class or `Module.reg(...)`. Both take a `typ` and an optional reset value via the `init=` keyword (the keyword is `init`, not `reset_value` / `reset`). Assign the next-state expression with `<<=`:

```python
from spirehdl.spirehdl import Register, UInt

m = Module("Counter", with_clock=True, with_reset=True)
cnt = Register(UInt(8), init=0, name="cnt")       # or: cnt = m.reg(UInt(8), "cnt", init=0)
cnt <<= cnt + 1                                   # next-state = cnt + 1
m.output(UInt(8), "q") <<= cnt
```

### 2. Simulate the design

```python
from spirehdl.spirehdl_simulator import Simulator

sim = Simulator(m)
sim.set("a", 0x55).set("b", 0x0F).set("sel", 1)
sim.eval()                  # recompute combinational logic
print(sim.peek_outputs())   # {'sum': 0x64, 'mask': 0x9, 'out': 0x05}
```

The simulator tracks inputs, wires, outputs, and registers; supports `eval()` for combinational updates and `step()` for clocked designs; and exposes `peek`, `peek_next`, and signal watching for deeper inspection.

### 3. Integrate with external tooling

Modules can be exported to Verilog, AIG, or AAG for downstream synthesis, equivalence checking, or integration into larger verification environments. Import helpers let you bring optimized or third-party netlists back into SpireHDL for continued composition and simulation.

## Modules and components

- `Component` subclasses package reusable structures. They can materialize new modules (`to_module`), import designs from Verilog or AIG formats (`from_verilog`, `from_aag_lines`), and retag ports as internals (`make_internal`). `get_spec()` drives `IOCollector` regrouping when importing flattened designs.
- `Module` is typically used at the top level or as an intermediate representation while wiring a design. It offers constructors for inputs, outputs, wires, and registers; utilities for enumerating signals; Verilog emission with automatic width fitting; and a `module_analyze()` routine that reports combinational depth and node counts for timing exploration.
- `IOCollector` rebuilds packed buses (e.g., `a[0] … a[N-1]` → `a[N-1:0]`) after reading back designs from AIG/AAG files or external synthesizers.

Short component + hierarchy usage example:

```python
from dataclasses import dataclass
from spirehdl.spirehdl import UInt, Signal
from spirehdl.spirehdl_module import Component

class SimpleAdder(Component):
    def __init__(self, width=8):
        self.width = width
        @dataclass
        class IO:
            a: Signal
            b: Signal
            sum: Signal
        self.io = IO(
            a=Signal(name="a", typ=UInt(width), kind="input"),
            b=Signal(name="b", typ=UInt(width), kind="input"),
            sum=Signal(name="sum", typ=UInt(width + 1), kind="output"),
        )
        self.elaborate()

    def elaborate(self):
        self.io.sum <<= self.io.a + self.io.b

class Sum3Hier(Component):
    def __init__(self):
        @dataclass
        class IO:
            a: Signal
            b: Signal
            c: Signal
            sum: Signal
        self.io = IO(
            a=Signal(name="a", typ=UInt(8), kind="input"),
            b=Signal(name="b", typ=UInt(8), kind="input"),
            c=Signal(name="c", typ=UInt(8), kind="input"),
            sum=Signal(name="sum", typ=UInt(10), kind="output"),
        )
        self.elaborate()

    def elaborate(self):
        add_ab = SimpleAdder(width=8).make_internal()     # first sub-component
        add_abc = SimpleAdder(width=9).make_internal()    # second sub-component
        add_ab.io.a <<= self.io.a
        add_ab.io.b <<= self.io.b
        add_abc.io.a <<= add_ab.io.sum
        add_abc.io.b <<= self.io.c
        self.io.sum <<= add_abc.io.sum

module = Sum3Hier().to_module(name="Sum3Hier")
print(module.to_verilog())  # one top module, built from internal components
```

### Hierarchical design with components

Components are ideal for assembling hierarchical designs: instantiate another component, adapt its IO, even swap in a pre-synthesized netlist without leaving Python. A common pattern wraps a reusable building block with `make_internal()` so auxiliary logic can surround the core implementation while exposing a compact public interface. A related flow imports an external AIG module, converts it into a `Component`, and calls `from_module(..., make_internal=True)` so the imported logic behaves like a native SpireHDL block inside a larger generator. These techniques extend to Verilog importers and make it straightforward to mix SpireHDL-authored code with IP produced by external flows.

## Aggregate data types

SpireHDL includes structured, bit-packable aggregates for cleaner interfaces and bulk assignments:

- `HDLAggregate` defines the base "pack to bits" API that powers all aggregates.
- `Array` offers N-dimensional indexing, packed assignment (`<<=`), and element-wise assignment (`@=`) for nested vectors or aggregates.
- `AggregateRecord` lets you declare bundle-like classes with named fields that remain packable to a flat bitvector.
- `FixedPoint` wraps a `Wire` or view with explicit total/frac widths and quantization helpers, keeping arithmetic readable while staying hardware-friendly.
- `AggregateRegister` stores any aggregate in a single register while preserving a structured view via `.value`/`.Q`.

Example:

```python
from spirehdl.aggregate.aggregate_array import Array
from spirehdl.aggregate.aggregate_record import AggregateRecord
from spirehdl.aggregate.aggregate_fixed_point import FixedPoint, FixedPointType
from spirehdl.aggregate.aggregate_register import AggregateRegister
from spirehdl.spirehdl import UInt, Wire

class Bus(AggregateRecord):
    data = Wire(UInt(8))
    valid = Wire(UInt(1))

payload = Array([Bus(), Bus()])
acc = FixedPoint(FixedPointType(width_total=16, width_frac=8))
acc_reg = AggregateRegister(FixedPoint, acc.ftype, name="acc_reg")

acc_reg <<= acc            # packed register write
payload[1] @= payload[0]   # element-wise copy between bundles
```

## Simulation notes

The simulator supports both combinational and sequential designs:

- `eval()` recomputes combinational logic and captures registered probes.
- `set()` and `get()` drive or inspect signals by name.
- `step()` advances the clock, committing register next-state expressions while honoring asynchronous resets.
- `watch()` and `peek_next()` provide scope-style visibility for debugging complex pipelines.

## Slices

Indexing follows Python conventions. For example `sig[4:7]` creates a new expression containing bits 4 and 5 (counted from LSB) of the original expression `sig`.

## Main development flow

1. **Model logic in Python.** Use `Module` at the top level and DSL expressions to capture datapaths, state machines, and control logic.
2. **Factor reusable pieces.** Wrap recurring structures in `Component` subclasses so they can be instantiated, parameterized, or replaced with imported implementations.
3. **Simulate early and often.** Drive stimuli with the simulator, observe register evolution, iterate before handing designs to downstream tools.
4. **Export netlists.** Emit Verilog or AIG/AAG when you are ready for synthesis, formal checking, or integration with external flows.
