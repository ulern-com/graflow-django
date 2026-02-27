# Myflows Demo Project

This directory contains the reference Django project used to demonstrate the
`graflow` app. It wires up Django REST Framework + the Graflow viewsets and
provides a runnable example API.

If you want to integrate Graflow into your own Django project, use the root
README instead. This document is only for the demo project.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate

# Install with PostgreSQL support (required for persistence backend)
pip install -e ".[dev,postgres]"

# Start PostgreSQL (using Docker Compose from repo root)
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

## Configuration

All settings live in `myflows/settings.py`. Environment-specific overrides can
be provided via `.env`.

### Database Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `DB_NAME` | `myflows` | PostgreSQL database name |
| `DB_USER` | `postgres` | PostgreSQL user |
| `DB_PASSWORD` | `postgres` | PostgreSQL password |
| `DB_HOST` | `127.0.0.1` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_SSLMODE` | `disable` | SSL mode for connection |

### Graflow Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `GRAFLOW_APP_NAME` | `myflows` | Logical namespace for graphs and flows |
| `GRAFLOW_PERSISTENCE_BACKEND` | `django` | `django` (requires PostgreSQL) or `memory` for testing |
| `GRAFLOW_NODE_CACHE_TTL` | 2592000 (30 days) | Cache TTL for LangGraph node results |
| `GRAFLOW_REQUIRE_AUTHENTICATION` | `True` | Require authentication for API access |

## Flow Type Registration

Flow types (graphs) are registered via the Django admin interface using the
`FlowType` model. This provides a database-backed registry that supports
multi-tenancy, versioning, and per-flow-type permissions/throttling.

To register a flow type:
1. Go to the Django admin interface
2. Navigate to "Flow Types"
3. Click "Add Flow Type"
4. Fill in the required fields:
   - `app_name`
   - `flow_type`
   - `version`
   - `builder_path`
   - `state_path`
   - `is_latest`
   - `is_active`

You can also configure permissions and throttling per flow type by specifying
class paths (e.g., `myapp.permissions:CustomPermission`).

## API Overview

- `GET /api/graflow/flows/` list flows
- `POST /api/graflow/flows/` create a flow
- `POST /api/graflow/flows/{id}/resume/` resume a flow
- `POST /api/graflow/flows/{id}/cancel/` cancel a flow
- `GET /api/graflow/flows/stats/` stats by status/type
- `GET /api/graflow/flows/most-recent/` most recent flow
- `GET /api/graflow/flow-types/` list registered flow types

For complete endpoint details, see `graflow/api/README.md` and the OpenAPI
schema in `docs/flows-api.schema.yml`.
