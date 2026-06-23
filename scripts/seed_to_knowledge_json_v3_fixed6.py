#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SCHEMA_VERSION = "0.4"
RECOGNIZED_EDGE_KINDS = {"depends_on", "equivalent_to", "implies", "prereq", "used_by"}

LABEL_RE = re.compile(r"\\label\{[^{}]+\}")
HYPERREF_LINE_RE = re.compile(r"^\s*\\hyperref\[[^\]]+\]\{.*?\}\s*$", re.MULTILINE | re.DOTALL)
BEGIN_ENV_RE = re.compile(r"\\begin\{([A-Za-z*]+)\}(?:\[[^\]]*\])?")
END_ENV_RE = re.compile(r"\\end\{([A-Za-z*]+)\}")
ITEM_RE = re.compile(r"\\item(?:\[[^\]]*\])?\s*")
HYPERREF_TARGET_RE = re.compile(r"\\hyperref\[([^\]]+)\]")
COMMAND_SPACES_RE = re.compile(r"\\(?:smallskip|medskip|bigskip|noindent|phantomsection|newpage|hfill)\b")
TITLE_BRACKET_RE = re.compile(r"^\s*\[[^\]]*\]\s*")
COMMENT_RE = re.compile(r"(?<!\\)%.*")
HTML_LIST_TAG_RE = re.compile(r"</?(?:ul|ol|li)\b[^>]*>", re.IGNORECASE)
MATH_DISPLAY_WRAP_RE = re.compile(r"^\s*\\\[(.*)\\\]\s*$", re.DOTALL)
INLINE_MATH_DOLLAR_WRAP_RE = re.compile(r"^\s*\$(.*)\$\s*$", re.DOTALL)
MULTISPACE_RE = re.compile(r"[ \t]+")
MULTIBLANK_RE = re.compile(r"\n{3,}")
HTML_LI_RE = re.compile(r"<li\b", re.IGNORECASE)
LATEX_LIST_ENV_RE = re.compile(r"\\begin\{(?:enumerate|itemize|description)\}", re.IGNORECASE)
LATEX_ITEM_RE = re.compile(r"\\item(?:\[[^\]]*\])?", re.IGNORECASE)
PREDICATE_HEAD_RE = re.compile(
    r"(?:\\operatorname\{([A-Z][A-Za-z0-9]*)\}|\\?([A-Z][A-Za-z0-9]*(?:Point|Set|Limit|Function|Relation|Predicate|Map|Sequence)))\s*\(",
)
OPERATOR_NAME_RE = re.compile(r"\\operatorname\{([A-Z][A-Za-z0-9]*)\}")
NODE_ID_RE = re.compile(r"\b(?:def|thm|lem|prop|cor|ax):[A-Za-z0-9_.:-]+\b")
DEFINITION_HEAD_RE = re.compile(
    r"(?:\\operatorname\{([A-Z][A-Za-z0-9]*)\}|\\?([A-Z][A-Za-z0-9]*))\s*\([^)]{0,240}\)\s*(?:\\colonequiv|\\coloniff|:=|:|\\iff|\\Leftrightarrow|\\Longleftrightarrow)",
    re.DOTALL,
)
IS_IFF_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*){0,3})\s+is\s+.{0,160}?\b(?:iff|if and only if)\b",
    re.IGNORECASE | re.DOTALL,
)
TITLE_MULTI_CONCEPT_RE = re.compile(r"\s*(?:;|/|\band\b|,)\s*", re.IGNORECASE)
STANDARD_FIELD_PREDICATE_RE = re.compile(
    r"(?:\\operatorname\{([A-Z][A-Za-z0-9]*)\}|(?<![A-Za-z\\])([A-Z][A-Za-z0-9]{2,})\s*\()"
)
SPACING_ARTIFACT_RE = re.compile(
    r"\b(?:"
    r"This(?:allows|shows|gives|implies|ensures|means|is|has|the|a|an|we)|"
    r"Since(?:the|this|there|it|we|f|S|A)|"
    r"Then(?:the|this|there|it|we|f|S|A)|"
    r"Therefore(?:the|this|it|we)|"
    r"Thus(?:the|this|it|we)|"
    r"fromthe|forthe|inthe|onthe|tothe|bythe|ofthe|andthe|withthe|"
    r"sothat|suchthat|thereexists|thereforethe"
    r")\b",
    re.IGNORECASE,
)


def resolve_output_dir(chapter_root: Path, output_dir: Path | None) -> Path:
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    out_dir = chapter_root / ".explorer"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


_PRIMITIVE_DEFINITIONS_CACHE: dict[str, frozenset[str]] = {}


def _find_root_policy(chapter_root: Path) -> Path | None:
    r"""Locate the dependency-root policy YAML by walking up from a chapter root.

    The governance audit reads ``<repo>/volume-*/docs/governance/
    dependency-root-policy.yaml``.  Pass 2 runs over the monorepo, so the same
    file lives at ``<monorepo>/volume-*/docs/governance/...``; we search the
    chapter's ancestors for ``docs/governance/dependency-root-policy.yaml`` and
    return the first hit.  Returns None when no policy is present (the common
    case while ``primitive_definitions`` is empty).
    """
    rel = Path("docs") / "governance" / "dependency-root-policy.yaml"
    for ancestor in [chapter_root, *chapter_root.parents]:
        candidate = ancestor / rel
        if candidate.exists():
            return candidate
    return None


