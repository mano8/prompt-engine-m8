# prompt-engine-m8 - FastAPI Prompt Template Microservice

![CI](https://github.com/mano8/prompt-engine-m8/actions/workflows/CI.yaml/badge.svg?branch=main)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/9113c06590604fca9709d66d3b6fd64d)](https://app.codacy.com/gh/mano8/prompt-engine-m8/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade)
[![codecov](https://codecov.io/gh/mano8/prompt-engine-m8/graph/badge.svg?token=SD4GHGM24V)](https://codecov.io/gh/mano8/prompt-engine-m8)
[![Docker Pulls](https://img.shields.io/docker/pulls/tepochtli/prompt-engine-m8)](https://hub.docker.com/r/tepochtli/prompt-engine-m8)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/mano8/prompt-engine-m8/blob/main/LICENSE)

`prompt-engine-m8` is a self-hosted FastAPI service for managing reusable prompt
blocks, assembling prompt templates, and composing deterministic prompt strings
for authenticated users. It is designed as an M8 service-layer microservice:
authentication is delegated to `fa-auth-m8`, token validation is handled through
`fastapi-m8` / `auth-sdk-m8`, and persistence is backed by PostgreSQL.

The repository includes a Docker Compose development stack with Traefik,
`fa-auth-m8`, PostgreSQL, Prometheus, and Grafana. The service is mounted under
`/prompt` by default.

> The Python package directory is named `promt_engine_service` in this
> repository. That spelling is part of the current package/import contract.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Docker Compose Stack](#docker-compose-stack)
- [API Endpoints](#api-endpoints)
  - [List query parameters](#list-query-parameters)
  - [Compatibility preflight (`/meta`)](#compatibility-preflight-meta)
  - [Published contract artifact (`contracts/openapi.json`)](#published-contract-artifact-contractsopenapijson)
- [Dynamic Block Composition](#dynamic-block-composition)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [Security Defaults](#security-defaults)
- [Docker Image](#docker-image)
- [Development](#development)
- [Quality Gates](#quality-gates)
- [Dependencies](#dependencies)

---

## Features

- User-owned prompt categories
- Reusable prompt blocks
- Prompt templates composed from ordered blocks
- Dynamic content injection at compose time
- Slug lookup for prompt blocks and templates
- Owner isolation for normal users
- Superuser visibility across all records
- JWT authentication through `fastapi-m8`
- Stateful token revocation through `fa-auth-m8` private introspection
- PostgreSQL persistence with Alembic migrations
- Prometheus metrics when `METRICS_ENABLED=true`
- Docker Compose development stack with Traefik, auth, database, metrics, and Grafana
- Production Docker build from a hash-locked dependency file

---

## Architecture

```text
Browser / Frontend
       |
       v
  Traefik :9000
       | app_net
       +--> /user/*   -> fa-auth-m8 auth_user_service :8000
       +--> /prompt/* -> prompt_engine_service :8000

  prompt_engine_service
       +--> PostgreSQL on data_net
       +--> fa-auth-m8 private API for token revocation checks
       +--> JWKS endpoint for RS256 token validation
       +--> Prometheus metrics when enabled
```

The prompt service is a consumer service. It does not own authentication state
and does not connect to the auth service Redis instance. In `stateful` token
mode it checks access-token revocation over HTTP with:

```ini
INTROSPECTION_URL=http://auth_user_service:8000/user/private/v1/jti-status
INTERNAL_CLIENT_ID=prompt-engine-service
PRIVATE_API_SECRET=<consumer secret registered by fa-auth-m8>
```

---

## Docker Compose Stack

The local stack lives in:

```text
docker_compose/dev_prompt_engine_m8
```

It runs:

| Service | Purpose | Local access |
| --- | --- | --- |
| `traefik` | Edge router for `/user` and `/prompt` | `http://localhost:9000`, dashboard on `127.0.0.1:8080` |
| `auth_user_service` | Authentication issuer from `fa-auth-m8` | `/user` via Traefik |
| `prompt_engine_service` | Prompt API built from this repo | `/prompt` via Traefik |
| `m8_db` | PostgreSQL 18 database | loopback-bound DB port from `.env` |
| `redis_cache` | Auth-owned Redis for sessions/revocation | internal data network |
| `prometheus` | Metrics collection | `127.0.0.1:9090` |
| `grafana` | Dashboards | `127.0.0.1:3000` |

`app_net` carries application traffic. `data_net` is internal-only and has no
gateway; database and Redis are not exposed through that network.

---

## API Endpoints

All routes are prefixed by `API_PREFIX`, which defaults to `/prompt` in the
Compose stack.

| Tag | Method | Path | Auth | Description |
| --- | --- | --- | --- | --- |
| meta | GET | `/meta` | none | Service metadata from `fastapi-m8` |
| meta | GET | `/ping` | none | Lightweight liveness probe |
| health | GET | `/health/` | optional detail credential | Health/readiness endpoint |
| metrics | GET | `/metrics` | optional scrape credential | Prometheus metrics when enabled |
| category | GET | `/category/` | JWT | List categories visible to the current user |
| category | GET | `/category/get/{item_id}/` | JWT | Get a category |
| category | POST | `/category/add/` | JWT | Create a category |
| category | PUT | `/category/edit/{item_id}/` | JWT | Update a category |
| category | DELETE | `/category/delete/{item_id}/` | JWT | Delete a category |
| prompt-block | GET | `/prompt-block/` | JWT | List prompt blocks |
| prompt-block | GET | `/prompt-block/export/` | JWT | Export every prompt block in the filtered set |
| prompt-block | GET | `/prompt-block/get/{item_id}/` | JWT | Get a prompt block by ID |
| prompt-block | GET | `/prompt-block/get_by_slug/{item_slug}/` | JWT | Get a prompt block by slug |
| prompt-block | POST | `/prompt-block/add/` | JWT | Create a prompt block |
| prompt-block | PUT | `/prompt-block/edit/{item_id}/` | JWT | Update a prompt block |
| prompt-block | DELETE | `/prompt-block/delete/{item_id}/` | JWT | Delete an unused prompt block |
| prompt-template | GET | `/prompt-template/` | JWT | List prompt templates with blocks |
| prompt-template | GET | `/prompt-template/export/` | JWT | Export every prompt template in the filtered set |
| prompt-template | GET | `/prompt-template/get/{item_id}/` | JWT | Get a prompt template by ID |
| prompt-template | GET | `/prompt-template/get_by_slug/{item_slug}/` | JWT | Get a prompt template by slug |
| prompt-template | GET | `/prompt-template/get-blocks/{item_id}/` | JWT | Get ordered template blocks |
| prompt-template | POST | `/prompt-template/compose/{item_id}/` | JWT | Compose a template into final prompt text |
| prompt-template | POST | `/prompt-template/add/` | JWT | Create a prompt template |
| prompt-template | PUT | `/prompt-template/edit/{item_id}/` | JWT | Update a prompt template |
| prompt-template | DELETE | `/prompt-template/delete/{item_id}/` | JWT | Delete a prompt template |
| prompt-template | POST | `/prompt-template/{template_id}/add-block/{block_id}/` | JWT | Attach a block to a template |
| prompt-template | PUT | `/prompt-template/{template_id}/set-block-position/{block_id}/` | JWT | Reorder a template block |
| prompt-template | DELETE | `/prompt-template/{template_id}/delete-block/{block_id}/` | JWT | Remove a block from a template |
| dashboard | GET | `/dashboard/users/activity/` | JWT | All-user prompt activity summary |
| dashboard | GET | `/dashboard/users/activity/current/` | JWT | Current-user prompt activity summary |

### List query parameters

`GET /prompt-block/`, `GET /prompt-template/` and `GET /category/` accept
`skip`/`limit` plus a declared, additive list-query vocabulary — every value
is validated against an allow-list published in the OpenAPI document
(`promt_engine_service/schemas/list_params.py`); an undeclared value is
rejected with `422`, never silently ignored.

| Param | Meaning | `prompt-block` | `prompt-template` | `category` |
| --- | --- | --- | --- | --- |
| `q` | Free-text search, bound as a parameter (never interpolated) | `name`, `slug`, `description`, `content` | `name`, `slug`, `description` | `name`, `slug` |
| `csrc` | Restrict `q` to one of its columns | same as `q` | same as `q` | not offered |
| `sort` | Column to order by | `id`, `name`, `slug`, `type`, `is_dynamic`, `is_public`, `created_at`, `updated_at` | `id`, `name`, `slug`, `is_public`, `block_count`, `created_at`, `updated_at` | `id`, `name`, `slug`, `type`, `created_at`, `updated_at` |
| `order` | `asc` \| `desc` | ✓ | ✓ | ✓ |
| `f` | Comma-joined facet values, combined with `OR` | block type axis + `dynamic`/`static`/`public`/`private` | `public`/`private` | not offered |

Notes:

- `limit` is bounded at `MAX_PAGE_SIZE = 500` (published as `maximum` in the
  OpenAPI schema); `q` is bounded at `MAX_SEARCH_LENGTH = 200` characters.
  `q` compiles to a leading-wildcard `LIKE` over every declared column —
  `content` included, which is unindexed text — so the request payload is
  bounded even though the underlying scan is a function of table size and
  indexing rather than of `limit`.
- `count` in every list response is the **filtered** count, not the count of
  everything visible to the caller. A client that never sends `q`/`f` sees no
  difference; one that does gets a paginator that agrees with its own result
  set.
- `sort=block_count` on `GET /prompt-template/` orders by the number of
  attached blocks via a correlated subquery — it is not a real column.
- Every route also answers plain `skip`/`limit` unchanged; the new parameters
  are additive and optional.

### Bulk export (`A-C8`)

`GET /prompt-block/export/` and `GET /prompt-template/export/` carry the same
`q`/`csrc`/`sort`/`order`/`f` vocabulary as their list counterparts but accept
no `skip`/`limit` — they answer the *whole* filtered set in one response, not
one page of it. That is the point: a list route with a `limit` of 500 cannot
answer "export everything currently filtered to" without a client stitching
pages together, which is what a bulk-export button actually needs.

Bounded by `MAX_EXPORT_SIZE = 5000` instead of a caller-supplied `limit`: a
filtered set larger than that returns the first `MAX_EXPORT_SIZE` rows with
`truncated: true` on the response rather than materialising an unbounded
result. A caller that hits the cap narrows the filter.

### Compatibility preflight (`/meta`)

`GET /meta` (mounted with no auth requirement) publishes
`CONTRACT_NAME = "prompt-engine-m8"`, `CONTRACT_VERSION`, `CONTRACT_RANGE`
(currently `>=2.1.0 <3.0.0`) and `SERVICE_VERSION` alongside the generic
`fastapi-m8` service metadata. `GET /ping` is the dependency-free liveness
probe — `astro-prompt-m8`'s server-only `ping()` calls this route, not the
unmounted API-prefix root. `@mano8/astro-prompt-m8/compatibility` mirrors
`CONTRACT_RANGE` and is wired into `PromptProvider`, which runs the preflight
once per session and renders an incompatibility state instead of proceeding
silently against a service outside its supported range.

Interactive docs are available at:

```text
http://localhost:9000/prompt/docs
```

when `SET_DOCS=true`.

### Published contract artifact (`contracts/openapi.json`)

`contracts/openapi.json` is this service's OpenAPI document, committed as a
file. It is the same spec `GET /prompt/openapi.json` serves, serialised with
sorted keys and LF endings so a diff shows the contract change rather than a
reordering or a checkout's line endings.

It exists so a consumer has something to diff against. The list vocabulary,
the required body fields and the mutating verbs are all published here, and a
client that pins this contract can compare its own request and response
schemas against the file instead of reading service source — which is how
`astro-prompt-m8`'s `verify:contract-drift` gate works. Nothing in this
repository reads a consumer; the artifact is published, and the diff is the
consumer's side of the wire.

`test_openapi_snapshot.py` fails when the file and the served document
disagree, so the artifact can never describe a service that no longer exists.
Refresh it after any change to a route, a schema or the list vocabulary:

```bash
PROMPT_ENGINE_M8_WRITE_OPENAPI=1 pytest tests/test_openapi_snapshot.py
```

Read the resulting diff as the contract change it is, and hand it to the
consumers that pin this contract.

---

## Dynamic Block Composition

Prompt templates are composed from ordered static and dynamic blocks. Static
blocks render their stored `content` exactly as authored. Dynamic blocks can use
the placeholder token `{{dynamic_content}}` inside their stored `content` to mark
where the runtime replacement value should be inserted.

Example dynamic block content:

```text
Use this source text:
{{dynamic_content}}
Return only bullets.
```

Compose payload:

```json
[
  { "id": 2, "content": "Summarize the release notes." }
]
```

Rendered dynamic block:

```text
Use this source text:
Summarize the release notes.
Return only bullets.
```

The payload item `id` is the prompt block ID and `content` is the runtime
replacement value. If a dynamic block does not contain `{{dynamic_content}}`, the
service keeps the current compatibility path and renders the replacement value
as the whole dynamic block. New dynamic blocks should include the placeholder so
authored surrounding text is preserved. Static blocks do not interpret
`{{dynamic_content}}`; if the token appears in static content, it is rendered
literally.

---

## Quick Start

### 1. Prepare env files

```bash
cd docker_compose/dev_prompt_engine_m8
cp .env.example .env
cp auth.env.example auth.env
cp prompt.env.example prompt.env
cp grafana.env.example grafana.env
```

Replace every `changethis` value before starting the stack.

### 2. Check the most important prompt settings

In `prompt.env`, the prompt service should use:

```ini
API_PREFIX=/prompt
AUTH_SERVICE_ROLE=consumer
AUTH_PREFIX=/user
SELECTED_DB=Postgres
DB_HOST=m8_db
DB_DATABASE=prompt_engine_db
ACCESS_TOKEN_ALGORITHM=RS256
JWKS_URI=http://auth_user_service:8000/user/.well-known/jwks.json
TOKEN_MODE=stateful
INTROSPECTION_URL=http://auth_user_service:8000/user/private/v1/jti-status
INTERNAL_CLIENT_ID=prompt-engine-service
```

Use the same `TOKEN_ISSUER`, compatible `TOKEN_AUDIENCE`, and
`EVENT_SIGNING_KEY` values expected by the auth stack.

### 3. Generate local keys and certificates

```bash
bash init.sh
```

On Windows, run this from Git Bash or WSL.

### 4. Start the stack

```bash
docker compose up -d --build
```

### 5. Verify

```http
GET http://localhost:9000/prompt/health/
GET http://localhost:9000/prompt/docs
GET http://localhost:9000/user/.well-known/jwks.json
```

Useful local URLs:

| What | URL |
| --- | --- |
| Auth docs | `http://localhost:9000/user/docs` |
| Prompt docs | `http://localhost:9000/prompt/docs` |
| JWKS | `http://localhost:9000/user/.well-known/jwks.json` |
| Prompt metrics | `http://localhost:9000/prompt/metrics` |
| Traefik dashboard | `http://localhost:8080` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` |

---

## Environment Variables

The stack uses three main runtime files:

| File | Purpose |
| --- | --- |
| `.env` | Infrastructure/bootstrap values for PostgreSQL, Redis, ports, and database creation |
| `auth.env` | Runtime configuration for `fa-auth-m8` |
| `prompt.env` | Runtime configuration for `prompt_engine_service` |

Prompt-specific values are intentionally small. Most service settings come from
`fastapi-m8`'s `ConsumerServiceSettings`.

Important prompt service variables:

| Variable | Description |
| --- | --- |
| `API_PREFIX` | Public route prefix, usually `/prompt` |
| `DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USER`, `DB_PASSWORD` | Prompt database connection |
| `ACCESS_TOKEN_ALGORITHM` | Token algorithm expected from `fa-auth-m8` |
| `JWKS_URI` | JWKS endpoint for RS256/ES256 validation |
| `TOKEN_MODE` | `stateful`, `hybrid`, or `stateless`; local stack uses `stateful` |
| `INTROSPECTION_URL` | Auth private API revocation endpoint |
| `INTERNAL_CLIENT_ID` | Consumer id registered in the auth private API config |
| `PRIVATE_API_SECRET` | Consumer secret for auth private API calls |
| `TOKEN_ISSUER`, `TOKEN_AUDIENCE` | Strict token claim validation values |
| `EVENT_SIGNING_KEY` | Shared key for signed auth event payloads when event signing is enabled |
| `METRICS_ENABLED` | Enables `/prompt/metrics` |

All real env files contain secrets and must stay untracked. Only `*.example`
files belong in Git.

---

## Security Defaults

- The service is a consumer of `fa-auth-m8`; it does not issue tokens.
- JWT validation is handled locally with `fastapi-m8` and `auth-sdk-m8`.
- RS256 validation should use `JWKS_URI` so key rotation can happen at the auth service.
- In `stateful` mode, revocation checks go through the auth private API.
- Auth Redis remains private to `fa-auth-m8`; the prompt service must not connect to it directly.
- Normal users can only see and mutate their own categories, blocks, and templates.
- Superusers can read across users for administrative use.
- The production Docker image installs dependencies from `requirements_prod.lock`
  with `--require-hashes`.
- The runtime image runs as a non-root `appuser`.
- The Compose service drops Linux capabilities, uses `no-new-privileges`, mounts
  a read-only filesystem, and provides writable `tmpfs` only for `/tmp` and `/run`.

---

## Docker Image

The publish workflow builds:

```text
${DOCKERHUB_USERNAME}/prompt-engine-m8
```

Release builds:

- build multi-arch images for `linux/amd64` and `linux/arm64`
- scan the image with Trivy
- generate an SPDX SBOM
- sign the published image with keyless OIDC signing
- attach SBOM and Trivy JSON reports to GitHub releases

Build locally:

```bash
docker build -f promt_engine_service/Dockerfile -t prompt-engine-m8:local .
```

---

## Development

### Run locally without Docker

```bash
pip install -r promt_engine_service/requirements_dev.txt
uvicorn promt_engine_service.main:app --host 0.0.0.0 --port 8000 --reload
```

For local non-Docker runs, provide a valid `.env` for
`promt_engine_service/core/config.py` to load.

### Database migrations

Container startup runs:

```bash
alembic -c /opt/promt_engine_service/alembic.ini upgrade head
```

The startup script can generate an initial migration when the mounted
`shared_migrations/prompt_engine/versions` directory is empty. In normal
development, prefer the Compose flow and keep generated migrations owned by the
stack lifecycle.

### VS Code debugging

Set:

```ini
VSCODE_DEBUG=true
```

The container starts `debugpy` on port `5678` and waits for the debugger before
starting Uvicorn.

---

## Quality Gates

The CI workflow enforces:

```bash
ruff format --check .
ruff check .
mypy promt_engine_service --ignore-missing-imports
pytest --cov-report=xml --cov-fail-under=100   # includes the contracts/openapi.json artifact check
bandit -r promt_engine_service -x promt_engine_service/alembic --severity-level medium
pip-audit -r promt_engine_service/requirements_dev.txt
docker build -f promt_engine_service/Dockerfile -t prompt-engine-m8:ci-scan .
```

Coverage is required to stay at `100%`.

To regenerate the production dependency lock:

```bash
pip-compile --generate-hashes --no-emit-index-url \
  --output-file=promt_engine_service/requirements_prod.lock \
  promt_engine_service/requirements_prod.txt
```

---

## Dependencies

**Stack:** Python 3.14, FastAPI, SQLModel, PostgreSQL, Traefik, Docker Compose,
Prometheus, Grafana

- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLModel](https://sqlmodel.tiangolo.com/)
- [Alembic](https://alembic.sqlalchemy.org/)
- [fastapi-m8](https://github.com/mano8/fastapi-m8) - consumer service wiring, auth dependencies, health, metrics
- [auth-sdk-m8](https://github.com/mano8/auth-sdk-m8) - JWT validation, JWKS, shared auth schemas
- [fa-auth-m8](https://github.com/mano8/fa-auth-m8) - authentication issuer and private revocation API
- [Prometheus](https://prometheus.io/)
- [Grafana](https://grafana.com/)

---

## License

Apache-2.0
