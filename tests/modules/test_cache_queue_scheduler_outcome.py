# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the cache, queue and scheduler modules are entitled to claim.

Ten modules, and between them they contain four of the five shapes the outcome
ladder exists to catch. Each shape gets a test that fails if the module goes
back to it:

  a literal dressed as a measurement
      `cache.set` returned `stored: True` -- written in the file, identical
      whether the value landed or not. `queue.size` returned `0` for a queue
      that does not exist, indistinguishable from the `0` an existing empty
      queue returns. Both are the `file.write` `bytes_written` shape.

  a measurement taken before the effect
      `cache.delete`'s `deleted` and `cache.clear`'s `cleared_count` are both
      read BEFORE anything is removed. They answer "what was there", not "what
      went away", and they are unchanged if the removal never runs.

  a number that cannot be attributed
      `queue.enqueue`'s Redis reply is the length of the whole list. Without a
      baseline, on a list other producers write to, it is consistent with any
      history -- so it earns ACCEPTED and the test below pins it there.

  an empty answer read as evidence
      A cache miss and an empty dequeue both read the same whether the data is
      absent or we are looking in the wrong store. That is `database.query`'s
      empty-result-set case, and it is ACCEPTED here for the same reason.

The pure helpers are tested directly wherever a branch needs a race to reach.
That is the separation `file.write._write_outcome` keeps: a rung that can only
be produced by winning a race is a rung nobody can check.
"""

import asyncio
import sys
import time
from contextlib import suppress
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import core.modules.atomic.cache.clear as clear_module
import core.modules.atomic.cache.delete as delete_module
import core.modules.atomic.cache.get as get_module
import core.modules.atomic.cache.set as set_module
import core.modules.atomic.queue.dequeue as dequeue_module
import core.modules.atomic.queue.enqueue as enqueue_module
import core.modules.atomic.queue.size as size_module
import core.modules.atomic.scheduler.delay as delay_module
from core.engine.outcome import ClaimBy, Outcome, ceiling_for, read_envelope
from core.modules.registry import ModuleRegistry


def ensure_modules_loaded():
    from core.modules import atomic  # noqa: F401
    with suppress(Exception):
        from core.modules import third_party  # noqa: F401


ensure_modules_loaded()


async def run(module_id, **params):
    """Execute a module the way the engine does and return its result dict."""
    module = ModuleRegistry.get(module_id)
    return await module(params, {}).execute()


def envelope_of(result):
    """The outcome envelope, read the way `step_executor` reads it."""
    return read_envelope(result["data"])


def rung_of(result):
    return envelope_of(result)["rung"]


def effect_kinds(found):
    return [effect["kind"] for effect in found["effects"]]


def effect_named(found, kind):
    return next(effect for effect in found["effects"] if effect["kind"] == kind)


@pytest.fixture(autouse=True)
def empty_stores():
    """Both in-process stores, empty, before and after every test.

    They are module-level dicts shared by every module in their category, so a
    test that leaves one dirty is a test that changes another test's answer.
    """
    get_module._memory_cache.clear()
    enqueue_module._memory_queues.clear()
    yield
    get_module._memory_cache.clear()
    enqueue_module._memory_queues.clear()


# ===========================================================================
# cache.set -- the literal, and the read-back that replaced it
# ===========================================================================

class TestCacheSetEarnsObservedFromAReadBack:
    @pytest.mark.asyncio
    async def test_a_stored_key_reads_back_and_earns_observed(self):
        result = await run("cache.set", key="k", value="v", backend="memory")
        found = envelope_of(result)

        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert result["data"]["read_back"] is True

    @pytest.mark.asyncio
    async def test_the_read_back_goes_through_the_path_cache_get_uses(self):
        """Not `key in _memory_cache`: the TTL-respecting path a reader uses.

        A read-back that skipped the TTL would report `observed` for a value
        that `cache.get` will never hand back.
        """
        await run("cache.set", key="k", value="v", backend="memory")
        result = await run("cache.set", key="k2", value="v2", backend="memory")

        measurement = effect_named(envelope_of(result), "cache_key_read_back")
        assert "_cache_get" in measurement["measured_by"]
        assert "TTL" in measurement["detail"] or "TTL" in measurement["measured_by"]

    @pytest.mark.asyncio
    async def test_the_stored_flag_is_recorded_as_measuring_nothing(self):
        """`stored: True` is a literal, and the envelope has to say so.

        This is the `file.write` mistake in its original form. If somebody
        later builds a rung on `stored`, this test is what says no.
        """
        result = await run("cache.set", key="k", value="v", backend="memory")

        assert result["data"]["stored"] is True, "the field itself is unchanged"
        literal = effect_named(envelope_of(result), "store_call_returned")
        assert literal["measured_by"] is None
        assert "identical whether the value landed or not" in literal["detail"]

    @pytest.mark.asyncio
    async def test_a_blinded_read_back_falls_to_indeterminate(self, monkeypatch):
        """Take the measurement away and the claim must fall with it."""
        monkeypatch.setattr(set_module, "_cache_get", lambda key: None)

        result = await run("cache.set", key="k", value="v", backend="memory")
        found = envelope_of(result)

        assert found["rung"] == Outcome.INDETERMINATE.value
        assert result["data"]["read_back"] is False
        assert "cache_key_read_back_disagrees" in effect_kinds(found)

    @pytest.mark.asyncio
    async def test_a_racing_writer_is_indeterminate_and_not_failed(self, monkeypatch):
        """Somebody else's value under our key is a race, not a broken promise.

        `outcome.py` splits on who claimed the predicate. Nobody asked for a
        read-back, so a disagreement is this module's inference going wrong.
        """
        monkeypatch.setattr(set_module, "_cache_get", lambda key: "somebody else's")

        found = envelope_of(await run("cache.set", key="k", value="v", backend="memory"))

        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["rung"] != Outcome.FAILED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value

    def test_the_redis_branch_is_accepted_and_stays_accepted(self):
        """A SET reply is the peer reporting on its own work. Nothing was read back."""
        found = set_module._redis_store_outcome(ttl=0, reply=True)

        assert found["rung"] == Outcome.ACCEPTED.value
        acknowledgement = effect_named(found, "redis_set_acknowledged")
        assert "peer reporting on its own work" in acknowledgement["detail"]

    def test_a_redis_set_without_an_ok_is_indeterminate(self):
        found = set_module._redis_store_outcome(ttl=30, reply=None)

        assert found["rung"] == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_expiry_is_never_claimed(self):
        """The TTL is handed to the store and never watched.

        `observed` here means "a reader would hit now", not "this value will
        live exactly ttl seconds".
        """
        result = await run("cache.set", key="k", value="v", ttl=60, backend="memory")
        found = envelope_of(result)

        assert found["postcondition"] is None
        assert "Expiry is not observed" in effect_named(found, "cache_key_read_back")["detail"]


# ===========================================================================
# cache.get -- a hit is the value, a miss is not evidence
# ===========================================================================

class TestCacheGetSplitsOnWhetherAValueCameBack:
    @pytest.mark.asyncio
    async def test_a_hit_is_observed(self):
        await run("cache.set", key="k", value="v", backend="memory")

        result = await run("cache.get", key="k", backend="memory")

        assert result["data"]["hit"] is True
        assert rung_of(result) == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_a_miss_is_accepted_not_observed(self):
        """`hit=False` reads the same for absent data and the wrong store."""
        result = await run("cache.get", key="never-written", backend="memory")

        assert result["data"]["hit"] is False
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert "cache_miss" in effect_kinds(envelope_of(result))

    @pytest.mark.asyncio
    async def test_an_expired_key_is_a_miss_and_drops_to_accepted(self):
        """The rung follows the TTL, because the read path does."""
        await run("cache.set", key="k", value="v", ttl=60, backend="memory")
        get_module._memory_cache["k"]["expires_at"] = time.time() - 1

        result = await run("cache.get", key="k", backend="memory")

        assert result["data"]["hit"] is False
        assert rung_of(result) == Outcome.ACCEPTED.value

    def test_the_miss_effect_names_the_per_process_store_as_a_reason(self):
        """The memory backend is a module-level dict; another worker misses.

        The rung cannot fix that, and the effect has to say the rung cannot
        fix it, or a reader takes `accepted` for "the data is gone".
        """
        found = get_module._lookup_outcome("memory", False)

        assert "per-process" in effect_named(found, "cache_miss")["detail"]


# ===========================================================================
# cache.delete -- the reading taken before the deletion
# ===========================================================================

class TestCacheDeleteNeedsTheSecondReading:
    @pytest.mark.asyncio
    async def test_a_key_that_was_there_and_is_gone_is_observed(self):
        await run("cache.set", key="k", value="v", backend="memory")

        result = await run("cache.delete", key="k", backend="memory")
        found = envelope_of(result)

        assert found["rung"] == Outcome.OBSERVED.value
        assert result["data"]["deleted"] is True
        assert result["data"]["present_after"] is False
        assert "cache_key_removed" in effect_kinds(found)

    @pytest.mark.asyncio
    async def test_deleting_nothing_is_accepted(self):
        """Absent afterwards is what we would read without issuing the delete."""
        result = await run("cache.delete", key="never-written", backend="memory")

        assert rung_of(result) == Outcome.ACCEPTED.value
        assert "cache_key_absent" in effect_kinds(envelope_of(result))

    @pytest.mark.asyncio
    async def test_the_deleted_flag_alone_never_earns_the_rung(self):
        """The trap, pinned directly.

        `deleted` is `key in _memory_cache` read BEFORE the `del`. Hand the
        helper a `True` for it and a key that is still present afterwards --
        the exact reading a delete that did not take produces -- and the rung
        must not be `observed`.
        """
        found = delete_module._memory_delete_outcome(
            present_before=True, present_after=True
        )

        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["rung"] != Outcome.OBSERVED.value

    def test_the_before_reading_is_recorded_as_not_being_evidence(self):
        found = delete_module._memory_delete_outcome(
            present_before=True, present_after=False
        )

        before = effect_named(found, "cache_key_present_before")
        assert "before one could have happened" in before["detail"]

    def test_a_redis_del_that_removed_keys_is_observed(self):
        """A DEL reply counts what the server removed FOR THIS COMMAND."""
        found = delete_module._redis_delete_outcome(1)

        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "redis_keys_removed")["count"] == 1

    def test_a_redis_del_that_removed_nothing_is_accepted(self):
        """Identical to the reply for a key that was never there."""
        found = delete_module._redis_delete_outcome(0)

        assert found["rung"] == Outcome.ACCEPTED.value

    def test_a_reply_that_is_not_a_count_is_accepted(self):
        found = delete_module._redis_delete_outcome(None)

        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "redis_no_key_removed")["count"] is None


# ===========================================================================
# cache.clear -- a count of what matched is not a count of what went away
# ===========================================================================

class TestCacheClearMeasuresTheStoreTwice:
    @pytest.mark.asyncio
    async def test_a_clear_that_removed_entries_is_observed(self):
        for key in ("a:1", "a:2", "b:1"):
            await run("cache.set", key=key, value="v", backend="memory")

        result = await run("cache.clear", pattern="a:*", backend="memory")
        found = envelope_of(result)

        assert found["rung"] == Outcome.OBSERVED.value
        assert result["data"]["cleared_count"] == 2
        assert result["data"]["entries_before"] == 3
        assert result["data"]["entries_after"] == 1

    @pytest.mark.asyncio
    async def test_a_pattern_that_matched_nothing_is_accepted(self):
        await run("cache.set", key="b:1", value="v", backend="memory")

        result = await run("cache.clear", pattern="a:*", backend="memory")

        assert result["data"]["cleared_count"] == 0
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert "cache_unchanged" in effect_kinds(envelope_of(result))

    @pytest.mark.asyncio
    async def test_clearing_an_already_empty_store_is_accepted(self):
        result = await run("cache.clear", pattern="*", backend="memory")

        assert rung_of(result) == Outcome.ACCEPTED.value

    def test_a_delta_that_disagrees_is_indeterminate(self):
        """A concurrent writer, not a broken contract."""
        found = clear_module._memory_clear_outcome(
            pattern="a:*", cleared_count=2, size_before=3, size_after=2
        )

        assert found["rung"] == Outcome.INDETERMINATE.value
        assert effect_named(found, "cache_size_disagrees")["actual_removed"] == 1

    def test_the_matched_count_is_recorded_as_not_being_evidence(self):
        found = clear_module._memory_clear_outcome(
            pattern="*", cleared_count=3, size_before=3, size_after=0
        )

        matched = effect_named(found, "cache_keys_matched")
        assert "unchanged if the removal never runs" in matched["detail"]

    def test_it_never_claims_the_cache_is_now_empty(self):
        """SCAN is not a snapshot, and the memory branch reports a delta."""
        found = clear_module._redis_clear_outcome(pattern="*", cleared_count=5)

        assert found["rung"] == Outcome.OBSERVED.value
        assert "not a claim that the pattern now matches nothing" in (
            effect_named(found, "redis_keys_removed")["detail"]
        )

    def test_a_redis_clear_that_removed_nothing_is_accepted(self):
        found = clear_module._redis_clear_outcome(pattern="a:*", cleared_count=0)

        assert found["rung"] == Outcome.ACCEPTED.value


# ===========================================================================
# queue.enqueue -- the textbook ACCEPTED, and the one case that beats it
# ===========================================================================

class TestQueueEnqueue:
    @pytest.mark.asyncio
    async def test_the_in_process_queue_growing_by_one_is_observed(self):
        result = await run("queue.enqueue", queue_name="q", data="x", backend="memory")
        found = envelope_of(result)

        assert found["rung"] == Outcome.OBSERVED.value
        assert result["data"]["size_before"] == 0
        assert result["data"]["queue_size"] == 1

    @pytest.mark.asyncio
    async def test_the_baseline_is_taken_and_reported(self):
        """Without it, `queue_size` says how long the queue is, not why."""
        await run("queue.enqueue", queue_name="q", data="x", backend="memory")

        result = await run("queue.enqueue", queue_name="q", data="y", backend="memory")

        assert result["data"]["size_before"] == 1
        growth = effect_named(envelope_of(result), "queue_grew_by_one")
        assert growth["size_before"] == 1 and growth["size_after"] == 2

    def test_a_delta_that_is_not_one_is_indeterminate(self):
        """A consumer taking the item straight back out is an ordinary race."""
        found = enqueue_module._memory_enqueue_outcome(
            queue_name="q", size_before=1, size_after=1
        )

        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_a_redis_push_is_accepted_and_must_stay_accepted(self):
        """The pin on the hint: a queued job is the textbook ACCEPTED.

        RPUSH replies with the length of the whole list, not a count of what
        this command did. On a list other producers write to, with no baseline
        taken here, that number is consistent with any history -- so it cannot
        carry OBSERVED. If somebody later reads the length as an observation,
        this is the test that objects.
        """
        found = enqueue_module._redis_enqueue_outcome(queue_name="q", reply=7)

        assert found["rung"] == Outcome.ACCEPTED.value
        assert found["rung"] != Outcome.OBSERVED.value
        assert effect_named(found, "redis_rpush_acknowledged")["list_length_after"] == 7

    def test_a_redis_push_without_a_length_is_indeterminate(self):
        found = enqueue_module._redis_enqueue_outcome(queue_name="q", reply=None)

        assert found["rung"] == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_no_rung_here_says_the_item_was_processed(self):
        result = await run("queue.enqueue", queue_name="q", data="x", backend="memory")

        detail = effect_named(envelope_of(result), "queue_grew_by_one")["detail"]
        assert "nothing about it being consumed" in detail


# ===========================================================================
# queue.dequeue -- an item is evidence, an empty answer is not
# ===========================================================================

class TestQueueDequeue:
    @pytest.mark.asyncio
    async def test_an_item_that_came_back_is_observed(self):
        await run("queue.enqueue", queue_name="q", data="payload", backend="memory")

        result = await run("queue.dequeue", queue_name="q", backend="memory")

        assert result["data"]["data"] == "payload"
        assert rung_of(result) == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_an_empty_non_blocking_read_is_accepted(self):
        result = await run("queue.dequeue", queue_name="q", backend="memory")

        assert result["data"]["empty"] is True
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert effect_named(envelope_of(result), "queue_returned_nothing")["source"] == (
            "get_nowait"
        )

    @pytest.mark.asyncio
    async def test_a_blocking_timeout_is_accepted_and_consumes_nothing(self):
        """Not `indeterminate`, and the reason is measured rather than assumed.

        A timeout is the textbook indeterminate when it leaves us unable to
        say whether the effect happened. `asyncio.wait_for` cancelling a
        pending `Queue.get()` is that shape -- but `Queue.get`'s cancellation
        handler puts the waiter back, so the item stays queued. Nothing was
        consumed, nothing came back: ACCEPTED.
        """
        await run("queue.enqueue", queue_name="q", data="stays", backend="memory")
        await run("queue.dequeue", queue_name="q", backend="memory")  # drain it

        result = await run("queue.dequeue", queue_name="q", backend="memory", timeout=1)

        assert result["data"]["empty"] is True
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert effect_named(envelope_of(result), "queue_returned_nothing")["source"] == (
            "wait_for(get())"
        )

    @pytest.mark.asyncio
    async def test_a_blocking_read_that_got_an_item_is_observed(self):
        await run("queue.enqueue", queue_name="q", data="payload", backend="memory")

        result = await run("queue.dequeue", queue_name="q", backend="memory", timeout=1)

        assert rung_of(result) == Outcome.OBSERVED.value
        assert effect_named(envelope_of(result), "queue_item_removed")["source"] == (
            "wait_for(get())"
        )

    def test_the_empty_effect_names_the_per_process_store(self):
        found = dequeue_module._dequeue_outcome(
            backend="memory", queue_name="q", source="LPOP", got_item=False
        )

        assert "per-process" in effect_named(found, "queue_returned_nothing")["detail"]

    def test_no_rung_here_says_the_item_was_handled(self):
        """A dequeue is destructive and nothing here puts the item back."""
        found = dequeue_module._dequeue_outcome(
            backend="redis", queue_name="q", source="BLPOP", got_item=True
        )

        assert "nothing here puts" in effect_named(found, "queue_item_removed")["detail"]


# ===========================================================================
# queue.size -- two zeros that are not the same zero
# ===========================================================================

class TestQueueSizeTellsTheTwoZerosApart:
    @pytest.mark.asyncio
    async def test_an_existing_empty_queue_reports_a_counted_zero(self):
        await run("queue.enqueue", queue_name="q", data="x", backend="memory")
        await run("queue.dequeue", queue_name="q", backend="memory")

        result = await run("queue.size", queue_name="q", backend="memory")

        assert result["data"]["size"] == 0
        assert result["data"]["queue_exists"] is True
        assert rung_of(result) == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_an_unknown_name_reports_a_literal_zero(self):
        """The same integer, and it must not carry the same rung.

        `size = 0` in that branch is written in the file: `_memory_queues` has
        no entry, and this module does not create one. It is the postgres
        `CREATE TABLE` shape from `database.query` -- a count that did not
        come from a count.
        """
        result = await run("queue.size", queue_name="never-created", backend="memory")

        assert result["data"]["size"] == 0
        assert result["data"]["queue_exists"] is False
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert effect_named(envelope_of(result), "no_queue_to_measure")[
            "count_reported"
        ] is False

    @pytest.mark.asyncio
    async def test_the_two_zeros_differ_only_in_the_envelope(self):
        """Pinned side by side, because `size` alone destroys the distinction."""
        await run("queue.enqueue", queue_name="real", data="x", backend="memory")
        await run("queue.dequeue", queue_name="real", backend="memory")

        counted = await run("queue.size", queue_name="real", backend="memory")
        literal = await run("queue.size", queue_name="ghost", backend="memory")

        assert counted["data"]["size"] == literal["data"]["size"] == 0
        assert rung_of(counted) == Outcome.OBSERVED.value
        assert rung_of(literal) == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_reading_a_size_does_not_create_the_queue(self):
        """If it did, the second read would be a counted zero and the rung a lie."""
        await run("queue.size", queue_name="ghost", backend="memory")

        again = await run("queue.size", queue_name="ghost", backend="memory")

        assert again["data"]["queue_exists"] is False
        assert rung_of(again) == Outcome.ACCEPTED.value

    def test_a_redis_llen_zero_is_a_real_answer(self):
        """Redis draws no line between an empty list and an absent one."""
        found = size_module._size_outcome(
            backend="redis", queue_name="q", counted=True, size=0
        )

        assert found["rung"] == Outcome.OBSERVED.value


# ===========================================================================
# scheduler.delay -- the one module here whose contract is fully provable
# ===========================================================================

class TestSchedulerDelayIsGenuinelyVerified:
    @pytest.mark.asyncio
    async def test_a_completed_delay_is_verified_by_the_caller_s_own_number(self):
        result = await run("scheduler.delay", seconds=0.02)
        found = envelope_of(result)

        assert found["rung"] == Outcome.VERIFIED.value
        assert found["claim_by"] == ClaimBy.CALLER.value

    def test_the_postcondition_is_declared_where_the_engine_reads_it(self):
        """Without the declaration the engine caps this module at `observed`.

        `verified` means a postcondition was evaluated; an undeclared module
        has no predicate the claim could be about, so `ceiling_for` lowers it.
        """
        metadata = ModuleRegistry.get_metadata("scheduler.delay")

        assert metadata["postcondition"] == delay_module.POSTCONDITION
        assert ceiling_for(metadata["postcondition"]) is Outcome.VERIFIED

    @pytest.mark.asyncio
    async def test_the_claim_and_the_declaration_are_the_same_sentence(self):
        """Two copies that drift is how the field this replaces went wrong."""
        found = envelope_of(await run("scheduler.delay", seconds=0))
        metadata = ModuleRegistry.get_metadata("scheduler.delay")

        assert found["postcondition"] == metadata["postcondition"]

    @pytest.mark.asyncio
    async def test_the_elapsed_time_is_measured_and_is_at_least_what_was_asked(self):
        requested = 0.05
        before = time.monotonic()
        result = await run("scheduler.delay", seconds=requested)
        independently_measured = time.monotonic() - before

        measurement = effect_named(envelope_of(result), "monotonic_elapsed")
        assert measurement["elapsed_seconds"] >= requested - delay_module.CLOCK_RESOLUTION
        assert measurement["elapsed_seconds"] <= independently_measured

    def test_a_short_delay_is_failed_because_the_caller_asked_for_it(self):
        """FAILED, not INDETERMINATE: `seconds` is the caller's contract."""
        found = delay_module._delay_outcome(requested=1.0, elapsed=0.4)

        assert found["rung"] == Outcome.FAILED.value
        assert found["claim_by"] == ClaimBy.CALLER.value
        assert effect_named(found, "delay_shorter_than_requested")[
            "short_by_seconds"
        ] == pytest.approx(0.6)

    def test_the_clock_resolution_tolerance_comes_from_the_loop_s_own_source(self):
        """asyncio fires a timer up to one clock resolution early, by design.

        A predicate without that slack marks correct sleeps FAILED, which is
        `file.write`'s newline-translation mistake in a different unit.
        """
        assert time.get_clock_info("monotonic").resolution == delay_module.CLOCK_RESOLUTION

        found = delay_module._delay_outcome(
            requested=1.0, elapsed=1.0 - delay_module.CLOCK_RESOLUTION / 2
        )
        assert found["rung"] == Outcome.VERIFIED.value

    def test_the_predicate_reads_the_unrounded_elapsed_time(self):
        """`delayed_seconds` is rounded to milliseconds; the predicate is not.

        Rounding moves a value by up to half a millisecond, which is enough to
        turn a delay that satisfied the request into a report that says it did
        not. These numbers are chosen so the rounded value fails and the raw
        one holds.
        """
        requested, elapsed = 1.0004, 1.00041

        assert round(elapsed, 3) < requested - delay_module.CLOCK_RESOLUTION
        assert delay_module._delay_outcome(requested=requested, elapsed=elapsed)[
            "rung"
        ] == Outcome.VERIFIED.value

    def test_overshoot_is_not_a_violation(self):
        """The postcondition is a floor. A busy event loop is not a failure."""
        found = delay_module._delay_outcome(requested=1.0, elapsed=9.0)

        assert found["rung"] == Outcome.VERIFIED.value


