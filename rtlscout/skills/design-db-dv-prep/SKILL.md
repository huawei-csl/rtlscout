---
name: design-db-dv-prep
description: Set up the verification oracle for an unverified (typically sequential) design-DB slot — author test stimulus, dry-run it with --check, then freeze it once with honest authorship. Required before any insert into such a slot.
---

# Verification prep for an unverified slot

Combinational slots get a CEC oracle by default at registration. **Sequential** slots register
unverified — inserts are refused until a sim-tier verification is set. That takes an authored
stimulus generator and a one-shot freeze.

## What "freeze" means (why this is one-shot)

Freezing turns the chosen stimulus into the slot's *permanent acceptance oracle*: tooling
simulates the **golden** with it and stores the input+expected-output trace (`vectors.dat`) plus
the replaying testbench (`tb.sv`), read-only. Every later insert is judged against exactly this
trace — so a re-freeze is refused (it would silently swap the yardstick admitted designs were
measured with). Commit only stimulus worth committing.

## Workflow

1. **Author stimulus** — `stimulus.py` defining `generate(ports, n_vectors, seed)`, yielding one
   `{input_name: int}` dict per cycle. You write inputs only; expected outputs always come from
   tooling simulating the golden. Clock/reset are driven by the testbench, not by you. Aim to
   *exercise the block*: reset-adjacent values, corners, wraparound bursts, protocol sequences —
   not just uniform random. Weak stimulus weakens the check for every future design in the slot.
2. **Dry-run, iterate** (writes nothing, preserves the one-shot freeze):
   ```
   spire db set-verification --slot <name|key> --stimulus stimulus.py --check
   ```
3. **Freeze once**, with honest authorship recorded:
   ```
   spire db set-verification --slot <name|key> --stimulus stimulus.py --author agent:rtl-dv-prep [--vectors 64]
   ```

Delegation variant: hand the *authoring* (steps 1-2) to the `rtl-dv-prep` subagent via the task
tool (pass the slot key); it delivers `work/<key>/stimulus.py` and never freezes — you review,
then run step 3 yourself.

## Rules

- The stimulus is stored in the slot and stays open to human review — honest `--author` matters.
- Never freeze over a `--check` iteration loop that hasn't converged; the freeze is final.
