# lra-knowledge-explorer

Theorem knowledge explorer for the **Learning Real Analysis** project.

Extracted from `Learning-Real-Analysis/theorem-explorer/`.

## Contents

```
extract_lra_chapter.py        — LaTeX → knowledge JSON extractor
run_extraction.py             — batch extraction runner
seed_to_knowledge_json_v3_fixed6.py  — seed → knowledge.json transformer
clean_explorer.py             — cleans explorer output
knowledge-explorer.html       — interactive HTML graph viewer
real-analysis-explorer.html   — full explorer UI
preview.html                  — preview UI
PIPELINE.md                   — pipeline documentation
knowledge.json                — current knowledge graph
knowledge-seed.json           — seed data
graph-edges.json              — dependency graph edges
```

## Running the extractor

```bash
python scripts/run_extraction.py --repos-root /path/to/workspace-containing-lra-volume-repos
python scripts/build_proof_vault_index.py --vault-root /path/to/lra-proof-vault
```

## Relationship to monorepo

The extraction scripts do not use the `Learning-Real-Analysis` monorepo as a
TeX source. They require local split volume checkouts (`lra-volume-i`,
`lra-volume-ii`, and `lra-volume-iii`) and hard fail if an expected volume,
chapter, `notes/index.tex`, or `proofs/index.tex` is missing.

Extraction reads live TeX files through the same volume governance inventory
provider used by validators, so validation and explorer publication operate on
the same canonical source set.

The HTML viewers are self-contained and load `knowledge.json` and `graph-edges.json` from the same directory.

## Verification Fields

Explorer nodes may include formal verification metadata. The UI accepts either
a nested `verification` object or the equivalent flat fields:

- `verification.system` or `verification_system`
- `verification.status` or `verification_status`
- `verification.module`, `lean_module`, or `verification_module`
- `verification.declaration`, `lean_decl`, or `verification_decl`
- `verification.source_path`, `lean_source`, or `verification_source`
- `verification.lean_code_b64`, `verification.code_b64`, `lean_code_b64`,
  or `verification_code_b64`

The proof modal renders these records in the `Verification` tab. Use `checked`
only for declarations that are accepted by the formal build without
placeholders for that declaration; use `statement` or `pending` otherwise.
