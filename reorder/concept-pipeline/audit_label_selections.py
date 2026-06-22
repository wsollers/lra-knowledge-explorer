"""Audit direct label-selection outputs against the cumulative graph."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "direct-label-selection-audit-1"
MANIFEST_SCHEMA_VERSION = "direct-label-selection-audit-manifest-1"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def stable_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    rendered += "\n"
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(rendered, encoding="utf-8")
    tmp.replace(path)


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


def edge_check(graph: dict[str, list[str]], source: str, target: str) -> dict[str, Any]:
    direct = target in graph.get(source, [])
    transitive_path = path_to(graph, source, target)
    cycle_path = path_to(graph, target, source)
    return {
        "already_direct": direct,
        "already_transitive": bool(transitive_path),
        "transitive_path": transitive_path,
        "creates_cycle": source == target or bool(cycle_path),
        "cycle_path_if_added": [source, target, source]
        if source == target
        else ([source, target] + cycle_path[1:] if cycle_path else []),
    }


def recommendation(
    *,
    source: str,
    target: str,
    missing_source: bool,
    missing_target: bool,
    cumulative: dict[str, Any] | None,
) -> str:
    if missing_source or missing_target:
        return "investigate_missing_label"
    if source == target:
        return "reject_self_dependency"
    assert cumulative is not None
    if cumulative["creates_cycle"]:
        return "reject_cycle"
    if cumulative["already_direct"]:
        return "reject_already_direct_in_cumulative_graph"
    if cumulative["already_transitive"]:
        return "reject_redundant_in_cumulative_graph"
    return "candidate_ok_graph_hygiene_only"


def output_name(selection_path: Path) -> str:
    return selection_path.name.removesuffix(".label-selection.json") + ".label-audit.json"


def audit_selection(
    selection: dict[str, Any],
    nodes_by_label: dict[str, Any],
    base_graph: dict[str, list[str]],
    cumulative_graph: dict[str, list[str]],
) -> dict[str, Any]:
    source = selection["node"]
    add_audits = []
    for item in selection.get("statement_dependency_adds", []):
        target = item["target"]
        missing_source = source not in nodes_by_label
        missing_target = target not in nodes_by_label
        current = None
        cumulative = None
        if not missing_source and not missing_target:
            current = edge_check(base_graph, source, target)
            cumulative = edge_check(cumulative_graph, source, target)
        add_audits.append(
            {
                "target": target,
                "selection_reason": item.get("reason", ""),
                "selection_confidence": item.get("confidence", ""),
                "missing_source": missing_source,
                "missing_target": missing_target,
                "current": current,
                "cumulative": cumulative,
                "recommendation": recommendation(
                    source=source,
                    target=target,
                    missing_source=missing_source,
                    missing_target=missing_target,
                    cumulative=cumulative,
                ),
            }
        )

    proof_audits = []
    for item in selection.get("proof_dependencies", []):
        target = item["target"]
        proof_audits.append(
            {
                "target": target,
                "selection_reason": item.get("reason", ""),
                "selection_confidence": item.get("confidence", ""),
                "missing_source": source not in nodes_by_label,
                "missing_target": target not in nodes_by_label,
                "recommendation": "proof_candidate_not_statement_graph_checked"
                if source in nodes_by_label and target in nodes_by_label
                else "investigate_missing_label",
            }
        )

    remove_audits = []
    for item in selection.get("statement_dependency_removes", []):
        target = item["target"]
        remove_audits.append(
            {
                "target": target,
                "selection_reason": item.get("reason", ""),
                "selection_confidence": item.get("confidence", ""),
                "replacement": item.get("replacement", ""),
                "currently_direct": target in cumulative_graph.get(source, []),
                "recommendation": "remove_candidate_existing_direct"
                if target in cumulative_graph.get(source, [])
                else "investigate_remove_not_currently_direct",
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "node": source,
        "statement_add_audits": add_audits,
        "proof_dependency_audits": proof_audits,
        "statement_remove_audits": remove_audits,
        "uncertain": selection.get("uncertain", []),
    }


def build_audits(repo_root: Path, selections_dir: Path, out_dir: Path) -> dict[str, Any]:
    base = load_json(repo_root / "reorder" / "state" / "base-graph.json")
    delta_path = repo_root / "reorder" / "state" / "working-delta.json"
    delta = load_json(delta_path) if delta_path.exists() else {"adds": [], "removes": []}
    nodes_by_label = base.get("nodes_by_label", {})
    base_graph = sorted_direct(base.get("direct_dependencies", {}))
    cumulative_graph = apply_delta(base_graph, delta)

    selection_paths = sorted(selections_dir.glob("*.label-selection.json"))
    reports = []
    for selection_path in selection_paths:
        selection = load_json(selection_path)
        audit = audit_selection(selection, nodes_by_label, base_graph, cumulative_graph)
        out_path = out_dir / output_name(selection_path)
        stable_write_json(out_path, audit)
        reports.append(
            {
                "node": audit["node"],
                "statement_add_count": len(audit["statement_add_audits"]),
                "proof_dependency_count": len(audit["proof_dependency_audits"]),
                "statement_remove_count": len(audit["statement_remove_audits"]),
                "path": str(out_path.as_posix()),
            }
        )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "scope": "propositional-logic",
        "report_count": len(reports),
        "reports": reports,
    }
    stable_write_json(out_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--selections", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    selections_dir = (
        args.selections.resolve()
        if args.selections
        else repo_root / "reorder" / "concept-pipeline" / "label-selections" / "propositional-logic"
    )
    out_dir = (
        args.out.resolve()
        if args.out
        else repo_root / "reorder" / "concept-pipeline" / "label-selection-audits" / "propositional-logic"
    )
    manifest = build_audits(repo_root, selections_dir, out_dir)
    print(
        json.dumps(
            {
                "scope": manifest["scope"],
                "report_count": manifest["report_count"],
                "manifest": str(out_dir / "manifest.json"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
