# ChatGPT Pro Web Reliability Design

## Scope

Stabilize the existing web-based ChatGPT Pro path in `multi-aiweb-runtime` without replacing it with API or Codex-auth model calls. The first implementation phase targets only `oracle_target="chatgpt_browser"` with `mode_label="Pro Extended"`. Gemini Web remains a later phase behind a separate discovery and validation gate.

## Goals

- Make ChatGPT Pro browser runs fail with classified, resumable states instead of opaque failures.
- Keep Oracle as the primary automated web backend for Pro runs.
- Keep Playwright MCP as an operator-visible observation and recovery fallback, not the primary automation path.
- Preserve current security boundaries: no token extraction, no cookie copying, no localStorage scraping, no login bypass, no payment or CAPTCHA bypass.
- Improve artifacts so a run records what happened, why it failed, and whether it can be resumed.

## Non-goals

- No OpenAI API or `codex exec` backend for Pro substitution.
- No direct use or parsing of `~/.codex/auth.json`.
- No Gemini Web implementation in this phase.
- No raw Oracle MCP or `oracle serve` exposure.
- No broad rewrite of the bundled Oracle engine.
- No automatic interaction with CAPTCHA, payment, or account security gates.

## Existing architecture

The runtime has three relevant layers:

1. Python MCP control plane: `multi_aiweb_runtime/src/chatgpt_web_runtime/runtime.py`, `oracle_adapter.py`, `oracle_client.py`, and `mcp_server.py` own run creation, policy preview, status mapping, artifacts, and MCP tools.
2. Oracle browser engine: `engines/oracle/src/browser/*` owns Chrome lifecycle, ChatGPT DOM interaction, model selection, prompt submission, thinking observation, response capture, and reattach.
3. Playwright MCP fallback: `browser_backend="playwright_mcp"` returns an action plan and requires explicit `aiweb_run_complete` or `aiweb_run_fail` recording.

The reliability work should keep this split: Python remains the safety cockpit and artifact contract; Oracle remains the primary browser automation engine; Playwright MCP remains a fallback surface for human-observable recovery.

## Reliability state machine

A ChatGPT Pro run should move through explicit states:

```text
PREFLIGHT
  -> PROFILE_LOCKED
  -> LOGIN_READY
  -> MODEL_READY
  -> PROMPT_SUBMITTED
  -> THINKING_OBSERVED
  -> RESPONSE_CAPTURED
  -> VERIFIED_COMPLETION
```

Terminal success requires `VERIFIED_COMPLETION`. Failures should be classified into one of these states:

```text
PROFILE_BUSY
LOGIN_REQUIRED
MODEL_SELECTOR_UNAVAILABLE
PRO_NOT_AVAILABLE
PRO_EFFORT_UNCONFIRMED
PROMPT_NOT_SUBMITTED
LONG_THINKING_IN_PROGRESS
REATTACH_REQUIRED
CAPTURE_INCOMPLETE
USER_ACTION_REQUIRED
```

`failed` remains available only for non-classified internal errors after redaction.

## Component design

### Python control plane

Add a ChatGPT Pro reliability adapter layer around the current Oracle call path. The layer should not duplicate DOM automation. It should prepare inputs, enforce safety rules, map Oracle/engine outcomes into structured states, and expose recovery guidance.

Responsibilities:

- Force ChatGPT Pro runs through `oracle_target="chatgpt_browser"`.
- Normalize Pro mode to `oracle_model="gpt-5.5-pro"` and a requested thinking effort.
- Preserve the existing one-hour minimum timeout for Pro Extended runs.
- Record `prompt_hash`, `oracle_target`, requested model, requested thinking effort, and classified run state in `run.json`.
- Prevent terminal status overwrite from `aiweb_run_complete` or recovery tools.
- Require stronger evidence for external Playwright completion: run id, provider, URL, conversation id or URL, prompt hash/equivalent correlation, non-empty response text, and final status.

