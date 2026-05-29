<!--
GENERATED FILE — DO NOT EDIT BY HAND.

Source repo: wsollers/lra-governance
Source commit: a55609adaf2be4bd68941a4cb78336e56d92a60b
Generated from:
- docs/governance/...
- docs/architecture/...
- docs/governance/repo-overlays/lra-knowledge-explorer.md

Regenerate from lra-governance.
Emergency downstream edits must be ported upstream before the next sync.
-->

# Claude Instructions

@AGENTS.md

If import semantics are unavailable, use the generated `AGENTS.md` content for
the same repository as the canonical local instruction body.

## Global Agent Rules

- Treat generated instruction files as derived artifacts.
- Follow the owning repository boundary for every task.
- Do not include secrets, credentials, tokens, or machine-local private values.
- Do not modify mathematical content during governance or wrapper-generation tasks.
- Do not touch `Learning-Real-Analysis/scripts/`.
- Port emergency downstream instruction repairs back to `lra-governance`.

## Repo Overlay

# lra-knowledge-explorer Overlay

Stub overlay for theorem explorer and extraction pipeline work.

Owned concerns:

- extraction pipeline implementation,
- knowledge graph and edge generation,
- explorer UI,
- rebuild dispatch expectations.

## Agent Scope

Extraction implementation and UI changes belong here. Monorepo changes may
trigger rebuild dispatch, but extractor code ownership remains with
`lra-knowledge-explorer`.

Do not duplicate canonical YAML ownership here.

## Provider Notes

Claude should use this wrapper as a pointer to the generated repo instructions.
