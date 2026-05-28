#!/usr/bin/env python3
"""
run_extraction.py — chapter list for lra-knowledge-explorer CI.
----------------------------------------------------------------
NOTE: The rebuild workflow runs the copy of this script that lives in
Learning-Real-Analysis/theorem-explorer/run_extraction.py — not this one.
This file is kept in sync for reference only.

To add a chapter: update Learning-Real-Analysis/theorem-explorer/run_extraction.py.

Chapters extracted:
  - volume-ii/peano-systems
  - volume-ii/natural-numbers
  - volume-ii/rationals
  - volume-iii/analysis/bounding
  - volume-iii/analysis/functions
  - volume-iii/analysis/continuity
  - volume-iii/analysis/differentiation
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPLORER_DIR = REPO_ROOT / "theorem-explorer"

PASS1_SCRIPT = EXPLORER_DIR / "extract_lra_chapter.py"
PASS2_SCRIPT = EXPLORER_DIR / "seed_to_knowledge_json_v3_fixed6.py"

CHAPTERS = [
    REPO_ROOT / "volume-ii" / "peano-systems",
    REPO_ROOT / "volume-ii" / "natural-numbers",
    REPO_ROOT / "volume-ii" / "rationals",
    REPO_ROOT / "volume-iii" / "analysis" / "bounding",
    REPO_ROOT / "volume-iii" / "analysis" / "functions",
    REPO_ROOT / "volume-iii" / "analysis" / "continuity",
    REPO_ROOT / "volume-iii" / "analysis" / "differentiation",
]

COMBINED_KNOWLEDGE = EXPLORER_DIR / "knowledge.json"
COMBINED_EDGES = EXPLORER_DIR / "graph-edges.json"
COMBINED_ERRORS = EXPLORER_DIR / "proof-errors.json"
COMBINED_EDGE_ERRORS = EXPLORER_DIR / "graph-edge-errors.json"


def run(cmd: list[str], label: str) -> subprocess.CompletedProcess:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode != 0:
        print(f"[ERROR] {label} failed with code {result.returncode}")
    return result


def extract_chapter(chapter_root: Path) -> Path:
    out_dir = chapter_root / ".explorer"
    out_dir.mkdir(parents=True, exist_ok=True)
    run(
        [sys.executable, str(PASS1_SCRIPT), str(chapter_root),
         "--output-dir", str(out_dir)],
        f"Pass 1 — extract: {chapter_root.name}",
    )
    return out_dir


def compile_chapter(chapter_root: Path, explorer_dir: Path) -> Path:
    run(
        [sys.executable, str(PASS2_SCRIPT), str(chapter_root),
         "--output-dir", str(explorer_dir)],
        f"Pass 2 — compile: {chapter_root.name}",
    )
    return explorer_dir / "knowledge.json"


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        print(f"[WARN] Not found: {path}")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def merge_knowledge(chapter_roots: list[Path]) -> None:
    all_nodes: list[dict] = []
    all_edges: list[dict] = []
    all_errors: list[dict] = []
    all_edge_errors: list[dict] = []
    chapter_names: list[str] = []

    for chapter_root in chapter_roots:
        exp = chapter_root / ".explorer"
        k = load_json(exp / "knowledge.json")
        e = load_json(exp / "graph-edges.json")
        pe = load_json(exp / "proof-errors.json")
        ge = load_json(exp / "graph-edge-errors.json")

        if k and "nodes" in k:
            all_nodes.extend(k["nodes"])
            chapter_names.append(k.get("metadata", {}).get("chapter", chapter_root.name))
        if e and isinstance(e, list):
            all_edges.extend(e)
        if pe and "errors" in pe:
            all_errors.extend(pe["errors"])
        if ge and "errors" in ge:
            all_edge_errors.extend(ge["errors"])

    seen_edges: set[tuple] = set()
    deduped_edges: list[dict] = []
    for edge in all_edges:
        key = (edge.get("from"), edge.get("to"), edge.get("kind"))
        if key not in seen_edges:
            seen_edges.add(key)
            deduped_edges.append(edge)

    combined = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "chapters": chapter_names,
            "node_count": len(all_nodes),
            "edge_count": len(deduped_edges),
            "error_count": len(all_errors) + len(all_edge_errors),
            "schema_version": "0.3",
            "script": "run_extraction.py",
        },
        "nodes": all_nodes,
        "edges": deduped_edges,
    }

    COMBINED_KNOWLEDGE.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    COMBINED_EDGES.write_text(
        json.dumps(deduped_edges, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    COMBINED_ERRORS.write_text(
        json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "chapters": chapter_names,
            "error_count": len(all_errors),
            "errors": all_errors,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    COMBINED_EDGE_ERRORS.write_text(
        json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "chapters": chapter_names,
            "error_count": len(all_edge_errors),
            "errors": all_edge_errors,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    if not PASS1_SCRIPT.exists():
        sys.exit(f"[ERROR] Pass 1 script not found: {PASS1_SCRIPT}")
    if not PASS2_SCRIPT.exists():
        sys.exit(f"[ERROR] Pass 2 script not found: {PASS2_SCRIPT}")

    for chapter in CHAPTERS:
        if not chapter.exists():
            print(f"[WARN] Chapter not found, skipping: {chapter}")
            continue
        if not (chapter / "notes").exists():
            print(f"[WARN] No notes/ dir in {chapter}, skipping.")
            continue
        explorer_dir = extract_chapter(chapter)
        compile_chapter(chapter, explorer_dir)

    print("\n[INFO] Merging all chapters into combined knowledge.json ...")
    merge_knowledge(CHAPTERS)


if __name__ == "__main__":
    main()
