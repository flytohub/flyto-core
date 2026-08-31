# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""How far the `database.*` and `db.*` modules actually follow reality.

Eight modules, and they do not share a rung -- not across modules and, for the
two SQL writers, not across returns of the same module. What these tests pin is
the *discrimination*: that a number derived from the caller's own input and a
number the server sent produce different rungs even when they are the same
integer, and that the two Redis modules sitting in one file land on different
rungs because the evidence available to them differs.

Where a real engine can answer the question, one does. Every sqlite test runs
against real sqlite3, including the INDETERMINATE case, which is provoked with
a `BEFORE INSERT ... RAISE(IGNORE)` trigger -- a row that is offered, accepted
without error, and not stored. No mock can tell you what `cursor.rowcount` does
there and it is exactly the fact the rung turns on.

asyncpg, aiomysql and motor are not installed here and no server is available,
so those backends are driven through injected fakes whose only job is to return
the command tags, rowcounts and result objects the real drivers return. Where a
fake's shape is load-bearing -- `InsertOneResult.inserted_id` being generated
client-side, `aiomysql.connect` defaulting to autocommit=False -- the reason is
written next to it, because the fake is standing in for a claim about the
driver and a claim is what a reader has to be able to check.
"""

import asyncio
import sqlite3
import sys
import types

import pytest

from core.engine.outcome import ClaimBy, Outcome, read_envelope
from core.modules.atomic.database.insert import database_insert
from core.modules.atomic.database.update import database_update
from core.modules.third_party.database.connectors.mongodb_find import mongodb_find
from core.modules.third_party.database.connectors.mongodb_insert import mongodb_insert
from core.modules.third_party.database.connectors.mysql import mysql_query
from core.modules.third_party.database.connectors.postgresql import postgresql_query
from core.modules.third_party.database.redis import RedisGetModule, RedisSetModule


_insert = database_insert.__wrapped_func__
_update = database_update.__wrapped_func__
_mongo_find = mongodb_find.__wrapped_func__
_mongo_insert = mongodb_insert.__wrapped_func__
_mysql = mysql_query.__wrapped_func__
_postgres = postgresql_query.__wrapped_func__


def _run(func, params):
    """Invoke a module the way the engine does: one dict, under 'params'."""
    return asyncio.run(func({'params': params}))


def _envelope(result):
    found = read_envelope(result)
    assert found is not None, f"no well-formed envelope in {sorted(result)}"
    return found


def _rung(result):
    return Outcome(_envelope(result)['rung'])


def _effects(result):
    return _envelope(result)['effects']


def _effect(result, kind):
    """The one effect of this kind, asserting it is not ambiguous."""
    matching = [e for e in _effects(result) if e['kind'] == kind]
    assert len(matching) == 1, [e['kind'] for e in _effects(result)]
    return matching[0]


def _kinds(result):
    return [e['kind'] for e in _effects(result)]


# ===========================================================================
# database.insert -- the module whose count was arithmetic on its own input
# ===========================================================================


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    """A file-backed sqlite db reached through env, not through params.

    Through env deliberately: `_dsn_guard.guard_client_dsn` rejects a
    client-supplied `database` param unless FLYTO_ALLOW_CLIENT_DB_DSN is set, and
    a test that flipped that flag would be testing the module with a security
    control disabled. A file rather than ':memory:' because the module opens a
    fresh connection per call.
    """
    path = tmp_path / "ladder.sqlite3"
    monkeypatch.setenv("SQLITE_DATABASE", str(path))
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (a INT, b TEXT)")
    # A row offered, accepted without error, and not stored. `RAISE(IGNORE)`
    # abandons the current row and lets the statement succeed, which is the one
    # honest way to make offered != stored on a real engine.
    conn.execute(
        "CREATE TRIGGER skip_high BEFORE INSERT ON t WHEN NEW.a > 100 "
        "BEGIN SELECT RAISE(IGNORE); END"
    )
    conn.commit()
    conn.close()
    return {'database_type': 'sqlite', 'table': 't'}


def _rows_on_disk(monkeypatch_env_path):
    conn = sqlite3.connect(monkeypatch_env_path)
    try:
        return conn.execute("SELECT a, b FROM t ORDER BY a").fetchall()
    finally:
        conn.close()


class TestSqliteInsert:
    def test_a_stored_row_is_counted_by_the_engine_not_by_us(self, sqlite_db):
        result = _run(_insert, {**sqlite_db, 'data': {'a': 1, 'b': 'x'}})

        assert result['inserted_count'] == 1  # offered
        assert result['observed_count'] == 1  # sqlite3_changes()
        assert _rung(result) is Outcome.OBSERVED
        assert _envelope(result)['claim_by'] == ClaimBy.INFERRED.value

        observed = _effect(result, 'rows_reported_inserted')
        assert observed['count'] == 1
        assert 'sqlite3_changes' in observed['measured_by']

    def test_the_offered_count_is_carried_and_labelled_as_input(self, sqlite_db):
        """The number that used to be the whole claim, now named for what it is.

        `inserted_count` is `len(rows)`. It has to keep travelling -- consumers
        read it -- but beside it must sit the fact that no server contributed to
        it, or the field goes on being read as a measurement.
        """
        result = _run(
            _insert,
            {**sqlite_db, 'data': [{'a': 1, 'b': 'x'}, {'a': 2, 'b': 'y'}]},
        )

        offered = _effect(result, 'rows_offered')
        assert offered['count'] == 2
        assert offered['measured_by'] == 'len(rows) -- the list this module was handed'
        assert 'stored every row, some of them, or none' in offered['detail']

    def test_a_row_the_engine_silently_dropped_is_indeterminate_not_observed(
        self, sqlite_db, tmp_path
    ):
        """The case the old `len(rows)` could not see, on a real engine.

        Two rows are offered, one trips the trigger and is never stored, and
        sqlite raises nothing. `inserted_count` says 2 -- it always would. Only
        `observed_count` moves, and the rung moves with it.

        INDETERMINATE rather than FAILED because nobody declared a row-count
        contract: this trigger is doing exactly what its author wrote, and a red
        mark on a correctly-behaving schema is the error the claim_by axis
        exists to prevent.
        """
        result = _run(
            _insert,
            {**sqlite_db, 'data': [{'a': 1, 'b': 'kept'}, {'a': 999, 'b': 'dropped'}]},
        )

        assert result['ok'] is True
        assert result['inserted_count'] == 2
        assert result['observed_count'] == 1
        assert _rung(result) is Outcome.INDETERMINATE
        assert _envelope(result)['claim_by'] == ClaimBy.INFERRED.value

        disagreement = _effect(result, 'row_count_disagrees')
        assert disagreement['expected_count'] == 2
        assert disagreement['actual_count'] == 1

        # And the database agrees with the lower number, not the higher one.
        assert _rows_on_disk(tmp_path / "ladder.sqlite3") == [(1, 'kept')]

    def test_the_two_counts_are_equal_whenever_nothing_went_wrong(self, sqlite_db):
        """Which is why the old field looked correct for as long as it did."""
        result = _run(
            _insert,
            {**sqlite_db, 'data': [{'a': i, 'b': 'x'} for i in range(5)]},
        )

        assert result['inserted_count'] == result['observed_count'] == 5
        assert _rung(result) is Outcome.OBSERVED

    def test_the_rows_are_committed(self, sqlite_db, tmp_path):
        """OBSERVED would be worthless if the close discarded the transaction."""
        _run(_insert, {**sqlite_db, 'data': {'a': 42, 'b': 'committed'}})

        assert _rows_on_disk(tmp_path / "ladder.sqlite3") == [(42, 'committed')]


# ---------------------------------------------------------------------------
# postgres -- fake asyncpg returning real command tags
# ---------------------------------------------------------------------------


class _FakePgConnection:
    def __init__(self, state):
        self._state = state
        self.closed = False

    async def execute(self, query, *args):
        return self._state['tag']

    async def fetchrow(self, query, *args):
        return self._state['returning_row']

    async def fetch(self, query, *args):
        return list(self._state['rows'])

    async def close(self):
        self.closed = True


@pytest.fixture
def fake_postgres(monkeypatch):
    """Inject an `asyncpg` whose command tags are the ones a server sends."""
    state = {'tag': 'INSERT 0 1', 'returning_row': {'id': 7}, 'rows': []}

    async def connect(dsn, *args, **kwargs):
        conn = _FakePgConnection(state)
        state.setdefault('connections', []).append(conn)
        return conn

    fake = types.ModuleType('asyncpg')
    fake.connect = connect
    monkeypatch.setitem(sys.modules, 'asyncpg', fake)
    # Reached through env, so `guard_client_dsn` sees no client-supplied target.
    monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@127.0.0.1:5432/d')
    return state


class TestPostgresInsert:
    def test_the_command_tag_that_used_to_be_thrown_away_is_the_measurement(
        self, fake_postgres
    ):
        """`await conn.execute(...)` returned 'INSERT 0 1' and nobody read it."""
        fake_postgres['tag'] = 'INSERT 0 1'
        result = _run(
            _insert,
            {'database_type': 'postgresql', 'table': 't', 'data': {'a': 1}},
        )

        assert result['observed_count'] == 1
        assert _rung(result) is Outcome.OBSERVED
        assert 'command tag' in _effect(result, 'rows_reported_inserted')['measured_by']

    def test_counts_are_totalled_across_the_statements(self, fake_postgres):
        fake_postgres['tag'] = 'INSERT 0 1'
        result = _run(
            _insert,
            {
                'database_type': 'postgresql',
                'table': 't',
                'data': [{'a': 1}, {'a': 2}, {'a': 3}],
            },
        )

        assert result['inserted_count'] == result['observed_count'] == 3
        assert _rung(result) is Outcome.OBSERVED

    def test_a_server_reported_zero_is_a_disagreement_not_a_success(
        self, fake_postgres
    ):
        """'INSERT 0 0' is the server saying it stored nothing."""
        fake_postgres['tag'] = 'INSERT 0 0'
        result = _run(
            _insert,
            {'database_type': 'postgresql', 'table': 't', 'data': {'a': 1}},
        )

        assert result['inserted_count'] == 1
        assert result['observed_count'] == 0
        assert _rung(result) is Outcome.INDETERMINATE

    @pytest.mark.parametrize("tag", ['CREATE TABLE', 'INSERT', 'INSERT 0', ''])
    def test_a_tag_carrying_no_count_stays_at_accepted(self, fake_postgres, tag):
        """No number crossed the wire, so `observed_count` is null, not zero.

        A zero would be indistinguishable from the server reporting zero, which
        is the confusion `database.query` was carrying before this contract.
        """
        fake_postgres['tag'] = tag
        result = _run(
            _insert,
            {'database_type': 'postgresql', 'table': 't', 'data': {'a': 1}},
        )

        assert result['observed_count'] is None
        assert _rung(result) is Outcome.ACCEPTED
        assert 'rows_not_counted' in _kinds(result)
        assert _effect(result, 'rows_not_counted')['count_reported'] is False

    def test_one_silent_statement_makes_the_whole_total_unreported(
        self, fake_postgres
    ):
        """A partial total presented as a total would be the worse lie.

        The fake answers with the same tag for every row, so this drives the
        rule directly rather than through the loop: any unreported statement
        takes the total to null, never to a smaller integer that reads as a
        short insert.
        """
        from core.modules.atomic.database.insert import _total_reported

        assert _total_reported([1, 1, 1]) == 3
        assert _total_reported([1, None, 1]) is None
        assert _total_reported([1, -1, 1]) is None

    def test_returning_counts_the_rows_the_server_actually_sent_back(
        self, fake_postgres
    ):
        """The strongest evidence available on any path in this module."""
        fake_postgres['returning_row'] = {'id': 7}
        result = _run(
            _insert,
            {
                'database_type': 'postgresql',
                'table': 't',
                'data': {'a': 1},
                'returning': ['id'],
            },
        )

        assert result['returning_data'] == [{'id': 7}]
        assert result['observed_count'] == 1
        assert _rung(result) is Outcome.OBSERVED
        assert 'RETURNING' in _effect(result, 'rows_reported_inserted')['measured_by']

    def test_a_returning_insert_that_stored_nothing_no_longer_raises(
        self, fake_postgres
    ):
        """`dict(None)` raised TypeError here; a suppressed row is not a crash.

        `fetchrow` gives None when the statement stored no row -- what a BEFORE
        INSERT trigger returning NULL does. The row is simply absent from the
        count, the totals disagree, and the rung says so.
        """
        fake_postgres['returning_row'] = None
        result = _run(
            _insert,
            {
                'database_type': 'postgresql',
                'table': 't',
                'data': {'a': 1},
                'returning': ['id'],
            },
        )

        assert result['returning_data'] == []
        assert result['observed_count'] == 0
        assert result['inserted_count'] == 1
        assert _rung(result) is Outcome.INDETERMINATE


# ---------------------------------------------------------------------------
# mysql -- fake aiomysql returning real rowcount values
# ---------------------------------------------------------------------------


class _FakeMySQLCursor:
    def __init__(self, state):
        self._state = state
        self.rowcount = state['rowcount']
        self.description = state.get('description')

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, query, args=None):
        self._state.setdefault('calls', []).append('execute')
        return self.rowcount

    async def fetchall(self):
        return list(self._state['rows'])


class _FakeMySQLConnection:
    def __init__(self, state):
        self._state = state

    def cursor(self, cursor_class=None):
        return _FakeMySQLCursor(self._state)

    async def commit(self):
        self._state.setdefault('calls', []).append('commit')

    def close(self):
        self._state.setdefault('calls', []).append('close')

    async def ensure_closed(self):
        pass


@pytest.fixture
def fake_mysql(monkeypatch):
    state = {'rowcount': 1, 'rows': [], 'description': None, 'calls': []}

    async def connect(**kwargs):
        return _FakeMySQLConnection(state)

    fake = types.ModuleType('aiomysql')
    fake.connect = connect
    fake.DictCursor = object
    monkeypatch.setitem(sys.modules, 'aiomysql', fake)
    monkeypatch.setenv('MYSQL_HOST', '127.0.0.1')
    monkeypatch.setenv('MYSQL_DATABASE', 'd')
    monkeypatch.setenv('MYSQL_USER', 'u')
    monkeypatch.setenv('MYSQL_PASSWORD', 'p')
    return state


class TestMysqlInsert:
    def test_affected_rows_off_the_ok_packet_earns_observed(self, fake_mysql):
        fake_mysql['rowcount'] = 1
        result = _run(
            _insert,
            {'database_type': 'mysql', 'table': 't', 'data': [{'a': 1}, {'a': 2}]},
        )

        assert result['observed_count'] == 2
        assert _rung(result) is Outcome.OBSERVED
        assert 'OK packet' in _effect(result, 'rows_reported_inserted')['measured_by']

    def test_a_rowcount_of_minus_one_is_not_a_count(self, fake_mysql):
        """PEP 249's "cannot determine". Not zero, and not evidence."""
        fake_mysql['rowcount'] = -1
        result = _run(
            _insert,
            {'database_type': 'mysql', 'table': 't', 'data': {'a': 1}},
        )

        assert result['observed_count'] is None
        assert _rung(result) is Outcome.ACCEPTED

    def test_a_reported_zero_is_a_count_and_disagrees(self, fake_mysql):
        """-1 and 0 are different answers, and only one of them is a number."""
        fake_mysql['rowcount'] = 0
        result = _run(
            _insert,
            {'database_type': 'mysql', 'table': 't', 'data': {'a': 1}},
        )

        assert result['observed_count'] == 0
        assert _rung(result) is Outcome.INDETERMINATE


