# dev_local_prompt_m8

Local dev stack for `prompt_engine_service` on the full hardened M8 platform:
`auth_user_service` (issuer) + `media_service` + `prompt_engine_service`, plus
the async workers and infrastructure.

Same hardened posture as the media hardened stack (PostgreSQL 18, two Redis
instances (auth + media), SeaweedFS S3 storage, ClamAV, Traefik, Prometheus, Grafana,
RS256/JWKS auth, container hardening, network segmentation), with one developer
convenience: **all application services are built from local source** (the
sibling repos `../../../fa-auth-m8`, `../../../media-service-m8`,
`../../../media-worker-m8`, and this repo) instead of pulling published images,
and **the storage backend's S3 gateway is published on loopback**
(`127.0.0.1:9005`) for host access. There is no console port: SeaweedFS's
admin/filer surfaces stay loopback-bound inside the container.

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
       +--> Object storage (SeaweedFS S3) on data_net
```

`app_net` is external-facing for Traefik, app services, and observability.
`data_net` is internal and has no gateway; DB, Redis, and storage are not exposed
through that network (storage additionally publishes its S3 port on loopback for
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
| storage-tls-init | `alpine:3.21.3` | one-shot: mints the S3 gRPC mTLS certificate, then destroys the CA key |
| storage-config | `alpine:3.21.3` | one-shot: writes the backend's static identity table before it boots |
| storage | `chrislusf/seaweedfs:4.45` | `127.0.0.1:9005` S3 gateway — admin/filer surfaces loopback-bound inside the container |
| storage-init | `amazon/aws-cli:2.36.40` | one-shot: creates the five buckets + pins per-bucket CORS |
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
S3_ROOT_USER=<storage-admin-access-key>
S3_ROOT_PASSWORD=<storage-admin-secret-key>
S3_CORS_ALLOW_ORIGIN=http://localhost:4321,http://localhost:5173,http://localhost:9000
```

`init-db.sh` provisions a per-service PostgreSQL user + database from each
`*_DB_*` triplet on first volume init. Each service then connects with the
generic `DB_USER` / `DB_PASSWORD` / `DB_DATABASE` names in its own env file:

- `auth.env` → `AUTH_DB_*`, plus `REDIS_PASSWORD` to match `.env` (only
  `auth_user_service` connects to the auth Redis).
- `media.env` → `MEDIA_DB_*`, plus the `MEDIA_REDIS_*` and `S3_*` values.
- `prompt.env` → `PROMPT_DB_*`:

  ```ini
  DB_DATABASE=prompt_engine_db
  DB_USER=<same-as-PROMPT_DB_USER>
  DB_PASSWORD=<same-as-PROMPT_DB_PASSWORD>
  ```

The `storage-config` one-shot writes the backend's identity table from
`media.env`'s `S3_ACCESS_KEY` / `S3_SECRET_KEY` **before** the backend boots
(SeaweedFS has no bootstrap-time user-creation API), so they become the scoped
`media-rw` identity, not the storage admin (`S3_ROOT_USER` in `.env`).
`storage-init` then creates the five buckets with CORS pinned to
`S3_CORS_ALLOW_ORIGIN`. `prompt_engine_service` uses no object storage.

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

Re-running this on a stack that already has a keypair does not regenerate it,
but it does re-check `ACCESS_KEY_ID` against the mounted key and re-binds it
(with a `NOTE:`) if the two have drifted apart, instead of skipping silently.
Use `--rotate-keys` to actually generate a new keypair with the JWKS overlap
window.

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
| Storage S3 gateway | `http://127.0.0.1:9005` |

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
  supplies the Redis and storage admin credentials used by `redis_cache`,
  `media_redis_cache`, and the storage-bootstrap services via Compose
  interpolation. `storage` itself reads its identities from
  `seaweedfs/config/s3.json`, which `storage-config` generates (gitignored — it
  carries both credentials verbatim).
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

<!-- env-files:start -->
## Environment files

Copy each template to the name after the arrow (`init.sh` does this where the stack has one), then replace every
`changethis`. Every key is documented in its template; each secret carries a `# Value:` line with its minimum
and maximum length and allowed characters. Real env files are gitignored and never committed.

| Template → file | Read by | Must be set (placeholders) |
| --- | --- | --- |
| `.env.example` → `.env` | Compose itself (`${VAR}` interpolation) and the engine init scripts | `DB_PASSWORD`, `AUTH_DB_USER`, `AUTH_DB_PASSWORD`, `MEDIA_DB_USER`, `MEDIA_DB_PASSWORD`, `PROMPT_DB_USER`, `PROMPT_DB_PASSWORD`, `REDIS_PASSWORD`, `MEDIA_REDIS_PASSWORD`, `S3_ROOT_USER`, `S3_ROOT_PASSWORD` |
| `auth.env.example` → `auth.env` | `auth_user_service` | `DB_USER`, `DB_PASSWORD`, `REDIS_PASSWORD`, `ACCESS_KEY_ID`, `REFRESH_SECRET_KEY`, `FIRST_SUPERUSER_PASSWORD`, `PRIVATE_API_SECRET`, `SESSION_SECRET`, `TOKENS_ENCRYPTION_KEY`, `EVENT_SIGNING_KEY` |
| `grafana.env.example` → `grafana.env` | `grafana` | `GF_SECURITY_ADMIN_PASSWORD` |
| `media.env.example` → `media.env` | `media_service`, `media_service_worker`, `storage-config`, `storage-init` | `DB_USER`, `DB_PASSWORD`, `MEDIA_REDIS_PASSWORD`, `MEDIA_INTERNAL_SERVICE_TOKEN`, `MEDIA_SHARE_SIGNING_SECRET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `REFRESH_SECRET_KEY`, `PRIVATE_API_SECRET`, `EVENT_SIGNING_KEY` |
| `prompt.env.example` → `prompt.env` | `prompt_engine_service` | `DB_USER`, `DB_PASSWORD`, `REFRESH_SECRET_KEY`, `PRIVATE_API_SECRET`, `EVENT_SIGNING_KEY` |
| `test.env.example` → `test.env` | the live security tests (`shared_live_tests`), not a container | `LIVE_TEST_ADMIN_EMAIL`, `LIVE_TEST_ADMIN_PASSWORD`, `LIVE_TEST_PRIVATE_API_SECRET`, `LIVE_TEST_REFRESH_SECRET_KEY` |
| `worker.env.example` → `worker.env` | `media_worker` | `MEDIA_INTERNAL_SERVICE_TOKEN`, `MEDIA_REDIS_PASSWORD`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` |

Generate a value that satisfies every secret rule (48 chars: upper, lower, digit and `-`):

```sh
python -c "import secrets,string; a=string.ascii_letters+string.digits; print('Aa1-'+''.join(secrets.choice(a) for _ in range(44)))"
```

Values must avoid spaces, `$`, `#`, quotes and backslashes: Compose interpolates `$`, dotenv treats `#` as a
comment, and several values are embedded in URLs, JSON or the Redis ACL.
<!-- env-files:end -->
