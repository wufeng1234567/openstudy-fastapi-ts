# Security Policy

## Secrets

- Never commit real `.env` files, API keys, tokens, passwords, or private endpoints.
- Use `.env.example` only for placeholders.
- Git remotes are configured outside the repository; tokens must not appear in URLs, config, commits, logs, or documentation.
- Rotate any credential that has been exposed; do not rely on history deletion alone.

## Reporting

Report a vulnerability privately to the project maintainers rather than opening a public issue with exploit details. Include affected endpoint/component, reproduction steps, impact, and suggested mitigation.

## Access and data boundaries

- Authentication and role checks belong in backend services, not only in the UI.
- User-uploaded files and parsed content are untrusted input; validate size/type and never execute uploaded content.
- PII and document evidence must not be logged in full. Use IDs or redacted excerpts in diagnostics.
- Write-capable Agent tools require explicit confirmation and authorization; read-only tools must not silently perform writes.

## Repository hygiene

`git ls-files` must not contain `.env`, `node_modules/`, `.venv/`, generated evidence, local screenshots beyond README assets, or temporary logs. The CI `repo-hygiene` job is a guard, not a substitute for reviewing `git status` before commit.
