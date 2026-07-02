# dev_local_prompt_m8

Local dev stack for `prompt_engine_service` on the full hardened M8 platform:
`auth_user_service` (issuer) + `media_service` + `prompt_engine_service`, plus
the async workers and infrastructure.

Same hardened posture as the media hardened stack (PostgreSQL 18, two Redis
instances (auth + media), MinIO, ClamAV, Traefik, Prometheus, Grafana,
RS256/JWKS auth, container hardening, network segmentation), with one developer
convenience: **all application services are built from local source** (the
sibling repos `../../../fa-auth-m8`, `../../../media-service-m8`,
`../../../media-worker-m8`, and this repo) instead of pulling published images,
and **MinIO is published on loopback** (`127.0.0.1:9005`/`9006`) for host access.

> For a lean prompt-only stack (just `auth_user_service` + `prompt_engine_service`,
> no media/storage/scan/worker components), use
> [`../dev_prompt_engine_m8`](../dev_prompt_engine_m8).

## Architecture

```text
Browser / Frontend
       |
       v
  Traefik :9000
       | app_net
       +--> /user/*   -> auth_user_service :8000   (RS256 issuer)
       +--> /media/*  -> media_service :8000        (RS256 consumer via JWKS)
       +--> /prompt/* -> prompt_engine_service :8000 (RS256 consumer via JWKS)

  prompt_engine_service
       +--> PostgreSQL (prompt_engine_db) on data_net
       +--> auth_user_service private API (HTTP introspection) for token revocation

  media_service
       +--> PostgreSQL (media_db) on data_net
       +--> auth_user_service private API (HTTP introspection) for token revocation
       +--> Media Redis on data_net for queues/rate limits/cache
       +--> MinIO on data_net
```

`app_net` is external-facing for Traefik, app services, and observability.
`data_net` is internal and has no gateway; DB, Redis, and MinIO are not exposed
through that network (MinIO additionally publishes loopback-only host ports for
dev convenience).

> **Token revocation:** consumers do **not** connect to the auth Redis. In
> `stateful` mode each consumer queries the auth service's private introspection
> endpoint (`INTROSPECTION_URL` → `/user/private/v1/jti-status`) over HTTP. The
> auth Redis (`redis_cache`) is used only by `auth_user_service`.

## Services

| Service | Image/build | Local access |
| --- | --- | --- |
| traefik | `traefik:v3.7.5` | `:8000`, `:4430`, `127.0.0.1:9000`, `127.0.0.1:8080` |
| auth_user_service | local `../../../fa-auth-m8` build | `/user` via Traefik |
| media_service | local `../../../media-service-m8` build | `/media` via Traefik |
| media_service_worker | local `../../../media-service-m8` build (arq command override) | internal — no port; lifecycle/outbox crons |
| media_worker | local `../../../media-worker-m8` build | internal — enqueue-driven (scan + variants) |
| prompt_engine_service | local `../../` build (this repo) | `/prompt` via Traefik |
| clamav | `clamav/clamav:1.5-debian13-slim` | internal `scan_net` only |
| m8_db | `postgres:18.4-alpine` | internal data network |
| redis_cache | `redis:8.8.0-alpine` | auth Redis — internal data network |
| media_redis_cache | `redis:8.8.0-alpine` | media Redis — internal data network |
| minio | `quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z.hotfix.7aa24e772` | `127.0.0.1:9005` API, `127.0.0.1:9006` console |
| minio-init | `quay.io/minio/mc:RELEASE.2025-08-13T08-35-41Z` | one-shot: buckets + `media-rw` policy |
| prometheus | `ubuntu/prometheus:3.11-26.04_stable` | `127.0.0.1:9090` |
| grafana | `grafana/grafana:13.1.0-25530058790` | `127.0.0.1:3000` |

A one-shot `cert-init` (`alpine:3.21.3`) generates local TLS certs before
Traefik starts.

## Setup

From `docker_compose/dev_local_prompt_m8`:

```sh
cp .env.example .env
cp auth.env.example auth.env
cp media.env.example media.env
cp worker.env.example worker.env
cp prompt.env.example prompt.env
cp grafana.env.example grafana.env
cp test.env.example test.env   # live-test runner config (edit before running tests)
```

Edit `.env` (infrastructure / bootstrap):

```ini
DB_USER=<postgres-superuser>
DB_PASSWORD=<postgres-superuser-password>
AUTH_DB_USER=<auth-db-user>
AUTH_DB_PASSWORD=<auth-db-password>
AUTH_DB_NAME=auth_db
MEDIA_DB_USER=<media-db-user>
MEDIA_DB_PASSWORD=<media-db-password>
MEDIA_DB_NAME=media_db
PROMPT_DB_USER=<prompt-db-user>
PROMPT_DB_PASSWORD=<prompt-db-password>
PROMPT_DB_NAME=prompt_engine_db
REDIS_PASSWORD=<auth-redis-password>
MEDIA_REDIS_PASSWORD=<media-redis-password>
MINIO_ROOT_USER=<minio-root-user>
MINIO_ROOT_PASSWORD=<minio-root-password>
```

`init-db.sh` provisions a per-service PostgreSQL user + database from each
`*_DB_*` triplet on first volume init. Each service then connects with the
generic `DB_USER` / `DB_PASSWORD` / `DB_DATABASE` names in its own env file:

- `auth.env` → `AUTH_DB_*`, plus `REDIS_PASSWORD` to match `.env` (only
  `auth_user_service` connects to the auth Redis).
- `media.env` → `MEDIA_DB_*`, plus the `MEDIA_REDIS_*` and `MINIO_*` values.
- `prompt.env` → `PROMPT_DB_*`:

  ```ini
  DB_DATABASE=prompt_engine_db
  DB_USER=<same-as-PROMPT_DB_USER>
  DB_PASSWORD=<same-as-PROMPT_DB_PASSWORD>
  ```

The `minio-init` one-shot provisions a MinIO user from `media.env`'s
`MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` (the media-rw credentials, not the MinIO
root user). `prompt_engine_service` uses no object storage.

### Secure-by-default settings (auth-sdk-m8 2.1.1)

`auth.env`, `media.env`, and `prompt.env` each ship with two boot-required
blocks. Leaving them unset makes the service **fail closed** at startup:

- **`TOKEN_ISSUER` / `TOKEN_AUDIENCE`** — required because
  `TOKEN_STRICT_VALIDATION` defaults to `true`. A single issuer stamps **one**
  audience shared by every consumer, so use identical `TOKEN_ISSUER` /
  `TOKEN_AUDIENCE` values across `auth.env`, `media.env`, and `prompt.env` (opt
  out with `TOKEN_STRICT_VALIDATION=false` for local-only experiments).
- **`EVENT_SIGNING_KEY`** — required because `EVENT_SIGNING_ENABLED` defaults to
  `true`. Use the **same** key in `auth.env` and every consumer. It signs and
  verifies the auth event-stream payloads delivered over fa-auth's private SSE
  bridge (each consumer evicts its validation cache early); set
  `EVENT_SIGNING_ENABLED=false` everywhere to disable signing entirely.

Both consumers use the per-consumer private-auth model: `prompt.env` sets
`INTERNAL_CLIENT_ID=prompt-engine-service` and `media.env` sets
`INTERNAL_CLIENT_ID=media-service`. **Both ids must be registered** in
`auth.env`'s `PRIVATE_API_CONSUMERS`, each with a secret equal to that consumer's
`PRIVATE_API_SECRET`.

Initialize keys and local certificates:

```sh
bash init.sh
```

On Windows, run this from Git Bash. Start the stack:

```sh
docker compose up -d --build
```

## URLs

| What | URL |
| --- | --- |
| Auth docs | `http://localhost:9000/user/docs` |
| Media docs | `http://localhost:9000/media/docs` |
| Prompt docs | `http://localhost:9000/prompt/docs` |
| JWKS | `http://localhost:9000/user/.well-known/jwks.json` |
| Prompt health | `http://localhost:9000/prompt/health/` |
| Prompt metrics | `http://localhost:9000/prompt/metrics` |
| Media metrics | `http://localhost:9000/media/metrics` |
| Traefik dashboard | `http://localhost:8080` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` |
| MinIO console | `http://127.0.0.1:9006` |