### Oracle browser engine

The first phase should make targeted changes in existing Oracle browser modules only where current failure evidence points:

- `actions/modelSelection.ts`: improve selector discovery and model picker failure evidence.
- `actions/thinkingTime.ts`: keep fail-closed behavior for Pro Extended effort when it cannot be confirmed.
- `profileState.ts` and `chromeLifecycle.ts`: improve stale DevTools port and profile ownership diagnostics.
- `sessionRunner.ts` and reattach modules: expose long-running thinking and incomplete capture as resumable states.

The Oracle engine should continue to leave the browser/profile visible and recoverable when a Pro run is still thinking or capture is incomplete.

### Playwright MCP fallback

Playwright MCP should remain a fallback plan that is generated when Oracle cannot proceed automatically or when an operator needs to inspect a live tab.

Fallback requirements:

- It must not read cookies, localStorage, browser profile files, or `auth.json`.
- It must not mark a run complete unless completion evidence matches the pending run.
- It should record partial observations through `aiweb_run_record_event` before `aiweb_run_complete` or `aiweb_run_fail`.
- It should prefer `user_action_required` or `partial_thinking_timeout` over false success when Pro is still thinking.

## Data flow

```text
MCP aiweb_run_start
  -> validate ChatGPT Pro request
  -> create run artifacts
  -> compute prompt hash
  -> Oracle policy and scope validation
  -> Oracle browser command
  -> browser profile lock and preflight
  -> ChatGPT login/composer/model/effort checks
  -> prompt submit
  -> thinking and response observation
  -> response capture or resumable failure
  -> Python status mapping
  -> artifact write
```

Artifacts should include enough structured evidence for auditing without storing secrets in new metadata fields:

- `run.json`: requested target/model/thinking effort, prompt hash, state history summary, recoverability flag, Oracle engine identity.
- `status.json`: current classified state, message, next action, and resume guidance when applicable.
- `events.jsonl`: redacted event records with model label, URL/conversation metadata, and signals.
- `response.md`: final answer only after verified completion or successful salvage from the output file.
- `oracle.stdout.log` / `oracle.stderr.log`: redacted logs.

## Error handling

### Profile and browser lifecycle

- If a profile lock is held by a live Oracle-owned process, classify as `PROFILE_BUSY` and return the owning pid/session hint.
- If a DevTools port exists but is unreachable, clean stale state only when safe and classify the first failed attempt as recoverable.
- If Chrome is using the target profile outside Oracle control, do not terminate it automatically. Classify as `PROFILE_BUSY` or `USER_ACTION_REQUIRED` with clear close/retry guidance.

### Login and account gates

- If ChatGPT login is absent, classify as `LOGIN_REQUIRED` and point to `aiweb_prepare_session(... open_browser=true)`.
- If CAPTCHA, payment, or account security gates appear, classify as `USER_ACTION_REQUIRED` and leave the browser visible.
- Do not attempt to bypass gates.

### Model and thinking effort

- If the model selector button is missing, classify as `MODEL_SELECTOR_UNAVAILABLE` and record non-secret DOM debug evidence.
- If Pro is unavailable for the account, classify as `PRO_NOT_AVAILABLE`.
- If Pro Extended effort cannot be confirmed, classify as `PRO_EFFORT_UNCONFIRMED` and do not submit the prompt.

### Long-running Pro runs

- If the prompt is submitted and ChatGPT is still thinking at timeout, classify as `LONG_THINKING_IN_PROGRESS` or `REATTACH_REQUIRED` instead of generic timeout.
- If partial response capture is incomplete but conversation metadata exists, classify as `CAPTURE_INCOMPLETE` with resume instructions.
- If the output file appears after subprocess timeout, keep the existing salvage-as-success behavior.

## Security and artifact safety

The reliability work must not weaken the existing browser-auth boundary.

