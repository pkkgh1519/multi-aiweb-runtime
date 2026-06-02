# Embedded Oracle Engine Single-Plugin Pattern

Use this reference when custom Oracle behavior is needed repeatedly.

## Pattern

Expose one user-facing plugin:

```text
multi-aiweb-runtime
```

Internally split responsibilities:

```text
safe adapter / MCP / artifacts / policy gates -> shell-free wrapper -> pinned Oracle engine
```

The adapter is the safety boundary. The engine is an implementation detail.

## Required properties

- Shell-free subprocess invocation.
- Adapter-controlled `--engine browser` only.
- No raw Oracle MCP tools.
- No `oracle serve`.
- No provider API-key passthrough by default.
- No remote Chrome or inline cookies.
- Target-specific profile directories.
- Engine identity and capability version persisted in artifacts.
- Unsupported models fail closed before browser execution.

## Gemini model rule

Never add a Gemini model only to the Python allowlist. First prove the engine supports the exact Web model id/header/resolver mapping and add tests that prevent fallback to another model.
