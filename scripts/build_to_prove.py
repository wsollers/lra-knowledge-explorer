#!/usr/bin/env python3
"""Build proof-to-do tracker markdown and Knowledge Explorer to-prove data."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KNOWLEDGE = REPO_ROOT / "knowledge.json"
DEFAULT_OUTPUT = REPO_ROOT / "to-prove.json"
TRACKER_RE = re.compile(r"^\d+\.\s+\((?P<mark>✅)?\)\s+`(?P<label>[^`]+)`", re.MULTILINE)
VOLUME_REPOS = {
    1: "lra-volume-i",
    2: "lra-volume-ii",
    3: "lra-volume-iii",
    4: "lra-volume-iv",
    5: "lra-volume-v",
    6: "lra-volume-vi",
    7: "lra-volume-vii",
    8: "lra-volume-viii",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def completed_labels(tracker: Path) -> set[str]:
    if not tracker.is_file():
        return set()
    text = tracker.read_text(encoding="utf-8", errors="replace")
    return {m.group("label") for m in TRACKER_RE.finditer(text) if m.group("mark")}


def volume_title(volume: dict[str, Any]) -> str:
    roman = str(volume.get("roman") or "").upper()
    title = str(volume.get("title") or "")
    return f"Volume {roman} - {title}".strip()


def blockquote_statement(statement: str, *, indent: str = "") -> list[str]:
    lines = [f"{indent}> **Statement.**"]
    body = str(statement or "").strip()
    if not body:
        lines.append(f"{indent}> _No statement extracted._")
        return lines
    for line in body.splitlines():
        lines.append(f"{indent}> {line}".rstrip())
    return lines


def item_markdown(item: dict[str, Any], index: int) -> list[str]:
    mark = "✅" if item["status"] == "completed" else ""
    lines = [
        f"{index}. ({mark}) `{item['id']}` — **{item['title']}**",
        *blockquote_statement(item.get("statement", ""), indent="   "),
    ]
    return lines


def tracker_markdown(volume: dict[str, Any], items: list[dict[str, Any]]) -> str:
    open_count = sum(1 for item in items if item["status"] == "open")
    completed_count = sum(1 for item in items if item["status"] == "completed")
    lines = [
        f"# {volume_title(volume)} Proofs To Do",
        "",
        "Proof-writing order is dependency-first among active TODO proof labels, with the generated knowledge graph order used as the stable tie-breaker.",
        "Use `✅` to record completion after the canonical proof file has both proof bodies populated and validated.",
        "",
        f"Open proofs to do: {open_count}",
        f"Completed in this tracker: {completed_count}",
        "",
    ]
    for index, item in enumerate(items, start=1):
        lines.extend(item_markdown(item, index))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def dependency_maps(knowledge: dict[str, Any]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    theorem_deps: dict[str, set[str]] = {}
    proof_deps: dict[str, set[str]] = {}
    for edge in knowledge.get("edges", []):
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        kind = str(edge.get("kind") or "")
        if not source or not target:
            continue
        if kind == "depends_on":
            theorem_deps.setdefault(source, set()).add(target)
        elif kind == "proof_depends_on":
            proof_deps.setdefault(source, set()).add(target)
    for node in knowledge.get("nodes", []):
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        for dep in node.get("depends_on_ids") or []:
            theorem_deps.setdefault(node_id, set()).add(str(dep))
    return theorem_deps, proof_deps


def dependency_first(items: list[dict[str, Any]], order: dict[str, int]) -> list[dict[str, Any]]:
    by_id = {item["id"]: item for item in items}
    active = set(by_id)
    visited: set[str] = set()
    visiting: set[str] = set()
    out: list[str] = []

    def deps_for(node_id: str) -> list[str]:
        item = by_id[node_id]
        deps = set(item.get("theorem_dependency_ids") or []) | set(item.get("proof_dependency_ids") or [])
        return sorted((dep for dep in deps if dep in active), key=lambda dep: order.get(dep, 10**9))

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            return
        visiting.add(node_id)
        for dep in deps_for(node_id):
            visit(dep)
        visiting.remove(node_id)
        visited.add(node_id)
        out.append(node_id)

    for node_id in sorted(active, key=lambda item_id: order.get(item_id, 10**9)):
        visit(node_id)
    return [by_id[node_id] for node_id in out]


def build_items(knowledge: dict[str, Any], repos_root: Path) -> tuple[list[dict[str, Any]], dict[int, set[str]]]:
    nodes = knowledge.get("nodes", [])
    order = {str(node.get("id")): index for index, node in enumerate(nodes) if node.get("id")}
    theorem_deps, proof_deps = dependency_maps(knowledge)
    completed_by_volume = {
        volume: completed_labels(repos_root / repo / "proofs-to-do.md")
        for volume, repo in VOLUME_REPOS.items()
    }
    items: list[dict[str, Any]] = []
    for node in nodes:
        node_id = str(node.get("id") or "")
        if not node_id or not node.get("has_proof_file"):
            continue
        volume = int(node.get("volume") or 0)
        is_open = node.get("proof_sketch_source") == "todo_stub_skipped"
        is_completed = node_id in completed_by_volume.get(volume, set())
        if not is_open and not is_completed:
            continue
        theorem_dependency_ids = sorted(theorem_deps.get(node_id, set()), key=lambda dep: order.get(dep, 10**9))
        proof_dependency_ids = sorted(proof_deps.get(node_id, set()), key=lambda dep: order.get(dep, 10**9))
        item = {
            "id": node_id,
            "status": "completed" if is_completed else "open",
            "title": node.get("name") or node.get("title") or node_id,
            "kind": node.get("kind") or "",
            "statement": node.get("statement_display") or node.get("statement_tex") or "",
            "volume": volume,
            "volume_roman": node.get("volume_roman") or "",
            "volume_title": node.get("volume_title") or "",
            "book": node.get("book") or "",
            "book_title": node.get("book_title") or "",
            "chapter": node.get("chapter") or "",
            "chapter_title": node.get("chapter_title") or "",
            "section": node.get("section") or "",
            "section_title": node.get("section_title") or node.get("deck") or "",
            "source": node.get("source") or "",
            "proof_source": node.get("proof_source") or "",
            "theorem_dependency_ids": theorem_dependency_ids,
            "proof_dependency_ids": proof_dependency_ids,
            "graph_dependency_ids": sorted(set(theorem_dependency_ids) | set(proof_dependency_ids), key=lambda dep: order.get(dep, 10**9)),
        }
        item["markdown"] = "\n".join(item_markdown(item, 1)).split("\n", 1)[1]
        items.append(item)
    return dependency_first(items, order), completed_by_volume


def volume_payloads(knowledge: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_volume: dict[int, list[dict[str, Any]]] = {}
    for item in items:
        by_volume.setdefault(int(item["volume"]), []).append(item)
    volumes = []
    toc = knowledge.get("metadata", {}).get("toc") or []
    for volume in toc:
        volume_id = int(volume.get("id") or 0)
        volume_items = by_volume.get(volume_id, [])
        volumes.append(
            {
                "id": volume_id,
                "roman": volume.get("roman") or "",
                "title": volume.get("title") or "",
                "repo": VOLUME_REPOS.get(volume_id, ""),
                "open_count": sum(1 for item in volume_items if item["status"] == "open"),
                "completed_count": sum(1 for item in volume_items if item["status"] == "completed"),
                "items": volume_items,
            }
        )
    return volumes


def write_volume_trackers(volumes: list[dict[str, Any]], repos_root: Path) -> None:
    for volume in volumes:
        repo = volume.get("repo")
        if not repo:
            continue
        path = repos_root / repo / "proofs-to-do.md"
        path.write_text(tracker_markdown(volume, volume.get("items") or []), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge", type=Path, default=DEFAULT_KNOWLEDGE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repos-root", type=Path, default=REPO_ROOT.parent)
    parser.add_argument("--write-volume-trackers", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    knowledge = load_json(args.knowledge.resolve())
    repos_root = args.repos_root.resolve()
    items, _completed = build_items(knowledge, repos_root)
    volumes = volume_payloads(knowledge, items)
    payload = {
        "metadata": {
            "schema_version": "0.1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": args.knowledge.name,
            "item_count": len(items),
            "open_count": sum(1 for item in items if item["status"] == "open"),
            "completed_count": sum(1 for item in items if item["status"] == "completed"),
        },
        "volumes": volumes,
        "items": items,
    }
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.write_volume_trackers:
        write_volume_trackers(volumes, repos_root)
    print(f"Wrote {len(items)} proof todo records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
