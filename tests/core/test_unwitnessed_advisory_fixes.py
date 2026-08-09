# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Regression coverage for advisory fixes that shipped without a test.

Building the generated security status page (``scripts/generate_security_status.py``)
required naming a regression test for every published advisory. Three had none —
the fix was in the source and correct, but nothing would have caught its removal:

* GHSA-hr7p-wg7r-hg9m — ``${env.VAR}`` interpolation read any environment secret
  despite ``env.get`` being denylisted. Fixed by ``module_policy.is_env_var_allowed``.
* GHSA-qq9q-xgm3-xv9g — LLM/API keys taken from the environment were sent to a
  caller-supplied ``base_url``. Fixed by ``utils.assert_env_credential_endpoint_allowed``.
* GHSA-mxcc-cr6x-2mvr — MCP ``run_recipe`` loaded workflows outside the bundled
  recipe directory. Fixed by the confinement in ``cli.recipe.load_recipe``.

An untested fix is one refactor away from being an unfixed bug, which is the
failure mode the whole coverage effort exists to prevent. These close that gap.
"""

import pytest

import core.module_policy as module_policy
from core.module_policy import ModuleFilter, is_env_var_allowed
from core.utils import CredentialEndpointError, assert_env_credential_endpoint_allowed


@pytest.fixture
def default_policy(monkeypatch):
    """Deny-by-default policy: no allowlist, no denylist, no grants."""
    monkeypatch.delenv("FLYTO_MODULE_ALLOWLIST", raising=False)
    monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
    monkeypatch.delenv("FLYTO_GRANTED_PERMISSIONS", raising=False)
    monkeypatch.delenv("FLYTO_ENV_VAR_ALLOWLIST", raising=False)
    monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())


# ---------------------------------------------------------------------------
# GHSA-hr7p-wg7r-hg9m — ${env.VAR} interpolation bypassed the env.get denylist
# ---------------------------------------------------------------------------


class TestEnvInterpolationPolicy:
    def test_env_interpolation_denied_when_env_get_is_denied(self, default_policy):
        """The headline bug: env.get was denylisted, but ${env.VAR} still read
        every secret in the process environment."""
        assert module_policy.module_filter.is_allowed("env.get") is False
        assert is_env_var_allowed("OPENAI_API_KEY") is False
        assert is_env_var_allowed("AWS_SECRET_ACCESS_KEY") is False

    def test_allowlisted_name_resolves(self, default_policy, monkeypatch):
        monkeypatch.setenv("FLYTO_ENV_VAR_ALLOWLIST", "APP_REGION,APP_TIER")
        assert is_env_var_allowed("APP_REGION") is True
        assert is_env_var_allowed("APP_TIER") is True
        assert is_env_var_allowed("OPENAI_API_KEY") is False

    def test_allowlist_supports_globs_without_becoming_a_wildcard(
        self, default_policy, monkeypatch
    ):
        monkeypatch.setenv("FLYTO_ENV_VAR_ALLOWLIST", "APP_*")
        assert is_env_var_allowed("APP_REGION") is True
        assert is_env_var_allowed("OPENAI_API_KEY") is False

    def test_empty_name_is_denied(self, default_policy):
        assert is_env_var_allowed("") is False
        assert is_env_var_allowed(None) is False

    def test_env_access_enabled_when_env_get_is_allowed(self, default_policy, monkeypatch):
        """The documented opt-in: allowing env.get turns env access back on, so
        the two controls cannot disagree."""
        monkeypatch.setenv("FLYTO_MODULE_ALLOWLIST", "env.get")
        monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())
        assert module_policy.module_filter.is_allowed("env.get") is True
        assert is_env_var_allowed("OPENAI_API_KEY") is True


# ---------------------------------------------------------------------------
# GHSA-qq9q-xgm3-xv9g — env-sourced API keys sent to a caller-supplied base_url
# ---------------------------------------------------------------------------


class TestEnvCredentialEndpointGuard:
    def test_env_key_to_untrusted_base_url_is_refused(self):
        """The headline bug: the workflow author picks base_url, the operator's
        OPENAI_API_KEY goes with the request, and the key lands on their host."""
        with pytest.raises(CredentialEndpointError):
            assert_env_credential_endpoint_allowed(
                "https://attacker.example/v1", key_from_env=True
            )

    def test_any_custom_endpoint_is_refused_by_default(self):
        """The guard is deliberately stricter than an SSRF check: even a
        well-known provider host is refused when named explicitly, because the
        SSRF guard happily allows an attacker's *public* host and cannot tell
        the two apart. Only the provider default or an operator-listed host
        may carry an environment credential."""
        with pytest.raises(CredentialEndpointError):
            assert_env_credential_endpoint_allowed(
                "https://api.openai.com/v1", key_from_env=True
            )

    def test_no_base_url_is_allowed(self):
        """Omitting base_url means the provider's official endpoint."""
        assert_env_credential_endpoint_allowed(None, key_from_env=True)
        assert_env_credential_endpoint_allowed("", key_from_env=True)

    def test_caller_supplied_key_may_go_anywhere(self):
        """The guard protects the *operator's* environment credentials. A key the
        caller passed explicitly is theirs to send where they like."""
        assert_env_credential_endpoint_allowed(
            "https://self-hosted.example/v1", key_from_env=False
        )

    def test_operator_can_extend_the_trusted_host_list(self, monkeypatch):
        """FLYTO_TRUSTED_LLM_HOSTS is the documented escape hatch for a
        self-hosted gateway, and it accepts fnmatch globs."""
        monkeypatch.setenv("FLYTO_TRUSTED_LLM_HOSTS", "llm.internal.corp,*.mycorp.com")
        assert_env_credential_endpoint_allowed(
            "https://llm.internal.corp/v1", key_from_env=True
        )
        assert_env_credential_endpoint_allowed(
            "https://gateway.mycorp.com/v1", key_from_env=True
        )
        with pytest.raises(CredentialEndpointError):
            assert_env_credential_endpoint_allowed(
                "https://attacker.example/v1", key_from_env=True
            )


# ---------------------------------------------------------------------------
# GHSA-mxcc-cr6x-2mvr — MCP run_recipe loaded workflows outside RECIPES_DIR
# ---------------------------------------------------------------------------


class TestRecipeLoaderConfinement:
    def test_traversal_recipe_name_is_refused(self):
        """`run_recipe` takes a caller-controlled name. Without confinement,
        '../../etc/passwd'-style names executed workflows outside the bundle."""
        from cli.recipe import load_recipe

        for hostile in (
            "../../../etc/passwd",
            "../../pyproject",
            "../conftest",
        ):
            assert load_recipe(hostile) is None

    def test_absolute_recipe_name_is_refused(self, tmp_path):
        """An absolute name must not escape the bundle either, even when the
        target exists and is valid YAML."""
        from cli.recipe import load_recipe

        planted = tmp_path / "evil.yaml"
        planted.write_text("name: evil\nsteps: []\n", encoding="utf-8")

        # Path joining with an absolute component discards the base directory,
        # which is exactly why the resolved path is re-checked against the root.
        assert load_recipe(str(planted.with_suffix(""))) is None

    def test_a_bundled_recipe_still_loads(self):
        """Confinement must not break the feature it protects."""
        from cli.recipe import RECIPES_DIR, load_recipe

        bundled = sorted(RECIPES_DIR.glob("*.yaml"))
        if not bundled:
            pytest.skip("no bundled recipes in this checkout")

        assert load_recipe(bundled[0].stem) is not None
