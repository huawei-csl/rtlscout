---
name: design-db-dispatch
description: Delegate the optimization of ONE design-DB slot to the rtl-subcircuit subagent via the task tool. Dispatch only delegates — analyzing the result afterwards is a separate design-db-inspect step.
---

# Dispatch a slot to the rtl-subcircuit subagent

You coordinate; the subagent implements. Dispatch is **delegation only** — it does not analyze
results. What changed in the slot is read afterwards, from the DB, with the design-db-inspect
skill; the subagent's self-description is never the result.

## Protocol (per dispatch)

1. **Slot verified?** A sequential slot with no verification set needs the dv-prep leg first
   (design-db-dv-prep skill) — dispatching an optimizer at an unverified slot just yields
   refused inserts.
2. **Seed the floor** (idempotent): `spire db seed --slot <key>` — so a correct-but-worse
   result can never displace the original.
3. **Delegate via the task tool** to the `rtl-subcircuit` subagent. The task prompt carries only
   the pointer (+ workdir, source tag, and optionally a search lens) — nothing else travels
   through the agent channel:
   > Optimize design-DB slot `<spec_key>`. Objective: minimize `<objective>`. Workdir:
   > `work/<spec_key>-<lens>/`. Source tag: `agent:rtl-subcircuit-<lens>`. Lens: <one line —
   > e.g. "minimize logic depth" | "aggressive sharing/area" | "start from the current Pareto
   > designs as prior art" | "from scratch, ignore the starting point">. Budget guidance:
   > `<minutes>` minutes — check `./remaining_time`.
   (Solo dispatch may keep the defaults: workdir `work/<spec_key>/`, tag `agent:rtl-subcircuit`,
   no lens.)
4. The subtask returns the slot key it worked — that is the dispatch's whole output.
5. **Afterwards, separately**: `spire db show <key> --pareto` (design-db-inspect skill) to see
   what was admitted and whether the best beat the seeded `original:*`.

## Rules

- **Delegate — do not implement slot candidates yourself.** Slot implementation belongs to the
  `rtl-subcircuit` subagent (honest provenance depends on it); your job is coordination and,
  afterwards, judging the DB state. Actually invoke the task tool — describing a dispatch is
  not dispatching.
- One slot per dispatch (a dispatch never spans slots). **Parallel dispatch is safe** — the DB
  derives its index from atomically-admitted design dirs, so concurrent inserts (different
  slots or the same slot) can never lose designs, and duplicate discoveries simply dedup.
- **Same-slot parallelism only pays with diversity**: give each child a *distinct* lens,
  workdir (`work/<spec_key>-<lens>/`), and source tag (`agent:rtl-subcircuit-<lens>`).
  Identical twins explore the same space and waste budget — dedup absorbs the collisions, but
  one child with double budget beats two clones. Never assign two children the same workdir.
- Re-evaluate the full design (`./evaluate_design`) after a slot is filled — don't defer all
  re-evaluation to the end of the session (the budget may cut it off).
- Do not retry a failed dispatch in a loop — inspect the slot, note what happened, move on.
- Never bypass the subagent by editing the DB; every implementation enters through the gate.
