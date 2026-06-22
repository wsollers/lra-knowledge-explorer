"""Prepare direct-label-selection packets for propositional logic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "direct-label-selection-packet-1"
MANIFEST_SCHEMA_VERSION = "direct-label-selection-manifest-1"


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


def filename_slug(label: str) -> str:
    out = []
    for char in label:
        out.append(char if char.isalnum() or char in ("-", "_", ".") else "-")
    return "".join(out).strip("-") or "node"


def summary(node: dict[str, Any], *, max_len: int = 360) -> str:
    text = node.get("statement_preview") or node.get("statement_display") or ""
    text = " ".join(str(text).split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def universe_entry(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node.get("id") or "",
        "kind": node.get("kind") or "",
        "volume": node.get("volume") or "",
        "chapter": node.get("chapter") or "",
        "section": node.get("section") or "",
        "title": node.get("title") or "",
        "summary": summary(node),
    }


def node_entry(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node.get("id") or "",
        "kind": node.get("kind") or "",
        "volume": node.get("volume") or "",
        "chapter": node.get("chapter") or "",
        "section": node.get("section") or "",
        "title": node.get("title") or "",
        "statement_display": node.get("statement_display") or "",
        "statement_tex": node.get("statement_tex") or "",
        "source": node.get("source") or "",
        "source_order": node.get("source_order"),
    }


def direct_dependency_map(knowledge: dict[str, Any]) -> dict[str, list[str]]:
    deps: dict[str, set[str]] = {}
    for edge in knowledge.get("edges", []):
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            deps.setdefault(source, set()).add(target)
    return {source: sorted(targets) for source, targets in deps.items()}


def packet_sort_key(node: dict[str, Any]) -> tuple[Any, ...]:
    return (
        node.get("section") or "",
        node.get("source_order") is None,
        node.get("source_order") or 0,
        node.get("id") or "",
    )


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

    all_nodes = [node for node in knowledge.get("nodes", []) if node.get("id")]
    by_id = {node["id"]: node for node in all_nodes}
    deps = direct_dependency_map(knowledge)

    prop_nodes = [
        node
        for node in all_nodes
        if node.get("volume") == "i" and node.get("chapter") == "propositional-logic"
    ]
    prop_nodes.sort(key=packet_sort_key)

    volume_i_universe = [
        universe_entry(node)
        for node in all_nodes
        if node.get("volume") == "i"
    ]
    volume_i_universe.sort(key=lambda item: (item["chapter"], item["section"], item["id"]))

    packet_index = []
    for index, node in enumerate(prop_nodes, start=1):
        node_id = node["id"]
        direct_ids = deps.get(node_id, [])
        packet = {
            "schema_version": SCHEMA_VERSION,
            "packet_id": f"prop-label-{index:04d}.{node_id}",
            "prompt": {
                "path": "reorder/concept-pipeline/prompts/label-selection.md",
                "output_schema": "direct-label-selection-1",
            },
            "scope": floor.get("scope", {}),
            "toc_layer": floor.get("toc_layers", {}).get(node.get("section") or ""),
            "definitional_roots": policy.get("definitional_roots", []),
            "virtual_structures": floor.get("virtual_structures", []),
            "node": node_entry(node),
            "current_direct_dependencies": [
                universe_entry(by_id[label])
                for label in direct_ids
                if label in by_id
            ],
            "label_universe_policy": {
                "allowed_targets": "Only ids listed in label_universe may be used as new statement or proof dependency targets.",
                "scope": "All Volume I nodes, including propositional logic, predicate logic, axiom systems, and sets-relations-functions.",
            },
            "label_universe": volume_i_universe,
        }
        rel_path = Path("propositional-logic") / f"{index:04d}.{filename_slug(node_id)}.labels.packet.json"
        stable_write_json(output_root / rel_path, packet)
        packet_index.append(
            {
                "packet_id": packet["packet_id"],
                "node": node_id,
                "kind": node.get("kind") or "",
                "section": node.get("section") or "",
                "path": str((Path("label-selection") / rel_path).as_posix()),
                "universe_count": len(volume_i_universe),
            }
        )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "scope": floor.get("scope", {}),
        "packet_count": len(packet_index),
        "label_universe_count": len(volume_i_universe),
        "packets": packet_index,
    }
    stable_write_json(output_root / "propositional-logic" / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output_root = (
        args.out.resolve()
        if args.out
        else repo_root / "reorder" / "concept-pipeline" / "label-selection"
    )
    manifest = build_packets(repo_root, output_root)
    print(
        json.dumps(
            {
                "scope": manifest["scope"],
                "packet_count": manifest["packet_count"],
                "label_universe_count": manifest["label_universe_count"],
                "manifest": str(output_root / "propositional-logic" / "manifest.json"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