# ===========================================================================
# database.update -- already counting; now able to say so
# ===========================================================================


class TestUpdateOutcomes:
    def test_sqlite_counts_matched_rows(self, sqlite_db, tmp_path):
        _run(_insert, {**sqlite_db, 'data': [{'a': 1, 'b': 'x'}, {'a': 2, 'b': 'x'}]})

        result = _run(
            _update,
            {**sqlite_db, 'data': {'b': 'y'}, 'where': {'b': 'x'}},
        )

        assert result['updated_count'] == 2
        assert _rung(result) is Outcome.OBSERVED
        effect = _effect(result, 'rows_updated')
        assert effect['count'] == 2
        assert 'sqlite3_changes' in effect['measured_by']

    def test_a_counted_zero_is_still_observed(self, sqlite_db):
        """The server said "no rows matched". That is a measurement of the world.

        This is the case `database.query` had to be corrected on in the other
        direction: there, zero ROWS RETURNED was not evidence. Here, zero rows
        MATCHED is the engine's own answer to the question asked, and the two
        must not be conflated because they are both spelled 0.
        """
        _run(_insert, {**sqlite_db, 'data': {'a': 1, 'b': 'x'}})

        result = _run(
            _update,
            {**sqlite_db, 'data': {'b': 'y'}, 'where': {'b': 'nothing-matches-this'}},
        )

        assert result['updated_count'] == 0
        assert _rung(result) is Outcome.OBSERVED

    def test_the_update_is_committed(self, sqlite_db, tmp_path):
        _run(_insert, {**sqlite_db, 'data': {'a': 1, 'b': 'before'}})
        _run(_update, {**sqlite_db, 'data': {'b': 'after'}, 'where': {'a': 1}})

        assert _rows_on_disk(tmp_path / "ladder.sqlite3") == [(1, 'after')]

    def test_postgres_reads_the_count_out_of_the_command_tag(self, fake_postgres):
        fake_postgres['tag'] = 'UPDATE 5'
        result = _run(
            _update,
            {
                'database_type': 'postgresql',
                'table': 't',
                'data': {'b': 'y'},
                'where': {'a': 1},
            },
        )

        assert result['updated_count'] == 5
        assert _rung(result) is Outcome.OBSERVED
        effect = _effect(result, 'rows_updated')
        assert "'UPDATE 5'" in effect['measured_by']
        assert effect['counts'] == 'rows matched by the WHERE clause'

    def test_mysql_says_its_count_is_changed_rows_not_matched_rows(self, fake_mysql):
        """The caveat rides in the effect, not in the rung.

        An UPDATE that matched five rows and altered none reports 0 on MySQL,
        truthfully. That is a fact about what the integer counts, not about how
        far the effect was followed, so it must not move the rung -- but a
        consumer comparing this integer with sqlite's needs to be told.
        """
        fake_mysql['rowcount'] = 3
        result = _run(
            _update,
            {
                'database_type': 'mysql',
                'table': 't',
                'data': {'b': 'y'},
                'where': {'a': 1},
            },
        )

        assert result['updated_count'] == 3
        assert _rung(result) is Outcome.OBSERVED
        assert 'CHANGED' in _effect(result, 'rows_updated')['counts']

    def test_mysql_minus_one_reports_no_count_and_stays_at_accepted(self, fake_mysql):
        fake_mysql['rowcount'] = -1
        result = _run(
            _update,
            {
                'database_type': 'mysql',
                'table': 't',
                'data': {'b': 'y'},
                'where': {'a': 1},
            },
        )

        assert result['updated_count'] == -1
        assert _rung(result) is Outcome.ACCEPTED
        assert _effect(result, 'statement_accepted')['count_reported'] is False


