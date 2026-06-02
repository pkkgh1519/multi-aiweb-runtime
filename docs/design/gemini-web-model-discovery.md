# Gemini Web Model Discovery Gate

## Purpose

Discover whether a Gemini Web account exposes unproven models such as browser-mode `gemini-3.1-pro`, and identify exact Web model routing evidence before the safe adapter can expose them.

## Approval boundary

This gate requires fresh operator approval before execution because it uses a signed-in Gemini browser profile and may inspect browser/Web request routing.

Allowed:

- browser-only Gemini Web session;
- target-specific manual-login profile;
- non-secret structural model selector/header evidence;
- redacted notes about request shape.

Forbidden:

- `GEMINI_API_KEY` or `GOOGLE_API_KEY`;
- Oracle API engine;
- cookie/localStorage export;
- persisting cookie/auth/header values;
- remote Chrome;
- inline cookies;
- guessing model headers.

## Required evidence for a new model

1. The model is visible/selectable in the Gemini Web UI for the target account, or an equivalent Web-only selector is observed.
2. The request contains a distinct model id/header/selector for the model.
3. The captured evidence is redacted and contains no cookie/auth values.
4. The Oracle fork has a `GeminiWebModelId`, `MODEL_HEADERS` entry, resolver mapping, and tests.
5. A browser-only live smoke records requested and effective model as the same value.
6. `run.json`, `status.json`, `events.jsonl`, and `response.md` contain clean artifacts and no secrets.

## Stop rules

Stop and report without implementing adapter exposure if:

- the model is not visible in Gemini Web;
- the model header cannot be identified without storing sensitive data;
- the Web route falls back to another model;
- CAPTCHA/payment/security gates block the browser session;
- any evidence would require API keys or remote browser services.

## Current status

- `gemini-3.1-flash-lite`, `gemini-3.5-flash`, and `gemini-3.1-pro`: current screenshot-backed Gemini Web picker allowlist exposed by this fork.
- `gemini-3.1-pro` supports `standard` and `extended` thinking levels.
- `gemini-3.5-flash` and `gemini-3.1-flash-lite` support `standard` thinking only.
- Retired upstream Gemini Web strings remain blocked so artifacts cannot claim a removed model or silent fallback.
