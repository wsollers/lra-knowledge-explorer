#!/usr/bin/env python3
r"""
Extract structured theorem-like data from a standardized Learning Real Analysis chapter.

What it does
------------
- Recurses through a chapter's notes/ and proofs/ trees.
- Extracts theorem-like environments from note files, even when nested inside tcolorbox.
- Captures immediate trailing remark* blocks attached to each theorem-like item.
- Captures \begin{dependencies}...\end{dependencies} blocks that follow each item
  (after its enclosing tcolorbox if present) and before the next theorem-like
  environment begins — emitted as dependency_refs and depends_on graph edges.
- Promotes item-attached Exposition remark blocks into metadata fields without
  creating graph nodes.
- Maps proof files to theorem-like items via:
    * \\hyperref[prf:...] links inside note blocks
    * \\label{prf:...} inside proof files
    * \\hyperref[thm:...] / return links inside proof files
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
import sys
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

# Semantic statement boxes: \newtcolorbox wrappers from common/boxes.tex. Source
# now wraps each theorem-like env as
#   \begin{definitionbox}{..}\begin{definition}..\end{definition}\end{definitionbox}
# so trailing remark*/dependencies blocks sit AFTER the box close, not after
# \end{<env>}. These names must be treated both as the enclosing wrapper (so the
# trailing window jumps past the box close) and as node-opening fences.
SEMANTIC_BOX_ENVS = {
    "tcolorbox",
    "definitionbox",
    "definitionalbox",
    "axiombox",
    "theorembox",
    "lemmabox",
    "propositionbox",
    "corollarybox",
}

# Environments whose \begin signals we must not scan past when looking for
# a trailing dependencies block.  Includes all theorem-like envs plus
# structural wrappers that open a new logical node.
LOOKAHEAD_FENCE_ENVS = TARGET_ENVS | {"topicbox"} | SEMANTIC_BOX_ENVS

SECTIONING_ENVS = {
    "section",
    "subsection",
    "subsubsection",
    "paragraph",
    "subparagraph",
}

BEGIN_END_RE = re.compile(r"\\(begin|end)\{([A-Za-z*_-]+)\}")
LABEL_RE = re.compile(r"\\label\{([^{}]+)\}")
HYPERREF_RE = re.compile(r"\\hyperref\[([^\]]+)\]")
INPUT_RE = re.compile(r"\\(?:input|include)\{([^{}]+)\}")
SECTION_RE = re.compile(r"\\(?:section|subsection|subsubsection)\{([^{}]+)\}")
# Definitional roots: a bare \DefinitionalRoot macro placed in the trailing
# window after a formal environment marks that item as a primitive / undefined
# notion (a legitimate leaf of the dependency tree).  Detection mirrors the
# governance audit (tools/governance/dependency_graph.py): the macro is matched
# on a word boundary, and the trailing window is bounded by the next formal
# environment / structural wrapper or the next sectioning command.
DEFINITIONAL_ROOT_RE = re.compile(r"\\DefinitionalRoot\b")
NO_LOCAL_DEPENDENCIES_RE = re.compile(r"\\NoLocalDependencies\b")
SOURCE_VARIANT_RE = re.compile(
    r"\\SourceVariantOf"
    r"\{(?P<target>(?:def|ax|thm|lem|prop|cor):[^{}]+)\}"
    r"\{(?P<author>[^{}]+)\}"
    r"\{(?P<book>[^{}]+)\}"
    r"\{(?P<kind>source_variant_of|reduces_to)\}",
    re.IGNORECASE,
)
DEFROOT_BOUNDARY_RE = re.compile(r"\\(?:chapter|section|subsection|subsubsection)\*?\{")
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
    dependency_refs: list[str]
    remark_blocks: list[dict[str, Any]]
    dependency_blocks: list[dict[str, Any]] = field(default_factory=list)
    source_variants: list[dict[str, Any]] = field(default_factory=list)
    no_local_dependencies: bool = False
    expositions: list[dict[str, Any]] = field(default_factory=list)
    proof_source_path: str | None = None
    proof_labels: list[str] = field(default_factory=list)
    proof_return_targets: list[str] = field(default_factory=list)
    proof_raw_latex_b64: str | None = None
    proof_file_blocks: list[dict[str, Any]] = field(default_factory=list)
    proof_dependency_refs: list[str] = field(default_factory=list)
    text_preview: str = ""
    definitional_root: bool = False


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
    stack: list[tuple[str, int, int, int]] = []  # env_name, token_start, token_end, content_start
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
    # pos points just after \begin{env}
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


def line_number(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "item"


def relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def find_governance_tools_root(path: Path) -> Path | None:
    """Return the governance checkout that provides the file inventory.

    Extraction intentionally uses the same live TeX inventory provider as the
    volume validators: ``tools/governance/core/file_inventory.py``. Split-volume
    checkouts keep that provider in the sibling ``lra-governance`` repository.
    """
    start = path.resolve()
    for candidate in (start, *start.parents):
        provider = candidate / "tools" / "governance" / "core" / "file_inventory.py"
        if provider.is_file():
            return candidate
        sibling = candidate / "lra-governance" / "tools" / "governance" / "core" / "file_inventory.py"
        if sibling.is_file():
            return candidate / "lra-governance"
    return None


def validator_live_tex_files(root: Path, *, allow_empty: bool = False) -> list[Path]:
    """Return live TeX files exactly as the volume validator inventory sees them."""
    repo_root = find_governance_tools_root(root)
    if repo_root is None:
        entry = root / "index.tex"
        if entry.is_file():
            return live_tex_closure(entry, root.parent)
        return sorted(path.resolve() for path in root.rglob("*.tex"))
    governance_tools = repo_root / "tools" / "governance"
    governance_tools_s = str(governance_tools)
    if governance_tools_s not in sys.path:
        sys.path.insert(0, governance_tools_s)

    from core.file_inventory import files_to_validate  # type: ignore

    files = [Path(p).resolve() for p in files_to_validate([root], only_reachable=True, include_excluded=True)]
    if not files and not allow_empty:
        raise SystemExit(f"No live TeX files found by validator inventory: {root}")
    return files


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


def _find_repo_root(start: Path, sample_target: str) -> Path | None:
    r"""Find the ancestor of ``start`` under which a repo-root-relative
    ``\input`` target (e.g. ``volume-ii/reals/notes/x/index``) resolves. LRA
    ``\input`` paths are relative to the LaTeX compile root — the directory that
    holds the ``volume-*`` dirs."""
    if not sample_target:
        return None
    first = Path(sample_target).parts[0]
    p = start
    while True:
        if (p / first).is_dir():
            return p
        if p == p.parent:
            return None
        p = p.parent


def _resolve_input_target(target: str, repo_root: Path | None, including_file: Path) -> Path | None:
    r"""Resolve one ``\input``/``\include`` target to a real ``.tex`` file.
    Targets omit the ``.tex`` extension and are normally repo-root-relative;
    fall back to a path relative to the including file's own directory."""
    target = target.strip()
    names = [target] if target.endswith(".tex") else [target + ".tex", target + "/index.tex"]
    roots = [r for r in (repo_root, including_file.parent) if r is not None]
    for root in roots:
        for name in names:
            cand = root / name
            if cand.is_file():
                return cand.resolve()
    return None


