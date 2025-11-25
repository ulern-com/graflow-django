# Graflow API

This directory hosts the Django REST Framework viewset that exposes the Graflow
Flows API. All endpoints live under `/api/graflow/` and are fully described by
the OpenAPI schema that ships with the repo.

## Artifact overview

| File | Description |
| --- | --- |
| `docs/flows-api.schema.yml` | OpenAPI 3.0 contract generated via `drf-spectacular`. |

## Regenerating the schema

Whenever you touch the viewset, serializers, or throttles, regenerate the schema
so the docs stay in sync:

```bash
source .venv/bin/activate
python manage.py spectacular --file docs/flows-api.schema.yml --format openapi
```

The command runs entirely offline; no server has to be running. Commit the
updated YAML alongside your change so reviewers can spot API diffs easily.

## Endpoint summary

| Endpoint | Method(s) | Notes |
| --- | --- | --- |
| `/flows/` | `GET`, `POST` | List/create flows. Supports `status`, `flow_type`, and `state__*` filters. |
| `/flows/{id}/` | `GET`, `DELETE` | Retrieve or delete a flow owned by the current user. |
| `/flows/{id}/resume/` | `POST` | Resume execution. Response includes flow metadata plus `state_update`. |
| `/flows/{id}/cancel/` | `POST` | Cancel a flow (terminal action). |
| `/flows/stats/` | `GET` | Aggregated counts by status/type. |
| `/flows/most-recent/` | `GET` | Fetch the latest flow (optionally filtered by status or type). |
| `/flow-types/` | `GET` | Enumerate registered flow types. Filtered to the authenticated user’s graphs. |

All endpoints require authentication unless `GRAFLOW_REQUIRE_AUTHENTICATION`
is set to `False`.

### Cancel vs Delete

- `POST /flows/{id}/cancel/` enforces business rules. It returns `400` if the flow
  is already in a terminal state (completed/failed/cancelled), so clients know
  they attempted to cancel something that already finished.
- `DELETE /flows/{id}/` is an idempotent soft-delete. It always succeeds, even for
  completed flows, by marking the flow as `cancelled` so it no longer appears in
  list/detail responses.

Choose the one that matches your UX: use `/cancel/` when you need explicit
validation, and `DELETE` when you just want to hide the flow regardless of
its current state.

## Rendering HTML docs (optional)

If you prefer Redoc/Swagger style docs, you can turn the YAML into static HTML:

```bash
npx redoc-cli bundle docs/flows-api.schema.yml -o docs/flows-api.html
```

Commit the resulting `docs/flows-api.html` if you want a browsable artifact in
CI, or generate it ad hoc when you need to inspect the contract locally.