# ===========================================================================
# db.mysql.query -- the second silent rollback
# ===========================================================================


class TestMysqlQuery:
    def _query(self, **params):
        return _run(_mysql, {'host': '127.0.0.1', 'query': 'SELECT 1', **params})

    def test_rows_off_the_wire_are_observed(self, fake_mysql):
        fake_mysql['rows'] = [{'a': 1}, {'a': 2}]
        fake_mysql['description'] = [('a',)]
        result = self._query()

        assert result['row_count'] == 2
        assert _rung(result) is Outcome.OBSERVED
        assert _effect(result, 'rows_returned')['count'] == 2

    def test_an_empty_answer_is_only_accepted(self, fake_mysql):
        """The zero that a rolled-back INSERT and an empty SELECT both produce.

        This module runs whatever SQL it is handed through one path, so the
        empty result set is what every write it has ever run looks like. A rung
        of OBSERVED on it would say "we saw the world change" about a payload
        that contains no evidence either way.
        """
        fake_mysql['rows'] = []
        result = self._query(query="INSERT INTO t VALUES (1)")

        assert result['row_count'] == 0
        assert _rung(result) is Outcome.ACCEPTED
        assert _effect(result, 'no_rows_returned')['measured_by'] is None

    def test_the_connection_is_committed_before_it_is_closed(self, fake_mysql):
        """The bug the rung uncovered, pinned by call order.

        `aiomysql.connect` defaults to autocommit=False. Before this fix the
        `finally` ran `conn.close()` with no commit, so every INSERT / UPDATE /
        DELETE this module ran executed inside a transaction that the close
        discarded -- a successful payload over a write that never landed. No
        fake can demonstrate a rollback, so what is pinned is the mechanism: a
        commit happens, and it happens before the close.
        """
        self._query(query="INSERT INTO t VALUES (1)")

        calls = fake_mysql['calls']
        assert 'commit' in calls, calls
        assert calls.index('commit') < calls.index('close'), calls

    def test_the_commit_also_runs_after_a_read(self, fake_mysql):
        """A commit after a pure read is a no-op, which is why it can be
        unconditional -- and unconditional is what makes it correct for the
        write path, which is not distinguishable from the read path here."""
        fake_mysql['rows'] = [{'a': 1}]
        self._query()

        assert 'commit' in fake_mysql['calls']


