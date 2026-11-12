# OpenStudy quality task runner.
# Windows developers: run scripts\verify-quality.bat directly.
# This Makefile is a portable shorthand for CI/Unix contributors.

.PHONY: verify backend-check frontend-check build clean

verify: backend-check frontend-check

backend-check:
	cd openstudy-fastapi && .venv/Scripts/python.exe -m compileall -q app
	cd openstudy-fastapi && .venv/Scripts/python.exe -m ruff check app --select E9,F63,F7,F82
	cd openstudy-fastapi && .venv/Scripts/python.exe -m pytest tests -q

frontend-check:
	cd openstudy-vue3-ts && npm run lint
	cd openstudy-vue3-ts && npm run build:prod
	cd openstudy-vue3-ts && npm run type-check

build:
	cd openstudy-vue3-ts && npm run build:prod

clean:
	rm -rf openstudy-vue3-ts/dist openstudy-vue3-ts/.tmp-build
