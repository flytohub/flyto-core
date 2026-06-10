"""git.clone URL validation — reject the ext:: transport (RCE) and other unsafe
clone targets (pass-2 G2)."""

import pytest

from core.modules.atomic.git.clone import (
    _validate_clone_url,
    _build_clone_cmd,
    UnsafeCloneURL,
)


class TestValidateCloneURL:
    @pytest.mark.parametrize("bad", [
        'ext::sh -c "id"',                 # remote-helper transport = RCE
        'ext::sh -c touch /tmp/pwned',
        'fd::17/foo',                      # another transport helper
        'file:///etc/passwd',              # file:// scheme not allowed
        '--upload-pack=/bin/sh',           # option injection
        '-o ProxyCommand=sh',
        '',                                # empty
    ])
    def test_rejects_unsafe(self, bad):
        with pytest.raises(UnsafeCloneURL):
            _validate_clone_url(bad)

    @pytest.mark.parametrize("ok", [
        'https://github.com/flytohub/flyto-core.git',
        'http://internal.example/repo.git',
        'ssh://git@github.com/org/repo.git',
        'git://github.com/org/repo.git',
        'git@github.com:org/repo.git',      # scp-style, no scheme
        '/tmp/local/repo.git',              # local clone is a legit git feature
    ])
    def test_allows_normal(self, ok):
        _validate_clone_url(ok)  # must not raise


def test_build_cmd_uses_double_dash():
    cmd = _build_clone_cmd('https://h/r.git', '/tmp/dest')
    assert '--' in cmd
    # '--' must come immediately before the positional url/destination
    i = cmd.index('--')
    assert cmd[i + 1] == 'https://h/r.git'
    assert cmd[i + 2] == '/tmp/dest'


def test_clone_declares_subprocess_execute_permission():
    """git.clone spawns host git (ext:: = RCE) so it MUST declare a dangerous
    host-exec permission, otherwise the capability gate would treat it as safe."""
    from core.modules import atomic  # noqa: F401 — registers modules
    from core.modules.registry import ModuleRegistry
    meta = ModuleRegistry.get_metadata('git.clone') or {}
    assert 'subprocess.execute' in meta.get('required_permissions', []), meta.get('required_permissions')


@pytest.mark.asyncio
async def test_clone_denied_by_default_policy(monkeypatch):
    """git.* is in the default denylist, so git.clone cannot run via execute_module
    without an explicit operator opt-in."""
    import core.module_policy as module_policy
    from core.module_policy import ModuleFilter
    from core.mcp_handler import execute_module
    monkeypatch.delenv("FLYTO_MODULE_ALLOWLIST", raising=False)
    monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
    monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())
    res = await execute_module(
        "git.clone", {"url": "https://github.com/x/y.git", "destination": "/tmp/z"}
    )
    assert res.get("ok") is False
    assert res.get("blocked_by") in ("module_filter", "required_permissions"), res


def test_clone_env_restricts_git_protocols():
    """The git subprocess env pins GIT_ALLOW_PROTOCOL to safe transports so the
    ext/fd remote-helpers are refused by git itself (defense in depth)."""
    from core.modules.atomic.git.clone import _build_clone_env
    env = _build_clone_env()
    assert "ext" not in env.get("GIT_ALLOW_PROTOCOL", "").split(":")
    assert "https" in env.get("GIT_ALLOW_PROTOCOL", "").split(":")
    assert env.get("GIT_TERMINAL_PROMPT") == "0"
