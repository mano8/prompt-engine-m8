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