# ===========================================================================
# scheduler.interval / scheduler.cron_parse -- in the population by prefix only
# ===========================================================================

class TestTheSchedulerForecastersDeclareRatherThanClaim:
    @pytest.mark.parametrize("module_id", ["scheduler.interval", "scheduler.cron_parse"])
    def test_they_declare_derives_and_no_postcondition(self, module_id):
        """`derives` says the return value IS the effect.

        The alternative was leaving them on the undeclared list, where the
        engine stamps `dispatched` -- and `dispatched` is not a cautious answer
        here, it is a wrong one: no instruction left this process.
        """
        metadata = ModuleRegistry.get_metadata(module_id)

        assert metadata["derives"] is True
        assert metadata["postcondition"] is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "module_id, params",
        [
            ("scheduler.interval", {"minutes": 5}),
            ("scheduler.cron_parse", {"expression": "0 9 * * MON-FRI", "count": 3}),
        ],
    )
    async def test_they_build_no_envelope_of_their_own(self, module_id, params):
        """The declaration is the claim. A runtime rung would be a second one."""
        result = await run(module_id, **params)

        assert envelope_of(result) is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "module_id, params",
        [
            ("scheduler.interval", {"hours": 1}),
            ("scheduler.cron_parse", {"expression": "*/15 * * * *", "count": 4}),
        ],
    )
    async def test_they_schedule_nothing_on_the_event_loop(self, module_id, params):
        """The evidence for `derives`: no future work is created.

        The loop's timer heap is the place future work would have to appear.
        It is unchanged across the call, which is what "returns a forecast
        nobody will act on" looks like from outside the module.
        """
        loop = asyncio.get_running_loop()
        scheduled = getattr(loop, "_scheduled", None)
        if scheduled is None:  # pragma: no cover - depends on the loop implementation
            pytest.skip("this event loop does not expose its timer heap")

        before = len(scheduled)
        result = await run(module_id, **params)

        assert len(scheduled) == before
        assert result["data"]["next_runs"], "it did return a forecast"

    @pytest.mark.asyncio
    async def test_the_interval_forecast_is_a_function_of_its_parameters(self):
        """Given a start time, nothing outside the parameters can move it."""
        params = {"minutes": 30, "start_time": "2026-01-15T10:00:00Z"}

        first = await run("scheduler.interval", **params)
        second = await run("scheduler.interval", **params)

        assert first["data"]["next_runs"] == second["data"]["next_runs"]

    @pytest.mark.asyncio
    async def test_the_cron_forecast_is_in_the_future_and_purely_advisory(self):
        result = await run("scheduler.cron_parse", expression="* * * * *", count=2)

        assert len(result["data"]["next_runs"]) == 2
        # Nothing anywhere holds a reference to these times.
        assert result["data"]["is_valid"] is True


