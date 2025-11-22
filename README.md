# Graflow Django

This is a Django app plus a reference Django project that has a simple flows API built on top of [Django REST Framework](https://www.django-rest-framework.org/) and [LangGraph](https://langchain-ai.github.io/langgraph/). It's A WAY to build and run stateful, long-running, and interactive workflows (flows) in a multi-tenant environment.

## Highlights

- **Flows API** to get flow types, CRUD operation on flows, stats, resume, and cancellation endpoints.
- **User Interaction** based on LangGraph's human-in-the-loop.
- **Persistence** with pluggable node-cache, checkpointer and store for long-term memory (based on PostgreSQL).
- **Django admin** for inspecting flow state and store/cache tables using Django ORM (models).
- **Flow Deifnition and Registration**
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

pip install -e ".[dev]"

python manage.py migrate
python manage.py createsuperuser  # optional, for admin access
python manage.py runserver
```

Visit `http://localhost:8000/api/graflow/flows/` to explore the DRF browsable API (login required).

Note that to run a flow with LLM call, you need to set your own API key in the environment.

---

## Configuration

All settings of this Django project live in `myflows/settings.py`. Environment-specific overrides can be provided via `.env`, e.g.:

| Variable | Default | Description |
| --- | --- | --- |
| `GRAFLOW_APP_NAME` | `myflows` | Logical namespace for graphs and flows |
| `GRAFLOW_PERSISTENCE_BACKEND` | `django` | `django` (PostgreSQL or any other configured DB) or `memory` |
| `GRAFLOW_NODE_CACHE_TTL` | 2592000 (30 days) | Cache TTL for LangGraph node results |

Tests default to the in-memory backend so they run without PostgreSQL. Production should use PostgreSQL to enable the Django store, cache, and checkpointer implementations. Just configure your Django project with PostgreSQL DB and everything should work.

---

## Working with Flows

1. **Register graphs** in `graflow/graphs/registry.py` or via app startup (see `graflow/tests/fixtures/test_graph.py` for examples).
2. **Create flows** by POSTing to `/api/graflow/flows/` with a `flow_type` and optional state payload.
3. **Resume flows** via `/api/graflow/flows/<id>/resume/` when user input is required.
4. **Inspect** stats at `/api/graflow/flows/stats/` or fetch the most recent flow via `/api/graflow/flows/most-recent/`.

All endpoints require authentication; DRF session auth is enabled by default.

---

## Testing

```bash
pytest
```

The suite spins up a fully configured Django test environment, registers sample graphs, and covers:

- API contract tests (`graflow/tests/test_flows_api.py`)
- LangGraph integrations
- Cache / store / checkpoint adapters

Tests that require PostgreSQL are automatically skipped when running against SQLite (see `test_checkpoint.py` and `test_store.py`).

---

## Development Tips

- Format & lint using the configured tools (`ruff`, `black`, etc.) defined in `pyproject.toml`.
- Use `python manage.py visualize_graph --flow-type your_flow` to inspect graph structure (Graphviz recommended).
- Refer to `graflow/tests/factories.py` for sample model factories and to bootstrap seed data.

---

## Contributing

1. Fork the repo and create a feature branch.
2. Install dev dependencies: `pip install -e ".[dev]"`.
3. Run `pytest` and ensure linting passes before opening a PR.
4. Describe your change clearly and link related issues.

We welcome bug reports, feature requests, docs updates, and test improvements.

---

## Licence

See [`LICENCE`](./LICENCE) for the full legal text. Contributions are accepted under the same terms.
