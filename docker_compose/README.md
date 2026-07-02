# docker_compose

Docker Compose examples for prompt-engine-m8.

## Stacks

- [`dev_prompt_engine_m8`](dev_prompt_engine_m8) — lean local dev stack: Traefik,
  `fa-auth-m8`, PostgreSQL, auth Redis, `prompt-engine-m8`, Prometheus, and
  Grafana. Adapted from media-service-m8's hardened compose pattern with the
  media-only storage, ClamAV, and worker services removed.
- [`dev_local_prompt_m8`](dev_local_prompt_m8) — full combined platform stack:
  everything above **plus** `media-service-m8`, its workers, media Redis, MinIO,
  and ClamAV, so `prompt_engine_service` runs beside the media service on one
  hardened stack. All application services are built from local sibling repos.
- [`shared_live_tests`](shared_live_tests) — reusable `security-tests-m8` live
  security suite (pytest example) plus the CLI-mode instructions. Points at a
  running stack via its `.env`; defaults to `dev_local_prompt_m8`.

Every application service consumes the same platform baseline — `fastapi-m8`
3.3.0 on `auth-sdk-m8` 2.1.1 — so the env-file layout and secure-by-default
requirements (`TOKEN_ISSUER`/`TOKEN_AUDIENCE`, `EVENT_SIGNING_KEY`, per-consumer
`INTERNAL_CLIENT_ID`) are identical across stacks. Only the `*.example` env files
are tracked; copy them to their runtime names before starting a stack.
