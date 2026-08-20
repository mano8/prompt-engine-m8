"""`C6` — the served contract is the declared contract, and it is sufficient.

`H2` and `H6` both lived inside fully-covered code on both sides of the wire.
Coverage could not see them because every test on each side stopped at the
boundary: the client mocked transport, and the service built its own request
objects in-process. Two models that never meet cannot be observed to disagree.

The tests here cross that boundary in the only direction a standalone service
can (`STANDALONE-CHILD-USABILITY` — nothing in this repository may read a
consumer's source). They assert the **published** contract, which is what a
consumer mirrors:

* the OpenAPI document names exactly the parameters and enum values that
  ``schemas.list_params`` declares — so a client generated from the schema and
  a client written against the declaration are the same client;
* every published value is *accepted* — the declaration has no member the
  service would reject, which is the failure a list of names alone cannot rule
  out; and
* the published required body fields are **necessary and sufficient** — a
  request carrying exactly them succeeds, and dropping any one of them fails.

That last property is the one that fails on today's `astro-prompt-m8`:
`CategoryCreateSchema` is `.strict({ name })` and complete-looking, while the
published contract requires `{name, type}`. A strict schema that is wrong is
worse than a loose one — it validates locally and fails remotely.
"""

from __future__ import annotations

import uuid

import pytest

from promt_engine_service.core.config import settings
from promt_engine_service.schemas.list_params import (
    CATEGORY_LIST_VOCABULARY,
    MAX_PAGE_SIZE,
    PROMPT_BLOCK_LIST_VOCABULARY,
    PROMPT_TEMPLATE_LIST_VOCABULARY,
    ListSortOrder,
    ListVocabulary,
)

PREFIX = settings.API_PREFIX

LIST_ROUTES = [
    pytest.param("/prompt-block/", PROMPT_BLOCK_LIST_VOCABULARY, id="prompt-block"),
    pytest.param(
        "/prompt-template/", PROMPT_TEMPLATE_LIST_VOCABULARY, id="prompt-template"
    ),
    pytest.param("/category/", CATEGORY_LIST_VOCABULARY, id="category"),
]


@pytest.fixture
def spec(client):
    return client.get(f"{PREFIX}/openapi.json").json()


@pytest.fixture
def headers(auth_headers):
    return auth_headers("superadmin", is_superuser=True)


def list_parameters(spec, path: str) -> dict[str, dict]:
    operation = spec["paths"][f"{PREFIX}{path}"]["get"]
    return {param["name"]: param for param in operation.get("parameters", [])}


def published_enum(spec, parameter: dict) -> list[str]:
    """Read an enum out of a parameter schema, following one ``$ref`` hop.

    An optional enum parameter is published as ``anyOf: [$ref, null]``, so the
    values a client would generate from the document are one level down.
    """
    schema = parameter["schema"]
    for candidate in schema.get("anyOf", [schema]):
        ref = candidate.get("$ref")
        if ref:
            name = ref.rsplit("/", 1)[-1]
            return spec["components"]["schemas"][name]["enum"]
    return schema["enum"]


# --------------------------------------------------------------------------
# The document says what the declaration says.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("path", "vocabulary"), LIST_ROUTES)
def test_the_published_parameters_are_the_declared_ones(
    spec, path: str, vocabulary: ListVocabulary
) -> None:
    expected = {"skip", "limit", "q", "sort", "order"}
    if vocabulary.csrc:
        expected.add("csrc")
    if vocabulary.facets:
        expected.add("f")

    assert set(list_parameters(spec, path)) == expected


@pytest.mark.parametrize(("path", "vocabulary"), LIST_ROUTES)
def test_the_published_enums_are_the_declared_vocabulary(
    spec, path: str, vocabulary: ListVocabulary
) -> None:
    parameters = list_parameters(spec, path)

    assert published_enum(spec, parameters["sort"]) == list(vocabulary.sort)
    assert published_enum(spec, parameters["order"]) == [
        member.value for member in ListSortOrder
    ]
    if vocabulary.csrc:
        assert published_enum(spec, parameters["csrc"]) == list(vocabulary.csrc)


