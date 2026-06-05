# ChatGPT Pro Web Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ChatGPT Pro browser runs in `multi-aiweb-runtime` fail with classified, resumable states instead of opaque browser failures.

**Architecture:** Keep Python as the MCP safety cockpit and artifact owner, keep bundled Oracle as the primary ChatGPT Pro browser automation engine, and keep Playwright MCP as an evidence-checked observation/recovery fallback. Implement the work as small test-first slices: manifest hygiene, artifact safety, run completion guards, Pro failure classification, resume guidance, Oracle selector diagnostics, and a final live-smoke gate.

**Tech Stack:** Python 3, FastMCP-compatible MCP tools, pytest/unittest, TypeScript Oracle browser engine, Vitest, PowerShell validation commands on Windows.

---

## Source specification

- `docs/superpowers/specs/2026-06-04-chatgpt-pro-web-reliability-design.md`

## File structure

- Modify `.codex-plugin/plugin.json`
  - Owns Codex-visible plugin metadata and default prompts.
  - First slice fixes current `interface.defaultPrompt` warnings before behavioral work starts.
- Modify `multi_aiweb_runtime/src/chatgpt_web_runtime/redaction.py`
  - Owns artifact/log/evidence redaction patterns.
  - Expand the secret corpus and expose `contains_secret_risk()` and `redact_nested()`.
- Modify `multi_aiweb_runtime/src/chatgpt_web_runtime/event_model.py`
  - Owns event payload serialization.
  - Redact event text and signal payloads before JSONL persistence.
- Modify `multi_aiweb_runtime/src/chatgpt_web_runtime/runtime.py`
  - Owns MCP run lifecycle, artifacts, external Playwright completion, status, wait, resume, and run metadata.
  - Add prompt hashes, terminal overwrite prevention, completion evidence checks, and classified resume guidance.
- Modify `multi_aiweb_runtime/src/chatgpt_web_runtime/oracle_adapter.py`
  - Owns Oracle command result mapping into runtime status.
  - Add classification for ChatGPT Pro failure messages and resumable outcomes.
- Modify `multi_aiweb_runtime/src/chatgpt_web_runtime/oracle_client.py`
  - Owns Oracle subprocess command building, environment sanitization, manual-login setup launch, and timeout salvage.
  - Stop writing child manual-login stdout/stderr directly to persistent logs.
- Modify `tests/test_prompt_only_and_target.py`
  - Existing Python-side focused test file.
  - Add tests for prompt hash metadata, terminal overwrite guard, evidence validation, redaction, Pro classification, and manual-login log safety.
- Modify `engines/oracle/src/browser/actions/modelSelection.ts`
  - Owns ChatGPT model picker selection and selector failure messages.
  - Add structured stage markers to missing-selector errors without broad DOM rewrites.
- Modify `engines/oracle/src/browser/actions/thinkingTime.ts`
  - Owns ChatGPT thinking effort selection.
  - Preserve fail-closed Pro Extended behavior and make the failure stage easy for Python to classify.
- Modify `engines/oracle/tests/browser/modelSelection.test.ts`
  - Add focused Vitest coverage for the structured model selector failure marker.
- Modify `engines/oracle/tests/browser/thinkingTime.test.ts`
  - Add focused Vitest coverage for the structured Pro Extended effort failure marker.
- Create: `engines/oracle/tests/browser/reliabilityMarkers.test.ts`
  - Verifies real Oracle browser lifecycle modules expose classifiable reliability markers.
- Modify `engines/oracle/src/browser/profileState.ts`
  - Adds classifiable profile-busy and stale DevTools diagnostics.
- Modify `engines/oracle/src/browser/chromeLifecycle.ts`
  - Adds classifiable profile/DevTools reuse diagnostics.
- Modify `engines/oracle/src/cli/sessionRunner.ts`
  - Adds classifiable long-thinking and incomplete-capture markers emitted by real timeout/reattach paths.
- Modify `README.md` and `SECURITY.md`
  - Document local artifact storage, prompt/response retention, and the no-token-extraction boundary.

## Implementation tasks

### Task 1: Plugin manifest prompt hygiene

**Files:**
- Modify: `.codex-plugin/plugin.json`

- [ ] **Step 1: Inspect the current default prompts**

Run:

```powershell
python - <<'PY'
import json
from pathlib import Path
p = Path('.codex-plugin/plugin.json')
data = json.loads(p.read_text(encoding='utf-8'))
for i, prompt in enumerate(data['interface']['defaultPrompt']):
    print(i, len(prompt), prompt)
PY
```

Expected: more than three prompts or prompts longer than 128 characters are printed.

- [ ] **Step 2: Replace `interface.defaultPrompt` with exactly three short prompts**

Use this value:

```json
[
  "GPT Pro web review via Oracle. Use Pro Extended only when explicitly requested.",
  "Prepare the ChatGPT web profile and report login, Pro, or CAPTCHA blockers.",
  "Run an AI web dry run and show artifact paths before sending files."
]
```

- [ ] **Step 3: Validate prompt count and length**

Run:

```powershell
python - <<'PY'
import json
from pathlib import Path
prompts = json.loads(Path('.codex-plugin/plugin.json').read_text(encoding='utf-8'))['interface']['defaultPrompt']
assert len(prompts) <= 3, len(prompts)
assert all(len(p) <= 128 for p in prompts), [(len(p), p) for p in prompts]
print('defaultPrompt ok')
PY
```

Expected: `defaultPrompt ok`.

- [ ] **Step 4: Commit**

```powershell
git add .codex-plugin/plugin.json
git commit -m "fix: shorten plugin default prompts"
```

### Task 2: Artifact-safe redaction baseline

**Files:**
- Modify: `multi_aiweb_runtime/src/chatgpt_web_runtime/redaction.py`
- Modify: `multi_aiweb_runtime/src/chatgpt_web_runtime/event_model.py`
- Modify: `tests/test_prompt_only_and_target.py`

- [ ] **Step 1: Add failing redaction tests**

Append these tests to `tests/test_prompt_only_and_target.py` before the `if __name__ == "__main__"` block:

