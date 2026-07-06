---
name: design-db-dispatch
description: Delegate the optimization of ONE design-DB slot to the rtl-subcircuit subagent via the task tool. Dispatch only delegates — analyzing the result afterwards is a separate design-db-inspect step.
---

# Dispatch a slot to the rtl-subcircuit subagent

You coordinate; the subagent implements. Dispatch is **delegation only** — it does not analyze
results. What changed in the slot is read afterwards, from the DB, with the design-db-inspect
skill; the subagent's self-description is never the result.

## Protocol (one slot at a time, sequential)

1. **Slot verified?** A sequential slot with no verification set needs the dv-prep leg first
   (design-db-dv-prep skill) — dispatching an optimizer at an unverified slot just yields
   refused inserts.
2. **Seed the floor** (idempotent): `spire db seed --slot <key>` — so a correct-but-worse
   result can never displace the original.
3. **Delegate via the task tool** to the `rtl-subcircuit` subagent. The task prompt carries only
   the pointer — nothing else travels through the agent channel:
   > Optimize design-DB slot `<spec_key>`. Objective: minimize `<objective>`. Work in
   > `work/<spec_key>/`. Budget guidance: `<minutes>` minutes — check `./remaining_time`.
4. The subtask returns the slot key it worked — that is the dispatch's whole output.
5. **Afterwards, separately**: `spire db show <key> --pareto` (design-db-inspect skill) to see
   what was admitted and whether the best beat the seeded `original:*`.

## Rules

- One slot per dispatch; dispatch slots **sequentially** (concurrent inserts into one DB are not
  supported yet).
- Do not retry a failed dispatch in a loop — inspect the slot, note what happened, move on.
- Never bypass the subagent by editing the DB; every implementation enters through the gate.