def live_tex_closure(index_file: Path, chapter_root: Path) -> list[Path]:
    r"""Return the ``.tex`` files reachable from ``index_file`` by transitively
    following ``\input``/``\include`` — the files the book actually compiles, in
    document order. Intermediate index files are included (harmless: they carry
    no theorem environments). Returns ``[]`` if ``index_file`` is absent so the
    caller can fall back to a directory scan."""
    if not index_file.is_file():
        return []
    head = strip_comments_keep_length(read_file(index_file))
    repo_root = None
    for t in INPUT_RE.findall(head):
        repo_root = _find_repo_root(chapter_root, t)
        if repo_root:
            break
    seen: set[Path] = set()
    order: list[Path] = []
    stack = [index_file.resolve()]
    while stack:
        f = stack.pop()
        if f in seen or not f.is_file():
            continue
        seen.add(f)
        order.append(f)
        body = strip_comments_keep_length(read_file(f))
        resolved = [r for r in (_resolve_input_target(t, repo_root, f)
                                for t in INPUT_RE.findall(body)) if r]
        for nxt in reversed(resolved):   # reversed so the first \input is popped first
            stack.append(nxt)
    return order


def extract_dependencies_block(text: str) -> list[str]:
    r"""Return the sorted hyperref labels inside every ``\begin{dependencies}``
    block in ``text``. Used for proof files: the proof's dependency block records
    what the *proof* uses, which is distinct from the theorem's conceptual
    dependencies declared in the notes (those remain the `depends_on` set)."""
    refs: set[str] = set()
    for env in parse_env_tree(text):
        if env.name == "dependencies":
            refs.update(h for h in HYPERREF_RE.findall(env.raw(text)) if ":" in h)
    return sorted(refs)