# ===========================================================================
# The group as a whole
# ===========================================================================

class TestEveryPayloadPathCarriesAnEnvelope:
    """A consumer that reads `data['outcome']` must never KeyError.

    Every return path of every reporting module in this group, driven through
    the in-process backends. The two `derives` modules are excluded on purpose:
    they declare instead of reporting, and the engine stamps them.
    """

    @pytest.mark.asyncio
    async def test_every_memory_backed_path_reports_a_rung(self):
        paths = [
            ("cache.set", {"key": "k", "value": "v", "backend": "memory"}),
            ("cache.get", {"key": "k", "backend": "memory"}),
            ("cache.get", {"key": "absent", "backend": "memory"}),
            ("cache.delete", {"key": "k", "backend": "memory"}),
            ("cache.delete", {"key": "k", "backend": "memory"}),
            ("cache.clear", {"pattern": "*", "backend": "memory"}),
            ("queue.enqueue", {"queue_name": "q", "data": "x", "backend": "memory"}),
            ("queue.size", {"queue_name": "q", "backend": "memory"}),
            ("queue.size", {"queue_name": "ghost", "backend": "memory"}),
            ("queue.dequeue", {"queue_name": "q", "backend": "memory"}),
            ("queue.dequeue", {"queue_name": "q", "backend": "memory"}),
            ("scheduler.delay", {"seconds": 0}),
        ]

        for module_id, params in paths:
            found = envelope_of(await run(module_id, **params))
            assert found is not None, f"{module_id} {params} reported no outcome"
            assert Outcome(found["rung"])

    @pytest.mark.asyncio
    async def test_nothing_without_a_declaration_claims_verified(self):
        """The ceiling, checked at the source rather than after the engine caps it.

        A module that returns `verified` with no declared postcondition is
        silently lowered to `observed` by `_apply_outcome_contract`. That is a
        safety net, not a licence: a claim the engine has to fix is a claim
        somebody wrote wrong.
        """
        undeclared = [
            ("cache.set", {"key": "k", "value": "v", "backend": "memory"}),
            ("cache.get", {"key": "k", "backend": "memory"}),
            ("cache.delete", {"key": "k", "backend": "memory"}),
            ("cache.clear", {"pattern": "*", "backend": "memory"}),
            ("queue.enqueue", {"queue_name": "q", "data": "x", "backend": "memory"}),
            ("queue.size", {"queue_name": "q", "backend": "memory"}),
            ("queue.dequeue", {"queue_name": "q", "backend": "memory"}),
        ]

        for module_id, params in undeclared:
            assert ModuleRegistry.get_metadata(module_id)["postcondition"] is None
            found = envelope_of(await run(module_id, **params))
            assert found["rung"] != Outcome.VERIFIED.value, module_id

    @pytest.mark.asyncio
    async def test_every_effect_says_what_measured_it_or_that_nothing_did(self):
        """`measured_by` is the field the brief turns on: name the line, or None.

        An effect with neither is a rung nobody can audit.
        """
        results = [
            await run("cache.set", key="k", value="v", backend="memory"),
            await run("cache.get", key="k", backend="memory"),
            await run("cache.get", key="absent", backend="memory"),
            await run("cache.delete", key="k", backend="memory"),
            await run("cache.clear", pattern="*", backend="memory"),
            await run("queue.enqueue", queue_name="q", data="x", backend="memory"),
            await run("queue.size", queue_name="q", backend="memory"),
            await run("queue.size", queue_name="ghost", backend="memory"),
            await run("queue.dequeue", queue_name="q", backend="memory"),
            await run("scheduler.delay", seconds=0),
        ]

        for result in results:
            for effect in envelope_of(result)["effects"]:
                assert "kind" in effect
                assert "measured_by" in effect or "predicate" in effect, effect