def load_primitive_definitions(chapter_root: Path, policy_path: Path | None = None) -> frozenset[str]:
    r"""Return the set of policy-declared primitive-definition labels.

    Defensive by design, mirroring the audit's ``load_policy``: a missing file, a
    missing ``pyyaml`` dependency, or a malformed document all yield an empty set
    rather than failing the extraction run.  Cached per policy path so repeated
    chapter conversions don't re-read the file.
    """
    path = policy_path or _find_root_policy(chapter_root)
    if path is None or not path.exists():
        return frozenset()
    key = str(path.resolve())
    cached = _PRIMITIVE_DEFINITIONS_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        import yaml  # pyyaml is already a pipeline dependency (rebuild.yml)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        primitives = frozenset(str(x) for x in (data.get("primitive_definitions") or []))
    except Exception:
        primitives = frozenset()
    _PRIMITIVE_DEFINITIONS_CACHE[key] = primitives
    return primitives


FIELD_DEFAULTS: dict[str, Any] = {
    "id": "",
    "kind": "",
    "name": "",
    "deck": "",
    "chapter": "",          # top-level chapter slug (e.g. "peano-systems")
    "source": "",
    "proof_source": "",
    "question": "",
    "statement_display": "",
    "statement_tex": "",
    "hint": "",
    "proposition": "",
    "formal": "",
    "fully_quantified_form": "",
    "negation_display": "",
    "negation_formal": "",
    "negation_predicate": "",
    "failure_modes": "",
    "failure_mode_decomposition": "",
    "contrapositive": "",
    "depends_on_ids": [],
    "used_by_ids": [],
    "prereq_ids": [],
    "equivalent_to_ids": [],
    "implies_ids": [],
    "aliases": [],
    "tags": [],
    "symbol": "",
    "category": "",
    "proof_sketch": "",
    "proof_steps": [],
    "proof_sketch_source": "",
    "proof_idea": "",
    "proof_type": "",
    "method": "",
    "uses_text": "",
    "source_text": "",
    "section": "",
    "has_proof_file": False,
    "ignored": False,
    "is_theorem_like": True,
    # Root / terminal classification (mirrors the governance audit's allowed_root):
    # a node is a legitimate leaf of the dependency tree iff it is an axiom, a
    # \DefinitionalRoot-tagged primitive, or a policy-listed primitive definition.
    "definitional_root": False,
    "is_root": False,
    "root_kind": "",          # "axiom" | "definitional" | "primitive" | ""
    "depends_on_titles": [],
    "used_by_titles": [],
    "prereq_titles": [],
    "equivalent_to_titles": [],
    "implies_titles": [],
}


def decode_b64(s: str | None) -> str:
    if not s:
        return ""
    return base64.b64decode(s).decode("utf-8", errors="replace")


def humanize_slug(slug: str) -> str:
    if not slug:
        return ""
    return slug.replace("-", " ").replace("_", " ").title()


def humanize_label(label: str) -> str:
    tail = str(label or "").split(":", 1)[-1]
    return humanize_slug(tail)


def strip_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        lines.append(COMMENT_RE.sub("", line))
    return "\n".join(lines)


def cleanup_statement_tex(text: str) -> str:
    t = decode_b64(text) if not isinstance(text, str) else text
    t = strip_comments(t)
    t = TITLE_BRACKET_RE.sub("", t, count=1)
    t = LABEL_RE.sub("", t)
    t = HYPERREF_LINE_RE.sub("", t)
    t = HTML_LIST_TAG_RE.sub(" ", t)
    t = COMMAND_SPACES_RE.sub(" ", t)
    t = MULTISPACE_RE.sub(" ", t)
    t = MULTIBLANK_RE.sub("\n\n", t)
    return t.strip()


def extract_body_from_env(raw_env_tex: str) -> str:
    text = strip_comments(raw_env_tex).strip()
    m = BEGIN_ENV_RE.search(text)
    if not m:
        return text
    start = m.end()
    body = text[start:]
    end_matches = list(END_ENV_RE.finditer(body))
    if end_matches:
        body = body[: end_matches[-1].start()]
    return body.strip()


def clean_remark_content(raw_b64: str) -> str:
    raw = decode_b64(raw_b64)
    body = extract_body_from_env(raw)
    body = strip_comments(body)
    body = COMMAND_SPACES_RE.sub(" ", body)
    body = MULTIBLANK_RE.sub("\n\n", body)
    return body.strip()


def latex_to_basic_html(text: str) -> str:
    t = text.strip()
    def replace_list_env(src: str, env_name: str) -> str:
        pattern = re.compile(rf"\\begin\{{{env_name}\}}(.*?)\\end\{{{env_name}\}}", re.DOTALL)
        while True:
            m = pattern.search(src)
            if not m:
                break
            content = m.group(1)
            parts = [p.strip() for p in ITEM_RE.split(content) if p.strip()]
            repl = "\n".join(f"- {p}" for p in parts)
            src = src[: m.start()] + repl + src[m.end() :]
        return src
    t = replace_list_env(t, "enumerate")
    t = replace_list_env(t, "itemize")
    t = HYPERREF_LINE_RE.sub("", t)
    t = LABEL_RE.sub("", t)
    t = COMMAND_SPACES_RE.sub(" ", t)
    t = MULTIBLANK_RE.sub("\n\n", t)
    return t.strip()


