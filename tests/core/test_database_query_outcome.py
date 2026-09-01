# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""How far `database.query` actually follows reality, per path.

The module has nine payload-returning paths and they do not share a rung. A
single per-module constant would have to be wrong about at least one of them,
so what these tests pin is the *discrimination*: that two returns carrying the
identical `row_count: 0` come back with different rungs when one of those zeros
was counted and the other was written into the source as a fallback.

The sqlite tests run against real sqlite3 -- no mock can tell you what
`cursor.rowcount` does for `ALTER TABLE`, and that is the fact the rung turns
on. asyncpg and aiomysql are not installed in this environment (and a real
server is not available), so those two backends are driven through injected
fakes whose only job is to return the command tags and rowcounts the real
drivers return.
"""

import asyncio
import os
import sys
import types

import pytest

from core.engine.outcome import ENVELOPE_KEY, Outcome, read_envelope
from core.modules.atomic.database.query import database_query as _module_class


_query = _module_class.__wrapped_func__


def _run(params):
    """Invoke the module the way the engine does: one dict, under 'params'."""
    return asyncio.run(_query({'params': params}))


def _envelope(result):
    found = read_envelope(result)
    assert found is not None, f"no well-formed envelope in {sorted(result)}"
    return found


def _rung(result):
    return Outcome(_envelope(result)['rung'])


def _effect(result):
    effects = _envelope(result)['effects']
    assert len(effects) == 1, effects
    return effects[0]


# ---------------------------------------------------------------------------
# sqlite -- real engine, real rowcount
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    """A file-backed sqlite db reached through env, not through params.

    Through env deliberately: `_dsn_guard.guard_client_dsn` rejects a
    client-supplied `database` param unless FLYTO_ALLOW_CLIENT_DB_DSN is set, and
    a test that flips that flag would be testing the module with a security
    control disabled. A file rather than ':memory:' because the module opens a
    fresh connection per call and an in-memory db would not survive between them.
    """
    path = tmp_path / "ladder.sqlite3"
    monkeypatch.setenv("SQLITE_DATABASE", str(path))
    base = {'database_type': 'sqlite'}
    _run({**base, 'query': 'CREATE TABLE t (a INT, b TEXT)', 'fetch': 'none'})
    _run({
        **base,
        'query': "INSERT INTO t VALUES (1,'x'),(2,'y'),(3,'z')",
        'fetch': 'none',
    })
    return base


class TestSqliteWrites:
    """`fetch='none'` -- the mode every write goes through."""

    @pytest.mark.parametrize(
        "query,expected_count",
        [
            ("INSERT INTO t VALUES (4,'w')", 1),
            ("INSERT INTO t VALUES (5,'v'),(6,'u')", 2),
            ("UPDATE t SET b='q' WHERE a > 1", 2),
            # The honest zero: sqlite3_changes() really did return 0.
            ("UPDATE t SET b='q' WHERE a > 999", 0),
            ("DELETE FROM t WHERE a = 999", 0),
        ],
    )
    def test_dml_reports_a_counted_change(self, sqlite_db, query, expected_count):
        result = _run({**sqlite_db, 'query': query, 'fetch': 'none'})

        assert result['row_count'] == expected_count
        assert _rung(result) is Outcome.OBSERVED
        effect = _effect(result)
        assert effect['kind'] == 'rows_affected'
        assert effect['count'] == expected_count
        assert 'sqlite3_changes' in effect['measured_by']

    @pytest.mark.parametrize(
        "query",
        [
            "CREATE TABLE t2 (a INT)",
            "ALTER TABLE t ADD COLUMN c INT",
            "CREATE INDEX idx_t_a ON t(a)",
            "PRAGMA user_version = 3",
        ],
    )
    def test_non_dml_reports_no_count_and_stays_at_accepted(self, sqlite_db, query):
        """sqlite answers -1 here, and -1 is not a count of anything.

        The statement was taken and answered without raising -- ACCEPTED, and
        not one rung more. Claiming OBSERVED would attach "we saw the world
        change" to a `row_count` of -1.
        """
        result = _run({**sqlite_db, 'query': query, 'fetch': 'none'})

        assert result['row_count'] == -1
        assert _rung(result) is Outcome.ACCEPTED
        effect = _effect(result)
        assert effect['kind'] == 'statement_accepted'
        assert effect['count_reported'] is False

    def test_the_ddl_is_real_even_though_the_rung_is_only_accepted(self, sqlite_db):
        """ACCEPTED is a statement about our evidence, not about the database.

        The table really is created. What the module cannot say is that it
        watched that happen, and the rung reports the evidence rather than the
        optimistic guess.

        Showing the table is real takes a read-back that RETURNS SOMETHING.
        `SELECT * FROM t3` on the empty new table comes back at ACCEPTED, not
        OBSERVED, and that is the correction: `row_count == 0` would read
        exactly the same if the CREATE had been discarded, so it is not evidence
        of the CREATE. It is only the row inserted and read back -- a value that
        could not exist unless the table did -- that demonstrates the DDL landed.
        """
        created = _run({**sqlite_db, 'query': 'CREATE TABLE t3 (a INT)', 'fetch': 'none'})
        assert _rung(created) is Outcome.ACCEPTED

        empty_readback = _run({**sqlite_db, 'query': 'SELECT * FROM t3', 'fetch': 'all'})
        assert empty_readback['row_count'] == 0
        assert _rung(empty_readback) is Outcome.ACCEPTED

        _run({**sqlite_db, 'query': 'INSERT INTO t3 VALUES (11)', 'fetch': 'none'})
        readback = _run({**sqlite_db, 'query': 'SELECT * FROM t3', 'fetch': 'all'})
        assert readback['rows'] == [{'a': 11}]
        assert readback['row_count'] == 1
        assert _rung(readback) is Outcome.OBSERVED


class TestSqliteReads:
    def test_fetch_all_counts_rows_the_engine_returned(self, sqlite_db):
        result = _run({**sqlite_db, 'query': 'SELECT * FROM t', 'fetch': 'all'})

        assert result['row_count'] == 3
        assert _rung(result) is Outcome.OBSERVED
        effect = _effect(result)
        assert effect['kind'] == 'rows_returned'
        assert effect == {
            'kind': 'rows_returned',
            'backend': 'sqlite',
            'fetch': 'all',
            'count': 3,
            'measured_by': 'len() over rows the driver returned from the server',
        }

    def test_a_select_matching_nothing_is_not_an_observation(self, sqlite_db):
        """This test used to claim the opposite, and the claim was unearned.

        A returned row is an observation of that row. NO returned rows is an
        observation of nothing: `len(rows) == 0` reads identically whether the
        statement matched nothing, changed five rows and returned no result set,
        or was discarded entirely. A value that would be unchanged if the effect
        had not happened is not evidence of the effect, so an empty read is
        ACCEPTED -- the server answered, and the answer says nothing about the
        data.

        This was found by running a real INSERT through fetch='all' -- the
        DEFAULT fetch mode -- and watching the row get silently rolled back,
        because `conn.commit()` only existed in the fetch='none' branch. The
        module was losing the data AND reporting that it had observed it. Both
        halves are fixed; see
        `test_a_write_run_with_fetch_all_is_committed_not_rolled_back`.
        """
        result = _run({**sqlite_db, 'query': 'SELECT * FROM t WHERE a > 999', 'fetch': 'all'})

        assert result['row_count'] == 0
        assert _rung(result) is Outcome.ACCEPTED
        effect = _effect(result)
        assert effect['kind'] == 'no_rows_returned'
        assert effect['measured_by'] is None

    def test_fetch_one_answers_a_narrower_question_than_it_looks(self, sqlite_db):
        """`row_count` under fetch='one' is capped at 1 by construction.

        Three rows match; the module reports 1. That is not a defect, but it
        means the number answers "did at least one row come back", so the effect
        carries `fetch` and a consumer can tell which question was asked.
        """
        result = _run({**sqlite_db, 'query': 'SELECT * FROM t', 'fetch': 'one'})

        assert result['row_count'] == 1
        assert _rung(result) is Outcome.OBSERVED
        assert _effect(result)['fetch'] == 'one'

    def test_a_write_run_with_fetch_all_reports_returned_not_affected(self, sqlite_db):
        """The trap this effect name exists to defuse.

        An UPDATE run with fetch='all' yields `row_count: 0` because no result
        set came back -- not because it matched nothing; it matched two rows.
        The same statement through fetch='none' reports 2. So the 0 is a fact
        about the RESULT SET and never about the data, which is why the two
        paths must not be allowed to produce the same-looking answer.

        This is the case that proves the rung had to move. Zero returned rows
        used to be reported OBSERVED, which put "we saw the world change" on the
        one number in this module guaranteed not to have seen it: a write that
        changed two rows and a SELECT that matched none both land here. ACCEPTED
        with `kind: no_rows_returned` says only what is true -- the server took
        the statement and answered -- and the fetch='none' comparison below is
        what an actual count of the change looks like.
        """
        result = _run({**sqlite_db, 'query': "UPDATE t SET b='r' WHERE a > 1", 'fetch': 'all'})

        assert result['row_count'] == 0
        assert _rung(result) is Outcome.ACCEPTED
        effect = _effect(result)
        assert effect['kind'] == 'no_rows_returned'
        assert effect['fetch'] == 'all'
        assert effect['measured_by'] is None

        affected = _run({**sqlite_db, 'query': "UPDATE t SET b='s' WHERE a > 1", 'fetch': 'none'})
        assert affected['row_count'] == 2
        assert _rung(affected) is Outcome.OBSERVED
        assert _effect(affected)['kind'] == 'rows_affected'

    def test_a_write_run_with_fetch_all_is_committed_not_rolled_back(self, sqlite_db):
        """The data loss that asking "what is the rung measuring?" uncovered.

        `conn.commit()` used to exist only in the fetch='none' branch, and
        `fetch` defaults to 'all'. An INSERT / UPDATE / DELETE run through the
        default mode therefore opened sqlite's implicit DML transaction,
        returned `ok: True` with a rung on it, and was rolled back by the
        `conn.close()` in the `finally`. Measured on a real file-backed db:
        `INSERT INTO t VALUES (42)` with fetch='all' reported success and left
        the table empty.

        The read-back must go through a SEPARATE `_run`, because the module
        opens a fresh connection per call -- an uncommitted write is visible on
        the connection that made it and nowhere else, so reading it back on a
        new connection is the only thing that distinguishes committed from
        merely written. Remove the commit from the `finally` and this fails.
        """
        written = _run({
            **sqlite_db,
            'query': "INSERT INTO t VALUES (42,'committed')",
            'fetch': 'all',
        })
        assert written['ok'] is True

        readback = _run({
            **sqlite_db,
            'query': 'SELECT a, b FROM t WHERE a = 42',
            'fetch': 'all',
        })

        assert readback['rows'] == [{'a': 42, 'b': 'committed'}]
        assert readback['row_count'] == 1
        assert _rung(readback) is Outcome.OBSERVED


# ---------------------------------------------------------------------------
# postgresql -- fake asyncpg returning real command tags
# ---------------------------------------------------------------------------


class _FakePgConnection:
    def __init__(self, tag, rows):
        self._tag = tag
        self._rows = rows
        self.closed = False

    async def execute(self, query, *args):
        return self._tag

    async def fetchrow(self, query, *args):
        return self._rows[0] if self._rows else None

    async def fetch(self, query, *args):
        return list(self._rows)

    async def close(self):
        self.closed = True


@pytest.fixture
def fake_postgres(monkeypatch):
    """Inject an `asyncpg` whose command tags are the ones a server sends."""
    state = {'tag': 'SELECT 0', 'rows': []}
    connections = []

    async def connect(dsn, *args, **kwargs):
        conn = _FakePgConnection(state['tag'], state['rows'])
        connections.append(conn)
        return conn

    fake = types.ModuleType('asyncpg')
    fake.connect = connect
    monkeypatch.setitem(sys.modules, 'asyncpg', fake)
    # Reached through env, so `guard_client_dsn` sees no client-supplied target.
    monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@db.example.invalid:5432/d')
    state['connections'] = connections
    return state


def _pg(fake_postgres, *, tag=None, rows=None, fetch='none', query='SELECT 1'):
    if tag is not None:
        fake_postgres['tag'] = tag
    if rows is not None:
        fake_postgres['rows'] = rows
    return _run({'database_type': 'postgresql', 'query': query, 'fetch': fetch})


class TestPostgresWrites:
    @pytest.mark.parametrize(
        "tag,expected_count",
        [
            ('INSERT 0 3', 3),
            ('INSERT 0 1', 1),
            ('UPDATE 5', 5),
            ('DELETE 2', 2),
            # A counted zero: the server said zero rows matched.
            ('UPDATE 0', 0),
            ('DELETE 0', 0),
        ],
    )
    def test_a_dml_tag_carries_a_count_off_the_wire(self, fake_postgres, tag, expected_count):
        result = _pg(fake_postgres, tag=tag)

        assert result['row_count'] == expected_count
        assert _rung(result) is Outcome.OBSERVED
        effect = _effect(result)
        assert effect['kind'] == 'rows_affected'
        assert effect['count'] == expected_count
        assert 'command tag' in effect['measured_by']

    @pytest.mark.parametrize(
        "tag",
        [
            'CREATE TABLE',
            'ALTER TABLE',
            'DROP TABLE',
            'TRUNCATE TABLE',
            'CREATE INDEX',
            # MERGE really does report a count -- 'MERGE 4' -- and the substring
            # test throws it away. The rung must not pretend otherwise.
            'MERGE 4',
        ],
    )
    def test_a_tag_the_parser_does_not_match_stays_at_accepted(self, fake_postgres, tag):
        """`row_count` here is the literal 0 in query.py, not a measurement."""
        result = _pg(fake_postgres, tag=tag)

        assert result['row_count'] == 0
        assert _rung(result) is Outcome.ACCEPTED
        effect = _effect(result)
        assert effect['kind'] == 'statement_accepted'
        assert effect['count_reported'] is False
        assert tag in effect['detail']

    def test_two_identical_zeros_that_are_not_the_same_fact(self, fake_postgres):
        """The whole point, in one assertion pair.

        `DELETE 0` and `CREATE TABLE` both leave `row_count == 0`. One is the
        server saying no rows matched; the other is this module failing to parse
        a count and writing a zero itself. Downstream they were indistinguishable
        before the envelope, and a per-module rung constant would make them
        indistinguishable again.
        """
        matched_nothing = _pg(fake_postgres, tag='DELETE 0')
        no_count_reported = _pg(fake_postgres, tag='CREATE TABLE')

        assert matched_nothing['row_count'] == no_count_reported['row_count'] == 0
        assert _rung(matched_nothing) is Outcome.OBSERVED
        assert _rung(no_count_reported) is Outcome.ACCEPTED

    def test_the_tag_is_not_matched_against_the_sql_text(self, fake_postgres):
        """A query that mentions INSERT but whose tag does not is not counted.

        `'INSERT' in result` reads the command tag, never the query, so
        `CREATE TABLE ... AS SELECT ... FROM insert_log` cannot fake a count.
        """
        result = _pg(
            fake_postgres,
            tag='CREATE TABLE AS',
            query='CREATE TABLE snapshot AS SELECT * FROM insert_log',
        )

        assert _rung(result) is Outcome.ACCEPTED


class TestPostgresReads:
    def test_fetch_all_counts_records_the_server_sent(self, fake_postgres):
        result = _pg(fake_postgres, rows=[{'a': 1}, {'a': 2}], fetch='all')

        assert result['row_count'] == 2
        assert result['columns'] == ['a']
        assert _rung(result) is Outcome.OBSERVED
        assert _effect(result) == {
            'kind': 'rows_returned',
            'backend': 'postgresql',
            'fetch': 'all',
            'count': 2,
            'measured_by': 'len() over rows the driver returned from the server',
        }

    def test_fetch_one_observes_a_row_but_only_accepts_an_empty_answer(
        self, fake_postgres
    ):
        """The two answers fetch='one' can give are not the same kind of fact.

        A row that came back is a row the server materialised and sent: OBSERVED,
        and `row_count` is capped at 1 by `rows = [row] if row else []`, so it
        means "at least one came back". No row is `len([]) == 0`, which is the
        same integer a discarded statement would leave behind and therefore
        evidence of nothing: ACCEPTED. This test asserted OBSERVED for both,
        which erased exactly the distinction the rest of this file exists to
        make.
        """
        empty = _pg(fake_postgres, rows=[], fetch='one')
        assert empty['row_count'] == 0
        assert _rung(empty) is Outcome.ACCEPTED
        assert _effect(empty)['kind'] == 'no_rows_returned'

        found = _pg(fake_postgres, rows=[{'a': 1}, {'a': 2}], fetch='one')
        assert found['row_count'] == 1
        assert _rung(found) is Outcome.OBSERVED
        assert _effect(found)['kind'] == 'rows_returned'


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
        return self.rowcount

    async def fetchone(self):
        rows = self._state['rows']
        return rows[0] if rows else None

    async def fetchall(self):
        return list(self._state['rows'])


class _FakeMySQLConnection:
    def __init__(self, state):
        self._state = state
        self.committed = False

    def cursor(self, cursor_class=None):
        return _FakeMySQLCursor(self._state)

    async def commit(self):
        self.committed = True

    def close(self):
        pass

    async def ensure_closed(self):
        pass


@pytest.fixture
def fake_mysql(monkeypatch):
    state = {'rowcount': -1, 'rows': [], 'description': None}

    async def connect(**kwargs):
        return _FakeMySQLConnection(state)

    fake = types.ModuleType('aiomysql')
    fake.connect = connect
    fake.DictCursor = object
    monkeypatch.setitem(sys.modules, 'aiomysql', fake)
    monkeypatch.setenv('MYSQL_HOST', 'db.example.invalid')
    monkeypatch.setenv('MYSQL_DATABASE', 'd')
    monkeypatch.setenv('MYSQL_USER', 'u')
    monkeypatch.setenv('MYSQL_PASSWORD', 'p')
    return state


#: `None` is itself a rowcount worth testing, so "not supplied" cannot be None.
_UNSET = object()


def _my(fake_mysql, *, rowcount=_UNSET, rows=None, description=None, fetch='none'):
    if rowcount is not _UNSET:
        fake_mysql['rowcount'] = rowcount
    if rows is not None:
        fake_mysql['rows'] = rows
    if description is not None:
        fake_mysql['description'] = description
    return _run({'database_type': 'mysql', 'query': 'SELECT 1', 'fetch': fetch})


class TestMysqlWrites:
    @pytest.mark.parametrize("rowcount", [0, 1, 5, 4096])
    def test_a_non_negative_rowcount_is_a_number_the_server_sent(self, fake_mysql, rowcount):
        """MySQL's OK packet carries affected_rows for every statement.

        Unlike postgres, a 0 here is not a fallback -- which is exactly why the
        rung is decided from the value and not from the backend name.
        """
        result = _my(fake_mysql, rowcount=rowcount)

        assert result['row_count'] == rowcount
        assert _rung(result) is Outcome.OBSERVED
        effect = _effect(result)
        assert effect['kind'] == 'rows_affected'
        assert effect['count'] == rowcount
        assert 'OK packet' in effect['measured_by']

    @pytest.mark.parametrize("rowcount", [-1, None])
    def test_an_undeterminable_rowcount_stays_at_accepted(self, fake_mysql, rowcount):
        """PEP 249 reserves -1 for "cannot be determined"; None is the same answer."""
        result = _my(fake_mysql, rowcount=rowcount)

        assert result['row_count'] == rowcount
        assert _rung(result) is Outcome.ACCEPTED
        assert _effect(result)['count_reported'] is False


class TestMysqlReads:
    def test_fetch_all_counts_rows_the_cursor_returned(self, fake_mysql):
        result = _my(
            fake_mysql,
            rows=[{'a': 1}, {'a': 2}, {'a': 3}],
            description=[('a',)],
            fetch='all',
        )

        assert result['row_count'] == 3
        assert result['columns'] == ['a']
        assert _rung(result) is Outcome.OBSERVED
        assert _effect(result)['kind'] == 'rows_returned'
        assert _effect(result)['backend'] == 'mysql'

    def test_fetch_one_observes_zero_or_one(self, fake_mysql):
        result = _my(fake_mysql, rows=[{'a': 1}, {'a': 2}], fetch='one')

        assert result['row_count'] == 1
        assert _rung(result) is Outcome.OBSERVED


# ---------------------------------------------------------------------------
# The backend that is advertised and does not exist
# ---------------------------------------------------------------------------


class TestMssqlIsAdvertisedButUnimplemented:
    def test_the_supported_list_names_a_backend_the_dispatch_rejects(self):
        from core.modules.atomic.database.query import SUPPORTED_DATABASES

        assert 'mssql' in SUPPORTED_DATABASES

        with pytest.raises(ValueError, match='Unsupported database type: mssql'):
            _run({'database_type': 'mssql', 'query': 'SELECT 1'})

    def test_no_envelope_is_invented_for_a_backend_that_never_ran(self):
        """A raise is a step failure; it is not a rung, and not an envelope.

        There is no fourth backend's worth of return sites to stamp -- there are
        nine, across three backends. The list at module scope is dead code that
        implies a fourth.
        """
        for db_type in ('mssql', 'oracle', 'db2'):
            with pytest.raises(ValueError, match='Unsupported database type'):
                _run({'database_type': db_type, 'query': 'SELECT 1'})

    def test_the_ui_selector_does_not_offer_it_either(self):
        from core.modules.schema import presets

        options = presets.DB_TYPE()['database_type']['options']
        assert [o['value'] for o in options] == ['postgresql', 'mysql', 'sqlite']

    def test_the_sibling_module_lists_only_what_exists(self):
        """`database.insert`'s copy of the same constant omits mssql."""
        from core.modules.atomic.database.insert import (
            SUPPORTED_DATABASES as insert_supported,
        )

        assert 'mssql' not in insert_supported


