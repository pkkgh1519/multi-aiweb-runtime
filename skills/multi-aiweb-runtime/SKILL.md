---
name: multi-aiweb-runtime
description: Use the local Multi-AI Web Runtime MCP tools from Codex. Manages prepare/start/status/wait/resume/artifacts with explicit login handling.
version: 0.5.1
author: Hermes Agent
license: MIT
metadata:
  tags: [chatgpt, browser, mcp, codex, runtime]
---

# Multi-AI Web Runtime

Use this skill when a task should be sent through the local Multi-AI Web Runtime MCP plugin instead of direct model calls.

## Core rules

- Do not bypass login, copy cookies, extract localStorage, or work around CAPTCHA/payment checks.
- Do not expose raw Oracle MCP tools, call `oracle serve`, enable remote Chrome, pass inline cookies, or allow arbitrary file paths.
- Prefer `browser_backend="oracle"` when Oracle is installed and the task benefits from Oracle's browser automation/file bundling; this plugin remains the policy and artifact gate.
- Keep Oracle provider/browser targets explicit. Default to `oracle_target="chatgpt_browser"`; use `oracle_target="gemini_browser"` only when the user asks for Gemini/Gemini browser cross-checking. API mode and provider API-key passthrough stay disabled unless separately approved.
- Use the configured Codex `playwright` MCP as the fallback live browser path when Oracle is unavailable or Codex should drive browser actions directly; keep `oracle_target` explicit there too so Gemini requests open Gemini rather than ChatGPT.
- Call `aiweb_prepare_session` before live browser runs when login/session state is uncertain.
- Use `dry_run=true` first when validating tool wiring.
- Store and inspect artifacts rather than relying on transient browser text.
- Keep external sharing and publication approval-gated.
- Treat CS WebLatch-style completion signals as optional future backend ideas, not a required v1/v2 dependency.

## Agent-style natural-language triggers

Treat Web GPT as an auxiliary agent when the user asks for outside reasoning, not as a raw text relay. Trigger this runtime for Korean or English requests such as:

- "GPT한테 물어봐"
- "GPT 프로모드로 호출해서 의견 물어봐"
- "웹 GPT한테 검색/브레인스토밍/리뷰/크로스검토 맡겨"
- "프로바이더 장애니까 ChatGPT Web으로 우회해"
- "GPT provider 장애니까 Oracle 경유로 Web GPT에 리뷰 맡겨"
- "Oracle 안전 어댑터로 파일 범위 먼저 preview하고 물어봐"
- "제미나이 브라우저 모드로 크로스검토해"
- "Gemini browser로 같은 변경사항 리뷰시켜봐"
- "상황에 맞게 프롬프트 짜서 GPT에 던져봐"
- "Ask GPT for a second opinion / review / brainstorm / cross-check."

Use Web GPT especially as a:

- search brain for broad web-style discovery and source-finding ideas
- brainstorming partner for alternatives, names, product ideas, and solution shapes
- reviewer for design, code, document, incident, and risk review
- cross-checker for assumptions, hidden failure modes, and independent second opinions

## Prompt composer policy

Do not simply forward the user's short request when context is available. First compose the prompt for the situation, then pass that composed prompt as `question` to `aiweb_run_start`.

The composed prompt should normally include:

1. **Role** — e.g. independent expert reviewer, search brain, brainstorming partner, cross-checker.
2. **Context** — current task, constraints, repo/files/artifacts, observed evidence, and what the main agent already tried.
3. **Question** — the exact decision, review target, or hypothesis set GPT should address.
4. **Output shape** — concise bullets, ranked options, risks, verification steps, or a structured review packet.
5. **Non-goals** — avoid generic advice, do not request secrets/cookies/localStorage, and do not claim actions outside the browser response.

Situation templates:

- Search/research: ask for search angles, source categories, query variants, likely authoritative references, and uncertainty.
- Brainstorming: ask for diverse options, trade-offs, constraints, and one recommended path.
- Reviewer: ask for correctness, security, regressions, tests, missing edge cases, and concrete changes.
- Cross-check: ask for assumptions, counterexamples, alternative root causes, and verification steps.
- Provider outage fallback: say the main GPT provider is degraded and Web GPT is being used as a fallback reasoning agent.

## Model/mode policy

- Default mode is **Extension Heavy**. Use it unless the user explicitly asks for Pro/프로모드/Pro Extended/pro expansion.
- Use **Pro Extended** only for explicit user requests such as "GPT 프로모드로 호출해서 의견 물어봐"; when the user asks for the highest/slowest ChatGPT browser mode, pair it with `mode_variant="heavy"`.
- Pro Extended responses can take **10 minutes or longer**; some Pro/extended-thinking runs can take **30-60 minutes**. For those runs, set `timeout_seconds=3600` or more and do not fail early just because normal runs are faster.
- Use `mode_variant` for requested thinking intensity when supported: `light`, `standard`, `extended`, or `heavy`. ChatGPT browser runs support all four. Gemini `gemini-3.1-pro` supports `standard`/`extended`; Gemini Flash and Flash-Lite support `standard` only.
- Preserve the requested mode in `mode_label` / `mode_variant` artifacts so the caller can audit which mode was intended.