# ===========================================================================
# db.postgresql.query
# ===========================================================================


class TestPostgresQuery:
    def _query(self, **params):
        return _run(
            _postgres,
            {
                'connection_string': 'postgresql://u:p@127.0.0.1:5432/d',
                'query': 'SELECT 1',
                **params,
            },
        )

    def test_records_the_server_sent_are_observed(self, fake_postgres):
        fake_postgres['rows'] = [{'a': 1}, {'a': 2}]
        result = self._query()

        assert result['row_count'] == 2
        assert _rung(result) is Outcome.OBSERVED
        assert 'asyncpg' in _effect(result, 'rows_returned')['measured_by']

    def test_an_empty_answer_is_only_accepted(self, fake_postgres):
        fake_postgres['rows'] = []
        result = self._query(query="INSERT INTO t VALUES (1)")

        assert result['row_count'] == 0
        assert _rung(result) is Outcome.ACCEPTED

    def test_the_two_backends_agree_on_what_an_empty_answer_proves(
        self, fake_postgres, fake_mysql
    ):
        """Different drivers, same evidence, same rung.

        The rung follows the measurement, not the module. Two sibling connectors
        reporting different rungs for the same empty result set would mean the
        field encodes which file you happened to call.
        """
        fake_postgres['rows'] = []
        fake_mysql['rows'] = []

        assert _rung(self._query()) is Outcome.ACCEPTED
        assert _rung(_run(_mysql, {'host': '127.0.0.1', 'query': 'SELECT 1'})) is (
            Outcome.ACCEPTED
        )


