#!/usr/bin/env python3
"""Check a proposed dependency edge against base and cumulative delta graphs."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REORDER = HERE.parent


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sorted_direct(raw: dict[str, list[str]]) -> dict[str, list[str]]:
    return {source: sorted(set(targets)) for source, targets in raw.items()}


def apply_delta(base_direct: dict[str, list[str]], delta: dict[str, Any]) -> dict[str, list[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for source, targets in base_direct.items():
        graph[source].update(targets)
    for item in delta.get("removes", []):
        source = item.get("source")
        target = item.get("target")
        if source and target:
            graph[source].discard(target)
    for item in delta.get("adds", []):
        source = item.get("source")
        target = item.get("target")
        if source and target:
            graph[source].add(target)
    return {source: sorted(targets) for source, targets in sorted(graph.items())}


def path_to(graph: dict[str, list[str]], source: str, target: str) -> list[str]:
    if source == target:
        return [source]
    queue = deque([(source, [source])])
    seen = {source}
    while queue:
        node, path = queue.popleft()
        for dep in graph.get(node, []):
            if dep == target:
                return path + [dep]
            if dep not in seen:
                seen.add(dep)
                queue.append((dep, path + [dep]))
    return []


def check(graph: dict[str, list[str]], source: str, target: str) -> dict[str, Any]:
    direct = target in graph.get(source, [])
    transitive_path = path_to(graph, source, target)
    cycle_path = path_to(graph, target, source)
    creates_cycle = source == target or bool(cycle_path)
    return {
        "source": source,
        "target": target,
        "already_direct": direct,
        "already_transitive": bool(transitive_path),
        "transitive_path": transitive_path,
        "creates_cycle": creates_cycle,
        "cycle_path_if_added": ([source, target, source] if source == target else [source, target] + cycle_path[1:] if cycle_path else []),
        "valid_add": not direct and not transitive_path and not creates_cycle,
    }


def recommendation(current: dict[str, Any], cumulative: dict[str, Any], missing_source: bool, missing_target: bool) -> str:
    if missing_source or missing_target:
        return "investigate_missing_label"
    if cumulative["creates_cycle"]:
        return "reject_cycle"
    if cumulative["already_direct"]:
        return "reject_already_direct_in_cumulative_graph"
    if cumulative["already_transitive"]:
        return "reject_redundant_in_cumulative_graph"
    if current["already_transitive"]:
        return "reject_redundant_in_base_graph"
    return "candidate_ok_graph_hygiene_only"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=REORDER / "state" / "base-graph.json")
    parser.add_argument("--delta", type=Path, default=REORDER / "state" / "working-delta.json")
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base = load_json(args.base)
    delta = load_json(args.delta) if args.delta.exists() else {"adds": [], "removes": [], "proof_dependencies": []}
    nodes_by_label = base.get("nodes_by_label", {})
    base_direct = sorted_direct(base.get("direct_dependencies", {}))
    cumulative_direct = apply_delta(base_direct, delta)
    current = check(base_direct, args.source, args.target)
    cumulative = check(cumulative_direct, args.source, args.target)
    missing_source = args.source not in nodes_by_label
    missing_target = args.target not in nodes_by_label
    payload = {
        "schema_version": "reorder-edge-check-1",
        "source": args.source,
        "target": args.target,
        "source_node": nodes_by_label.get(args.source),
        "target_node": nodes_by_label.get(args.target),
        "missing_source": missing_source,
        "missing_target": missing_target,
        "current": current,
        "cumulative": cumulative,
        "recommendation": recommendation(current, cumulative, missing_source, missing_target),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
