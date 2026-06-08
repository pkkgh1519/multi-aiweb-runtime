from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from subprocess import DEVNULL, CompletedProcess, TimeoutExpired
from typing import Any, Sequence
from unittest.mock import patch

from chatgpt_web_runtime import oracle_client as oracle_client_module
from chatgpt_web_runtime.config import RuntimeConfig
from chatgpt_web_runtime.oracle_adapter import OracleAdapter
from chatgpt_web_runtime.oracle_client import (
    CHATGPT_BROWSER_TARGET,
    GEMINI_BROWSER_TARGET,
    GEMINI_BROWSER_URL,
    OracleClient,
    OracleCommandResult,
    resolve_oracle_thinking_time,
)
from chatgpt_web_runtime.runtime import ChatGptWebRuntime, ORACLE_BACKEND, PLAYWRIGHT_MCP_BACKEND


class FakeOracleClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result: OracleCommandResult | None = None

    def run_browser_consult(
        self,
        *,
        prompt: str,
        files: Sequence[str | Path],
        output_path: str | Path,
        cwd: str | Path,
        mode_label: str,
        timeout_seconds: int,
        oracle_target: str,
        oracle_model: str | None = None,
        mode_variant: str | None = None,
    ) -> OracleCommandResult:
        self.calls.append(
            {
                "prompt": prompt,
                "files": list(files),
                "output_path": Path(output_path),
                "cwd": Path(cwd),
                "mode_label": mode_label,
                "timeout_seconds": timeout_seconds,
                "oracle_target": oracle_target,
                "oracle_model": oracle_model,
                "mode_variant": mode_variant,
            }
        )
        if self.result is not None:
            return self.result
        Path(output_path).write_text("external review ok", encoding="utf-8")
        return OracleCommandResult(
            exit_code=0,
            stdout="",
            stderr="",
            output_text="external review ok",
            command=["oracle"],
            output_path=Path(output_path),
            engine_identity={"source": "fake"},
        )


class PromptOnlyOracleTests(unittest.TestCase):
    def test_oracle_prompt_only_run_uses_managed_empty_repo_when_repo_root_is_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            response_path = state_root / "runs" / "smoke" / "response.md"
            response_path.parent.mkdir(parents=True)
            client = FakeOracleClient()
            adapter = OracleAdapter(client=client)

            result = adapter.run(
                prompt="review this prompt",
                files=[],
                repo_root=None,
                permission_level="safe_default",
                mode_label="Extension Heavy",
                response_path=response_path,
                timeout_seconds=30,
            )

            self.assertEqual(result.status, "completed")
            self.assertEqual(result.scope.blocked_files, [])
            self.assertEqual(result.scope.allowed_files, [])
            self.assertEqual(len(client.calls), 1)
            prompt_only_repo = (state_root / "prompt-only-repo").resolve()
            self.assertEqual(client.calls[0]["cwd"].resolve(), prompt_only_repo)
            self.assertTrue((prompt_only_repo / ".git").is_dir())

    def test_oracle_timeout_writes_redacted_stdout_and_stderr_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            response_path = state_root / "runs" / "timeout" / "response.md"
            response_path.parent.mkdir(parents=True)
            client = FakeOracleClient()
            client.result = OracleCommandResult(
                exit_code=124,
                stdout="before timeout",
                stderr="timeout detail",
                output_text="",
                command=["oracle"],
                output_path=response_path,
                timed_out=True,
                engine_identity={"source": "fake"},
            )
            adapter = OracleAdapter(client=client)

            result = adapter.run(
                prompt="review this prompt",
                files=[],
                repo_root=None,
                permission_level="safe_default",
                mode_label="Extension Heavy",
                response_path=response_path,
                timeout_seconds=30,
            )

            self.assertEqual(result.status, "timeout")
            self.assertIn("stdout_tail=before timeout", result.message)
            self.assertIn("stderr_tail=timeout detail", result.message)
            self.assertEqual((response_path.parent / "oracle.stdout.log").read_text(encoding="utf-8"), "before timeout")
            self.assertEqual((response_path.parent / "oracle.stderr.log").read_text(encoding="utf-8"), "timeout detail")

    def test_invalid_gemini_thinking_time_is_policy_blocked_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            response_path = state_root / "runs" / "blocked" / "response.md"
            response_path.parent.mkdir(parents=True)
            client = FakeOracleClient()
            adapter = OracleAdapter(client=client)

            result = adapter.run(
                prompt="review this prompt",
                files=[],
                repo_root=None,
                permission_level="safe_default",
                mode_label="Extension Heavy",
                mode_variant="extended",
                response_path=response_path,
                timeout_seconds=30,
                oracle_target=GEMINI_BROWSER_TARGET,
                oracle_model="gemini-3.5-flash",
            )

            self.assertEqual(result.status, "policy_blocked")
            self.assertEqual(client.calls, [])


