---
name: design-db-insert
description: Submit a candidate implementation to a design-DB slot through the verification gate. Spire-first — insert a .py design (source stored, correct by construction); Verilog also accepted. Seed the baseline floor first.
---

# Insert a design into a slot (the gate)

Every implementation enters a slot through **one gate**: it is verified against the slot's
oracle, structurally deduped, metric-stamped, and only then admitted. Rejections tell you why.
**Only admitted designs count** — nothing else you produce has any effect on selection.

## Author in spire (primary path)

Spire is this ecosystem's design language; Verilog is only the intermediate representation.
Write a python design file defining `build() -> Netlist/Component` and insert it directly:

```
spire db insert cand.py --slot <name|key> --source agent:<who-you-are>
```

`--source` is provenance and must be honest: use your own role (the primary agent inserts as
`agent:rtl`); `agent:rtl-subcircuit` is reserved for the dispatched subagent. Prefer not to
implement slot candidates yourself at all — delegate via the design-db-dispatch skill.

The gate elaborates `build()` itself — the generated Verilog becomes the canonical `design.v`,
and your **python source is stored with the design** (plus its project-local import helpers),
correct by construction. The slot's `starting_point.py` (at `<db_root>/v1/<key>/`) shows the
current implementation in exactly this form — a good starting point.

## Verilog (fallback)

External or handwritten candidates insert the same way (no source stored):

```
spire db insert cand.v --slot <name|key> --source <who-made-it>
```

## Seed the floor first

Before filling a slot, admit its own golden as the baseline once (idempotent):

```
spire db seed --slot <name|key>
```

This gives selection a *floor* — a correct-but-worse candidate can never displace the original.

## Rules

- Port names/widths must match the slot spec exactly (`spec.json`); the module name is free.
- Never write into the DB directory by hand; `spire db insert` is the only write path.
- Do not fabricate metrics — the gate stamps them from tooling.
- Submit several structurally *different* correct designs when you can: the DB keeps them all
  and selection picks per objective (the area/delay Pareto matters, not just one winner).
- Check a candidate first with the design-db-eval skill (advisory, writes nothing).
