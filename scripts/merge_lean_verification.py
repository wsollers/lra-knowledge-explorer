#!/usr/bin/env python3
"""Merge Lean verification metadata into Knowledge Explorer nodes.

The script scans Lean source files for Volume II declarations that carry a
nearby `Notes cross-ref` comment, maps the referenced LaTeX label to explorer
nodes, and attaches a `verification` object with module, declaration, status,
source path, and base64-encoded Lean code.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DECL_RE = re.compile(
    r"^(?P<prefix>(?:noncomputable\s+|private\s+|protected\s+|partial\s+)*)"
    r"(?P<kind>theorem|lemma|def|structure|axiom|abbrev|instance)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_'.]*)",
    re.MULTILINE,
)
CROSS_REF_RE = re.compile(r"\*Notes cross-ref:\*[\s\S]{0,260}", re.MULTILINE)
EXPLICIT_LABEL_RE = re.compile(r"\b(?P<prefix>def|thm|lem|prop|cor|ax):(?P<slug>[A-Za-z0-9_.-]+)\b")
ANCHOR_RE = re.compile(r"#(?P<anchor>[A-Za-z0-9_.-]+)")
PREFIX_BY_WORD = {
    "definition": "def",
    "theorem": "thm",
    "lemma": "lem",
    "proposition": "prop",
    "corollary": "cor",
    "axiom": "ax",
}
LABEL_ALIASES = {
    # Peano systems: older Lean note anchors -> current extracted labels.
    "thm:successor-preserves-inequality": "thm:successor-inequality-reflection",
    "thm:every-element-is-either-one-or-a-successor": "thm:every-element-is-one-or-a-successor",
    "thm:successor-is-not-self": "thm:no-object-is-its-own-successor",
    "def:successor-closed-subset-of-a-peano-system": "def:successor-closed-subset",
    "def:inductive-subset-of-a-peano-system": "def:inductive-subset-of-peano-system",
    "def:predecessor-in-a-peano-system": "def:predecessor-in-peano-system",
    "def:iterator-data": "def:iterator-data-on-peano-system",
    "thm:completeness-of-the-minimal-iterator-relation": "lem:minimal-iterator-relation-complete",
    "thm:determinism-of-the-minimal-iterator-relation": "lem:minimal-iterator-relation-deterministic",
    "thm:forced-successor-values-are-unique": "lem:forced-values-are-unique",
    "thm:iterator-base-clause": "thm:iterator-base-value",
    "thm:iterator-successor-clause": "thm:iterator-successor-step",
    "thm:uniqueness-of-iterator-functions": "lem:uniqueness-of-iterator-functions",
    "thm:existence-of-an-iterator-function": "lem:existence-of-iterator-function",

    # Natural numbers: Landau-style Lean anchors -> current Volume II labels.
    "def:addition-on-a-peano-system": "def:addition-on-peano-system",
    "thm:addition-base-clause": "thm:addition-with-one",
    "thm:addition-successor-clause": "thm:addition-successor-on-right",
    "thm:addition-is-associative": "thm:addition-associative",
    "def:multiplication-on-a-peano-system": "def:multiplication-on-peano-system",
    "thm:multiplication-base-clause": "thm:multiplication-with-one",
    "thm:multiplication-successor-clause": "thm:multiplication-successor-on-right",
    "thm:mul-one-left": "thm:one-times-n",
    "thm:multiplication-is-associative": "thm:multiplication-associative",
    "thm:mul-distrib-add": "thm:multiplication-distributes-over-addition",
    "thm:multiplication-is-commutative": "thm:multiplication-commutative",
    "def:lt-on-a-peano-system": "def:strict-less-than-on-peano-system",
    "def:le-on-a-peano-system": "def:less-than-or-equal-on-peano-system",
}


@dataclass(slots=True)
class LeanDecl:
    label: str
    module: str
    declaration: str
    kind: str
    source_path: str
    code: str
    status: str


def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def module_name(path: Path, lean_root: Path) -> str:
    relative = path.relative_to(lean_root).with_suffix("")
    return ".".join(relative.parts)


def label_from_cross_ref(text: str) -> str | None:
    explicit = EXPLICIT_LABEL_RE.search(text)
    if explicit:
        return f"{explicit.group('prefix')}:{explicit.group('slug')}"

    anchors = ANCHOR_RE.findall(text)
    for anchor in anchors:
        for word, prefix in PREFIX_BY_WORD.items():
            marker = word + "-"
            if anchor.startswith(marker):
                return f"{prefix}:{anchor[len(marker):]}"
    return None


def declaration_extent(text: str, match: re.Match[str], next_match: re.Match[str] | None) -> str:
    start = match.start()
    end = next_match.start() if next_match else len(text)
    code = text[start:end].rstrip()
    doc_start = code.rfind("\n/--")
    if doc_start != -1:
        separator_start = code.rfind("\n\n-- =", 0, doc_start)
        code = code[: separator_start if separator_start != -1 else doc_start].rstrip()
    return code


def preceding_cross_ref(text: str, start: int) -> str | None:
    window_start = max(0, start - 900)
    window = text[window_start:start]
    matches = list(CROSS_REF_RE.finditer(window))
    if not matches:
        return None
    return matches[-1].group(0)


def declaration_status(code: str) -> str:
    lowered = code.lower()
    if re.search(r"\b(sorry|admit)\b", lowered):
        return "statement"
    return "checked"


def scan_lean(lean_root: Path, volume_dir: Path) -> list[LeanDecl]:
    out: list[LeanDecl] = []
    for path in sorted(volume_dir.rglob("*.lean")):
        text = path.read_text(encoding="utf-8")
        decls = list(DECL_RE.finditer(text))
        for index, match in enumerate(decls):
            cross_ref = preceding_cross_ref(text, match.start())
            if not cross_ref:
                continue
            label = label_from_cross_ref(cross_ref)
            if not label:
                continue
            code = declaration_extent(text, match, decls[index + 1] if index + 1 < len(decls) else None)
            out.append(
                LeanDecl(
                    label=label,
                    module=module_name(path, lean_root),
                    declaration=match.group("name"),
                    kind=match.group("kind"),
                    source_path=path.relative_to(lean_root).as_posix(),
                    code=code,
                    status=declaration_status(code),
                )
            )
    return out


def merge_verification(knowledge: dict[str, Any], decls: list[LeanDecl]) -> dict[str, int]:
    nodes = knowledge.get("nodes", [])
    by_label: dict[str, LeanDecl] = {}
    duplicate_labels: set[str] = set()
    aliases_used = 0
    for decl in decls:
        target_label = LABEL_ALIASES.get(decl.label, decl.label)
        if target_label != decl.label:
            aliases_used += 1
        if target_label in by_label:
            duplicate_labels.add(target_label)
            continue
        by_label[target_label] = decl

    matched = 0
    checked = 0
    statement = 0
    for node in nodes:
        labels = [node.get("id"), node.get("label"), *(node.get("labels") or []), *(node.get("seed_labels") or [])]
        decl = next((by_label[label] for label in labels if label in by_label), None)
        if not decl:
            continue
        target_label = next(label for label in labels if label in by_label)
        node["verification"] = {
            "system": "Lean 4",
            "status": decl.status,
            "label": target_label,
            "cross_ref_label": decl.label,
            "module": decl.module,
            "declaration": decl.declaration,
            "source_path": decl.source_path,
            "kind": decl.kind,
            "code_b64": b64(decl.code),
        }
        matched += 1
        if decl.status == "checked":
            checked += 1
        else:
            statement += 1

    return {
        "lean_declarations": len(decls),
        "unique_labels": len(by_label),
        "duplicate_labels": len(duplicate_labels),
        "aliases_used": aliases_used,
        "matched_nodes": matched,
        "checked_nodes": checked,
        "statement_nodes": statement,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge Volume II Lean verification data into knowledge.json.")
    parser.add_argument("--knowledge", type=Path, default=Path("knowledge.json"))
    parser.add_argument("--lean-root", type=Path, default=Path("../lra-lean"))
    parser.add_argument("--volume-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=Path("lean-verification-report.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    knowledge_path = args.knowledge.resolve()
    lean_root = args.lean_root.resolve()
    volume_dir = (args.volume_dir.resolve() if args.volume_dir else lean_root / "LRA" / "VolumeII")
    out_path = args.out.resolve() if args.out else knowledge_path

    knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))
    decls = scan_lean(lean_root, volume_dir)
    summary = merge_verification(knowledge, decls)

    out_path.write_text(json.dumps(knowledge, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.report.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
