"""Prepare deterministic concept-decomposition packets for propositional logic.

This script is read-only with respect to source data. It writes derived
invocation packets under reorder/concept-pipeline/invocations/.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "concept-invocation-packet-1"
MANIFEST_SCHEMA_VERSION = "concept-invocation-manifest-1"


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


def node_summary(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node.get("id"),
        "title": node.get("title") or "",
        "kind": node.get("kind") or "",
        "volume": node.get("volume") or "",
        "chapter": node.get("chapter") or "",
        "section": node.get("section") or "",
        "statement_display": node.get("statement_display") or "",
        "statement_tex": node.get("statement_tex") or "",
        "source": node.get("source") or "",
        "source_order": node.get("source_order"),
    }


def compact_definition(node: dict[str, Any]) -> dict[str, str]:
    return {
        "id": node.get("id") or "",
        "title": node.get("title") or "",
        "section": node.get("section") or "",
        "summary": node.get("statement_preview")
        or (node.get("statement_display") or "").replace("\n", " ")[:500],
    }


def filename_slug(label: str) -> str:
    allowed = []
    for char in label:
        if char.isalnum() or char in ("-", "_", "."):
            allowed.append(char)
        else:
            allowed.append("-")
    return "".join(allowed).strip("-") or "node"


def direct_dependency_map(knowledge: dict[str, Any]) -> dict[str, list[str]]:
    deps: dict[str, list[str]] = {}
    for edge in knowledge.get("edges", []):
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            continue
        deps.setdefault(source, []).append(target)
    return {source: sorted(set(targets)) for source, targets in deps.items()}


def build_packets(repo_root: Path, output_root: Path) -> dict[str, Any]:
    knowledge = load_json(repo_root / "knowledge.json")
    policy = load_json(repo_root / "reorder" / "policy.json")
    floor = load_json(
        repo_root
        / "reorder"
        / "concept-pipeline"
        / "floors"
        / "propositional-logic.json"
    )

    nodes = [
        node
        for node in knowledge.get("nodes", [])
        if node.get("volume") == "i" and node.get("chapter") == "propositional-logic"
    ]
    nodes.sort(
        key=lambda node: (
            node.get("section") or "",
            node.get("source_order") is None,
            node.get("source_order") or 0,
            node.get("id") or "",
        )
    )

    by_id = {node.get("id"): node for node in knowledge.get("nodes", []) if node.get("id")}
    deps = direct_dependency_map(knowledge)

    floor_component_ids: list[str] = []
    for structure in floor.get("virtual_structures", []):
        floor_component_ids.extend(structure.get("components", []))
    floor_component_ids = sorted(set(floor_component_ids))
    floor_components = [
        compact_definition(by_id[label])
        for label in floor_component_ids
        if label in by_id
    ]

    scope_definitions = [
        compact_definition(node)
        for node in nodes
        if node.get("kind") == "Definition"
    ]

    packet_paths: list[dict[str, Any]] = []
    for index, node in enumerate(nodes, start=1):
        node_id = node.get("id") or f"node-{index:04d}"
        direct_ids = deps.get(node_id, [])
        packet = {
            "schema_version": SCHEMA_VERSION,
            "packet_id": f"prop-logic-{index:04d}.{node_id}",
            "prompt": {
                "path": "reorder/concept-pipeline/prompts/concept-decomposition.md",
                "output_schema": "concept-decomposition-1",
            },
            "scope": floor.get("scope", {}),
            "toc_layer": floor.get("toc_layers", {}).get(node.get("section") or ""),
            "definitional_roots": policy.get("definitional_roots", []),
            "virtual_structures": floor.get("virtual_structures", []),
            "floor_components": floor_components,
            "scope_match_pool": scope_definitions,
            "node": node_summary(node),
            "current_direct_dependencies": [
                compact_definition(by_id[label])
                for label in direct_ids
                if label in by_id
            ],
            "inference_policy": floor.get("inference_policy", []),
        }
        rel_path = (
            Path("propositional-logic")
            / f"{index:04d}.{filename_slug(node_id)}.json"
        )
        stable_write_json(output_root / rel_path, packet)
        packet_paths.append(
            {
                "packet_id": packet["packet_id"],
                "node": node_id,
                "kind": node.get("kind") or "",
                "section": node.get("section") or "",
                "path": str((Path("invocations") / rel_path).as_posix()),
            }
        )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "scope": floor.get("scope", {}),
        "packet_count": len(packet_paths),
        "packets": packet_paths,
    }
    stable_write_json(output_root / "propositional-logic" / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root containing knowledge.json.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory for invocation packets.",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output_root = (
        args.out.resolve()
        if args.out
        else repo_root / "reorder" / "concept-pipeline" / "invocations"
    )
    manifest = build_packets(repo_root, output_root)
    print(
        json.dumps(
            {
                "scope": manifest["scope"],
                "packet_count": manifest["packet_count"],
                "manifest": str(
                    output_root / "propositional-logic" / "manifest.json"
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