def choose_shortest_nonempty(items: list[str]) -> str:
    cleaned = [i.strip() for i in items if i and i.strip()]
    if not cleaned:
        return ""
    return min(cleaned, key=len)


def strip_leading_proof_heading(text: str) -> str:
    t = text.strip()
    t = re.sub(r'^\\textbf\{[^{}]*?Proof\.?\}\.?(?:\\\\)?\s*', '', t, count=1)
    t = re.sub(r'^Detailed\s+Learning\s+Proof\.?\s*~?\\\\\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^Professional\s+Standard\s+Proof\.?\s*~?\\\\\s*', '', t, flags=re.IGNORECASE)
    return t.strip()


def extract_detailed_learning_steps(text: str) -> list[str]:
    body = strip_leading_proof_heading(text)
    pattern = re.compile(
        r'\\textbf\{Step\s+([0-9A-Za-z]+)\.\s*([^{}]*?)\}\s*(.*?)(?=(?:\\textbf\{Step\s+[0-9A-Za-z]+\.)|\Z)',
        re.DOTALL | re.IGNORECASE,
    )
    steps: list[str] = []
    for m in pattern.finditer(body):
        step_no = m.group(1).strip()
        step_title = m.group(2).strip()
        step_body = m.group(3).strip()
        step_text = " ".join(part for part in [step_title, step_body] if part)
        if step_text:
            steps.append(f"Step {step_no}. {step_text}")
    return steps


RELATIONSHIP_REMARK_KINDS = {
    "dependencies": "dependencies",
    "prerequisites": "dependencies",
    "uses": "dependencies",
    "consequences": "implies_ids",
    "implies": "implies_ids",
    "equivalent forms": "equivalent_to_ids",
    "equivalent to": "equivalent_to_ids",
    "equivalences": "equivalent_to_ids",
}


def extract_relationships_from_blocks(blocks: list[dict[str, Any]]) -> dict[str, list[str]]:
    relationships: dict[str, list[str]] = {
        "dependencies": [],
        "implies_ids": [],
        "equivalent_to_ids": [],
    }
    for blk in blocks:
        title = (blk.get("title") or "").strip().lower()
        field = RELATIONSHIP_REMARK_KINDS.get(title)
        if blk.get("env_name") == "remark*" and field:
            raw = clean_remark_content(blk.get("raw_latex_b64", ""))
            relationships[field].extend(HYPERREF_TARGET_RE.findall(raw))
    for field, ids in relationships.items():
        seen = set()
        out = []
        for x in ids:
            if x not in seen:
                seen.add(x)
                out.append(x)
        relationships[field] = out
    return relationships


def extract_dependencies_from_blocks(blocks: list[dict[str, Any]]) -> list[str]:
    return extract_relationships_from_blocks(blocks)["dependencies"]


def proof_blocks_are_todo_stub(blocks: list[dict[str, Any]]) -> bool:
    for blk in blocks:
        if blk.get("env_name") != "proof":
            continue
        raw = decode_b64(blk.get("raw_latex_b64", ""))
        body = strip_comments(extract_body_from_env(raw)).strip().lower()
        if "todo" in body:
            return True
    return False


def summarize_proof_blocks(blocks: list[dict[str, Any]], node_id: str, proof_source_path: str) -> tuple[str, list[str], str, str, str, str, dict[str, Any] | None]:
    if proof_blocks_are_todo_stub(blocks):
        return "", [], "todo_stub_skipped", "", "", "", None

    proof_texts: list[str] = []
    proof_structure = ""
    method = ""
    detailed_steps: list[str] = []
    found_detailed_learning_proof = False

    for blk in blocks:
        env = blk.get("env_name", "")
        title = (blk.get("title") or "").strip().lower()
        if env == "proof":
            raw = decode_b64(blk.get("raw_latex_b64", ""))
            body = extract_body_from_env(raw)
            body = strip_comments(body).strip()
            if body:
                proof_texts.append(body)
                if "detailed learning proof" in body.lower():
                    found_detailed_learning_proof = True
                    detailed_steps = extract_detailed_learning_steps(body)
        elif env == "remark*" and title == "proof structure":
            proof_structure = clean_remark_content(blk.get("raw_latex_b64", ""))
        elif env == "remark*" and title == "method":
            method = clean_remark_content(blk.get("raw_latex_b64", ""))

    if detailed_steps:
        proof_sketch = "\n".join(detailed_steps)
        proof_sketch_source = "detailed_learning_proof_steps"
    else:
        proof_sketch = choose_shortest_nonempty(proof_texts)
        proof_sketch_source = "proof_body_fallback" if proof_sketch else ""

    proof_type = ""
    if proof_texts:
        joined = "\n\n".join(proof_texts[:2]).lower()
        if "induct" in joined:
            proof_type = "induction"
        elif "contradiction" in joined:
            proof_type = "contradiction"
        elif "contrapositive" in joined:
            proof_type = "contrapositive"
        else:
            proof_type = "direct"

    error = None
    if proof_source_path and proof_texts and not found_detailed_learning_proof:
        error = {
            "type": "missing_detailed_learning_proof",
            "node_id": node_id,
            "proof_source": proof_source_path,
            "message": "Proof file has proof content but no Detailed Learning Proof block.",
        }

    return proof_sketch, detailed_steps, proof_sketch_source, proof_structure, proof_type, method, error


