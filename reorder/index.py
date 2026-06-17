#!/usr/bin/env python3
"""
reorder/index.py
================
Build the dependency-audit work tree from the published knowledge graph.

Reads (repo root, i.e. the parent of this folder):
    knowledge.json      enriched nodes
    graph-edges.json    edges (depends_on is the relation we audit)

Writes (inside reorder/):
    index.json          one compact record per node {id, kind, title, gloss, root}
                        -- the LLM reads this ONCE, then resolves ids against it.
    manifest.json       ordered list of batches (batch dir, volume, chapter, #graphs)
    batch-XXXX/graph-NNNN.json
                        ONE node + its DIRECT dependencies (with glosses).
                        NOT the full transitive closure -- the deep structure is
                        verified deterministically elsewhere; the model only needs
                        the local neighbourhood to judge whether THIS node's direct
                        deps are the right set.

Ordering
--------
Batches are whole chapters, processed highest-volume-first. metadata.chapters is
emitted volume-ascending by the extractor, so we simply reverse it. A chapter's
volume label (for records) comes from the optional reorder/chapter-volumes.json
map; unmapped chapters get "?" and still process in the right order.

This script is deterministic and has no third-party dependencies.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
KNOWLEDGE = ROOT / "knowledge.json"
EDGES = ROOT / "graph-edges.json"

# kinds that get an audit graph (everything statement-bearing)
AUDIT_KINDS = {"Definition", "Theorem", "Lemma", "Proposition", "Corollary", "Axiom"}
WS = re.compile(r"\s+")


def gloss(n: dict) -> str:
    for field in ("source_text", "text_preview", "statement_display", "name"):
        v = (n.get(field) or "").strip()
        if v:
            return WS.sub(" ", v)[:200]
    return ""


def root_label(n: dict) -> str:
    rk = str(n.get("root_kind", "")).lower()
    if n.get("kind") == "Axiom" or rk == "axiom":
        return "axiom"
    if n.get("definitional_root") or rk in ("definitional", "primitive"):
        return "definitional_truth"
    return ""


def title_of(n: dict) -> str:
    return n.get("name") or n.get("title") or n.get("id")


def load_chapter_volumes() -> dict:
    """Return a flat {chapter: volume-label} map.

    Accepts either a flat JSON object ({"bounding": "iii"}) or the richer schema
    with a nested "chapter_to_volume" block whose values may be full dir names
    ("volume-iii"); the "volume-" prefix is stripped to a bare label.
    """
    p = HERE / "chapter-volumes.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    raw = data.get("chapter_to_volume", data) if isinstance(data, dict) else {}
    out = {}
    for chap, vol in raw.items():
        if not isinstance(vol, str):
            continue
        out[chap] = vol[len("volume-"):] if vol.startswith("volume-") else vol
    return out


def main() -> None:
    K = json.loads(KNOWLEDGE.read_text(encoding="utf-8"))
    nodes = K["nodes"]
    by_id = {n["id"]: n for n in nodes}

    deps: dict[str, list[str]] = {}
    for e in json.loads(EDGES.read_text(encoding="utf-8")):
        if e.get("kind") == "depends_on":
            deps.setdefault(e["from"], []).append(e["to"])

    chapter_volume = load_chapter_volumes()

    # --- index.json: the LLM's one-shot vocabulary ---
    index = [
        {"id": n["id"], "kind": n["kind"], "title": title_of(n),
         "gloss": gloss(n), "root": root_label(n)}
        for n in nodes
    ]
    (HERE / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- chapter order: volume-ascending -> reverse = highest-volume-first ---
    meta_chaps = K.get("metadata", {}).get("chapters", [])
    ordered, seen = [], set()
    for c in meta_chaps:
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)
    ordered = ordered[::-1]
    # any chapter present in nodes but missing from metadata -> append at end
    for n in nodes:
        c = n.get("chapter")
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)

    audit_nodes = [n for n in nodes if n.get("kind") in AUDIT_KINDS and not n.get("ignored")]
    by_chapter: dict[str, list[dict]] = {}
    for n in audit_nodes:
        by_chapter.setdefault(n.get("chapter") or "_unknown", []).append(n)

    manifest = []
    bi = 0
    for chap in ordered:
        members = by_chapter.get(chap)
        if not members:
            continue
        bi += 1
        batch_dir = HERE / f"batch-{bi:04d}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        members.sort(key=lambda n: (n.get("source", ""), n["id"]))
        vol = chapter_volume.get(chap, "")
        for gi, n in enumerate(members, start=1):
            direct = deps.get(n["id"], [])
            graph = {
                "graph_id": f"{bi:04d}-{gi:04d}",
                "volume": vol,
                "chapter": chap,
                "section": n.get("section", ""),
                "term": n["id"],
                "kind": n["kind"],
                "title": title_of(n),
                "root": root_label(n),
                "statement": (n.get("statement_display") or "").strip(),
                "current_dependencies": [
                    {"id": d,
                     "title": title_of(by_id[d]) if d in by_id else d,
                     "kind": by_id.get(d, {}).get("kind", ""),
                     "root": root_label(by_id[d]) if d in by_id else ""}
                    for d in direct
                ],
            }
            (batch_dir / f"graph-{gi:04d}.json").write_text(
                json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest.append({"batch": f"batch-{bi:04d}", "volume": vol,
                         "chapter": chap, "graphs": len(members)})
        print(f"batch-{bi:04d}  vol={vol or '?':>4}  {chap:<38} graphs={len(members)}")

    (HERE / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote index.json ({len(index)} nodes), {bi} batches, manifest.json")


if __name__ == "__main__":
    main()
