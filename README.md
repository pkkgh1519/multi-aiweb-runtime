# Multi-AI Web Runtime

Multi-AI Web Runtime is a local Codex plugin that lets Codex delegate prompts to supported AI web browser targets such as ChatGPT and Gemini through explicit, user-mediated browser sessions. The plugin owns policy preview, file-scope validation, environment isolation, structured artifacts, and MCP tool exposure.

## What it does

- Exposes Codex MCP tools for preparing, starting, waiting for, resuming, and inspecting AI web runs.
- Supports prompt-only dry runs with no browser dependency.
- Uses a bundled Oracle browser engine wrapper for ChatGPT/Gemini browser targets when local dependencies are installed.
- Keeps login manual and profile-scoped; the runtime does not copy cookies, extract tokens, or bypass CAPTCHA/payment gates.
- Records auditable artifacts under the local Codex state directory.

## Requirements

- Windows Codex CLI with plugin support.
- PowerShell 5.1 or newer.
- Python 3.11 or newer.
- Optional Oracle browser backend:
  - Node 24 or newer.
  - pnpm 10 or newer.
  - Manual browser login when a provider asks for it.
- Optional Playwright MCP fallback:
  - Codex `playwright` MCP configured separately.

Dry-run mode has no browser dependency.

## Install from a Git checkout

Clone the repository, then run the installer from the repository root:

```powershell
git clone https://github.com/pkkgh1519/multi-aiweb-runtime.git
cd multi-aiweb-runtime
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

The installer copies the plugin into the shared local Codex marketplace:

```text
%USERPROFILE%\.codex\local-marketplaces\
  .agents\plugins\marketplace.json
  multi-aiweb-runtime\plugins\
    .codex-plugin\plugin.json
    .mcp.json
    multi_aiweb_runtime_server.py
    multi_aiweb_runtime\src\...
    skills\multi-aiweb-runtime\...
    engines\oracle\...
```

The installer generates machine-local files such as `.mcp.json` and `install-manifest.json` in the installed plugin copy. Those files are not source-of-truth repository files.

### Installer options

```powershell
.\install.ps1 -DryRun
.\install.ps1 -SkipOracleDeps
.\install.ps1 -SkipMarketplaceRegistration
.\install.ps1 -SkipPluginInstall
.\install.ps1 -NoCachebuster
```

`node_modules` is intentionally not committed. When `-SkipOracleDeps` is not used, the installer checks for Node 24 or newer, then runs this in the installed Oracle engine directory:

```powershell
pnpm install --prod --frozen-lockfile --ignore-scripts
```

`--ignore-scripts` is required because Oracle's package `prepare` lifecycle runs a TypeScript build that depends on devDependencies. The release includes the built `engines/oracle/dist` files, so installation only needs production dependencies from the lockfile.

## Troubleshooting

### Codex reports `invalid marketplace file`

Older installer versions could write `%USERPROFILE%\.codex\local-marketplaces\.agents\plugins\marketplace.json` with a UTF-8 BOM on Windows PowerShell 5.1. Codex may reject that file at line 1 column 1. Update to `v0.5.4` or newer and rerun the installer:

```powershell
git pull --tags
git checkout v0.5.4
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

The installer rewrites generated JSON as UTF-8 without BOM. If the previous marketplace file is empty or invalid JSON, the installer backs it up with an `.invalid.<timestamp>.bak` suffix and recreates the local marketplace manifest.

### Oracle dependency install fails

If the installer reports `Unsupported engine: wanted: {"node": ">=24"}`, install Node 24 or newer and rerun the installer.

If `pnpm install --prod` tries to run `pnpm run build` and fails with `tsgo` missing, update to `v0.5.2` or newer and rerun the installer. The installer must use `--ignore-scripts` for production dependency restore.

```powershell
git pull
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

To install the plugin without Oracle dependencies, use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -SkipOracleDeps
```

## Verify the install

```powershell
codex plugin marketplace list
codex plugin list
codex mcp list
```

Expected installed plugin selector:

```text
multi-aiweb-runtime@local-marketplaces
```

Expected MCP server name:

```text
multi_aiweb_runtime
```

Start a new Codex thread or restart Codex after installing so the app loads the plugin skills and MCP tools.

## First dry run

Ask Codex to use Multi-AI Web Runtime for a dry-run prompt, or call the MCP flow through the plugin skill. Dry-run responses write artifacts without requiring a browser login.

## MCP tools

- `aiweb_prepare_session`
- `aiweb_run_start`
- `aiweb_run_record_event`
- `aiweb_run_complete`
- `aiweb_run_fail`
- `aiweb_run_status`
- `aiweb_run_wait`
- `aiweb_run_resume`
- `aiweb_run_artifacts`
- `aiweb_run_list_recent`

## Security notes

Authentication remains user-mediated in visible or dedicated browser profiles. The runtime does not extract browser credentials, copy cookies, move tokens between profiles, or enable provider API keys by default.

For Oracle-backed runs, requested files are validated before launch. Prompt-only Oracle runs use a managed empty runtime directory. File-attached runs reject repo escapes, absolute Windows drive paths, home-directory paths, `.env`-style files, private keys, cookie stores, and browser profile storage.

## Development checks

```powershell
python -m pip install -r requirements-dev.txt
python scripts\validate_portability.py
python scripts\validate_plugin.py .
$env:PYTHONPATH = "$PWD\multi_aiweb_runtime\src"
python -m pytest -q tests
python -m compileall -q multi_aiweb_runtime tests
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -DryRun -SkipOracleDeps -SkipMarketplaceRegistration -SkipPluginInstall
```

## Repository layout

```text
.codex-plugin/plugin.json       Codex plugin manifest
.mcp.json                       portable source-tree MCP smoke config
.mcp.json.template              installer template for machine-local MCP config
install.ps1                     Windows installer for local Codex marketplace setup
multi_aiweb_runtime/            Python runtime source
engines/oracle/                 bundled Oracle engine source/dist without node_modules
skills/multi-aiweb-runtime/     Codex skill instructions
tests/                          focused runtime tests
docs/                           design and productization notes
scripts/                        validation helpers
```

## Uninstall

```powershell
codex plugin remove multi-aiweb-runtime@local-marketplaces
```

Then remove the installed local plugin copy if it is no longer needed:

```powershell
Remove-Item -Recurse -Force "$env:USERPROFILE\.codex\local-marketplaces\multi-aiweb-runtime"
```

Do not remove runtime state unless saved browser profiles and run artifacts are no longer needed.
