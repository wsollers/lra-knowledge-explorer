#!/usr/bin/env python3
"""Build an exclude list for resolutions already satisfied by a fresh graph.

The output is review-only. It does not edit source files or resolution files.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def universe_labels(run_dir: Path) -> set[str]:
    universe = load_json(run_dir / "universe.json")
    nodes = universe.get("nodes", universe)
    values = nodes.values() if isinstance(nodes, dict) else nodes
    return {node.get("label") or node.get("id") or node.get("node_id") for node in values}


def edge_set(run_dir: Path) -> set[tuple[str, str]]:
    data = load_json(run_dir / "combined-edges.json")
    return {(edge["source"], edge["target"]) for edge in data["edges"]}


def build_closure(edges: set[tuple[str, str]]):
    adjacency: dict[str, set[str]] = defaultdict(set)
    for source, target in edges:
        adjacency[source].add(target)

    cache: dict[str, set[str]] = {}

    def closure(source: str) -> set[str]:
        if source in cache:
            return cache[source]
        seen: set[str] = set()
        stack = list(adjacency.get(source, ()))
        while stack:
            item = stack.pop()
            if item in seen:
                continue
            seen.add(item)
            stack.extend(adjacency.get(item, ()))
        cache[source] = seen
        return seen

    return closure


def classify_dependency(term: str, dependency: str, labels: set[str], edges: set[tuple[str, str]], closure) -> str:
    if term not in labels or dependency not in labels:
        return "missing-label"
    if (term, dependency) in edges:
        return "direct"
    if dependency in closure(term):
        return "transitive"
    return "pending"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Fresh governance extraction run directory.")
    parser.add_argument("--review-decisions", type=Path, default=HERE / "review-decisions.json")
    parser.add_argument("--output", type=Path, default=HERE / "fixed-resolution-excludes.json")
    args = parser.parse_args()

    labels = universe_labels(args.run_dir)
    edges = edge_set(args.run_dir)
    closure = build_closure(edges)
    review = load_json(args.review_decisions)

    excluded: list[dict] = []
    partial: list[dict] = []
    missing: list[dict] = []

    for decision in review["decisions"]:
        adds = decision.get("adds") or []
        removes = decision.get("removes") or []
        if not adds and not removes:
            continue

        statuses = [
            {
                "dependency": dep,
                "status": classify_dependency(decision["term"], dep, labels, edges, closure),
            }
            for dep in adds
        ]

        base = {
            "batch": decision["batch"],
            "resolution": decision["resolution"],
            "graph": decision.get("graph"),
            "term": decision["term"],
            "original_decision": decision.get("decision"),
        }

        if any(status["status"] == "missing-label" for status in statuses):
            missing.append({**base, "dependencies": statuses})
            continue

        fixed_adds = bool(adds) and all(status["status"] in ("direct", "transitive") for status in statuses)
        if fixed_adds and not removes:
            excluded.append(
                {
                    **base,
                    "reason": "all proposed additions are already direct or transitive in the fresh graph",
                    "dependencies": statuses,
                }
            )
        elif any(status["status"] in ("direct", "transitive") for status in statuses):
            partial.append(
                {
                    **base,
                    "fixed_dependencies": [s for s in statuses if s["status"] in ("direct", "transitive")],
                    "pending_dependencies": [s for s in statuses if s["status"] == "pending"],
                    "removes": removes,
                }
            )

    summary = {
        "generated_from_run": str(args.run_dir),
        "review_decisions": str(args.review_decisions),
        "policy": (
            "Exclude a resolution from manual sweep only when all proposed additions "
            "are already direct or transitive in the fresh graph and there are no proposed removals."
        ),
        "excluded_resolution_count": len(excluded),
        "partial_resolution_count": len(partial),
        "missing_label_resolution_count": len(missing),
        "excluded_by_original_decision": dict(Counter(item["original_decision"] for item in excluded)),
        "partial_by_original_decision": dict(Counter(item["original_decision"] for item in partial)),
    }

    args.output.write_text(
        json.dumps(
            {
                "summary": summary,
                "exclude_resolutions": excluded,
                "partial_resolutions": partial,
                "missing_label_resolutions": missing,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