# ===========================================================================
# db.mongodb.* -- one module that can observe, one that cannot
# ===========================================================================


class _FakeInsertResult:
    """The pymongo result shape, with the property that matters.

    `inserted_id` / `inserted_ids` are generated CLIENT-side: pymongo stamps an
    `_id` on any document that lacks one before the write goes on the wire and
    hands those same values back. So the fake builds them from the documents it
    was given, exactly as the driver does -- which is the whole reason the count
    derived from them is not evidence.
    """

    def __init__(self, documents, acknowledged=True):
        self.inserted_ids = [f"oid-{i}" for i, _ in enumerate(documents)]
        self.inserted_id = self.inserted_ids[0]
        self.acknowledged = acknowledged


class _FakeCursor:
    def __init__(self, documents):
        self._documents = documents

    def sort(self, spec):
        return self

    def limit(self, n):
        self._documents = self._documents[:n]
        return self

    async def to_list(self, length=None):
        return [dict(d) for d in self._documents]


class _FakeCollection:
    def __init__(self, state):
        self._state = state

    def find(self, filter_query, projection=None):
        return _FakeCursor(self._state['documents'])

    async def insert_one(self, document):
        return _FakeInsertResult([document], self._state['acknowledged'])

    async def insert_many(self, documents):
        return _FakeInsertResult(documents, self._state['acknowledged'])


class _FakeDatabase:
    """`client[db][collection]` is two subscripts, and the fake must be both."""

    def __init__(self, state):
        self._state = state

    def __getitem__(self, name):
        return _FakeCollection(self._state)


@pytest.fixture
def fake_mongo(monkeypatch):
    state = {'documents': [], 'acknowledged': True, 'closed': False}

    class _Client:
        def __init__(self, conn_string, *args, **kwargs):
            self._state = state

        def __getitem__(self, name):
            return _FakeDatabase(state)

        def close(self):
            state['closed'] = True

    motor = types.ModuleType('motor')
    motor_asyncio = types.ModuleType('motor.motor_asyncio')
    motor_asyncio.AsyncIOMotorClient = _Client
    motor.motor_asyncio = motor_asyncio
    monkeypatch.setitem(sys.modules, 'motor', motor)
    monkeypatch.setitem(sys.modules, 'motor.motor_asyncio', motor_asyncio)
    monkeypatch.setenv('MONGODB_URL', 'mongodb://127.0.0.1:27017')
    return state


_MONGO_BASE = {'database': 'app', 'collection': 'users'}


