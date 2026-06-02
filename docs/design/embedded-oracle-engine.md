# Embedded Oracle Engine Design

## Goal

Keep `multi-aiweb-runtime` as one user-facing Codex plugin while allowing a pinned/custom Oracle browser engine internally.

The plugin remains the control plane for Korean/operator UX, policy preview, repo-scoped file sharing, environment sanitization, target-specific profiles, and structured artifacts. The embedded engine is only an execution backend.

## Target architecture

```text
multi-aiweb-runtime
├─ MCP tools / Korean UX / prompt policy / artifacts
├─ safe adapter / file scope / env sanitizer / model gate
└─ embedded Oracle engine wrapper
   └─ pinned custom Oracle browser engine
```

## Boundaries

The adapter continues to block:

- raw Oracle MCP exposure;
- `oracle serve`;
- provider API engine and API-key passthrough by default;
- remote Chrome;
- inline cookies;
- cookie/localStorage extraction or persistence;
- arbitrary absolute paths, Windows drive paths, home paths, and repo escapes.

The engine wrapper is shell-free and receives only adapter-controlled flags. The adapter still appends `--engine browser`, target-specific profile flags, allowed files, and prompt text.

## Upstream Gemini model rationale

Reviewed Oracle upstream commit: `6019a19`; this repo carries a custom Gemini Web alignment fork.

The bundled fork matches the current Gemini Web picker allowlist:

```text
gemini-3.5-flash
gemini-3.1-pro
gemini-3.1-flash-lite
```

Gemini Web thinking levels are restricted to the picker surface: `standard` and `extended`. `extended` is exposed only for `gemini-3.1-pro`; Flash/Flash-Lite use `standard`.

Older upstream model strings (`gemini-3-pro`, deep-think aliases, and `gemini-2.5-*`) are retired. Unknown or retired Gemini Web strings fail closed instead of silently falling back to another model.

## Model support rule

A browser model is exposed only after engine-level support is proven:

1. exact engine model id exists;
2. Gemini Web header/selector exists;
3. resolver maps the requested string exactly;
4. CLI/run-options dry-run preserves the requested browser model before executor handoff;
5. tests prove no fallback to another model;
6. browser-only live smoke confirms requested/effective model and clean artifacts.

Until then, the safe adapter fails closed before launching the engine.

## Capability contract

The runtime records deterministic local engine capabilities. Gemini model gates read from this capability table instead of blindly passing arbitrary strings to Oracle.

Required capability fields:

```json
{
  "engine": "oracle-custom",
  "engine_version": "0.13.0-multi-aiweb-runtime.1",
  "capabilities_version": "2026-05-31",
  "browser_targets": {
    "gemini_browser": {
      "models": ["gemini-3.1-pro", "gemini-3.5-flash", "gemini-3.1-flash-lite"],
      "aliases": {"gemini": "gemini-3.1-pro"},
      "retired_models": ["gemini-3-pro", "gemini-3-pro-deep-think", "gemini-3-deep-think", "gemini-2.5-pro", "gemini-2.5-flash"],
      "default_model": "gemini-3.1-pro"
    }
  }
}
```

## Artifact metadata

Oracle-backed runs should persist engine identity in `run.json`, `status.json`, and event signals:

```json
{
  "oracle_engine": {
    "source": "bundled",
    "name": "oracle-custom",
    "version": "0.13.0-multi-aiweb-runtime.1",
    "upstream_commit": "6019a19",
    "capabilities_version": "2026-05-31"
  }
}
```

## Live discovery gate

New Gemini browser models such as browser-mode `gemini-3.1-pro` require a separate operator-approved live discovery gate because it involves a signed-in Gemini browser profile and inspection of Web model routing. No API keys are allowed. Cookie/auth values must not be stored.