def collect_proof_catalog(chapter_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    # Proofs live under proofs/<topic>/prf-*.tex (older trees used proofs/notes/);
    # scan the whole proofs/ subtree so either layout resolves.
    proof_root = chapter_root / "proofs"
    label_to_proof: dict[str, dict[str, Any]] = {}
    theorem_return_to_proof: dict[str, str] = {}
    if not proof_root.exists():
        return label_to_proof, theorem_return_to_proof

    proof_root_resolved = proof_root.resolve()
    proof_files = [
        p for p in validator_live_tex_files(proof_root, allow_empty=True)
        if p == proof_root_resolved / "index.tex" or proof_root_resolved in p.parents
    ]

    for path in proof_files:
        text = read_file(path)
        labels = LABEL_RE.findall(text)
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
            "proof_raw_latex_b64": b64(text),
            "proof_file_blocks": file_blocks,
            "proof_dependency_refs": extract_dependencies_block(text),
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
        if parent_env.name in SEMANTIC_BOX_ENVS:
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
                "body_latex_b64": b64(nxt.content(text).strip()),
                "body_preview": clean_preview(nxt.content(text)),
                "source_line_start": line_number(text, nxt.begin_start),
                "source_line_end": line_number(text, nxt.end_end),
            }
        )
        current_end = nxt.end_end
        j += 1
    return out


def dependency_block_json(text: str, env: EnvBlock, *, hidden: bool) -> dict[str, Any]:
    refs = sorted({h for h in HYPERREF_RE.findall(env.raw(text)) if ":" in h})
    return {
        "env_name": env.name,
        "hidden": hidden,
        "refs": refs,
        "raw_latex_b64": b64(env.raw(text)),
        "body_latex_b64": b64(env.content(text).strip()),
        "body_preview": clean_preview(env.content(text)),
        "source_line_start": line_number(text, env.begin_start),
        "source_line_end": line_number(text, env.end_end),
    }


def dependency_info_from_hidden(text: str, envs: list[EnvBlock], hidden_idx: int) -> tuple[list[str], list[dict[str, Any]], bool]:
    hidden = envs[hidden_idx]
    raw = hidden.raw(text)
    no_local = bool(NO_LOCAL_DEPENDENCIES_RE.search(strip_comments_keep_length(raw)))
    blocks: list[dict[str, Any]] = []
    refs: list[str] = []
    for child_idx in hidden.children:
        child = envs[child_idx]
        if child.name != "dependencies":
            continue
        block = dependency_block_json(text, child, hidden=True)
        blocks.append(block)
        refs.extend(block["refs"])
    return sorted(set(refs)), blocks, no_local


