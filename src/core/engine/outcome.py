# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""How far a step's effect was actually confirmed.

One ladder, four rungs, monotonic in exactly one thing — how far into reality
the effect was followed:

    dispatched  the instruction left us. Nobody confirmed receipt.
    accepted    the other side acknowledged taking it. Not that it ran.
    observed    we saw the world change. Not that the right thing changed.
    verified    a postcondition was evaluated and held.

and two answers that are not rungs at all, because they cannot be compared with
the four or with each other:

    failed          a postcondition was evaluated and did not hold, or the
                    execution itself raised.
    indeterminate   we cannot say. A timeout, a severed observation channel, or
                    an inference of ours that may simply be wrong.

`verified` is the only rung anything is allowed to render as "done".

Why a second axis. "Claimed an effect and did not observe it" is not one state,
it is two, and what separates them is who made the claim:

    the caller asked for `expected_outcome='new_tab'` and no tab opened
        -> failed. A contract was broken.
    we noticed `target=_blank` ourselves and no tab opened
        -> indeterminate. Our inference may be wrong; the click may be fine.

So `claim_by` travels beside the rung rather than being folded into it. Folding
them together is how the field this replaces ended up with `unverified` — a
value that says neither what happened nor how sure anyone is.

WHAT THIS REPLACES, and what it had to work around

`browser.click` is the only module in 483 that reports an outcome today. It
writes four bare string literals; `step_executor/executor.py` independently
re-declares one of them and compares against it with `!=`. The two files agreed
by coincidence, nothing validated the field, and four of its five values were
inert — `verified`, `inferred`, `dispatched` and `not_requested` all took the
same path as a module that said nothing at all.

Three constraints from the code, each of which shaped this file:

  * The envelope must live INSIDE `data`. `NodeExecutionResult.to_legacy_dict`
    (`core/modules/items.py:281`) returns exactly `{"ok": ..., "data": ...}`;
    any sibling key is discarded on the way out of a step. `browser.click`'s
    envelope survives only because it returns a bare dict with no `ok`, which
    falls to the raw-passthrough branch — a shape almost nothing else shares.

  * The field names must survive `_redact_sensitive_output`
    (`step_executor/executor.py:44`), which blanks any key matching
    `api[_-]?key|secret|password|token|credential|auth|private[_-]?key|bearer|jwt`.
    An envelope field called `auth_verified` would reach every consumer as
    '[REDACTED]'. None of the five names below match it.

  * It is a container, not five loose keys. Scattering `outcome`, `claim_by`,
    `postcondition`, `effects` and `evidence_ref` across `data` would collide
    with module payloads — `effects` is already a key `browser.click` returns.
    The rung inside the container is called `rung` rather than `outcome`, so
    that reading it is `outcome['rung']` and not `outcome['outcome']`.

