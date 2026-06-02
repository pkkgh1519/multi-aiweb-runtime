from __future__ import annotations

from typing import Any

from .runtime import ChatGptWebRuntime, DEFAULT_MODE_LABEL

runtime = ChatGptWebRuntime()

try:  # pragma: no cover - environment dependent
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover - tested through wrapper functions
    FastMCP = None  # type: ignore[assignment]

if FastMCP is not None:  # pragma: no cover - registration smoke is environment dependent
    server = FastMCP(
        "multi-aiweb-runtime",
        instructions="Local Multi-AI web runtime. Use ChatGPT, Gemini, or future supported AI web targets as auxiliary search/brainstorm/review/cross-check agents when requested. Use browser_backend='oracle' for the safe Oracle adapter with repo-scoped files and explicit oracle_target values ('chatgpt_browser' or 'gemini_browser'); browser_backend='playwright_mcp' returns a target-aware action plan. dry_run is safe for smoke tests.",
    )
else:
    server = None


def _tool(**tool_kwargs):
    def decorator(fn):
        if server is not None:
            return server.tool(**tool_kwargs)(fn)
        return fn
    return decorator


@_tool(name="aiweb_prepare_session", description="Prepare or inspect the AI web browser session state. For browser_backend='oracle', oracle_target selects chatgpt_browser or gemini_browser and open_browser=true launches the dedicated manual-login setup browser. For open_browser=true with playwright_mcp, returns a target-aware action plan.")
def aiweb_prepare_session_tool(
    profile_name: str | None = None,
    dry_run: bool = False,
    open_browser: bool = False,
    browser_backend: str = "playwright_mcp",
    oracle_target: str = "chatgpt_browser",
) -> dict[str, Any]:
    return runtime.prepare_session(
        profile_name=profile_name,
        dry_run=dry_run,
        open_browser=open_browser,
        browser_backend=browser_backend,
        oracle_target=oracle_target,
    )


@_tool(
    name="aiweb_run_start",
    description="Start an AI web run. Compose situational prompts for agent-style search, brainstorming, review, or cross-check tasks. Use browser_backend='oracle' for safe Oracle browser/file-bundling runs; choose oracle_target='chatgpt_browser' or 'gemini_browser'. Use mode_variant for supported thinking intensity (light, standard, extended, heavy) and set long timeout_seconds for Pro/extended runs. browser_backend='playwright_mcp' returns a target-aware action plan. use dry_run_policy=true to preview repo-scoped files before external submission; use dry_run=true for safe smoke tests.",
)
def aiweb_run_start_tool(
    question: str,
    files: list[str] | None = None,
    output_name: str | None = None,
    mode_label: str = DEFAULT_MODE_LABEL,
    mode_variant: str | None = None,
    dry_run: bool = False,
    dry_run_response: str | None = None,
    browser_backend: str = "playwright_mcp",
    completion_backend: str = "cdp_injected",
    live: bool = False,
    profile_name: str | None = None,
    timeout_seconds: int = 120,
    open_browser: bool = False,
    repo_root: str | None = None,
    permission_level: str = "safe_default",
    dry_run_policy: bool = False,
    oracle_target: str = "chatgpt_browser",
    oracle_model: str | None = None,
) -> dict[str, Any]:
    return runtime.start_run(
        question=question,
        files=files,
        output_name=output_name,
        mode_label=mode_label,
        mode_variant=mode_variant,
        dry_run=dry_run,
        dry_run_response=dry_run_response,
        browser_backend=browser_backend,
        completion_backend=completion_backend,
        live=live,
        profile_name=profile_name,
        timeout_seconds=timeout_seconds,
        open_browser=open_browser,
        repo_root=repo_root,
        permission_level=permission_level,
        dry_run_policy=dry_run_policy,
        oracle_target=oracle_target,
        oracle_model=oracle_model,
    )