```python
class RedactionTests(unittest.TestCase):
    def test_redacts_common_secret_shapes(self) -> None:
        from chatgpt_web_runtime.redaction import contains_secret_risk, redact

        samples = [
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
            "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz1234567890",
            "github=ghp_abcdefghijklmnopqrstuvwxyz1234567890",
            "Cookie: __Secure-next-auth.session-token=sensitive-cookie-value",
            '{"access_token":"abcdefghijklmnopqrstuvwxyz1234567890"}',
        ]
        for sample in samples:
            self.assertTrue(contains_secret_risk(sample), sample)
            redacted = redact(sample)
            self.assertNotIn("abcdefghijklmnopqrstuvwxyz", redacted)
            self.assertNotIn("sensitive-cookie-value", redacted)
            self.assertIn("[REDACTED", redacted)

    def test_runtime_events_are_redacted_before_jsonl(self) -> None:
        from chatgpt_web_runtime.event_model import RuntimeEvent

        event = RuntimeEvent(
            event_id=1,
            run_id="redact-smoke",
            status="done",
            user_text="OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz1234567890",
            assistant_text="Cookie: __Secure-next-auth.session-token=sensitive-cookie-value",
            signals={"auth": "Bearer abcdefghijklmnopqrstuvwxyz123456"},
        )

        payload = json.dumps(event.to_dict(), ensure_ascii=False)
        self.assertNotIn("sk-proj-abcdefghijklmnopqrstuvwxyz", payload)
        self.assertNotIn("sensitive-cookie-value", payload)
        self.assertNotIn("Bearer abcdefghijklmnopqrstuvwxyz", payload)
        self.assertIn("[REDACTED", payload)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='multi_aiweb_runtime\src'
python -m pytest -q tests/test_prompt_only_and_target.py -k redacts
```

Expected: failure because `contains_secret_risk` is not defined or event JSON is not redacted.

- [ ] **Step 3: Replace `redaction.py` with expanded redaction helpers**

Use this implementation:

```python
from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|session[_-]?token)\s*[=:]\s*)['\"]?[A-Za-z0-9._~+/=-]{12,}['\"]?"),
    re.compile(r"(?i)(\"(?:access_token|refresh_token|id_token|session_token)\"\s*:\s*\")[^\"]{8,}(\")"),
    re.compile(r"(?i)(cookie\s*:\s*)[^\r\n]{8,}"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
)


def redact(text: str | None) -> str:
    if not text:
        return ""
    redacted = str(text)
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(_replace_secret_match, redacted)
    return redacted


def contains_secret_risk(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def redact_nested(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {redact(str(key)): redact_nested(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_nested(item) for item in value]
    if isinstance(value, tuple):
        return [redact_nested(item) for item in value]
    return value


def _replace_secret_match(match: re.Match[str]) -> str:
    groups = match.groups()
    if len(groups) == 2 and groups[1] == '"':
        return f"{groups[0]}[REDACTED_SECRET]{groups[1]}"
    if groups:
        return f"{groups[0]}[REDACTED_SECRET]"
    return "[REDACTED_SECRET]"
```

- [ ] **Step 4: Update `event_model.py` to redact event payloads**

Add:

```python
from .redaction import redact, redact_nested
```

Update `RuntimeEvent.to_dict()` in place. Preserve the existing camelCase schema and wrap the current values with redaction:

```python
return {
    "eventId": self.event_id,
    "runId": self.run_id,
    "status": self.status,
    "url": redact(self.url),
    "title": redact(self.title),
    "conversationId": redact(self.conversation_id),
    "tabId": self.tab_id,
    "pageSessionId": redact(self.page_session_id),
    "userText": redact(self.user_text),
    "assistantText": redact(self.assistant_text),
    "userTextHash": self.user_text_hash,
    "assistantTextHash": self.assistant_text_hash,
    "modelLabel": redact(self.model_label),
    "errorText": redact(self.error_text),
    "observedAt": self.observed_at,
    "signals": redact_nested(self.signals or {}),
}
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='multi_aiweb_runtime\src'
python -m pytest -q tests/test_prompt_only_and_target.py -k redacts
```

Expected: selected redaction tests pass.

- [ ] **Step 6: Commit**

```powershell
git add multi_aiweb_runtime/src/chatgpt_web_runtime/redaction.py multi_aiweb_runtime/src/chatgpt_web_runtime/event_model.py tests/test_prompt_only_and_target.py
git commit -m "fix: redact runtime event artifacts"
```

### Task 3: Prompt hash metadata and terminal completion guard

**Files:**
- Modify: `multi_aiweb_runtime/src/chatgpt_web_runtime/runtime.py`
- Modify: `tests/test_prompt_only_and_target.py`

- [ ] **Step 1: Add failing tests for prompt hash and terminal overwrite**

Append these tests:

```python
class RuntimeCompletionGuardTests(unittest.TestCase):
    def test_start_run_records_prompt_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
            result = runtime.start_run(question="hash me", dry_run=True)
            run_json = Path(result["artifact_paths"]["run"])
            payload = json.loads(run_json.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["prompt_hash"]), 64)
            self.assertEqual(payload["prompt_hash_algorithm"], "sha256")
            self.assertEqual(payload["state_history"], [])
            self.assertFalse(payload["recoverable"])

    def test_complete_run_rejects_terminal_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
            result = runtime.start_run(question="already done", dry_run=True)
            with self.assertRaisesRegex(ValueError, "terminal"):
                runtime.complete_run(result["run_id"], response_text="overwrite")

    def test_complete_run_rejects_all_existing_terminal_statuses(self) -> None:
        terminal_statuses = ("user_action_required", "watch_lost", "policy_preview", "policy_blocked", "cancelled")
        for terminal_status in terminal_statuses:
            with tempfile.TemporaryDirectory() as tmp:
                runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
                result = runtime.start_run(question=f"terminal {terminal_status}", live=False)
                artifacts = runtime._artifacts(result["run_id"])
                status = json.loads(artifacts.status_json.read_text(encoding="utf-8"))
                status.update({"status": terminal_status, "phase": terminal_status.upper()})
                artifacts.status_json.write_text(json.dumps(status), encoding="utf-8")

                with self.assertRaisesRegex(ValueError, "terminal"):
                    runtime.complete_run(result["run_id"], response_text="overwrite")

    def test_status_updates_append_state_history_and_recoverability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
            result = runtime.start_run(question="history", dry_run=True)
            artifacts = runtime._artifacts(result["run_id"])

            runtime._write_status_and_update_run(
                artifacts,
                {
                    "run_id": result["run_id"],
                    "status": "running",
                    "phase": "REATTACH_REQUIRED",
                    "updated_at": "2026-06-05T00:00:00+00:00",
                },
            )

            run_payload = json.loads(artifacts.run_json.read_text(encoding="utf-8"))
            self.assertTrue(run_payload["recoverable"])
            self.assertEqual(run_payload["state_history"][-1]["status"], "running")
            self.assertEqual(run_payload["state_history"][-1]["phase"], "REATTACH_REQUIRED")
```

