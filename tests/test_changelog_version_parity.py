"""Changelog/version parity — A32-changelog-version-parity.

`fa-auth-m8` shipped `2.0.1`/`2.0.2`, `auth-sdk-m8` shipped `3.1.1`/`3.1.2`, and
`imgtools_m8` shipped `2.1.0` — all tagged and released with no matching
`CHANGELOG.md` entry. This locks the fix in place for `prompt-engine-m8`: the
current package version must head a changelog entry, and no two entries may
claim the same version, so the next release cannot ship undocumented.

`H14`/`C18` extend this: a heading existing is not the same as it *carrying*
anything — `2.0.0` headed a dated, closed entry while every substantive change
sat under `[Unreleased]` instead, which the A32 lock could not see because it
only asked whether the heading was present. The non-empty check below is the
property A32 meant.
"""

import re
from pathlib import Path

from promt_engine_service import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

_HEADING_RE = re.compile(r"^## \[(?P<version>\d+\.\d+\.\d+)\]", re.MULTILINE)
_ALL_HEADING_RE = re.compile(r"^## \[(?P<version>[^\]]+)\].*$", re.MULTILINE)


def test_changelog_exists() -> None:
    assert CHANGELOG.exists(), "CHANGELOG.md must exist at the repo root."


def test_current_version_has_a_changelog_entry() -> None:
    """The version in `promt_engine_service.__version__` must head a CHANGELOG entry."""
    headings = _HEADING_RE.findall(CHANGELOG.read_text(encoding="utf-8"))
    assert __version__ in headings, (
        f"CHANGELOG.md has no '## [{__version__}]' heading for the current "
        f"version (promt_engine_service.__version__ = {__version__!r}); "
        "every published version must be documented."
    )


def test_current_version_section_is_non_empty() -> None:
    """A heading is not documentation — the section under it must carry content.

    `H14`: `2.0.0` headed a closed, dated entry while every Wave-1 change sat
    under `[Unreleased]` beneath it, undocumented in the section that would
    ship. Slices the text between the current version's heading and the next
    `## [...]` heading (or end of file) and asserts something other than a
    blank line or a bare sub-heading (`### Added` etc.) is in it.
    """
    text = CHANGELOG.read_text(encoding="utf-8")
    matches = list(_ALL_HEADING_RE.finditer(text))
    current = next((m for m in matches if m.group("version") == __version__), None)
    assert current is not None, (
        f"CHANGELOG.md has no '## [{__version__}]' heading to inspect."
    )
    start = current.end()
    later = [m for m in matches if m.start() > current.start()]
    end = later[0].start() if later else len(text)
    section = text[start:end]

    content_lines = [
        line
        for line in section.splitlines()
        if line.strip() and not line.strip().startswith("###")
    ]
    assert content_lines, (
        f"CHANGELOG.md's '## [{__version__}]' section has no content beyond "
        "sub-headings; a version heading with nothing under it ships "
        "undocumented exactly as 2.0.0 did before C18 (H14)."
    )


def test_changelog_headings_are_unique() -> None:
    """No two entries may claim the same version (the imgtools_m8 A32 finding)."""
    headings = _HEADING_RE.findall(CHANGELOG.read_text(encoding="utf-8"))
    duplicates = {v for v in headings if headings.count(v) > 1}
    assert not duplicates, (
        f"CHANGELOG.md has duplicate '## [x.y.z]' headings for: {sorted(duplicates)}"
    )


def test_unreleased_section_is_empty_after_a_fold() -> None:
    """`C18` opens a fresh, empty `[Unreleased]` when it folds into a release.

    Not a general rule (mid-wave `[Unreleased]` content is normal) — this
    fixture is post-fold, so its `[Unreleased]` section must be genuinely
    empty, not merely present, or the fold left something stranded.
    """
    text = CHANGELOG.read_text(encoding="utf-8")
    matches = list(_ALL_HEADING_RE.finditer(text))
    unreleased = next((m for m in matches if m.group("version") == "Unreleased"), None)
    assert unreleased is not None, "CHANGELOG.md has no '## [Unreleased]' heading."
    start = unreleased.end()
    later = [m for m in matches if m.start() > unreleased.start()]
    end = later[0].start() if later else len(text)
    section = text[start:end]
    assert not section.strip(), (
        "CHANGELOG.md's '## [Unreleased]' section is not empty after the "
        "C18 fold; either fold its content into the current version or "
        "confirm it belongs to genuinely new, unfolded work."
    )
