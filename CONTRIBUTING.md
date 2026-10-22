# Contributing

## Commit messages

Conventional Commits with a scope:

```text
<type>(<scope>): <description>
```

```text
[optional body]
```

- Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `style`, `ai`
- Scope: repo name or subsystem (e.g. `winter-service-process-compose`, `manifest`)
- The `/wf-commit` skill from [winter-workflow](https://github.com/paul-gross/winter-workflow) generates commits in this
  format

## Pre-commit checks

Markdown: every `.md` file here is held to the mechanical style gates `dprint.json` and `.rumdl.toml` declare — run both
before pushing any documentation change, and note that one of them writes its own fix:

```bash
dprint check          # dprint fmt to apply
rumdl check .         # rumdl check . --fix for the autofixable subset
```

They also run through `winter lint`: the `winter-context` extension contributes the check, and committing these two
configs is what opts this repo into it.

Bash scripts: `bash -n <file>` catches syntax errors; `winter doctor` exercises the probe. No automated pre-commit hook.

Python (`src/process_compose_orchestrator/`, `tests/`): run these before pushing any Python changes. Requires Python
3.11+ (`tomllib` is stdlib from 3.11; the current dev env uses 3.12).

```bash
uv run pytest          # must be green
uv run ruff check .    # lint
uv run pyright         # typecheck
```

Or via mise tasks if configured:

```bash
mise run test
mise run lint
mise run typecheck
```

The `process_compose_orchestrator` runtime has no third-party dependencies (stdlib-only). The dev tooling (pytest, ruff,
pyright) lives in `pyproject.toml`'s `[dependency-groups] dev` and is installed via `uv sync`.

## No-real-binary test approach

Unit tests never require a running process-compose daemon. Every external system sits behind a Protocol seam with an
in-memory fake in `tests/fakes.py`.
