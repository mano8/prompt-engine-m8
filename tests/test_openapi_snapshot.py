"""`A-C1` — the served OpenAPI document is published as a committed artifact.

`test_contract_fidelity.py` (`C6`) already asserts that the *served* document
says what ``schemas.list_params`` declares. What it cannot do is hand that
document to anybody: it builds the spec inside the test process and throws it
away. A consumer therefore had no machine-readable contract to diff against,
which is why `H1`, `H2` and `H6` each had to be found by reading source on both
sides of the wire instead of by comparing two files.

This module publishes the document. ``contracts/openapi.json`` is the served
spec, serialised deterministically, and the test below fails when the two
disagree — so the artifact can never describe a service that no longer exists.
Refresh it with::

    PROMPT_ENGINE_M8_WRITE_OPENAPI=1 pytest tests/test_openapi_snapshot.py

Nothing in this repository reads a consumer's source (`STANDALONE-CHILD-USABILITY`);
the artifact is published, and diffing it against a client is the client's job.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from promt_engine_service import __version__
from promt_engine_service.core.config import settings

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = REPO_ROOT / "contracts" / "openapi.json"

#: Set to refresh the artifact instead of asserting against it.
WRITE_ENV = "PROMPT_ENGINE_M8_WRITE_OPENAPI"

PREFIX = settings.API_PREFIX


def _serialise(document: Any) -> str:
    """Serialise deterministically.

    ``sort_keys`` because FastAPI's key order follows declaration order, which
    moves when a route is reordered without the contract changing at all — a
    diff that says "everything moved" is a diff nobody reads. LF and a trailing
    newline so a CRLF checkout cannot rewrite the artifact (the failure mode
    `C12` found in the registry generator).
    """
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _served_document(client) -> Any:
    response = client.get(f"{PREFIX}/openapi.json")
    assert response.status_code == 200, (
        f"GET {PREFIX}/openapi.json answered {response.status_code}; the "
        "contract artifact cannot be published from a spec the app will not serve."
    )
    return response.json()


def test_openapi_artifact_matches_the_served_document(client) -> None:
    """The committed contract is the contract the app serves."""
    served = _serialise(_served_document(client))

    if os.environ.get(WRITE_ENV):
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(served, encoding="utf-8", newline="\n")

    assert SNAPSHOT.exists(), (
        f"{SNAPSHOT.relative_to(REPO_ROOT)} is missing. It is the published "
        "contract artifact consumers diff against; regenerate it with "
        f"`{WRITE_ENV}=1 pytest tests/test_openapi_snapshot.py`."
    )

    committed = SNAPSHOT.read_text(encoding="utf-8")
    assert committed == served, (
        f"{SNAPSHOT.relative_to(REPO_ROOT)} no longer matches the served "
        "OpenAPI document. The served surface is the source of truth: refresh "
        f"the artifact with `{WRITE_ENV}=1 pytest tests/test_openapi_snapshot.py`, "
        "read the diff as the contract change it is, and hand it to the "
        "consumers that pin this contract."
    )


def test_artifact_publishes_the_version_a_consumer_pins(client) -> None:
    """`info.version` is the service version the consumer range is checked against.

    `astro-prompt-m8` pins ``>=2.0.0 <3.0.0`` and reads the live value from
    ``GET /meta``. The artifact has to carry the same number, or a consumer
    diffing the artifact offline would check its range against nothing.
    """
    document = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert document["info"]["version"] == __version__
    assert document["info"]["version"] == settings.SERVICE_VERSION


def test_artifact_carries_the_declared_list_vocabulary(client) -> None:
    """Sanity floor: the artifact is the whole document, not a trimmed one.

    `C6` asserts the vocabulary in depth against the served spec. This asserts
    only that the *published file* still reaches it, so a serialisation change
    that silently dropped parameters cannot pass as a formatting diff.
    """
    document = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    for resource in ("prompt-block", "prompt-template", "category"):
        operation = document["paths"][f"{PREFIX}/{resource}/"]["get"]
        names = {parameter["name"] for parameter in operation["parameters"]}
        assert {"skip", "limit", "q", "sort", "order"} <= names, resource
