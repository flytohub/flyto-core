"""Every command in docs/guides/BUILD_A_PACK.md is run, in order, exactly as written.

The guide is the end-to-end path a provider follows without Flyto2's help:
init, decide, test, build, sign, run standalone, load into a Space. This
test reads it and runs it:

* every line of a ```` ```sh ```` block is a command, run in one working
  directory in page order (``export`` lines set the environment; a trailing
  ``# exit N`` states the exit code the page promises, otherwise 0);
  ``flyto pack run`` is started as a real process and spoken to as an MCP
  client;
* a block after ``<!-- file: NAME -->`` is written to ``NAME`` first;
* every ```` ```python ```` block is executed;
* a ```` ```json ```` block after ``<!-- excerpt: PATH -->`` must be the
  file's own content;
* every ``flyto`` command quoted inline must be one a block runs.

So no command on the page is untested prose. The page's hashed lockfile is
this suite's fixture lock (the page cannot ship a real hash), and nothing
reaches a provider: ``pack test`` answers from recorded fixtures, and the
standalone server is only listed, never called.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading

import pytest
from devkit_helpers import LOCK, ROOT, cli

GUIDE = ROOT / "docs" / "guides" / "BUILD_A_PACK.md"
FENCE = re.compile(r"(?:<!-- (file|excerpt): (\S+) -->\s*\n)?```(\w+)\n(.*?)```", re.DOTALL)
INLINE = re.compile(r"(?<!`)`(flyto [^`]+)`(?!`)")
EXIT = re.compile(r"\s+#\s*exit\s+(\d+)\s*$")


def blocks():
    return [(m.group(1), m.group(2), m.group(3), m.group(4)) for m in FENCE.finditer(GUIDE.read_text(encoding="utf-8"))]


def commands():
    found = []
    for _marker, _target, language, body in blocks():
        if language == "sh":
            found += [line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith("#")]
    return found


def contained(excerpt, actual):
    """The excerpt states nothing the file does not: every key, and every object in a list, is the file's own.

    A list of objects (the operations) may be quoted in part; a list of values
    (the features an operation requires) is quoted whole, in order.
    """
    if isinstance(excerpt, dict):
        return isinstance(actual, dict) and all(k in actual and contained(v, actual[k]) for k, v in excerpt.items())
    if isinstance(excerpt, list) and not all(isinstance(item, dict) for item in excerpt):
        return excerpt == actual
    if isinstance(excerpt, list):
        return isinstance(actual, list) and all(any(contained(e, a) for a in actual) for e in excerpt)
    return excerpt == actual


def run_standalone(argv, cwd, env):
    """Start ``flyto pack run`` as a process, list its tools as an MCP client, then close it."""
    command = [sys.executable, "-m", "cli.main", *argv]
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, bufsize=1)
    lines = []

    def read():
        lines.append(process.stdout.readline())

    try:
        answers = []
        for message in (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "guide", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ):
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
            if "id" in message:
                reader = threading.Thread(target=read, daemon=True)
                reader.start()
                reader.join(60)
                assert lines and lines[-1], "the standalone server did not answer"
                answers.append(json.loads(lines[-1]))
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
        stderr = process.stderr.read()
        process.stderr.close()
        process.stdout.close()
    assert process.returncode == 0, stderr
    return answers, stderr


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """A directory laid out like a provider's: the lockfile, and the example the page tests."""
    shutil.copy(LOCK, tmp_path / "requirements.lock")
    example = tmp_path / "examples" / "packs" / "product-combinations"
    shutil.copytree(ROOT / "examples" / "packs" / "product-combinations", example)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FLYTO_PACK_NO_KEYCHAIN", "1")
    return tmp_path


def test_every_command_on_the_page_runs_as_written(workdir, capsys, monkeypatch):
    ran = []
    standalone = []
    for marker, target, language, body in blocks():
        if marker == "file":
            (workdir / target).write_text(body, encoding="utf-8")
            continue
        if language == "python":
            exec(compile(body, str(GUIDE), "exec"), {"__name__": "guide"})  # noqa: S102 - the page's own code
            ran.append("python")
            continue
        if language != "sh":
            continue
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            expected = 0
            match = EXIT.search(line)
            if match:
                expected, line = int(match.group(1)), line[: match.start()]
            argv = shlex.split(line)
            if argv[0] == "export":
                name, _, value = argv[1].partition("=")
                monkeypatch.setenv(name, value)
                continue
            assert argv[:2] == ["flyto", "pack"], f"the page runs only flyto pack commands: {line}"
            if argv[2] == "run":
                env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
                answers, stderr = run_standalone(argv[1:], workdir, env)
                standalone.append((answers, stderr))
                code = 0
            else:
                capsys.readouterr()
                code = cli(*argv[2:])
            assert code == expected, f"{line} exited {code}, the page says {expected}\n{capsys.readouterr()}"
            ran.append(line)
    assert "python" in ran, "the page loads the pack into a Space"
    assert standalone, "the page runs the pack standalone"
    answers, stderr = standalone[0]
    assert answers[0]["result"]["serverInfo"]["name"] == "com.example.items"
    assert {tool["name"] for tool in answers[1]["result"]["tools"]} == {"items.account.entitlements", "items.item.get"}
    assert "your-provider-token" not in stderr


def test_the_page_covers_the_whole_path():
    subcommands = [shlex.split(EXIT.sub("", line))[2] for line in commands() if line.startswith("flyto ")]
    for step in ("init", "doctor", "consequence", "test", "keygen", "build", "verify", "health", "run"):
        assert step in subcommands, f"the page has no flyto pack {step}"
    assert subcommands.index("init") < subcommands.index("test") < subcommands.index("build") < subcommands.index("run")


def test_every_inline_flyto_command_is_one_a_block_runs():
    run = {tuple(shlex.split(EXIT.sub("", line))[:3]) for line in commands() if line.startswith("flyto ")}
    for quoted in INLINE.findall(GUIDE.read_text(encoding="utf-8")):
        words = quoted.split()
        assert tuple(words[:3]) in run, f"`{quoted}` is quoted on the page but no block runs it"


def test_every_excerpt_is_the_files_own_content():
    excerpts = [(target, body) for marker, target, _language, body in blocks() if marker == "excerpt"]
    assert excerpts, "the worked example quotes its manifest"
    for target, body in excerpts:
        actual = json.loads((ROOT / target).read_text(encoding="utf-8"))
        assert contained(json.loads(body), actual), f"the excerpt of {target} is not the file's content"