# ---------------------------------------------------------------------------
# The ceiling, and where the envelope has to sit to survive
# ---------------------------------------------------------------------------


class TestTheCeiling:
    def test_no_path_claims_verified(self, sqlite_db):
        """VERIFIED requires a postcondition that was evaluated and held.

        Nothing here evaluates a predicate -- no read-back, no assertion -- so
        every path must sit at OBSERVED or below regardless of what the
        declaration plumbing eventually allows.
        """
        results = [
            _run({**sqlite_db, 'query': 'SELECT * FROM t', 'fetch': 'all'}),
            _run({**sqlite_db, 'query': 'SELECT * FROM t', 'fetch': 'one'}),
            _run({**sqlite_db, 'query': "INSERT INTO t VALUES (9,'i')", 'fetch': 'none'}),
            _run({**sqlite_db, 'query': 'CREATE TABLE t9 (a INT)', 'fetch': 'none'}),
        ]

        for result in results:
            assert _rung(result) is not Outcome.VERIFIED

    def test_nothing_declares_a_postcondition(self, sqlite_db):
        """`postcondition: None` is the thing a ratchet counts, so it must be None."""
        result = _run({**sqlite_db, 'query': 'SELECT * FROM t', 'fetch': 'all'})

        assert _envelope(result)['postcondition'] is None

    def test_the_declaration_kwarg_exists_and_this_module_still_declines_it(self):
        """The plumbing landed, and the ceiling did not move.

        This test used to pin the ABSENCE of `postcondition` on
        `register_module`, as the reason `database.query` could not reach
        VERIFIED. That reason has expired: the kwarg exists, it is explicit
        rather than swallowed by **kwargs, and it reaches the metadata dict.

        The half worth keeping is the ceiling, and it is unchanged -- because
        being ABLE to declare a postcondition is not declaring one. This module
        declares none, so `ceiling_for(None)` still caps it at OBSERVED, which
        is the honest cap: none of the nine paths evaluates a predicate, so a
        declaration here would be a claim about a check that does not run. If a
        future edit adds `postcondition=` to this module's `register_module`
        call, this test fails and the read-back has to be written first.
        """
        import inspect

        from core.engine.outcome import ceiling_for
        from core.modules.registry import ModuleRegistry
        from core.modules.registry.decorators import register_module

        parameters = inspect.signature(register_module).parameters
        assert 'postcondition' in parameters
        assert parameters['postcondition'].default is None
        assert 'derives' in parameters
        assert parameters['derives'].default is False
        assert not any(p.kind is p.VAR_KEYWORD for p in parameters.values())

        metadata = ModuleRegistry.get_metadata('database.query')
        assert metadata['postcondition'] is None
        assert metadata['derives'] is False
        assert ceiling_for(metadata['postcondition']) is Outcome.OBSERVED

    def test_the_ceiling_helper_agrees(self):
        from core.engine.outcome import ceiling_for

        assert ceiling_for(None) is Outcome.OBSERVED

    def test_the_envelope_is_declared_in_the_output_schema(self):
        """An undeclared output is invisible to the catalog and the UI."""
        from core.modules.registry import ModuleRegistry

        schema = ModuleRegistry.get_metadata('database.query')['output_schema']
        assert schema[ENVELOPE_KEY]['type'] == 'object'
        assert set(schema) == {'rows', 'row_count', 'columns', ENVELOPE_KEY}