PREDICATE_LEAD_IN_RE = re.compile(
    r"^\s*\\\[\s*"
    r"(?:\\neg\s*)?"
    r"\\operatorname\{[A-Za-z][A-Za-z0-9]*\}\s*(?:\([^][]*?\))?\s*\.?\s*"
    r"\\\]\s*"
    r"(?:Equivalently,?\s*)",
    re.DOTALL,
)


def strip_predicate_lead_in(content: str) -> str:
    stripped = PREDICATE_LEAD_IN_RE.sub("", content, count=1).strip()
    return stripped or content


def classify_remark_fields(remark_blocks: list[dict[str, Any]]) -> dict[str, str]:
    out = {
        "formal": "",
        "fully_quantified_form": "",
        "negation_display": "",
        "negation_formal": "",
        "negation_predicate": "",
        "failure_modes": "",
        "failure_mode_decomposition": "",
        "contrapositive": "",
        "proposition": "",
        "source_text": "",
    }
    for blk in remark_blocks:
        title = (blk.get("title") or "").strip().lower()
        content = clean_remark_content(blk.get("raw_latex_b64", ""))
        if not content:
            continue
        if title == "standard quantified statement":
            content = strip_predicate_lead_in(content)
            out["fully_quantified_form"] = content
            if not out["formal"]:
                out["formal"] = content
        elif title in {"definition predicate reading", "predicate statement", "predicate reading", "definition predicate language"}:
            out["proposition"] = content
            if not out["formal"]:
                out["formal"] = content
        elif title == "negated quantified statement":
            content = strip_predicate_lead_in(content)
            out["negation_display"] = content
            out["negation_formal"] = content
        elif title == "negation predicate reading":
            out["negation_predicate"] = content
        elif title in {"failure mode", "failure modes"}:
            out["failure_modes"] = content
        elif title == "failure mode decomposition":
            out["failure_mode_decomposition"] = content
        elif title == "contrapositive quantified statement":
            out["contrapositive"] = content
        elif title == "interpretation":
            out["source_text"] = content
    return out


def strip_latex_for_structure(text: str) -> str:
    t = strip_comments(text)
    t = LABEL_RE.sub(" ", t)
    t = re.sub(r"\\(?:begin|end)\{[^{}]+\}", " ", t)
    t = re.sub(r"\\(?:textbf|textit|emph|operatorname|mathrm|mathsf)\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?", " ", t)
    t = t.replace("{", " ").replace("}", " ")
    return re.sub(r"\s+", " ", t).strip()


def short_excerpt(text: str, limit: int = 420) -> str:
    t = re.sub(r"\s+", " ", strip_comments(text)).strip()
    if len(t) <= limit:
        return t
    return t[: limit - 3].rstrip() + "..."


def unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def detect_multiple_primary_statements(
    statement_text: str,
    kind: str,
    title: str,
    raw_latex: str,
) -> list[str]:
    text = raw_latex or statement_text or ""
    display_text = statement_text or text
    plain = strip_latex_for_structure(display_text)
    kind_l = kind.lower()
    signals: list[str] = []

    latex_item_count = len(LATEX_ITEM_RE.findall(text))
    html_item_count = len(HTML_LI_RE.findall(display_text))
    if LATEX_LIST_ENV_RE.search(text) and latex_item_count >= 2:
        signals.append(f"latex_list_with_multiple_items:{latex_item_count}")
    if html_item_count >= 2:
        signals.append(f"html_list_with_multiple_items:{html_item_count}")

    definition_heads = unique_preserve_order(
        (a or b) for a, b in DEFINITION_HEAD_RE.findall(text)
    )
    if len(definition_heads) >= 2:
        signals.append("multiple_definition_heads:" + ", ".join(definition_heads[:5]))

    predicate_heads = unique_preserve_order(
        (a or b) for a, b in PREDICATE_HEAD_RE.findall(text)
    )
    point_heads = [x for x in predicate_heads if x.endswith("Point")]
    if len(point_heads) >= 2:
        signals.append("multiple_point_predicates:" + ", ".join(point_heads[:5]))

    iff_subjects = unique_preserve_order(IS_IFF_RE.findall(plain))
    if len(iff_subjects) >= 2:
        signals.append("multiple_is_iff_definition_clauses:" + ", ".join(iff_subjects[:5]))

    title_parts = [
        p.strip()
        for p in TITLE_MULTI_CONCEPT_RE.split(title or "")
        if p.strip() and len(p.strip()) > 2
    ]
    if kind_l.startswith("definition") and len(title_parts) >= 2:
        signals.append("definition_title_contains_multiple_concepts:" + ", ".join(title_parts[:5]))

    paragraph_definition_count = len(
        re.findall(r"\b[A-Z][A-Za-z0-9 ]{1,60}\s+(?:is|are)\s+.{0,120}?(?:\.|;)", plain)
    )
    if kind_l.startswith("definition") and paragraph_definition_count >= 2:
        signals.append(f"multiple_definition_sentences:{paragraph_definition_count}")

    return signals