def test_the_facet_vocabulary_is_documented_where_it_cannot_be_an_enum(
    spec,
) -> None:
    """``f`` carries several values in one string, so its type cannot be an enum.

    The values still have to reach the document somehow, or a client generating
    from the schema has nothing to generate. They are published in the
    parameter description instead, and that is asserted rather than trusted —
    an undocumented facet is a facet nobody sends.
    """
    for path, vocabulary in (
        ("/prompt-block/", PROMPT_BLOCK_LIST_VOCABULARY),
        ("/prompt-template/", PROMPT_TEMPLATE_LIST_VOCABULARY),
    ):
        description = list_parameters(spec, path)["f"].get("description", "")
        for facet in vocabulary.facets:
            assert facet in description, (path, facet)


# --------------------------------------------------------------------------
# Every published value is one the service accepts.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("path", "vocabulary"), LIST_ROUTES)
def test_every_published_sort_is_accepted(
    client, headers, spec, path: str, vocabulary: ListVocabulary
) -> None:
    for value in published_enum(spec, list_parameters(spec, path)["sort"]):
        for order in ("asc", "desc"):
            response = client.get(
                f"{PREFIX}{path}",
                params={"sort": value, "order": order},
                headers=headers,
            )
            assert response.status_code == 200, (value, order, response.text)


@pytest.mark.parametrize(("path", "vocabulary"), LIST_ROUTES)
def test_every_published_search_column_is_accepted(
    client, headers, spec, path: str, vocabulary: ListVocabulary
) -> None:
    if not vocabulary.csrc:
        pytest.skip("endpoint declares no csrc")
    for value in published_enum(spec, list_parameters(spec, path)["csrc"]):
        response = client.get(
            f"{PREFIX}{path}", params={"q": "x", "csrc": value}, headers=headers
        )
        assert response.status_code == 200, (value, response.text)


@pytest.mark.parametrize(
    ("path", "vocabulary"),
    [
        pytest.param("/prompt-block/", PROMPT_BLOCK_LIST_VOCABULARY, id="prompt-block"),
        pytest.param(
            "/prompt-template/", PROMPT_TEMPLATE_LIST_VOCABULARY, id="prompt-template"
        ),
    ],
)
def test_every_declared_facet_is_accepted(
    client, headers, path: str, vocabulary: ListVocabulary
) -> None:
    for value in vocabulary.facets:
        response = client.get(f"{PREFIX}{path}", params={"f": value}, headers=headers)
        assert response.status_code == 200, (value, response.text)

    # ...and all of them at once, which is what "select all" in the filter sends.
    joined = client.get(
        f"{PREFIX}{path}", params={"f": ",".join(vocabulary.facets)}, headers=headers
    )
    assert joined.status_code == 200, joined.text


# --------------------------------------------------------------------------
# The page ceiling is published, and it is the declared one.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("path", "vocabulary"), LIST_ROUTES)
def test_the_published_page_ceiling_is_the_declared_one(
    spec, path: str, vocabulary: ListVocabulary
) -> None:
    """``limit`` publishes ``MAX_PAGE_SIZE`` as its maximum on every list route.

    A ceiling a caller cannot read is a ceiling a caller discovers as a ``422``
    in production. It reaches the document through ``le=``, so this asserts the
    document rather than the annotation.
    """
    schema = list_parameters(spec, path)["limit"]["schema"]
    assert schema["maximum"] == MAX_PAGE_SIZE, (path, schema)
    assert schema["minimum"] == 1, (path, schema)


