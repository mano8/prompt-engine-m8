# prompt-engine-m8

## Layer

Service (prompt generation system).

## Purpose

Transform templates into optimized prompts.

## Repository boundaries

- Prefer stateless transformation logic.
- Do not couple the service to external services.
- Remain deterministic where possible.
- `auth-sdk-m8` is never imported directly in service code — only `fastapi-m8`
  and its re-exports are. `ruff.toml` enforces this with a `TID251`
  banned-api rule (`auth_sdk_m8`); `ruff check .` fails on any direct import
  outside `tests/`.

## Contract surface

- `GET /prompt-block/`, `GET /prompt-template/` and `GET /category/` accept
  `skip`/`limit` plus a declared, additive list-query vocabulary
  (`q`/`csrc`/`sort`/`order`/`f`, per resource) published in
  `schemas/list_params.py` and applied by `ListQueryController` in
  `controllers/prompts.py`. An undeclared value is a `422`, never a silently
  ignored parameter. `count` in every list response is the filtered count.
  `limit` is bounded at `MAX_PAGE_SIZE = 500`; `q` at `MAX_SEARCH_LENGTH = 200`.
- `POST /prompt-template/{id}/add-block/{block_id}/` and
  `PUT /prompt-template/{id}/set-block-position/{block_id}/` are the only
  verbs these paths answer; the state-mutating `GET` aliases they used to keep
  as a deprecated compatibility window are gone.
- `GET /meta` (no auth) publishes `CONTRACT_NAME`/`CONTRACT_VERSION`/
  `CONTRACT_RANGE`/`SERVICE_VERSION` for the client compatibility preflight;
  `GET /ping` is the dependency-free liveness probe.

## Standalone authority

This file, repository documentation, and existing CI are the authoritative local
context. A verified nearest workspace may optionally add launcher-selected
policies and tasks; its absence is a successful standalone condition and does
not make a parent workspace necessary.
