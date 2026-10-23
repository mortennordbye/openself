# AGENTS.md

Guidance for coding agents (Claude Code and others) working in this repository.

## Commands

| Task | Command |
| ---- | ------- |
| Test | `make test` (the sync tests need age 1.3 on the PATH) |
| Lint the example profile | `python3 -m openself lint --strict example` |
| Docs site | `make docs-build` (strict), `make docs` to preview |
| Diagrams | `make diagram`, then commit the `.d2`, `.svg` and `.png` (needs Docker) |

## Layout

- `SPEC.md`: the format, schema 1. `schema/v1/`: the JSON Schemas. `CHANGELOG.md`: format changes.
- `openself/`: the library and CLI (`python3 -m openself`). `openself/web/`: the web app.
- `labels/`: section headings and labels per language. `tech-names.txt`: canonical tech names.
- `example/`: a complete fictional profile (Ola Eksempel).
- `tests/`: unittest suites. `docs/`: the docs site, `docs/assets/diagrams/`: D2 sources and renders.

## Conventions

- Standard library only, Python 3.10 or newer.
- Never put real personal data anywhere: code, tests, docs, commits, issues, pull requests.
- A format change follows SPEC.md section 6 and goes in CHANGELOG.md.
- Pull request titles follow Conventional Commits (see CONTRIBUTING.md); they become the squash
  commit release-please reads.
- Never commit secrets or credentials.
- Open a pull request; don't push directly to `main`.
