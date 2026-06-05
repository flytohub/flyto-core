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
