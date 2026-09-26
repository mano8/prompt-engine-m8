# dev_prompt_engine_m8

Local dev stack for `auth_user_service` and `prompt_engine_service`.

This stack is adapted from the media-service-m8 compose layout while removing media-only storage, scan, and worker components.

## Architecture

```text
Browser / Frontend
       |
       v
  Traefik :9000
       | app_net
       +--> /user/*   -> auth_user_service :8000
       +--> /prompt/* -> prompt_engine_service :8000

  prompt_engine_service
       +--> PostgreSQL on data_net
       +--> auth_user_service private API for token revocation
```

## Setup

From `docker_compose/dev_prompt_engine_m8`:

```sh
cp .env.example .env
cp auth.env.example auth.env
cp prompt.env.example prompt.env
cp grafana.env.example grafana.env
bash init.sh
```

Edit `.env`, `auth.env`, and `prompt.env` so every `changethis` is replaced before starting the stack.

Re-running `bash init.sh` after keys already exist does not regenerate them,
but it does re-derive `kid` from the mounted `keys/public.pem` and check it
against `ACCESS_KEY_ID` in `auth.env`: a match is confirmed, an unset value is
written, and a stale value is re-bound with a `NOTE:` naming the correction —
it never silently skips over an unbound `kid`. Use `--rotate-keys` to actually
generate a new keypair with the JWKS overlap window.

Start:

```sh
docker compose up -d --build
```

## URLs

| What | URL |
| --- | --- |
| Auth docs | `http://localhost:9000/user/docs` |
| Prompt docs | `http://localhost:9000/prompt/docs` |
| JWKS | `http://localhost:9000/user/.well-known/jwks.json` |
| Prompt metrics | `http://localhost:9000/prompt/metrics` |
| Traefik dashboard | `http://localhost:8080` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` |

## Notes

- `.env` provisions `AUTH_DB_*` and `PROMPT_ENGINE_DB_*` through `../shared/db_init/init-db.sh`.
- `prompt.env` uses generic runtime DB variables: `DB_DATABASE`, `DB_USER`, and `DB_PASSWORD`.
- The app code directory remains `promt_engine_service` because that is the package name in this repository.
- The service base path is `/prompt`.

<!-- env-files:start -->
## Environment files

Copy each template to the name after the arrow (`init.sh` does this where the stack has one), then replace every
`changethis`. Every key is documented in its template; each secret carries a `# Value:` line with its minimum
and maximum length and allowed characters. Real env files are gitignored and never committed.

| Template → file | Read by | Must be set (placeholders) |
| --- | --- | --- |
| `.env.example` → `.env` | Compose itself (`${VAR}` interpolation) and the engine init scripts | `DB_PASSWORD`, `AUTH_DB_USER`, `AUTH_DB_PASSWORD`, `PROMPT_ENGINE_DB_USER`, `PROMPT_ENGINE_DB_PASSWORD`, `REDIS_PASSWORD` |
| `auth.env.example` → `auth.env` | `auth_user_service` | `DB_USER`, `DB_PASSWORD`, `REDIS_PASSWORD`, `ACCESS_KEY_ID`, `REFRESH_SECRET_KEY`, `FIRST_SUPERUSER_PASSWORD`, `PRIVATE_API_SECRET`, `SESSION_SECRET`, `TOKENS_ENCRYPTION_KEY`, `EVENT_SIGNING_KEY` |
| `grafana.env.example` → `grafana.env` | `grafana` | `GF_SECURITY_ADMIN_PASSWORD` |
| `prompt.env.example` → `prompt.env` | `prompt_engine_service` | `DB_USER`, `DB_PASSWORD`, `REFRESH_SECRET_KEY`, `PRIVATE_API_SECRET`, `EVENT_SIGNING_KEY` |
| `test.env.example` → `test.env` | the live security tests (`shared_live_tests`), not a container | `LIVE_TEST_ADMIN_EMAIL`, `LIVE_TEST_ADMIN_PASSWORD`, `LIVE_TEST_PRIVATE_API_SECRET`, `LIVE_TEST_REFRESH_SECRET_KEY` |

Generate a value that satisfies every secret rule (48 chars: upper, lower, digit and `-`):

```sh
python -c "import secrets,string; a=string.ascii_letters+string.digits; print('Aa1-'+''.join(secrets.choice(a) for _ in range(44)))"
```

Values must avoid spaces, `$`, `#`, quotes and backslashes: Compose interpolates `$`, dotenv treats `#` as a
comment, and several values are embedded in URLs, JSON or the Redis ACL.
<!-- env-files:end -->