## Observability

Prometheus scrapes (when `METRICS_ENABLED=true` on each service):

| Job | Target | Path |
| --- | --- | --- |
| traefik | `traefik:8082` | built-in metrics |
| auth_user_service | `auth_user_service:8000` | `/user/metrics` |
| media_service | `media_service:8000` | `/media/metrics` |
| prompt_engine_service | `prompt_engine_service:8000` | `/prompt/metrics` |

Grafana uses the local Prometheus datasource; default credentials come from
`grafana.env`.

## Configuration Notes

- `.env` is infrastructure/bootstrap config. It provisions `AUTH_DB_*`,
  `MEDIA_DB_*`, and `PROMPT_DB_*` through `../shared/db_init/init-db.sh`, and
  supplies the Redis and MinIO root passwords used by `redis_cache`,
  `media_redis_cache`, and `minio` via Compose interpolation.
- `auth.env`, `media.env`, and `prompt.env` are runtime application configs
  consumed by `fastapi-m8` / `auth-sdk-m8`. They use generic `DB_DATABASE`,
  `DB_USER`, `DB_PASSWORD` — do **not** replace those with the `*_DB_*` names.
- Only `auth_user_service` connects to the auth Redis (`redis_cache`). Consumers
  reach the auth service over HTTP (`INTROSPECTION_URL`) for revocation.
- `.env`, `auth.env`, `media.env`, `worker.env`, `prompt.env`, `grafana.env`,
  and `test.env` hold secrets and are git-ignored (`*.env`); only the `*.example`
  files are tracked.
- Service base paths: auth `/user`, media `/media`, prompt `/prompt`.

## Live security tests

`test.env` configures the `security-tests-m8` runner (see
[`../shared_live_tests`](../shared_live_tests) for the pytest example). It targets
the `prompt_engine_service` consumer by default (`LIVE_TEST_SVC_BASE=/prompt`,
`LIVE_TEST_PRIVATE_API_CLIENT_ID=prompt-engine-service`); add a `media` entry to
`LIVE_TEST_SVC_BASES` / `LIVE_TEST_PROTECTED_ENDPOINTS` to also exercise
media-service. Use a dedicated test-only superuser — never `FIRST_SUPERUSER`.

## Common Commands

```sh
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs -f prompt_engine_service
docker compose logs -f media_service
docker compose down
```

Resetting the DB is destructive:

```sh
bash init.sh --reset-db --yes
```

`--reset-db` removes `db_data/` even when PostgreSQL owns it as the container
uid — it falls back to a throwaway root container, so no manual `sudo rm` is
needed on WSL2/Linux bind mounts. On every run `init.sh` also enforces
`chmod 600` on each runtime `*.env` file and private key.

## Troubleshooting

**`changethis` rejection on startup**: replace placeholder values in `.env`,
`auth.env`, `media.env`, and `prompt.env`.

**Service exits at boot complaining about `EVENT_SIGNING_KEY` or
`TOKEN_ISSUER`/`TOKEN_AUDIENCE`**: these are required under auth-sdk-m8. Set them
identically across auth + every consumer, or set `EVENT_SIGNING_ENABLED=false` /
`TOKEN_STRICT_VALIDATION=false` for local-only runs.

**Prompt calls to the auth private API return 401**: confirm
`prompt.env`'s `INTERNAL_CLIENT_ID=prompt-engine-service` is registered in
`auth.env`'s `PRIVATE_API_CONSUMERS` with a secret equal to `prompt.env`'s
`PRIVATE_API_SECRET`.

**DB user authentication fails**: confirm each service env's `DB_USER` /
`DB_PASSWORD` match its `*_DB_*` triplet in `.env`. If `db_data/` already exists,
DB init will not rerun unless you reset it.

**Prometheus prompt target is down**: check `prompt_engine_service` logs and
confirm `/prompt/metrics` is enabled with `METRICS_ENABLED=true`.
