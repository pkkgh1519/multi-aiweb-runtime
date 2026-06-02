# Contributing

## Development setup

```powershell
python -m pip install -r requirements-dev.txt
$env:PYTHONPATH = "$PWD\multi_aiweb_runtime\src"
python -m pytest -q tests
```

## Validation before publishing

```powershell
python scripts\validate_portability.py
python scripts\validate_plugin.py .
$env:PYTHONPATH = "$PWD\multi_aiweb_runtime\src"
python -m pytest -q tests
python -m compileall -q multi_aiweb_runtime tests
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -DryRun -SkipOracleDeps -SkipMarketplaceRegistration -SkipPluginInstall
```

## Boundaries

- Do not commit `node_modules`, runtime state, browser profiles, cookies, tokens, or generated artifacts.
- Do not weaken file-scope, environment-sanitization, or login-boundary checks to make live runs easier.
- Keep user-facing plugin names and machine-readable IDs stable unless a migration plan is written.