If needed, add `import json`.

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='multi_aiweb_runtime\src'
python -m pytest -q tests/test_prompt_only_and_target.py -k "prompt_hash or terminal_overwrite"
```

Expected: failure because prompt hash metadata and terminal overwrite protection do not exist yet.

- [ ] **Step 3: Add hash and terminal helpers to `runtime.py`**

Add:

```python
import hashlib
```

Reuse the existing `status_is_terminal()` imported from `chatgpt_web_runtime.state`; do not create a second terminal status set.

Add methods inside `ChatGptWebRuntime`:

```python
    @staticmethod
    def _prompt_hash(question: str) -> str:
        return hashlib.sha256(question.encode("utf-8")).hexdigest()

    def _assert_run_not_terminal(self, artifacts: RunArtifacts) -> None:
        if not artifacts.status_json.exists():
            return
        status_payload = json.loads(artifacts.status_json.read_text(encoding="utf-8"))
        status = str(status_payload.get("status") or "")
        if status_is_terminal(status):
            raise ValueError(f"Cannot update terminal run status: {status}")

    @staticmethod
    def _status_payload_recoverable(status_payload: dict[str, Any]) -> bool:
        status = str(status_payload.get("status") or "")
        phase = str(status_payload.get("phase") or "")
        if status == "running":
            return True
        return phase in {
            "PROFILE_BUSY",
            "LOGIN_REQUIRED",
            "MODEL_SELECTOR_UNAVAILABLE",
            "PRO_NOT_AVAILABLE",
            "PRO_EFFORT_UNCONFIRMED",
            "PROMPT_NOT_SUBMITTED",
            "LONG_THINKING_IN_PROGRESS",
            "REATTACH_REQUIRED",
            "CAPTURE_INCOMPLETE",
            "USER_ACTION_REQUIRED",
        }
```

- [ ] **Step 4: Store prompt hash and state metadata in `run_payload`**

Add these fields in `start_run`:

```python
"prompt_hash": self._prompt_hash(question),
"prompt_hash_algorithm": "sha256",
"state_history": [],
"recoverable": False,
```

- [ ] **Step 5: Update `_write_status_and_update_run` to append state history**

Inside `_write_status_and_update_run`, when `run_payload` exists, append a compact state history entry and update the recoverability flag:

```python
history = list(run_payload.get("state_history") or [])
history.append(
    {
        "status": status_payload.get("status"),
        "phase": status_payload.get("phase"),
        "updated_at": status_payload.get("updated_at"),
    }
)
run_payload.update(
    {
        "status": status_payload.get("status"),
        "phase": status_payload.get("phase"),
        "updated_at": status_payload.get("updated_at"),
        "state_history": history[-20:],
        "recoverable": self._status_payload_recoverable(status_payload),
    }
)
```

- [ ] **Step 6: Guard `complete_run` and `fail_run`**

At the start of both methods, after resolving artifacts, call:

```python
self._assert_run_not_terminal(artifacts)
```

- [ ] **Step 7: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='multi_aiweb_runtime\src'
python -m pytest -q tests/test_prompt_only_and_target.py -k "prompt_hash or terminal_overwrite"
```

Expected: selected tests pass.

- [ ] **Step 8: Commit**

```powershell
git add multi_aiweb_runtime/src/chatgpt_web_runtime/runtime.py tests/test_prompt_only_and_target.py
git commit -m "feat: guard terminal runtime completion"
```

### Task 4: Evidence-checked Playwright MCP completion

**Files:**
- Modify: `multi_aiweb_runtime/src/chatgpt_web_runtime/runtime.py`
- Modify: `tests/test_prompt_only_and_target.py`

- [ ] **Step 1: Add failing external completion evidence tests**

Append:

```python
class ExternalCompletionEvidenceTests(unittest.TestCase):
    def test_complete_run_requires_evidence_for_external_browser_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
            result = runtime.start_run(
                question="external prompt",
                live=True,
                browser_backend=PLAYWRIGHT_MCP_BACKEND,
                oracle_target=CHATGPT_BROWSER_TARGET,
            )
            with self.assertRaisesRegex(ValueError, "completion evidence"):
                runtime.complete_run(result["run_id"], response_text="answer without evidence")

    def test_complete_run_rejects_empty_external_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
            result = runtime.start_run(
                question="external prompt",
                live=True,
                browser_backend=PLAYWRIGHT_MCP_BACKEND,
                oracle_target=CHATGPT_BROWSER_TARGET,
            )
            run_payload = json.loads(Path(result["artifact_paths"]["run"]).read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValueError, "response_text"):
                runtime.complete_run(
                    result["run_id"],
                    response_text="",
                    evidence={
                        "run_id": result["run_id"],
                        "oracle_provider": "chatgpt",
                        "oracle_target": "chatgpt_browser",
                        "url": "https://chatgpt.com/c/test-conversation",
                        "conversation_id": "test-conversation",
                        "prompt_hash": run_payload["prompt_hash"],
                        "final_status": "done",
                    },
                )

    def test_complete_run_accepts_matching_external_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
            result = runtime.start_run(
                question="external prompt",
                live=True,
                browser_backend=PLAYWRIGHT_MCP_BACKEND,
                oracle_target=CHATGPT_BROWSER_TARGET,
            )
            run_payload = json.loads(Path(result["artifact_paths"]["run"]).read_text(encoding="utf-8"))
            completed = runtime.complete_run(
                result["run_id"],
                response_text="external answer",
                evidence={
                    "run_id": result["run_id"],
                    "oracle_provider": "chatgpt",
                    "oracle_target": "chatgpt_browser",
                    "url": "https://chatgpt.com/c/test-conversation",
                    "conversation_id": "test-conversation",
                    "prompt_hash": run_payload["prompt_hash"],
                    "final_status": "done",
                },
            )
            self.assertEqual(completed["status"], "completed")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='multi_aiweb_runtime\src'
python -m pytest -q tests/test_prompt_only_and_target.py -k external_completion
```

