"""Match propositional-logic concept decompositions to knowledge labels.

The matcher is deterministic and read-only with respect to source data. It reads
concept files and writes derived match reports under concept-pipeline/matches.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "concept-match-report-1"
MANIFEST_SCHEMA_VERSION = "concept-match-manifest-1"
TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "for",
    "from",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "then",
    "to",
    "under",
    "with",
}

SYNONYMS = {
    "formula": {"wff", "formulas"},
    "formulas": {"formula", "wff"},
    "well": {"wff"},
    "formed": {"wff"},
    "connective": {"connectives"},
    "connectives": {"connective"},
    "variable": {"variables"},
    "variables": {"variable"},
    "prop": {"propositional"},
    "propositional": {"prop"},
    "truth": {"boolean"},
    "boolean": {"truth"},
}


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


def normalize_text(value: str) -> str:
    value = value.lower()
    value = value.replace("\\", " ")
    value = value.replace("operatorname", " ")
    return value


def tokens(value: str) -> set[str]:
    found = set(TOKEN_RE.findall(normalize_text(value)))
    normalized = {token for token in found if token not in STOPWORDS}
    expanded = set(normalized)
    for token in normalized:
        expanded.update(SYNONYMS.get(token, set()))
    return expanded


def phrase(value: str) -> str:
    return " ".join(TOKEN_RE.findall(normalize_text(value)))


def compact_node(node: dict[str, Any]) -> dict[str, str]:
    return {
        "id": node.get("id") or "",
        "kind": node.get("kind") or "",
        "title": node.get("title") or "",
        "volume": node.get("volume") or "",
        "chapter": node.get("chapter") or "",
        "section": node.get("section") or "",
        "summary": node.get("statement_preview")
        or (node.get("statement_display") or "").replace("\n", " ")[:500],
    }


def candidate_score(concept: str, node: dict[str, Any]) -> tuple[int, list[str]]:
    concept_tokens = tokens(concept)
    concept_phrase = phrase(concept)
    node_id = node.get("id") or ""
    title = node.get("title") or ""
    summary = node.get("summary") or ""
    haystacks = {
        "id": phrase(node_id.replace(":", " ").replace("-", " ")),
        "title": phrase(title),
        "summary": phrase(summary),
    }
    node_tokens = tokens(" ".join(haystacks.values()))

    score = 0
    reasons: list[str] = []

    if concept_phrase and concept_phrase in haystacks["id"]:
        score += 120
        reasons.append("concept phrase appears in id")
    if concept_phrase and haystacks["title"] and concept_phrase in haystacks["title"]:
        score += 120
        reasons.append("concept phrase appears in title")
    if concept_phrase and concept_phrase in haystacks["summary"]:
        score += 60
        reasons.append("concept phrase appears in summary")

    overlap = concept_tokens & node_tokens
    if overlap:
        score += 12 * len(overlap)
        reasons.append("token overlap: " + ", ".join(sorted(overlap)))

    if node.get("chapter") == "propositional-logic":
        score += 20
        reasons.append("same chapter")
    elif node.get("volume") == "i":
        score += 5
        reasons.append("same volume")

    if node.get("kind") == "Definition":
        score += 75
        reasons.append("definition preferred for concept label")

    id_text = node_id.replace(":", " ").replace("-", " ")
    id_without_prefix = re.sub(r"^(def|thm|lem|prop|cor|ax)\s+", "", id_text)
    id_tokens = tokens(id_text)
    exactish = concept_tokens & id_tokens
    if exactish:
        score += 8 * len(exactish)
        reasons.append("id token overlap: " + ", ".join(sorted(exactish)))

    if concept_phrase and phrase(id_without_prefix).startswith(concept_phrase):
        score += 45
        reasons.append("id begins with concept phrase after kind prefix")

    return score, reasons


def concepts_from_file(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for bucket_name in ("statement_dependency_concepts", "proof_dependency_concepts"):
        bucket_role = "statement" if bucket_name.startswith("statement") else "proof"
        for item in data.get(bucket_name, []):
            concept = item.get("concept")
            if not concept:
                continue
            out.append(
                {
                    "bucket": bucket_role,
                    "concept": concept,
                    "source_role": item.get("role") or bucket_role,
                    "confidence": item.get("confidence") or "",
                    "reason": item.get("reason") or "",
                }
            )
    return out


def match_concept(
    concept: str,
    candidates: list[dict[str, Any]],
    *,
    limit: int,
    min_score: int,
) -> list[dict[str, Any]]:
    scored = []
    for node in candidates:
        score, reasons = candidate_score(concept, node)
        if score < min_score:
            continue
        scored.append(
            {
                "id": node["id"],
                "kind": node["kind"],
                "title": node["title"],
                "volume": node["volume"],
                "chapter": node["chapter"],
                "section": node["section"],
                "score": score,
                "reasons": reasons,
                "summary": node["summary"],
            }
        )
    scored.sort(
        key=lambda item: (
            -item["score"],
            item["volume"] != "i",
            item["chapter"] != "propositional-logic",
            item["kind"] != "Definition",
            len(item["id"]),
            item["id"],
        )
    )
    return scored[:limit]


def output_name(concept_path: Path) -> str:
    name = concept_path.name
    if name.endswith(".concepts.json"):
        return name[: -len(".concepts.json")] + ".matches.json"
    return concept_path.stem + ".matches.json"


def build_matches(
    repo_root: Path,
    concepts_dir: Path,
    output_dir: Path,
    *,
    limit: int,
    min_score: int,
) -> dict[str, Any]:
    knowledge = load_json(repo_root / "knowledge.json")
    candidates = [compact_node(node) for node in knowledge.get("nodes", [])]
    candidates = [node for node in candidates if node["id"]]
    candidates.sort(key=lambda node: node["id"])

    concept_paths = sorted(concepts_dir.glob("*.concepts.json"))
    reports = []

    for concept_path in concept_paths:
        data = load_json(concept_path)
        node_id = data.get("node") or concept_path.stem
        concept_items = concepts_from_file(data)
        matches = []
        for item in concept_items:
            matches.append(
                {
                    **item,
                    "candidates": match_concept(
                        item["concept"],
                        candidates,
                        limit=limit,
                        min_score=min_score,
                    ),
                }
            )

        report = {
            "schema_version": SCHEMA_VERSION,
            "node": node_id,
            "source_concepts": str(concept_path.as_posix()),
            "matcher": {
                "method": "deterministic id/title/summary token scoring",
                "candidate_limit": limit,
                "min_score": min_score,
            },
            "matches": matches,
        }
        out_path = output_dir / output_name(concept_path)
        stable_write_json(out_path, report)
        reports.append(
            {
                "node": node_id,
                "concept_count": len(concept_items),
                "path": str(out_path.as_posix()),
            }
        )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "scope": "propositional-logic",
        "report_count": len(reports),
        "reports": reports,
    }
    stable_write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument(
        "--concepts",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
    )
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--min-score", type=int, default=20)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    concepts_dir = (
        args.concepts.resolve()
        if args.concepts
        else repo_root
        / "reorder"
        / "concept-pipeline"
        / "concepts"
        / "propositional-logic"
    )
    output_dir = (
        args.out.resolve()
        if args.out
        else repo_root
        / "reorder"
        / "concept-pipeline"
        / "matches"
        / "propositional-logic"
    )

    manifest = build_matches(
        repo_root,
        concepts_dir,
        output_dir,
        limit=args.limit,
        min_score=args.min_score,
    )
    print(
        json.dumps(
            {
                "scope": manifest["scope"],
                "report_count": manifest["report_count"],
                "manifest": str(output_dir / "manifest.json"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
