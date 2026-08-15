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

## Standalone authority

This file, repository documentation, and existing CI are the authoritative local
context. A verified nearest workspace may optionally add launcher-selected
policies and tasks; its absence is a successful standalone condition and does
not make a parent workspace necessary.