Expected: first test fails because no evidence is required yet.

- [ ] **Step 3: Add evidence validation helper to `runtime.py`**

Add:

```python
    def _validate_external_completion_evidence(
        self,
        *,
        run_id: str,
        artifacts: RunArtifacts,
        response_text: str,
        evidence: dict[str, Any] | None,
    ) -> dict[str, Any]:
        run_payload = self._load_run_payload(artifacts, artifacts.run_dir.name)
        if run_payload.get("browser_backend") != PLAYWRIGHT_MCP_BACKEND:
            return evidence or {}
        payload = evidence or {}
        if not response_text.strip():
            raise ValueError("External completion response_text must be non-empty")
        required = ("run_id", "oracle_provider", "oracle_target", "url", "prompt_hash", "final_status")
        missing = [key for key in required if not payload.get(key)]
        if missing:
            raise ValueError(f"Missing completion evidence: {', '.join(missing)}")
        if str(payload.get("run_id")) != run_id:
            raise ValueError("External completion evidence run_id mismatch")
        if payload.get("oracle_provider") != "chatgpt":
            raise ValueError("External completion evidence must identify chatgpt provider")
        if payload.get("oracle_target") != "chatgpt_browser":
            raise ValueError("External completion evidence must identify chatgpt_browser target")
        if str(payload.get("prompt_hash")) != str(run_payload.get("prompt_hash")):
            raise ValueError("External completion evidence prompt_hash mismatch")
        url = str(payload.get("url") or "")
        if "chatgpt.com" not in url:
            raise ValueError("External completion evidence must include a ChatGPT URL")
        if "/c/" not in url and not payload.get("conversation_id"):
            raise ValueError("External completion evidence must include a conversation URL or conversation_id")
        if str(payload.get("final_status")).lower() not in {"done", "completed"}:
            raise ValueError("External completion evidence final_status must be done or completed")
        return self._redact_nested(payload)
```

- [ ] **Step 4: Use the helper in `complete_run`**

Before status writing in `complete_run`, compute:

```python
safe_evidence = self._validate_external_completion_evidence(
    run_id=run_id,
    artifacts=artifacts,
    response_text=response_text,
    evidence=evidence,
)
```

Use `safe_evidence` in status payloads and event signals.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='multi_aiweb_runtime\src'
python -m pytest -q tests/test_prompt_only_and_target.py -k external_completion
```

Expected: selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add multi_aiweb_runtime/src/chatgpt_web_runtime/runtime.py tests/test_prompt_only_and_target.py
git commit -m "feat: validate external browser completion evidence"
```

### Task 5: ChatGPT Pro classified status mapping

**Files:**
- Modify: `multi_aiweb_runtime/src/chatgpt_web_runtime/oracle_adapter.py`
- Modify: `tests/test_prompt_only_and_target.py`

- [ ] **Step 1: Add failing tests for known Oracle failure strings**

Append:

```python
class ChatGptProClassificationTests(unittest.TestCase):
    def _run_with_error(self, stderr: str) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            response_path = state_root / "runs" / "pro" / "response.md"
            response_path.parent.mkdir(parents=True)
            client = FakeOracleClient()
            client.result = OracleCommandResult(
                exit_code=1,
                stdout="",
                stderr=stderr,
                output_text="",
                command=["oracle"],
                output_path=response_path,
                engine_identity={"source": "fake"},
            )
            adapter = OracleAdapter(client=client)
            result = adapter.run(
                prompt="pro prompt",
                files=[],
                repo_root=None,
                permission_level="safe_default",
                mode_label="Pro Extended",
                mode_variant="heavy",
                response_path=response_path,
                timeout_seconds=3600,
                oracle_target=CHATGPT_BROWSER_TARGET,
            )
            return {"status": result.status, "phase": result.phase, "message": result.message}

    def test_classifies_model_selector_missing(self) -> None:
        result = self._run_with_error("Unable to locate the ChatGPT model selector button.")
        self.assertEqual(result["status"], "user_action_required")
        self.assertEqual(result["phase"], "MODEL_SELECTOR_UNAVAILABLE")

    def test_classifies_pro_effort_unconfirmed(self) -> None:
        result = self._run_with_error("refusing to submit without confirmed Pro Extended")
        self.assertEqual(result["status"], "user_action_required")
        self.assertEqual(result["phase"], "PRO_EFFORT_UNCONFIRMED")

    def test_classifies_long_thinking_timeout(self) -> None:
        result = self._run_with_error("Assistant response timed out before completion; reattach later to capture the answer.")
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["phase"], "REATTACH_REQUIRED")

    def test_classifies_real_timeout_with_thinking_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            response_path = state_root / "runs" / "pro-timeout" / "response.md"
            response_path.parent.mkdir(parents=True)
            client = FakeOracleClient()
            client.result = OracleCommandResult(
                exit_code=124,
                stdout="[browser] ChatGPT thinking - 5m elapsed",
                stderr="Oracle timed out.",
                output_text="",
                command=["oracle"],
                output_path=response_path,
                timed_out=True,
                engine_identity={"source": "fake"},
            )
            adapter = OracleAdapter(client=client)
            result = adapter.run(
                prompt="pro prompt",
                files=[],
                repo_root=None,
                permission_level="safe_default",
                mode_label="Pro Extended",
                mode_variant="heavy",
                response_path=response_path,
                timeout_seconds=3600,
                oracle_target=CHATGPT_BROWSER_TARGET,
            )
            self.assertEqual(result.status, "running")
            self.assertEqual(result.phase, "LONG_THINKING_IN_PROGRESS")

    def test_classifies_incomplete_capture(self) -> None:
        result = self._run_with_error("response status incomplete; incompleteReason=incomplete-capture")
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["phase"], "CAPTURE_INCOMPLETE")

    def test_classifies_prompt_not_submitted(self) -> None:
        result = self._run_with_error("Prompt did not appear in conversation before timeout")
        self.assertEqual(result["status"], "user_action_required")
        self.assertEqual(result["phase"], "PROMPT_NOT_SUBMITTED")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='multi_aiweb_runtime\src'
python -m pytest -q tests/test_prompt_only_and_target.py -k ChatGptProClassificationTests
```

