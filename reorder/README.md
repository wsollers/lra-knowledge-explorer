# reorder/ — dependency-graph audit pipeline

Deterministic where the truth is structural; the model only where it is semantic.
Nothing here edits `.tex` or `.json` source — the model **proposes**, a human applies.

## Flow

1. `python reorder/index.py`
   Reads `../knowledge.json` + `../graph-edges.json`. Writes:
   - `index.json` — compact vocabulary (`id, kind, title, gloss, root`), read once.
   - `batch-XXXX/graph-NNNN.json` — one node + its **direct** deps. Batches are whole
     chapters, **highest volume first**.
2. **Semantic pass** — an agent reads `PROMPT.md` (verbatim, every run), then `index.json`
   once, then each `graph-NNNN.json`, writing a sibling `resolution-NNNN.json`.
3. `python reorder/apply_resolution.py batch-XXXX --batch`
   Routes resolutions by consequence:
   - `ok` → logged.
   - `reorder` → **only if the set is unchanged** → `patches.yaml` (idempotent,
     auto-runnable; the order is a deterministic canonical sort computed here).
   - `change` (or a `reorder` whose set secretly differs — the **guard**) →
     `suspicious.yaml` for human review. Low-confidence changes → `focus-queue.yaml`.
   Each resolution also renders `graph-NNNN.tree.txt` and appends to `progress.yaml`.
4. `python reorder/build_dependency_universe.py`
   Builds `dependency-universe.json`, a deterministic review index of direct
   dependencies, transitive dependencies, and proposed additions. Use it during
   triage to see whether a proposed edge is already present through the current
   dependency tree or would create a cycle.
5. Apply reviewed `patches.yaml`, then run the **governance validators** as the gate,
   **per batch**, before committing — a bad resolution is caught before it compounds.

Use `TRIAGE_PROMPT.md` between steps 3 and 5 when reviewing `suspicious.yaml` or
completed `resolution-*.json` files. It classifies proposed changes as applied,
rejected, or investigate, with guidance for ancestor-owned dependencies.

## The cursor

The filesystem *is* the cursor: a batch with no `resolution-*.json` is unfinished.
`progress.yaml` is the append-only log. Chapter order is `metadata.chapters` reversed
(the extractor emits it volume-ascending), so the audit walks highest volume first.

## chapter-volumes.json (optional)

Ordering works without it. To put real volume labels in records, generate it once
from the **monorepo** root:

```bash
python - <<'PY'
import os, json
m={}
for vol in sorted(d for d in os.listdir('.') if d.startswith('volume-')):
    for dp,_,_ in os.walk(vol):
        if os.path.basename(dp)=='notes' and os.path.basename(os.path.dirname(dp)) not in ('proofs','notes'):
            m[os.path.basename(os.path.dirname(dp))]=vol.split('-',1)[1]
json.dump(dict(sorted(m.items())), open('chapter-volumes.json','w'), indent=2)
PY
```

Drop the result in `reorder/`.

## policy.json

The accepted-exceptions store, so reviewed decisions stop re-flagging:
`definitional_roots` (accepted primitives), `accepted_leaf_definitions`, and
`well_definedness_dependencies` (licensed definition→theorem obligations).
