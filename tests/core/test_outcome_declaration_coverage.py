# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Which side-effecting modules still cannot say what they proved.

Not a percentage, and not a number in a budget file: a list, by name, that may
only get shorter. The difference matters. A count of 196 tells you nothing you
can act on; a name tells you which module to open. And a module that quietly
falls out of the population — because somebody renamed a category, or the
classifier drifted — shows up as a stale entry rather than as an improvement.

Two ways a module satisfies this:

  * it declares — `postcondition=` or `derives=` on `@register_module`; or
  * it reports — its source imports `core.engine.outcome`, meaning it builds an
    envelope at runtime and the rung is decided from what it measured.

Reporting without declaring is a real state and deliberately counts: `verified`
requires a declared postcondition, but `dispatched`, `accepted` and `observed`
are earned by measurement, and a module that honestly reports `accepted` has
done the work this ratchet exists to ask for. What it has not done is claim to
have proved anything, which is the point.

THE POPULATION is `outcome.is_side_effecting` — 200 of 483 registered modules.
That predicate had to be widened from the one live classifier in the repository
(`modules/quality/rules/capability.py:47`), which lists `sms`, a category no
module registers, and omits `http`, `ssh`, `docker`, `k8s`, `network`,
`notification`, `storage`, `queue`, `git`, `process`, `port` and `dns`. Under
the old list `http.request` was not side-effecting, which is not a taxonomy
anyone can defend.

