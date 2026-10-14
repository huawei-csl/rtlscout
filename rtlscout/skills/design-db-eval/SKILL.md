---
name: design-db-eval
description: Advisory correctness check of a candidate design against a slot's verification oracle — PASS/FAIL, admits nothing, writes nothing. The iteration step before design-db-insert.
---

# Check a candidate against a slot (advisory)

Runs exactly the check the insert gate applies — the slot's set oracle (CEC for combinational
slots, the frozen trace testbench for sim tiers) — but **admits and writes nothing**. Iterate
here until PASS, then submit through the gate (design-db-insert skill).

```
spire db verify cand.py --slot <name|key>     # spire design: elaborated exactly as insert would
spire db verify cand.v  --slot <name|key>     # Verilog candidate
```

Output: `{"verdict": "PASS"|"FAIL", …}` (exit 2 on FAIL, with the reason). A "no verification
set" error means the slot's oracle isn't configured — for sequential slots see the
design-db-dv-prep skill.

## Notes

- Advisory means advisory: a PASS here does not admit the design. `spire db insert` re-runs the
  same verification authoritatively and is the only path into the DB.
- Port mismatches fail fast with the expected port list — fix the interface, not the oracle.
