"""
Tests for crypto.totp

Correctness is pinned to the published RFC 6238 (TOTP) and RFC 4226 (HOTP)
test vectors rather than to this implementation's own output, so a refactor
that silently changes the algorithm fails here.
"""

import base64
import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.modules.errors import ValidationError

# RFC 6238 Appendix B seeds, given there as ASCII and used here Base32-encoded
# because that is the form an authenticator hands to a user.
RFC6238_SEED_SHA1 = b"12345678901234567890"
RFC6238_SEED_SHA256 = b"12345678901234567890123456789012"
RFC6238_SEED_SHA512 = b"1234567890123456789012345678901234567890123456789012345678901234"


def b32(seed: bytes) -> str:
    return base64.b32encode(seed).decode("ascii")


@pytest.fixture
def module_class():
    from core.modules import atomic  # noqa: F401 — triggers registration
    from core.modules.registry import ModuleRegistry
    return ModuleRegistry.get("crypto.totp")


async def run(module_class, params):
    instance = module_class(params, {})
    return await instance.execute()


class TestRFC6238Vectors:
    """The published TOTP vectors, all three hash algorithms, 8 digits."""

    SHA1_VECTORS = [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
        (20000000000, "65353130"),
    ]
    SHA256_VECTORS = [
        (59, "46119246"),
        (1111111109, "68084774"),
        (1111111111, "67062674"),
        (1234567890, "91819424"),
        (2000000000, "90698825"),
        (20000000000, "77737706"),
    ]
    SHA512_VECTORS = [
        (59, "90693936"),
        (1111111109, "25091201"),
        (1111111111, "99943326"),
        (1234567890, "93441116"),
        (2000000000, "38618901"),
        (20000000000, "47863826"),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("at,expected", SHA1_VECTORS)
    async def test_sha1(self, module_class, at, expected):
        result = await run(module_class, {
            "secret": b32(RFC6238_SEED_SHA1),
            "digits": 8,
            "period": 30,
            "algorithm": "SHA1",
            "at": at,
        })
        assert result["ok"] is True
        assert result["data"]["code"] == expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize("at,expected", SHA256_VECTORS)
    async def test_sha256(self, module_class, at, expected):
        result = await run(module_class, {
            "secret": b32(RFC6238_SEED_SHA256),
            "digits": 8,
            "period": 30,
            "algorithm": "SHA256",
            "at": at,
        })
        assert result["data"]["code"] == expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize("at,expected", SHA512_VECTORS)
    async def test_sha512(self, module_class, at, expected):
        result = await run(module_class, {
            "secret": b32(RFC6238_SEED_SHA512),
            "digits": 8,
            "period": 30,
            "algorithm": "SHA512",
            "at": at,
        })
        assert result["data"]["code"] == expected


class TestRFC4226Vectors:
    """TOTP is HOTP over counter = time // period, so the HOTP vectors apply."""

    HOTP_VECTORS = [
        "755224", "287082", "359152", "969429", "338314",
        "254676", "287922", "162583", "399871", "520489",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("counter,expected", list(enumerate(HOTP_VECTORS)))
    async def test_counter(self, module_class, counter, expected):
        result = await run(module_class, {
            "secret": b32(RFC6238_SEED_SHA1),
            "period": 30,
            "at": counter * 30,
        })
        assert result["data"]["code"] == expected
        assert result["data"]["digits"] == 6


class TestDefaults:
    """Omitted settings fall back to the RFC defaults an authenticator uses."""

    @pytest.mark.asyncio
    async def test_defaults_are_6_digits_sha1_30s(self, module_class):
        result = await run(module_class, {
            "secret": b32(RFC6238_SEED_SHA1),
            "at": 59,
        })
        data = result["data"]
        assert data["digits"] == 6
        assert data["period"] == 30
        assert data["algorithm"] == "SHA1"
        # Same instant as the RFC SHA1 vector, truncated to 6 digits.
        assert data["code"] == "287082"

    @pytest.mark.asyncio
    async def test_expires_in_counts_down_within_the_window(self, module_class):
        result = await run(module_class, {
            "secret": b32(RFC6238_SEED_SHA1),
            "period": 30,
            "at": 45,
        })
        assert result["data"]["expires_in"] == pytest.approx(15.0)

    @pytest.mark.asyncio
    async def test_issuer_and_account_are_null_without_a_uri(self, module_class):
        result = await run(module_class, {"secret": b32(RFC6238_SEED_SHA1), "at": 59})
        assert result["data"]["issuer"] is None
        assert result["data"]["account"] is None


class TestSecretFormats:
    """Secrets are copied off a screen, so accept the forms a screen shows."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("secret", [
        "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",          # canonical
        "gezdgnbvgy3tqojqgezdgnbvgy3tqojq",          # lowercase
        "GEZD GNBV GY3T QOJQ GEZD GNBV GY3T QOJQ",   # grouped, as displayed
        "  GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ  ",      # padded by a sloppy paste
    ])
    async def test_equivalent_renderings_of_one_secret(self, module_class, secret):
        result = await run(module_class, {"secret": secret, "at": 59})
        assert result["data"]["code"] == "287082"

    @pytest.mark.asyncio
    async def test_unpadded_secret_is_accepted(self, module_class):
        # 26 characters: a length Base32 cannot decode without added padding.
        result = await run(module_class, {"secret": "JBSWY3DPEHPK3PXPJBSWY3DPEH", "at": 0})
        assert len(result["data"]["code"]) == 6

    @pytest.mark.asyncio
    async def test_non_base32_secret_is_rejected(self, module_class):
        with pytest.raises(ValidationError) as exc:
            await run(module_class, {"secret": "not-base32!!", "at": 0})
        assert exc.value.field == "secret"
        assert "otpauth" in (exc.value.hint or "")

    @pytest.mark.asyncio
    async def test_empty_secret_is_rejected(self, module_class):
        with pytest.raises(ValidationError):
            await run(module_class, {"secret": "", "at": 0})

    @pytest.mark.asyncio
    async def test_non_string_secret_is_rejected(self, module_class):
        with pytest.raises(ValidationError):
            await run(module_class, {"secret": 12345, "at": 0})


class TestOtpauthUri:
    """The enrolment QR code's URI is the import path for an authenticator."""

    @pytest.mark.asyncio
    async def test_uri_supplies_the_secret(self, module_class):
        uri = f"otpauth://totp/Example:alice@example.com?secret={b32(RFC6238_SEED_SHA1)}&issuer=Example"
        result = await run(module_class, {"secret": uri, "at": 59})
        data = result["data"]
        assert data["code"] == "287082"
        assert data["issuer"] == "Example"
        assert data["account"] == "alice@example.com"

    @pytest.mark.asyncio
    async def test_uri_supplies_digits_period_and_algorithm(self, module_class):
        uri = (
            f"otpauth://totp/ACME:bob?secret={b32(RFC6238_SEED_SHA256)}"
            "&algorithm=SHA256&digits=8&period=30"
        )
        result = await run(module_class, {"secret": uri, "at": 1111111109})
        data = result["data"]
        assert data["algorithm"] == "SHA256"
        assert data["digits"] == 8
        assert data["period"] == 30
        assert data["code"] == "68084774"

    @pytest.mark.asyncio
    async def test_explicit_params_win_over_the_uri(self, module_class):
        uri = f"otpauth://totp/ACME:bob?secret={b32(RFC6238_SEED_SHA1)}&digits=8"
        result = await run(module_class, {"secret": uri, "digits": 6, "at": 59})
        assert result["data"]["digits"] == 6
        assert result["data"]["code"] == "287082"

    @pytest.mark.asyncio
    async def test_label_without_issuer_query_still_yields_both(self, module_class):
        uri = f"otpauth://totp/GitHub:chester?secret={b32(RFC6238_SEED_SHA1)}"
        result = await run(module_class, {"secret": uri, "at": 59})
        assert result["data"]["issuer"] == "GitHub"
        assert result["data"]["account"] == "chester"

    @pytest.mark.asyncio
    async def test_percent_encoded_label_is_decoded(self, module_class):
        uri = f"otpauth://totp/My%20Company:a%40b.com?secret={b32(RFC6238_SEED_SHA1)}"
        result = await run(module_class, {"secret": uri, "at": 59})
        assert result["data"]["issuer"] == "My Company"
        assert result["data"]["account"] == "a@b.com"

    @pytest.mark.asyncio
    async def test_hotp_uri_is_rejected(self, module_class):
        uri = f"otpauth://hotp/ACME:bob?secret={b32(RFC6238_SEED_SHA1)}&counter=1"
        with pytest.raises(ValidationError) as exc:
            await run(module_class, {"secret": uri, "at": 0})
        assert exc.value.field == "secret"
        assert "hotp" in (exc.value.hint or "").lower()

    @pytest.mark.asyncio
    async def test_uri_without_secret_is_rejected(self, module_class):
        with pytest.raises(ValidationError):
            await run(module_class, {"secret": "otpauth://totp/ACME:bob?issuer=ACME", "at": 0})

    @pytest.mark.asyncio
    async def test_uri_with_non_numeric_digits_is_rejected(self, module_class):
        uri = f"otpauth://totp/ACME:bob?secret={b32(RFC6238_SEED_SHA1)}&digits=six"
        with pytest.raises(ValidationError):
            await run(module_class, {"secret": uri, "at": 0})


class TestParameterBounds:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("params", [
        {"digits": 5},
        {"digits": 11},
        {"period": 0},
        {"period": 601},
        {"algorithm": "MD5"},
        {"min_remaining": -1},
    ])
    async def test_out_of_range_values_are_rejected(self, module_class, params):
        with pytest.raises(ValidationError):
            await run(module_class, {"secret": b32(RFC6238_SEED_SHA1), "at": 0, **params})

    @pytest.mark.asyncio
    async def test_min_remaining_must_be_shorter_than_period(self, module_class):
        with pytest.raises(ValidationError) as exc:
            await run(module_class, {
                "secret": b32(RFC6238_SEED_SHA1),
                "period": 30,
                "min_remaining": 30,
                "at": 0,
            })
        assert exc.value.field == "min_remaining"


class TestMinRemaining:
    """A code that rotates in transit is rejected by the server; skip ahead."""

    @pytest.mark.asyncio
    async def test_code_about_to_expire_rolls_to_the_next_window(self, module_class):
        # at=58 leaves 2s of the 0..59 window; ask for at least 5s.
        result = await run(module_class, {
            "secret": b32(RFC6238_SEED_SHA1),
            "period": 30,
            "min_remaining": 5,
            "at": 58,
        })
        # Rolled into the window starting at 60, i.e. HOTP counter 2.
        assert result["data"]["code"] == "359152"
        assert result["data"]["expires_in"] == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_fresh_code_is_returned_unchanged(self, module_class):
        result = await run(module_class, {
            "secret": b32(RFC6238_SEED_SHA1),
            "period": 30,
            "min_remaining": 5,
            "at": 31,
        })
        # Still in the 30..59 window: HOTP counter 1, no roll.
        assert result["data"]["code"] == "287082"
        assert result["data"]["expires_in"] == pytest.approx(29.0)


class TestSecretIsNotLeaked:
    @pytest.mark.asyncio
    async def test_secret_and_code_stay_out_of_the_logs(self, module_class, caplog):
        secret = b32(RFC6238_SEED_SHA1)
        with caplog.at_level("DEBUG"):
            result = await run(module_class, {"secret": secret, "at": 59})
        logged = "\n".join(record.getMessage() for record in caplog.records)
        assert secret not in logged
        assert result["data"]["code"] not in logged
