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
pip install pyyaml
python run_extraction.py --repo-dir /path/to/Learning-Real-Analysis
```

## Relationship to monorepo

The extraction scripts expect the LaTeX volumes to live in `Learning-Real-Analysis`. Point `--repo-dir` at your local clone of the monorepo.

The HTML viewers are self-contained and load `knowledge.json` and `graph-edges.json` from the same directory.
