# Concept Pipeline

Experimental workspace for dependency inference by concept extraction.

This folder is for derived reports, prompts, and intermediate artifacts only.
It should not contain edits to TeX, `knowledge.json`, `graph-edges.json`, or
generated source batches.

## Goal

Split dependency review into mechanical and semantic stages:

1. Extract statement/proof concepts from a node statement.
2. Match concepts against the local knowledge library.
3. Validate matched labels against the cumulative graph.
4. Triage only ambiguous or policy-sensitive cases with the model.
5. Record accepted changes with `reorder/tools/record_delta.py`.

## Directories

- `concepts/` - model or tool output listing conceptual dependencies by node.
- `floors/` - scoped floor/config files, including virtual ambient structures.
- `invocations/` - deterministic model-input packets generated from source data.
- `matches/` - concept-to-label match candidates from the local library.
- `audits/` - graph hygiene and dedupe reports.
- `prompts/` - prompt templates for concept extraction and triage.

## Propositional Logic Packets

Prepare concept-decomposition packets with:

```powershell
python reorder\concept-pipeline\prepare_prop_logic_invocations.py
```

This reads `knowledge.json`, `reorder/policy.json`, and
`floors/propositional-logic.json`, then writes deterministic JSON packets under:

```text
reorder/concept-pipeline/invocations/propositional-logic/
```

Rerunning the command replaces packets with the same content and filenames when
the inputs have not changed.

## Direct Label Selection

The preferred workflow is direct semantic label selection. It gives the model the
floor, the reviewed node, current direct dependencies, and a compact Volume I
label universe, then asks for exact dependency labels.

Prepare direct-label-selection packets with:

```powershell
python reorder\concept-pipeline\prepare_prop_logic_label_selection.py
```

This writes deterministic packets under:

```text
reorder/concept-pipeline/label-selection/propositional-logic/
```

Use `prompts/label-selection.md` with one packet at a time, or with a small
batch of packets, and write model outputs separately from the packets. The graph
audit stage should then validate selected labels before anything is recorded in
`working-delta.json`.

## Boundary

This pipeline may generate candidate reports and resolution drafts. Accepted
statement adds, statement removes, and proof dependencies must still be recorded
through the existing working-delta workflow:

```powershell
python reorder\tools\record_delta.py --action add ...
python reorder\tools\record_delta.py --action remove ...
python reorder\tools\record_delta.py --action proof ...
```
