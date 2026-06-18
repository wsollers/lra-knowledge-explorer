# Processed Batch Status Report Prompt

Use this prompt when you need to regenerate
`reorder/processed-batches-status.md` from the current filesystem state.

## Goal

Generate a Markdown status report for the dependency reorder audit. The report
must summarize only batches that have already been processed by the semantic
pass, meaning batches with at least one sibling `resolution-*.json` file.

Write the report to:

```text
reorder/processed-batches-status.md
```

## Inputs

Read from the `reorder/` directory:

- `manifest.json`
- `batch-*/graph-*.json`
- `batch-*/resolution-*.json`

Do not modify graph or resolution files.

The pipeline calls model outputs `resolution-####.json`; if someone says
`solution-####.json`, interpret that as `resolution-####.json` unless actual
solution files exist.

## Report Structure

The report should have these sections.

### Summary

Include:

- total manifest batches
- batches with semantic-pass resolutions
- graphs in manifest
- graphs in processed batches
- resolution files present
- unresolved graphs within processed batches
- verdict totals for `ok`, `reorder`, `change`, and `other`

Use the phrase `Unresolved Graphs`, not `Missing`, because `Missing` is easy to
confuse with missing dependencies.

### Processed Batch Table

Include one row per processed batch with columns:

```text
Batch | Volume | Chapter | Status | Graphs | Resolutions | Unresolved Graphs |
OK | Reorder | Change | Other | Avg Confidence | Min Confidence |
Last Resolution
```

Rules:

- `Status` is `complete` when resolution count equals graph count.
- `Status` is `partial` when at least one graph lacks a matching resolution.
- `Unresolved Graphs` is `graph-*.json count - resolution-*.json count`.
- Confidence values should be averaged over resolution files that contain a
  numeric `confidence`.

### Change Candidates

Include only resolution files whose verdict is `change`.

Group rows by batch. For each row include:

```text
Graph | Resolution | Term | Current Dependencies | Proposed Dependencies |
Adds | Removes | Confidence
```

Rules:

- `Current Dependencies` comes from the matching `graph-####.json` file's
  `current_dependencies[].id`.
- `Proposed Dependencies` comes from the matching `resolution-####.json` file's
  `dependencies`.
- `Adds` is proposed dependencies minus current dependencies.
- `Removes` is current dependencies minus proposed dependencies.
- Show `(none)` for an empty dependency set.
- List the `resolution-####.json` filename for traceability.
- Keep `rationale` out of the table; the resolution filename is enough to find
  the rationale.

### Unprocessed Batches

List batches from `manifest.json` that have graph files but no
`resolution-*.json` files. Include:

```text
Batch | Volume | Chapter | Graphs
```

## Formatting

- Use GitHub-flavored Markdown tables.
- Escape pipe characters in table cells.
- Sort dependency lists alphabetically for stable diffs.
- Preserve the manifest batch order.
- Include a generated timestamp near the top.
- Mention that the apply phase has not run if no `progress.yaml`,
  `patches.yaml`, `suspicious.yaml`, or `focus-queue.yaml` files exist.

## Verification

After writing the report:

1. Read the first 50-80 lines and confirm the table headers are correct.
2. Search the report for malformed PowerShell interpolation such as `$(@` or
   `@{graph_id`; neither should appear.
3. Check `git status --short --branch` so the caller can see that only the
   report changed, unless other work was already present.
