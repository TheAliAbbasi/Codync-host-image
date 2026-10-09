"""Unit tests for scripts/install-agent-on-demand.sh (sourced, not executed)."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install-agent-on-demand.sh"


def _bash_source(script: Path, body: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "-c", f"set -eu; . '{script}'; {body}"],
        capture_output=True,
        text=True,
        env=merged,
        check=False,
    )


class AgentCliPresentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cli_home = Path(self.tmp.name) / "codync-cli"
        self.cli_home.mkdir()
        self.env = {"CODYNC_CLI_HOME": str(self.cli_home)}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_cli_returns_false(self) -> None:
        proc = _bash_source(
            INSTALL_SCRIPT,
            "if agent_cli_present definitely-not-installed; then exit 2; fi",
            env=self.env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_detects_executable_under_known_paths(self) -> None:
        for sub in (".local/bin", ".npm/bin", ".opencode/bin", "bin"):
            with self.subTest(sub=sub):
                bindir = self.cli_home / sub
                bindir.mkdir(parents=True)
                tool = bindir / "fake-agent"
                tool.write_text("#!/bin/sh\ntrue\n")
                tool.chmod(0o755)
                proc = _bash_source(
                    INSTALL_SCRIPT,
                    "agent_cli_present fake-agent",
                    env=self.env,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                tool.unlink()

    def test_detects_nested_bin_directory(self) -> None:
        nested = self.cli_home / "vendor" / "foo" / "bin"
        nested.mkdir(parents=True)
        tool = nested / "nested-cli"
        tool.write_text("#!/bin/sh\ntrue\n")
        tool.chmod(0o755)
        proc = _bash_source(
            INSTALL_SCRIPT,
            "agent_cli_present nested-cli",
            env=self.env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_command_on_path(self) -> None:
        bindir = Path(self.tmp.name) / "path-bin"
        bindir.mkdir()
        tool = bindir / "on-path-tool"
        tool.write_text("#!/bin/sh\ntrue\n")
        tool.chmod(0o755)
        env = {**self.env, "PATH": f"{bindir}:{os.environ.get('PATH', '')}"}
        proc = _bash_source(INSTALL_SCRIPT, "agent_cli_present on-path-tool", env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class InstallScriptStructureTests(unittest.TestCase):
    def test_every_install_function_checks_agent_cli_present(self) -> None:
        text = INSTALL_SCRIPT.read_text()
        install_funcs = re.findall(r"^(_install_\w+)\(\)", text, re.MULTILINE)
        self.assertGreater(len(install_funcs), 5)
        for func in install_funcs:
            block = re.search(
                rf"{func}\(\) \{{(.*?\n\}})",
                text,
                re.DOTALL,
            )
            self.assertIsNotNone(block, f"missing body for {func}")
            body = block.group(1)
            self.assertIn(
                "agent_cli_present",
                body,
                f"{func} must call agent_cli_present before installing",
            )

    def test_no_legacy_have_helper(self) -> None:
        text = INSTALL_SCRIPT.read_text()
        self.assertNotIn("_have()", text)
        self.assertNotIn("_have ", text)


class LazyInstallSkipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cli_home = Path(self.tmp.name) / "codync-cli"
        (self.cli_home / ".npm" / "bin").mkdir(parents=True)
        gemini = self.cli_home / ".npm" / "bin" / "gemini"
        gemini.write_text("#!/bin/sh\necho gemini-stub\n")
        gemini.chmod(0o755)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_gemini_skips_npm_when_preinstalled(self) -> None:
        env = {
            "CODYNC_CLI_HOME": str(self.cli_home),
            "GEMINI_API_KEY": "test-key",
            "PATH": f"{self.cli_home}/.npm/bin:/usr/bin:/bin",
        }
        proc = _bash_source(
            INSTALL_SCRIPT,
            "_install_gemini; echo install-gemini-ok",
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("install-gemini-ok", proc.stdout)
        self.assertNotIn("npm", proc.stderr.lower())


if __name__ == "__main__":
    unittest.main()