@_tool(name="aiweb_run_record_event", description="Record an externally observed Playwright MCP browser event for a AI web run.")
def aiweb_run_record_event_tool(
    run_id: str,
    status: str,
    user_text: str = "",
    assistant_text: str = "",
    url: str = "",
    title: str = "",
    conversation_id: str = "",
    tab_id: str | int | None = None,
    page_session_id: str = "",
    model_label: str = "",
    error_text: str = "",
    signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return runtime.record_event(
        run_id=run_id,
        status=status,
        user_text=user_text,
        assistant_text=assistant_text,
        url=url,
        title=title,
        conversation_id=conversation_id,
        tab_id=tab_id,
        page_session_id=page_session_id,
        model_label=model_label,
        error_text=error_text,
        signals=signals,
    )


@_tool(name="aiweb_run_complete", description="Persist the final response from an externally driven Playwright MCP AI web run.")
def aiweb_run_complete_tool(
    run_id: str,
    response_text: str,
    evidence: dict[str, Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    return runtime.complete_run(run_id, response_text=response_text, evidence=evidence, message=message)


@_tool(name="aiweb_run_fail", description="Persist a failure or user-action-required state from an externally driven Playwright MCP AI web run.")
def aiweb_run_fail_tool(
    run_id: str,
    status: str,
    message: str,
    error_text: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return runtime.fail_run(run_id, status=status, message=message, error_text=error_text, evidence=evidence)


@_tool(name="aiweb_run_status", description="Get the structured status for a AI web run.")
def aiweb_run_status_tool(run_id: str) -> dict[str, Any]:
    return runtime.run_status(run_id)


@_tool(name="aiweb_run_wait", description="Wait for a AI web run to reach a terminal state.")
def aiweb_run_wait_tool(run_id: str, timeout_seconds: int = 120) -> dict[str, Any]:
    return runtime.run_wait(run_id, timeout_seconds=timeout_seconds)


@_tool(name="aiweb_run_resume", description="Return resume guidance for a blocked or user-action-required run.")
def aiweb_run_resume_tool(run_id: str) -> dict[str, Any]:
    return runtime.run_resume(run_id)


@_tool(name="aiweb_run_artifacts", description="Return artifact paths for a AI web run.")
def aiweb_run_artifacts_tool(run_id: str) -> dict[str, str]:
    return runtime.run_artifacts(run_id)


@_tool(name="aiweb_run_list_recent", description="List recent AI web runtime runs.")
def aiweb_run_list_recent_tool(limit: int = 20) -> list[dict[str, Any]]:
    return runtime.list_recent_runs(limit=limit)



# Backward-compatible Python wrapper aliases. The preferred MCP surface uses aiweb_* names.
chatgpt_prepare_session_tool = aiweb_prepare_session_tool
chatgpt_run_start_tool = aiweb_run_start_tool
chatgpt_run_record_event_tool = aiweb_run_record_event_tool
chatgpt_run_complete_tool = aiweb_run_complete_tool
chatgpt_run_fail_tool = aiweb_run_fail_tool
chatgpt_run_status_tool = aiweb_run_status_tool
chatgpt_run_wait_tool = aiweb_run_wait_tool
chatgpt_run_resume_tool = aiweb_run_resume_tool
chatgpt_run_artifacts_tool = aiweb_run_artifacts_tool
chatgpt_run_list_recent_tool = aiweb_run_list_recent_tool


def _register_legacy_tool(name: str, description: str, fn):
    if server is not None:  # pragma: no cover - depends on optional mcp package
        server.tool(name=name, description=description)(fn)


_register_legacy_tool("chatgpt_prepare_session", "Legacy alias for aiweb_prepare_session.", aiweb_prepare_session_tool)
_register_legacy_tool("chatgpt_run_start", "Legacy alias for aiweb_run_start.", aiweb_run_start_tool)
_register_legacy_tool("chatgpt_run_record_event", "Legacy alias for aiweb_run_record_event.", aiweb_run_record_event_tool)
_register_legacy_tool("chatgpt_run_complete", "Legacy alias for aiweb_run_complete.", aiweb_run_complete_tool)
_register_legacy_tool("chatgpt_run_fail", "Legacy alias for aiweb_run_fail.", aiweb_run_fail_tool)
_register_legacy_tool("chatgpt_run_status", "Legacy alias for aiweb_run_status.", aiweb_run_status_tool)
_register_legacy_tool("chatgpt_run_wait", "Legacy alias for aiweb_run_wait.", aiweb_run_wait_tool)
_register_legacy_tool("chatgpt_run_resume", "Legacy alias for aiweb_run_resume.", aiweb_run_resume_tool)
_register_legacy_tool("chatgpt_run_artifacts", "Legacy alias for aiweb_run_artifacts.", aiweb_run_artifacts_tool)
_register_legacy_tool("chatgpt_run_list_recent", "Legacy alias for aiweb_run_list_recent.", aiweb_run_list_recent_tool)

def main() -> None:  # pragma: no cover - exercised by external MCP clients
    if server is None:
        raise SystemExit("The 'mcp' package is required to run the MCP server. Install with: python -m pip install mcp")
    server.run()


if __name__ == "__main__":  # pragma: no cover
    main()
