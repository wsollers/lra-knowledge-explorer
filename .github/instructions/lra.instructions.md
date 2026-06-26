<!--
GENERATED FILE — DO NOT EDIT BY HAND.

Source repo: wsollers/lra-governance
Source commit: 36fd69ac2e23b406e522c0c753400ce7f3938ff0
Generated from:
- docs/governance/...
- docs/architecture/...
- docs/governance/repo-overlays/lra-knowledge-explorer.md

Regenerate from lra-governance.
Emergency downstream edits must be ported upstream before regeneration.
-->

# LRA Repository Instructions

This file is intended for `.github/instructions/lra.instructions.md`. Keep it
concise and refer to canonical governance docs rather than copying large docs.

## Global Agent Rules

- Treat generated instruction files as derived artifacts.
- Follow the owning repository boundary for every task.
- Do not include secrets, credentials, tokens, or machine-local private values.
- Do not modify mathematical content during governance or wrapper-generation tasks.
- Do not touch the retired `Learning-Real-Analysis` monorepo.
- Port emergency downstream instruction repairs back to `lra-governance`.

## Repo Overlay

# lra-knowledge-explorer Overlay

Stub overlay for theorem explorer and extraction pipeline work.

Owned concerns:

- extraction pipeline implementation,
- knowledge graph and edge generation,
- explorer UI,
- rebuild refresh expectations.

## Agent Scope

Extraction implementation and UI changes belong here. The rebuild is
orchestrated from `lra-governance` over the independent volume repos, but
extractor code ownership remains with `lra-knowledge-explorer`.

Do not duplicate canonical YAML ownership here.

## Formal Verification Surface

When explorer records include formal verification metadata, the UI should show
it as a first-class proof companion rather than as ordinary prose. The proof
modal should include a `Verification` tab that displays:

- the verification system,
- status,
- module and declaration when known,
- source path when known,
- well-formatted formal code when available.

The UI must not present pending or incomplete targets as checked. Missing code
or missing metadata should render as an explicit empty state, not as a broken
panel.

## Provider Notes

Keep provider-specific guidance concise and defer durable policy to governance docs.
