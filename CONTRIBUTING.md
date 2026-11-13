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
- frontend: composable import check, component folder structure check, lint, unit tests, build:prod;
- type-check is no longer part of the iteration gate; keep historical numbers in the quality report only, never describe them as passing.

## Directory conventions

- `views/` — page orchestration only.
- `components/` — reusable presentational components.
- `composables/` — stateful / side-effect logic.
- `utils/` — pure functions.
- `api/` — typed API clients.
- `store/` or `stores/` — shared state.

Feature packages under `src/components/<Feature>/` follow this layout:

```text
<Feature>.vue or index.vue   # one public entry at the root only
components/                  # child .vue components
composables/                 # use* state/side-effect helpers
utils/                       # pure TypeScript helpers
styles/                      # .css/.scss files
```

The structural rule is enforced by `scripts/check_frontend_structure.py`.

## Tool-assisted development

- Follow the repository rule in [.codeartsdoer/rule/openstudy-project.md](.codeartsdoer/rule/openstudy-project.md) and the release skill in [.codeartsdoer/skills/openstudy-release/SKILL.md](.codeartsdoer/skills/openstudy-release/SKILL.md).
- Keep tool-generated logs, sessions, and decision notes under [doc/dev-process/README.md](doc/dev-process/README.md); do not rewrite raw logs as marketing copy.
- Before editing, locate the code with `grep` / `read`; make one focused change at a time.
- Run `scripts\verify-quality.bat` before every push.
- Use commit prefixes `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`.

New code should not increase the warning baseline without an explicit debt note.

## Commit conventions

Use prefixes: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`. A commit that removes code should state the 0-reference evidence and affected paths.

## Pull requests

- Describe the user-visible change and evidence command.
- Include screenshots only when the UI changes.
- Update `CHANGELOG.md` for user-visible releases.
- Do not commit `.env`, generated evidence, local media, or `node_modules`.
