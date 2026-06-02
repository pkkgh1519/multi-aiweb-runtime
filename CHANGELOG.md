# Changelog

## 0.5.2 - Oracle dependency install fix

- Fixed Windows installer Oracle dependency restore by adding `--ignore-scripts` to `pnpm install --prod --frozen-lockfile`.
- Added a clear Node 24+ requirement check before installing Oracle backend dependencies.
- Documented the `tsgo`/`prepare` lifecycle failure mode and recovery commands.

## 0.5.1 - Productization baseline

- Created a canonical source layout for Git-based distribution.
- Added portable Windows installer support for Codex local marketplace installs.
- Added repository hygiene files, portability checks, and CI-oriented validation commands.
- Kept Oracle `node_modules` out of source control; production dependencies are installed locally during setup.
