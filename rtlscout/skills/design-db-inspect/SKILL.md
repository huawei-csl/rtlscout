---
name: design-db-inspect
description: Inspect and analyze design-DB slots — list slots, read a slot's designs/metrics/Pareto front, judge whether a fill improved it. Use before dispatching work and again afterwards to see what changed.
---

# Inspect & analyze the design DB

The design DB (resolved via `$SPIREHDL_DB_PATH`, else the nearest/auto-created `./design_db`)
stores *slots*: subcircuits with a golden reference, a verification oracle, and gated,
verified implementations. Everything below is tooling output — trust it over any agent's prose.

## Commands

```
spire db ls                          # all slots: name, class, #designs, spec key, last selection
spire db show <name|key> --pareto    # one slot as JSON: spec, verification, designs, Pareto front
```

Slot references resolve by manifest **name** (e.g. `mul4` — the decorated function's qualname or
the netlist name) or a **unique key prefix** (≥ 8 hex chars); full 64-hex keys are rarely needed.
The manifest itself is at `<db_root>/v1/manifest.json`.

## Analyzing a slot (reading `spire db show <key> --pareto`)

- **`designs`** lists every admitted implementation with its per-system metric blocks
  (`aig` structural stats, `transistors` estimate, any annotated technology like `asap7`).
  `original:*` is the seeded baseline — the selection floor.
- **The best for one objective** (e.g. area) is the min-cost point of the **`pareto`** front —
  read it straight off. The *binding* selection is made deterministically at compile time and
  recorded in the manifest; your inspection is decision-support on trusted numbers.
- **Did a fill improve the slot?** Compare the best admitted design to `original:*`:
  strictly better ⇒ yes; only ties/worse ⇒ the floor holds and the original stays selected.
- Selection is computed at compile time (nothing is recorded in the DB); each
  `./evaluate_design` run leaves `db_selections.jsonl` in the workspace — exactly what
  that compile spliced, one JSON line per slot.

## Rules

- Read-only: never write into the DB directory by hand. Inserts go only through
  `spire db insert` (the verification gate — see the design-db-insert skill).
