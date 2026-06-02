# Oracle Gemini Web Model Gating

Gemini API support is not Gemini Web/browser support.

Before exposing a Gemini browser model, check the engine has all of these:

1. `GeminiWebModelId` entry.
2. Gemini Web model header/selector entry.
3. Resolver mapping for the requested string and aliases.
4. Tests proving unsupported explicit Gemini model strings do not fall back to another Gemini Web model.
5. CLI/run-options boundary tests proving `--engine browser --model <model> --dry-run summary` preserves supported Gemini Web models and rejects unsupported explicit Gemini strings.
6. Tests proving model-unavailable responses do not fall back to a different Gemini model.
7. Browser-only live smoke with requested/effective model recorded.

Current safe browser models:

```text
gemini-3.1-pro          standard, extended
gemini-3.5-flash        standard
gemini-3.1-flash-lite   standard
```

Current retired models:

```text
gemini-3-pro
gemini-3-pro-deep-think
gemini-3-deep-think
gemini-2.5-pro
gemini-2.5-flash
```

The adapter must fail before launching Oracle when the requested model is unknown or retired. During execution, the engine must also fail closed if Gemini Web reports the requested model as unavailable; it must not silently retry another Gemini Web model while artifacts keep the original request.