Expected: tests fail because Oracle errors currently map to generic `failed`.

- [ ] **Step 3: Add classification helper to `oracle_adapter.py`**

Add near `_failure_message`:

```python
def _classify_chatgpt_pro_failure(message: str) -> tuple[str, str] | None:
    lowered = message.lower()
    if "chatgpt thinking" in lowered or "pro thinking" in lowered:
        return "running", "LONG_THINKING_IN_PROGRESS"
    if "model_selector_unavailable" in lowered or "unable to locate the chatgpt model selector button" in lowered:
        return "user_action_required", "MODEL_SELECTOR_UNAVAILABLE"
    if "unable to find model option" in lowered and "pro" in lowered:
        return "user_action_required", "PRO_NOT_AVAILABLE"
    if "pro_effort_unconfirmed" in lowered or "refusing to submit without confirmed pro extended" in lowered:
        return "user_action_required", "PRO_EFFORT_UNCONFIRMED"
    if "assistant response timed out before completion" in lowered or "reattach later" in lowered:
        return "running", "REATTACH_REQUIRED"
    if "incomplete-capture" in lowered or "capture incomplete" in lowered:
        return "running", "CAPTURE_INCOMPLETE"
    if "prompt did not appear in conversation" in lowered:
        return "user_action_required", "PROMPT_NOT_SUBMITTED"
    if "chrome window closed" in lowered or "econnrefused" in lowered:
        return "user_action_required", "PROFILE_BUSY"
    if "login" in lowered and "required" in lowered:
        return "user_action_required", "LOGIN_REQUIRED"
    return None
```

- [ ] **Step 4: Use classification before timeout and generic failure mapping**

Only apply this helper when `target == CHATGPT_BROWSER_TARGET`. Gemini must remain on its existing fail-closed path until the separate Gemini phase.

In `OracleAdapter.run`, before the existing `if command_result.timed_out:` return, add:

```python
        timeout_message = _failure_message("Oracle browser run timed out.", command_result)
        timeout_classified = (
            _classify_chatgpt_pro_failure(timeout_message)
            if target == CHATGPT_BROWSER_TARGET
            else None
        )
        if command_result.timed_out and timeout_classified is not None:
            status, phase = timeout_classified
            return OracleRunResult(
                status=status,
                phase=phase,
                message=redact(timeout_message),
                scope=scope,
                oracle_target=target,
                provider=provider,
                oracle_model=resolved_model,
                oracle_thinking_time=thinking_time,
                oracle_engine=command_result.engine_identity,
                command_result=command_result,
            )
```

In `OracleAdapter.run`, after:

```python
message = _failure_message("Oracle browser run failed.", command_result)
```

add:

```python
        classified = (
            _classify_chatgpt_pro_failure(message)
            if target == CHATGPT_BROWSER_TARGET
            else None
        )
        if classified is not None:
            status, phase = classified
            return OracleRunResult(
                status=status,
                phase=phase,
                message=redact(message),
                scope=scope,
                oracle_target=target,
                provider=provider,
                oracle_model=resolved_model,
                oracle_thinking_time=thinking_time,
                oracle_engine=command_result.engine_identity,
                command_result=command_result,
            )
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='multi_aiweb_runtime\src'
python -m pytest -q tests/test_prompt_only_and_target.py -k ChatGptProClassificationTests
```

Expected: selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add multi_aiweb_runtime/src/chatgpt_web_runtime/oracle_adapter.py tests/test_prompt_only_and_target.py
git commit -m "feat: classify ChatGPT Pro browser failures"
```

### Task 6: Manual-login setup log safety

**Files:**
- Modify: `multi_aiweb_runtime/src/chatgpt_web_runtime/oracle_client.py`
- Modify: `tests/test_prompt_only_and_target.py`

- [ ] **Step 1: Add a failing test for manual-login child output isolation**

Append:

```python
class ManualLoginLogSafetyTests(unittest.TestCase):
    def test_manual_login_setup_does_not_capture_child_secret_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            captured_kwargs: dict[str, Any] = {}

            class FakeProcess:
                pid = 12345

            def fake_popen(command: Sequence[str], **kwargs: Any) -> FakeProcess:
                captured_kwargs.update(kwargs)
                return FakeProcess()

            client = OracleClient(
                command=("python", "-P", "-m", "multi_aiweb_runtime.oracle_engine_cli"),
                oracle_home_dir=root / "oracle",
            )
            original_popen = subprocess.Popen
            try:
                subprocess.Popen = fake_popen  # type: ignore[assignment]
                launch = client.launch_manual_login_setup(cwd=root, oracle_target=CHATGPT_BROWSER_TARGET)
            finally:
                subprocess.Popen = original_popen  # type: ignore[assignment]

            self.assertEqual(captured_kwargs["stdout"], DEVNULL)
            self.assertEqual(captured_kwargs["stderr"], DEVNULL)
            self.assertTrue(launch.stdout_path.name.endswith(".log"))
            self.assertFalse(launch.stdout_path.exists())
            self.assertFalse(launch.stderr_path.exists())
```

Add `import subprocess` if needed.

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
$env:PYTHONPATH='multi_aiweb_runtime\src'
python -m pytest -q tests/test_prompt_only_and_target.py -k manual_login_setup_does_not_capture
```

Expected: failure because `launch_manual_login_setup` currently passes opened log files to `Popen`.