class TestMongoFind:
    def test_documents_decoded_from_the_server_are_observed(self, fake_mongo):
        fake_mongo['documents'] = [{'name': 'a'}, {'name': 'b'}]
        result = _run(_mongo_find, {**_MONGO_BASE})

        assert result['count'] == 2
        assert _rung(result) is Outcome.OBSERVED
        assert _effect(result, 'documents_returned')['count'] == 2

    def test_an_empty_cursor_is_only_accepted(self, fake_mongo):
        """Refusing the tempting reading, and saying which one it is.

        `find` cannot be a write, so an empty cursor looks like a positive
        observation that nothing matches. It is not: a database or collection
        name that does not exist returns an empty cursor rather than an error,
        so a typo in `collection` produces this exact payload.
        """
        fake_mongo['documents'] = []
        result = _run(_mongo_find, {**_MONGO_BASE})

        assert result['count'] == 0
        assert _rung(result) is Outcome.ACCEPTED
        assert 'does not exist' in _effect(result, 'no_documents_returned')['detail']

    def test_the_count_carries_the_limit_that_capped_it(self, fake_mongo):
        """A page size silently reported as a total is its own false green."""
        fake_mongo['documents'] = [{'n': i} for i in range(10)]
        result = _run(_mongo_find, {**_MONGO_BASE, 'limit': 3})

        assert result['count'] == 3
        effect = _effect(result, 'documents_returned')
        assert effect['limit'] == 3
        assert 'not that the collection holds that many' in effect['detail']


class TestMongoInsert:
    def test_an_acknowledged_write_is_accepted_and_no_higher(self, fake_mongo):
        result = _run(_mongo_insert, {**_MONGO_BASE, 'document': {'name': 'a'}})

        assert _rung(result) is Outcome.ACCEPTED
        assert _effect(result, 'write_acknowledged')['measured_by'] == (
            'result.acknowledged from the driver'
        )

    def test_an_unacknowledged_write_falls_to_dispatched(self, fake_mongo):
        """Write concern w=0: the driver did not wait, so nobody confirmed."""
        fake_mongo['acknowledged'] = False
        result = _run(_mongo_insert, {**_MONGO_BASE, 'document': {'name': 'a'}})

        assert _rung(result) is Outcome.DISPATCHED
        assert 'w=0' in _effect(result, 'write_unacknowledged')['detail']

    def test_the_counts_are_identical_across_both_rungs(self, fake_mongo):
        """The reason neither number could carry a rung.

        `inserted_count` and `len(inserted_ids)` are byte-identical whether the
        server acknowledged the write or was never waited on, because both come
        from ids pymongo generated before anything went on the wire. Only
        `acknowledged` moves, so only `acknowledged` can decide the rung.
        """
        documents = [{'name': 'a'}, {'name': 'b'}]

        fake_mongo['acknowledged'] = True
        acknowledged = _run(_mongo_insert, {**_MONGO_BASE, 'documents': documents})
        fake_mongo['acknowledged'] = False
        unacknowledged = _run(_mongo_insert, {**_MONGO_BASE, 'documents': documents})

        assert acknowledged['inserted_count'] == unacknowledged['inserted_count'] == 2
        assert acknowledged['inserted_ids'] == unacknowledged['inserted_ids']
        assert _rung(acknowledged) is Outcome.ACCEPTED
        assert _rung(unacknowledged) is Outcome.DISPATCHED

    def test_the_offered_count_says_the_ids_are_client_generated(self, fake_mongo):
        result = _run(_mongo_insert, {**_MONGO_BASE, 'document': {'name': 'a'}})

        offered = _effect(result, 'documents_offered')
        assert offered['count'] == 1
        assert 'generated client-side' in offered['detail']

    def test_a_driver_that_reports_no_acknowledgement_is_not_given_the_benefit(
        self, fake_mongo
    ):
        """Absent evidence is not evidence, so the missing attribute reads low.

        `getattr(result, 'acknowledged', None) is True` rather than a default of
        True: defaulting the other way would let any result object without the
        field claim ACCEPTED, which is a rung handed out for a driver we could
        not question.
        """
        from core.modules.third_party.database.connectors.mongodb_insert import (
            _insert_outcome,
        )

        class _Bare:
            pass

        assert Outcome(_insert_outcome(_Bare(), 1)['rung']) is Outcome.DISPATCHED


# ===========================================================================
# db.redis.* -- two modules, one file, two rungs
# ===========================================================================


class _FakeRedis:
    def __init__(self, state):
        self._state = state

    async def get(self, key):
        return self._state['value']

    async def set(self, key, value):
        self._state['written'] = (key, value)
        return self._state['reply']

    async def setex(self, key, ttl, value):
        self._state['written'] = (key, value, ttl)
        return self._state['reply']

    async def close(self):
        self._state['closed'] = self._state.get('closed', 0) + 1


@pytest.fixture
def fake_redis(monkeypatch):
    redis_asyncio = pytest.importorskip(
        "redis.asyncio", reason="needs the redis extra"
    )

    state = {'value': None, 'reply': True, 'closed': 0}
    monkeypatch.setattr(
        redis_asyncio, 'Redis', lambda **kwargs: _FakeRedis(state), raising=True
    )
    return state


def _redis_get(params, context=None):
    return asyncio.run(RedisGetModule(params, context or {}).execute())


def _redis_set(params, context=None):
    return asyncio.run(RedisSetModule(params, context or {}).execute())


