# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Shared page-state waits for browser modules.

Every helper here ends on an observed page state -- a DOM mutation, a
navigation, a locator reaching a state -- and uses its time budget only as an
upper bound. None of them sleeps for a fixed interval: a page that is already
settled costs one round trip, not a guessed pause.
"""
import asyncio
from typing import Awaitable, Mapping, Optional

# Installed right before an action. It counts mutations from that moment so the
# matching ``settle_dom`` can tell "the action changed nothing" (return at once)
# from "the action is still rendering" (wait for a quiet window). The record
# lives on ``window``, so a navigation discards it and ``settle_dom`` learns that
# the document itself was replaced.
#
# Work the action starts but has not finished is state too: a short timer (up
# to 1 s) or a fetch/XHR issued while the watch is tracking. An onclick that
# navigates from ``setTimeout`` or after a fetch mutates nothing at first, so
# without this the click would be reported as changing nothing. Tracking stops
# when ``settle_dom`` starts; a timer chain or poller the page keeps running
# afterwards is not the action's work. The page's own functions are restored
# when the watch is stopped.
_INSTALL_DOM_WATCH_JS = r"""() => {
  const previous = window.__flytoSettle;
  if (previous && previous.stop) previous.stop();
  const root = document.documentElement || document;
  const nativeSetTimeout = window.setTimeout;
  const nativeClearTimeout = window.clearTimeout;
  const nativeFetch = window.fetch;
  const xhrProto = window.XMLHttpRequest && window.XMLHttpRequest.prototype;
  const nativeSend = xhrProto && xhrProto.send;
  const timers = new Set();
  const watch = {
    count: 0, last: 0, activity: 0, pending: 0, tracking: true,
    onMutation: null, onSettle: null,
    setTimeout: (fn, ms) => nativeSetTimeout.call(window, fn, ms),
    clearTimeout: (id) => nativeClearTimeout.call(window, id),
  };
  watch.observer = new MutationObserver((records) => {
    watch.count += records.length;
    watch.last = performance.now();
    if (watch.onMutation) watch.onMutation();
  });
  watch.observer.observe(root, {
    subtree: true, childList: true, attributes: true, characterData: true,
  });
  // A finished piece of tracked work. Its mutations are still queued as
  // observer records at this point, so they are absorbed before anyone asks
  // whether the action changed anything.
  const finished = (wasActivity) => {
    watch.pending = Math.max(0, watch.pending - 1);
    const records = watch.observer.takeRecords();
    if (records.length) { watch.count += records.length; watch.last = performance.now(); }
    if (wasActivity) watch.activity = performance.now();
    if (watch.onSettle) watch.onSettle();
  };
  // Response handlers run as microtasks after the request settles; a
  // macrotask later they have run, including a router push they make.
  const afterHandlers = () => nativeSetTimeout.call(window, () => finished(true), 0);
  const trackedSetTimeout = function (handler, delay, ...args) {
    if (!watch.tracking || typeof handler !== 'function' || (Number(delay) || 0) > 1000) {
      return nativeSetTimeout.call(window, handler, delay, ...args);
    }
    watch.pending += 1;
    let id = null;
    id = nativeSetTimeout.call(window, function (...fired) {
      if (!timers.delete(id)) return undefined;
      try { return handler.apply(this, fired); } finally { finished(true); }
    }, delay, ...args);
    timers.add(id);
    return id;
  };
  const trackedClearTimeout = function (id) {
    if (timers.delete(id)) finished(false);
    return nativeClearTimeout.call(window, id);
  };
  const trackedFetch = nativeFetch && function (...args) {
    const request = nativeFetch.apply(window, args);
    if (watch.tracking) {
      watch.pending += 1;
      request.then(afterHandlers, afterHandlers);
    }
    return request;
  };
  const trackedSend = nativeSend && function (...args) {
    if (watch.tracking) {
      watch.pending += 1;
      this.addEventListener('loadend', afterHandlers, { once: true });
    }
    return nativeSend.apply(this, args);
  };
  window.setTimeout = trackedSetTimeout;
  window.clearTimeout = trackedClearTimeout;
  if (trackedFetch) window.fetch = trackedFetch;
  if (trackedSend) xhrProto.send = trackedSend;
  watch.stop = () => {
    watch.tracking = false;
    watch.observer.disconnect();
    if (window.setTimeout === trackedSetTimeout) window.setTimeout = nativeSetTimeout;
    if (window.clearTimeout === trackedClearTimeout) window.clearTimeout = nativeClearTimeout;
    if (trackedFetch && window.fetch === trackedFetch) window.fetch = nativeFetch;
    if (trackedSend && xhrProto.send === trackedSend) xhrProto.send = nativeSend;
  };
  window.__flytoSettle = watch;
  return true;
}"""

# Resolves 'unchanged' immediately when nothing mutated since the watch was
# installed and no tracked work is outstanding, 'settled' once the DOM has been
# quiet for ``quietMs`` after the last mutation or finished piece of work,
# 'capped' at ``capMs``, or 'new_document' when the watch is gone (the page
# navigated). While tracked work is outstanding no quiet timer runs: the work
# finishing is what re-arms it, so a timer only exists while something is
# actually happening.
_SETTLE_DOM_JS = r"""([quietMs, capMs]) => new Promise((resolve) => {
  const watch = window.__flytoSettle;
  if (!watch || !watch.observer) { resolve('new_document'); return; }
  watch.tracking = false;
  const pending = watch.observer.takeRecords();
  if (pending.length) { watch.count += pending.length; watch.last = performance.now(); }
  let quietTimer = null;
  let capTimer = null;
  const finish = (reason) => {
    watch.clearTimeout(quietTimer);
    watch.clearTimeout(capTimer);
    watch.onMutation = null;
    watch.onSettle = null;
    watch.stop();
    if (window.__flytoSettle === watch) delete window.__flytoSettle;
    resolve(reason);
  };
  const arm = () => {
    watch.clearTimeout(quietTimer);
    if (watch.pending > 0) return;
    if (watch.count === 0 && watch.activity === 0) { finish('unchanged'); return; }
    const quietFor = performance.now() - Math.max(watch.last, watch.activity);
    quietTimer = watch.setTimeout(() => finish('settled'), Math.max(0, quietMs - quietFor));
  };
  watch.onMutation = arm;
  watch.onSettle = arm;
  capTimer = watch.setTimeout(() => finish('capped'), capMs);
  arm();
})"""

# Resolves on a batch of DOM mutations that could reveal an element -- a node
# added, text changed, or a visibility-bearing attribute flipped -- or at
# ``capMs``. A batch ends once the DOM has been quiet for ``quietMs`` or
# ``batchMs`` after its first record, whichever is first. A single change is
# answered within one quiet window, and a page that mutates continuously
# (a ticking clock, an animation) wakes the caller at most once per
# ``batchMs`` instead of on every frame. Used to re-run heuristics that no
# locator can express.
_NEXT_MUTATION_JS = r"""([capMs, quietMs, batchMs]) => new Promise((resolve) => {
  const root = document.documentElement || document;
  let capTimer = null;
  let quietTimer = null;
  let batchTimer = null;
  const finish = (reason) => {
    clearTimeout(capTimer);
    clearTimeout(quietTimer);
    clearTimeout(batchTimer);
    observer.disconnect();
    resolve(reason);
  };
  const observer = new MutationObserver(() => {
    clearTimeout(quietTimer);
    quietTimer = setTimeout(() => finish('mutated'), quietMs);
    if (batchTimer === null) batchTimer = setTimeout(() => finish('mutated'), batchMs);
  });
  observer.observe(root, {
    subtree: true, childList: true, characterData: true, attributes: true,
    attributeFilter: ['class', 'style', 'hidden', 'aria-hidden', 'aria-label',
                      'placeholder', 'title', 'disabled', 'open'],
  });
  capTimer = setTimeout(() => finish('capped'), capMs);
})"""

# Resolves once the DOM has gone ``quietMs`` without a mutation, or at
# ``capMs``. The timer is re-armed by mutations, so a still page answers after
# exactly one quiet window and a busy one at the cap.
_DOM_QUIET_JS = r"""([quietMs, capMs]) => new Promise((resolve) => {
  const root = document.documentElement || document;
  let quietTimer = null;
  let capTimer = null;
  const finish = (reason) => {
    clearTimeout(quietTimer);
    clearTimeout(capTimer);
    observer.disconnect();
    resolve(reason);
  };
  const arm = () => {
    clearTimeout(quietTimer);
    quietTimer = setTimeout(() => finish('quiet'), quietMs);
  };
  const observer = new MutationObserver(arm);
  observer.observe(root, {
    subtree: true, childList: true, attributes: true, characterData: true,
  });
  capTimer = setTimeout(() => finish('capped'), capMs);
  arm();
})"""

# A new document renders interactive content after domcontentloaded. Anything a
# following step could act on counts, including plain buttons and links, so a
# page with no form fields does not spend the whole budget.
INTERACTIVE_SELECTOR = (
    'input:not([type=hidden]), textarea, select, button, a[href], '
    '[role="button"], [role="link"], [role="combobox"], [role="listbox"], '
    '[contenteditable="true"]'
)


async def install_dom_watch(page) -> bool:
    """Start counting DOM mutations on ``page``; False when that is impossible."""
    try:
        return bool(await page.evaluate(_INSTALL_DOM_WATCH_JS))
    except Exception:  # noqa: BLE001 - a page we cannot script just is not watched
        return False


async def settle_dom(page, *, quiet_ms: int = 100, cap_ms: int = 1000) -> str:
    """Wait until the DOM stops changing after ``install_dom_watch``.

    Returns at once with 'unchanged' when the action mutated nothing and left
    no timer or request of its own outstanding; work it did start is waited
    for (within ``cap_ms``) before the quiet window runs. The answer
    'new_document' means the watch did not survive, i.e. the page
    navigated, and 'error' means the page could not be asked at all.
    """
    try:
        return await page.evaluate(_SETTLE_DOM_JS, [quiet_ms, cap_ms])
    except Exception:  # noqa: BLE001 - mid-navigation contexts are destroyed
        return 'error'


async def settle_new_document(page, *, cap_ms: int = 5000) -> Optional[str]:
    """Settle a freshly loaded document: interactive content, or a still page.

    Ends when anything a following step could act on exists, or -- for a page
    that has none, such as a blank popup or a text-only result -- once the
    document has loaded and its DOM has stopped changing. ``cap_ms`` bounds a
    page that does neither.
    """
    return await first_state(
        {
            'interactive': page.wait_for_function(
                '(sel) => document.querySelectorAll(sel).length > 0',
                arg=INTERACTIVE_SELECTOR,
                timeout=cap_ms,
            ),
            'quiet': settle_document(page, quiet_ms=300, cap_ms=cap_ms),
        },
        timeout_ms=cap_ms,
    )


async def settle_document(page, *, quiet_ms: int, cap_ms: int) -> str:
    """Wait for ``page``'s document to load and then go ``quiet_ms`` without a mutation.

    Raises when the document is replaced mid-wait (its context is destroyed),
    which a ``first_state`` race treats as this wait dropping out.
    """
    await page.wait_for_load_state('load', timeout=max(1, cap_ms))
    return await page.evaluate(_DOM_QUIET_JS, [quiet_ms, max(1, cap_ms)])


async def next_mutation(
    frame, *, cap_ms: int, quiet_ms: int = 50, batch_ms: int = 250,
) -> str:
    """Resolve on ``frame``'s next batch of element-revealing mutations or at the cap."""
    cap_ms = max(1, int(cap_ms))
    return await frame.evaluate(
        _NEXT_MUTATION_JS, [cap_ms, min(quiet_ms, cap_ms), min(batch_ms, cap_ms)],
    )


async def first_state(waits: Mapping[str, Awaitable], timeout_ms: float) -> Optional[str]:
    """Return the name of the first wait that completes without raising.

    Waits that raise (a timeout, a malformed selector, a destroyed context)
    drop out of the race instead of ending it; ``None`` means nothing was
    observed within ``timeout_ms``. Losing waits are cancelled before this
    returns, so no listener outlives the call.
    """
    loop = asyncio.get_running_loop()
    tasks = {asyncio.ensure_future(wait): name for name, wait in waits.items()}
    pending = set(tasks)
    deadline = loop.time() + max(0.0, timeout_ms) / 1000
    try:
        while pending:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            done, pending = await asyncio.wait(
                pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED,
            )
            # Read every finished task's exception, winners included, so a
            # loser that raised is never reported as an unretrieved error.
            winners = [
                task for task in done
                if not task.cancelled() and task.exception() is None
            ]
            if winners:
                return tasks[winners[0]]
        return None
    finally:
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
