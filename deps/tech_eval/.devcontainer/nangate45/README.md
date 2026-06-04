# Vendored NanGate45 simulation cells (`cells.v`)

`cells.v` is a behavioral Verilog model of the **NanGate45 Open Cell Library** standard cells
(100 cells, e.g. `AND2_X1`, `DFF_X1`, …; each is a simple functional model such as
`assign ZN = (A1 & A2);`). It is used **only** for *gate-level / netlist* simulation of nangate45
synthesis results.

## Why it's vendored here

The base EDA image (`deps/tech_eval/.devcontainer/Dockerfile`) originally obtained this file by
cloning `https://github.com/oscc-ip/nangate` into `/app/nangate`. **That repository has been
deleted from GitHub (HTTP 404 — "Repository not found").** As a result the clone now fails and the
base image build aborts. We therefore vendor the single file the flow actually needs and `COPY` it
into the image instead of cloning a now-missing repo — removing the external dependency entirely.

## How it's used

- The Dockerfile copies it to `/app/nangate/sim/cells.v`.
- `tech_eval`'s `ppa_extract/core/template.py` references it from the `NANGATE45` technology config:
  `verilator_netlist_flags=["/app/nangate/sim/cells.v"]`.

Note this file is required **only** for nangate45 *netlist* simulation. nangate45 PPA (synthesis,
timing, power) uses the liberty/LEF files bundled with OpenROAD-flow-scripts
(`/prog/OpenROAD-flow-scripts/flow/platforms/nangate45/...`), and the project default technology is
**asap7**, so neither the default flow nor the test suite depends on this file.

## Provenance / license

The NanGate45 Open Cell Library is an openly available standard-cell library; these are trivial
behavioral simulation models of its cells (name → boolean function) and are redistributed widely in
open EDA toolchains. No license header was present on the original file.