## Tools

- `aiweb_prepare_session(profile_name?, dry_run?, open_browser?, browser_backend?, oracle_target?)`
  - Reports `ready`, `login_required`, `captcha_required`, `payment_required`, `user_action_required`, or `unknown`-style states.
  - For `browser_backend="oracle"`, returns a target-specific `manual_login_setup.command` using `--browser-keep-browser`; with `open_browser=true`, launches that dedicated Oracle manual-login browser setup process.
  - Default `browser_backend="playwright_mcp"`; `open_browser=true` returns a target-aware action plan for Codex's `playwright` MCP instead of launching Python Playwright.
- `aiweb_run_start(question, files?, output_name?, mode_label?, mode_variant?, dry_run?, dry_run_response?, browser_backend?, completion_backend?, live?, profile_name?, timeout_seconds?, open_browser?, repo_root?, permission_level?, dry_run_policy?, oracle_target?, oracle_model?)`
  - Starts a run and writes structured artifacts.
  - Use `browser_backend="oracle"` for the safe Oracle adapter. Set `repo_root` and `permission_level` (`safe_default`, `review`, `research`, or `elevated`). Use `dry_run_policy=true` to preview the exact files and blocked inputs before launching Oracle.
  - For Gemini browser mode set `oracle_target="gemini_browser"` and optionally `oracle_model` to one of `gemini-3.1-pro`, `gemini-3.5-flash`, or `gemini-3.1-flash-lite`. `gemini-3.1-pro` supports `mode_variant="standard"`/`"extended"` thinking; Flash and Flash-Lite support `mode_variant="standard"` only. Retired Gemini Web names fail closed.
  - Fallback live backend is `playwright_mcp`; default mode is `mode_label="Extension Heavy"`; it returns `awaiting_external_browser` plus a target-aware action plan for Codex.
- `aiweb_run_record_event(run_id, status, ...)`
  - Records externally observed Playwright MCP browser progress.
- `aiweb_run_complete(run_id, response_text, evidence?, message?)`
  - Persists the final external browser response to `response.md` and marks the run completed.
- `aiweb_run_fail(run_id, status, message, error_text?, evidence?)`
  - Persists login/CAPTCHA/payment/timeout/error states without pretending the browser run succeeded.
- `aiweb_run_status(run_id)`
  - Reads `status.json`.
- `aiweb_run_wait(run_id, timeout_seconds?)`
  - Waits for terminal state.
- `aiweb_run_resume(run_id)`
  - Returns resume guidance for blocked runs.
- `aiweb_run_artifacts(run_id)`
  - Returns artifact paths.
- `aiweb_run_list_recent(limit?)`
  - Lists recent runs.

## Recommended workflow

1. Install through the Codex plugin marketplace path rather than copying files into separate Codex roots:
   - `.\install.ps1 -DryRun`
   - `.\install.ps1`
   - Expected selector: `multi-aiweb-runtime@local-multi-aiweb-runtime`
2. Run `aiweb_prepare_session(dry_run=true)` to verify server wiring.
3. Run a dry smoke:
   - `aiweb_run_start(question="Reply with exactly OK", dry_run=true, dry_run_response="OK")`
   - `aiweb_run_wait(run_id, timeout_seconds=10)`
   - `aiweb_run_artifacts(run_id)`
4. For Oracle-backed live use, first preview the policy scope:
   - `aiweb_run_start(question="...", files=["src/*.py"], repo_root="C:/path/to/repo", permission_level="review", browser_backend="oracle", oracle_target="chatgpt_browser", live=true, dry_run_policy=true)`
   - Confirm that `oracle_scope.allowed_files` contains only intended repo-relative files and that no sensitive file is blocked unexpectedly.
5. If `aiweb_prepare_session(browser_backend="oracle")` reports `run_oracle_manual_login_setup`, initialize the target-specific profile first:
   - `aiweb_prepare_session(browser_backend="oracle", oracle_target="chatgpt_browser", open_browser=true)`
   - Complete login in the visible dedicated Oracle browser.
   - For Gemini, use `oracle_target="gemini_browser"`; the Gemini profile is isolated from ChatGPT.
6. Run Oracle only after the scope is acceptable and the profile is initialized:
   - `aiweb_run_start(question="...", files=["src/*.py"], repo_root="C:/path/to/repo", permission_level="review", browser_backend="oracle", oracle_target="chatgpt_browser", live=true, mode_label="Extension Heavy", mode_variant="heavy", timeout_seconds=3600)`
   - If the user explicitly asks for Pro/프로모드, use `mode_label="Pro Extended"`; the adapter enforces a 3600-second minimum browser timeout for that mode, and use an even larger `timeout_seconds` when the user expects more than 60 minutes.
   - For Gemini cross-checking, use `oracle_target="gemini_browser"` and `oracle_model="gemini-3.1-pro"`; prepare/login state is isolated from the ChatGPT browser target.
