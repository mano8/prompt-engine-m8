"""Policy tests: CI/CD workflow supply-chain invariants."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CI_YAML = WORKFLOWS / "CI.yaml"
PUBLISH_YAML = WORKFLOWS / "docker-publish.yaml"

# Matches a SHA-pinned action ref: uses: owner/repo@<40-hex-chars>
_SHA_PIN_RE = re.compile(r"uses:\s+\S+@[0-9a-f]{40}")
# Matches any uses: line
_USES_RE = re.compile(r"^\s+uses:\s+(\S+)")


def _action_lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text().splitlines() if re.match(r"\s+uses:\s+", ln)]


# ── single CI gate ────────────────────────────────────────────────────────────

def test_no_duplicate_ci_yml() -> None:
    assert not (WORKFLOWS / "ci.yml").exists(), "Legacy ci.yml must be removed — use CI.yaml only"


def test_ci_yaml_exists() -> None:
    assert CI_YAML.exists(), "CI.yaml is missing"


# ── SHA-pinned actions ────────────────────────────────────────────────────────

def test_ci_yaml_actions_are_sha_pinned() -> None:
    for line in _action_lines(CI_YAML):
        assert _SHA_PIN_RE.search(line), f"CI.yaml action not SHA-pinned: {line.strip()}"


def test_publish_yaml_actions_are_sha_pinned() -> None:
    for line in _action_lines(PUBLISH_YAML):
        assert _SHA_PIN_RE.search(line), f"docker-publish.yaml action not SHA-pinned: {line.strip()}"


# ── Publish workflow supply-chain features ────────────────────────────────────

def test_publish_yaml_has_oidc_permission() -> None:
    content = PUBLISH_YAML.read_text()
    assert "id-token: write" in content, "docker-publish.yaml must grant id-token:write for OIDC signing"


def test_publish_yaml_has_attestations_permission() -> None:
    content = PUBLISH_YAML.read_text()
    assert "attestations: write" in content, "docker-publish.yaml must grant attestations:write"


def test_publish_yaml_has_sbom_step() -> None:
    content = PUBLISH_YAML.read_text()
    assert "anchore/sbom-action" in content, "docker-publish.yaml must include anchore/sbom-action SBOM step"


def test_publish_yaml_has_provenance() -> None:
    content = PUBLISH_YAML.read_text()
    assert "provenance: mode=max" in content, "docker-publish.yaml must set provenance: mode=max"


def test_publish_yaml_has_cosign_sign() -> None:
    content = PUBLISH_YAML.read_text()
    assert "cosign sign" in content, "docker-publish.yaml must include keyless cosign sign step"


# ── Contract settings ─────────────────────────────────────────────────────────

def test_contract_version_is_1_0() -> None:
    from promt_engine_service.core.config import settings

    assert settings.CONTRACT_VERSION == "1.0", (
        f"CONTRACT_VERSION must be '1.0', got {settings.CONTRACT_VERSION!r}"
    )


def test_contract_range_is_1_x() -> None:
    from promt_engine_service.core.config import settings

    assert settings.CONTRACT_RANGE == ">=1.1.0 <2.0.0", (
        f"CONTRACT_RANGE must be '>=1.1.0 <2.0.0', got {settings.CONTRACT_RANGE!r}"
    )


def test_service_version_in_contract_range() -> None:
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    from promt_engine_service.core.config import settings
    from promt_engine_service import __version__

    # SpecifierSet requires comma-separated specifiers (PEP 440 standard)
    normalized = settings.CONTRACT_RANGE.replace(" ", ",", 1)
    spec = SpecifierSet(normalized)
    assert spec.contains(Version(__version__)), (
        f"SERVICE_VERSION {__version__!r} is not within CONTRACT_RANGE {settings.CONTRACT_RANGE!r}"
    )
