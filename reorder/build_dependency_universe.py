#!/usr/bin/env python3
"""
Build a dependency-universe index for triage.

Reads only reorder artifacts:
  - index.json
  - manifest.json
  - batch-*/graph-*.json
  - batch-*/resolution-*.json

Writes:
  - dependency-universe.json

The output is review-only and deterministic. It does not edit source TeX,
knowledge.json, graph-edges.json, graph files, or resolution files.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
INDEX = HERE / "index.json"
MANIFEST = HERE / "manifest.json"
OUT = HERE / "dependency-universe.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def direct_dependencies(graph: dict[str, Any]) -> list[str]:
    return [dep["id"] for dep in graph.get("current_dependencies", []) if dep.get("id")]


def resolution_dependencies(resolution: dict[str, Any]) -> list[str]:
    return [dep for dep in resolution.get("dependencies", []) if isinstance(dep, str) and dep]


def build_closure(direct: dict[str, list[str]]) -> tuple[dict[str, list[str]], dict[str, dict[str, list[str]]]]:
    closure_cache: dict[str, set[str]] = {}

    def closure(term: str) -> set[str]:
        if term in closure_cache:
            return closure_cache[term]
        seen: set[str] = set()
        stack = list(direct.get(term, []))
        while stack:
            dep = stack.pop()
            if dep in seen:
                continue
            seen.add(dep)
            stack.extend(direct.get(dep, []))
        closure_cache[term] = seen
        return seen

    closures: dict[str, list[str]] = {term: sorted(closure(term)) for term in sorted(direct)}
    via: dict[str, dict[str, list[str]]] = {}
    for term in sorted(direct):
        via[term] = {}
        for ancestor in direct.get(term, []):
            reachable = {ancestor}
            reachable.update(closure(ancestor))
            for dep in reachable:
                via[term].setdefault(dep, []).append(ancestor)
        via[term] = {dep: sorted(ancestors) for dep, ancestors in sorted(via[term].items())}
    return closures, via


def main() -> int:
    index = load_json(INDEX)
    manifest = load_json(MANIFEST)
    vocabulary = {row["id"]: {"kind": row.get("kind", ""), "title": row.get("title", ""), "root": row.get("root", "")} for row in index}

    direct: dict[str, list[str]] = {}
    graph_records: dict[str, dict[str, Any]] = {}
    resolution_records: list[tuple[str, Path, dict[str, Any], dict[str, Any]]] = []
    graph_count = 0
    resolution_count = 0

    for entry in manifest:
        batch = entry["batch"]
        batch_dir = HERE / batch
        for graph_path in sorted(batch_dir.glob("graph-*.json")):
            graph = load_json(graph_path)
            term = graph.get("term")
            if not term:
                continue
            graph_count += 1
            deps = direct_dependencies(graph)
            direct[term] = deps
            graph_records[term] = {
                "batch": batch,
                "graph": graph_path.name,
                "graph_id": graph.get("graph_id", ""),
                "volume": graph.get("volume", ""),
                "chapter": graph.get("chapter", ""),
                "kind": graph.get("kind", ""),
                "title": graph.get("title", ""),
                "direct_dependencies": deps,
            }
        for resolution_path in sorted(batch_dir.glob("resolution-*.json")):
            graph_path = resolution_path.with_name(resolution_path.name.replace("resolution-", "graph-"))
            if not graph_path.exists():
                continue
            graph = load_json(graph_path)
            resolution = load_json(resolution_path)
            resolution_count += 1
            resolution_records.append((batch, resolution_path, graph, resolution))

    closures, via = build_closure(direct)

    proposed_additions: list[dict[str, Any]] = []
    for batch, resolution_path, graph, resolution in resolution_records:
        term = resolution.get("term") or graph.get("term")
        current = set(direct_dependencies(graph))
        proposed = resolution_dependencies(resolution)
        for dep in sorted(dep for dep in proposed if dep not in current):
            already_transitive = dep in set(closures.get(term, []))
            creates_cycle = term in set(closures.get(dep, [])) or dep == term
            proposed_additions.append(
                {
                    "batch": batch,
                    "graph": resolution_path.name.replace("resolution-", "graph-"),
                    "resolution": resolution_path.name,
                    "term": term,
                    "dependency": dep,
                    "dependency_title": vocabulary.get(dep, {}).get("title", dep),
                    "already_direct": dep in current,
                    "already_transitive": already_transitive,
                    "via_direct_dependencies": via.get(term, {}).get(dep, []),
                    "creates_cycle": creates_cycle,
                    "verdict": resolution.get("verdict", ""),
                    "confidence": resolution.get("confidence"),
                }
            )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "index": "index.json",
            "manifest": "manifest.json",
            "graphs": "batch-*/graph-*.json",
            "resolutions": "batch-*/resolution-*.json",
        },
        "summary": {
            "vocabulary_nodes": len(vocabulary),
            "graph_nodes": graph_count,
            "resolution_files": resolution_count,
            "direct_edges": sum(len(deps) for deps in direct.values()),
            "proposed_additions": len(proposed_additions),
            "proposed_already_transitive": sum(1 for row in proposed_additions if row["already_transitive"]),
            "proposed_creates_cycle": sum(1 for row in proposed_additions if row["creates_cycle"]),
        },
        "nodes": graph_records,
        "direct_dependencies": {term: deps for term, deps in sorted(direct.items())},
        "transitive_dependencies": closures,
        "via_direct_dependencies": via,
        "proposed_additions": proposed_additions,
    }
    write_json(OUT, payload)
    print(f"Wrote {OUT}")
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
