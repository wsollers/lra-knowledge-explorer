#!/usr/bin/env python3
"""
Build the optional proof-vault index consumed by knowledge-explorer.html.

The explorer is a static page, so it cannot browse sibling repositories at
runtime. This script snapshots accepted, reviewed-correct proof records from
lra-proof-vault into proof-vault-index.json, keyed by canonical theorem label.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required: pip install pyyaml") from exc


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VAULT_ROOT = REPO_ROOT.parent / "lra-proof-vault"
OUTPUT = REPO_ROOT / "proof-vault-index.json"
GITHUB_BLOB_BASE = "https://github.com/wsollers/lra-proof-vault/blob/master"


def rel_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return data if isinstance(data, dict) else {}


def read_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def attempt_path(folder: Path, attempt: dict[str, Any], key: str) -> Path | None:
    value = attempt.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return folder / value


def tags_text(attempt: dict[str, Any]) -> str:
    tags = attempt.get("tags")
    if not isinstance(tags, list) or not tags:
        return ""
    return "\n\nTags: " + ", ".join(str(tag) for tag in tags)


def image_links(vault_root: Path, folder: Path, attempt: dict[str, Any]) -> list[str]:
    path = attempt_path(folder, attempt, "source_path")
    if path is None or not path.exists():
        return []
    return [f"{GITHUB_BLOB_BASE}/{rel_posix(path, vault_root)}"]


def should_publish(attempt: dict[str, Any]) -> bool:
    return (
        attempt.get("review_status") == "reviewed-correct"
        and attempt.get("text_review_status") == "accepted"
        and bool(attempt.get("markdown_path"))
        and bool(attempt.get("tex_path"))
        and bool(attempt.get("ocr_text_path"))
    )


def record_for(vault_root: Path, metadata_path: Path, metadata: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    folder = metadata_path.parent
    title = str(metadata.get("theorem_title") or metadata.get("theorem_id") or "Untitled")
    notes = str(attempt.get("notes") or "").strip()
    vault_record = rel_posix(folder, vault_root)
    return {
        "title": f"{title} ({attempt.get('attempt_id')})",
        "path": rel_posix(metadata_path, vault_root),
        "vault_record": vault_record,
        "vault_url": f"https://github.com/wsollers/lra-proof-vault/tree/master/{vault_record}",
        "attempt_id": str(attempt.get("attempt_id") or ""),
        "review_status": str(attempt.get("review_status") or ""),
        "images": image_links(vault_root, folder, attempt),
        "body": notes + tags_text(attempt),
        "ocr_text": read_text(attempt_path(folder, attempt, "ocr_text_path")),
        "markdown": read_text(attempt_path(folder, attempt, "markdown_path")),
        "tex": read_text(attempt_path(folder, attempt, "tex_path")),
        "text_source": str(attempt.get("text_source") or ""),
        "text_review_status": str(attempt.get("text_review_status") or ""),
    }


def build(vault_root: Path) -> dict[str, Any]:
    records: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    for metadata_path in sorted(vault_root.glob("volume-*/**/metadata.yaml")):
        metadata = load_yaml(metadata_path)
        label = metadata.get("theorem_id")
        attempts = metadata.get("attempts")
        if not isinstance(label, str) or not isinstance(attempts, list):
            continue

        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            if not should_publish(attempt):
                continue
            record = record_for(vault_root, metadata_path, metadata, attempt)
            missing = [key for key in ("ocr_text", "markdown", "tex") if not record[key]]
            if missing:
                warnings.append(f"{label}::{attempt.get('attempt_id')}: missing {', '.join(missing)}")
                continue
            records.setdefault(label, []).append(record)

    return {
        "schema": "lra.proof_vault_index",
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": rel_posix(vault_root, REPO_ROOT.parent),
        "record_count": sum(len(items) for items in records.values()),
        "warning_count": len(warnings),
        "warnings": warnings,
        "records": records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vault-root",
        type=Path,
        default=DEFAULT_VAULT_ROOT,
        help="Path to the lra-proof-vault checkout to snapshot.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="Destination JSON file for the generated proof-vault index.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    vault_root = args.vault_root.resolve()
    output_path = args.output.resolve()
    if not vault_root.exists():
        raise SystemExit(f"Proof vault not found: {vault_root}")
    index = build(vault_root)
    output_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {output_path} with {index['record_count']} records and {index['warning_count']} warnings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
