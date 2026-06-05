"""Secret-redaction tests for persisted evidence (H-12 / P1-5).

Credentials that flow through workflow variables / module output must not be
written to evidence.jsonl in plaintext.
"""

from core.engine.redaction import (
    redact_text,
    redact_sensitive,
    redact_for_persistence,
)


class TestRedactText:
    def test_masks_url_credentials(self):
        out = redact_text("postgres://admin:s3cr3tpw@db.internal:5432/app")
        assert "s3cr3tpw" not in out
        assert "admin" not in out
        assert "db.internal" in out  # host preserved

    def test_masks_known_token_formats(self):
        for token in [
            "sk-ABCDEFGHIJKLMNOPQRSTUVWX",
            "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
            "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ01234",
            "AKIAIOSFODNN7EXAMPLE",
        ]:
            assert token not in redact_text(f"key={token} end")

    def test_masks_jwt_and_bearer(self):
        jwt = "eyJhbGciOi.eyJzdWIiOiAx.c2lnbmF0dXJl"
        assert jwt not in redact_text(f"auth {jwt}")
        assert "Bearer abcdef0123456789ABCDEF" not in redact_text("Bearer abcdef0123456789ABCDEF")

    def test_leaves_ordinary_text(self):
        s = "the quick brown fox jumps over 13 lazy dogs"
        assert redact_text(s) == s


class TestRedactStructures:
    def test_key_based_still_works(self):
        d = {"api_key": "anything", "user": "bob"}
        out = redact_sensitive(d)
        assert out["api_key"] == "[REDACTED]"
        assert out["user"] == "bob"

    def test_persistence_masks_values_in_nested_strings(self):
        data = {
            "note": "connect via postgres://u:p@h/db",
            "items": ["token sk-ABCDEFGHIJKLMNOPQRST", "fine"],
            "password": "topsecret",
        }
        out = redact_for_persistence(data)
        assert "p@h" not in out["note"] or ":p@" not in out["note"]
        assert "sk-ABCDEFGHIJKLMNOPQRST" not in out["items"][0]
        assert out["items"][1] == "fine"
        assert out["password"] == "[REDACTED]"

    def test_redact_sensitive_leaves_value_strings(self):
        # The live-output redactor must NOT mangle string values (back-compat).
        data = {"note": "sk-ABCDEFGHIJKLMNOPQRST"}
        assert redact_sensitive(data)["note"] == "sk-ABCDEFGHIJKLMNOPQRST"
