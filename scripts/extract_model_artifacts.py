#!/usr/bin/env python3
"""Extract machine-readable model/theory/bridge cards from LRA TeX sources."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


MODELBOX_RE = re.compile(r"\\begin\{modelbox\}\{")
ID_RE = re.compile(r"\\modelid\{([^{}]+)\}")
KIND_RE = re.compile(r"\\modelkind\{([^{}]+)\}")
LAYER_RE = re.compile(r"\\modellayer\{([^{}]+)\}")
DEPENDS_RE = re.compile(r"\\modeldepends\{([\s\S]*?)\}", re.MULTILINE)
COMMENT_ID_RE = re.compile(r"%\s*BEGIN MODEL ARTIFACT:\s*([A-Za-z0-9:_\-.]+)")
LABEL_RE = re.compile(r"\\label\{([^{}]+)\}")
COMPONENT_START_RE = re.compile(r"\\begin\{(modelcomponent|modelsorts|modelconstants|modelarity|modelfunctions|modelrelations|modelsemantics|modelbridge|modelaxioms|modelconsequences)\}")

SEMANTIC_COMMANDS = {
    "modelparameter": ("Parameter", "parameter"),
    "modellanguage": ("Language", "language"),
    "modelpresentation": ("Presented Theory", "presentation"),
    "modelstructure": ("Structure", "structure"),
    "modelinterpretation": ("Interpretation", "interpretation"),
    "modelbinding": ("Binding", "binding"),
    "modelbinds": ("Binds", "binding"),
    "modelsemanticbridge": ("Syntax--Semantics Bridge", "bridge"),
    "modeldelta": ("Layer Delta", "delta"),
    "modelinstances": ("Instances", "instances"),
    "modeladmissibility": ("Admissibility", "admissibility"),
    "modelboundary": ("Boundary", "boundary"),
    "modelnote": ("Note", "note"),
    "modeltheorem": ("Theorem", "theorem"),
    "modeltheorymodels": ("Models of the Theory", "theory_models"),
    "modelinherits": ("Inherits", "inherits"),
}

SEMANTIC_ENVIRONMENTS = {
    f"{command}block": value for command, value in SEMANTIC_COMMANDS.items()
}
SEMANTIC_ENVIRONMENTS["modelaxiomsblock"] = ("Axioms and Laws", "axioms")

COMPONENT_ENV_NAMES = [
    "modelcomponent",
    "modelsorts",
    "modelconstants",
    "modelarity",
    "modelfunctions",
    "modelrelations",
    "modelsemantics",
    "modelbridge",
    "modelaxioms",
    "modelconsequences",
    *SEMANTIC_ENVIRONMENTS.keys(),
]
COMPONENT_START_RE = re.compile(r"\\begin\{(" + "|".join(re.escape(name) for name in COMPONENT_ENV_NAMES) + r")\}")
SIMPLE_COMMAND_RE = re.compile(r"\\(?:newcommand|providecommand)\s*\{(\\[A-Za-z@]+)\}")
DECLARE_MATH_OPERATOR_RE = re.compile(r"\\DeclareMathOperator\*?\s*\{(\\[A-Za-z@]+)\}\s*\{([^{}]+)\}")


COMPONENT_NAMES = {
    "modelsorts": "Sorts and Domains",
    "modelconstants": "Constants",
    "modelarity": "Arities",
    "modelfunctions": "Functions",
    "modelrelations": "Relations",
    "modelsemantics": "Semantic Clauses",
    "modelbridge": "Syntax--Semantics Bridge",
    "modelaxioms": "Axioms and Laws",
    "modelconsequences": "Theorems and Consequences",
}
COMPONENT_NAMES.update({env: title for env, (title, _field) in SEMANTIC_ENVIRONMENTS.items()})

ITEM_COMMAND_ARITY = {
    "modelsort": 3,
    "modelconstant": 2,
    "arity": 2,
    "modelfunction": 3,
    "modelrelation": 3,
    "modelclause": 1,
    "bridgeclause": 1,
    "modelaxiom": 1,
    "modelconsequence": 1,
    "inheritfrom": 2,
}


KNOWN_TITLE_TO_ID = {
    "Consequence": "bridge:consequence",
    "Free \\(\\Sigma\\)-Algebra and Evaluation": "bridge:free-sigma-algebra-evaluation",
    "Theory (Propositional Logic)": "theory:propositional-logic",
    "Model (Classical Propositional Logic)": "model:classical-propositional-logic",
    "Definitional Extension (Propositional Logic)": "defext:propositional-logic",
    "Theory (First-Order Logic)": "theory:first-order-logic",
    "Model (First-Order Logic)": "model:first-order-logic",
    "Definitional Extension (First-Order Logic)": "defext:first-order-logic",
    "Theory (ZF, ZFC)": "theory:set-theory",
    "Model (Set Theory)": "model:set-theory",
    "Definitional Extension (Set Theory)": "defext:set-theory",
}


KNOWN_DEPENDENCY_NAMES = {
    "Consequence": "bridge:consequence",
    "Free \\(\\Sigma\\)-Algebra and Evaluation": "bridge:free-sigma-algebra-evaluation",
    "Free \\(\\Sigma\\)-Algebra and Evaluation": "bridge:free-sigma-algebra-evaluation",
    "Free Σ-Algebra and Evaluation": "bridge:free-sigma-algebra-evaluation",
    "Theory (First-Order Logic)": "theory:first-order-logic",
    "Model (First-Order Logic)": "model:first-order-logic",
    "Definitional Extension (First-Order Logic)": "defext:first-order-logic",
    "Theory (ZF, ZFC)": "theory:set-theory",
    "Model (Set Theory)": "model:set-theory",
    "CPL": "theory:propositional-logic",
}


@dataclass
class ExtractionError:
    path: str
    message: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def find_matching_brace(text: str, open_brace: int) -> int:
    depth = 0
    escaped = False
    for i in range(open_brace, len(text)):
        ch = text[i]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unmatched brace")


def find_environment_end(text: str, env: str, body_start: int) -> int:
    begin_pat = re.compile(rf"\\begin\{{{re.escape(env)}\}}")
    end_pat = re.compile(rf"\\end\{{{re.escape(env)}\}}")
    depth = 1
    pos = body_start
    while True:
        b = begin_pat.search(text, pos)
        e = end_pat.search(text, pos)
        if not e:
            raise ValueError(f"missing \\end{{{env}}}")
        if b and b.start() < e.start():
            depth += 1
            pos = b.end()
            continue
        depth -= 1
        if depth == 0:
            return e.start()
        pos = e.end()


def extract_modelboxes(text: str) -> list[tuple[str, str, int, int]]:
    boxes: list[tuple[str, str, int, int]] = []
    for match in MODELBOX_RE.finditer(text):
        title_open = match.end() - 1
        title_close = find_matching_brace(text, title_open)
        title = text[title_open + 1:title_close].strip()
        body_start = title_close + 1
        body_end = find_environment_end(text, "modelbox", body_start)
        boxes.append((title, text[body_start:body_end], match.start(), body_end))
    return boxes


def macro_value(regex: re.Pattern[str], body: str) -> str:
    m = regex.search(body)
    return m.group(1).strip() if m else ""


def clean_tex(s: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", s.strip())


def command_arguments(text: str, command: str, arity: int) -> list[list[str]]:
    out: list[list[str]] = []
    pattern = re.compile(rf"\\{re.escape(command)}\s*")
    for match in pattern.finditer(text):
        pos = match.end()
        args: list[str] = []
        ok = True
        for _ in range(arity):
            while pos < len(text) and text[pos].isspace():
                pos += 1
            if pos >= len(text) or text[pos] != "{":
                ok = False
                break
            end = find_matching_brace(text, pos)
            args.append(clean_tex(text[pos + 1:end]))
            pos = end + 1
        if ok:
            out.append(args)
    return out


def normalize_katex_macro_expansion(expansion: str) -> str:
    expansion = clean_tex(expansion)
    replacements = {
        r"\vcentcolon\equiv": r"\equiv",
        r"\;\vcentcolon\iff\;": r"\Longleftrightarrow",
    }
    for source, target in replacements.items():
        expansion = expansion.replace(source, target)
    return expansion


def katex_macro_skip_reason(expansion: str) -> str:
    unsupported_tokens = [
        r"\par",
        r"\noindent",
        r"\ignorespaces",
        r"\textbf",
        r"\textit",
        r"\texttt",
        r"\href",
        r"\hyperref",
        r"\cite",
        r"\citeauthor",
        r"\mbox",
        r"\begin",
        r"\end",
        r"\directlua",
        "$",
    ]
    for token in unsupported_tokens:
        if token in expansion:
            return f"contains non-KaTeX frontend token {token}"
    return ""


def extract_katex_macros(path: Path | None) -> dict:
    if not path or not path.exists():
        return {"source_file": "", "macros": {}, "skipped": []}

    text = read_text(path)
    macros: dict[str, str] = {}
    skipped: list[dict[str, str]] = []
    command_names = {"newcommand", "providecommand", "renewcommand"}

    for match in DECLARE_MATH_OPERATOR_RE.finditer(text):
        name, operator = match.groups()
        macros[name] = rf"\operatorname{{{operator}}}"

    for match in SIMPLE_COMMAND_RE.finditer(text):
        command_start = match.start()
        if text[max(0, command_start - 1):command_start] == "%":
            continue
        name = match.group(1)
        pos = match.end()
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos < len(text) and text[pos] == "[":
            skipped.append({"name": name, "reason": "takes arguments or optional arguments"})
            continue
        if pos >= len(text) or text[pos] != "{":
            skipped.append({"name": name, "reason": "missing simple replacement body"})
            continue
        try:
            end = find_matching_brace(text, pos)
        except ValueError:
            skipped.append({"name": name, "reason": "unmatched replacement body"})
            continue
        expansion = normalize_katex_macro_expansion(text[pos + 1:end])
        if any(rf"\{command_name}" in expansion for command_name in command_names):
            skipped.append({"name": name, "reason": "replacement contains macro declaration"})
            continue
        reason = katex_macro_skip_reason(expansion)
        if reason:
            skipped.append({"name": name, "reason": reason})
            continue
        macros[name] = expansion

    return {
        "source_file": path.as_posix(),
        "macros": dict(sorted(macros.items())),
        "skipped": sorted(skipped, key=lambda item: item["name"]),
    }


def default_macro_file(source_root: Path) -> Path | None:
    candidates = [
        source_root.parent / "lra-common" / "common" / "macros.tex",
        Path(__file__).resolve().parents[2] / "lra-common" / "common" / "macros.tex",
        source_root / "common" / "macros.tex",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def extract_items(text: str) -> list[dict]:
    items: list[dict] = []
    for command, arity in ITEM_COMMAND_ARITY.items():
        for args in command_arguments(text, command, arity):
            item = {"command": command, "args": args}
            if command in {"modelsort", "modelrelation", "modelfunction"}:
                item.update({"symbol": args[0], "type": args[1], "description": args[2]})
            elif command == "modelconstant":
                item.update({"symbol": args[0], "description": args[1]})
            elif command == "arity":
                item.update({"symbol": args[0], "arity": args[1]})
            elif command == "inheritfrom":
                item.update({"source": args[0], "items": args[1]})
            else:
                item.update({"tex": args[0]})
            items.append(item)
    return items


def normalize_dependency(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"\\\((.*?)\\\)", r"\1", raw)
    raw = raw.replace(r"\Sigma", "Σ")
    raw = raw.replace(r"\mathrm{Cn}_{\vdash}", "Cn_vdash")
    return raw.strip()


def split_dependencies(raw: str) -> list[dict[str, str]]:
    deps = []
    for part in re.split(r";|,", raw):
        label = normalize_dependency(part)
        if not label:
            continue
        deps.append({"label": label, "id": KNOWN_DEPENDENCY_NAMES.get(label, label if ":" in label else "")})
    return deps


def extract_components(body: str) -> list[dict[str, str]]:
    components: list[dict] = []
    semantic_spans: list[tuple[int, int, dict]] = []
    for command, (title, field) in SEMANTIC_COMMANDS.items():
        for match in re.finditer(rf"\\{re.escape(command)}\s*", body):
            pos = match.end()
            while pos < len(body) and body[pos].isspace():
                pos += 1
            if pos >= len(body) or body[pos] != "{":
                continue
            end = find_matching_brace(body, pos)
            component_tex = clean_tex(body[pos + 1:end])
            semantic_spans.append((
                match.start(),
                end + 1,
                {
                    "name": title,
                    "env": command,
                    "field": field,
                    "tex": component_tex,
                    "items": extract_items(component_tex),
                    "semantic": True,
                },
            ))
    pos = 0
    occupied = [(start, end) for start, end, _ in semantic_spans]
    while True:
        m = COMPONENT_START_RE.search(body, pos)
        if not m:
            break
        if any(start <= m.start() < end for start, end in occupied):
            pos = m.end()
            continue
        env = m.group(1)
        title = COMPONENT_NAMES.get(env, env)
        content_start = m.end()
        if env == "modelcomponent":
            if content_start >= len(body) or body[content_start] != "{":
                pos = content_start
                continue
            title_end = find_matching_brace(body, content_start)
            title = body[content_start + 1:title_end].strip()
            content_start = title_end + 1
        content_end = find_environment_end(body, env, content_start)
        component_tex = clean_tex(body[content_start:content_end])
        semantic_env = SEMANTIC_ENVIRONMENTS.get(env)
        components.append({
            "name": semantic_env[0] if semantic_env else title,
            "env": env,
            "field": semantic_env[1] if semantic_env else title.lower().replace("--", "-").replace(" ", "_"),
            "tex": component_tex,
            "items": extract_items(component_tex),
            "semantic": bool(semantic_env),
        })
        pos = content_end + len(f"\\end{{{env}}}")
    components.extend(component for _, _, component in semantic_spans)
    return sorted(components, key=lambda component: body.find(component["tex"]) if component["tex"] else 0)


def normalized_fields(components: list[dict]) -> dict[str, list[dict]]:
    fields: dict[str, list[dict]] = {}
    for component in components:
        field = component.get("field") or "component"
        fields.setdefault(field, []).append({
            "name": component.get("name", ""),
            "tex": component.get("tex", ""),
            "items": component.get("items", []),
        })
    return fields


def infer_kind(model_id: str, title: str) -> str:
    if model_id.startswith("bridge:"):
        return "bridge"
    if model_id.startswith("theory:"):
        return "theory"
    if model_id.startswith("model:"):
        return "model"
    if model_id.startswith("defext:"):
        return "definitional-extension"
    lower = title.lower()
    if "theory" in lower:
        return "theory"
    if "definitional extension" in lower:
        return "definitional-extension"
    if "model" in lower:
        return "model"
    return "bridge"


def infer_layer(path: Path, model_id: str) -> str:
    parts = [p.lower() for p in path.parts]
    for layer in ("propositional-logic", "predicate-logic", "set-theory", "axiom-systems"):
        if layer in parts:
            return "first-order-logic" if layer == "predicate-logic" else ("shared" if layer == "axiom-systems" else layer)
    if ":" in model_id:
        return model_id.split(":", 1)[1]
    return ""


def extract_file(path: Path, root: Path, errors: list[ExtractionError]) -> list[dict]:
    text = read_text(path)
    rel = path.relative_to(root).as_posix()
    artifacts = []
    for title, body, start, _end in extract_modelboxes(text):
        before = text[max(0, start - 160):start]
        model_id = macro_value(ID_RE, body)
        if not model_id:
            cm = COMMENT_ID_RE.search(before)
            model_id = cm.group(1) if cm else KNOWN_TITLE_TO_ID.get(title, "")
        if not model_id:
            errors.append(ExtractionError(rel, f"modelbox '{title}' has no \\modelid"))
            continue
        depends_raw = macro_value(DEPENDS_RE, body)
        labels = LABEL_RE.findall(body)
        components = extract_components(body)
        artifact = {
            "id": model_id,
            "title": title,
            "kind": macro_value(KIND_RE, body) or infer_kind(model_id, title),
            "layer": macro_value(LAYER_RE, body) or infer_layer(path, model_id),
            "source_file": rel,
            "labels": labels,
            "depends_on": split_dependencies(depends_raw),
            "components": components,
            "fields": normalized_fields(components),
            "tex": clean_tex(body),
        }
        artifacts.append(artifact)
    return artifacts


def validate(artifacts: list[dict], errors: list[ExtractionError], forbid_generic_components: bool = False) -> None:
    ids: dict[str, str] = {}
    for artifact in artifacts:
        aid = artifact["id"]
        if aid in ids:
            errors.append(ExtractionError(artifact["source_file"], f"duplicate model artifact id '{aid}' first seen in {ids[aid]}"))
        ids[aid] = artifact["source_file"]
        if not artifact.get("kind"):
            errors.append(ExtractionError(artifact["source_file"], f"{aid} missing kind"))
        if not artifact.get("layer"):
            errors.append(ExtractionError(artifact["source_file"], f"{aid} missing layer"))
        if forbid_generic_components:
            for component in artifact.get("components", []):
                if component.get("env") == "modelcomponent" and not component.get("semantic"):
                    errors.append(ExtractionError(
                        artifact["source_file"],
                        f"{aid} uses generic modelcomponent '{component.get('name', '')}' instead of a semantic wrapper",
                    ))
    known = set(ids)
    for artifact in artifacts:
        for dep in artifact.get("depends_on", []):
            did = dep.get("id", "")
            if did and ":" in did and did not in known:
                errors.append(ExtractionError(artifact["source_file"], f"{artifact['id']} depends on unknown model artifact '{did}'"))


def model_artifact_rank(artifact: dict) -> tuple:
    layer_rank = {
        "shared": 0,
        "propositional-logic": 1,
        "first-order-logic": 2,
        "set-theory": 3,
    }
    kind_rank = {
        "bridge": 0,
        "theory": 1,
        "model": 2,
        "definitional-extension": 3,
    }
    id_rank = {
        "bridge:free-sigma-algebra-evaluation": 0,
        "bridge:consequence": 1,
    }
    return (
        layer_rank.get(artifact.get("layer"), 99),
        kind_rank.get(artifact.get("kind"), 99),
        id_rank.get(artifact.get("id"), 50),
        artifact.get("title", ""),
        artifact.get("id", ""),
    )


def order_artifacts(artifacts: list[dict]) -> list[dict]:
    by_id = {artifact.get("id"): artifact for artifact in artifacts if artifact.get("id")}
    indegree = {artifact.get("id"): 0 for artifact in artifacts}
    outgoing = {artifact.get("id"): [] for artifact in artifacts}
    for artifact in artifacts:
        artifact_id = artifact.get("id")
        if not artifact_id:
            continue
        for dep in artifact.get("depends_on", []):
            dep_id = dep.get("id")
            if dep_id in by_id:
                outgoing[dep_id].append(artifact)
                indegree[artifact_id] = indegree.get(artifact_id, 0) + 1

    ready = sorted(
        [artifact for artifact in artifacts if indegree.get(artifact.get("id"), 0) == 0],
        key=model_artifact_rank,
    )
    ordered: list[dict] = []
    while ready:
        artifact = ready.pop(0)
        ordered.append(artifact)
        for dependent in sorted(outgoing.get(artifact.get("id"), []), key=model_artifact_rank):
            dependent_id = dependent.get("id")
            indegree[dependent_id] = indegree.get(dependent_id, 0) - 1
            if indegree.get(dependent_id, 0) == 0:
                ready.append(dependent)
                ready.sort(key=model_artifact_rank)

    if len(ordered) != len(artifacts):
        return sorted(artifacts, key=model_artifact_rank)
    return ordered


def default_source_root() -> Path:
    here = Path(__file__).resolve()
    sibling = here.parents[2] / "lra-volume-i"
    return sibling if sibling.exists() else Path.cwd()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=default_source_root())
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "model-artifacts.json")
    parser.add_argument("--macro-file", type=Path, default=None, help="TeX macro file used to seed frontend KaTeX macros.")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero when validation errors are present.")
    args = parser.parse_args()

    root = args.source_root.resolve()
    if not root.exists():
        print(f"[ERROR] source root not found: {root}", file=sys.stderr)
        return 2

    search_roots = [
        root / "volume-i" / "axiom-systems" / "notes" / "models",
        root / "volume-i" / "propositional-logic" / "notes" / "model",
        root / "volume-i" / "predicate-logic" / "notes" / "model",
        root / "volume-i" / "set-theory" / "notes" / "model",
    ]
    files: list[Path] = []
    for search_root in search_roots:
        if search_root.exists():
            files.extend(sorted(search_root.glob("*.tex")))

    errors: list[ExtractionError] = []
    artifacts: list[dict] = []
    for path in files:
        artifacts.extend(extract_file(path, root, errors))
    artifacts = order_artifacts(artifacts)
    validate(artifacts, errors, forbid_generic_components=args.strict)
    macro_file = args.macro_file.resolve() if args.macro_file else default_macro_file(root)
    katex_macros = extract_katex_macros(macro_file)

    payload = {
        "metadata": {
            "schema_version": "0.1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_root": root.name,
            "artifact_count": len(artifacts),
            "error_count": len(errors),
            "katex_macro_count": len(katex_macros["macros"]),
            "katex_macro_source": katex_macros["source_file"],
        },
        "katex_macros": katex_macros,
        "artifacts": artifacts,
        "errors": [error.__dict__ for error in errors],
    }
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(artifacts)} model artifacts to {args.output}")
    if errors:
        print(f"[WARN] {len(errors)} validation error(s); see payload errors.")
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
