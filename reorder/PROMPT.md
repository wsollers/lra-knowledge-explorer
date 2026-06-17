# Dependency Audit — Semantic Pass Prompt

This file is the **single source of truth** for the LLM step. Every run starts by
reading this file verbatim so the instructions never drift between invocations.

## Your job

You audit the dependency graph one node at a time. You do **not** edit any source.
You read `index.json` once, then for each `graph-NNNN.json` you decide whether its
**direct** dependencies are the right set, and emit a `resolution-NNNN.json`.

## Inputs

- `index.json` — the entire vocabulary: `{id, kind, title, gloss, root}` per node.
  This is the **only** set of ids you may reference. Never invent an id.
- `batch-XXXX/graph-NNNN.json` — one node: its `statement`, `kind`, `root`, and
  `current_dependencies` (direct only). The deep structure is already verified
  deterministically; you only judge this node's local neighbourhood.

## Rules (do not improvise others)

1. **Closed world.** Every dependency you propose must be an `id` that exists in
   `index.json`. If the concept the statement needs has no node, do not invent one —
   say so in `notes` and leave it for human review.

2. **Ground every change in the text.** For any edge you add or remove, quote the
   exact span of `statement` that licenses it in `licensing_quote`. No quote, no edge.

3. **Definition vs theorem layering.**
   - A **definition's** dependencies are what you need to *state* it. These normally
     bottom out at definitional-truths / primitives, never at an axiom or theorem.
   - **Exception — well-definedness.** A definition *may* depend on a theorem when
     that theorem discharges an obligation needed to *name* the object: existence-
     and-uniqueness ("*the* limit", "*the* gcd"), representative-independence
     (quotient operations), or convergence ("$e^x:=\sum x^n/n!$"). If you accept such
     an edge, state the obligation in `rationale`. A definition leaning on a theorem
     that is merely a *downstream consequence* of the concept is wrong — propose
     deleting it.
   - A **theorem/lemma/prop/cor's** dependencies are what its proof uses; its chain
     should reach an axiom. (Termination is checked deterministically, not by you.)

4. **The completeness trap.** Never route a supremum/infimum *definition* to
   `ax:completeness-of-reals`. Completeness governs the *existence* of suprema, which
   belongs to existence *theorems* (e.g. `thm:lub-property-r`). Leave the definition's
   deps alone and note the observation for the theorem layer.

5. **Lean is ground truth.** If the node carries a Lean formalization, prefer the
   Lean dependency set over your own judgement.

## The three verdicts

- `ok` — the current direct dependency set is correct.
- `reorder` — the **set is correct** but the listing order should change. Return the
  correct set in `dependencies`; you do **not** decide the order — a deterministic
  canonical sort is applied downstream. (If you find yourself adding or removing a
  member, it is **not** a reorder — use `change`.)
- `change` — the set is wrong: something must be added and/or removed.

If you are unsure, set a low `confidence`; low-confidence changes are diverted to a
focused re-run rather than the main review queue.

## Output — write `resolution-NNNN.json` next to the graph

```json
{
  "graph_id": "<copied from the graph>",
  "term": "<the node id>",
  "verdict": "ok | reorder | change",
  "dependencies": ["<the dependency set you believe is correct>"],
  "rationale": "<one or two sentences; required for reorder/change>",
  "licensing_quote": "<verbatim span of the statement that licenses an added edge>",
  "confidence": 0.0,
  "notes": "<optional: concepts with no node, ambiguities, Lean observations>"
}
```

Emit exactly one object per graph. Temperature 0. Do not edit `.tex` or `.json`
source; `apply_resolution.py` turns your verdicts into reviewable patch records.
