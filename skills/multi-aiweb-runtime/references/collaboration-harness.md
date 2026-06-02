# Collaboration Harness

This policy layer is adapted from the notes-style harness, but kept independent from the runtime engine.

## Goal intake

- Restate the objective in concrete output terms.
- Identify required artifacts, deadline, and approval boundaries.
- Ask only for missing information that cannot be discovered from files or tools.

## Decomposition

- Split work into small observable phases.
- Keep a run artifact for each externally meaningful ChatGPT Web query.
- Prefer dry-run validation before live browser execution.

## Review loop

For every substantial answer:

1. Inspect `status.json` and `events.jsonl`.
2. Read `response.md` fully.
3. Check whether the answer satisfies the original goal.
4. Classify feedback as accept, revise, reject, or defer.
5. Save a concise final packet with links/paths to evidence.

## Approval gates

Explicit approval is required before:

- posting externally
- sending messages as the user
- publishing files
- changing global Codex/Hermes config
- bypassing or weakening authentication/session controls

## Completion packet

Final reports should include:

- run id
- artifact directory
- tools used
- verification performed
- known limitations and next optional step
