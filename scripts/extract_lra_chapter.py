#!/usr/bin/env python3
"""
Extract structured theorem-like data from a standardized Learning Real Analysis chapter.

What it does
------------
- Recurses through a chapter's notes/ and proofs/ trees.
- Extracts theorem-like environments from note files, even when nested inside tcolorbox.
- Captures immediate trailing remark* blocks attached to each theorem-like item.
- Promotes definition-attached Examples and Non-Examples remark blocks into
  metadata fields without creating graph nodes.
- Maps proof files to theorem-like items via:
    * \\hyperref[prf:...] links inside note blocks
    * \\label{prf:...} inside proof files
    * \\hyperref[thm:...] / return links inside proof files
- Captures \\ProofVaultURL{...} backlinks inside proof files.
- Stores raw LaTeX in base64 in the output JSON.
- Emits a seed knowledge file and a minimal edge file.

This is intentionally a seed-data extractor, not a full semantic compiler.
It preserves raw standardized LaTeX so later passes can interpret house-style blocks.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

TARGET_ENVS = {
    "definition",
    "theorem",
    "lemma",
    "proposition",
    "corollary",
    "axiom",
    "definition*",
    "theorem*",
    "lemma*",
    "proposition*",
    "corollary*",
    "axiom*",
}

REMARK_ENV = "remark*"

SECTIONING_ENVS = {
    "section",
    "subsection",
    "subsubsection",
    "paragraph",
    "subparagraph",
}

BEGIN_END_RE = re.compile(r"\\(begin|end)\{([A-Za-z*]+)\}")
LABEL_RE = re.compile(r"\\label\{([^{}]+)\}")
HYPERREF_RE = re.compile(r"\\hyperref\[([^\]]+)\]")
PROOF_VAULT_URL_RE = re.compile(r"\\ProofVaultURL\s*\{([^{}]+)\}")
INPUT_RE = re.compile(r"\\(?:input|include)\{([^{}]+)\}")
SECTION_RE = re.compile(r"\\(?:section|subsection|subsubsection)\{([^{}]+)\}")
STRIP_CMD_RE = re.compile(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})?")
WHITESPACE_RE = re.compile(r"\s+")
HTML_LIST_TAG_RE = re.compile(r"</?(?:ul|ol|li)\b[^>]*>", re.IGNORECASE)


@dataclass(slots=True)
class EnvBlock:
    name: str
    begin_start: int
    begin_end: int
    end_start: int
    end_end: int
    content_start: int
    content_end: int
    parent: int | None = None
    children: list[int] = field(default_factory=list)

    def raw(self, text: str) -> str:
        return text[self.begin_start : self.end_end]

    def content(self, text: str) -> str:
        return text[self.content_start : self.content_end]


@dataclass(slots=True)
class ExtractedItem:
    id: str
    kind: str
    env_name: str
    title: str
    label: str
    source_path: str
    chapter: str
    section_slug: str
    note_dir: str
    raw_latex_b64: str
    body_latex_b64: str
    title_latex_b64: str
    labels: list[str]
    proof_refs: list[str]
    theorem_refs: list[str]
    remark_blocks: list[dict[str, Any]]
    examples: list[dict[str, Any]] = field(default_factory=list)
    non_examples: list[dict[str, Any]] = field(default_factory=list)
    proof_source_path: str | None = None
    proof_labels: list[str] = field(default_factory=list)
    proof_return_targets: list[str] = field(default_factory=list)
    proof_vault_url: str = ""
    proof_raw_latex_b64: str | None = None
    proof_file_blocks: list[dict[str, Any]] = field(default_factory=list)
    text_preview: str = ""


def b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def strip_comments_keep_length(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "%":
            backslashes = 0
            j = i - 1
            while j >= 0 and text[j] == "\\":
                backslashes += 1
                j -= 1
            if backslashes % 2 == 0:
                while i < n and text[i] != "\n":
                    out.append(" ")
                    i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def skip_optional_arg(text: str, pos: int) -> int:
    i = pos
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    if i >= n or text[i] != "[":
        return pos
    depth = 0
    i += 1
    while i < n:
        ch = text[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            if depth == 0:
                return i + 1
            depth -= 1
        i += 1
    return pos


def parse_env_tree(text: str) -> list[EnvBlock]:
    masked = strip_comments_keep_length(text)
    stack: list[tuple[str, int, int, int]] = []
    envs: list[EnvBlock] = []
    for m in BEGIN_END_RE.finditer(masked):
        kind, name = m.group(1), m.group(2)
        if kind == "begin":
            stack.append((name, m.start(), m.end(), skip_optional_arg(masked, m.end())))
        else:
            for idx in range(len(stack) - 1, -1, -1):
                if stack[idx][0] == name:
                    name0, begin_start, begin_end, content_start = stack.pop(idx)
                    parent = stack[-1][1] if stack else None
                    envs.append(
                        EnvBlock(
                            name=name0,
                            begin_start=begin_start,
                            begin_end=begin_end,
                            end_start=m.start(),
                            end_end=m.end(),
                            content_start=content_start,
                            content_end=m.start(),
                            parent=parent,
                        )
                    )
                    break
    envs.sort(key=lambda e: (e.begin_start, e.end_end))
    begin_to_idx = {e.begin_start: i for i, e in enumerate(envs)}
    for i, e in enumerate(envs):
        if e.parent in begin_to_idx:
            parent_idx = begin_to_idx[e.parent]
            envs[i].parent = parent_idx
            envs[parent_idx].children.append(i)
        else:
            envs[i].parent = None
    return envs


def extract_optional_arg(text: str, pos: int) -> tuple[str, int]:
    i = pos
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    if i >= n or text[i] != "[":
        return "", i
    depth = 0
    start = i + 1
    i += 1
    while i < n:
        ch = text[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            if depth == 0:
                return text[start:i], i + 1
            depth -= 1
        i += 1
    return "", pos


def read_braced_arg(text: str, pos: int) -> tuple[str, int] | None:
    i = pos
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    if i >= n or text[i] != "{":
        return None
    depth = 0
    start = i + 1
    i += 1
    while i < n:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            if depth == 0:
                return text[start:i], i + 1
            depth -= 1
        i += 1
    return None


def replace_two_arg_command(text: str, command: str, arg_index: int) -> str:
    needle = "\\" + command
    out: list[str] = []
    i = 0
    while True:
        j = text.find(needle, i)
        if j < 0:
            out.append(text[i:])
            break
        first = read_braced_arg(text, j + len(needle))
        if not first:
            out.append(text[i : j + len(needle)])
            i = j + len(needle)
            continue
        second = read_braced_arg(text, first[1])
        if not second:
            out.append(text[i : first[1]])
            i = first[1]
            continue
        out.append(text[i:j])
        out.append(first[0] if arg_index == 0 else second[0])
        i = second[1]
    return "".join(out)


def clean_title(title: str) -> str:
    t = strip_comments_keep_length(title).strip()
    t = replace_two_arg_command(t, "texorpdfstring", 1)
    t = re.sub(r"\\hyperref\[[^\]]+\]\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\\(?:textbf|textit|emph|mathrm|mathsf|small)\{([^{}]*)\}", r"\1", t)
    t = STRIP_CMD_RE.sub(r" ", t)
    t = t.replace("{", " ").replace("}", " ")
    t = WHITESPACE_RE.sub(" ", t).strip()
    return t


def infer_kind(env_name: str) -> str:
    return env_name.replace("*", "").capitalize()


def clean_preview(latex: str, limit: int = 220) -> str:
    s = SECTION_RE.sub(" ", latex)
    s = HTML_LIST_TAG_RE.sub(" ", s)
    s = STRIP_CMD_RE.sub(" ", s)
    s = s.replace("{", " ").replace("}", " ")
    s = WHITESPACE_RE.sub(" ", s).strip()
    return s[:limit]


def relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def find_section_slug(path: Path, chapter_root: Path) -> str:
    try:
        rel = path.relative_to(chapter_root)
    except ValueError:
        return ""
    parts = rel.parts
    if len(parts) >= 3 and parts[0] == "notes":
        return parts[1]
    if len(parts) >= 3 and parts[0] == "proofs" and parts[1] == "notes":
        return "proofs"
    return ""


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def gather_tex_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.tex") if p.is_file())


def collect_proof_catalog(chapter_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    proof_root = chapter_root / "proofs" / "notes"
    label_to_proof: dict[str, dict[str, Any]] = {}
    theorem_return_to_proof: dict[str, str] = {}
    if not proof_root.exists():
        return label_to_proof, theorem_return_to_proof

    for path in gather_tex_files(proof_root):
        text = read_file(path)
        labels = LABEL_RE.findall(text)
        proof_vault_urls = PROOF_VAULT_URL_RE.findall(text)
        envs = parse_env_tree(text)
        return_theorem_targets: list[str] = []
        file_blocks: list[dict[str, Any]] = []
        for env in envs:
            if env.name in TARGET_ENVS or env.name in {"proof", REMARK_ENV}:
                title, _ = extract_optional_arg(text, env.begin_end)
                if env.name == REMARK_ENV and title.strip().lower() == "return":
                    return_targets = HYPERREF_RE.findall(env.raw(text))
                    return_theorem_targets = sorted(
                        {
                            t
                            for t in return_targets
                            if t.startswith(("def:", "thm:", "lem:", "prop:", "cor:", "ax:"))
                        }
                    )
                file_blocks.append(
                    {
                        "env_name": env.name,
                        "kind": infer_kind(env.name) if env.name in TARGET_ENVS else env.name,
                        "title": title.strip(),
                        "raw_latex_b64": b64(env.raw(text)),
                    }
                )
        record = {
            "proof_source_path": relative_posix(path, chapter_root),
            "proof_labels": labels,
            "proof_return_targets": return_theorem_targets,
            "proof_vault_url": proof_vault_urls[0].strip() if proof_vault_urls else "",
            "proof_raw_latex_b64": b64(text),
            "proof_file_blocks": file_blocks,
        }
        for lbl in labels:
            if lbl.startswith("prf:"):
                label_to_proof[lbl] = record
        for tgt in return_theorem_targets:
            theorem_return_to_proof[tgt] = relative_posix(path, chapter_root)
    return label_to_proof, theorem_return_to_proof


def enclosing_tcolorbox_end(envs: list[EnvBlock], env: EnvBlock) -> int | None:
    parent = env.parent
    while parent is not None:
        parent_env = envs[parent]
        if parent_env.name == "tcolorbox":
            return parent_env.end_end
        parent = parent_env.parent
    return None


def collect_trailing_remarks(text: str, envs: list[EnvBlock], idx: int) -> list[dict[str, Any]]:
    current = envs[idx]
    current_end = current.end_end
    wrapper_end = enclosing_tcolorbox_end(envs, current)
    out: list[dict[str, Any]] = []
    j = idx + 1
    while j < len(envs):
        nxt = envs[j]
        if nxt.begin_start < current_end:
            j += 1
            continue
        between_start = current_end
        if wrapper_end is not None and between_start < wrapper_end <= nxt.begin_start:
            between_start = wrapper_end
        between = text[between_start : nxt.begin_start]
        if between.strip():
            break
        if nxt.name != REMARK_ENV:
            break
        title, _ = extract_optional_arg(text, nxt.begin_end)
        raw = nxt.raw(text)
        out.append(
            {
                "title": title.strip(),
                "env_name": nxt.name,
                "raw_latex_b64": b64(raw),
            }
        )
        current_end = nxt.end_end
        j += 1
    return out


def make_fallback_id(kind: str, path: Path, ordinal: int) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "-", path.stem).strip("-").lower()
    return f"{kind.lower()}:{stem}:{ordinal:03d}"


def definition_boundary_metadata(kind: str, remarks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if kind != "definition":
        return [], []
    examples = [r for r in remarks if r.get("title", "").strip() == "Examples"]
    non_examples = [r for r in remarks if r.get("title", "").strip() == "Non-Examples"]
    return examples, non_examples


def extract_note_items(chapter_root: Path) -> list[ExtractedItem]:
    notes_root = chapter_root / "notes"
    chapter_name = chapter_root.name
    proof_catalog, theorem_return_to_proof = collect_proof_catalog(chapter_root)
    items: list[ExtractedItem] = []

    if not notes_root.exists():
        return items

    for path in gather_tex_files(notes_root):
        text = read_file(path)
        envs = parse_env_tree(text)
        ordinal = 0
        for idx, env in enumerate(envs):
            if env.name not in TARGET_ENVS:
                continue
            ordinal += 1
            raw = env.raw(text)
            body = env.content(text)
            title, _ = extract_optional_arg(text, env.begin_end)
            cleaned_title = clean_title(title)
            labels = LABEL_RE.findall(raw)
            label = labels[0] if labels else ""
            kind = infer_kind(env.name)
            item_id = label or make_fallback_id(kind, path, ordinal)
            proof_refs = sorted({h for h in HYPERREF_RE.findall(raw) if h.startswith("prf:")})
            theorem_refs = sorted({h for h in HYPERREF_RE.findall(raw) if h.startswith(("def:", "thm:", "lem:", "prop:", "cor:", "ax:"))})
            remarks = collect_trailing_remarks(text, envs, idx)
            examples, non_examples = definition_boundary_metadata(kind, remarks)

            item = ExtractedItem(
                id=item_id,
                kind=kind,
                env_name=env.name,
                title=cleaned_title,
                label=label,
                source_path=relative_posix(path, chapter_root),
                chapter=chapter_name,
                section_slug=find_section_slug(path, chapter_root),
                note_dir=path.parent.name,
                raw_latex_b64=b64(raw),
                body_latex_b64=b64(body),
                title_latex_b64=b64(title.strip()),
                labels=labels,
                proof_refs=proof_refs,
                theorem_refs=theorem_refs,
                remark_blocks=remarks,
                examples=examples,
                non_examples=non_examples,
                text_preview=clean_preview(raw),
            )

            matched_proof = None
            if env.name != "definition":
                for prf in proof_refs:
                    if prf in proof_catalog:
                        matched_proof = proof_catalog[prf]
                        break
                if not matched_proof and label and label in theorem_return_to_proof:
                    proof_path = theorem_return_to_proof[label]
                    for rec in proof_catalog.values():
                        if rec["proof_source_path"] == proof_path:
                            matched_proof = rec
                            break
            if matched_proof:
                item.proof_source_path = matched_proof["proof_source_path"]
                item.proof_labels = matched_proof["proof_labels"]
                item.proof_return_targets = matched_proof["proof_return_targets"]
                item.proof_vault_url = matched_proof["proof_vault_url"]
                item.proof_raw_latex_b64 = matched_proof["proof_raw_latex_b64"]
                item.proof_file_blocks = matched_proof["proof_file_blocks"]

            items.append(item)
    return items


def build_edges(items: Iterable[ExtractedItem]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        if item.proof_source_path:
            edge = (item.id, f"proof-file:{item.proof_source_path}", "has_proof_file")
            if edge not in seen:
                seen.add(edge)
                edges.append({"from": edge[0], "to": edge[1], "kind": edge[2]})
        for prf in item.proof_refs:
            edge = (item.id, prf, "links_to_proof")
            if edge not in seen:
                seen.add(edge)
                edges.append({"from": edge[0], "to": edge[1], "kind": edge[2]})
        for ref in item.theorem_refs:
            edge = (item.id, ref, "references")
            if edge not in seen:
                seen.add(edge)
                edges.append({"from": edge[0], "to": edge[1], "kind": edge[2]})
    return edges


def item_to_json(item: ExtractedItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind,
        "env_name": item.env_name,
        "title": item.title,
        "label": item.label,
        "chapter": item.chapter,
        "section_slug": item.section_slug,
        "note_dir": item.note_dir,
        "source_path": item.source_path,
        "proof_source_path": item.proof_source_path,
        "labels": item.labels,
        "proof_labels": item.proof_labels,
        "proof_refs": item.proof_refs,
        "theorem_refs": item.theorem_refs,
        "proof_return_targets": item.proof_return_targets,
        "proof_vault_url": item.proof_vault_url,
        "raw_latex_b64": item.raw_latex_b64,
        "body_latex_b64": item.body_latex_b64,
        "title_latex_b64": item.title_latex_b64,
        "proof_raw_latex_b64": item.proof_raw_latex_b64,
        "remark_blocks": item.remark_blocks,
        "examples": item.examples,
        "non_examples": item.non_examples,
        "proof_file_blocks": item.proof_file_blocks,
        "text_preview": item.text_preview,
    }


def infer_output_dir(chapter_root: Path) -> Path:
    out = chapter_root / ".explorer"
    out.mkdir(parents=True, exist_ok=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract theorem-like seed data from an LRA chapter.")
    parser.add_argument("chapter", type=Path, help="Path to the chapter directory")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--knowledge-name", default="knowledge-seed.json")
    parser.add_argument("--edges-name", default="graph-edges-seed.json")
    args = parser.parse_args()

    chapter_root = args.chapter.resolve()
    if not chapter_root.exists() or not chapter_root.is_dir():
        raise SystemExit(f"Chapter directory not found: {chapter_root}")
    if not (chapter_root / "notes").exists():
        raise SystemExit(f"Not an LRA chapter root (missing notes/): {chapter_root}")

    items = extract_note_items(chapter_root)
    edges = build_edges(items)

    output_dir = args.output_dir.resolve() if args.output_dir else infer_output_dir(chapter_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    knowledge = {
        "chapter": chapter_root.name,
        "source_root": chapter_root.as_posix(),
        "node_count": len(items),
        "nodes": [item_to_json(x) for x in items],
    }
    (output_dir / args.knowledge_name).write_text(json.dumps(knowledge, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / args.edges_name).write_text(json.dumps(edges, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Extracted {len(items)} theorem-like items from {chapter_root.name}")
    print(f"Wrote: {(output_dir / args.knowledge_name).as_posix()}")
    print(f"Wrote: {(output_dir / args.edges_name).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