def build_multiple_primary_statement_warning(node: dict[str, Any]) -> dict[str, Any] | None:
    signals = detect_multiple_primary_statements(
        node.get("statement_tex", ""),
        node.get("kind", ""),
        node.get("name", ""),
        decode_b64(node.get("raw_latex_b64", "")),
    )
    if not signals:
        return None
    warning: dict[str, Any] = {
        "type": "multiple_primary_statements_in_box",
        "kind": node.get("kind", ""),
        "node_id": node.get("id", ""),
        "title": node.get("name", ""),
        "source": node.get("source", ""),
        "message": (
            "Extracted theorem/definition box appears to contain more than one primary statement. "
            "Extraction was preserved, but the source should be split into separate boxes and re-extracted."
        ),
        "signals": signals,
        "excerpt": short_excerpt(node.get("statement_tex", "")),
    }
    if node.get("proof_source"):
        warning["proof_source"] = node["proof_source"]
    return warning


def build_missing_dependencies_warning(node: dict[str, Any]) -> dict[str, Any] | None:
    # Roots legitimately have no dependencies: axioms, \DefinitionalRoot primitives,
    # and policy-declared primitive definitions all bottom out a chain by design.
    # Suppress the false "missing Dependencies remark" warning for them.
    if node.get("is_root") or node.get("definitional_root") or node.get("kind") == "Axiom":
        return None
    headings = {
        (blk.get("title") or "").strip().lower()
        for blk in node.get("remark_blocks", [])
        if blk.get("env_name") == "remark*"
    }
    if "dependencies" in headings:
        return None
    warning: dict[str, Any] = {
        "type": "missing_dependencies_block",
        "kind": node.get("kind", ""),
        "node_id": node.get("id", ""),
        "title": node.get("name", ""),
        "source": node.get("source", ""),
        "message": (
            "Extracted theorem/definition item has no attached Dependencies remark. "
            "Extraction was preserved, but the source should include explicit dependency "
            "hyperrefs or 'No local dependencies.' for reliable graph generation."
        ),
        "signals": ["missing remark*:Dependencies"],
        "excerpt": short_excerpt(node.get("statement_tex", "")),
    }
    if node.get("proof_source"):
        warning["proof_source"] = node["proof_source"]
    return warning


def build_missing_environment_title_warning(seed_node: dict[str, Any], node: dict[str, Any]) -> dict[str, Any] | None:
    if (seed_node.get("title") or "").strip():
        return None
    warning: dict[str, Any] = {
        "type": "missing_environment_title",
        "kind": node.get("kind", ""),
        "node_id": node.get("id", ""),
        "title": node.get("name", ""),
        "source": node.get("source", ""),
        "message": (
            "Extracted theorem/definition-like environment has no explicit title. "
            "The converter used a humanized label fallback, but the source should add "
            "an environment title for stable extraction and readable graph labels."
        ),
        "signals": ["empty optional environment title"],
        "label": seed_node.get("label", ""),
        "fallback_title": node.get("name", ""),
        "excerpt": short_excerpt(node.get("statement_tex", "")),
    }
    if node.get("proof_source"):
        warning["proof_source"] = node["proof_source"]
    return warning


def find_standard_field_predicates(text: str) -> list[str]:
    names = []
    for op_name, bare_name in STANDARD_FIELD_PREDICATE_RE.findall(text or ""):
        name = op_name or bare_name
        if name and name not in {"Bigl", "Bigr", "Big"}:
            names.append(name)
    return unique_preserve_order(names)


def build_predicate_notation_warning(node: dict[str, Any]) -> dict[str, Any] | None:
    fields = [
        "statement_display",
        "formal",
        "fully_quantified_form",
        "negation_display",
        "negation_formal",
        "contrapositive",
    ]
    hits = []
    signals = []
    for field in fields:
        names = find_standard_field_predicates(node.get(field, ""))
        if names:
            hits.append({"field": field, "predicate_names": names})
            signals.append(f"{field}:" + ", ".join(names[:8]))
    if not hits:
        return None
    warning: dict[str, Any] = {
        "type": "predicate_notation_in_standard_field",
        "kind": node.get("kind", ""),
        "node_id": node.get("id", ""),
        "title": node.get("name", ""),
        "source": node.get("source", ""),
        "message": (
            "A standard statement/formal field appears to contain predicate notation. "
            "House style reserves canonical predicate names for predicate-reading blocks; "
            "standard quantified, negated, contrapositive, and statement fields should use standard mathematical notation."
        ),
        "signals": signals,
        "fields": hits,
        "excerpt": short_excerpt(
            node.get("formal")
            or node.get("fully_quantified_form")
            or node.get("statement_display")
            or node.get("negation_formal", "")
        ),
    }
    if node.get("proof_source"):
        warning["proof_source"] = node["proof_source"]
    return warning


def find_spacing_artifacts(text: str) -> list[str]:
    return unique_preserve_order(SPACING_ARTIFACT_RE.findall(text or ""))


def build_proof_spacing_artifact_warning(node: dict[str, Any]) -> dict[str, Any] | None:
    candidates: list[tuple[str, str]] = []
    if node.get("proof_sketch"):
        candidates.append(("proof_sketch", node["proof_sketch"]))
    if node.get("proof_idea"):
        candidates.append(("proof_idea", node["proof_idea"]))
    for i, step in enumerate(node.get("proof_steps", []) or [], start=1):
        candidates.append((f"proof_steps[{i}]", step))

    hits = []
    signals = []
    for field, text in candidates:
        artifacts = find_spacing_artifacts(text)
        if artifacts:
            hits.append({"field": field, "artifacts": artifacts})
            signals.append(f"{field}:" + ", ".join(artifacts[:8]))
    if not hits:
        return None
    warning: dict[str, Any] = {
        "type": "proof_text_spacing_artifact",
        "kind": node.get("kind", ""),
        "node_id": node.get("id", ""),
        "title": node.get("name", ""),
        "source": node.get("source", ""),
        "proof_source": node.get("proof_source", ""),
        "message": (
            "Extracted proof sketch text appears to contain fused-word spacing artifacts. "
            "Extraction was preserved, but the proof source or extraction cleanup should be reviewed."
        ),
        "signals": signals,
        "fields": hits,
        "excerpt": short_excerpt(node.get("proof_sketch") or "\n".join(node.get("proof_steps", []) or [])),
    }
    return warning


