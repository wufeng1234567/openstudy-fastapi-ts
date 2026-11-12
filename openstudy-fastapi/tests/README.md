# OpenStudy Backend Tests

Current baseline: 109 tests collected, `pytest tests -q` exit 0.

## Target layout (P1)

```text
tests/
  unit/          # pure functions, schema validation, service boundaries
  integration/   # DB/Redis/API integration
  contract/      # Agent tool schemas, route/response contracts
  _fixtures/     # shared fixtures and sample data
```

Existing test files are intentionally kept flat until P1 migration; do not mix new tests into ad-hoc probe scripts. Run:

```bat
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe -m ruff check app --select E9,F63,F7,F82
```

Tests must not depend on real LLM output; mock/fixture boundaries.
