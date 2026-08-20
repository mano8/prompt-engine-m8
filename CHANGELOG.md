# Changelog

All notable changes to prompt-engine-m8 are documented here.

## [Unreleased]

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