class TestTheEnvelopeSurvivesTheWayOut:
    def test_a_top_level_key_lands_under_data_for_this_module_shape(self, sqlite_db):
        """The placement rule needs care for a flat `{'ok': ..., ...}` return.

        The contract says the envelope must live inside `data`, because
        `to_legacy_dict` returns exactly {"ok", "data"} and drops data's
        siblings. This module returns no `data` key at all, so
        `wrap_legacy_result` (items.py:348-350) promotes every non-meta
        top-level key into the item's json -- and a top-level 'outcome' arrives
        as `data['outcome']`. Pinned because the reasoning is not obvious and a
        future refactor that adds a `data` key would silently drop the envelope.
        """
        from core.modules.items import wrap_legacy_result

        result = _run({**sqlite_db, 'query': 'SELECT * FROM t', 'fetch': 'all'})
        legacy = wrap_legacy_result(result).to_legacy_dict()

        assert ENVELOPE_KEY in legacy['data']
        assert read_envelope(legacy['data']) is not None

    def test_the_step_executor_reads_the_weakest_rung(self, sqlite_db):
        from core.engine.step_executor.executor import step_outcome
        from core.modules.items import wrap_legacy_result

        ddl = wrap_legacy_result(
            _run({**sqlite_db, 'query': 'CREATE TABLE t8 (a INT)', 'fetch': 'none'})
        ).to_legacy_dict()

        assert step_outcome(ddl)[0] is Outcome.ACCEPTED

    def test_an_accepted_step_is_not_degraded_to_a_failure(self, sqlite_db):
        """ACCEPTED is on the ladder, so it must not turn the step amber.

        Being honest about a DDL write is not the same as reporting a problem,
        and a contract that made every schema migration look broken would be
        switched off within a week.
        """
        from core.engine.step_executor.executor import _unconfirmed_outcome
        from core.modules.items import wrap_legacy_result

        ddl = wrap_legacy_result(
            _run({**sqlite_db, 'query': 'CREATE TABLE t7 (a INT)', 'fetch': 'none'})
        ).to_legacy_dict()

        assert _unconfirmed_outcome(ddl) is None


class TestThePayloadIsUnchanged:
    """The envelope is additive. No existing field moved or changed value."""

    def test_the_original_keys_still_carry_the_original_values(self, sqlite_db):
        result = _run({**sqlite_db, 'query': 'SELECT * FROM t ORDER BY a', 'fetch': 'all'})

        assert set(result) == {'ok', 'rows', 'row_count', 'columns', 'outcome'}
        assert result['ok'] is True
        assert result['rows'] == [
            {'a': 1, 'b': 'x'}, {'a': 2, 'b': 'y'}, {'a': 3, 'b': 'z'}
        ]
        assert result['columns'] == ['a', 'b']
        assert result['row_count'] == 3

    def test_the_postgres_count_expression_was_not_altered(self, fake_postgres):
        """Hoisting the substring test into `counted` must not move a number."""
        for tag, expected in [
            ('INSERT 0 3', 3), ('UPDATE 5', 5), ('DELETE 2', 2),
            ('CREATE TABLE', 0), ('SELECT 7', 0), ('BEGIN', 0),
        ]:
            assert _pg(fake_postgres, tag=tag)['row_count'] == expected
