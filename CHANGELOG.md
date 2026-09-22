# Changelog

All notable changes to prompt-engine-m8 are documented here.

## [Unreleased]

## [2.2.1] - 2026-09-20

Debian patch-layer convergence — `B23-converge-patch-layer` (Wave 6) of the
workspace's consumer-alignment closure plan, finding `G18`; the form is
recorded once, in the workspace's `.workspace/context/debian-patch-layer.md`,
and the five service images now carry it byte-for-byte. Image-only patch
release: no route, schema, contract or dependency change. `SERVICE_VERSION`
(and `contracts/openapi.json`'s `info.version`) move to `2.2.1`;
`CONTRACT_VERSION` stays `2.1.0` and `CONTRACT_RANGE` `>=2.1.0 <3.0.0`, so
`@mano8/astro-prompt-m8`'s preflight admits this release unchanged. It also
carries one repository-hygiene file that ships in no image (`B24`, below).

### Added

- **`docker_compose/dev_prompt_engine_m8/.gitignore`** (`B24-prompt-stack-gitignore`),
  matching the sibling `dev_local_prompt_m8` stack's pattern, so everything
  `init.sh` generates — `.env` copies, `keys/`, `traefik/certs/`, `db_data/`,
  `redis/`, `shared_migrations/`, `prometheus/data/`, `grafana/data/` — is
  ignored as it already is in every other stack in the fleet. It rides this
  release rather than its own PR: its own PR (#41) was red on the `anyio`
  advisory below, which lives on `main` and not in its one-file diff.

### Security

- **The runtime image's Debian layer is now the fleet's one form:**
  `apt-get update && apt-get upgrade -y`, nothing exact-pinned, nothing
  installed that the base does not already ship. `curl` is no longer
  installed: its exact `=8.14.1-2+deb13u5` pin was the one package
  `apt-get upgrade -y` could not raise, it had already been hand-raised once
  (`deb13u4` → `deb13u5`, `d9a62fb`) for an advisory on a package nothing in
  this image uses — no `HEALTHCHECK`, the Compose healthchecks probe with
  `python -c "import urllib.request…"`, and the only `curl` calls in this
  repository run outside the image.
- **Base image raised to the current `python:3.14-slim` digest
  `caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2`**
  (Debian 13.7, Python 3.14.7, created 2026-09-19), from `cad9a2…` (Debian 13.6).
  All five service images now pin this same digest, and from here on base
  digests move together — on advisory or on cadence, never one repository
  alone. Measured inside the new base: every package this fleet had ever
  pinned ships at or above its pinned version (`openssl` `3.5.7-1~deb13u2`,
  `gzip` `1.13-1+deb13u1`, `libpcre2-8-0` `10.46-1~deb13u2`, `libsqlite3-0`
  `3.46.1-7+deb13u2`, `perl-base` `5.40.1-6+deb13u1`), so `upgrade -y` is a
  no-op today and self-heals from the next advisory on.
- **`anyio` `4.14.1` → `4.14.2` in `promt_engine_service/requirements_prod.lock`** — CVE-2026-63374
  (CRITICAL, TLS certificate spoofing via IDNA 2003 host-name encoding in
  `TLSStream`) and CVE-2026-63349 (HIGH, `run_process`/`open_process`
  retaining the parent's supplementary groups), both published 2026-09-18,
  after this repository's last green `trivy-image` run on `main`. Transitive
  (under `fastapi-m8`, `httpx` and `starlette`), so the hash-locked release
  set is the only place it
  appears; regenerated with `pip-compile --upgrade-package anyio==4.14.2`,
  so exactly one version line moves. Found by this release's own pre-PR
  Trivy read — the gate's freshness limit, not a property of the diff.
- Verified before the change was proposed: `docker build --no-cache` green
  on the new Dockerfile; Trivy at the `trivy-image` gate's own settings
  (`severity: CRITICAL,HIGH`, `ignore-unfixed: true`) reports **0**
  findings; inside the built container `openssl version` reads
  `OpenSSL 3.5.7` and `dpkg-query -W curl` reports it not installed.

## [2.2.0] - 2026-09-13

Dependency realignment onto the published JWKS `kid`/key-binding release
train. No route, schema, or contract change: `CONTRACT_VERSION` stays `2.1.0`
and `CONTRACT_RANGE` stays `>=2.1.0 <3.0.0`, so `@mano8/astro-prompt-m8`'s
preflight admits this release unchanged. Steps `W3.1`, `W3.2` and `W3.6` of
the 2026-09-08 JWKS `kid`/key-binding remediation plan.

### Changed

- **`fastapi-m8` floor raised `>=4.4.0,<5.0.0` → `>=4.5.1,<5.0.0`**
  (`promt_engine_service/requirements_base.txt`); `constraints.txt` and
  `constraints-all.txt` regenerated. `4.5.1` is the first framework release
  whose declared floor *and* compiled constraints both resolve
  `auth-sdk-m8>=3.2.0`, so the transitive `auth-sdk-m8` pin moves
  `3.1.3` → `3.2.0`: `JwksKeyResolver` now recovers from key material
  changing under an unchanged `kid` within one refresh interval instead of
  one cache TTL, and cannot be made to storm the issuer. The SDK is still
  reached only through `fastapi-m8` — no direct `auth-sdk-m8` declaration is
  added. Dev-only movement from the regeneration: `mypy 2.3.0 → 2.3.1`,
  `ruff 0.15.18 → 0.16.3`, `colorama` surfaced as a `click` dependency.
- **`requirements_prod.lock` regenerated onto the declared floors.** The
  first cut of this entry regenerated the constraints but not the lock, so
  the hash-locked graph the release image installs still pinned
  `fastapi-m8 4.4.0` / `auth-sdk-m8 3.1.3` — the release would have shipped
  without the `JwksKeyResolver` fix it exists to carry. The Dependabot floor
  bumps merged in the same window (`uvicorn >=0.52.4`, `alembic >=1.19.2`,
  `redis >=8.1.0`) had likewise moved the declaration without moving the
  artifact. Lock movement, all on declared packages: `fastapi-m8 4.4.0 →
  4.5.1`, `auth-sdk-m8 3.1.3 → 3.2.0` (transitive only, still undeclared),
  `uvicorn 0.49.0 → 0.52.4`, `alembic 1.18.5 → 1.20.0`, `redis 8.0.1 →
  8.1.0`. The other 44 pins are unchanged: the documented `pip-compile`
  command carries no `--upgrade`, so pins that still satisfy the graph are
  kept. Verified the way `test-shipped-lock` does: hash-locked install,
  49/49 pins matched after adding test tooling, 228 tests at 100% coverage,
  `pip-audit` clean.
- **`constraints.txt` / `constraints-all.txt` regenerated again** on the
  same floors (`alembic 1.19.0 → 1.20.0`, `uvicorn 0.52.1 → 0.52.4`,
  dev-only `ruff 0.16.3 → 0.16.6`). All three compiled files were produced
  on Linux this time, inside `python:3.14-slim` at the digest the Dockerfile
  pins, so `colorama` — the Windows-only `click` transitive noted above —
  drops back out and the constraints describe the same platform as the lock
  and CI. pip-tools `7.6.1` (the first release that runs against pip `26.x`)
  renders a spurious `--no-index` into the autogenerated header; the header
  line is kept at the documented command, nothing was resolved offline.
- **`dev_prompt_engine_m8` issuer image `tepochtli/fa-auth-m8:2.2.0` →
  `2.2.1`** (`docker_compose/dev_prompt_engine_m8/docker-compose.yml`).
  `2.2.1` is a patch of the issuer: its bundled `init-keys.sh` verifies the
  `kid` binding on a keys-exist rerun instead of skipping it. Published on
  Docker Hub at index digest `sha256:12ac4d51…9272`.
- **`docker_compose/shared/scripts/init-keys.sh` re-vendored from
  `fa-auth-m8`**, replacing a copy that predated the issuer's `2.1.0` fixes.
  `kid` is now derived from canonical SPKI DER bytes — the same derivation
  the service uses and refuses to boot without; a rerun with keys already
  present re-derives `kid` and checks it against `ACCESS_KEY_ID` in
  `auth.env` (writes it when unset, re-binds with a `NOTE:` when stale)
  rather than skipping silently; `--rotate-keys` keeps the previous public
  key as `public_old.pem` for the JWKS overlap window. Both stack READMEs
  document the rerun behaviour.
- `README.md`: the `/meta` section's quoted `CONTRACT_RANGE` corrected from
  `>=2.0.0 <3.0.0` to the `>=2.1.0 <3.0.0` the service has published since
  `2.1.0` (doc drift only).

### Deployment note

`fa-auth-m8 2.1.0+` refuses to boot when `ACCESS_KEY_ID` is not the DER
fingerprint of the key it serves. A host taking this release should run
`bash init.sh` once before starting the stack — it now verifies and, if
needed, re-binds the value.

## [2.1.0] - 2026-08-30

Additive contract release. Everything below landed **after** `2.0.0` was
published and was, until this entry, documented inside `2.0.0`'s own section —
so the changelog of a shipped artifact claimed routes that artifact does not
serve (`G14`). The entries are moved here unchanged and the version is bumped,
which is the correction rather than new work.

### Added

- **`GET /prompt-block/export/` and `GET /prompt-template/export/` (`A-C8`).**
  The same `q`/`csrc`/`sort`/`order`/`f` vocabulary as the list routes, with no
  `skip`/`limit` — a deliberately unpaginated read of the whole filtered set,
  bounded by `MAX_EXPORT_SIZE = 5000` rather than a caller-supplied `limit`. A
  filtered set larger than the cap returns the first `MAX_EXPORT_SIZE` rows
  with `truncated: true` rather than materialising an unbounded result. Closes
  the gap `C7`/`C8` left on `astro-prompt-m8`, where the block/template bundle
  export buttons could only act on one fetched page because that is all a
  server-driven table's list read ever returns.

- **The served OpenAPI document is published as a committed artifact (`A-C1`).**
  `contracts/openapi.json` is the spec the app actually serves, serialised
  deterministically, and `tests/test_openapi_snapshot.py` fails when the two
  disagree — so the artifact can never describe a service that no longer
  exists. `test_contract_fidelity.py` (`C6`) already asserted the served
  document against `schemas/list_params.py`, but built it inside the test
  process and threw it away, leaving a consumer with nothing to diff against.
  Refresh with `PROMPT_ENGINE_M8_WRITE_OPENAPI=1 pytest
  tests/test_openapi_snapshot.py`.

### Changed

- **BREAKING — `CONTRACT_VERSION` moved `2.0.0` → `2.1.0` and `CONTRACT_RANGE`
  moved `>=2.0.0 <3.0.0` → `>=2.1.0 <3.0.0`.** `A-C8` added routes while leaving
  the contract axis on `2.0.0`, which meant a host running the published
  `prompt-engine-m8:2.0.0` image passed a client's `/meta` preflight cleanly and
  then `404`ed on "Export all" — `H12` re-formed one release later, the exact
  defect `C17` spent a step closing. The axis now names the surface it
  describes, and the supported range moves with it: `2.1.0` is the floor this
  release supports. The export routes are additive, so a 2.0 caller is still
  *served* in practice; the range states what is supported, not what is
  tolerated, and a 2.0 client is expected to move with the pair.
  ⚠️ **Consequence for an already-published client.**
  `@mano8/astro-prompt-m8@2.0.0` compares the contract axis by exact string
  equality and therefore refuses a `2.1.0` service at preflight. Upgrade the
  pair together — the service and its client have released as a pair since
  `1.1.1`/`1.0.0`, for this reason.

## [2.0.0] - 2026-08-20

Folded from `[Unreleased]` (`C18`): `2.0.0` was never published (published:
`1.0.0`), so this release note is the consolidation of the full contract-
completeness wave — the fa-auth 2.0 stack-alignment work dated 2026-08-10
below, plus the server-driven list contract, mutating-verb fix and
publish-readiness hardening that landed under `[Unreleased]` afterward — into
the single entry the version that ships actually carries.

### Added

- **Declared list vocabulary (`C1`).** `promt_engine_service/schemas/list_params.py` names every value the list endpoints accept in `csrc`, `sort`, `order` and `f`, per resource, as enum members — so the allow-lists reach the OpenAPI document verbatim and a client can mirror them instead of guessing. `ListQueryController` in `controllers/prompts.py` is the single bridge from a declared name to a column or predicate, shared by all three list routes: an undeclared value is rejected, never silently ignored, and free-text `q` is bound as a parameter with `%`/`_` escaped rather than interpolated (`SEC-VALIDATE-UNTRUSTED-INPUT`). No route consumes this yet — `C2`/`C3` wire it.

- **Server-driven list parameters on `GET /prompt-block/` and `GET /prompt-template/` (`C2`).** Both accept `q` (free-text over the declared columns), `csrc` (restrict `q` to one column), `f` (comma-joined facet values combined with `OR`), and `sort`/`order`. `sort=block_count` on templates orders by attached-block count via a correlated subquery. Additive: `skip`/`limit` behave exactly as before when the new parameters are absent, and an absent `sort` still adds no `ORDER BY`. `skip`/`limit` now reject negative/zero values with `422` instead of reaching the database.

- **Contract-fidelity tests (`C6`).** The test class whose absence let `H2` and `H6` sit inside fully-covered code on both sides of the wire. They assert the *served* contract — the thing a consumer mirrors — rather than a hand-written fixture: the OpenAPI document publishes exactly the parameters and enum values `schemas/list_params.py` declares (facet values reach the document through the `f` parameter description, since a comma-joined string cannot be an enum); every published value is accepted by the service; and the published required body fields are **necessary and sufficient** on all three create routes — a request carrying exactly them succeeds, and dropping any one of them is a `422`. `/meta` and `/ping` identity is pinned for the consumer preflight `C9` will wire.

- **Mutating verbs for template block membership (`C5`, `C17`).** `POST /prompt-template/{id}/add-block/{block_id}/` and `PUT /prompt-template/{id}/set-block-position/{block_id}/` are the only verbs these two paths answer. Both operations change state and were previously reachable only by `GET`, which is cacheable, prefetchable and link-followable (`H3`). `C5` kept the `GET` forms mounted as deprecated aliases for a consumer mid-flight; `C17` removed them before this release was published, so no released consumer ever met them — a `GET` now returns `405` and the OpenAPI document publishes one operation per path. `DELETE .../delete-block/...` was already correct and is unchanged.

- **HTTP-level `POST /category/add/` coverage (`C4`).** The route has never had any. `CategoryCreate` still requires `type` — decision `D-C1` resolves `H2` on the client side, because the UI knows whether it is filing a block or a template category and a server-chosen default would be a guess. The new tests pin the required payload (`{name, type}`), the derived slug, the rejection of the `{name}`-only payload the client sends today, the writer floor, and that `owner_id` comes from the token rather than the body.

- **Server-driven list parameters on `GET /category/` (`C3`).** `q` (free-text over `name`/`slug`) plus `sort`/`order`. A category carries no public flag and no faceted axis, so the endpoint declares no `csrc` and no `f` — the empty tuples in `CATEGORY_LIST_VOCABULARY` say so explicitly. The superuser-vs-owner visibility split is preserved and is now applied as a predicate alongside the search rather than by branching the whole query, so a filter cannot widen what a non-superuser sees.

- `constraints.txt` / `constraints-all.txt` for reproducible resolution.
- Supply-chain policy tests: `test_dependency_lock.py` and `test_ci_policy.py` (hashed lock, digest-pinned `FROM` stages, SBOM/provenance/cosign, SHA-pinned actions, single CI gate, contract assertions).
- **`pip-audit` now runs against the shipped `requirements_prod.lock`, not only the dev floors.** CI audited `requirements_dev.txt` alone — `-r requirements_base.txt` plus dev tools, every entry a `>=` floor — so it resolved whatever was newest on the day it ran rather than the pinned graph the release image installs with `--require-hashes`. Measured at the time of the fix: 20 of the lock's 49 pins were audited at a *newer* version than the shipped one (`starlette` 1.3.1 vs 1.6.0, `uvicorn` 0.49.0 vs 0.52.4, `alembic` 1.18.5 vs 1.19.1, …), and `gunicorn` — the production server, declared in `requirements_prod.txt` and in no dev file — was audited at no version at all. A CVE against a shipped version that is fixed upstream was therefore invisible: the audit resolved the fixed release and reported clean while the image shipped the vulnerable one. `trivy-image` did cover the built image, but only at CRITICAL/HIGH with `ignore-unfixed`. `test_ci_audits_the_file_the_dockerfile_installs` reads the lock's name out of the Dockerfile's prod install and asserts CI audits that same file, so the gate cannot drift from the artifact. The lock is clean as of this entry — no known vulnerabilities.
- **The test suite now runs against the shipped `requirements_prod.lock`, not only against the dev floors (`test-shipped-lock`).** `pip-audit` and Trivy *scan* the lock; neither *runs* it, and the `test` matrix installs `requirements_dev.txt` — `>=` floors — so it exercised whatever resolved newest that day. The lock differed from that graph on 20 of its 49 pins, which made the shipped dependency set the one graph nothing executed: a lock that installs and then fails at import or at runtime would have shipped with every job green. The new job installs the lock with `--require-hashes` exactly as the Dockerfile does, adds pytest under constraints derived from the lock, and then re-verifies the environment with `scripts/shipped_lock_env.py --verify` before running the suite — without that check, installing test tooling could drag a runtime package forward and quietly recreate the defect inside the job meant to close it. Verified: the shipped set passes at 100% coverage (212 tests; the 4 absent against a dev environment are `[trio]` parametrisations, since `trio` is not a runtime dependency).

### Changed

- **`limit` is bounded at 500 on all three list endpoints.** It carried a floor (`ge=1`) and no ceiling, which was survivable while the lists were `skip`/`limit` only. `C2` changed the cost behind it: `q` compiles to a leading-wildcard `LIKE` over every declared column — on blocks that includes `content`, unindexed text — so an authenticated caller at any tier could ask one request to materialise the whole visible table. The ceiling is declared once as `MAX_PAGE_SIZE` beside `MAX_SEARCH_LENGTH`, reaches the OpenAPI document as `maximum`, and is asserted at its boundary rather than at a round number. It bounds what one request materialises; it does **not** bound the scan, which is a function of table size and indexing. The tables page at 10/20/40, so no client is affected.
- **BREAKING — `/dashboard/*` floor raised `require_writer` → `require_admin` (decision `D-C2`, superseding the A15 writer floor).** Both dashboard routes aggregate activity across users, and the consuming UI has always gated the dashboard on an administrative principal, so the writer floor admitted a tier no client ever sent. A WRITER-tier caller now receives `403`. `CurrentAdmin` was already exported for exactly this; the `is_superuser` branch inside `DashboardController` still narrows own-scope from fleet-wide.
- **BEHAVIOUR CHANGE — `count` is now the *filtered* count on all three list endpoints (`C2`, `C3`).** It was previously the count of everything visible to the caller, regardless of any filtering. Nothing filtered before this release, so no existing caller can observe a difference; a caller that starts sending `q`/`f` gets a paginator that agrees with its own result set, which is the entire reason the parameters exist. Called out here as a behaviour change rather than a fix.
- **BREAKING** — `CONTRACT_VERSION` realigned to `2.0.0`; `CONTRACT_RANGE` to `>=2.0.0 <3.0.0`, superseding the unreleased `1.0` / `>=1.1.0 <2.0.0` values. Consumers pinning the 1.x prompt-engine contract must move to 2.x (`astro-prompt-m8` realigned in the same wave).
- Service version promoted to `2.0.0` to stay within `CONTRACT_RANGE`.
- `fastapi-m8` floor raised from `>=3.3.0,<4.0.0` to `>=4.2.2,<5.0.0`; `requirements_prod.lock` regenerated (`fastapi-m8` 4.2.2, `auth-sdk-m8` 3.1.2).
- `ruff` pinned exactly to `0.15.18` in `requirements_dev.txt` and CI, for a reproducible lint gate.
- `core/events.py` now delegates straight to `auth.handle_auth_event` / `auth.flush_cache`, dropping the local `handle_auth_event` / `handle_auth_gap` wrappers and matching the `fastapi_full` template shape.
- `Settings.ENV_FILE_DIR` declared `ClassVar[Path]` so it is no longer shadowed as a pydantic settings field.
- `AGENTS.md` / `CLAUDE.md` restructured around a shared `REPOSITORY_CONTEXT.md`.
- `shared_live_tests` conftest corrected to target prompt-engine (`/prompt`) instead of media-service.

### Fixed

- **`CategoryCreate`/`CategoryUpdate` no longer publish `slug` as required (`C6`).** The `mode="before"` validator derives it from the required `name` and overwrites anything sent, so the published schema was demanding a field the service was going to ignore — a client mirroring the contract would send exactly the wrong thing. `slug` is now optional on the *payload* schemas only; the table still cannot hold a null, and `PromptBlockModel`/`PromptTemplateModel` already declared it this way.
- **`fastapi-m8` floor raised `>=4.3.0,<5.0.0` → `>=4.4.0,<5.0.0`** now that `4.4.0` is published, and `constraints.txt` / `constraints-all.txt` / `requirements_prod.lock` regenerated against it. `auth-sdk-m8` moves `3.1.2` → `3.1.3` in those generated files **transitively only** — it stays undeclared in `requirements_base.txt`, per the operator ruling that a consumer depends on `fastapi-m8` and never on `auth-sdk-m8` directly. The two had to move together: `fastapi-m8 4.4.0` requires `auth-sdk-m8>=3.1.3`, so pinning `4.4.0` against the old `3.1.2` pin is a hard `ResolutionImpossible`.
- `requirements_prod.lock` no longer carries `colorama` — a Windows-only transitive of `click` (`platform_system == "Windows"`) that entered the lock when it was regenerated on a Windows host. The production image is Linux, so the entry was never installable there; this lock was regenerated on Linux to match CI.
- Compose issuer image re-pinned `tepochtli/fa-auth-m8` `1.0.0` → `2.0.2`, retiring the pre-v2 pin.
- Redis ACL for the `auth` user granted `~introspect:*` and `~security:*` in both dev compose stacks, which fa-auth 2.0 requires.

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