- [ ] **Step 3: Update `launch_manual_login_setup` to discard child output**

Replace the file-opening `Popen` block with:

```python
        process = subprocess.Popen(
            command,
            cwd=str(Path(cwd).expanduser().resolve()),
            env=self._sanitized_env(base_env, oracle_target=target),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=creationflags,
        )
```

Keep returning `stdout_path` and `stderr_path` for backward-compatible tool payload fields, but do not create those files in this function.

- [ ] **Step 4: Run focused test**

Run:

```powershell
$env:PYTHONPATH='multi_aiweb_runtime\src'
python -m pytest -q tests/test_prompt_only_and_target.py -k manual_login_setup_does_not_capture
```

Expected: selected test passes.

- [ ] **Step 5: Commit**

```powershell
git add multi_aiweb_runtime/src/chatgpt_web_runtime/oracle_client.py tests/test_prompt_only_and_target.py
git commit -m "fix: avoid manual login child log capture"
```

### Task 7: Resume guidance for classified Pro states

**Files:**
- Modify: `multi_aiweb_runtime/src/chatgpt_web_runtime/runtime.py`
- Modify: `tests/test_prompt_only_and_target.py`

- [ ] **Step 1: Add failing resume guidance tests**

Append:

```python
class ResumeGuidanceTests(unittest.TestCase):
    def test_resume_guidance_for_model_selector_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
            result = runtime.start_run(question="selector", dry_run=True)
            artifacts = runtime._artifacts(result["run_id"])
            status = json.loads(artifacts.status_json.read_text(encoding="utf-8"))
            status.update({"status": "user_action_required", "phase": "MODEL_SELECTOR_UNAVAILABLE"})
            artifacts.status_json.write_text(json.dumps(status), encoding="utf-8")

            resume = runtime.run_resume(result["run_id"])
            self.assertEqual(resume["next_action"], "use_playwright_mcp")
            self.assertIn("model selector", resume["message"].lower())

    def test_resume_guidance_for_reattach_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
            result = runtime.start_run(question="reattach", dry_run=True)
            artifacts = runtime._artifacts(result["run_id"])
            status = json.loads(artifacts.status_json.read_text(encoding="utf-8"))
            status.update({"status": "running", "phase": "REATTACH_REQUIRED"})
            artifacts.status_json.write_text(json.dumps(status), encoding="utf-8")

            resume = runtime.run_resume(result["run_id"])
            self.assertEqual(resume["next_action"], "inspect_artifacts")
            self.assertIn("reattach", resume["message"].lower())

    def test_resume_guidance_for_capture_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
            result = runtime.start_run(question="capture", dry_run=True)
            artifacts = runtime._artifacts(result["run_id"])
            status = json.loads(artifacts.status_json.read_text(encoding="utf-8"))
            status.update({"status": "running", "phase": "CAPTURE_INCOMPLETE"})
            artifacts.status_json.write_text(json.dumps(status), encoding="utf-8")

            resume = runtime.run_resume(result["run_id"])
            self.assertEqual(resume["next_action"], "inspect_artifacts")
            self.assertIn("capture", resume["message"].lower())
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='multi_aiweb_runtime\src'
python -m pytest -q tests/test_prompt_only_and_target.py -k ResumeGuidanceTests
```

Expected: failure because `run_resume` does not provide phase-specific guidance yet.

- [ ] **Step 3: Add guidance helper to `runtime.py`**

Add:

```python
    def _resume_guidance_for_phase(self, status_payload: dict[str, Any]) -> tuple[str, str]:
        phase = str(status_payload.get("phase") or "")
        if phase == "MODEL_SELECTOR_UNAVAILABLE":
            return (
                "use_playwright_mcp",
                "ChatGPT model selector was not available to Oracle. Use Playwright MCP to inspect the visible ChatGPT tab and record user_action_required if the UI changed or a gate is visible.",
            )
        if phase == "PRO_NOT_AVAILABLE":
            return (
                "use_playwright_mcp",
                "ChatGPT Pro was not available in the model picker. Inspect the account in the browser profile before retrying.",
            )
        if phase == "PRO_EFFORT_UNCONFIRMED":
            return (
                "use_playwright_mcp",
                "Oracle refused to submit because Pro Extended effort was not confirmed. Inspect the model picker and thinking effort controls.",
            )
        if phase == "PROFILE_BUSY":
            return (
                "close_conflicting_browser",
                "The Oracle ChatGPT profile is busy or has an unreachable DevTools port. Close Chrome windows using the Oracle profile, then retry prepare_session or run_start.",
            )
        if phase == "LOGIN_REQUIRED":
            return (
                "run_oracle_manual_login_setup",
                "The ChatGPT browser profile is not logged in. Run aiweb_prepare_session with browser_backend='oracle', oracle_target='chatgpt_browser', open_browser=true.",
            )
        if phase == "REATTACH_REQUIRED":
            return (
                "inspect_artifacts",
                "The Pro run appears to be still thinking or capture was incomplete. Inspect Oracle artifacts and retry resume after the answer appears.",
            )
        if phase == "CAPTURE_INCOMPLETE":
            return (
                "inspect_artifacts",
                "The Pro answer capture was incomplete. Inspect Oracle artifacts, then retry resume or use Playwright MCP to harvest the completed response.",
            )
        return (
            "inspect_artifacts" if status_payload.get("status") != "user_action_required" else "use_playwright_mcp",
            str(status_payload.get("message") or "Inspect artifacts for the current run state."),
        )
```

- [ ] **Step 4: Use helper in `run_resume`**

After loading `status_payload`, compute:

```python
next_action, message = self._resume_guidance_for_phase(status_payload)
```

Return those values instead of generic values.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='multi_aiweb_runtime\src'
python -m pytest -q tests/test_prompt_only_and_target.py -k ResumeGuidanceTests
```

Expected: selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add multi_aiweb_runtime/src/chatgpt_web_runtime/runtime.py tests/test_prompt_only_and_target.py
git commit -m "feat: add ChatGPT Pro resume guidance"
```

### Task 8: Oracle model selector and thinking markers