def build_node(seed_node: dict[str, Any], chapter_name: str, primitive_definitions: frozenset[str] = frozenset()) -> tuple[dict[str, Any], dict[str, Any] | None]:
    node = json.loads(json.dumps(FIELD_DEFAULTS))
    node["id"] = seed_node["id"]
    node["kind"] = seed_node.get("kind", "")
    node["name"] = seed_node.get("title") or humanize_label(seed_node.get("label") or seed_node["id"])
    node["deck"] = humanize_slug(seed_node.get("section_slug") or seed_node.get("note_dir") or chapter_name)
    node["chapter"] = chapter_name   # raw slug, e.g. "peano-systems" — used by the explorer chapter filter
    node["section"] = seed_node.get("section_slug") or ""
    node["source"] = seed_node.get("source_path") or ""
    node["proof_source"] = seed_node.get("proof_source_path") or ""
    node["question"] = f"State the {node['kind'].lower()}: {node['name']}."

    statement_tex = cleanup_statement_tex(decode_b64(seed_node.get("body_latex_b64", "")))
    node["statement_tex"] = statement_tex
    node["statement_display"] = latex_to_basic_html(statement_tex)
    node["has_proof_file"] = bool(seed_node.get("proof_source_path"))
    node["is_theorem_like"] = True

    # Root / terminal classification — mirror the governance audit's allowed_root:
    #   ax -> root ; \DefinitionalRoot -> root ; label/id in policy primitives -> root.
    definitional_root = bool(seed_node.get("definitional_root", False))
    label = seed_node.get("label") or ""
    is_axiom = node["kind"] == "Axiom"
    in_policy = (label in primitive_definitions) or (node["id"] in primitive_definitions)
    node["definitional_root"] = definitional_root
    if is_axiom:
        node["root_kind"] = "axiom"
    elif definitional_root:
        node["root_kind"] = "definitional"
    elif in_policy:
        node["root_kind"] = "primitive"
    else:
        node["root_kind"] = ""
    node["is_root"] = bool(is_axiom or definitional_root or in_policy)

    remark_fields = classify_remark_fields(seed_node.get("remark_blocks", []))
    node.update(remark_fields)
    note_relationships = extract_relationships_from_blocks(seed_node.get("remark_blocks", []))
    node["dependencies"] = note_relationships["dependencies"]
    node["implies_ids"] = note_relationships["implies_ids"]
    node["equivalent_to_ids"] = note_relationships["equivalent_to_ids"]

    proof_is_todo_stub = proof_blocks_are_todo_stub(seed_node.get("proof_file_blocks", []))
    proof_sketch, proof_steps, proof_sketch_source, proof_idea, proof_type, method, error = summarize_proof_blocks(
        seed_node.get("proof_file_blocks", []),
        node_id=node["id"],
        proof_source_path=node["proof_source"],
    )
    node["proof_sketch"] = proof_sketch
    node["proof_steps"] = proof_steps
    node["proof_sketch_source"] = proof_sketch_source
    node["proof_idea"] = proof_idea
    node["proof_type"] = proof_type
    node["method"] = method

    deps = [] if proof_is_todo_stub else extract_dependencies_from_blocks(seed_node.get("proof_file_blocks", []))
    node["uses_text"] = ", ".join(deps)

    node["raw_latex_b64"] = seed_node.get("raw_latex_b64", "")
    node["body_latex_b64"] = seed_node.get("body_latex_b64", "")
    node["title_latex_b64"] = seed_node.get("title_latex_b64", "")
    node["proof_raw_latex_b64"] = seed_node.get("proof_raw_latex_b64", "")
    node["remark_blocks"] = seed_node.get("remark_blocks", [])
    node["expositions"] = seed_node.get("expositions", [])
    node["proof_file_blocks"] = seed_node.get("proof_file_blocks", [])
    node["seed_labels"] = seed_node.get("labels", [])
    node["seed_proof_refs"] = seed_node.get("proof_refs", [])
    node["seed_theorem_refs"] = seed_node.get("theorem_refs", [])
    node["seed_proof_return_targets"] = seed_node.get("proof_return_targets", [])
    node["env_name"] = seed_node.get("env_name", "")
    node["text_preview"] = seed_node.get("text_preview", "")
    return node, error