@pytest.mark.parametrize(("path", "vocabulary"), LIST_ROUTES)
def test_the_page_ceiling_holds_at_its_boundary(
    client, headers, path: str, vocabulary: ListVocabulary
) -> None:
    """Exactly the ceiling is served; one past it is a ``422``.

    Asserted at the boundary rather than with a round number, so raising
    ``MAX_PAGE_SIZE`` cannot leave the declaration and the behaviour disagreeing.
    """
    at_ceiling = client.get(
        f"{PREFIX}{path}", params={"limit": MAX_PAGE_SIZE}, headers=headers
    )
    assert at_ceiling.status_code == 200, at_ceiling.text

    over_ceiling = client.get(
        f"{PREFIX}{path}", params={"limit": MAX_PAGE_SIZE + 1}, headers=headers
    )
    assert over_ceiling.status_code == 422, over_ceiling.text


# --------------------------------------------------------------------------
# Published request bodies: necessary and sufficient.
# --------------------------------------------------------------------------

CREATE_ROUTES = [
    pytest.param(
        "/category/add/",
        {"name": "Fidelity", "type": "prompt_block"},
        id="category",
    ),
    pytest.param(
        "/prompt-block/add/",
        {"name": "Fidelity", "content": "body", "type": "task"},
        id="prompt-block",
    ),
    pytest.param("/prompt-template/add/", {"name": "Fidelity"}, id="prompt-template"),
]


def required_body_fields(spec, path: str) -> list[str]:
    body = spec["paths"][f"{PREFIX}{path}"]["post"]["requestBody"]
    ref = body["content"]["application/json"]["schema"]["$ref"]
    schema = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    return schema.get("required", [])


@pytest.mark.parametrize(("path", "payload"), CREATE_ROUTES)
def test_the_published_required_fields_are_exactly_the_payload_keys(
    spec, path: str, payload: dict
) -> None:
    """The document and the minimal working payload agree.

    Either direction being wrong is a defect a consumer pays for: extra
    published fields make a correct client send noise it cannot derive
    (`slug` did exactly this on `CategoryCreate`), and missing ones make a
    complete-looking client fail remotely (`H2`).
    """
    assert sorted(required_body_fields(spec, path)) == sorted(payload)


@pytest.mark.parametrize(("path", "payload"), CREATE_ROUTES)
def test_a_payload_of_exactly_the_required_fields_is_sufficient(
    client, auth_headers, path: str, payload: dict
) -> None:
    response = client.post(
        f"{PREFIX}{path}", headers=auth_headers("writer", uuid.uuid4()), json=payload
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(("path", "payload"), CREATE_ROUTES)
def test_every_required_field_is_necessary(
    client, auth_headers, path: str, payload: dict
) -> None:
    headers = auth_headers("writer", uuid.uuid4())
    for omitted in payload:
        short = {key: value for key, value in payload.items() if key != omitted}
        response = client.post(f"{PREFIX}{path}", headers=headers, json=short)
        assert response.status_code == 422, (omitted, response.text)


# --------------------------------------------------------------------------
# Identity — what a consumer's preflight reads before it trusts any of the above.
# --------------------------------------------------------------------------


def test_meta_reports_the_contract_a_consumer_pins(client) -> None:
    """`H5`'s other half: the guard is unwired client-side, but the service
    must still serve the identity that guard is written against."""
    body = client.get(f"{PREFIX}/meta").json()

    assert body["service"] == "prompt-engine-m8"
    assert body["version"] == settings.SERVICE_VERSION
    assert body["contract"]["name"] == settings.CONTRACT_NAME == "prompt-engine-m8"
    assert body["contract"]["version"] == settings.CONTRACT_VERSION
    assert body["contract"]["range"] == settings.CONTRACT_RANGE


def test_the_dependency_free_liveness_route_is_ping_not_the_prefix_root(
    client,
) -> None:
    """`H4`/`D-C3`: the fix is client-side, so this pins what the client must call.

    The API-prefix root is deliberately *not* mounted; a consumer probing it
    gets a 404, which is the bug `astro-prompt-m8` carries today.
    """
    assert client.get(f"{PREFIX}/ping").status_code == 200
    assert client.get(f"{PREFIX}/").status_code == 404
