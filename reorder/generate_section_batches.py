#!/usr/bin/env python3
"""Generate section-scoped dependency audit batches for Volumes II and III.

The generated batches are review inputs. They do not mutate TeX source,
knowledge.json, or graph-edges.json. Rerunning this script replaces the
section-batches directory and base graph snapshot deterministically, while
preserving reorder/state/working-delta.json unless --reset-delta is passed.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
AUDIT_KINDS = {"Definition", "Axiom", "Theorem", "Lemma", "Proposition", "Corollary"}
DEFAULT_VOLUMES = ("ii", "iii")
WS = re.compile(r"\s+")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "unknown"


def compact(value: str, limit: int = 500) -> str:
    value = WS.sub(" ", (value or "").strip())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def title(node: dict[str, Any] | None, fallback: str = "") -> str:
    if not node:
        return fallback
    return node.get("title") or node.get("name") or node.get("id") or fallback


def node_summary(node: dict[str, Any] | None, fallback: str = "") -> dict[str, Any]:
    if not node:
        return {"id": fallback, "title": fallback, "kind": "", "statement_preview": ""}
    return {
        "id": node["id"],
        "title": title(node),
        "kind": node.get("kind", ""),
        "volume": node.get("volume", ""),
        "chapter": node.get("chapter", ""),
        "chapter_title": node.get("chapter_title", ""),
        "section": node.get("section", ""),
        "section_title": node.get("section_title", ""),
        "statement_preview": compact(node.get("statement_display") or node.get("statement_tex") or node.get("text_preview") or "", 360),
    }


def build_direct_edges(edges: list[dict[str, Any]]) -> dict[str, list[str]]:
    direct: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.get("kind") != "depends_on":
            continue
        source = edge.get("from")
        target = edge.get("to")
        if source and target:
            direct[source].add(target)
    return {source: sorted(targets) for source, targets in sorted(direct.items())}


def closure(label: str, direct: dict[str, list[str]]) -> list[str]:
    seen: set[str] = set()
    stack = list(direct.get(label, []))
    while stack:
        dep = stack.pop()
        if dep in seen:
            continue
        seen.add(dep)
        stack.extend(direct.get(dep, []))
    return sorted(seen)


def ancestor_tree(
    label: str,
    direct: dict[str, list[str]],
    by_id: dict[str, dict[str, Any]],
    *,
    max_depth: int = 6,
    seen: set[str] | None = None,
) -> list[dict[str, Any]]:
    seen = set(seen or ())
    if max_depth <= 0:
        return []
    out: list[dict[str, Any]] = []
    for dep in direct.get(label, []):
        item = node_summary(by_id.get(dep), dep)
        if dep in seen:
            item["cycle_marker"] = True
            out.append(item)
            continue
        item["dependencies"] = ancestor_tree(dep, direct, by_id, max_depth=max_depth - 1, seen=seen | {dep})
        out.append(item)
    return out


def topological_section_order(nodes: list[dict[str, Any]], direct: dict[str, list[str]]) -> list[dict[str, Any]]:
    members = {node["id"] for node in nodes}
    incoming_count = {node["id"]: 0 for node in nodes}
    users: dict[str, list[str]] = defaultdict(list)
    order_key = {
        node["id"]: (
            node.get("source_order", 10**9),
            node.get("source", ""),
            node.get("id", ""),
        )
        for node in nodes
    }
    for source in members:
        for dep in direct.get(source, []):
            if dep in members:
                users[dep].append(source)
                incoming_count[source] += 1
    ready = deque(sorted([label for label, count in incoming_count.items() if count == 0], key=lambda label: order_key[label]))
    ordered: list[str] = []
    while ready:
        label = ready.popleft()
        ordered.append(label)
        for user in sorted(users.get(label, []), key=lambda item: order_key[item]):
            incoming_count[user] -= 1
            if incoming_count[user] == 0:
                ready.append(user)
        ready = deque(sorted(ready, key=lambda item: order_key[item]))
    if len(ordered) != len(nodes):
        # Preserve deterministic progress if the existing graph contains a local cycle.
        remaining = sorted((label for label in members if label not in set(ordered)), key=lambda label: order_key[label])
        ordered.extend(remaining)
    by_label = {node["id"]: node for node in nodes}
    return [by_label[label] for label in ordered]


def toc_lookup(knowledge: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, str]]:
    lookup: dict[tuple[str, str, str], dict[str, str]] = {}
    for volume in knowledge.get("metadata", {}).get("toc", []):
        volume_id = str(volume.get("id", ""))
        for chapter in volume.get("chapters", []):
            chapter_id = str(chapter.get("id", ""))
            for section in chapter.get("sections", []):
                section_id = str(section.get("id", ""))
                lookup[(volume_id, chapter_id, section_id)] = {
                    "volume": volume_id,
                    "chapter": chapter_id,
                    "section": section_id,
                    "chapter_title": str(chapter.get("title") or chapter_id),
                    "section_title": str(section.get("title") or section_id),
                }
    return lookup


def toc_order(knowledge: dict[str, Any], volumes: set[str]) -> list[tuple[str, str, str]]:
    ordered: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for volume in knowledge.get("metadata", {}).get("toc", []):
        volume_id = str(volume.get("id", ""))
        if volume_id not in volumes:
            continue
        for chapter in volume.get("chapters", []):
            chapter_id = str(chapter.get("id", ""))
            for section in chapter.get("sections", []):
                key = (volume_id, chapter_id, str(section.get("id", "")))
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
    return ordered


def ordered_group_keys(
    knowledge: dict[str, Any],
    groups: dict[tuple[str, str, str], list[dict[str, Any]]],
    volumes: set[str],
) -> list[tuple[str, str, str]]:
    ordered: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def group_key(key: tuple[str, str, str]) -> tuple[Any, ...]:
        members = groups.get(key, [])
        source_orders = [item.get("source_order") for item in members if isinstance(item.get("source_order"), int)]
        min_order = min(source_orders) if source_orders else 10**9
        min_source = min((str(item.get("source", "")) for item in members), default="")
        return (min_order, min_source, key[2])

    for volume in knowledge.get("metadata", {}).get("toc", []):
        volume_id = str(volume.get("id", ""))
        if volume_id not in volumes:
            continue
        for chapter in volume.get("chapters", []):
            chapter_id = str(chapter.get("id", ""))
            chapter_keys = [key for key in groups if key[0] == volume_id and key[1] == chapter_id]
            if not chapter_keys:
                continue
            for section in chapter.get("sections", []):
                key = (volume_id, chapter_id, str(section.get("id", "")))
                if key in groups and key not in seen:
                    seen.add(key)
                    ordered.append(key)
            for key in sorted((key for key in chapter_keys if key not in seen), key=group_key):
                seen.add(key)
                ordered.append(key)

    ordered.extend(sorted((key for key in groups if key not in seen), key=group_key))
    return ordered


def context_note(scope: dict[str, str]) -> str:
    volume = scope.get("volume", "")
    chapter = scope.get("chapter_title") or scope.get("chapter", "")
    section = scope.get("section_title") or scope.get("section", "")
    return (
        f"Volume {volume.upper()} section from an undergraduate real analysis note set. "
        f"The local mathematical setting is chapter '{chapter}', section '{section}'. "
        "The audit goal is in-depth learning of the structure: direct dependencies should be concepts needed "
        "to state each node precisely, with common ambient structure carried by the nearest appropriate ancestor."
    )


def make_base_graph(knowledge: dict[str, Any], direct: dict[str, list[str]], volumes: set[str]) -> dict[str, Any]:
    nodes = [node for node in knowledge["nodes"] if str(node.get("volume", "")) in volumes and node.get("kind") in AUDIT_KINDS and not node.get("ignored")]
    nodes_by_label = {
        node["id"]: node_summary(node)
        | {
            "statement_display": node.get("statement_display", ""),
            "statement_tex": node.get("statement_tex", ""),
            "source": node.get("source", ""),
            "source_order": node.get("source_order"),
        }
        for node in knowledge["nodes"]
        if node.get("id")
    }
    labels = set(nodes_by_label)
    related = set(direct)
    for targets in direct.values():
        related.update(targets)
    return {
        "schema_version": "reorder-base-graph-1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "knowledge": str(ROOT / "knowledge.json"),
            "graph_edges": str(ROOT / "graph-edges.json"),
            "knowledge_version": knowledge.get("metadata", {}).get("version_id"),
            "knowledge_generated_at": knowledge.get("metadata", {}).get("generated_at"),
        },
        "volumes": sorted(volumes),
        "nodes_by_label": nodes_by_label,
        "direct_dependencies": {label: direct.get(label, []) for label in sorted(related)},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge", type=Path, default=ROOT / "knowledge.json")
    parser.add_argument("--edges", type=Path, default=ROOT / "graph-edges.json")
    parser.add_argument("--out", type=Path, default=HERE / "section-batches")
    parser.add_argument("--state", type=Path, default=HERE / "state")
    parser.add_argument("--volumes", nargs="+", default=list(DEFAULT_VOLUMES), help="Volume ids to include, default: ii iii")
    parser.add_argument("--reset-delta", action="store_true", help="Replace working-delta.json with an empty delta.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    volumes = {str(volume).removeprefix("volume-") for volume in args.volumes}
    knowledge = load_json(args.knowledge)
    direct = build_direct_edges(load_json(args.edges))
    by_id = {node["id"]: node for node in knowledge["nodes"]}
    toc = toc_lookup(knowledge)

    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True, exist_ok=True)
    args.state.mkdir(parents=True, exist_ok=True)

    base_graph = make_base_graph(knowledge, direct, volumes)
    write_json(args.state / "base-graph.json", base_graph)
    delta_path = args.state / "working-delta.json"
    if args.reset_delta or not delta_path.exists():
        write_json(
            delta_path,
            {
                "schema_version": "reorder-working-delta-2",
                "description": "Accepted review deltas. Preserved across batch regeneration unless --reset-delta is used.",
                "adds": [],
                "removes": [],
                "proof_dependencies": [],
            },
        )

    audit_nodes = [
        node
        for node in knowledge["nodes"]
        if str(node.get("volume", "")) in volumes and node.get("kind") in AUDIT_KINDS and not node.get("ignored")
    ]
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for node in audit_nodes:
        groups[(str(node.get("volume", "")), str(node.get("chapter", "")), str(node.get("section", "")))].append(node)

    manifest: list[dict[str, Any]] = []
    ordered_keys = ordered_group_keys(knowledge, groups, volumes)

    for index, key in enumerate(ordered_keys, start=1):
        volume, chapter, section = key
        members = topological_section_order(groups[key], direct)
        scope = toc.get(key, {})
        scope = {
            "volume": volume,
            "chapter": chapter,
            "section": section,
            "chapter_title": scope.get("chapter_title") or members[0].get("chapter_title") or chapter,
            "section_title": scope.get("section_title") or members[0].get("section_title") or section or "Unsectioned",
        }
        batch_id = f"batch-{index:04d}.{slug('volume-' + volume)}.{slug(chapter)}.{slug(section or 'unsectioned')}"
        batch_path = args.out / f"{batch_id}.json"
        batch_nodes: list[dict[str, Any]] = []
        for ordinal, node in enumerate(members, start=1):
            label = node["id"]
            deps = direct.get(label, [])
            batch_nodes.append(
                {
                    "review_order": ordinal,
                    "id": label,
                    "title": title(node),
                    "kind": node.get("kind", ""),
                    "source": node.get("source", ""),
                    "source_order": node.get("source_order"),
                    "statement_display": node.get("statement_display", ""),
                    "statement_tex": node.get("statement_tex", ""),
                    "direct_dependencies": [node_summary(by_id.get(dep), dep) for dep in deps],
                    "transitive_dependencies": [node_summary(by_id.get(dep), dep) for dep in closure(label, direct)],
                    "ancestor_tree": ancestor_tree(label, direct, by_id),
                    "used_by_in_section": [
                        user["id"]
                        for user in members
                        if label in direct.get(user["id"], []) and user["id"] != label
                    ],
                }
            )
        batch = {
            "schema_version": "reorder-section-batch-1",
            "batch_id": batch_id,
            "scope": scope | {"context_note": context_note(scope)},
            "review_instructions": {
                "order": "Nodes are topologically sorted so dependencies and ambient ancestors appear before their users when possible.",
                "state": "Use reorder/state/working-delta.json as cumulative accepted state across all batches.",
                "checker": "Run reorder/tools/check_dependency_edge.py before accepting any statement add.",
                "classification": "Statement dependencies belong in adds/removes. Proof-only dependencies belong in proof_dependencies and are ignored by graph cycle/transitive checks.",
            },
            "base_graph": "../state/base-graph.json",
            "working_delta": "../state/working-delta.json",
            "nodes": batch_nodes,
        }
        write_json(batch_path, batch)
        manifest.append(
            {
                "batch_id": batch_id,
                "path": batch_path.relative_to(HERE).as_posix(),
                "volume": volume,
                "chapter": chapter,
                "section": section,
                "chapter_title": scope["chapter_title"],
                "section_title": scope["section_title"],
                "node_count": len(batch_nodes),
            }
        )

    write_json(
        args.out / "manifest.json",
        {
            "schema_version": "reorder-section-batch-manifest-1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "volumes": sorted(volumes),
            "batch_count": len(manifest),
            "node_count": sum(item["node_count"] for item in manifest),
            "batches": manifest,
        },
    )
    print(f"Wrote {len(manifest)} section batches under {args.out}")
    print(f"Wrote base graph: {args.state / 'base-graph.json'}")
    print(f"Working delta: {delta_path} ({'reset' if args.reset_delta else 'preserved/created'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
