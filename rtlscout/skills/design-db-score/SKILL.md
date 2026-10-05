---
name: design-db-score
description: Technology PPA (e.g. asap7) for stored slot designs — measure-and-annotate in one tool op so the DB can select on metric=<tech>, or --dry-run to just see the numbers. Minutes per design; score finalists, not every candidate.
---

# Score slot designs with technology PPA

Slot selection normally runs on the metrics the insert gate stamps for free (`transistors`,
`aig`). Technology PPA (e.g. **asap7**, via the OpenROAD flow) is measured on demand — it takes
minutes *per design*, so score finalists, not every candidate. This is the one design-DB action
backed by RTLScout tooling (spire has no PDK flow).

## Two modes

**Measure + store** — makes `metric="asap7"` selectable for the slot:

```
scripts/db-score --slot <name|key> [--design <id|prefix>] --technology asap7
```

This runs the asap7 cost flow and **annotates the DB itself, in one tool operation** — the
numbers go from the measuring tool straight into the store.

**Measure only** — see the numbers, write nothing (no DB change, free to use anytime):

```
scripts/db-score --slot <name|key> --design <id|prefix> --technology asap7 --dry-run
```

(`scripts/db-score` is this skill's wrapper; the equivalent raw command is
`python rtlscout_cli.py db-score …` from the RTLScout repo root.)

## Trust rule (why the atomic command matters)

**Never** type PPA numbers into `spire db annotate` yourself — annotate trusts its input, so
hand-entered PPA would be unverifiable. Storing technology numbers happens only through this
measure-and-store command, where the tool that measured them writes them.

## Parts vs whole

`db-score` measures each slot design **in isolation** — a per-part proxy that drives per-slot
selection. The composed design's authoritative PPA is your normal `./evaluate_design` on the
whole; isolated-best parts don't necessarily sum to whole-best, which is why both exist.

## After storing

`@from_design_db(metric="asap7")` / `pick_design(..., metric="asap7")` now work for that slot
— but only annotate a technology onto **all** of a slot's designs (the seeded `original:*`
included) before selecting on it, or unscored designs become ineligible under that metric.
