"""Audit prop-logic concept matches against the cumulative dependency graph."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "concept-graph-audit-1"
MANIFEST_SCHEMA_VERSION = "concept-graph-audit-manifest-1"


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
    target: str | None,
    missing_source: bool,
    missing_target: bool,
    cumulative: dict[str, Any] | None,
    bucket: str,
) -> str:
    if not target:
        return "investigate_no_match"
    if missing_source or missing_target:
        return "investigate_missing_label"
    if bucket == "proof":
        return "proof_candidate_not_statement_graph_checked"
    assert cumulative is not None
    if source == target:
        return "reject_self_dependency"
    if cumulative["creates_cycle"]:
        return "reject_cycle"
    if cumulative["already_direct"]:
        return "reject_already_direct_in_cumulative_graph"
    if cumulative["already_transitive"]:
        return "reject_redundant_in_cumulative_graph"
    return "candidate_ok_graph_hygiene_only"


def output_name(match_path: Path) -> str:
    return match_path.name.removesuffix(".matches.json") + ".audit.json"


def best_candidate(match: dict[str, Any]) -> dict[str, Any] | None:
    candidates = match.get("candidates") or []
    if not candidates:
        return None
    return candidates[0]


def audit_match_report(
    report: dict[str, Any],
    nodes_by_label: dict[str, Any],
    base_graph: dict[str, list[str]],
    cumulative_graph: dict[str, list[str]],
) -> dict[str, Any]:
    source = report["node"]
    results = []
    for match in report.get("matches", []):
        top = best_candidate(match)
        target = top.get("id") if top else None
        bucket = match.get("bucket", "statement")
        missing_source = source not in nodes_by_label
        missing_target = bool(target and target not in nodes_by_label)
        current = None
        cumulative = None
        if target and not missing_source and not missing_target and bucket == "statement":
            current = edge_check(base_graph, source, target)
            cumulative = edge_check(cumulative_graph, source, target)
        results.append(
            {
                "concept": match.get("concept"),
                "bucket": bucket,
                "source_role": match.get("source_role"),
                "concept_confidence": match.get("confidence"),
                "source_reason": match.get("reason"),
                "top_candidate": top,
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
                    bucket=bucket,
                ),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "node": source,
        "source_match_report": report.get("source_concepts"),
        "audits": results,
    }


def redundant_direct_edges(graph: dict[str, list[str]], sources: list[str]) -> list[dict[str, Any]]:
    out = []
    for source in sources:
        for target in graph.get(source, []):
            reduced = {node: list(targets) for node, targets in graph.items()}
            reduced[source] = [dep for dep in reduced.get(source, []) if dep != target]
            path = path_to(reduced, source, target)
            if path:
                out.append({"source": source, "target": target, "alternate_path": path})
    return out


def build_audits(repo_root: Path, matches_dir: Path, output_dir: Path) -> dict[str, Any]:
    base = load_json(repo_root / "reorder" / "state" / "base-graph.json")
    delta_path = repo_root / "reorder" / "state" / "working-delta.json"
    delta = load_json(delta_path) if delta_path.exists() else {"adds": [], "removes": []}
    nodes_by_label = base.get("nodes_by_label", {})
    base_graph = sorted_direct(base.get("direct_dependencies", {}))
    cumulative_graph = apply_delta(base_graph, delta)

    match_paths = sorted(matches_dir.glob("*.matches.json"))
    reports = []
    prop_logic_sources = []
    for match_path in match_paths:
        report = load_json(match_path)
        audit = audit_match_report(report, nodes_by_label, base_graph, cumulative_graph)
        out_path = output_dir / output_name(match_path)
        stable_write_json(out_path, audit)
        reports.append(
            {
                "node": audit["node"],
                "audit_count": len(audit["audits"]),
                "path": str(out_path.as_posix()),
            }
        )
        prop_logic_sources.append(audit["node"])

    redundant = redundant_direct_edges(cumulative_graph, sorted(set(prop_logic_sources)))
    stable_write_json(
        output_dir / "direct-transitive-duplicates.json",
        {
            "schema_version": "concept-direct-duplicate-audit-1",
            "scope": "propositional-logic",
            "duplicate_count": len(redundant),
            "duplicates": redundant,
        },
    )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "scope": "propositional-logic",
        "report_count": len(reports),
        "direct_transitive_duplicate_count": len(redundant),
        "reports": reports,
    }
    stable_write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--matches", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    matches_dir = (
        args.matches.resolve()
        if args.matches
        else repo_root / "reorder" / "concept-pipeline" / "matches" / "propositional-logic"
    )
    output_dir = (
        args.out.resolve()
        if args.out
        else repo_root / "reorder" / "concept-pipeline" / "audits" / "propositional-logic"
    )

    manifest = build_audits(repo_root, matches_dir, output_dir)
    print(
        json.dumps(
            {
                "scope": manifest["scope"],
                "report_count": manifest["report_count"],
                "direct_transitive_duplicate_count": manifest["direct_transitive_duplicate_count"],
                "manifest": str(output_dir / "manifest.json"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