def collect_dependency_info(text: str, envs: list[EnvBlock], idx: int) -> tuple[list[str], list[dict[str, Any]], bool]:
    """Return dependency refs, serialized blocks, and no-local flag for an item.

    Search strategy
    ---------------
    Start scanning *after* the item's enclosing tcolorbox (if any), otherwise
    after the item itself.  Walk forward through the env list, skipping only:

      - envs that are nested inside the already-consumed region (they were
        already visited as children)
      - remark* blocks (they trail the tcolorbox and precede dependencies)

    Stop immediately — returning [] — if we encounter any env whose *begin*
    falls inside a LOOKAHEAD_FENCE_ENV (TARGET_ENVS | topicbox | tcolorbox).
    That means a new node is starting and this item simply has no dependencies
    block.

    Also stop if there is any non-whitespace text between the current scan
    position and the next env that is not accounted for by a remark* or
    dependencies block we just consumed.
    """
    current = envs[idx]
    wrapper_end = enclosing_tcolorbox_end(envs, current)
    # scan_from: the position in the text from which we look for the next env
    scan_from = wrapper_end if wrapper_end is not None else current.end_end

    j = idx + 1
    while j < len(envs):
        nxt = envs[j]

        # Skip envs that are nested inside what we've already consumed
        if nxt.begin_start < scan_from:
            j += 1
            continue

        # Hard fence: a new theorem-like env or structural wrapper is beginning.
        # This item has no dependencies block — bail out immediately.
        if nxt.name in LOOKAHEAD_FENCE_ENVS:
            return [], [], False

        # Gap check: if there is non-whitespace text between scan_from and the
        # next env, something unexpected is in the way — stop safely.
        between = text[scan_from : nxt.begin_start]
        if between.strip():
            return [], [], False

        # remark* blocks are allowed between tcolorbox and dependencies — skip.
        if nxt.name == REMARK_ENV:
            scan_from = nxt.end_end
            j += 1
            continue

        if nxt.name == "lra-not-visible":
            refs, blocks, no_local = dependency_info_from_hidden(text, envs, j)
            return refs, blocks, no_local

        # Found the dependencies block.
        if nxt.name == "dependencies":
            block = dependency_block_json(text, nxt, hidden=False)
            return block["refs"], [block], False

        # Anything else (itemize, enumerate, etc.) — not expected here, stop.
        return [], [], False

    return [], [], False


def collect_dependencies(text: str, envs: list[EnvBlock], idx: int) -> list[str]:
    refs, _blocks, _no_local = collect_dependency_info(text, envs, idx)
    return refs


def collect_definitional_root(text: str, envs: list[EnvBlock], idx: int) -> bool:
    r"""Return True if a bare ``\DefinitionalRoot`` macro appears in the trailing
    window after the theorem-like item at ``envs[idx]``.

    A definitional root is a primitive / undefined notion: the explorer's
    equivalent of an axiom-like terminal (Euclid's "point" / "line").  This
    mirrors the governance audit's ``root_kind_after_block`` so the two systems
    agree on what counts as a root:

      - the window runs from the item's own ``\end{...}`` up to the next formal
        environment / structural wrapper (``LOOKAHEAD_FENCE_ENVS``) or the next
        sectioning command, whichever comes first;
      - ``\DefinitionalRoot`` is loose text, not an environment, so it is found by
        scanning the window directly rather than through the env tree;
      - scanning starts at ``current.end_end`` so the macro is detected whether it
        sits inside the enclosing tcolorbox (between ``\end{definition}`` and the
        box close) or after the box, before the next node;
      - comments are masked first so a commented-out macro is not a false hit.
    """
    current = envs[idx]
    start = current.end_end

    # Boundary 1 — the next formal env / structural wrapper that opens a new node.
    boundary = len(text)
    for j in range(idx + 1, len(envs)):
        nxt = envs[j]
        if nxt.begin_start <= start:
            # Children of this item, or the enclosing wrapper that opened before
            # it — already accounted for; skip.
            continue
        if nxt.name in LOOKAHEAD_FENCE_ENVS:
            boundary = nxt.begin_start
            break

    # Boundary 2 — the next sectioning command, if it comes earlier.
    section = DEFROOT_BOUNDARY_RE.search(text, start)
    if section and section.start() < boundary:
        boundary = section.start()

    window = strip_comments_keep_length(text[start:boundary])
    return bool(DEFINITIONAL_ROOT_RE.search(window))