- Do not read or expose `~/.codex/auth.json`.
- Do not extract or copy cookies or localStorage.
- Do not store browser profile files in artifacts.
- Redact secrets in stdout, stderr, events, evidence, status messages, prompt-adjacent metadata, and response-adjacent metadata.
- Extend the redaction corpus for API keys, bearer tokens, GitHub tokens, cookie headers, quoted JSON token fields, and high-risk credential-like spans.
- Document that user prompts and web responses may be stored locally as run artifacts unless future configuration disables that storage.

## Implementation slices

### Slice 1: Artifact and manifest hygiene

- Fix plugin `interface.defaultPrompt` warnings by keeping at most three prompts under the Codex prompt-length limit.
- Add prompt hash and non-secret run metadata fields.
- Prevent terminal run completion overwrite.
- Add focused Python tests for status overwrite and evidence validation.

### Slice 2: ChatGPT Pro preflight contract

- Add Pro-specific preflight status mapping in the Python control plane.
- Surface login, profile, selector, Pro availability, and effort confirmation states.
- Add tests using fake Oracle client outputs and known failure strings.

### Slice 3: Oracle selector and thinking diagnostics

- Harden ChatGPT model selector diagnostics without broad DOM rewrites.
- Keep Pro Extended fail-closed if effort cannot be verified.
- Add focused Oracle engine tests for selector missing, Pro missing, and effort unconfirmed outcomes.

### Slice 4: Reattach and long-running state mapping

- Map Oracle long-thinking and incomplete-capture cases into resumable MCP states.
- Improve `aiweb_run_resume` guidance with Oracle session id, conversation URL when available, and Playwright observation fallback.
- Add tests for timeout-with-thinking, incomplete capture, and output-file salvage.

### Slice 5: Live smoke gate

- Run a tiny ChatGPT Pro prompt-only live smoke after unit tests pass and operator login is ready.
- Validate artifacts: `response.md`, `status.json`, `run.json`, `events.jsonl`, `oracle.stdout.log`, `oracle.stderr.log`.
- Treat account gates, selector changes, or Pro unavailability as classified outcomes, not failed implementation.

## Verification plan

Python control-plane checks:

```powershell
$env:PYTHONPATH='multi_aiweb_runtime\src'
python -m pytest -q tests
python -m compileall -q multi_aiweb_runtime tests
```

Plugin and installer checks:

```powershell
python scripts\validate_portability.py
python scripts\validate_plugin.py .
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -DryRun -SkipOracleDeps -SkipMarketplaceRegistration -SkipPluginInstall
```

Oracle engine checks for TypeScript/browser changes:

```powershell
cd engines\oracle
pnpm vitest run tests/browser/modelSelection.test.ts tests/browser/thinkingTime.test.ts tests/browser/reattach.test.ts tests/browser/reattach.e2e.test.ts tests/cli/browserConfig.test.ts
pnpm run build
```

Live smoke checks require explicit operator readiness because they use a signed-in ChatGPT browser profile.

## Rollout criteria

Phase 1 is complete when all of the following are true:

- ChatGPT Pro runs have classified status outcomes instead of opaque failures.
- Pro Extended effort is confirmed before prompt submission or the run fails closed.
- Profile busy, login required, selector unavailable, Pro unavailable, still thinking, and incomplete capture are separately observable.
- `aiweb_run_resume` gives actionable recovery guidance for resumable cases.
- Playwright MCP completion cannot overwrite terminal runs or complete the wrong pending run without evidence.
- No new path reads or stores browser credentials, cookies, localStorage, or `auth.json`.
- Focused Python and Oracle engine tests pass.

## Gemini follow-up gate

Gemini Web work starts only after ChatGPT Pro phase 1 is stable. Gemini requires a separate design/update because model availability, thinking controls, and DOM provider behavior differ from ChatGPT Pro. The existing Gemini model discovery design remains the reference for that later phase.
