# Multi-AI Web Runtime Design and Roadmap

## Goal

Build a local MCP-style plugin that lets Windows Codex ask supported AI web targets as helper agents with structured artifacts, explicit login handling, and policy-gated file sharing.

## Current architecture

The runtime is the control plane. Browser automation is delegated to one of three backends:

1. `oracle` — preferred safe adapter when Oracle is installed. Oracle performs browser/file-bundling work; this plugin owns scope policy, environment isolation, and artifacts.
2. `playwright_mcp` — fallback path where Codex drives the configured Playwright MCP and records the result through `aiweb_run_complete` / `aiweb_run_fail`.
3. `persistent_profile` / `python_playwright` — legacy direct Python Playwright fallback kept for rollback while Oracle is proven in real use.

## Completed

- Dry-run runtime and artifacts.
- `prepare_session` state contract for login/user-action handling.
- Path-safe run/profile/output identifiers.
- Codex local marketplace packaging.
- Agent-style AI web prompt policy: search brain, brainstorming partner, reviewer, and cross-checker.
- Default mode label: `Extension Heavy`; explicit-only `Pro Extended` with long timeout guidance.
- MCP-first Playwright fallback with externally recorded completion artifacts.
- Optional direct Python Playwright fallback with stale-response guards.
- Safe Oracle adapter:
  - repo-scoped file policy,
  - `safe_default` / `review` / `research` / `elevated` permission levels,
  - policy preview via `dry_run_policy=true`,
  - explicit browser targets for ChatGPT and Gemini,
  - target-specific `ORACLE_HOME_DIR` values under runtime state,
  - API-key/remote/client-factory environment sanitization,
  - shell-free Oracle CLI invocation,
  - `--engine browser`, `--browser-manual-login`, and `--browser-archive never`,
  - Gemini browser model allowlist with retired/unproven Gemini Web models blocked,
  - response/status/event integration with the existing artifact contract.

## Explicit non-goals

- No login bypass.
- No cookie/localStorage extraction.
- No `oracle serve` or raw Oracle MCP exposure.
- No remote Chrome or inline-cookie forwarding.
- No Oracle API engine or provider API-key passthrough by default.
- No arbitrary absolute file paths, Windows drive paths, home paths, or repo escapes.
- No automatic CAPTCHA/payment handling.
- No automatic edit of global Codex/Hermes config without explicit operator approval.

## Current deletion/deprecation posture

Removed:

- `src/chatgpt_web_runtime/completion.py` — unused abstraction after runtime/external completion paths settled.

Deprecated but retained for rollback until Oracle live smoke proves stable:

- `src/chatgpt_web_runtime/live_browser.py`
- `src/chatgpt_web_runtime/completion_cdp.py`
- `src/chatgpt_web_runtime/browser_session.py`
- `tests/test_live_browser.py`
- `tests/test_runtime_live.py`
- `browser` optional dependency in `pyproject.toml`

## Next roadmap

### v0.4.x — Windows Oracle/Gemini pilot and embedded engine foundation

- Keep `multi-aiweb-runtime` as the single user-facing plugin; the Python runtime remains the safety cockpit and the Oracle engine becomes an internal implementation detail.
- Add an embedded/pinned Oracle engine wrapper so the runtime can use a custom engine without exposing raw Oracle CLI/MCP surfaces.
- Record local engine identity and capability version in Oracle run artifacts.
- Replace hardcoded Gemini browser gates with deterministic engine capabilities.
- Keep unsupported Gemini Web models fail-closed: only the screenshot-backed Web allowlist (`gemini-3.1-pro`, `gemini-3.5-flash`, `gemini-3.1-flash-lite`) is exposed, and each model must have exact Web header/resolver tests plus browser-only live-smoke proof before being treated as supported. Model-unavailable responses must not silently fall back to another Gemini model.
- Install or verify the bundled/wrapper Oracle path under Windows Codex.
- Run `aiweb_run_start(... browser_backend="oracle", dry_run_policy=true)` on a small repo-scoped file set.
- Run a tiny ChatGPT Oracle browser prompt with no sensitive files.
- Run `aiweb_prepare_session(browser_backend="oracle", oracle_target="gemini_browser", open_browser=true)` and complete Gemini login manually if needed.
- Run a tiny Gemini browser prompt with `oracle_target="gemini_browser"` and `oracle_model="gemini-3.1-pro"`.
- Confirm `response.md`, `status.json`, `events.jsonl`, `run.json.oracle_scope`, and `run.json.oracle_engine` are correct.
- Confirm first-time Oracle login remains manual and isolated per browser target under runtime state.
- See `docs/design/embedded-oracle-engine.md` for the full single-plugin design.

### v0.5 — Fallback cleanup decision

After a successful Windows Oracle pilot:

- Either keep Python Playwright as documented legacy fallback, or remove the direct fallback stack listed above.
- If removed, delete the `browser` optional dependency and simplify README/skill safety notes.
- Keep Playwright MCP fallback unless it becomes clearly redundant for operator workflows.

### v0.6 — prompt contract hardening

- Persist a structured prompt contract for important AI web delegations: role, goal, done means, context, side-effect boundary, and output shape.
- Add review-state separation so callers can distinguish “response arrived” from “task satisfied.”
