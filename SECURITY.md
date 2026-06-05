# Security Policy

Multi-AI Web Runtime is a local Codex plugin for user-mediated AI web browser sessions.

## Security boundaries

- The runtime does not extract cookies, localStorage, browser tokens, or provider API keys.
- Authentication is completed manually by the user in the selected browser profile.
- File sharing is policy-gated before an Oracle-backed run starts.
- Repo escapes, home-directory paths, Windows drive paths, `.env` files, private keys, cookie stores, and browser profile storage are rejected from file attachments.
- Oracle browser targets use dedicated runtime state under the Codex state directory.
- The plugin must not read `~/.codex/auth.json`, browser cookie stores, browser localStorage, or provider profile files. Web authentication remains user-mediated through dedicated browser profiles. A run may ask the user to log in, close a conflicting browser, or inspect a CAPTCHA/payment/security gate, but it must not bypass those gates or copy authentication material between profiles.

## Sensitive data handling

Do not commit runtime state, browser profiles, cookies, tokens, logs containing secrets, `.env` files, or generated artifacts. The repository `.gitignore` excludes the common local paths, but contributors remain responsible for reviewing changes before publishing.

## Reporting issues

For private/local deployments, report security issues to the maintainer of the distribution source before publishing details. For public GitHub releases, add a repository-specific security contact or GitHub private vulnerability reporting before broad distribution.
