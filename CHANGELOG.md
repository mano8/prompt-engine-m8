# Changelog

All notable changes to prompt-engine-m8 are documented here.

## [Unreleased]

## [2.0.0] - 2026-08-10

Consolidation of the fa-auth 2.0 stack-alignment work: supersedes the unreleased
1.1.0 contract promotion below.

### Changed

- **BREAKING** — `CONTRACT_VERSION` realigned to `2.0.0`; `CONTRACT_RANGE` to `>=2.0.0 <3.0.0`, superseding the unreleased `1.0` / `>=1.1.0 <2.0.0` values. Consumers pinning the 1.x prompt-engine contract must move to 2.x (`astro-prompt-m8` realigned in the same wave).
- Service version promoted to `2.0.0` to stay within `CONTRACT_RANGE`.
- `fastapi-m8` floor raised from `>=3.3.0,<4.0.0` to `>=4.2.2,<5.0.0`; `requirements_prod.lock` regenerated (`fastapi-m8` 4.2.2, `auth-sdk-m8` 3.1.2).
- `ruff` pinned exactly to `0.15.18` in `requirements_dev.txt` and CI, for a reproducible lint gate.
- `core/events.py` now delegates straight to `auth.handle_auth_event` / `auth.flush_cache`, dropping the local `handle_auth_event` / `handle_auth_gap` wrappers and matching the `fastapi_full` template shape.
- `Settings.ENV_FILE_DIR` declared `ClassVar[Path]` so it is no longer shadowed as a pydantic settings field.
- `AGENTS.md` / `CLAUDE.md` restructured around a shared `REPOSITORY_CONTEXT.md`.
- `shared_live_tests` conftest corrected to target prompt-engine (`/prompt`) instead of media-service.

### Fixed

- Compose issuer image re-pinned `tepochtli/fa-auth-m8` `1.0.0` → `2.0.2`, retiring the pre-v2 pin.
- Redis ACL for the `auth` user granted `~introspect:*` and `~security:*` in both dev compose stacks, which fa-auth 2.0 requires.

### Added

- `constraints.txt` / `constraints-all.txt` for reproducible resolution.
- Supply-chain policy tests: `test_dependency_lock.py` and `test_ci_policy.py` (hashed lock, digest-pinned `FROM` stages, SBOM/provenance/cosign, SHA-pinned actions, single CI gate, contract assertions).

## [1.1.0] - 2026-07-03

Unreleased — superseded by 2.0.0.

### Changed

- `CONTRACT_VERSION` promoted from `0.0` to `1.0`; `CONTRACT_RANGE` updated to `>=1.1.0 <2.0.0` (service version 1.1.0 is within range).
- Supply-chain policy tests added: `test_dependency_lock.py` and `test_ci_policy.py` lock the 11.x invariants (hashed lock, digest-pinned FROM stages, SBOM/provenance/cosign, SHA-pinned actions, single CI gate, contract assertions).
- `shared_live_tests` conftest corrected to target prompt-engine (`/prompt`) instead of media-service.

## [1.0.0] - 2026-04-25

### Added

- Initial public release: prompt template and block management service built on fastapi-m8 3.3.0.
- Hashed production lock (`requirements_prod.lock`) with `--require-hashes` enforced in Dockerfile.
- SBOM (SPDX JSON), provenance (mode=max), and keyless cosign signing in publish workflow.
