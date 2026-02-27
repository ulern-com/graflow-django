# Graflow (Django App)

Graflow is a reusable Django app that exposes a flows API on top of
[Django REST Framework](https://www.django-rest-framework.org/) and
[LangGraph](https://langchain-ai.github.io/langgraph/). It helps you build and
run stateful, long-running, interactive workflows (flows) in a multi-tenant
environment.

## Highlights

- **Flows API** to get flow types, CRUD operation on flows, stats, resume, and cancellation endpoints.
- **User Interaction** based on LangGraph's human-in-the-loop.
- **Persistence** with pluggable node-cache, checkpointer and store for long-term memory (based on PostgreSQL).
- **Django admin** for inspecting flow state and store/cache tables using Django ORM (models).
- **Flow Definition and Registration** via settings or programmatically
- **Extensive tests** covering API behavior, graph execution, and storage abstractions.

---

## Project Layout

```
graflow-django/
├── graflow/                # Reusable app with models, API, graphs, and storage backends
├── myflows/                # Reference Django project (demo)
├── docs/                   # Documentation for the app
├── pyproject.toml          # Project metadata, dependencies, tooling config
├── README.md               # You are here
└── LICENCE                 # Project licence (MIT-compatible)
```

---

## Requirements

You need Python **3.12+** (project currently targets 3.13). If you use the
PostgreSQL persistence backend, you also need a PostgreSQL database.

## Installation (App Only)

```bash
pip install graflow-django  # when published
# or local editable install
pip install -e ".[dev,postgres]"
```

Add `graflow` to `INSTALLED_APPS`, run migrations, and configure:

```python
GRAFLOW_APP_NAME = "myapp"
GRAFLOW_PERSISTENCE_BACKEND = "django"  # or "memory"
GRAFLOW_REQUIRE_AUTHENTICATION = True
```

See `docs/README.md` for full configuration and usage.

## Permissions and Throttling

Graflow supports fine-grained, per-flow-type permissions and throttling for access control and rate limiting. Each `FlowType` can have separate permission and throttle classes for CRUD operations (list, create, retrieve, destroy, cancel) and resume operations.

### Quick Overview

**Permissions** control **who** can access which flows:
- Default: `IsAuthenticated` for both CRUD and resume operations
- Can be customized per flow type via `crud_permission_class` and `resume_permission_class`
- Supports custom permission classes for subscription tiers, user roles, flow ownership, etc.

**Throttling** controls **how frequently** users can perform operations:
- Default: 100 requests/hour for creation, 300 requests/hour for resume
- Can be customized per flow type via `crud_throttle_class` and `resume_throttle_class`
- Supports custom throttle classes for tiered access (premium vs. free users)

### Configuration

Configure permissions and throttling via Django admin or programmatically when creating `FlowType` instances. Specify class paths in format `module.path:ClassName` (e.g., `myapp.permissions:SubscriptionPermission`).

**Example:**
```python
flow_type = FlowType.objects.create(
    app_name="myapp",
    flow_type="premium_workflow",
    version="v1",
    builder_path="myapp.graphs:build_premium_workflow",
    state_path="myapp.graphs:PremiumWorkflowState",
    is_latest=True,
    crud_permission_class="myapp.permissions:SubscriptionPermission",
    resume_permission_class="myapp.permissions:SubscriptionPermission",
    crud_throttle_class="myapp.throttling:PremiumUserThrottle",
    resume_throttle_class="myapp.throttling:PremiumUserThrottle",
)
```

For detailed documentation, examples, and best practices, see [`docs/PERMISSIONS_AND_THROTTLING.md`](docs/PERMISSIONS_AND_THROTTLING.md).

---

## Working with Flows

1. **Register flow types** via the Django admin interface (see "Flow Type Registration" section above).
2. **Create flows** by POSTing to `/api/graflow/flows/` with a `flow_type` and optional state payload.
3. **Resume flows** via `/api/graflow/flows/<id>/resume/` when user input is required.
4. **Inspect** stats at `/api/graflow/flows/stats/` or fetch the most recent flow via `/api/graflow/flows/most-recent/`.
5. **List available flow types** at `/api/graflow/flow-types/`.

All endpoints require authentication by default; DRF session auth is enabled. You can disable authentication for demo/testing by setting `GRAFLOW_REQUIRE_AUTHENTICATION = False`.

**Cancellation semantics:** `POST /flows/<id>/cancel/` enforces business rules and
returns `400` if the flow is already completed/failed/cancelled. `DELETE /flows/<id>/`
is an idempotent soft delete that always succeeds by marking the flow cancelled so it
disappears from subsequent responses. Pick the endpoint that matches your UX needs.

---

## Persistence for Stateful Flows

Need to understand how the Django-based checkpointer, store, and cache work? Head over to `graflow/storage/README.md`. It documents:

- How `DjangoSaver`, `DjangoStore`, and `DjangoCache` wrap LangGraph’s PostgreSQL persistence layers
- Which Django models map to LangGraph tables
- When to enable the Django backend vs. in-memory persistence

Referencing that file keeps these docs close to the storage code so they stay accurate.

---

## API Documentation

- See `graflow/api/README.md` for a high-level overview of every endpoint plus regeneration instructions.
- The full OpenAPI contract lives at `docs/flows-api.schema.yml`. Regenerate it after API changes with:

  ```bash
  source .venv/bin/activate
  python manage.py spectacular --file docs/flows-api.schema.yml --format openapi
  ```

## Demo Project

The reference Django project lives in `myflows/`. See
`myflows/README.md` for setup and runtime instructions.

## Development

Development and testing notes live in `docs/DEVELOPMENT.md`.

  Commit the updated schema (and optional HTML exports) so API changes are visible in PRs without running the dev server.

---

## Testing
Make sure you have the DB running before running the tests. You can use:
```bash
docker-compose up -d
```

Then
```bash
just test
```

Note: If you run tests from a sandboxed environment (such as Codex), you may need elevated
permissions to access Docker's published ports (e.g., `127.0.0.1:5432`). Running tests directly
in your local terminal avoids this issue.

Or with coverage:

```bash
just test-cov
```

The suite spins up a fully configured Django test environment, registers sample graphs, and covers:

- API contract tests (`graflow/tests/test_flows_api.py`)
- LangGraph integrations
- Cache / store / checkpoint adapters

Tests that require PostgreSQL are automatically skipped when running against SQLite (see `test_checkpoint.py` and `test_store.py`).

---

## Development Tips

- **Format code**: `just format` (uses `black`)
- **Lint code**: `just lint` (uses `ruff`)
- **Fix linting issues**: `just lint-fix`
- **Type check**: `just type-check` (uses `mypy`)
- **Run all checks**: `just check` (lint + type-check)
- **Visualize graphs**: `python manage.py visualize_graph --flow-type your_flow` (Graphviz recommended)
- **Refer to** `graflow/tests/factories.py` for sample model factories and to bootstrap seed data

See `justfile` for all available commands. Install `just` from [https://github.com/casey/just](https://github.com/casey/just).

---

## Contributing

1. Fork the repo and create a feature branch.
2. Install dev dependencies: `pip install -e ".[dev]"`.
3. Run `just check` and `just test` to ensure everything passes before opening a PR.
4. Describe your change clearly and link related issues.

We welcome bug reports, feature requests, docs updates, and test improvements.

---

## Licence

See [`LICENCE`](./LICENCE) for the full legal text. Contributions are accepted under the same terms.
