# Multi-AI Web Runtime Productization Roadmap

## Product target

Multi-AI Web Runtime should be distributed as a Git-backed Codex plugin that a Windows user can clone, install into a local Codex marketplace, verify, and use without copying machine-local cache directories.

## Source-of-truth model

```text
GitHub repository
  -> install.ps1
  -> %USERPROFILE%\.codex\local-marketplaces\multi-aiweb-runtime\plugins
  -> codex plugin add multi-aiweb-runtime@local-marketplaces
```

The Git repository is the canonical source. The Codex local marketplace directory is an install target. Codex plugin cache directories and runtime state directories are generated outputs.

## Phase 0: Canonical repo baseline

- Create `D:\CodexProjects\multi-aiweb-runtime` as the source repository.
- Copy the current plugin source while excluding `node_modules`, cache files, local manifests, and Python bytecode.
- Initialize Git locally without pushing to a remote.
- Keep `C:\Users\<user>\.codex\local-marketplaces` as the install surface only.

## Phase 1: Repository hygiene

- Add `.gitignore`, `LICENSE`, `CHANGELOG.md`, `SECURITY.md`, and `CONTRIBUTING.md`.
- Remove local Codex cachebuster suffixes from source `plugin.json` versions.
- Remove machine-local URLs or profile paths from source files.
- Keep generated install files out of source control.

## Phase 2: Portable installer

- Generate user-specific `.mcp.json` during install.
- Update or create `.agents/plugins/marketplace.json` under the selected local marketplace root.
- Copy source files with generated/cache directories excluded.
- Install Oracle production dependencies locally instead of committing `node_modules`.
- Support `-DryRun`, `-SkipOracleDeps`, `-SkipMarketplaceRegistration`, `-SkipPluginInstall`, and `-NoCachebuster`.

## Phase 3: Validation gates

- Validate plugin manifest shape and companion MCP file.
- Validate portability by scanning for personal absolute paths and generated dependency directories.
- Run focused Python tests with `PYTHONPATH=multi_aiweb_runtime\src`.
- Compile Python sources.
- Run installer dry-run in CI.

## Phase 4: Public release readiness

- Use `https://github.com/pkkgh1519/multi-aiweb-runtime` as the GitHub owner/repository URL.
- Update plugin metadata URLs after the remote exists.
- Add release notes and tag `v0.5.1` or the selected release version.
- Test install from a clean clone on a second Windows profile or PC.
- Document login setup and troubleshooting with screenshots only after the flow is stable.

## Current non-goals

- No push, publish, or GitHub release creation without explicit operator approval.
- No provider login automation beyond user-mediated browser setup.
- No committed `node_modules` dependency tree.
- No mutation of global Codex config outside the local marketplace registration flow.