class TestRedisGet:
    def test_a_value_off_the_wire_is_observed(self, fake_redis):
        fake_redis['value'] = 'cached'
        result = _redis_get({'key': 'k', 'host': 'localhost'})

        assert result['value'] == 'cached'
        assert _rung(result) is Outcome.OBSERVED
        assert _effect(result, 'key_present')['measured_by'].startswith("the server's")

    def test_a_nil_reply_is_only_accepted(self, fake_redis):
        """A miss holds no state, and the group follows one rule about that.

        The tempting reading -- GET names a single key and cannot write, so nil
        must mean the key does not exist -- was written first and withdrawn,
        because it does not survive being applied to the sibling connectors:
        the wrong `db` index or a lagging replica answers nil for a key that
        does exist, exactly as a mistyped collection name gives `db.mongodb.find`
        an empty cursor. OBSERVED requires holding state the peer sent.
        """
        fake_redis['value'] = None
        result = _redis_get({'key': 'k', 'host': 'localhost'})

        assert result['exists'] is False
        assert _rung(result) is Outcome.ACCEPTED
        assert _effect(result, 'key_absent')['measured_by'] is None

    def test_an_empty_string_is_a_value_not_an_absence(self, fake_redis):
        """`exists = value is not None`, so '' is a hit and earns the hit's rung.

        Worth pinning because the obvious-looking `if not value` would make an
        empty cached string indistinguishable from a miss, and the rung would
        follow the bug down.
        """
        fake_redis['value'] = ''
        result = _redis_get({'key': 'k', 'host': 'localhost'})

        assert result['value'] == ''
        assert result['exists'] is True
        assert _rung(result) is Outcome.OBSERVED

    def test_the_connection_is_closed_when_the_get_raises(self, fake_redis, monkeypatch):
        """The close used to sit on the success path only.

        This module is retryable with max_retries=2, so an unreachable Redis
        leaked three connections per step.
        """
        redis_asyncio = pytest.importorskip(
            "redis.asyncio", reason="needs the redis extra"
        )

        closed = {'n': 0}

        class _Exploding(_FakeRedis):
            async def get(self, key):
                raise ConnectionError('no route to host')

            async def close(self):
                closed['n'] += 1

        monkeypatch.setattr(
            redis_asyncio, 'Redis', lambda **kwargs: _Exploding(fake_redis)
        )

        with pytest.raises(RuntimeError):
            _redis_get({'key': 'k', 'host': 'localhost'})

        assert closed['n'] == 1


class TestRedisSet:
    def test_an_ok_reply_is_accepted_and_no_higher(self, fake_redis):
        """A `+OK` is the peer reporting on its own work.

        OBSERVED would need a GET afterwards. This module does not make one, so
        it does not claim one -- and adding a second round trip to every SET is
        a change to what the module costs, not to what it can honestly say.
        """
        fake_redis['reply'] = True
        result = _redis_set({'key': 'k', 'value': 'v', 'host': 'localhost'})

        assert result['success'] is True
        assert _rung(result) is Outcome.ACCEPTED
        assert _effect(result, 'write_acknowledged')['backend'] == 'redis'

    def test_the_ttl_path_lands_on_the_same_rung(self, fake_redis):
        """SETEX has exactly the same evidence as SET: the server's own word."""
        fake_redis['reply'] = True
        result = _redis_set(
            {'key': 'k', 'value': 'v', 'ttl': 60, 'host': 'localhost'}
        )

        assert fake_redis['written'] == ('k', 'v', 60)
        assert _rung(result) is Outcome.ACCEPTED

    def test_a_reply_that_is_not_ok_is_indeterminate(self, fake_redis):
        """Not ACCEPTED: the peer did not acknowledge taking it.

        Not FAILED either -- nobody declared a postcondition, so no predicate
        was broken. `claim_by` records that reading a falsy reply as "not
        stored" is this module's inference, which is the axis `outcome.py`
        splits failed from indeterminate on.
        """
        fake_redis['reply'] = None
        result = _redis_set({'key': 'k', 'value': 'v', 'host': 'localhost'})

        assert result['success'] is False
        assert _rung(result) is Outcome.INDETERMINATE
        assert _envelope(result)['claim_by'] == ClaimBy.INFERRED.value

    def test_the_two_redis_modules_do_not_share_a_rung(self, fake_redis):
        """The point of putting them in one file and giving them two answers.

        A read that came back and a write that was acknowledged are not the same
        kind of fact, and a per-module or per-file constant would have to be
        wrong about one of them.
        """
        fake_redis['value'] = 'cached'
        fake_redis['reply'] = True

        assert _rung(_redis_get({'key': 'k', 'host': 'localhost'})) is Outcome.OBSERVED
        assert _rung(
            _redis_set({'key': 'k', 'value': 'v', 'host': 'localhost'})
        ) is Outcome.ACCEPTED


# ===========================================================================
# One rule, applied across every read in the group
# ===========================================================================