WHAT THIS DOES NOT DO is fail a module for being on the list. Everything here is
allowed to be here — that is what makes shipping possible at all. What it stops
is the other thing: a module leaving the list without anybody noticing, and a
module joining the population and being silently absent from both the covered
set and the written-down gap.
"""

from __future__ import annotations

import ast
import inspect
import os

import pytest

from core.engine.outcome import is_side_effecting


@pytest.fixture(scope="module")
def registry():
    os.environ.pop("FLYTO_ENV", None)
    from core.modules import atomic  # noqa: F401 - registers every module
    from core.modules import composite  # noqa: F401
    from core.modules.registry import ModuleRegistry

    # filter_by_stability=False on purpose: the default hides beta and alpha
    # modules under FLYTO_ENV=production, and a gate that cannot see them is a
    # gate the next beta module walks straight past.
    return ModuleRegistry, ModuleRegistry.get_all_metadata(filter_by_stability=False)


def _carries_contract(ModuleRegistry, module_id, metadata):
    """Declared on the decorator, or built at runtime from a measurement."""
    if metadata.get("postcondition") or metadata.get("derives"):
        return True
    module_class = ModuleRegistry.get(module_id)
    if module_class is None:
        return False
    try:
        source_path = inspect.getsourcefile(module_class)
        tree = ast.parse(open(source_path, encoding="utf-8").read())
    except (OSError, SyntaxError, TypeError):
        return False
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module
        and "engine.outcome" in node.module
        for node in ast.walk(tree)
    )


#: Side-effecting modules that cannot yet say what they proved. May only shrink.
#: Generated once from the registry on the day this landed; every later change
#: to it should be a deletion.
UNDECLARED = {
    "agent.autonomous",
    "agent.chain",
    "agent.tool_use",
    "ai.embed",
    "ai.extract",
    "ai.local_ollama.chat",
    "ai.memory",
    "ai.memory.entity",
    "ai.memory.redis",
    "ai.memory.vector",
    "ai.model",
    "ai.tool",
    "ai.vision.analyze",
    "api.anthropic.chat",
    "api.github.create_issue",
    "api.github.create_pr",
    "api.github.get_repo",
    "api.github.list_issues",
    "api.github.list_repos",
    "api.google_gemini.chat",
    "api.google_sheets.read",
    "api.google_sheets.write",
    "api.notion.create_page",
    "api.notion.query_database",
    "api.openai.chat",
    "api.openai.image",
    "auth.oauth2",
    "aws.s3.delete",
    "aws.s3.download",
    "aws.s3.list",
    "aws.s3.upload",
    "browser.challenge",
    "browser.click",
    "browser.close",
    "browser.connect",
    "browser.console",
    "browser.cookies",
    "browser.cookies_file",
    "browser.detect",
    "browser.detect_list",
    "browser.dialog",
    "browser.download",
    "browser.drag",
    "browser.emulate",
    "browser.ensure",
    "browser.evaluate",
    "browser.extract",
    "browser.extract_nested",
    "browser.find",
    "browser.form",
    "browser.frame",
    "browser.geolocation",
    "browser.goto",
    "browser.hover",
    "browser.interact",
    "browser.launch",
    "browser.login",
    "browser.navigation",
    "browser.network",
    "browser.pages",
    "browser.pagination",
    "browser.pdf",
    "browser.performance",
    "browser.pool",
    "browser.press",
    "browser.proxy_rotate",
    "browser.readability",
    "browser.record",
    "browser.release",
    "browser.response",
    "browser.robots",
    "browser.screenshot",
    "browser.scroll",
    "browser.select",
    "browser.sitemap",
    "browser.snapshot",
    "browser.storage",
    "browser.tab",
    "browser.table",
    "browser.throttle",
    "browser.trace",
    "browser.type",
    "browser.upload",
    "browser.viewport",
    "browser.wait",
    "cache.clear",
    "cache.delete",
    "cache.get",
    "cache.set",
    "cloud.aws_s3.download",
    "cloud.aws_s3.upload",
    "cloud.azure.download",
    "cloud.azure.upload",
    "cloud.gcs.download",
    "cloud.gcs.upload",
    "communication.twilio.make_call",
    "communication.twilio.send_sms",
    "core.api.google_search",
    "core.api.serpapi_search",
    "core.api.tavily_search",
    "database.insert",
    "database.update",
    "db.mongodb.find",
    "db.mongodb.insert",
    "db.mysql.query",
    "db.postgresql.query",
    "db.redis.get",
    "db.redis.set",
    "dns.lookup",
    "docker.build",
    "docker.inspect_container",
    "docker.logs",
    "docker.ps",
    "docker.run",
    "docker.stop",
    "email.read",
    "email.send",
    "file.copy",
    "file.delete",
    "file.diff",
    "file.edit",
    "file.exists",
    "file.move",
    "file.read",
    "git.clone",
    "git.commit",
    "git.diff",
    "google.calendar.create_event",
    "google.calendar.list_events",
    "google.gmail.search",
    "google.gmail.send",
    "http.batch",
    "http.get",
    "http.paginate",
    "http.response_assert",
    "http.session",
    "http.webhook_wait",
    "integration.jira.create_issue",
    "integration.jira.search_issues",
    "integration.salesforce.create_record",
    "integration.salesforce.query",
    "integration.salesforce.update_record",
    "integration.slack.list_channels",
    "integration.slack.send_message",
    "k8s.apply",
    "k8s.describe",
    "k8s.get_pods",
    "k8s.logs",
    "k8s.scale",
    "llm.agent",
    "llm.chat",
    "llm.code_fix",
    "network.ping",
    "network.port_scan",
    "network.traceroute",
    "network.whois",
    "notification.discord.send_message",
    "notification.email.send",
    "notification.slack.send_message",
    "notification.teams.send_message",
    "notification.telegram.send_message",
    "notification.whatsapp.send_message",
    "payment.stripe.create_payment",
    "payment.stripe.get_customer",
    "payment.stripe.list_charges",
    "port.check",
    "port.wait",
    "process.list",
    "process.start",
    "process.stop",
    "productivity.airtable.create",
    "productivity.airtable.read",
    "productivity.airtable.update",
    "queue.dequeue",
    "queue.enqueue",
    "queue.size",
    "robotics.move",
    "robotics.stop",
    "robotics.turn",
    "sandbox.execute_js",
    "sandbox.execute_python",
    "sandbox.execute_shell",
    "scheduler.cron_parse",
    "scheduler.delay",
    "scheduler.interval",
    "slack.send",
    "ssh.exec",
    "ssh.sftp_download",
    "ssh.sftp_upload",
    "storage.delete",
    "storage.get",
    "storage.set",
    "ui.evaluate",
    "verify.figma",
    "vision.analyze",
    "vision.compare",
}


class TestTheListOnlyShrinks:
    def test_no_new_module_is_missing_from_both_the_covered_set_and_this_list(
        self, registry
    ):
        """The one that catches a module added tomorrow.

        A new side-effecting module is either written with an outcome or written
        down here. Silently neither is how 483 modules came to have one contract
        between them.
        """
        ModuleRegistry, metadata = registry
        unaccounted = sorted(
            module_id
            for module_id, meta in metadata.items()
            if is_side_effecting(module_id, meta)
            and not _carries_contract(ModuleRegistry, module_id, meta)
            and module_id not in UNDECLARED
        )

        assert not unaccounted, (
            "these side-effecting modules report no outcome and are not on the "
            f"list: {unaccounted}. Give each one an envelope, or add it here and "
            "say so in the commit."
        )

    def test_the_list_has_no_stale_entries(self, registry):
        """An entry that no longer needs excusing is progress worth recording."""
        ModuleRegistry, metadata = registry
        no_longer_needed = sorted(
            module_id
            for module_id in UNDECLARED
            if module_id in metadata
            and _carries_contract(ModuleRegistry, module_id, metadata[module_id])
        )

        assert not no_longer_needed, (
            f"these now report an outcome and can come off the list: "
            f"{no_longer_needed}"
        )

    def test_the_list_names_no_module_that_does_not_exist(self, registry):
        """Renames and deletions leave entries that excuse nothing."""
        _, metadata = registry
        gone = sorted(module_id for module_id in UNDECLARED if module_id not in metadata)

        assert not gone, f"these are not registered any more: {gone}"

    def test_the_list_names_nothing_that_is_not_side_effecting(self, registry):
        """A derived module on this list would be excusing a duty it never had."""
        _, metadata = registry
        wrong_population = sorted(
            module_id
            for module_id in UNDECLARED
            if module_id in metadata and not is_side_effecting(module_id, metadata[module_id])
        )

        assert not wrong_population, (
            f"these are not side-effecting and do not belong here: {wrong_population}"
        )


class TestThePopulationIsWhatItClaims:
    def test_http_request_is_side_effecting(self, registry):
        """The module the previous classifier missed, pinned by name.

        `http` was absent from `capability.py`'s seven categories while `sms` —
        which no module registers — was present. A contract whose population
        excludes HTTP is not a contract, and the next person to narrow the list
        should have to delete this test to do it.
        """
        _, metadata = registry
        assert is_side_effecting("http.request", metadata.get("http.request", {}))

    def test_a_pure_computation_is_not_side_effecting(self, registry):
        _, metadata = registry
        assert not is_side_effecting("string.uppercase", metadata.get("string.uppercase", {}))

    def test_requires_credentials_is_enough_on_its_own(self):
        """The half of the rule that is not the category prefix."""
        assert is_side_effecting("anything.at_all", {"requires_credentials": True})
