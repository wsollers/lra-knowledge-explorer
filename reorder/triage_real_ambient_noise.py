#!/usr/bin/env python3
"""
Apply deterministic real-ambient triage to review decisions.

This is a review-artifact pass only. It does not edit source TeX, graph JSON, or
semantic-pass resolution JSON.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
UNIVERSE = HERE / "dependency-universe.json"
DECISIONS = HERE / "review-decisions.json"
REPORT = HERE / "processed-batches-status.md"
MANIFEST = HERE / "manifest.json"

REAL_AMBIENT_TERMS = {
    "def:reals",
    "def:order-on-r",
    "def:strict-order-on-r",
    "def:real-chapter-absolute-value-on-r",
    "def:addition-on-r",
    "def:subtraction-on-r",
    "def:multiplication-on-r",
    "def:division-on-r",
    "def:zero-in-r",
    "def:one-in-r",
    "def:negation-on-r",
    "def:reciprocal-on-r",
    "def:abstract-field",
    "def:abstract-ordered-field",
    "def:real-ordered-field",
    "thm:r-is-a-field",
    "thm:r-is-an-ordered-field",
    "thm:r-is-complete-ordered-field",
    "thm:lub-property-r",
}

REAL_AMBIENT_ANCESTORS = {
    "def:reals",
    "def:limit-function",
    "def:continuous-at-point",
    "def:sequence",
    "def:real-sequence",
    "def:real-valued-function",
    "def:real-ordered-field",
    "def:abstract-ordered-field",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_maps(universe: dict[str, Any]) -> tuple[dict[tuple[str, str], set[str]], dict[str, set[str]], dict[str, set[str]]]:
    direct = {term: set(deps) for term, deps in universe.get("direct_dependencies", {}).items()}
    transitive = {term: set(deps) for term, deps in universe.get("transitive_dependencies", {}).items()}
    proposed: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in universe.get("proposed_additions", []):
        proposed[(row.get("batch", ""), row.get("graph", ""))].add(row.get("dependency", ""))
    return proposed, direct, transitive


def has_real_ambient_context(term: str, adds: set[str], direct: dict[str, set[str]], transitive: dict[str, set[str]]) -> bool:
    context = set(direct.get(term, set()))
    context.update(transitive.get(term, set()))
    context.update(adds)
    return bool(context & REAL_AMBIENT_ANCESTORS)


def real_ambient_adds(adds: set[str]) -> set[str]:
    return adds & REAL_AMBIENT_TERMS


def apply_real_ambient_triage(decision: dict[str, Any], direct: dict[str, set[str]], transitive: dict[str, set[str]]) -> bool:
    if decision.get("verdict") != "change":
        return False
    if decision.get("decision") == "applied":
        return False
    adds = set(decision.get("adds") or [])
    if not adds:
        return False
    term = decision.get("term", "")
    noisy = real_ambient_adds(adds)
    if not noisy or not has_real_ambient_context(term, adds, direct, transitive):
        return False

    removes = set(decision.get("removes") or [])
    non_noisy_adds = adds - noisy

    if not removes and not non_noisy_adds:
        decision["decision"] = "rejected"
        decision["reason"] = (
            "real ambient structure should be carried by def:reals or its ambient ancestor, "
            f"not repeated as direct descendant edges: {', '.join(sorted(noisy))}"
        )
        decision["ambient_noise_rejected"] = sorted(noisy)
        return True

    if decision.get("decision") != "rejected":
        decision["decision"] = "investigate"
    decision["reason"] = (
        "mixed proposal contains real-ambient noise better handled by def:reals or an ambient ancestor; "
        f"review remaining changes separately: {', '.join(sorted(noisy))}"
    )
    decision["ambient_noise_rejected"] = sorted(noisy)
    return True


def update_summary(payload: dict[str, Any]) -> None:
    decisions = payload.get("decisions", [])
    change_counts = Counter(
        row.get("decision", "other")
        for row in decisions
        if row.get("verdict") == "change"
    )
    payload.setdefault("summary", {}).setdefault("change_decisions", {})
    payload["summary"]["change_decisions"] = {
        "applied": change_counts.get("applied", 0),
        "rejected": change_counts.get("rejected", 0),
        "investigate": change_counts.get("investigate", 0),
    }
    payload["summary"]["real_ambient_noise_marked"] = sum(
        1 for row in decisions if row.get("ambient_noise_rejected")
    )
    payload["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")


def format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "(none)"


def graph_dependencies(batch: str, graph_name: str) -> list[str]:
    graph = load_json(HERE / batch / graph_name)
    return sorted(dep["id"] for dep in graph.get("current_dependencies", []) if dep.get("id"))


def resolution_dependencies(batch: str, resolution_name: str) -> list[str]:
    resolution = load_json(HERE / batch / resolution_name)
    return sorted(dep for dep in resolution.get("dependencies", []) if isinstance(dep, str) and dep)


def markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def write_report(payload: dict[str, Any], changed: int) -> None:
    decisions = payload.get("decisions", [])
    summary = payload.get("summary", {})
    manifest = load_json(MANIFEST)
    change_decisions = summary.get("change_decisions", {})
    per_batch: dict[str, Counter[str]] = defaultdict(Counter)
    verdicts_by_batch: dict[str, Counter[str]] = defaultdict(Counter)
    resolutions_by_batch: Counter[str] = Counter()
    confidence_by_batch: dict[str, list[float]] = defaultdict(list)
    for row in decisions:
        batch = row.get("batch", "")
        verdicts_by_batch[batch][row.get("verdict", "other")] += 1
        resolutions_by_batch[batch] += 1
        if isinstance(row.get("confidence"), int | float):
            confidence_by_batch[batch].append(float(row["confidence"]))
        if row.get("verdict") == "change":
            per_batch[batch][row.get("decision", "other")] += 1

    ambient_rows = [
        row for row in decisions
        if row.get("ambient_noise_rejected")
    ]
    ambient_rows.sort(key=lambda row: (row.get("batch", ""), row.get("graph", ""), row.get("term", "")))

    lines = [
        "# Processed Batch Status",
        "",
        f"Generated: {payload.get('generated_at', '')}",
        "",
        "## Summary",
        "",
        f"- Total manifest batches: {summary.get('total_batches', 0)}",
        f"- Batches with semantic-pass resolutions: {summary.get('processed_batches', 0)}",
        f"- Graphs in manifest: {summary.get('graphs_manifest', 0)}",
        f"- Graphs processed: {summary.get('graphs_processed', 0)}",
        f"- Resolution files present: {summary.get('resolutions', 0)}",
        f"- Unresolved graphs: {summary.get('unresolved', 0)}",
        f"- Verdict totals: {', '.join(f'{k}={v}' for k, v in summary.get('verdicts', {}).items())}",
        (
            "- Change decisions: "
            f"applied={change_decisions.get('applied', 0)}, "
            f"rejected={change_decisions.get('rejected', 0)}, "
            f"investigate={change_decisions.get('investigate', 0)}"
        ),
        f"- Real-ambient noise decisions marked: {summary.get('real_ambient_noise_marked', 0)}",
        f"- Decisions changed by latest real-ambient pass: {changed}",
        "",
        "## Real-Ambient Noise",
        "",
        "| Batch | Graph | Term | Decision | Ambient Noise | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for row in ambient_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row.get("batch", ""),
                    row.get("graph", ""),
                    row.get("term", ""),
                    row.get("decision", ""),
                    format_list(row.get("ambient_noise_rejected", [])),
                    row.get("reason", "").replace("|", "\\|"),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Per-Batch Change Decisions", "", "| Batch | Applied | Rejected | Investigate |", "|---|---:|---:|---:|"])
    for entry in manifest:
        batch = entry["batch"]
        counts = per_batch[batch]
        lines.append(f"| {batch} | {counts.get('applied', 0)} | {counts.get('rejected', 0)} | {counts.get('investigate', 0)} |")

    lines.extend(
        [
            "",
            "## Processed Batch Table",
            "",
            "| Batch | Volume | Chapter | Status | Graphs | Resolutions | OK | Reorder | Change | Other | Applied Changes | Rejected Changes | Investigate Changes | Avg Confidence | Min Confidence | Last Resolution |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for entry in manifest:
        batch = entry["batch"]
        counts = verdicts_by_batch[batch]
        decision_counts = per_batch[batch]
        confidences = confidence_by_batch[batch]
        resolution_files = sorted((HERE / batch).glob("resolution-*.json"))
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        min_conf = min(confidences) if confidences else 0.0
        status = "complete" if resolutions_by_batch[batch] == entry["graphs"] else "partial"
        lines.append(
            "| "
            + " | ".join(
                [
                    batch,
                    entry.get("volume", ""),
                    entry.get("chapter", ""),
                    status,
                    str(entry.get("graphs", 0)),
                    str(resolutions_by_batch[batch]),
                    str(counts.get("ok", 0)),
                    str(counts.get("reorder", 0)),
                    str(counts.get("change", 0)),
                    str(sum(v for k, v in counts.items() if k not in {"ok", "reorder", "change"})),
                    str(decision_counts.get("applied", 0)),
                    str(decision_counts.get("rejected", 0)),
                    str(decision_counts.get("investigate", 0)),
                    f"{avg_conf:.3f}",
                    f"{min_conf:.3f}",
                    resolution_files[-1].name if resolution_files else "",
                ]
            )
            + " |"
        )

    decisions_by_batch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in decisions:
        if row.get("verdict") == "change":
            decisions_by_batch[row.get("batch", "")].append(row)

    lines.extend(["", "## Change Candidates", ""])
    for entry in manifest:
        batch = entry["batch"]
        rows = sorted(decisions_by_batch.get(batch, []), key=lambda row: row.get("graph", ""))
        if not rows:
            continue
        lines.extend(
            [
                f"### {batch}",
                "",
                "| Graph | Resolution | Term | Decision | Decision Reason | Current Dependencies | Proposed Dependencies | Adds | Removes | Ambient Noise | Confidence |",
                "|---|---|---|---|---|---|---|---|---|---|---:|",
            ]
        )
        for row in rows:
            current = graph_dependencies(batch, row.get("graph", ""))
            proposed = resolution_dependencies(batch, row.get("resolution", ""))
            lines.append(
                "| "
                + " | ".join(
                    [
                        row.get("graph", ""),
                        row.get("resolution", ""),
                        row.get("term", ""),
                        row.get("decision", ""),
                        markdown_escape(row.get("reason", "")),
                        markdown_escape(format_list(current)),
                        markdown_escape(format_list(proposed)),
                        markdown_escape(format_list(row.get("adds", []))),
                        markdown_escape(format_list(row.get("removes", []))),
                        markdown_escape(format_list(row.get("ambient_noise_rejected", []))),
                        f"{float(row.get('confidence') or 0):.3f}",
                    ]
                )
                + " |"
            )
        lines.append("")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    universe = load_json(UNIVERSE)
    payload = load_json(DECISIONS)
    _proposed, direct, transitive = build_maps(universe)

    changed = 0
    for decision in payload.get("decisions", []):
        before = json.dumps(decision, sort_keys=True)
        apply_real_ambient_triage(decision, direct, transitive)
        after = json.dumps(decision, sort_keys=True)
        if before != after:
            changed += 1

    update_summary(payload)
    write_json(DECISIONS, payload)
    write_report(payload, changed)
    print(f"Updated {DECISIONS}")
    print(f"Updated {REPORT}")
    print(f"Real-ambient decisions marked: {payload['summary']['real_ambient_noise_marked']}")
    print(f"Decisions changed: {changed}")
    print(json.dumps(payload["summary"]["change_decisions"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
