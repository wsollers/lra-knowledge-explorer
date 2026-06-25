#!/usr/bin/env python3
"""Build Knowledge Explorer data from split LRA volume repositories."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PASS1_SCRIPT = REPO_ROOT / "scripts" / "extract_lra_chapter.py"
PASS2_SCRIPT = REPO_ROOT / "scripts" / "seed_to_knowledge_json_v3_fixed6.py"

COMBINED_KNOWLEDGE = REPO_ROOT / "knowledge.json"
COMBINED_EDGES = REPO_ROOT / "graph-edges.json"
COMBINED_ERRORS = REPO_ROOT / "proof-errors.json"
COMBINED_EDGE_ERRORS = REPO_ROOT / "graph-edge-errors.json"


@dataclass(frozen=True)
class ChapterSpec:
    repo: str
    path: str
    volume_number: int
    volume_roman: str
    volume_title: str
    series_title: str
    book_slug: str
    book_title: str
    book_order: int
    book_dir: str
    chapter: str
    expected_notes: tuple[str, ...]


DEFAULT_BOOK_REGISTRY = REPO_ROOT.parent / "lra-governance" / "docs" / "architecture" / "book-registry.json"


def run(cmd: list[str], label: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    completed = subprocess.run(cmd, text=True)
    if completed.returncode:
        raise SystemExit(f"{label} failed with exit code {completed.returncode}")


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise SystemExit(f"Missing {label}: {path}")


def load_book_registry(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"Missing book registry: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def specs_from_registry(registry: dict) -> list[ChapterSpec]:
    specs: list[ChapterSpec] = []
    for volume in registry.get("volumes", []):
        roman = str(volume["roman"])
        for book in volume.get("books", []):
            for chapter in book.get("expected_toc", []):
                expected_notes = tuple(str(note) for note in chapter.get("notes", []))
                if not expected_notes:
                    continue
                chapter_slug = str(chapter["chapter"])
                specs.append(
                    ChapterSpec(
                        repo=f"lra-volume-{roman}",
                        path=str(Path(book["book_dir"]) / chapter_slug).replace("\\", "/"),
                        volume_number=int(volume["volume_number"]),
                        volume_roman=roman,
                        volume_title=str(volume["display_title"]),
                        series_title=str(volume.get("series_title", "")),
                        book_slug=str(book["slug"]),
                        book_title=str(book["title"]),
                        book_order=int(book["order"]),
                        book_dir=str(book["book_dir"]),
                        chapter=chapter_slug,
                        expected_notes=expected_notes,
                    )
                )
    if not specs:
        raise SystemExit("Book registry did not contain any chapters.")
    return specs


def require_chapter(repos_root: Path, spec: ChapterSpec) -> Path:
    repo_root = repos_root / spec.repo
    if not repo_root.is_dir():
        raise SystemExit(f"Required volume repository is missing: {repo_root}")
    if not (repo_root / ".git").exists():
        raise SystemExit(f"Required volume repository is not a git checkout: {repo_root}")

    chapter = repo_root / spec.path
    if not chapter.is_dir():
        raise SystemExit(f"Required chapter is missing: {chapter}")
    if not (chapter / "notes" / "index.tex").is_file():
        raise SystemExit(f"Required live notes index is missing: {chapter / 'notes' / 'index.tex'}")
    if not (chapter / "proofs" / "index.tex").is_file():
        raise SystemExit(f"Required live proofs index is missing: {chapter / 'proofs' / 'index.tex'}")
    return chapter.resolve()


def extract_chapter(chapter_root: Path) -> Path:
    out_dir = chapter_root / ".explorer"
    out_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            str(PASS1_SCRIPT),
            str(chapter_root),
            "--output-dir",
            str(out_dir),
        ],
        f"Pass 1 extract: {chapter_root}",
    )
    return out_dir


def compile_chapter(chapter_root: Path, explorer_dir: Path) -> Path:
    run(
        [
            sys.executable,
            str(PASS2_SCRIPT),
            str(chapter_root),
            "--output-dir",
            str(explorer_dir),
        ],
        f"Pass 2 compile: {chapter_root}",
    )
    return explorer_dir / "knowledge.json"


def load_json(path: Path) -> dict | list:
    if not path.exists():
        raise SystemExit(f"Expected generated JSON is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def chapter_title(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def section_title(slug: str) -> str:
    return chapter_title(slug)


def registry_toc(registry: dict) -> list[dict]:
    toc: list[dict] = []
    for volume in registry.get("volumes", []):
        toc_books: list[dict] = []
        for book in volume.get("books", []):
            toc_chapters: list[dict] = []
            for chapter in book.get("expected_toc", []):
                chapter_slug = str(chapter["chapter"])
                toc_chapters.append(
                    {
                        "id": chapter_slug,
                        "title": chapter_title(chapter_slug),
                        "sections": [
                            {"id": str(note), "title": section_title(str(note))}
                            for note in chapter.get("notes", [])
                        ],
                    }
                )
            toc_books.append(
                {
                    "id": str(book["slug"]),
                    "title": str(book["title"]),
                    "order": int(book["order"]),
                    "book_dir": str(book["book_dir"]),
                    "chapters": toc_chapters,
                }
            )
        toc.append(
            {
                "id": int(volume["volume_number"]),
                "roman": str(volume["roman"]),
                "title": str(volume["display_title"]),
                "series_title": str(volume.get("series_title", "")),
                "books": toc_books,
            }
        )
    return toc


def enrich_node(node: dict, spec: ChapterSpec) -> dict:
    node["volume"] = spec.volume_number
    node["volume_roman"] = spec.volume_roman
    node["volume_title"] = spec.volume_title
    node["series_title"] = spec.series_title
    node["book"] = spec.book_slug
    node["book_title"] = spec.book_title
    node["book_order"] = spec.book_order
    node["book_dir"] = spec.book_dir
    node["chapter"] = spec.chapter
    node.setdefault("chapter_title", chapter_title(spec.chapter))
    return node


def merge_knowledge(chapters: list[tuple[ChapterSpec, Path]], registry: dict) -> None:
    all_nodes: list[dict] = []
    all_edges: list[dict] = []
    all_errors: list[dict] = []
    all_edge_errors: list[dict] = []
    chapter_names: list[str] = []

    for spec, chapter_root in chapters:
        exp = chapter_root / ".explorer"
        k = load_json(exp / "knowledge.json")
        e = load_json(exp / "graph-edges.json")
        pe = load_json(exp / "proof-errors.json")
        ge = load_json(exp / "graph-edge-errors.json")

        if not isinstance(k, dict) or "nodes" not in k:
            raise SystemExit(f"Malformed chapter knowledge JSON: {exp / 'knowledge.json'}")
        if not isinstance(e, list):
            raise SystemExit(f"Malformed chapter edge JSON: {exp / 'graph-edges.json'}")
        if not isinstance(pe, dict) or "errors" not in pe:
            raise SystemExit(f"Malformed proof error JSON: {exp / 'proof-errors.json'}")
        if not isinstance(ge, dict) or "errors" not in ge:
            raise SystemExit(f"Malformed graph edge error JSON: {exp / 'graph-edge-errors.json'}")

        all_nodes.extend(enrich_node(node, spec) for node in k["nodes"])
        chapter_names.append(spec.chapter)
        all_edges.extend(e)
        all_errors.extend(pe["errors"])
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
            "schema_version": "0.5",
            "script": "scripts/run_extraction.py",
            "source": "split-volume-repositories",
            "source_registry": "lra-governance/docs/architecture/book-registry.json",
            "toc": registry_toc(registry),
        },
        "nodes": all_nodes,
        "edges": deduped_edges,
    }

    COMBINED_KNOWLEDGE.write_text(json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8")
    COMBINED_EDGES.write_text(json.dumps(deduped_edges, indent=2, ensure_ascii=False), encoding="utf-8")
    COMBINED_ERRORS.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "chapters": chapter_names,
                "error_count": len(all_errors),
                "errors": all_errors,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    COMBINED_EDGE_ERRORS.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "chapters": chapter_names,
                "error_count": len(all_edge_errors),
                "errors": all_edge_errors,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repos-root",
        type=Path,
        default=REPO_ROOT.parent,
        help="Workspace containing lra-volume-* repositories.",
    )
    parser.add_argument(
        "--book-registry",
        type=Path,
        default=DEFAULT_BOOK_REGISTRY,
        help="Canonical lra-governance book registry JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repos_root = args.repos_root.resolve()
    require_file(PASS1_SCRIPT, "pass 1 extractor")
    require_file(PASS2_SCRIPT, "pass 2 compiler")
    registry = load_book_registry(args.book_registry.resolve())

    chapters = [(spec, require_chapter(repos_root, spec)) for spec in specs_from_registry(registry)]
    for _spec, chapter in chapters:
        explorer_dir = extract_chapter(chapter)
        compile_chapter(chapter, explorer_dir)

    print("\n[INFO] Merging split-volume chapter outputs into explorer JSON ...")
    merge_knowledge(chapters, registry)
    print(f"[INFO] Wrote {COMBINED_KNOWLEDGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
