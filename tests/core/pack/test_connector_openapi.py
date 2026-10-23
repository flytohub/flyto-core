"""OpenAPI 3 -> a draft ``connector`` section that refuses to validate until a person decides.

A consequence is a decision about what a call does to the world. An HTTP
method is not that decision: a GET can trigger a scan and a POST can be a
search. So the importer leaves every ``consequence`` unset and the pack does
not validate until each one is set by hand.
"""

import json

import pytest

from cli.pack import add_pack_parser, run_pack_command
from core.pack.manifest import PackManifestError, validate_pack_manifest
from core.pack.openapi import import_openapi

OPENAPI = {
    "openapi": "3.0.3",
    "info": {"title": "Example ratings API", "version": "1.0"},
    "servers": [{"url": "https://api.ratings.example"}],
    "components": {
        "securitySchemes": {
            "token": {"type": "http", "scheme": "basic"},
            "partner": {"type": "oauth2", "flows": {"clientCredentials": {
                "tokenUrl": "https://id.ratings.example/token", "scopes": {"read": "read"}}}},
            "cookie_session": {"type": "apiKey", "in": "cookie", "name": "sid"},
        },
        "parameters": {
            "Company": {"name": "company_guid", "in": "path", "required": True, "schema": {"type": "string"}},
        },
        "schemas": {
            "Note": {"type": "object", "required": ["text"], "properties": {
                "text": {"type": "string", "description": "Note text"},
                "pinned": {"type": "boolean"},
            }},
        },
    },
    "paths": {
        "/v1/companies/{company_guid}": {
            "parameters": [{"$ref": "#/components/parameters/Company"}],
            "get": {"operationId": "getCompany", "summary": "Get a company"},
        },
        "/v1/companies/{company_guid}/findings": {
            "parameters": [{"$ref": "#/components/parameters/Company"}],
            "get": {
                "operationId": "getCompanyFindings",
                "parameters": [
                    {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                    {"name": "X-Trace", "in": "header", "schema": {"type": "string"}},
                ],
            },
        },
        "/v1/companies/{company_guid}/notes": {
            "parameters": [{"$ref": "#/components/parameters/Company"}],
            "post": {
                "operationId": "createNote",
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Note"}}}},
            },
        },
        "/v1/reports": {
            "post": {
                "operationId": "uploadReport",
                "requestBody": {"content": {"multipart/form-data": {"schema": {"type": "object"}}}},
            },
        },
    },
}


def pack(connector):
    return {
        "schema": "flyto.pack.v1",
        "pack": {"id": "com.example.ratings", "version": "0.1.0", "namespaces": ["ratings"], "min_host": "2.41.0"},
        "runtime": {"binding": "connector"},
        "connector": connector,
    }


def test_imported_operations_have_no_consequence():
    draft = import_openapi(OPENAPI)
    operations = draft["connector"]["operations"]
    assert [o["id"] for o in operations] == [
        "get_company", "get_company_findings", "create_note", "upload_report",
    ]
    assert all("consequence" not in o for o in operations)


def test_the_draft_refuses_to_validate_until_every_consequence_is_set():
    connector = import_openapi(OPENAPI)["connector"]
    with pytest.raises(PackManifestError) as caught:
        validate_pack_manifest(pack(connector))
    assert caught.value.code == "CONSEQUENCE_MISSING"
    assert caught.value.operation == "get_company"

    decided = {"get_company": "observe", "get_company_findings": "observe", "create_note": "external_write"}
    for operation in connector["operations"]:
        if operation["id"] in decided:
            operation["consequence"] = decided[operation["id"]]
    with pytest.raises(PackManifestError) as caught:
        validate_pack_manifest(pack(connector))
    assert caught.value.operation == "upload_report"  # one left undecided still refuses

    connector["operations"][-1]["consequence"] = "external_write"
    manifest = validate_pack_manifest(pack(connector))
    assert len(manifest["modules"]) == 4


def test_inputs_come_from_parameters_and_the_json_body():
    operations = {o["id"]: o for o in import_openapi(OPENAPI)["connector"]["operations"]}
    findings = operations["get_company_findings"]
    assert findings["path"] == "/v1/companies/{company_guid}/findings"
    assert findings["inputs"]["company_guid"] == {"type": "string", "in": "path", "required": True}
    assert findings["inputs"]["limit"] == {"type": "integer", "in": "query"}
    note = operations["create_note"]
    assert note["method"] == "POST"
    assert note["inputs"]["text"] == {"type": "string", "in": "body", "required": True, "description": "Note text"}
    assert note["inputs"]["pinned"] == {"type": "boolean", "in": "body"}


def test_auth_is_imported_by_credential_name_only():
    auth = import_openapi(OPENAPI)["connector"]["auth"]
    assert {"kind": "api_token", "header": "Authorization", "scheme": "Basic", "credential": "token"} in auth
    assert {
        "kind": "oauth2_client_credentials",
        "token_url": "https://id.ratings.example/token",
        "scopes": ["read"],
        "credential": "partner",
    } in auth


def test_what_could_not_be_mapped_is_reported():
    unmapped = import_openapi(OPENAPI)["unmapped"]
    reasons = {(item["where"], item["reason"]) for item in unmapped}
    assert ("components.securitySchemes.cookie_session", "apiKey in cookie is not a supported auth kind") in reasons
    assert ("paths./v1/companies/{company_guid}/findings.get.parameters.X-Trace",
            "header parameters are not mapped") in reasons
    assert ("paths./v1/reports.post.requestBody", "only an application/json object body is mapped") in reasons
    assert any(item["reason"] == "consequence is a decision; set it by hand" for item in unmapped)


def test_a_document_that_is_not_openapi_3_is_refused():
    with pytest.raises(PackManifestError) as caught:
        import_openapi({"swagger": "2.0", "paths": {}})
    assert caught.value.code == "UNSUPPORTED_OPENAPI"


def test_the_cli_prints_the_draft(tmp_path, capsys):
    import argparse

    source = tmp_path / "openapi.json"
    source.write_text(json.dumps(OPENAPI), encoding="utf-8")
    parser = argparse.ArgumentParser()
    add_pack_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["pack", "import-openapi", str(source)])
    assert run_pack_command(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["connector"]["base_url"] == "https://api.ratings.example"
    assert all("consequence" not in o for o in out["connector"]["operations"])
