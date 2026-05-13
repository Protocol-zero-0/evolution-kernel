"""Tests for Issue #17 / PR7a: process sandbox via firejail.

Layers exercised:

1. Config parsing — ``sandbox`` block shape, defaults, validation errors.
2. ``sandbox.wrap_argv`` — pure-function transformation, no subprocess.
3. End-to-end Governor run with sandbox enabled, verifying the OS blocks an
   out-of-worktree write attempted by the executor fixture.

The E2E layer is skipped when firejail is not installed, so the rest of the
unit tests stay portable.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evolution_kernel.config import ConfigError, parse_config
from evolution_kernel.governor import Governor, RoleCommand
from evolution_kernel.sandbox import SandboxConfig, SandboxError, wrap_argv


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _git(args, cwd):
    r = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {r.stderr}")
    return r.stdout.strip()


def _bootstrap_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(["init"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    (repo / "README.md").write_text("# target\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "initial"], repo)


def _role(name: str) -> RoleCommand:
    return RoleCommand([sys.executable, str(FIXTURES / name)])


# When invoked inside firejail the default interpreter at sys.executable may
# live under /home/<other-user>/, which firejail auto-cleans by default and
# refuses to re-expose via --noblacklist / --whitelist. Use the system python
# for sandboxed role processes so the test exercises firejail honestly. The
# test is skipped if /usr/bin/python3 is not available.
SYSTEM_PYTHON = "/usr/bin/python3"


def _role_system_python(name: str) -> RoleCommand:
    return RoleCommand([SYSTEM_PYTHON, str(FIXTURES / name)])


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------


class TestSandboxConfigParsing(unittest.TestCase):

    def test_default_is_disabled_firejail(self):
        cfg = parse_config({"mission": "x"})
        self.assertFalse(cfg.sandbox.enabled)
        self.assertEqual(cfg.sandbox.backend, "firejail")
        self.assertEqual(cfg.sandbox.extra_args, ())

    def test_enable_with_extra_args(self):
        cfg = parse_config({
            "mission": "x",
            "sandbox": {
                "enabled": True,
                "backend": "firejail",
                "extra_args": ["--private-tmp", "--net=none"],
            },
        })
        self.assertTrue(cfg.sandbox.enabled)
        self.assertEqual(cfg.sandbox.extra_args, ("--private-tmp", "--net=none"))

    def test_enabled_must_be_bool(self):
        with self.assertRaises(ConfigError):
            parse_config({"mission": "x", "sandbox": {"enabled": "yes"}})

    def test_backend_must_be_string(self):
        with self.assertRaises(ConfigError):
            parse_config({"mission": "x", "sandbox": {"backend": 42}})

    def test_extra_args_must_be_list(self):
        with self.assertRaises(ConfigError):
            parse_config({"mission": "x", "sandbox": {"extra_args": "--net=none"}})

    def test_extra_args_must_be_strings(self):
        with self.assertRaises(ConfigError):
            parse_config({"mission": "x", "sandbox": {"extra_args": ["", "x"]}})

    def test_sandbox_block_must_be_mapping(self):
        with self.assertRaises(ConfigError):
            parse_config({"mission": "x", "sandbox": [1, 2]})


# ---------------------------------------------------------------------------
# wrap_argv unit tests
# ---------------------------------------------------------------------------


class TestWrapArgv(unittest.TestCase):

    def test_disabled_returns_argv_unchanged(self):
        out = wrap_argv(["echo", "hi"], worktree="/tmp", config=SandboxConfig(enabled=False))
        self.assertEqual(out, ["echo", "hi"])

    def test_none_config_returns_argv_unchanged(self):
        out = wrap_argv(["echo", "hi"], worktree="/tmp", config=None)
        self.assertEqual(out, ["echo", "hi"])

    def test_firejail_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            out = wrap_argv(
                ["echo", "hi"],
                worktree=td,
                config=SandboxConfig(enabled=True, backend="firejail"),
            )
        self.assertEqual(out[0], "firejail")
        self.assertIn("--read-only=/", out)
        self.assertTrue(any(arg.startswith("--read-write=") for arg in out))
        # Original argv must follow `--`
        sep = out.index("--")
        self.assertEqual(out[sep + 1 :], ["echo", "hi"])

    def test_extra_writable_included(self):
        with tempfile.TemporaryDirectory() as worktree, tempfile.TemporaryDirectory() as ledger:
            out = wrap_argv(
                ["echo", "hi"],
                worktree=worktree,
                writable=[ledger],
                config=SandboxConfig(enabled=True),
            )
        rw = [a for a in out if a.startswith("--read-write=")]
        self.assertEqual(len(rw), 2)

    def test_extra_writable_dedup(self):
        with tempfile.TemporaryDirectory() as wt:
            out = wrap_argv(
                ["echo", "hi"],
                worktree=wt,
                writable=[wt, wt],
                config=SandboxConfig(enabled=True),
            )
        rw = [a for a in out if a.startswith("--read-write=")]
        self.assertEqual(len(rw), 1)

    def test_extra_args_appended_before_separator(self):
        with tempfile.TemporaryDirectory() as wt:
            out = wrap_argv(
                ["echo", "hi"],
                worktree=wt,
                config=SandboxConfig(
                    enabled=True,
                    extra_args=("--private-tmp", "--net=none"),
                ),
            )
        sep = out.index("--")
        self.assertIn("--private-tmp", out[:sep])
        self.assertIn("--net=none", out[:sep])

    def test_unsupported_backend_raises(self):
        with self.assertRaises(SandboxError):
            wrap_argv(
                ["echo", "hi"],
                worktree="/tmp",
                config=SandboxConfig(enabled=True, backend="bubblewrap"),
            )


# ---------------------------------------------------------------------------
# End-to-end: a real firejail run blocks an out-of-worktree write
# ---------------------------------------------------------------------------


_FIREJAIL_AVAILABLE = shutil.which("firejail") is not None
_SYSTEM_PYTHON_AVAILABLE = Path(SYSTEM_PYTHON).exists()


@unittest.skipUnless(_FIREJAIL_AVAILABLE, "firejail not installed")
@unittest.skipUnless(
    _SYSTEM_PYTHON_AVAILABLE,
    "/usr/bin/python3 not available — firejail hides other /home/* prefixes",
)
class TestSandboxBlocksEscape(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # Place the temp dir under /tmp so the firejail sandbox can reach it
        # — anything under /home/<other-user> is auto-hidden by firejail.
        self.base = Path(self._tmp.name)
        self.repo = self.base / "repo"
        self.ledger = self.base / "ledger"
        _bootstrap_repo(self.repo)
        # Escape target lives outside both repo and ledger and is unique per
        # test so a leftover from a prior interactive run cannot confuse us.
        self.escape = self.base / "escape" / "out.txt"
        self.escape.parent.mkdir(parents=True, exist_ok=True)
        self._old_env = os.environ.get("ESCAPE_TARGET")
        os.environ["ESCAPE_TARGET"] = str(self.escape)

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("ESCAPE_TARGET", None)
        else:
            os.environ["ESCAPE_TARGET"] = self._old_env
        self._tmp.cleanup()

    def _make_governor(self, sandbox: SandboxConfig | None) -> Governor:
        # The executor is the only role wrapped in the sandbox, so it is the
        # only one that must be invokable via the system interpreter.
        return Governor(
            target_repo=self.repo,
            ledger_dir=self.ledger,
            planner=_role("planner.py"),
            executor=_role_system_python("executor_escape_attempt.py"),
            evaluator=_role("evaluator_accept.py"),
            sandbox=sandbox,
        )

    def test_sandbox_blocks_outside_write(self):
        gov = self._make_governor(SandboxConfig(enabled=True))
        result = gov.run_once({"name": "sandbox-on"}, run_id="0001")

        executor_output = json.loads(
            (result.run_dir / "executor_output.json").read_text(encoding="utf-8")
        )
        self.assertTrue(executor_output["inside_write_ok"], executor_output)
        self.assertFalse(executor_output["outside_write_ok"], executor_output)
        self.assertIsNotNone(executor_output["outside_error"])
        # OS confirmation: the escape file must not exist on disk.
        self.assertFalse(
            self.escape.exists(),
            f"escape file leaked despite sandbox: {self.escape}",
        )
        # The inside write was committed and the candidate was accepted.
        self.assertTrue(result.decision.accepted, result.decision.reason)

    def test_no_sandbox_allows_outside_write(self):
        """Sanity check: the same executor without sandbox can write outside.

        Confirms the assertion above is meaningful (i.e. the previous test
        passed because of the sandbox, not because the fixture happened to
        always fail).
        """
        gov = self._make_governor(sandbox=None)
        result = gov.run_once({"name": "sandbox-off"}, run_id="0001")
        executor_output = json.loads(
            (result.run_dir / "executor_output.json").read_text(encoding="utf-8")
        )
        self.assertTrue(executor_output["inside_write_ok"])
        self.assertTrue(executor_output["outside_write_ok"], executor_output)
        self.assertTrue(self.escape.exists())


if __name__ == "__main__":
    unittest.main()
