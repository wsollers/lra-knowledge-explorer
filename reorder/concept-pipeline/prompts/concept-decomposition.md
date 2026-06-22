# Concept Decomposition Prompt

You are decomposing one knowledge-graph node from undergraduate real analysis
notes. Work from the supplied packet only.

## Task

Read the node statement and produce a structured mathematical decomposition.
Do not choose graph labels directly unless they are supplied in the packet as
matching candidates. The goal is to identify concepts first; label matching and
cycle/transitive checks happen later.

## Output

Return one JSON object:

```json
{
  "schema_version": "concept-decomposition-1",
  "node": "label",
  "ambient_environment": [],
  "mathematical_structures": [],
  "instances": [],
  "operations_relations_predicates": [],
  "statement_conditions": [],
  "statement_assertions": [],
  "statement_dependency_concepts": [
    {
      "concept": "",
      "role": "statement",
      "reason": "",
      "confidence": "high|medium|low"
    }
  ],
  "proof_dependency_concepts": [
    {
      "concept": "",
      "role": "proof_definition|proof_fact|proof_axiom",
      "reason": "",
      "confidence": "high|medium|low"
    }
  ],
  "not_dependencies": [
    {
      "concept": "",
      "reason": ""
    }
  ],
  "floor_mentions": [
    {
      "concept": "",
      "source": "definitional_root|virtual_structure|scope_floor",
      "emit_dependency": false,
      "reason": ""
    }
  ],
  "questions": []
}
```

## Policy

- A statement dependency is needed to state or parse the node precisely.
- A proof dependency is useful to prove the node but is not needed to state it.
- For definitions, usually leave proof dependencies empty.
- For theorem-like nodes, proof dependencies inferred from the statement alone
  should be marked `medium` or `low` unless the fact is explicitly named.
- Do not emit the virtual propositional L-structure as a graph dependency.
- Use the virtual propositional L-structure only to avoid repeatedly unpacking
  ordinary semantic background.
- If a concept is a policy definitional root, record it in `floor_mentions`
  rather than `statement_dependency_concepts`, unless the node is explicitly
  about that root.
