#!/usr/bin/env python3
"""Record an accepted dependency delta idempotently."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REORDER = HERE.parent


def load_json(path: Path) -> Any:
    if not path.exists():
        return {
            "schema_version": "reorder-working-delta-2",
            "description": "Accepted review deltas.",
            "adds": [],
            "removes": [],
            "proof_dependencies": [],
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("adds", [])
    payload.setdefault("removes", [])
    payload.setdefault("proof_dependencies", [])
    if payload.get("schema_version") == "reorder-working-delta-1":
        payload["schema_version"] = "reorder-working-delta-2"
    return payload


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


class FileLock:
    def __init__(self, path: Path, timeout: float = 30.0) -> None:
        self.path = path
        self.timeout = timeout
        self.fd: int | None = None

    def __enter__(self) -> "FileLock":
        start = time.monotonic()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode("ascii", errors="ignore"))
                return self
            except FileExistsError:
                if time.monotonic() - start > self.timeout:
                    raise TimeoutError(f"timed out waiting for lock: {self.path}")
                time.sleep(0.1)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def normalize(record: dict[str, Any]) -> dict[str, Any]:
    return {key: record[key] for key in sorted(record)}


def upsert(records: list[dict[str, Any]], record: dict[str, Any]) -> list[dict[str, Any]]:
    key = (record["source"], record["target"])
    existing = next((item for item in records if (item.get("source"), item.get("target")) == key), None)
    if existing and existing.get("recorded_at"):
        record["recorded_at"] = existing["recorded_at"]
    out = [item for item in records if (item.get("source"), item.get("target")) != key]
    out.append(record)
    return sorted((normalize(item) for item in out), key=lambda item: (item.get("source", ""), item.get("target", "")))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delta", type=Path, default=REORDER / "state" / "working-delta.json")
    parser.add_argument("--action", choices=("add", "remove", "proof"), required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--reason", default="")
    parser.add_argument("--batch", default="")
    parser.add_argument("--resolution", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with FileLock(args.delta.with_suffix(args.delta.suffix + ".lock")):
        delta = load_json(args.delta)
        record = {
            "source": args.source,
            "target": args.target,
            "reason": args.reason,
            "batch": args.batch,
            "resolution": args.resolution,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        if args.action == "proof":
            target_key = "proof_dependencies"
            opposite_key = "adds"
        else:
            target_key = "adds" if args.action == "add" else "removes"
            opposite_key = "removes" if args.action == "add" else "adds"
            if args.action == "add":
                delta["proof_dependencies"] = [
                    item
                    for item in delta.get("proof_dependencies", [])
                    if (item.get("source"), item.get("target")) != (args.source, args.target)
                ]
        delta[target_key] = upsert(delta.get(target_key, []), record)
        delta[opposite_key] = [
            item for item in delta.get(opposite_key, []) if (item.get("source"), item.get("target")) != (args.source, args.target)
        ]
        write_json(args.delta, delta)
    print(f"recorded {args.action}: {args.source} -> {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
