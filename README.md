# Graflow Django

This is a Django app plus a reference Django project that has a simple flows API built on top of [Django REST Framework](https://www.django-rest-framework.org/) and [LangGraph](https://langchain-ai.github.io/langgraph/). It's A WAY to build and run stateful, long-running, and interactive workflows (flows) in a multi-tenant environment.

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
├── myflows/                # Reference Django project wiring the app + DRF
├── manage.py               # Standard Django entry point
├── pyproject.toml          # Project metadata, dependencies, tooling config
├── README.md               # You are here
└── LICENCE                 # Project licence (MIT-compatible)
```

---

## Requirements

You need Python **3.12+** (project currently targets 3.13). You can install all required Python packages using pip command. See **Quick Start** section. You also need API keys if you are using LLM calls in your flows.

---

## Quick Start

To get the idea, you can run this Django project like other Django project. If you want to use the Django app as a 3rd party app in your own Django project, see the **Configuration** sectioin.

```bash
git clone https://github.com/ulern-com/graflow-django.git
cd graflow-django

python -m venv .venv
source .venv/bin/activate

# Install with PostgreSQL support (required for production)
pip install -e ".[dev,postgres]"

# Start PostgreSQL (using Docker Compose)
docker-compose up -d

# Or use your own PostgreSQL instance and configure DB_* environment variables
# Create .env file with your database credentials:
# DB_NAME=myflows
# DB_USER=postgres
# DB_PASSWORD=postgres
# DB_HOST=127.0.0.1  # Use 127.0.0.1 (not localhost) to avoid IPv6 connection issues
# DB_PORT=5432

python manage.py migrate
python manage.py createsuperuser  # optional, for admin access
python manage.py runserver
```

Visit `http://localhost:8000/api/graflow/flows/` to explore the DRF browsable API.

**Note:** This project requires PostgreSQL to demonstrate the full benefits of graflow's storage, cache, and checkpoint implementations. SQLite is not supported for the Django persistence backend.

Also note that to run a flow with LLM call, you need to set your own API key in the environment.

---

## Configuration

All settings of this Django project live in `myflows/settings.py`. Environment-specific overrides can be provided via `.env`.

### Database Configuration

The project uses PostgreSQL by default. Configure it via environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `DB_NAME` | `myflows` | PostgreSQL database name |
| `DB_USER` | `postgres` | PostgreSQL user |
| `DB_PASSWORD` | `postgres` | PostgreSQL password |
| `DB_HOST` | `127.0.0.1` | PostgreSQL host (use 127.0.0.1, not localhost, to avoid IPv6 issues) |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_SSLMODE` | `disable` | SSL mode for connection |

### Graflow Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `GRAFLOW_APP_NAME` | `myflows` | Logical namespace for graphs and flows |
| `GRAFLOW_PERSISTENCE_BACKEND` | `django` | `django` (requires PostgreSQL) or `memory` for testing |
| `GRAFLOW_NODE_CACHE_TTL` | 2592000 (30 days) | Cache TTL for LangGraph node results |
| `GRAFLOW_REQUIRE_AUTHENTICATION` | `True` | Require authentication for API access |
| `GRAFLOW_GRAPHS` | `[]` | List of graph configurations for static registration |

Tests default to the in-memory backend so they run without PostgreSQL. Production must use PostgreSQL to enable the Django store, cache, and checkpointer implementations.

### Static Graph Registration

You can register graphs statically via the `GRAFLOW_GRAPHS` setting:

```python
GRAFLOW_GRAPHS = [
    {
        'app_name': 'myflows',
        'flow_type': 'my_workflow',
        'version': 'v1',
        'builder': 'myapp.graphs.my_workflow:build_workflow',  # module.path:function_name
        'state': 'myapp.graphs.my_workflow:WorkflowState',     # module.path:class_name
        'is_latest': True,
    },
]
```

Graphs defined in settings are automatically registered when Django starts. You can also register graphs programmatically using `register_graph()` (useful for tests or dynamic registration).

---

## Working with Flows

1. **Register graphs** via Django settings (`GRAFLOW_GRAPHS` in `myflows/settings.py`) or programmatically using `register_graph()` (see `graflow/tests/fixtures/test_graph.py` for examples).
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

## Persistence For Stateful Flows

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

  Commit the updated schema (and optional HTML exports) so API changes are visible in PRs without running the dev server.

---

## Testing

```bash
just test
```

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
