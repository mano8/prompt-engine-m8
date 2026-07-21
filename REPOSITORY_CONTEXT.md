# prompt-engine-m8

## Layer

Service (prompt generation system).

## Purpose

Transform templates into optimized prompts.

## Repository boundaries

- Prefer stateless transformation logic.
- Do not couple the service to external services.
- Remain deterministic where possible.

## Standalone authority

This file, repository documentation, and existing CI are the authoritative local
context. A verified nearest workspace may optionally add launcher-selected
policies and tasks; its absence is a successful standalone condition and does
not make a parent workspace necessary.