`TraceStatus.PARTIAL` is deliberately not reused. It is documented as "Some
items failed" (`engine/trace.py:28`) and separately written for "outcome
unconfirmed" (`executor.py:399`), so a consumer seeing `partial` cannot tell a
foreach with three bad rows from a click nobody observed. A richer envelope
that rode on the same value would deepen that, not resolve it.
"""

from enum import Enum
from typing import Any, Dict, List, Optional


class Outcome(str, Enum):
    """How far the effect was followed. Compare with `outranks`, not with `<`."""

    DISPATCHED = "dispatched"
    ACCEPTED = "accepted"
    OBSERVED = "observed"
    VERIFIED = "verified"

    # Off the ladder. Not lower rungs — answers of a different kind.
    FAILED = "failed"
    INDETERMINATE = "indeterminate"


class ClaimBy(str, Enum):
    """Who said the effect was expected. Decides failed vs indeterminate."""

    CALLER = "caller"
    INFERRED = "inferred"
    NONE = "none"


#: The rungs, weakest first. Membership in this tuple is what "on the ladder"
#: means; everything else in `Outcome` is off it and has no position.
LADDER = (
    Outcome.DISPATCHED,
    Outcome.ACCEPTED,
    Outcome.OBSERVED,
    Outcome.VERIFIED,
)

#: The one rung a user-facing surface may render as success. Anything else that
#: renders as a green tick is the defect this whole contract exists to stop.
SUCCESS_RUNG = Outcome.VERIFIED

#: The key the envelope lives under, inside a module result's ``data``.
ENVELOPE_KEY = "outcome"


def is_on_ladder(outcome: Any) -> bool:
    """True for the four ordered rungs, False for failed/indeterminate/junk."""
    try:
        return Outcome(outcome) in LADDER
    except ValueError:
        return False


def rung_index(outcome: Any) -> Optional[int]:
    """Position on the ladder, or None for anything not on it."""
    try:
        return LADDER.index(Outcome(outcome))
    except ValueError:
        return None


def outranks(left: Any, right: Any) -> bool:
    """True when `left` is strictly further up the ladder than `right`.

    False whenever either side is off the ladder, including when they are the
    same off-ladder value. `failed` is not "less than" `observed`; the question
    does not have an answer, and returning one would let a caller sort a column
    that has no order in it.
    """
    left_index, right_index = rung_index(left), rung_index(right)
    if left_index is None or right_index is None:
        return False
    return left_index > right_index


def cap(outcome: Any, ceiling: Any) -> Outcome:
    """The claimed rung, lowered to `ceiling` when it climbs past it.

    Off-ladder answers pass through untouched: a module that failed did fail,
    and no declaration ceiling makes that into an `accepted`.
    """
    if not is_on_ladder(outcome):
        return Outcome(outcome)
    return Outcome(ceiling) if outranks(outcome, ceiling) else Outcome(outcome)


def envelope(
    rung: Any,
    *,
    claim_by: Any = ClaimBy.NONE,
    postcondition: Optional[str] = None,
    effects: Optional[List[Any]] = None,
    evidence_ref: Optional[str] = None,
) -> Dict[str, Any]:
    """One step's answer, in the shape every consumer may rely on.

    `postcondition` is the human-readable predicate that was evaluated, or None
    where none was declared — which is itself the thing the ratchet counts.
    `evidence_ref` points at a run artifact; it never carries the evidence,
    because this dict is copied into a database column and a websocket frame.
    """
    return {
        "rung": Outcome(rung).value,
        "claim_by": ClaimBy(claim_by).value,
        "postcondition": postcondition,
        "effects": list(effects) if effects else [],
        "evidence_ref": evidence_ref,
    }


#: Categories whose modules change something that outlives the step.
#:
#: The starting point was the one live classifier in this repository —
#: ``modules/quality/rules/capability.py:47``, keyed on the part of a module id
#: before the first dot — and the intention was to reuse it rather than invent a
#: second taxonomy that drifts. Measured against the registry, it could not be
#: reused as it stands:
#:
#:   * it lists ``sms``, which is not a category any module is registered under;
#:   * it omits ``http`` (7 modules), ``ssh`` (3), ``docker`` (6), ``k8s`` (5),
#:     ``network`` (4), ``notification`` (6), ``storage`` (3), ``queue`` (3),
#:     ``git`` (3), ``process`` (3), ``port`` (2), ``dns`` (1) and more.
#:
#: So ``http.request`` — the most-used side-effecting module in any automation
#: product — was not side-effecting, and would have received no default rung at
#: all. A contract whose population excludes HTTP is not a contract.
#:
#: The test applied to each addition: does completing this module change
#: something that outlives the step, which we have not observed? Reaching
#: another machine (http, network, dns, ssh), changing host state (docker, k8s,
#: process, port, sandbox), writing durable external state (storage, queue,
#: git), telling a person (notification, communication), creating future work
#: (scheduler), or spending somebody's money on a remote service (ai, llm,
#: vector) all qualify. ``env`` does not — it changes this process and dies with
#: it. ``cache`` is included because a distributed cache is external and the
#: category does not say which kind it is; the conservative reading is the one
#: that asks for a declaration.
#:
#: ``capability.py`` keeps its own list: it answers a different question — should
#: this module have declared a permission — and narrowing or widening a lint
#: warning is not the same decision as deciding what must carry an outcome.
#: ``SIDE_EFFECT_CAPABILITIES`` in ``modules/quality/constants.py`` is imported
#: once and never referenced; it is dead and is not a third opinion.
SIDE_EFFECT_CATEGORIES = frozenset({
    # Reaches another machine
    "http", "network", "dns", "ssh", "api", "browser",
    # Changes host state
    "docker", "k8s", "process", "port", "sandbox",
    # Writes durable state outside the workflow
    "file", "database", "storage", "queue", "git", "cache",
    # Reaches a person
    "email", "notification", "communication",
    # Runs a command, creates future work, or spends money
    "shell", "scheduler", "ai", "llm", "vector",
})


def is_side_effecting(module_id: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
    """Whether this module changes something outside the workflow.

    Measured 2026-08-31 over the registry: 483 modules, 89 categories, 149 of
    them side-effecting by this definition — the category prefix, or a declared
    need for credentials. The specification's figure of 147 does not reproduce
    from any rule in the code; this one is what the code can actually count,
    which is what a ratchet budget has to be.
    """
    category = module_id.split(".")[0] if "." in module_id else ""
    if category in SIDE_EFFECT_CATEGORIES:
        return True
    return bool((metadata or {}).get("requires_credentials"))


def ceiling_for(declared_postcondition: Optional[str]) -> Outcome:
    """The highest rung a module may claim, given what it declared.

    VERIFIED is *defined* as "a postcondition was evaluated and it held". A
    module that declared no postcondition has nothing to have evaluated, so
    claiming it is not an overreach of policy but a category error — there is
    no predicate the claim could be about.

    OBSERVED stays available without a declaration, because observing is not
    asserting: a module that read an HTTP status or a process exit code did
    measure something real, and refusing to let it say so would push honest
    modules down to the same rung as the ones that measured nothing.
    """
    return Outcome.VERIFIED if declared_postcondition else Outcome.OBSERVED


def default_for(module_id: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[Outcome]:
    """What a module that reported nothing is taken to have reached.

    None for a module declaring ``derives``: it is not on the ladder at all.
    The ladder measures how far an effect was followed into the world, and a
    module that computes its output from its inputs has no such distance to
    travel — the return value *is* the whole of what happened. That is the same
    answer `string.uppercase` gets, and for the same reason.

    ``derives`` is checked FIRST, ahead of the category, because the two are not
    the same kind of statement. `is_side_effecting` reads the text before the
    first dot: it is a heuristic over 483 modules, and a good one, but it is
    guessing. ``derives`` is a declaration the module's author wrote about the
    module in front of them. Where they disagree, the specific knowledge wins
    over the general guess — and seven modules are in exactly that
    disagreement, counted against the live registry rather than estimated:
    `file.diff`, `scheduler.interval` and `scheduler.cron_parse` declared it and
    were overruled, and four of the six `ai.*` sub-nodes are configuration
    providers wired to `llm.agent` over a RESOURCE edge that reach nothing.
    All seven were being stamped `dispatched`, which is not a conservative
    reading of what they did — it is a false one. No instruction left us. There
    is nobody who could confirm anything, because nothing was sent.

    FOUR of the six, not all six, and the two exceptions are the reason this is
    a per-module declaration rather than a rule about sub-nodes.
    `ai.memory.redis` connects to Redis and reports its own rung.  `ai.model`
    resolves the host whenever `base_url` is set, measured with an audit hook,
    and returns `ok: False` when the name does not resolve — a result that
    depends on the network is not computed from its inputs. Both keep the
    `dispatched` default. A rule keyed on `NodeType.AI_SUB_NODE` would have
    silenced both.

    NONE, AND NEVER VERIFIED. This function used to return VERIFIED for
    ``derives``, guarded only by asking about side effects first, and that guard
    was doing real work: three side-effecting modules declared ``derives`` and
    an earlier ordering stamped them `verified` with ``postcondition: None`` and
    ``effects: []`` — a green tick with nothing behind it, produced by the
    default whose job is to prevent exactly that. Reordering made the hazard
    unreachable but left it in the building. It is gone now, because it
    contradicted `ceiling_for` outright: VERIFIED is *defined* there as "a
    postcondition was evaluated and it held", so granting it to a module whose
    ``postcondition`` is None is not a policy overreach but a category error —
    there is no predicate the claim could be about. A boolean flag is not a
    postcondition, and the highest rung, the only one that renders as success,
    is not something a default may hand out.

    So the change can only ever lower a claim: VERIFIED became None, and for
    those seven modules DISPATCHED became None. Nothing anywhere gains a rung.

    DISPATCHED for anything side-effecting that declared nothing: the
    instruction left us and nobody confirmed anything, which is the truth about
    a module that says nothing.

    None for everything else — deliberately not a rung. Stamping the other 334
    modules would put an envelope on every string concatenation in the product
    and teach every consumer to ignore the field. What makes an undeclared
    module visible is the ratchet counting it, not the runtime decorating it.
    """
    if (metadata or {}).get("derives"):
        return None
    if is_side_effecting(module_id, metadata):
        return Outcome.DISPATCHED
    return None


#: The postcondition a derived module's stamp carries. Not None: an envelope
#: claiming VERIFIED with no predicate named is unreadable, and `ceiling_for`
#: uses exactly that absence to decide a claim may not stand.
DERIVES_POSTCONDITION = "the return value is the effect; there is nothing else to observe"


def read_envelope(payload: Any) -> Optional[Dict[str, Any]]:
    """The envelope in a module payload, or None when there is not one.

    Accepts only a well-formed one. A dict under the right key whose `rung` is
    not a rung is not an envelope — it is a typo, and reading it as `dispatched`
    would let a misspelling quietly become the safest possible claim.
    """
    if not isinstance(payload, dict):
        return None
    found = payload.get(ENVELOPE_KEY)
    if not isinstance(found, dict):
        return None
    try:
        Outcome(found.get("rung"))
    except ValueError:
        return None
    return found
