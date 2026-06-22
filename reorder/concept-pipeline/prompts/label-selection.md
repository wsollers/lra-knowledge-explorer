# Direct Label Selection Prompt

You are selecting exact dependency labels for one propositional-logic node.
Work only from the supplied packet.

## Goal

Choose exact graph labels from `label_universe` for:

- statement dependencies needed to state the node precisely;
- proof dependencies needed to prove theorem-like nodes but not needed to state
  them;
- existing direct dependencies that should be removed from statement
  dependencies because they are proof-only, redundant, or wrong.

Do not invent labels. Every `target` must be an `id` from `label_universe` or
`current_direct_dependencies`.

## Output

Return one JSON object:

```json
{
  "schema_version": "direct-label-selection-1",
  "node": "label",
  "statement_dependency_adds": [
    {
      "target": "label-from-universe",
      "reason": "",
      "confidence": "high|medium|low"
    }
  ],
  "statement_dependency_removes": [
    {
      "target": "existing-direct-label",
      "reason": "",
      "replacement": "proof|redundant|wrong|investigate",
      "confidence": "high|medium|low"
    }
  ],
  "proof_dependencies": [
    {
      "target": "label-from-universe",
      "reason": "",
      "confidence": "high|medium|low"
    }
  ],
  "unchanged_existing_dependencies": [
    {
      "target": "existing-direct-label",
      "reason": ""
    }
  ],
  "rejected_candidates": [
    {
      "target": "label-from-universe",
      "reason": ""
    }
  ],
  "uncertain": [
    {
      "concept_or_target": "",
      "reason": ""
    }
  ]
}
```

## Policy

- Statement dependencies are needed to parse or state the node.
- Proof dependencies support proofs but are not part of the statement.
- For definitions, proof dependencies should usually be empty.
- For theorem-like nodes, do not add every proof ingredient unless it is a
  named fact/axiom/definition likely needed in the proof.
- Do not emit accepted definitional roots unless the node is explicitly about
  that root.
- Do not emit virtual floor ids as graph dependencies.
- Prefer exact existing labels from the universe over conceptual paraphrases.
- If an existing direct dependency is only proof support, put it in both
  `statement_dependency_removes` and `proof_dependencies`.
- If a dependency is already direct and should remain, list it under
  `unchanged_existing_dependencies`, not as an add.
