---
name: design-db-lean-spec
description: Add a proven-equivalent spec layer to a Lean-gated design-DB slot — a nicer statement of what the slot computes (e.g. integer arithmetic), admitted with `spire db add-spec` after proving NAME.equiv. Makes every later candidate proof easier; append-only.
---

# Add a spec layer

The slot's canonical spec is fixed: `Spec.Correct e := ∀ i, e i = GoldenCircuit.eval i` (or trace
equivalence for clocked slots). A **layer** is a nicer formulation proven equivalent to it, so that
candidate proofs can argue at the integer level instead of bit patterns. Layers are append-only and
never change `Spec.Correct`, so nothing already admitted is affected.

## Files

`NAME.lean` (statement):
```lean
import Interface
open Interface
namespace Mmac
def Correct (eval : Inputs → Outputs) : Prop :=
  ∀ i : Inputs, (eval i).y.toInt = i.c.toInt + i.a.toInt * i.b.toInt   -- one conjunct per output
end Mmac
```
`NAMEProof.lean` (equivalence), the statement exactly `∀ e, NAME.Correct e ↔ Spec.Correct e`
(clocked slots: `∀ {σ : Type} (m : SpireSemantics.Machine Interface.Inputs Interface.Outputs σ), NAME.Correct m ↔ Spec.Correct m`):
```lean
theorem golden : Mmac.Correct GoldenCircuit.eval := by intro i; and_intros <;> (simp [GoldenCircuit.eval]; ac_rfl)
theorem equiv (e : Inputs → Outputs) : Mmac.Correct e ↔ Spec.Correct e := by
  constructor
  · intro h i; have a := h i; have b := golden i
    apply Outputs.ext <;> apply BitVec.toInt_inj.mp <;> simp_all
  · intro h i; rw [h i]; exact golden i
```
A second layer may be proven via the first: `Dot.equiv e := (Dot.via_Mmac e).trans (Mmac.equiv e)`.

## Commands

```
spire db add-spec --slot <slot> NAME NAME.lean NAMEProof.lean --check --workspace work/spec   # dry run, keeps the project
spire db add-spec --slot <slot> NAME NAME.lean NAMEProof.lean --author <your tag>
```
Names: capitalised identifier, not `Spec`/`Interface`/`GoldenCircuit`/`SpireSemantics`, not ending
in `Proof`, unique in the slot. Rejections: `SpecRejected` with the Lean log.

## Rules

- A layer must be *equivalent* to the golden's behaviour — you cannot weaken the gate through a layer.
- Only add a layer you (or later candidates) will actually prove through; every layer is checked
  into the slot forever.
