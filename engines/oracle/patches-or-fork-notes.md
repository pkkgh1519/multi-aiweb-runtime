# Multi-AI Web Runtime Oracle Fork Notes

Vendored from upstream Oracle review clone commit `6019a19`.

Local fork policy:

- The engine is called only through `multi_aiweb_runtime.oracle_engine_cli`.
- `multi-aiweb-runtime` remains the safety adapter and controls files, environment, browser target, model gate, and artifacts.
- Raw Oracle MCP and `oracle serve` are not exposed by this plugin.
- Provider API-key routes remain disabled by the adapter by default.

Local patches:

1. Gemini Web explicit unsupported model strings fail closed instead of falling back to another Gemini Web model.
   - Rationale: artifact truthfulness. A requested Gemini model must be used exactly or fail before browser execution.
   - Relevant files:
     - `src/gemini-web/executor.ts`
     - `tests/gemini-web/executor.test.ts`

2. Gemini Web model-unavailable responses fail closed instead of retrying another Gemini model.
   - Rationale: artifacts must not report the requested Gemini model when Gemini Web actually returned or attempted another model.
   - Relevant files:
     - `src/gemini-web/client.ts`
     - `tests/gemini-web/upload.test.ts`

3. Gemini Web picker is aligned to the current screenshot-backed allowlist: `gemini-3.1-pro`, `gemini-3.5-flash`, and `gemini-3.1-flash-lite`.
   - Header model ids: `e6fa609c3fa255c0` for `gemini-3.1-pro`, `56fdd199312815e2` for `gemini-3.5-flash`, and `9ec249fc9ad08861` for `gemini-3.1-flash-lite`.
   - `gemini-3.1-pro` supports `standard` and `extended`; Flash/Flash-Lite support `standard` only.

4. Oracle CLI/run-options Gemini normalization preserves supported Gemini Web models and rejects unsupported explicit Gemini model strings in browser mode.
   - Rationale: executor-level effective-model checks cannot catch a model that was already normalized before execution.
   - Relevant files:
     - `src/cli/options.ts`
     - `src/cli/browserConfig.ts`
     - `tests/cli/options.test.ts`
     - `tests/cli/browserConfig.test.ts`
     - `tests/runOptions.test.ts`
     - `tests/cli/integrationCli.test.ts`
