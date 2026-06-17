#!/usr/bin/env python3
"""
reorder/apply_resolution.py
===========================
Consume LLM resolution files and route them by *consequence*, not by trust.

A resolution (written by the semantic pass, one per graph) looks like:

    {
      "graph_id": "0020-0030",
      "term": "def:supremum",
      "verdict": "ok" | "reorder" | "change",
      "dependencies": ["def:ordered-set", "def:subset", "def:upper-bound"],
      "rationale": "....",
      "licensing_quote": "every upper bound u of A satisfies s <= u",
      "confidence": 0.93
    }

Routing
-------
  ok       -> logged, nothing emitted.
  reorder  -> ONLY if set(proposed) == set(current). A reorder is a permutation
              of an already-correct set, so it is safe to auto-apply. The order
              written is computed HERE (deterministic canonical sort), not taken
              from the model. Records go to patches.yaml (idempotent / runnable).
  change   -> the proposed set differs from current. Goes to suspicious.yaml for
              human review, as one add/delete record per differing edge.

The guard: if a resolution claims "reorder" but the sets differ, it is NOT a
reorder -- it is a content change wearing a reorder's costume. We reclassify it
to suspicious so a content edit can never auto-apply into the source.

Low-confidence changes (< --focus-threshold) are diverted to focus-queue.yaml
for a deeper, single-node re-run instead of cluttering the review file.

Every processed resolution appends a line to progress.yaml and a rendered
ASCII tree (graph-NNNN.tree.txt) for human inspection. No .tex / .json source
is ever modified by this script.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX = HERE / "index.json"

PATCHES = HERE / "patches.yaml"
SUSPICIOUS = HERE / "suspicious.yaml"
FOCUS = HERE / "focus-queue.yaml"
PROGRESS = HERE / "progress.yaml"

# Foundational-first canonical ordering for a dependency list.
KIND_RANK = {"Axiom": 0, "Definition": 2, "Lemma": 3,
             "Proposition": 4, "Corollary": 5, "Theorem": 6}


def load_index() -> dict:
    if INDEX.exists():
        return {r["id"]: r for r in json.loads(INDEX.read_text(encoding="utf-8"))}
    return {}


def rank(idx: dict, dep_id: str) -> tuple:
    rec = idx.get(dep_id, {})
    if rec.get("root") in ("axiom", "definitional_truth"):
        kr = 1                       # roots just after axioms, before ordinary defs
    else:
        kr = KIND_RANK.get(rec.get("kind"), 7)
    return (kr, rec.get("title", dep_id).lower(), dep_id)


def canonical_order(idx: dict, ids: list[str]) -> list[str]:
    return sorted(ids, key=lambda d: rank(idx, d))


# --- minimal YAML emitter for append-only sequences of flat records ---
def _scalar(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_scalar(x) for x in v) + "]"
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    needs_quote = any(c in s for c in ":#[]{}-\"'\n") or s.strip() != s or s == ""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"' if needs_quote else s


def append_record(path: Path, record: dict) -> None:
    lines = []
    first = True
    for k, v in record.items():
        prefix = "- " if first else "  "
        lines.append(f"{prefix}{k}: {_scalar(v)}")
        first = False
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def render_tree(idx: dict, term: str, dep_ids: list[str]) -> str:
    def lbl(i):
        r = idx.get(i, {})
        tag = r.get("root") or r.get("kind", "")
        return f"{i}  [{tag}]" if tag else i
    out = [lbl(term)]
    for n, d in enumerate(dep_ids):
        branch = "\u2514\u2500" if n == len(dep_ids) - 1 else "\u251c\u2500"
        out.append(f"{branch} {lbl(d)}")
    return "\n".join(out)


def current_deps_for(resolution_path: Path):
    graph_path = resolution_path.with_name(
        resolution_path.name.replace("resolution-", "graph-"))
    if not graph_path.exists():
        raise SystemExit(f"[ERROR] matching graph file not found: {graph_path}")
    g = json.loads(graph_path.read_text(encoding="utf-8"))
    return [d["id"] for d in g.get("current_dependencies", [])], g


def process(resolution_path: Path, idx: dict, focus_threshold: float) -> str:
    res = json.loads(resolution_path.read_text(encoding="utf-8"))
    term = res.get("term", "?")
    verdict = res.get("verdict", "ok")
    proposed = list(dict.fromkeys(res.get("dependencies", [])))  # dedup, keep order
    confidence = float(res.get("confidence", 0.0) or 0.0)
    current, graph = current_deps_for(resolution_path)
    vol, chap = graph.get("volume", ""), graph.get("chapter", "")

    # write the human-readable tree next to the graph
    tree = render_tree(idx, term, canonical_order(idx, proposed or current))
    resolution_path.with_name(
        resolution_path.name.replace("resolution-", "graph-").replace(".json", ".tree.txt")
    ).write_text(tree + "\n", encoding="utf-8")

    same_set = set(proposed) == set(current)
    outcome = verdict

    if verdict == "ok":
        outcome = "ok"

    elif verdict == "reorder" and same_set:
        new_order = canonical_order(idx, proposed)
        if new_order != current:
            append_record(PATCHES, {
                "volume": vol, "chapter": chap, "term": term,
                "change_type": "reorder",
                "old_order": current, "new_order": new_order,
                "confidence": confidence,
            })
            outcome = "reorder->patches"
        else:
            outcome = "reorder-noop"

    else:
        # verdict == "change", OR a "reorder" whose set actually differs (guard trip)
        if verdict == "reorder" and not same_set:
            outcome = "reorder-guard-tripped->suspicious"
        added = [d for d in proposed if d not in current]
        removed = [d for d in current if d not in proposed]
        target = FOCUS if confidence < focus_threshold else SUSPICIOUS
        for d in added:
            append_record(target, {
                "volume": vol, "chapter": chap, "term": term,
                "change_type": "add", "dependency": d,
                "rationale": res.get("rationale", ""),
                "licensing_quote": res.get("licensing_quote", ""),
                "confidence": confidence,
            })
        for d in removed:
            append_record(target, {
                "volume": vol, "chapter": chap, "term": term,
                "change_type": "delete", "dependency": d,
                "rationale": res.get("rationale", ""),
                "confidence": confidence,
            })
        if target is FOCUS:
            outcome = "change->focus" if outcome == "change" else outcome.replace("suspicious", "focus")
        elif outcome == "change":
            outcome = "change->suspicious"

    append_record(PROGRESS, {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graph_id": res.get("graph_id", ""), "volume": vol, "chapter": chap,
        "term": term, "verdict": verdict, "outcome": outcome,
        "confidence": confidence,
    })
    return outcome


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply LLM resolution files.")
    ap.add_argument("path", help="a resolution-NNNN.json file, or a batch dir with --batch")
    ap.add_argument("--batch", action="store_true",
                    help="treat path as a batch dir; apply every resolution-*.json in it")
    ap.add_argument("--focus-threshold", type=float, default=0.6,
                    help="changes below this confidence go to focus-queue.yaml")
    args = ap.parse_args()

    idx = load_index()
    target = Path(args.path)
    resolutions = (sorted(target.glob("resolution-*.json"))
                   if args.batch else [target])
    if not resolutions:
        raise SystemExit("[ERROR] no resolution files found.")

    counts: dict[str, int] = {}
    for r in resolutions:
        outcome = process(r, idx, args.focus_threshold)
        counts[outcome] = counts.get(outcome, 0) + 1
        print(f"  {r.name:28} -> {outcome}")

    print("\nsummary:")
    for k, v in sorted(counts.items()):
        print(f"  {k:34} {v}")
    print("\npatches.yaml / suspicious.yaml / focus-queue.yaml updated; progress.yaml appended.")


if __name__ == "__main__":
    main()
