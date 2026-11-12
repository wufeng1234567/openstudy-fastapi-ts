# Contributing to OpenStudy

## Local setup

1. Use Windows `.bat` scripts for local startup; do not add `.ps1` launchers.
2. Backend (Python 3.11):
   ```bat
   cd openstudy-fastapi
   .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   ```
3. Frontend (Node 20+):
   ```bat
   cd openstudy-vue3-ts
   npm install
   npm run dev
   ```

## Before every commit

```bat
scripts\verify-quality.bat
```

Expected gates:

- backend: compileall, ruff `E9,F63,F7,F82`, pytest;
- frontend: lint, build:prod;
- type-check is currently a report-only step with known historical debt; never describe it as passing.

## Directory conventions

- `views/` — page orchestration only.
- `components/` — reusable presentational components.
- `composables/` — stateful / side-effect logic.
- `utils/` — pure functions.
- `api/` — typed API clients.
- `store/` or `stores/` — shared state.

New code should not increase the warning/type-error baseline without an explicit debt note.

## Commit conventions

Use prefixes: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`. A commit that removes code should state the 0-reference evidence and affected paths.

## Pull requests

- Describe the user-visible change and evidence command.
- Include screenshots only when the UI changes.
- Update `CHANGELOG.md` for user-visible releases.
- Do not commit `.env`, generated evidence, local media, or `node_modules`.
