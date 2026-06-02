# Changelog

## 0.5.4 - Marketplace JSON encoding fix

- Fixed Windows PowerShell 5.1 marketplace registration failures by writing generated JSON as UTF-8 without BOM.
- Added recovery for empty or invalid local marketplace manifests by backing up the invalid file and recreating the manifest.
- Added portability validation coverage for installer JSON encoding regressions.

## 0.5.3 - Bundled Oracle dist release fix

- Included the built `engines/oracle/dist` runtime files in Git releases.
- Added plugin validation checks that fail when bundled Oracle CLI/MCP dist files are missing.

## 0.5.2 - Oracle dependency install fix

- Fixed Windows installer Oracle dependency restore by adding `--ignore-scripts` to `pnpm install --prod --frozen-lockfile`.
- Added a clear Node 24+ requirement check before installing Oracle backend dependencies.
- Documented the `tsgo`/`prepare` lifecycle failure mode and recovery commands.

## 0.5.1 - Productization baseline

- Created a canonical source layout for Git-based distribution.
- Added portable Windows installer support for Codex local marketplace installs.
- Added repository hygiene files, portability checks, and CI-oriented validation commands.
- Kept Oracle `node_modules` out of source control; production dependencies are installed locally during setup.