**Files:**
- Modify: `engines/oracle/src/browser/actions/modelSelection.ts`
- Modify: `engines/oracle/src/browser/actions/thinkingTime.ts`
- Modify: `engines/oracle/tests/browser/modelSelection.test.ts`
- Modify: `engines/oracle/tests/browser/thinkingTime.test.ts`

- [ ] **Step 1: Add model selector marker expectation**

In `engines/oracle/tests/browser/modelSelection.test.ts`, add:

```typescript
it("marks missing ChatGPT model selector as classifiable", () => {
  const expression = buildModelSelectionExpressionForTest("gpt-5.5-pro");
  expect(expression).toContain("MODEL_SELECTOR_UNAVAILABLE");
});
```

- [ ] **Step 2: Add thinking effort marker expectation**

In `engines/oracle/tests/browser/thinkingTime.test.ts`, add:

```typescript
it("marks unconfirmed Pro Extended effort as classifiable", () => {
  const expression = buildThinkingTimeExpressionForTest("extended");
  expect(expression).toContain("PRO_EFFORT_UNCONFIRMED");
});
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
cd engines\oracle
pnpm vitest run tests/browser/modelSelection.test.ts tests/browser/thinkingTime.test.ts
```

Expected: the new marker expectations fail.

- [ ] **Step 4: Add markers to Oracle browser errors**

In `modelSelection.ts`, change the missing button error to:

```typescript
throw new Error("MODEL_SELECTOR_UNAVAILABLE: Unable to locate the ChatGPT model selector button.");
```

In `thinkingTime.ts`, change strict Pro Extended throw paths to include:

```typescript
throw new Error(`${message}; PRO_EFFORT_UNCONFIRMED: refusing to submit without confirmed Pro Extended.`);
```

and:

```typescript
throw new Error(
  `PRO_EFFORT_UNCONFIRMED: Thinking time: unknown outcome selecting ${capitalizedLevel}; refusing to submit without confirmed Pro Extended.`,
);
```

- [ ] **Step 5: Run focused Vitest tests**

Run:

```powershell
cd engines\oracle
pnpm vitest run tests/browser/modelSelection.test.ts tests/browser/thinkingTime.test.ts
```

Expected: selected Vitest tests pass.

- [ ] **Step 6: Build Oracle dist if source TypeScript changed**

Run:

```powershell
cd engines\oracle
pnpm run build
```

Expected: build exits 0 and updates bundled `engines/oracle/dist` if emitted output changes.

- [ ] **Step 7: Commit**

```powershell
git add engines/oracle/src/browser/actions/modelSelection.ts engines/oracle/src/browser/actions/thinkingTime.ts engines/oracle/tests/browser/modelSelection.test.ts engines/oracle/tests/browser/thinkingTime.test.ts engines/oracle/dist
git commit -m "feat: mark Oracle Pro selector failures"
```

### Task 9: Oracle lifecycle reliability markers

**Files:**
- Create: `engines/oracle/tests/browser/reliabilityMarkers.test.ts`
- Modify: `engines/oracle/src/browser/profileState.ts`
- Modify: `engines/oracle/src/browser/chromeLifecycle.ts`
- Modify: `engines/oracle/src/cli/sessionRunner.ts`

- [ ] **Step 1: Add failing source-marker tests for real lifecycle modules**

Create `engines/oracle/tests/browser/reliabilityMarkers.test.ts`:

```typescript
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, test } from "vitest";

const repoRoot = path.resolve(__dirname, "../..");

function read(relativePath: string): string {
  return readFileSync(path.join(repoRoot, relativePath), "utf8");
}

describe("Oracle browser reliability markers", () => {
  test("profile and Chrome lifecycle modules expose classifiable profile diagnostics", () => {
    const profileState = read("src/browser/profileState.ts");
    const chromeLifecycle = read("src/browser/chromeLifecycle.ts");

    expect(profileState).toContain("PROFILE_BUSY");
    expect(profileState).toContain("STALE_DEVTOOLS_PORT");
    expect(chromeLifecycle).toContain("PROFILE_BUSY");
    expect(chromeLifecycle).toContain("STALE_DEVTOOLS_PORT");
  });

  test("session runner exposes classifiable Pro long-running states", () => {
    const sessionRunner = read("src/cli/sessionRunner.ts");

    expect(sessionRunner).toContain("PROMPT_NOT_SUBMITTED");
    expect(sessionRunner).toContain("LONG_THINKING_IN_PROGRESS");
    expect(sessionRunner).toContain("CAPTURE_INCOMPLETE");
  });
});
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
cd engines\oracle
pnpm vitest run tests/browser/reliabilityMarkers.test.ts
```

Expected: tests fail because the source markers are not present yet.

- [ ] **Step 3: Add classifiable profile diagnostics**

In `profileState.ts`, update the relevant log messages without changing control flow:

```typescript
logger?.(`STALE_DEVTOOLS_PORT: DevTools port ${port} unreachable (${probe.error}); clearing stale profile state`);
logger?.(`PROFILE_BUSY: Chrome pid ${pid} still alive; skipping profile lock cleanup`);
logger?.("PROFILE_BUSY: Detected running Chrome using this profile; skipping profile lock cleanup");
```

In `chromeLifecycle.ts`, update stale port / profile-busy log strings:

```typescript
logger(
  `STALE_DEVTOOLS_PORT: DevToolsActivePort found for ${userDataDir} but unreachable (${probe.error}); launching new Chrome.`,
);
```

If a Chrome profile conflict branch logs a busy profile without a marker, prefix that message with `PROFILE_BUSY:`.

- [ ] **Step 4: Add classifiable session runner states**

In `sessionRunner.ts`, update existing messages without changing control flow:

```typescript
log(dim("PROMPT_NOT_SUBMITTED: Chrome disconnected before a ChatGPT conversation was created; marking session error."));
log(dim("CAPTURE_INCOMPLETE: Assistant response timed out; marking capture incomplete for reattach."));
log(dim("LONG_THINKING_IN_PROGRESS: Auto-reattach will continue while ChatGPT Pro is still thinking."));
```

Use `LONG_THINKING_IN_PROGRESS` in the auto-reattach or thinking-timeout path, not on generic browser errors.

