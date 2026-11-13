# OpenStudy Frontend Tests

Current state: `npm run test:unit` exists and passes 29 assertions (mindmap 15 + latex table 14); Playwright E2E is still a P1 gap.

## Target layout

```text
tests/
  unit/          # Vitest: pure utils and composables
  e2e/           # Playwright smoke: login, workspace, practice, agent
```

Minimum P1 smoke:

1. login / guest entry;
2. open `/front/workspace` and render the document panel;
3. open `/front/questionPractice/1/practice/sequential` and render `.practice-container`;
4. open `/front/studio/create` and render `.question-panel`.

Commands:

```bat
npm run test:unit
npm run test:e2e
```

Current frontend gates: `npm run test:unit`, `npm run build:prod`, and the browser smoke script.
