"""Bootstrap concept decompositions for propositional-logic packets.

This is a deterministic first pass for the whole chapter. It is intentionally
conservative: it extracts concepts from statement keywords and current direct
dependencies, while preserving hand-authored concept files by default.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "concept-decomposition-1"

THEOREM_KINDS = {"Theorem", "Lemma", "Proposition", "Corollary", "Axiom"}
FACT_KINDS = {"Theorem", "Lemma", "Proposition", "Corollary"}

KEYWORD_CONCEPTS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\\WFF|well-formed formula|formula", re.I), "well-formed formula", "The statement refers to propositional formulas."),
    (re.compile(r"propositional variable|\\Prop|variable", re.I), "propositional variable", "The statement refers to propositional variables."),
    (re.compile(r"logical connective|connective|\\neg|\\land|\\lor|\\to|\\leftrightarrow", re.I), "logical connective", "The statement uses propositional connectives or connective formation."),
    (re.compile(r"atomic", re.I), "atomic formula", "The statement distinguishes atomic formulas."),
    (re.compile(r"molecular", re.I), "molecular formula", "The statement distinguishes molecular formulas."),
    (re.compile(r"subformula|\\operatorname\{Sub\}", re.I), "subformula", "The statement refers to subformulas."),
    (re.compile(r"proper subformula", re.I), "proper subformula", "The statement refers to proper subformulas."),
    (re.compile(r"parse tree|syntax tree", re.I), "parse tree", "The statement refers to formula parse trees."),
    (re.compile(r"main connective", re.I), "main connective", "The statement refers to the main connective of a formula."),
    (re.compile(r"depth|\\operatorname\{depth\}", re.I), "formula depth", "The statement refers to formula depth."),
    (re.compile(r"connective count|\\operatorname\{conn\}", re.I), "connective count", "The statement refers to connective count."),
    (re.compile(r"\\operatorname\{Var\}|variable set", re.I), "formula variable set", "The statement refers to the variable set of a formula."),
    (re.compile(r"truth assignment|valuation|\\widehat v|\\models", re.I), "truth assignment", "The statement uses truth assignments or semantic evaluation."),
    (re.compile(r"satisfies|satisfaction|satisfiable|unsatisfiable|\\models", re.I), "satisfaction", "The statement uses semantic satisfaction."),
    (re.compile(r"tautology", re.I), "tautology", "The statement refers to tautologies."),
    (re.compile(r"contradiction", re.I), "contradiction", "The statement refers to contradictions."),
    (re.compile(r"contingency", re.I), "contingency", "The statement refers to contingencies."),
    (re.compile(r"logical consequence|consequence", re.I), "logical consequence", "The statement refers to logical consequence."),
    (re.compile(r"logically equivalent|logical equivalence|\\equiv", re.I), "logical equivalence", "The statement refers to logical equivalence."),
    (re.compile(r"truth table", re.I), "truth table", "The statement refers to truth tables."),
    (re.compile(r"Boolean function|\\mathbb\{B\}\^n", re.I), "Boolean function", "The statement refers to Boolean functions."),
    (re.compile(r"connective basis|basis", re.I), "connective basis", "The statement refers to a connective basis."),
    (re.compile(r"functionally complete|functional completeness", re.I), "functional completeness", "The statement refers to functional completeness."),
    (re.compile(r"NAND|\\uparrow", re.I), "NAND connective", "The statement refers to NAND."),
    (re.compile(r"NOR|\\downarrow", re.I), "NOR connective", "The statement refers to NOR."),
    (re.compile(r"literal", re.I), "literal", "The statement refers to literals."),
    (re.compile(r"clause", re.I), "clause", "The statement refers to clauses."),
    (re.compile(r"term|conjunction term", re.I), "term", "The statement refers to conjunction terms."),
    (re.compile(r"conjunctive normal form|CNF", re.I), "conjunctive normal form", "The statement refers to CNF."),
    (re.compile(r"disjunctive normal form|DNF", re.I), "disjunctive normal form", "The statement refers to DNF."),
    (re.compile(r"negation normal form|NNF", re.I), "negation normal form", "The statement refers to NNF."),
    (re.compile(r"argument form|premise|conclusion", re.I), "argument form", "The statement refers to argument forms."),
    (re.compile(r"counterexample assignment", re.I), "counterexample assignment", "The statement refers to counterexample assignments."),
    (re.compile(r"rule of replacement", re.I), "rule of replacement", "The statement refers to replacement rules."),
    (re.compile(r"finite subset", re.I), "finite subset", "The statement refers to finite subsets."),
    (re.compile(r"finitely satisfiable", re.I), "finite satisfiability", "The statement refers to finite satisfiability."),
    (re.compile(r"finite unsatisfiability witness", re.I), "finite unsatisfiability witness", "The statement refers to finite unsatisfiability witnesses."),
    (re.compile(r"set of formulas|\\Gamma", re.I), "set of formulas", "The statement refers to a set of formulas."),
    (re.compile(r"recursively|recursive", re.I), "recursive definition on formula structure", "The statement is recursive over formula structure."),
]

SECTION_AMBIENT = {
    "syntax": ["propositional logic syntax", "propositional language"],
    "semantics": ["propositional logic semantics", "classical propositional L-structure"],
    "axioms": ["propositional proof system", "propositional formulas"],
    "algebra": ["propositional equivalence algebra", "formula contexts"],
    "normal-forms": ["propositional formula syntax", "normal-form transformations"],
    "functional-completeness": ["truth-functional semantics", "connective bases"],
    "argument-forms": ["propositional validity", "argument forms"],
    "compactness-preview": ["sets of propositional formulas", "satisfiability semantics"],
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


def output_name(packet_path: Path) -> str:
    return packet_path.name.removesuffix(".json") + ".concepts.json"


def concept_from_label(label: str) -> str:
    cleaned = re.sub(r"^(def|thm|lem|prop|cor|ax):", "", label)
    cleaned = cleaned.replace("-propositional-logic", "")
    cleaned = cleaned.replace("-propositional-formulas", "")
    cleaned = cleaned.replace("-", " ")
    return cleaned


def node_index(knowledge: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node.get("id"): node for node in knowledge.get("nodes", []) if node.get("id")}


def add_unique_concept(
    concepts: list[dict[str, str]],
    seen: set[str],
    concept: str,
    reason: str,
    *,
    confidence: str = "medium",
    role: str = "statement",
) -> None:
    key = concept.lower()
    if key in seen:
        return
    seen.add(key)
    concepts.append(
        {
            "concept": concept,
            "confidence": confidence,
            "reason": reason,
            "role": role,
        }
    )


def build_decomposition(packet: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    node = packet["node"]
    node_id = node["id"]
    kind = node.get("kind", "")
    section = node.get("section", "")
    statement = node.get("statement_display") or node.get("statement_tex") or ""

    statement_concepts: list[dict[str, str]] = []
    proof_concepts: list[dict[str, str]] = []
    seen_statement: set[str] = set()
    seen_proof: set[str] = set()

    for pattern, concept, reason in KEYWORD_CONCEPTS:
        if pattern.search(statement):
            add_unique_concept(statement_concepts, seen_statement, concept, reason)

    for dep in packet.get("current_direct_dependencies", []):
        dep_id = dep.get("id", "")
        dep_node = nodes.get(dep_id, {})
        dep_kind = dep_node.get("kind", "")
        concept = concept_from_label(dep_id)
        if not concept:
            continue
        if kind in THEOREM_KINDS and dep_kind in FACT_KINDS:
            add_unique_concept(
                proof_concepts,
                seen_proof,
                concept,
                "Existing direct fact dependency is likely proof support for a theorem-like node.",
                confidence="medium",
                role="proof_fact",
            )
        elif kind in THEOREM_KINDS and dep_kind == "Axiom":
            add_unique_concept(
                proof_concepts,
                seen_proof,
                concept,
                "Existing direct axiom dependency is likely proof support for a theorem-like node.",
                confidence="medium",
                role="proof_axiom",
            )
        else:
            add_unique_concept(
                statement_concepts,
                seen_statement,
                concept,
                "Current direct dependency names a concept likely relevant to the statement.",
                confidence="medium",
            )

    if not statement_concepts:
        add_unique_concept(
            statement_concepts,
            seen_statement,
            "propositional formula",
            "Fallback concept for a propositional-logic node with no keyword match.",
            confidence="low",
        )

    not_dependencies = []
    if section == "syntax":
        not_dependencies.extend(
            [
                {
                    "concept": "truth assignment",
                    "reason": "This syntax-section node can usually be stated without semantic valuation.",
                },
                {
                    "concept": "satisfaction",
                    "reason": "This syntax-section node can usually be stated without the satisfaction relation.",
                },
            ]
        )

    floor_mentions = []
    if "propositional language" in " ".join(SECTION_AMBIENT.get(section, [])).lower() or "Prop" in statement:
        floor_mentions.append(
            {
                "concept": "propositional language",
                "emit_dependency": False,
                "reason": "Propositional language is an accepted definitional root and ambient context.",
                "source": "definitional_root",
            }
        )
    if "truth" in statement.lower() or section == "semantics":
        floor_mentions.append(
            {
                "concept": "classical propositional L-structure",
                "emit_dependency": False,
                "reason": "The virtual structure supplies semantic context but is not a graph node.",
                "source": "virtual_structure",
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "node": node_id,
        "ambient_environment": SECTION_AMBIENT.get(section, ["propositional logic"]),
        "mathematical_structures": [item["concept"] for item in statement_concepts[:8]],
        "instances": [],
        "operations_relations_predicates": [],
        "statement_conditions": [],
        "statement_assertions": [statement.strip()] if statement.strip() else [],
        "statement_dependency_concepts": statement_concepts,
        "proof_dependency_concepts": proof_concepts,
        "not_dependencies": not_dependencies,
        "floor_mentions": floor_mentions,
        "questions": [],
        "generator": {
            "method": "deterministic bootstrap from statement keywords and current direct dependencies",
            "preserves_existing_by_default": True,
        },
    }


def build_all(repo_root: Path, out_dir: Path, preserve_existing: bool) -> dict[str, Any]:
    manifest = load_json(
        repo_root
        / "reorder"
        / "concept-pipeline"
        / "invocations"
        / "propositional-logic"
        / "manifest.json"
    )
    knowledge = load_json(repo_root / "knowledge.json")
    nodes = node_index(knowledge)

    written = []
    skipped = []
    for entry in manifest["packets"]:
        packet_path = repo_root / "reorder" / "concept-pipeline" / entry["path"]
        packet = load_json(packet_path)
        out_path = out_dir / output_name(packet_path)
        if preserve_existing and out_path.exists():
            skipped.append({"node": entry["node"], "path": str(out_path.as_posix())})
            continue
        decomposition = build_decomposition(packet, nodes)
        stable_write_json(out_path, decomposition)
        written.append({"node": entry["node"], "path": str(out_path.as_posix())})

    result = {
        "schema_version": "concept-bootstrap-manifest-1",
        "scope": "propositional-logic",
        "written_count": len(written),
        "skipped_existing_count": len(skipped),
        "written": written,
        "skipped_existing": skipped,
    }
    stable_write_json(out_dir / "bootstrap-manifest.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    out_dir = (
        args.out.resolve()
        if args.out
        else repo_root / "reorder" / "concept-pipeline" / "concepts" / "propositional-logic"
    )
    result = build_all(repo_root, out_dir, preserve_existing=not args.overwrite)
    print(
        json.dumps(
            {
                "scope": result["scope"],
                "written_count": result["written_count"],
                "skipped_existing_count": result["skipped_existing_count"],
                "manifest": str(out_dir / "bootstrap-manifest.json"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
