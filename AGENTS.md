<!--
GENERATED POINTER WRAPPER — DO NOT EDIT BY HAND.

Source repo: wsollers/lra-governance
Source revision: 0b8247413f9309a9cbf9f6cf36be57aba265bc70
Source documents:
- capabilities/manifest.yaml
- docs/governance/agent-instruction-policy.md
- docs/architecture/generated-file-policy.md
- docs/governance/repo-overlays/lra-knowledge-explorer.md
Canonical overlay: docs/governance/repo-overlays/lra-knowledge-explorer.md

Regenerate from lra-governance.
Emergency downstream edits must be ported upstream before regeneration.
-->

# Agent Instructions

This repository uses canonical LRA governance by pointer, not by copied rules.

Repository: `lra-knowledge-explorer`
Canonical repo overlay: `docs/governance/repo-overlays/lra-knowledge-explorer.md`
Canonical route resolver:
`python <governance-root>/capabilities/resolve.py --repo lra-knowledge-explorer --task "<user task>" --root <repo-root>`
Human route index (lazy reference only): `docs/agent-task-index.md`

Resolve canonical governance in this order:

1. `LRA_GOVERNANCE_ROOT`;
2. sibling `../lra-governance`;
3. an explicit `lra-governance` checkout supplied by the build image or task.

If canonical governance cannot be resolved, stop and report that
`lra-governance` is not present.

After resolving canonical governance, run the route resolver. Load its eager
packet only; follow lazy references, tools, schemas, and examples on demand.
Do not treat this wrapper as a local source of truth.

Provider note: Codex reads this file as the local entrypoint, then follows canonical governance.
