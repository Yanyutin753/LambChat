"""Real-process checks for the shared validation gate; no services required."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[2] / "scripts/run_validation.py"


class ValidationGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = {**os.environ, "HOME": self.temp.name, "USERPROFILE": self.temp.name}

    def command(self, code):
        return [sys.executable, str(RUNNER), sys.executable, "-c", code]

    def stop(self, process):
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=5)

    def test_worktrees_share_one_slot(self):
        lock = Path(self.temp.name) / ".cache/lambchat/validation.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text(json.dumps({"owner": "stale", "pid": os.getpid()}))
        self.env["LAMBCHAT_VALIDATION_OWNER"] = "stale"
        first_dir = Path(self.temp.name) / "first"
        second_dir = Path(self.temp.name) / "second"
        first_dir.mkdir()
        second_dir.mkdir()
        first = subprocess.Popen(
            self.command("print('ready', flush=True); input()"),
            cwd=first_dir,
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self.stop, first)
        self.assertEqual(first.stdout.readline().strip(), "ready")
        second = subprocess.Popen(
            self.command("print('second', flush=True)"),
            cwd=second_dir,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self.stop, second)
        stdout, stderr = second.communicate(timeout=5)
        self.assertEqual(second.returncode, 75)
        self.assertEqual(stdout, "")
        self.assertIn("busy", stderr)
        first.communicate("\n", timeout=5)
        next_run = subprocess.run(self.command("pass"), env=self.env, timeout=5)
        self.assertEqual(next_run.returncode, 0)

    def test_nested_commands_reuse_slot(self):
        result = subprocess.run(
            [sys.executable, str(RUNNER), *self.command("print('nested')")],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "nested")

    def test_failure_releases_slot_and_preserves_exit_code(self):
        failed = subprocess.run(self.command("raise SystemExit(7)"), env=self.env)
        self.assertEqual(failed.returncode, 7)
        next_run = subprocess.run(self.command("pass"), env=self.env, timeout=5)
        self.assertEqual(next_run.returncode, 0)

    @unittest.skipIf(os.name == "nt", "POSIX process-group signal check")
    def test_termination_releases_slot(self):
        process = subprocess.Popen(
            self.command("print('ready', flush=True); input()"),
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(lambda: process.poll() is None and process.kill())
        self.assertEqual(process.stdout.readline().strip(), "ready")
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=5)
        self.assertEqual(process.returncode, 128 + signal.SIGTERM)
        next_run = subprocess.run(self.command("pass"), env=self.env, timeout=5)
        self.assertEqual(next_run.returncode, 0)

    def test_stale_metadata_does_not_keep_slot_busy(self):
        lock = Path(self.temp.name) / ".cache/lambchat/validation.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text('{"owner":"old","pid":999999999}')
        next_run = subprocess.run(self.command("pass"), env=self.env, timeout=5)
        self.assertEqual(next_run.returncode, 0)

    def test_worker_environment_cannot_raise_limit(self):
        result = subprocess.run(
            self.command(
                "import os; print(os.environ['VITEST_MAX_WORKERS'], os.environ['CARGO_BUILD_JOBS'], os.environ['RAYON_NUM_THREADS'], os.environ['GOMAXPROCS'])"
            ),
            env={**self.env, "VITEST_MAX_WORKERS": "8", "CARGO_BUILD_JOBS": "8"},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "1 1 1 1")

    def test_parallel_cli_overrides_are_rejected(self):
        for flag in [
            "--maxWorkers=8",
            "--maxConcurrency=2",
            "--concurrency=auto",
            "-j8",
            "--fileParallelism",
        ]:
            with self.subTest(flag=flag):
                result = subprocess.run(
                    [*self.command("pass"), flag], env=self.env, capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("single", result.stderr)

    def test_dev_server_goals_keep_parallel_make_enabled(self):
        result = subprocess.run(
            ["make", "-qp", "dev-all"], cwd=RUNNER.parent.parent, capture_output=True, text=True
        )
        self.assertIn(result.returncode, (0, 1))
        self.assertNotIn("\n.NOTPARALLEL:", result.stdout)

    def test_node_bridge_preserves_literal_arguments(self):
        result = subprocess.run(
            [
                "node",
                str(RUNNER.with_name("run-validation.mjs")),
                sys.executable,
                "-c",
                "import sys; print(sys.argv[1])",
                "space $HOME; literal",
            ],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "space $HOME; literal")

    def test_interrupt_releases_slot(self):
        if os.name == "nt":
            self.skipTest("POSIX process group signal check")
        import signal

        process = subprocess.Popen(
            self.command("import time; print('ready', flush=True); time.sleep(30)"),
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self.stop, process)
        self.assertEqual(process.stdout.readline().strip(), "ready")
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=5)
        self.assertEqual(process.returncode, 143)
        next_run = subprocess.run(self.command("pass"), env=self.env, timeout=5)
        self.assertEqual(next_run.returncode, 0)


if __name__ == "__main__":
    unittest.main()
