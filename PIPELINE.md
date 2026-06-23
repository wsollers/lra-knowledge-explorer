# Theorem Explorer — Extraction Pipeline

## Overview

The knowledge explorer is rebuilt automatically whenever any `lra-*` repository
pushes to `main`. The pipeline runs in GitHub Actions, checks out the split
`lra-volume-*` repositories, extracts structured knowledge from their live
LaTeX source, and publishes the result to GitHub Pages at:

```
https://wsollers.github.io/lra-knowledge-explorer/
```

---

## Manual trigger

Go to **Actions → Rebuild Knowledge Explorer → Run workflow**.

---

## Triggering from other repos

Each `lra-*` repo sends a `repository_dispatch` event with type `lra-rebuild`
when it pushes to `main`. Add this step to any repo's CI workflow:

```yaml
- name: Trigger knowledge explorer rebuild
  uses: peter-evans/repository-dispatch@v3
  with:
    token: ${{ secrets.SYNC_PAT }}
    repository: wsollers/lra-knowledge-explorer
    event-type: lra-rebuild
```

---

## Pipeline stages

**Pass 1** — `scripts/extract_lra_chapter.py`

Walks each chapter's live `notes/index.tex` and `proofs/index.tex` closures,
extracts every
`definition`, `theorem`, `lemma`, `proposition`, `corollary`, and `axiom`
environment (including those nested inside `tcolorbox`), captures all trailing
`remark*` blocks, and matches each theorem to its proof file. Writes per-chapter
seed files into `<chapter>/.explorer/`.

**Pass 2** — `scripts/seed_to_knowledge_json_v3_fixed6.py`

Reads the seed files, interprets house-style remark blocks, extracts proof
sketches and step lists, builds dependency/implication/equivalence edges,
and writes explorer-ready JSON.

**Merge** — `scripts/run_extraction.py`

Combines per-chapter outputs into `knowledge.json` and `graph-edges.json`.
The runner fails hard if an expected split volume repository, chapter,
`notes/index.tex`, or `proofs/index.tex` is missing.

---

## Chapters extracted

```
volume-i/propositional-logic
volume-ii/natural-numbers
volume-ii/rationals
volume-iii/analysis/bounding
volume-iii/analysis/functions
volume-iii/analysis/continuity
volume-iii/analysis/differentiation
```

To add more chapters, edit the `CHAPTERS` list in `scripts/run_extraction.py`.

---

## Repo layout

```
.github/workflows/rebuild.yml   — CI: extract + deploy
scripts/
  extract_lra_chapter.py        — Pass 1: LaTeX → seed JSON
  seed_to_knowledge_json_v3_fixed6.py  — Pass 2: seed → explorer JSON
  run_extraction.py             — orchestrator
knowledge-explorer.html         — main interactive explorer
real-analysis-explorer.html     — alternate explorer UI
index.html                      — redirect → knowledge-explorer.html
knowledge.json                  — generated (auto-committed by CI)
graph-edges.json                — generated (auto-committed by CI)
```