def collect_source_variants(text: str, envs: list[EnvBlock], idx: int) -> list[dict[str, Any]]:
    current = envs[idx]
    start = current.end_end
    boundary = len(text)
    for j in range(idx + 1, len(envs)):
        nxt = envs[j]
        if nxt.begin_start <= start:
            continue
        if nxt.name in LOOKAHEAD_FENCE_ENVS:
            boundary = nxt.begin_start
            break
    section = DEFROOT_BOUNDARY_RE.search(text, start)
    if section and section.start() < boundary:
        boundary = section.start()
    window = strip_comments_keep_length(text[start:boundary])
    variants: list[dict[str, Any]] = []
    for match in SOURCE_VARIANT_RE.finditer(window):
        variants.append(
            {
                "target": match.group("target").strip(),
                "author": re.sub(r"\s+", " ", match.group("author").strip()),
                "book": re.sub(r"\s+", " ", match.group("book").strip()),
                "kind": match.group("kind").strip().lower(),
                "source_line_start": line_number(text, start + match.start()),
            }
        )
    return variants


def make_fallback_id(kind: str, path: Path, ordinal: int) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "-", path.stem).strip("-").lower()
    return f"{kind.lower()}:{stem}:{ordinal:03d}"


def exposition_metadata(
    remarks: list[dict[str, Any]],
    item_id: str,
    kind: str,
    label: str,
    section_slug: str,
    source_path: str,
) -> list[dict[str, Any]]:
    expositions: list[dict[str, Any]] = []
    for index, remark in enumerate(remarks, start=1):
        if remark.get("title", "").strip() != "Exposition":
            continue
        expositions.append(
            {
                "id": f"exposition:{slugify(item_id)}:{index:02d}",
                "attached_to": item_id,
                "attached_to_kind": kind,
                "source_label": label,
                "section": section_slug,
                "heading": "Exposition",
                "source_file": source_path,
                "source_line_start": remark.get("source_line_start"),
                "source_line_end": remark.get("source_line_end"),
                "body_latex_b64": remark.get("body_latex_b64", ""),
                "body_preview": remark.get("body_preview", ""),
            }
        )
    return expositions