7. If Oracle is unavailable or Codex should drive the browser directly, verify Codex has a session-capable `playwright` MCP:
   - `codex mcp get playwright`
   - Prefer a visible/session profile config such as `--user-data-dir C:/Users/<YOU>/.codex/state/playwright-mcp/profile`, not `--headless --isolated`, when Web-provider login persistence matters.
8. Start the fallback Playwright MCP run with Extension Heavy mode:
   - `aiweb_run_start(question="...", live=true, browser_backend="playwright_mcp", mode_label="Extension Heavy")`
   - For Gemini fallback, set `oracle_target="gemini_browser"` and `oracle_model="gemini-3.1-pro"` so the returned action plan navigates to Gemini Web.
   - Use the returned `action_plan` with the `playwright` MCP.
   - Persist success with `aiweb_run_complete(run_id, response_text, evidence?)` or blockage with `aiweb_run_fail(run_id, status, message, evidence?)`.
9. Use Python Playwright only as a legacy explicit fallback:
   - `python -m pip install -e '.[browser]'`
   - `playwright install chromium`
   - `aiweb_run_start(question="...", live=true, browser_backend="persistent_profile", timeout_seconds=120)`
10. Inspect `response.md`, `events.jsonl`, and `status.json` before using the answer.

## Install layout

The plugin-native install root is:

- `%USERPROFILE%\.codex\local-marketplaces\multi-aiweb-runtime\plugins\multi-aiweb-runtime`

The local marketplace manifest lives at:

- `%USERPROFILE%\.codex\local-marketplaces\multi-aiweb-runtime\.agents\plugins\marketplace.json`

The plugin bundle contains its own `.codex-plugin\plugin.json`, generated `.mcp.json`, runtime source, server wrapper, and skill files. Runtime state is intentionally outside the plugin bundle at `%USERPROFILE%\.codex\state\multi-aiweb-runtime`.

## Artifact contract

Each run writes:

- `run.json` — run metadata and backends
- `prompt.txt` — submitted prompt
- `response.md` — final response when available
- `events.jsonl` — WebLatch-inspired status/event stream
- `status.json` — current terminal/non-terminal status

## Harness policy

Follow `references/collaboration-harness.md` for goal confirmation, decomposition, review packets, and feedback handling.

## Safety notes

- The safe Oracle backend (`browser_backend="oracle"`) uses repo-scoped file policy, target-specific `ORACLE_HOME_DIR` values, sanitized environment variables, `--engine browser`, `--browser-manual-login`, and `--browser-archive never`.
- First-time Oracle browser login requires the target-specific `manual_login_setup` command with `--browser-keep-browser`; normal Oracle runs fail closed until the dedicated profile is initialized.
- The Oracle engine is an internal implementation detail. Prefer the bundled/pinned engine wrapper for custom behavior; keep `MULTI_AIWEB_RUNTIME_ORACLE_COMMAND` as an explicitly validated emergency override only.
- Oracle target support is intentionally browser-only: `chatgpt_browser` and `gemini_browser` are allowed; provider API-key env vars are stripped; API-only or unproven Gemini models are blocked.
- Gemini browser model support is capability-driven. Do not add a model string to the adapter unless the engine has exact Web model/header/resolver support, tests, and browser-only live-smoke evidence. Unsupported explicit Gemini models must fail closed rather than falling back to another Gemini Web model.
- Gemini browser mode requires a target-specific signed-in Google/Gemini profile. Do not pass inline cookies or provider API keys; do not persist cookie values in artifacts; keep Gemini and ChatGPT profiles separated.
- On Windows, the runtime auto-detects standard Chrome/Chromium-family executable paths for Oracle browser runs. If Oracle still reports `CHROME_NOT_FOUND`, tell the user to install Chrome or restore the standard Chrome path, then retry `aiweb_prepare_session` or `aiweb_run_start`.
- Oracle policy blocks repo escapes, absolute Windows paths, home paths, `.env` files, private keys, cookie stores, and browser profile storage before launching Oracle.
- The fallback browser backend is `playwright_mcp`; Codex performs browser actions through its configured `playwright` MCP and the runtime records artifacts/status. Its action plan is target-aware for `chatgpt_browser` and `gemini_browser`.
- The direct Python Playwright backend is legacy explicit fallback only (`browser_backend="persistent_profile"` or `"python_playwright"`) and may require `.[browser]` plus `playwright install chromium`.
- The Playwright MCP completion contract is external result recording via `aiweb_run_complete` / `aiweb_run_fail`; `cdp_injected` remains available to the direct fallback path.
- `open_browser=true` in MCP-first mode returns action guidance rather than extracting browser credentials or launching a separate Python Playwright browser.
- Live completion must match the submitted prompt text and differ from the pre-submit assistant baseline before `response.md` is accepted, reducing stale-answer risk in existing conversations.
- CAPTCHA/payment/login gates are user actions, not automation targets.
- CS WebLatch can be considered later as an optional `extension_latch` backend if completion detection is unreliable.