def load_seed(seed_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    knowledge_seed_path = seed_dir / "knowledge-seed.json"
    edge_seed_path = seed_dir / "graph-edges-seed.json"
    missing = [str(p) for p in [knowledge_seed_path, edge_seed_path] if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing seed file(s): " + ", ".join(missing)
            + ". Run the first-pass extractor first, or point --output-dir to the folder containing the seed JSON files."
        )
    knowledge_seed = json.loads(knowledge_seed_path.read_text(encoding="utf-8"))
    edge_seed = json.loads(edge_seed_path.read_text(encoding="utf-8"))
    return knowledge_seed, edge_seed


def split_relationship_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        raw = re.split(r"[,;\s]+", value)
    else:
        raw = []
    out: list[str] = []
    for item in raw:
        text = str(item).strip().strip("`'\"")
        if not text:
            continue
        ids = NODE_ID_RE.findall(text)
        out.extend(ids or [text])
    return out


def normalize_edge_kind(kind: str) -> str:
    k = (kind or "").strip().lower()
    aliases = {
        "dependency": "depends_on",
        "dependencies": "depends_on",
        "uses": "depends_on",
        "used": "depends_on",
        "references": "depends_on",
        "reference": "depends_on",
        "consequence": "implies",
        "consequences": "implies",
        "equivalent": "equivalent_to",
        "equivalence": "equivalent_to",
    }
    return aliases.get(k, k)


def edge_warning(source_node: dict[str, Any] | None, missing_target: str, kind: str) -> dict[str, Any]:
    return {
        "type": "dangling_graph_edge_reference",
        "source_node_id": source_node.get("id", "") if source_node else "",
        "missing_target_id": missing_target,
        "relationship_kind": kind,
        "source": source_node.get("source", "") if source_node else "",
        "message": "Graph edge relationship target was not found among extracted node IDs; edge was skipped.",
    }


def words_to_pascal(words: list[str]) -> str:
    return "".join(w[:1].upper() + w[1:] for w in words if w)


def predicate_candidates_from_definition(node: dict[str, Any]) -> set[str]:
    text = "\n".join(
        str(node.get(field, ""))
        for field in ["statement_tex", "formal", "fully_quantified_form", "proposition", "source_text"]
    )
    candidates = set(OPERATOR_NAME_RE.findall(text))
    raw_id = re.sub(r"^(?:def|thm|lem|prop|cor|ax):", "", node.get("id", ""))
    id_words = [w for w in re.split(r"[^A-Za-z0-9]+", raw_id) if w and w not in {"R", "N"}]
    title_words = [w for w in re.split(r"[^A-Za-z0-9]+", strip_latex_for_structure(node.get("name", ""))) if w]
    for words in [id_words, title_words]:
        if len(words) >= 2:
            candidates.add(words_to_pascal(words))
            candidates.add(words_to_pascal(list(reversed(words))))
        elif words:
            candidates.add(words_to_pascal(words))
    return {c for c in candidates if len(c) > 2}


def operators_used_by_node(node: dict[str, Any]) -> set[str]:
    text = "\n".join(
        str(node.get(field, ""))
        for field in ["statement_tex", "formal", "fully_quantified_form", "proposition", "source_text", "proof_sketch"]
    )
    return set(OPERATOR_NAME_RE.findall(text))


def build_edges(nodes: list[dict[str, Any]], edge_seed: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    node_ids = {n["id"] for n in nodes}
    by_id = {n["id"]: n for n in nodes}
    edges: list[dict[str, str]] = []
    warnings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(frm: str, to: str, kind: str, source_node: dict[str, Any] | None = None, warn_missing: bool = True) -> None:
        kind = normalize_edge_kind(kind)
        if not frm or not to or frm == to:
            return
        if kind not in RECOGNIZED_EDGE_KINDS:
            return
        if frm not in node_ids or to not in node_ids:
            missing = frm if frm not in node_ids else to
            if warn_missing:
                warnings.append(edge_warning(source_node, missing, kind))
            return
        key = (frm, to, kind)
        if key in seen:
            return
        seen.add(key)
        edges.append({"from": frm, "to": to, "kind": kind})

    for n in nodes:
        for dep in split_relationship_ids(n.get("dependencies", [])):
            add(dep, n["id"], "depends_on", n)
        for dep in split_relationship_ids(n.get("depends_on_ids", [])):
            add(dep, n["id"], "depends_on", n)
        for dep in split_relationship_ids(n.get("prereq_ids", [])):
            add(dep, n["id"], "prereq", n)
        for dep in split_relationship_ids(n.get("uses_text", "")):
            add(dep, n["id"], "depends_on", n)
        for target in split_relationship_ids(n.get("used_by_ids", [])):
            add(n["id"], target, "used_by", n)
        for target in split_relationship_ids(n.get("implies_ids", [])):
            add(n["id"], target, "implies", n)
        for target in split_relationship_ids(n.get("equivalent_to_ids", [])):
            add(n["id"], target, "equivalent_to", n)
            add(target, n["id"], "equivalent_to", by_id.get(target), warn_missing=False)
        for ref in split_relationship_ids(n.get("seed_theorem_refs", [])):
            add(ref, n["id"], "depends_on", n)

    for e in edge_seed:
        kind = normalize_edge_kind(e.get("kind", ""))
        if kind in RECOGNIZED_EDGE_KINDS:
            frm = e.get("from", "")
            to = e.get("to", "")
            source_node = by_id.get(to) or by_id.get(frm)
            add(frm, to, kind, source_node)

    edges.sort(key=lambda e: (e["kind"], e["from"], e["to"]))
    unique_warnings: list[dict[str, Any]] = []
    warning_seen: set[tuple[str, str, str]] = set()
    for warning in warnings:
        key = (warning["source_node_id"], warning["missing_target_id"], warning["relationship_kind"])
        if key in warning_seen:
            continue
        warning_seen.add(key)
        unique_warnings.append(warning)
    return edges, unique_warnings


def attach_edge_lists(nodes: list[dict[str, Any]], edges: list[dict[str, str]]) -> None:
    by_id = {n["id"]: n for n in nodes}
    for e in edges:
        frm, to, kind = e["from"], e["to"], e["kind"]
        if kind == "depends_on":
            # Edge frm->to means "frm depends on to": frm's depends_on, to's used_by.
            by_id[frm]["depends_on_ids"].append(to)
            by_id[to]["used_by_ids"].append(frm)
        elif kind == "used_by":
            by_id[frm]["used_by_ids"].append(to)
            by_id[to]["depends_on_ids"].append(frm)
        elif kind == "prereq":
            by_id[to]["prereq_ids"].append(frm)
        elif kind == "equivalent_to":
            by_id[frm]["equivalent_to_ids"].append(to)
        elif kind == "implies":
            by_id[frm]["implies_ids"].append(to)

    def names(ids: list[str]) -> list[str]:
        return [by_id[x]["name"] for x in ids if x in by_id]

    for n in nodes:
        for field in ["depends_on_ids", "used_by_ids", "prereq_ids", "equivalent_to_ids", "implies_ids"]:
            seen = set()
            dedup = []
            for x in n[field]:
                if x not in seen:
                    seen.add(x)
                    dedup.append(x)
            n[field] = dedup
        n["depends_on_titles"] = names(n["depends_on_ids"])
        n["used_by_titles"] = names(n["used_by_ids"])
        n["prereq_titles"] = names(n["prereq_ids"])
        n["equivalent_to_titles"] = names(n["equivalent_to_ids"])
        n["implies_titles"] = names(n["implies_ids"])


def build_metadata(chapter_root: Path, chapter_name: str, nodes: list[dict[str, Any]], edges: list[dict[str, str]], errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "roots": [str(chapter_root)],
        "node_count": len(nodes),
        "edge_count": len(edges),
        "error_count": len(errors),
        "edge_kinds": sorted({e["kind"] for e in edges}) or sorted(RECOGNIZED_EDGE_KINDS),
        "card_count": 0,
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "script": "seed_to_knowledge_json_v3.py",
        "chapter": chapter_name,
    }


def convert_chapter(chapter_root: Path, output_dir: Path | None = None) -> tuple[Path, Path, Path, Path]:
    out_dir = resolve_output_dir(chapter_root, output_dir)
    seed_dir = out_dir if output_dir is not None else (chapter_root / ".explorer")
    knowledge_seed, edge_seed = load_seed(seed_dir)
    chapter_name = knowledge_seed.get("chapter") or chapter_root.name
    primitive_definitions = load_primitive_definitions(chapter_root)
    nodes: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for seed in knowledge_seed.get("nodes", []):
        node, error = build_node(seed, chapter_name, primitive_definitions)
        nodes.append(node)
        title_warning = build_missing_environment_title_warning(seed, node)
        if title_warning:
            errors.append(title_warning)
        structure_warning = build_multiple_primary_statement_warning(node)
        if structure_warning:
            errors.append(structure_warning)
        dependency_warning = build_missing_dependencies_warning(node)
        if dependency_warning:
            errors.append(dependency_warning)
        predicate_warning = build_predicate_notation_warning(node)
        if predicate_warning:
            errors.append(predicate_warning)
        proof_spacing_warning = build_proof_spacing_artifact_warning(node)
        if proof_spacing_warning:
            errors.append(proof_spacing_warning)
        if error:
            errors.append(error)
    edges, edge_warnings = build_edges(nodes, edge_seed)
    errors.extend(edge_warnings)
    attach_edge_lists(nodes, edges)
    payload = {
        "metadata": build_metadata(chapter_root, chapter_name, nodes, edges, errors),
        "nodes": nodes,
        "edges": edges,
    }
    out_dir = output_dir or (chapter_root / ".explorer")
    out_dir.mkdir(parents=True, exist_ok=True)
    knowledge_path = out_dir / "knowledge.json"
    graph_edges_path = out_dir / "graph-edges.json"
    errors_path = out_dir / "proof-errors.json"
    graph_edge_errors_path = out_dir / "graph-edge-errors.json"
    knowledge_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    graph_edges_path.write_text(json.dumps(edges, indent=2, ensure_ascii=False), encoding="utf-8")
    edge_errors_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chapter": chapter_name,
        "error_count": len(edge_warnings),
        "errors": edge_warnings,
    }
    graph_edge_errors_path.write_text(json.dumps(edge_errors_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    errors_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chapter": chapter_name,
        "error_count": len(errors),
        "errors": errors,
    }
    errors_path.write_text(json.dumps(errors_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return knowledge_path, graph_edges_path, errors_path, graph_edge_errors_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Second pass: convert LRA seed extraction into explorer-ready knowledge.json")
    parser.add_argument("chapter_root", type=Path, help="Path to a single chapter root containing .explorer/knowledge-seed.json")
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional output directory. Default: <chapter>/.explorer")
    args = parser.parse_args()
    knowledge_path, edges_path, errors_path, graph_edge_errors_path = convert_chapter(args.chapter_root.resolve(), args.output_dir.resolve() if args.output_dir else None)
    print(f"Wrote {knowledge_path}")
    print(f"Wrote {edges_path}")
    print(f"Wrote {errors_path}")
    print(f"Wrote {graph_edge_errors_path}")


if __name__ == "__main__":
    main()