def extract_note_items(chapter_root: Path) -> list[ExtractedItem]:
    notes_root = chapter_root / "notes"
    chapter_name = chapter_root.name
    proof_catalog, theorem_return_to_proof = collect_proof_catalog(chapter_root)
    items: list[ExtractedItem] = []

    if not notes_root.exists():
        return items

    notes_root_resolved = notes_root.resolve()
    tex_files = [
        p for p in validator_live_tex_files(notes_root)
        if p == notes_root_resolved / "index.tex" or notes_root_resolved in p.parents
    ]

    for path in tex_files:
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
            dependency_refs, dependency_blocks, no_local_dependencies = collect_dependency_info(text, envs, idx)
            definitional_root = collect_definitional_root(text, envs, idx)
            source_variants = collect_source_variants(text, envs, idx)
            source_path = relative_posix(path, chapter_root)
            section_slug = find_section_slug(path, chapter_root)
            expositions = exposition_metadata(remarks, item_id, kind, label, section_slug, source_path)

            item = ExtractedItem(
                id=item_id,
                kind=kind,
                env_name=env.name,
                title=cleaned_title,
                label=label,
                source_path=source_path,
                chapter=chapter_name,
                section_slug=section_slug,
                note_dir=path.parent.name,
                raw_latex_b64=b64(raw),
                body_latex_b64=b64(body),
                title_latex_b64=b64(title.strip()),
                labels=labels,
                proof_refs=proof_refs,
                theorem_refs=theorem_refs,
                dependency_refs=dependency_refs,
                dependency_blocks=dependency_blocks,
                source_variants=source_variants,
                no_local_dependencies=no_local_dependencies,
                remark_blocks=remarks,
                expositions=expositions,
                text_preview=clean_preview(raw),
                definitional_root=definitional_root,
            )

            matched_proof = None
            if env.name != "definition":
                for prf in proof_refs:
                    if prf in proof_catalog:
                        matched_proof = proof_catalog[prf]
                        break
                if not matched_proof and label and label in theorem_return_to_proof:
                    proof_path = theorem_return_to_proof[label]
                    # recover full proof record by matching path in catalog
                    for rec in proof_catalog.values():
                        if rec["proof_source_path"] == proof_path:
                            matched_proof = rec
                            break
            if matched_proof:
                item.proof_source_path = matched_proof["proof_source_path"]
                item.proof_labels = matched_proof["proof_labels"]
                item.proof_return_targets = matched_proof["proof_return_targets"]
                item.proof_raw_latex_b64 = matched_proof["proof_raw_latex_b64"]
                item.proof_file_blocks = matched_proof["proof_file_blocks"]
                item.proof_dependency_refs = matched_proof.get("proof_dependency_refs", [])

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
        for dep in item.dependency_refs:
            edge = (item.id, dep, "depends_on")
            if edge not in seen:
                seen.add(edge)
                edges.append({"from": edge[0], "to": edge[1], "kind": edge[2]})
        for dep in item.proof_dependency_refs:
            edge = (item.id, dep, "proof_depends_on")
            if edge not in seen:
                seen.add(edge)
                edges.append({"from": edge[0], "to": edge[1], "kind": edge[2]})
        for variant in item.source_variants:
            edge = (item.id, variant.get("target", ""), variant.get("kind", "source_variant_of"))
            if edge[1] and edge not in seen:
                seen.add(edge)
                edges.append(
                    {
                        "from": edge[0],
                        "to": edge[1],
                        "kind": edge[2],
                        "source_author": variant.get("author", ""),
                        "source_book": variant.get("book", ""),
                    }
                )
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
        "dependency_refs": item.dependency_refs,
        "dependency_blocks": item.dependency_blocks,
        "source_variants": item.source_variants,
        "no_local_dependencies": item.no_local_dependencies,
        "proof_return_targets": item.proof_return_targets,
        "raw_latex_b64": item.raw_latex_b64,
        "body_latex_b64": item.body_latex_b64,
        "title_latex_b64": item.title_latex_b64,
        "proof_raw_latex_b64": item.proof_raw_latex_b64,
        "remark_blocks": item.remark_blocks,
        "expositions": item.expositions,
        "proof_file_blocks": item.proof_file_blocks,
        "proof_dependency_refs": item.proof_dependency_refs,
        "text_preview": item.text_preview,
        "definitional_root": item.definitional_root,
    }


def infer_output_dir(chapter_root: Path) -> Path:
    out = chapter_root / ".explorer"
    out.mkdir(parents=True, exist_ok=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract theorem-like seed data from an LRA chapter.")
    parser.add_argument("chapter", type=Path, help="Path to the chapter directory (for example: functions)")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for JSON output files")
    parser.add_argument("--knowledge-name", default="knowledge-seed.json", help="Knowledge JSON filename")
    parser.add_argument("--edges-name", default="graph-edges-seed.json", help="Edges JSON filename")
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