class PlaywrightTargetPlanTests(unittest.TestCase):
    def test_playwright_mcp_gemini_target_uses_gemini_url_and_preserves_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))

            result = runtime.start_run(
                question="review this prompt",
                live=True,
                browser_backend=PLAYWRIGHT_MCP_BACKEND,
                oracle_target=GEMINI_BROWSER_TARGET,
                oracle_model="gemini-3.1-pro",
                mode_label="Extension Heavy",
            )

            action_plan = result["action_plan"]
            self.assertEqual(action_plan["chat_url"], GEMINI_BROWSER_URL)
            self.assertEqual(action_plan["steps"][0]["args"]["url"], GEMINI_BROWSER_URL)
            self.assertEqual(action_plan["oracle_target"], GEMINI_BROWSER_TARGET)
            self.assertEqual(action_plan["oracle_provider"], "gemini")
            self.assertEqual(action_plan["oracle_model"], "gemini-3.1-pro")


class OracleManualLoginSetupTests(unittest.TestCase):
    def test_manual_login_setup_command_keeps_visible_browser_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = OracleClient(
                command=("python", "-P", "-m", "multi_aiweb_runtime.oracle_engine_cli"),
                oracle_home_dir=Path(tmp) / "oracle",
            )

            command = client.build_manual_login_setup_command(oracle_target=CHATGPT_BROWSER_TARGET)

            self.assertIn("--browser-manual-login", command)
            self.assertIn("--browser-keep-browser", command)
            self.assertIn("--browser-manual-login-profile-dir", command)
            self.assertNotIn("--browser-headless", command)
            self.assertNotIn("--browser-hide-window", command)
            strategy_index = command.index("--browser-model-strategy")
            self.assertEqual(command[strategy_index + 1], "ignore")
            self.assertEqual(command[-2:], ["-p", "HI"])

    def test_gemini_manual_login_setup_passes_detected_chrome_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chrome_path = str(Path(tmp) / "Google" / "Chrome" / "Application" / "chrome.exe")
            client = OracleClient(
                command=("python", "-P", "-m", "multi_aiweb_runtime.oracle_engine_cli"),
                oracle_home_dir=Path(tmp) / "oracle",
            )

            with patch.object(oracle_client_module, "detect_default_chrome_path", return_value=chrome_path):
                command = client.build_manual_login_setup_command(oracle_target=GEMINI_BROWSER_TARGET)

            chrome_index = command.index("--browser-chrome-path")
            self.assertEqual(command[chrome_index + 1], chrome_path)

    def test_gemini_browser_run_passes_detected_chrome_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_path = root / "response.md"
            chrome_path = str(root / "Google" / "Chrome" / "Application" / "chrome.exe")
            captured_command: list[str] = []

            def runner(command: Sequence[str], **kwargs: Any) -> CompletedProcess[str]:
                captured_command.extend(command)
                output_path.write_text("ok", encoding="utf-8")
                return CompletedProcess(command, 0, stdout="", stderr="")

            client = OracleClient(
                command=("python", "-P", "-m", "multi_aiweb_runtime.oracle_engine_cli"),
                oracle_home_dir=root / "oracle",
                runner=runner,
            )

            with patch.object(oracle_client_module, "detect_default_chrome_path", return_value=chrome_path):
                result = client.run_browser_consult(
                    prompt="review this prompt",
                    files=[],
                    output_path=output_path,
                    cwd=root,
                    mode_label="Extension Heavy",
                    timeout_seconds=30,
                    oracle_target=GEMINI_BROWSER_TARGET,
                )

            self.assertEqual(result.exit_code, 0)
            chrome_index = captured_command.index("--browser-chrome-path")
            self.assertEqual(captured_command[chrome_index + 1], chrome_path)

    def test_prepare_session_oracle_returns_first_time_setup_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))

            result = runtime.prepare_session(
                browser_backend=ORACLE_BACKEND,
                oracle_target=GEMINI_BROWSER_TARGET,
            )

            setup = result["manual_login_setup"]
            self.assertEqual(result["next_action"], "run_oracle_manual_login_setup")
            self.assertTrue(setup["opens_visible_browser"])
            self.assertTrue(setup["keeps_browser_open"])
            self.assertIn("--browser-keep-browser", setup["command"])
            self.assertIn("--model", setup["command"])
            self.assertIn("gemini-3.1-pro", setup["command"])

    def test_prepare_session_oracle_dry_run_is_target_aware_for_gemini(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))

            result = runtime.prepare_session(
                browser_backend=ORACLE_BACKEND,
                oracle_target=GEMINI_BROWSER_TARGET,
                dry_run=True,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["oracle_target"], GEMINI_BROWSER_TARGET)
            self.assertEqual(result["oracle_provider"], "gemini")
            self.assertEqual(result["chat_url"], GEMINI_BROWSER_URL)
            self.assertIn("gemini_browser", result["oracle_profile_dir"])

    def test_timeout_after_output_file_is_salvaged_as_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_path = root / "response.md"

            def runner(*args: Any, **kwargs: Any) -> None:
                output_path.write_text("late answer", encoding="utf-8")
                raise TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"], output="stdout tail", stderr="stderr tail")

            client = OracleClient(
                command=("python", "-P", "-m", "multi_aiweb_runtime.oracle_engine_cli"),
                oracle_home_dir=root / "oracle",
                runner=runner,
            )

            result = client.run_browser_consult(
                prompt="review this prompt",
                files=[],
                output_path=output_path,
                cwd=root,
                mode_label="Extension Heavy",
                timeout_seconds=1,
                oracle_target=CHATGPT_BROWSER_TARGET,
            )

            self.assertEqual(result.exit_code, 0)
            self.assertFalse(result.timed_out)
            self.assertEqual(result.output_text, "late answer")

    def test_browser_consult_detaches_stdin_for_mcp_stdio_safety(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_path = root / "response.md"
            captured_kwargs: dict[str, Any] = {}

            def runner(command: Sequence[str], **kwargs: Any) -> CompletedProcess[str]:
                captured_kwargs.update(kwargs)
                output_path.write_text("ok", encoding="utf-8")
                return CompletedProcess(command, 0, stdout="", stderr="")

            client = OracleClient(
                command=("python", "-P", "-m", "multi_aiweb_runtime.oracle_engine_cli"),
                oracle_home_dir=root / "oracle",
                runner=runner,
            )

            result = client.run_browser_consult(
                prompt="review this prompt",
                files=[],
                output_path=output_path,
                cwd=root,
                mode_label="Extension Heavy",
                timeout_seconds=30,
                oracle_target=CHATGPT_BROWSER_TARGET,
            )

            self.assertEqual(result.exit_code, 0)
            self.assertIs(captured_kwargs["stdin"], DEVNULL)

    def test_mode_variant_controls_chatgpt_browser_thinking_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_path = root / "response.md"
            captured_command: list[str] = []

            def runner(command: Sequence[str], **kwargs: Any) -> CompletedProcess[str]:
                captured_command.extend(command)
                output_path.write_text("ok", encoding="utf-8")
                return CompletedProcess(command, 0, stdout="", stderr="")

            client = OracleClient(
                command=("python", "-P", "-m", "multi_aiweb_runtime.oracle_engine_cli"),
                oracle_home_dir=root / "oracle",
                runner=runner,
            )

            result = client.run_browser_consult(
                prompt="review this prompt",
                files=[],
                output_path=output_path,
                cwd=root,
                mode_label="Extension Heavy",
                mode_variant="standard",
                timeout_seconds=30,
                oracle_target=CHATGPT_BROWSER_TARGET,
            )

            self.assertEqual(result.exit_code, 0)
            thinking_index = captured_command.index("--browser-thinking-time")
            self.assertEqual(captured_command[thinking_index + 1], "standard")

    def test_extension_heavy_ignores_model_selector_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_path = root / "response.md"
            captured_command: list[str] = []

            def runner(command: Sequence[str], **kwargs: Any) -> CompletedProcess[str]:
                captured_command.extend(command)
                output_path.write_text("ok", encoding="utf-8")
                return CompletedProcess(command, 0, stdout="", stderr="")

            client = OracleClient(
                command=("python", "-P", "-m", "multi_aiweb_runtime.oracle_engine_cli"),
                oracle_home_dir=root / "oracle",
                runner=runner,
            )

            result = client.run_browser_consult(
                prompt="review this prompt",
                files=[],
                output_path=output_path,
                cwd=root,
                mode_label="Extension Heavy",
                mode_variant="heavy",
                timeout_seconds=30,
                oracle_target=CHATGPT_BROWSER_TARGET,
            )

            self.assertEqual(result.exit_code, 0)
            strategy_index = captured_command.index("--browser-model-strategy")
            self.assertEqual(captured_command[strategy_index + 1], "ignore")
            thinking_index = captured_command.index("--browser-thinking-time")
            self.assertEqual(captured_command[thinking_index + 1], "heavy")

    def test_gemini_flash_rejects_extended_thinking_time(self) -> None:
        with self.assertRaises(ValueError):
            resolve_oracle_thinking_time(
                oracle_target=GEMINI_BROWSER_TARGET,
                resolved_model="gemini-3.5-flash",
                mode_label="Extension Heavy",
                mode_variant="extended",
            )

    def test_pro_extended_enforces_one_hour_browser_and_subprocess_timeouts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_path = root / "response.md"
            captured_command: list[str] = []
            captured_kwargs: dict[str, Any] = {}

            def runner(command: Sequence[str], **kwargs: Any) -> CompletedProcess[str]:
                captured_command.extend(command)
                captured_kwargs.update(kwargs)
                output_path.write_text("ok", encoding="utf-8")
                return CompletedProcess(command, 0, stdout="", stderr="")

            client = OracleClient(
                command=("python", "-P", "-m", "multi_aiweb_runtime.oracle_engine_cli"),
                oracle_home_dir=root / "oracle",
                runner=runner,
            )

            result = client.run_browser_consult(
                prompt="review this prompt",
                files=[],
                output_path=output_path,
                cwd=root,
                mode_label="Pro Extended",
                mode_variant="heavy",
                timeout_seconds=120,
                oracle_target=CHATGPT_BROWSER_TARGET,
            )

            self.assertEqual(result.exit_code, 0)
            browser_timeout_index = captured_command.index("--browser-timeout")
            self.assertEqual(captured_command[browser_timeout_index + 1], "3600s")
            strategy_index = captured_command.index("--browser-model-strategy")
            self.assertEqual(captured_command[strategy_index + 1], "select")
            thinking_index = captured_command.index("--browser-thinking-time")
            self.assertEqual(captured_command[thinking_index + 1], "heavy")
            self.assertEqual(captured_kwargs["timeout"], 4200)


class RedactionTests(unittest.TestCase):
    def test_redacts_common_secret_shapes(self) -> None:
        from chatgpt_web_runtime.redaction import contains_secret_risk, redact

        samples = [
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
            "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz1234567890",
            "token=abcdefghijklmnopqrstuvwxyz123456",
            "auth_token=abcdefghijklmnopqrstuvwxyz123456",
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


class RuntimeCompletionGuardTests(unittest.TestCase):
    def test_start_run_records_prompt_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
            result = runtime.start_run(question="hash me", dry_run=True)
            run_json = Path(result["artifact_paths"]["run"])
            payload = json.loads(run_json.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["prompt_hash"]), 64)
            self.assertEqual(payload["prompt_hash_algorithm"], "sha256")
            self.assertEqual(payload["hash_algorithm"], "sha256")
            self.assertEqual(payload["state_history"], [])
            self.assertFalse(payload["recoverable"])

    def test_complete_run_rejects_terminal_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
            result = runtime.start_run(question="already done", dry_run=True)
            with self.assertRaisesRegex(ValueError, "terminal"):
                runtime.complete_run(result["run_id"], response_text="overwrite")

    def test_complete_run_rejects_all_existing_nonrecoverable_terminal_statuses(self) -> None:
        terminal_statuses = ("watch_lost", "policy_preview", "policy_blocked", "cancelled")
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

    def test_complete_run_allows_recoverable_user_action_required_phase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
            result = runtime.start_run(
                question="selector",
                live=True,
                browser_backend=PLAYWRIGHT_MCP_BACKEND,
                oracle_target=CHATGPT_BROWSER_TARGET,
            )
            artifacts = runtime._artifacts(result["run_id"])
            status = json.loads(artifacts.status_json.read_text(encoding="utf-8"))
            status.update({"status": "user_action_required", "phase": "MODEL_SELECTOR_UNAVAILABLE"})
            artifacts.status_json.write_text(json.dumps(status), encoding="utf-8")
            run_payload = json.loads(artifacts.run_json.read_text(encoding="utf-8"))

            completed = runtime.complete_run(
                result["run_id"],
                response_text="recovered answer",
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

    def test_complete_run_accepts_matching_gemini_external_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
            result = runtime.start_run(
                question="gemini external prompt",
                live=True,
                browser_backend=PLAYWRIGHT_MCP_BACKEND,
                oracle_target=GEMINI_BROWSER_TARGET,
            )
            run_payload = json.loads(Path(result["artifact_paths"]["run"]).read_text(encoding="utf-8"))
            completed = runtime.complete_run(
                result["run_id"],
                response_text="gemini external answer",
                evidence={
                    "run_id": result["run_id"],
                    "oracle_provider": "gemini",
                    "oracle_target": "gemini_browser",
                    "url": "https://gemini.google.com/app/test-conversation",
                    "prompt_hash": run_payload["prompt_hash"],
                    "final_status": "done",
                },
            )
            self.assertEqual(completed["status"], "completed")


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

    def test_classifies_direct_oracle_markers(self) -> None:
        cases = {
            "LONG_THINKING_IN_PROGRESS: Auto-reattach will continue": ("running", "LONG_THINKING_IN_PROGRESS"),
            "PROMPT_NOT_SUBMITTED: Chrome disconnected before a ChatGPT conversation was created": ("user_action_required", "PROMPT_NOT_SUBMITTED"),
            "CAPTURE_INCOMPLETE: Assistant response timed out": ("running", "CAPTURE_INCOMPLETE"),
            "PROFILE_BUSY: Chrome pid 123 still alive": ("user_action_required", "PROFILE_BUSY"),
            "STALE_DEVTOOLS_PORT: DevTools port 9222 unreachable": ("user_action_required", "PROFILE_BUSY"),
            "ERROR: No Chrome installations found.": ("user_action_required", "CHROME_NOT_FOUND"),
        }
        for message, expected in cases.items():
            result = self._run_with_error(message)
            self.assertEqual((result["status"], result["phase"]), expected)


class GeminiClassificationTests(unittest.TestCase):
    def test_classifies_missing_chrome_as_user_action_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            response_path = state_root / "runs" / "gemini-chrome" / "response.md"
            response_path.parent.mkdir(parents=True)
            client = FakeOracleClient()
            client.result = OracleCommandResult(
                exit_code=1,
                stdout="ERROR: No Chrome installations found. User error (browser-automation): No Chrome installations found.",
                stderr="",
                output_text="",
                command=["oracle"],
                output_path=response_path,
                engine_identity={"source": "fake"},
            )
            adapter = OracleAdapter(client=client)

            result = adapter.run(
                prompt="gemini prompt",
                files=[],
                repo_root=None,
                permission_level="safe_default",
                mode_label="Extension Heavy",
                response_path=response_path,
                timeout_seconds=60,
                oracle_target=GEMINI_BROWSER_TARGET,
            )

            self.assertEqual(result.status, "user_action_required")
            self.assertEqual(result.phase, "CHROME_NOT_FOUND")

    def test_start_run_marks_gemini_chrome_not_found_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            client = FakeOracleClient()
            client.result = OracleCommandResult(
                exit_code=1,
                stdout="ERROR: No Chrome installations found.",
                stderr="",
                output_text="",
                command=["oracle"],
                engine_identity={"source": "fake"},
            )
            runtime = ChatGptWebRuntime(
                config=RuntimeConfig(state_root=state_root),
                oracle_adapter=OracleAdapter(client=client),
            )

            result = runtime.start_run(
                question="gemini prompt",
                live=True,
                browser_backend=ORACLE_BACKEND,
                oracle_target=GEMINI_BROWSER_TARGET,
            )

            run_payload = json.loads(Path(result["artifact_paths"]["run"]).read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "user_action_required")
            self.assertEqual(result["phase"], "CHROME_NOT_FOUND")
            self.assertTrue(run_payload["recoverable"])


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

    def test_resume_guidance_for_chrome_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ChatGptWebRuntime(config=RuntimeConfig(state_root=Path(tmp)))
            result = runtime.start_run(question="chrome", dry_run=True)
            artifacts = runtime._artifacts(result["run_id"])
            status = json.loads(artifacts.status_json.read_text(encoding="utf-8"))
            status.update({"status": "user_action_required", "phase": "CHROME_NOT_FOUND"})
            artifacts.status_json.write_text(json.dumps(status), encoding="utf-8")

            resume = runtime.run_resume(result["run_id"])
            self.assertEqual(resume["next_action"], "configure_chrome_path")
            self.assertIn("chrome", resume["message"].lower())


if __name__ == "__main__":
    unittest.main()
