# Development

## Tests

This repo uses Django models backed by PostgreSQL, so tests require a running
PostgreSQL instance.

From the repo root:

```bash
docker-compose up -d
just test
```

With coverage:

```bash
just test-cov
```

If you run tests from a sandboxed environment (such as Codex), you may need
elevated permissions to access Docker's published ports (e.g., `127.0.0.1:5432`).
Running tests directly in your local terminal avoids this issue.

## Formatting and Linting

- `just format` (black)
- `just lint` (ruff)
- `just lint-fix`
- `just type-check` (mypy)
- `just check` (lint + type-check)
