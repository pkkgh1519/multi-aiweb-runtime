from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from subprocess import DEVNULL, CompletedProcess, TimeoutExpired
from typing import Any, Sequence

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
            self.assertEqual(command[-2:], ["-p", "HI"])

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
            thinking_index = captured_command.index("--browser-thinking-time")
            self.assertEqual(captured_command[thinking_index + 1], "heavy")
            self.assertEqual(captured_kwargs["timeout"], 4200)


if __name__ == "__main__":
    unittest.main()
