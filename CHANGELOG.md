# Changelog

All notable changes to prompt-engine-m8 are documented here.

## [Unreleased]

## [1.1.0] - 2026-07-03

### Changed

- `CONTRACT_VERSION` promoted from `0.0` to `1.0`; `CONTRACT_RANGE` updated to `>=1.0.0 <2.0.0` (service version 1.1.0 is within range).
- Supply-chain policy tests added: `test_dependency_lock.py` and `test_ci_policy.py` lock the 11.x invariants (hashed lock, digest-pinned FROM stages, SBOM/provenance/cosign, SHA-pinned actions, single CI gate, contract assertions).
- `shared_live_tests` conftest corrected to target prompt-engine (`/prompt`) instead of media-service.

## [1.0.0] - 2026-04-25

### Added

- Initial public release: prompt template and block management service built on fastapi-m8 3.3.0.
- Hashed production lock (`requirements_prod.lock`) with `--require-hashes` enforced in Dockerfile.
- SBOM (SPDX JSON), provenance (mode=max), and keyless cosign signing in publish workflow.
