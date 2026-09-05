<!--
GENERATED POINTER WRAPPER — DO NOT EDIT BY HAND.

Source repo: wsollers/lra-governance
Canonical overlay: capabilities/overlays/lra-knowledge-explorer.md

Regenerate from lra-governance.
Emergency downstream edits must be ported upstream before regeneration.
-->

# Gemini Instructions

This repository uses canonical LRA governance by pointer, not by copied rules.

Repository: `lra-knowledge-explorer`
Canonical repo overlay: `capabilities/overlays/lra-knowledge-explorer.md`
Canonical route resolver:
`python <governance-root>/scripts/govpy.py capabilities/resolve.py --repo lra-knowledge-explorer --task "<user task>" --root <repo-root>`
Human route index (lazy reference only): `capabilities/task-index.md`

Resolve canonical governance in this order:

1. `LRA_GOVERNANCE_ROOT`;
2. sibling `../lra-governance`;
3. an explicit `lra-governance` checkout supplied by the build image or task.

If canonical governance cannot be resolved, stop and report that
`lra-governance` is not present.

Follow `AGENTS.md` in this repository as the local pointer wrapper, then run
the resolver. Do not treat this file as a local source of truth.

Provider note: Gemini should follow this pointer wrapper and canonical governance.