- [ ] **Step 5: Run focused marker tests**

Run:

```powershell
cd engines\oracle
pnpm vitest run tests/browser/reliabilityMarkers.test.ts
```

Expected: marker tests pass.

- [ ] **Step 6: Commit**

```powershell
git add engines/oracle/src/browser/profileState.ts engines/oracle/src/browser/chromeLifecycle.ts engines/oracle/src/cli/sessionRunner.ts engines/oracle/tests/browser/reliabilityMarkers.test.ts
git commit -m "feat: mark Oracle browser reliability states"
```

### Task 10: Documentation for artifact and auth boundaries

**Files:**
- Modify: `README.md`
- Modify: `SECURITY.md`

- [ ] **Step 1: Add README runtime artifact note**

Add:

```markdown
ChatGPT/Gemini prompts and final web responses are stored locally as run artifacts under the Codex state directory. Do not send secrets, credentials, cookies, private keys, or browser profile files through AI web runs. Runtime logs and events are redacted, but the browser provider still receives the prompt and any approved files.
```

- [ ] **Step 2: Add SECURITY boundary note**

Add:

```markdown
The plugin must not read `~/.codex/auth.json`, browser cookie stores, browser localStorage, or provider profile files. Web authentication remains user-mediated through dedicated browser profiles. A run may ask the user to log in, close a conflicting browser, or inspect a CAPTCHA/payment/security gate, but it must not bypass those gates or copy authentication material between profiles.
```

- [ ] **Step 3: Run documentation hygiene check**

Run:

```powershell
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 4: Commit**

```powershell
git add README.md SECURITY.md
git commit -m "docs: clarify AI web artifact boundaries"
```

### Task 11: Full local validation gate

**Files:**
- No source edits unless a previous task left a validation failure.

- [ ] **Step 1: Run Python tests**

Run:

```powershell
$env:PYTHONPATH='multi_aiweb_runtime\src'
python -m pytest -q tests
```

Expected: all tests pass.

- [ ] **Step 2: Run Python compile check**

Run:

```powershell
python -m compileall -q multi_aiweb_runtime tests
```

Expected: exit code 0.

- [ ] **Step 3: Run plugin validators**

Run:

```powershell
python scripts\validate_portability.py
python scripts\validate_plugin.py .
```

Expected: both commands exit 0.

- [ ] **Step 4: Run installer dry run**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -DryRun -SkipOracleDeps -SkipMarketplaceRegistration -SkipPluginInstall
```

Expected: exit code 0 and no marketplace or plugin installation side effects.

- [ ] **Step 5: Run Oracle browser focused tests**

Run:

```powershell
cd engines\oracle
pnpm vitest run tests/browser/modelSelection.test.ts tests/browser/thinkingTime.test.ts tests/browser/reattach.test.ts tests/browser/reattach.e2e.test.ts tests/cli/browserConfig.test.ts
```

Expected: selected Vitest tests pass.

- [ ] **Step 6: Review diff for accidental broad changes**

Run:

```powershell
git status --short
git diff --stat origin/main..HEAD
git diff --check origin/main..HEAD
```

Expected: only planned files changed, and diff check exits 0.

### Task 12: Operator-approved ChatGPT Pro live smoke

**Files:**
- No source edits unless the live smoke exposes a bug that must be fixed in a new focused task.

- [ ] **Step 1: Confirm ChatGPT Oracle profile readiness**

Run through MCP:

```text
aiweb_prepare_session(browser_backend="oracle", oracle_target="chatgpt_browser", open_browser=false)
```

Expected: returns ready/continue in the future implementation, or a classified manual-login / login-required state.

- [ ] **Step 2: Run a no-file Pro prompt**

Run through MCP:

```text
aiweb_run_start(
  question="PRO_RELIABILITY_SMOKE: reply with exactly PRO_RELIABILITY_SMOKE_OK and no other text.",
  browser_backend="oracle",
  oracle_target="chatgpt_browser",
  mode_label="Pro Extended",
  mode_variant="heavy",
  timeout_seconds=3600,
  live=true,
  files=[]
)
```

Expected `status` values are one of:

```text
completed
user_action_required
running
```

Expected `phase` values are one of:

```text
COMPLETED
LOGIN_REQUIRED
PROFILE_BUSY
MODEL_SELECTOR_UNAVAILABLE
PRO_NOT_AVAILABLE
PRO_EFFORT_UNCONFIRMED
PROMPT_NOT_SUBMITTED
LONG_THINKING_IN_PROGRESS
REATTACH_REQUIRED
CAPTURE_INCOMPLETE
USER_ACTION_REQUIRED
```

Opaque `status="failed"` is not acceptable unless it contains a new internal bug that receives a follow-up task.

- [ ] **Step 3: Verify artifacts**

Inspect:

```text
response.md
status.json
run.json
events.jsonl
oracle.stdout.log
oracle.stderr.log
```

Expected:

- `run.json` contains `prompt_hash`, `oracle_target`, `oracle_model`, `oracle_thinking_time`, and Oracle engine identity.
- `status.json` contains a classified phase.
- `events.jsonl` contains redacted event payloads.
- `response.md` contains the final answer only when status is `completed`.

## Final acceptance checklist

- [ ] Default prompt warnings are removed from plugin manifest validation.
- [ ] Runtime event and log surfaces redact the expanded secret corpus.
- [ ] `run.json` records `prompt_hash` for new runs.
- [ ] Terminal runs cannot be overwritten through `aiweb_run_complete` or `aiweb_run_fail`.
- [ ] External Playwright completion requires matching evidence.
- [ ] Known ChatGPT Pro failure strings map to classified phases.
- [ ] Manual-login setup no longer writes child stdout/stderr directly to persistent logs.
- [ ] `aiweb_run_resume` returns phase-specific guidance.
- [ ] Oracle selector and Pro effort errors include classifiable markers.
- [ ] README and SECURITY document local artifact/auth boundaries.
- [ ] Python tests, compile check, plugin validators, installer dry run, and focused Vitest tests pass.
- [ ] Live smoke returns a completed response or a classified, actionable state.
