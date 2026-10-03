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
_INSTALL_DOM_WATCH_JS = r"""() => {
  const previous = window.__flytoSettle;
  if (previous && previous.observer) previous.observer.disconnect();
  const root = document.documentElement || document;
  const watch = { count: 0, last: 0, onMutation: null };
  watch.observer = new MutationObserver((records) => {
    watch.count += records.length;
    watch.last = performance.now();
    if (watch.onMutation) watch.onMutation();
  });
  watch.observer.observe(root, {
    subtree: true, childList: true, attributes: true, characterData: true,
  });
  window.__flytoSettle = watch;
  return true;
}"""

# Resolves 'unchanged' immediately when nothing mutated since the watch was
# installed, 'settled' once the DOM has been quiet for ``quietMs``, 'capped' at
# ``capMs``, or 'new_document' when the watch is gone (the page navigated). The
# quiet window is re-armed by each mutation, so a timer only exists while the
# DOM is actually changing.
_SETTLE_DOM_JS = r"""([quietMs, capMs]) => new Promise((resolve) => {
  const watch = window.__flytoSettle;
  if (!watch || !watch.observer) { resolve('new_document'); return; }
  const pending = watch.observer.takeRecords();
  if (pending.length) { watch.count += pending.length; watch.last = performance.now(); }
  let quietTimer = null;
  let capTimer = null;
  const finish = (reason) => {
    clearTimeout(quietTimer);
    clearTimeout(capTimer);
    watch.observer.disconnect();
    watch.onMutation = null;
    if (window.__flytoSettle === watch) delete window.__flytoSettle;
    resolve(reason);
  };
  if (watch.count === 0) { finish('unchanged'); return; }
  const arm = () => {
    clearTimeout(quietTimer);
    const quietFor = performance.now() - watch.last;
    quietTimer = setTimeout(() => finish('settled'), Math.max(0, quietMs - quietFor));
  };
  watch.onMutation = arm;
  capTimer = setTimeout(() => finish('capped'), capMs);
  arm();
})"""

# Resolves on the first DOM mutation that could reveal an element -- a node
# added, text changed, or a visibility-bearing attribute flipped -- or at
# ``capMs``. Used to re-run heuristics that no locator can express.
_NEXT_MUTATION_JS = r"""(capMs) => new Promise((resolve) => {
  const root = document.documentElement || document;
  let capTimer = null;
  const observer = new MutationObserver(() => {
    clearTimeout(capTimer);
    observer.disconnect();
    resolve('mutated');
  });
  observer.observe(root, {
    subtree: true, childList: true, characterData: true, attributes: true,
    attributeFilter: ['class', 'style', 'hidden', 'aria-hidden', 'aria-label',
                      'placeholder', 'title', 'disabled', 'open'],
  });
  capTimer = setTimeout(() => { observer.disconnect(); resolve('capped'); }, capMs);
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

    Returns at once with 'unchanged' when the action mutated nothing. The
    answer 'new_document' means the watch did not survive, i.e. the page
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
    async def _loaded_and_quiet():
        await page.wait_for_load_state('load', timeout=cap_ms)
        await page.evaluate(_DOM_QUIET_JS, [300, cap_ms])

    return await first_state(
        {
            'interactive': page.wait_for_function(
                '(sel) => document.querySelectorAll(sel).length > 0',
                arg=INTERACTIVE_SELECTOR,
                timeout=cap_ms,
            ),
            'quiet': _loaded_and_quiet(),
        },
        timeout_ms=cap_ms,
    )


async def next_mutation(frame, *, cap_ms: int) -> str:
    """Resolve on ``frame``'s next element-revealing DOM mutation or at the cap."""
    return await frame.evaluate(_NEXT_MUTATION_JS, max(1, int(cap_ms)))


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