class TestTheGroupObeysOneRule:
    """OBSERVED requires holding state the peer sent. An empty answer does not.

    Four read paths across four drivers, and the temptation to relax the rule
    was different in each: mongo `find` cannot be a write, redis `GET` names a
    single key, and both look like they give an unambiguous negative. Neither
    does -- a collection that does not exist and a `db` index that is not the
    one you meant both answer empty -- and a rule bent per module is how the
    rung stops meaning anything across modules.

    This is the test that fails if somebody re-argues one of them in isolation.
    """

    def test_no_empty_answer_anywhere_in_the_group_claims_observed(
        self, fake_postgres, fake_mysql, fake_mongo, fake_redis
    ):
        fake_postgres['rows'] = []
        fake_mysql['rows'] = []
        fake_mongo['documents'] = []
        fake_redis['value'] = None

        empty_answers = {
            'db.postgresql.query': _run(
                _postgres,
                {
                    'connection_string': 'postgresql://u:p@127.0.0.1:5432/d',
                    'query': 'SELECT 1',
                },
            ),
            'db.mysql.query': _run(_mysql, {'host': '127.0.0.1', 'query': 'SELECT 1'}),
            'db.mongodb.find': _run(_mongo_find, {**_MONGO_BASE}),
            'db.redis.get': _redis_get({'key': 'k', 'host': 'localhost'}),
        }

        assert {
            module_id: _rung(result) for module_id, result in empty_answers.items()
        } == {module_id: Outcome.ACCEPTED for module_id in empty_answers}

    def test_and_every_non_empty_answer_does(
        self, fake_postgres, fake_mysql, fake_mongo, fake_redis
    ):
        """The other half. A rule that only ever says ACCEPTED is not a rule."""
        fake_postgres['rows'] = [{'a': 1}]
        fake_mysql['rows'] = [{'a': 1}]
        fake_mongo['documents'] = [{'a': 1}]
        fake_redis['value'] = 'v'

        answers = [
            _run(
                _postgres,
                {
                    'connection_string': 'postgresql://u:p@127.0.0.1:5432/d',
                    'query': 'SELECT 1',
                },
            ),
            _run(_mysql, {'host': '127.0.0.1', 'query': 'SELECT 1'}),
            _run(_mongo_find, {**_MONGO_BASE}),
            _redis_get({'key': 'k', 'host': 'localhost'}),
        ]

        assert [_rung(result) for result in answers] == [Outcome.OBSERVED] * 4

    def test_no_module_in_the_group_claims_verified(
        self, sqlite_db, fake_postgres, fake_mysql, fake_mongo, fake_redis
    ):
        """None of these evaluates a postcondition, so none may say it did.

        The engine would cap a VERIFIED claim down to OBSERVED and the cap would
        be invisible from inside the module, so the claim has to be checked
        where it is made.
        """
        fake_redis['value'] = 'v'
        fake_mongo['documents'] = [{'a': 1}]

        results = [
            _run(_insert, {**sqlite_db, 'data': {'a': 1, 'b': 'x'}}),
            _run(_update, {**sqlite_db, 'data': {'b': 'y'}, 'where': {'a': 1}}),
            _run(_mongo_find, {**_MONGO_BASE}),
            _run(_mongo_insert, {**_MONGO_BASE, 'document': {'a': 1}}),
            _run(_mysql, {'host': '127.0.0.1', 'query': 'SELECT 1'}),
            _redis_get({'key': 'k', 'host': 'localhost'}),
            _redis_set({'key': 'k', 'value': 'v', 'host': 'localhost'}),
        ]

        for result in results:
            assert _rung(result) is not Outcome.VERIFIED
            assert _envelope(result)['postcondition'] is None


# ===========================================================================
# The envelopes have to survive the trip out of a step
# ===========================================================================


class TestTheEnvelopeSurvives:
    """`to_legacy_dict` returns exactly {ok, data} and discards every sibling.

    An envelope written anywhere but inside `data` is dropped on the way out of
    a step, which is the failure mode `outcome.py` documents for `browser.click`.
    The SQL writers return `ok: True` with the envelope as a sibling key, so
    `wrap_legacy_result` has to sweep it into `data` -- that is worth pinning
    rather than assuming.
    """

    def test_a_flat_ok_result_carries_its_envelope_into_data(self, sqlite_db):
        from core.modules.items import wrap_legacy_result

        result = _run(_insert, {**sqlite_db, 'data': {'a': 1, 'b': 'x'}})
        legacy = wrap_legacy_result(result).to_legacy_dict()

        assert legacy['ok'] is True
        assert read_envelope(legacy['data'])['rung'] == Outcome.OBSERVED.value

    def test_a_result_with_no_ok_key_keeps_its_envelope_at_the_top(self, fake_mongo):
        """The class- and function-style modules that return a bare payload.

        `_apply_outcome_contract` looks in `data` when there is one and at the
        top level otherwise, so a bare dict is the right place for these.
        """
        fake_mongo['documents'] = [{'name': 'a'}]
        result = _run(_mongo_find, {**_MONGO_BASE})

        assert 'ok' not in result
        assert read_envelope(result)['rung'] == Outcome.OBSERVED.value

    def test_the_engine_does_not_cap_any_of_these(self, sqlite_db, fake_redis):
        """`ceiling_for(None)` is OBSERVED, and nothing here claims higher.

        A module that claimed VERIFIED without declaring a postcondition would
        be silently lowered, and the lowering would be invisible in these tests.
        Asserting no claim exceeds the ceiling is what keeps that honest.
        """
        from core.engine.outcome import ceiling_for, outranks

        fake_redis['value'] = 'v'
        results = [
            _run(_insert, {**sqlite_db, 'data': {'a': 1, 'b': 'x'}}),
            _run(_update, {**sqlite_db, 'data': {'b': 'y'}, 'where': {'a': 1}}),
            _redis_get({'key': 'k', 'host': 'localhost'}),
            _redis_set({'key': 'k', 'value': 'v', 'host': 'localhost'}),
        ]

        for result in results:
            assert not outranks(_envelope(result)['rung'], ceiling_for(None))
