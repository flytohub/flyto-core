"""Database credentials cannot expand a provisioned verification scope."""
import ssl

import pytest

from core.verification.adapters import Connection, database_connection_options
from core.verification.runtime import BlockedError


@pytest.mark.parametrize('endpoint,dsn,isolated', [
    ('postgresql://127.0.0.1:55476', 'postgresql://pv@127.0.0.2:55476/test', True),
    ('postgresql://127.0.0.1:55476', 'postgresql://pv@127.0.0.1:5432/test', True),
    ('postgresql://127.0.0.1', 'postgresql://pv@127.0.0.1/test?host=169.254.169.254', True),
    ('postgresql://127.0.0.1', 'postgresql://pv@127.0.0.1/test', False),
    ('postgresql://169.254.169.254', 'postgresql://pv@169.254.169.254/test', True),
    ('postgresql://localhost', 'postgresql://pv@localhost/test', True),
    ('postgresql://8.8.8.8', 'postgresql://pv@8.8.8.8/test?sslmode=disable', False),
    ('postgresql://8.8.8.8', 'postgresql://pv@8.8.8.8/test?sslmode=require', False),
    ('postgresql://8.8.8.8', 'postgresql://pv@8.8.8.8/test?sslmode=verify-full&sslmode=disable', False),
    ('postgresql://127.0.0.1', 'postgresql:///test?host=/tmp', True),
])
def test_database_scope_rejects_unapproved_targets(endpoint, dsn, isolated):
    with pytest.raises(BlockedError):
        database_connection_options(Connection('postgres', endpoint, isolated=isolated, database_dsn=dsn))


def test_literal_scope_preserves_credentials_and_explicit_tls():
    options = database_connection_options(Connection('postgres', 'postgresql://8.8.8.8',
        database_dsn='postgresql://reader:p%40ss@8.8.8.8/proof?sslmode=verify-full'))
    assert options['host'] == '8.8.8.8'
    assert options['password'] == 'p@ss'
    assert options['ssl'].check_hostname is True
    assert options['ssl'].verify_mode == ssl.CERT_REQUIRED


def test_explicit_isolated_scope_uses_fixed_address():
    options = database_connection_options(Connection('postgres', 'postgresql://127.0.0.1:55476',
        isolated=True, database_dsn='postgresql://pv@127.0.0.1:55476/proof?sslmode=disable'))
    assert (options['host'], options['port'], options['ssl']) == ('127.0.0.1', 55476, False)
