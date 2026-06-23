#!/usr/bin/env python3
"""
Build the optional proof-vault index consumed by knowledge-explorer.html.

The explorer is a static page, so it cannot browse sibling repositories at
runtime. This script snapshots reviewed markdown records from lra-proof-vault
into proof-vault-index.json, keyed by canonical theorem label.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VAULT_ROOT = REPO_ROOT.parent / "lra-proof-vault"
OUTPUT = REPO_ROOT / "proof-vault-index.json"
GITHUB_BLOB_BASE = "https://github.com/wsollers/lra-proof-vault/blob/master"

LABEL_RE = re.compile(r"Canonical theorem label:\s*`([^`]+)`", re.IGNORECASE)
STATUS_RE = re.compile(r"Status:\s*`([^`]+)`", re.IGNORECASE)
HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
TRANSCRIPTION_RE = re.compile(r"^##\s+Transcription\s*$([\s\S]*?)(?=^##\s+|\Z)", re.MULTILINE)


def rel_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def title_for(text: str, md_path: Path) -> str:
    match = HEADING_RE.search(text)
    if match:
        return match.group(1).strip()
    return md_path.parent.name.replace("-", " ").title()


def body_for(text: str) -> str:
    match = TRANSCRIPTION_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def read_sibling_text(md_path: Path, suffix: str) -> str:
    name = md_path.name
    if name.endswith(".proof.md"):
        path = md_path.with_name(name[: -len(".proof.md")] + suffix)
    else:
        path = md_path.with_suffix(suffix)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def build(vault_root: Path) -> dict:
    records: dict[str, list[dict]] = {}
    md_paths = [
        path
        for path in vault_root.rglob("*.md")
        if ".git" not in path.parts and path.name.lower().startswith("proof-")
    ]

    for md_path in sorted(md_paths):
        text = md_path.read_text(encoding="utf-8")
        label_match = LABEL_RE.search(text)
        if not label_match:
            continue

        label = label_match.group(1).strip()
        attempt_dir = md_path.parent
        image_paths = sorted(attempt_dir.glob("*.jpg")) + sorted(attempt_dir.glob("*.png"))
        image_links = [
            f"{GITHUB_BLOB_BASE}/{rel_posix(image_path, vault_root)}"
            for image_path in image_paths
        ]
        status_match = STATUS_RE.search(text)

        rec = {
            "title": title_for(text, md_path),
            "path": rel_posix(md_path, vault_root),
            "vault_record": rel_posix(attempt_dir, vault_root),
            "review_status": status_match.group(1).strip() if status_match else "",
            "images": image_links,
            "body": body_for(text),
            "ocr_text": read_sibling_text(md_path, ".ocr.txt"),
            "markdown": text.strip(),
            "tex": read_sibling_text(md_path, ".tex"),
        }
        records.setdefault(label, []).append(rec)

    return {
        "schema": "lra.proof_vault_index",
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": rel_posix(vault_root, REPO_ROOT.parent),
        "record_count": sum(len(items) for items in records.values()),
        "records": records,
    }


def main() -> None:
    if not DEFAULT_VAULT_ROOT.exists():
        raise SystemExit(f"Proof vault not found: {DEFAULT_VAULT_ROOT}")
    index = build(DEFAULT_VAULT_ROOT)
    OUTPUT.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUTPUT} with {index['record_count']} records.")


if __name__ == "__main__":
    main()
