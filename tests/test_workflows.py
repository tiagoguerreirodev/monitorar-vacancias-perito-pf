"""Acceptance contracts for Actions configuration and its executable Git boundary.

Workflow files use JSON (a YAML subset) so these tests need only the stdlib.
Live Actions/Pages acceptance remains a separate maintainer check.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return json.loads((ROOT / ".github" / "workflows" / name).read_text())


class WorkflowTests(unittest.TestCase):
    def test_source_changes_and_untrusted_prs_only_validate_without_credentials(self):
        config = workflow("validate.yml")
        self.assertEqual(config["on"], {"push": {}, "pull_request": {}})
        self.assertEqual(config["permissions"], {"contents": "read"})
        self.assertEqual(set(config["jobs"]), {"validate"})
        job = config["jobs"]["validate"]
        self.assertNotIn("permissions", job)
        self.assertNotIn("environment", job)
        steps = job["steps"]
        self.assertEqual(steps[0]["uses"], "actions/checkout@v7")
        self.assertIs(steps[0]["with"]["persist-credentials"], False)
        self.assertEqual(steps[1]["uses"], "actions/setup-python@v7")
        self.assertEqual(steps[1]["with"]["python-version"], "3.13")
        self.assertEqual([step["run"] for step in steps if "run" in step],
                         ["python3 -m unittest discover -v",
                          "node --check perito_dashboard/assets/inspection.js"])
        self.assertFalse(any("secrets" in str(step) for step in steps))

    def test_only_serialized_trusted_monthly_or_manual_runs_build_and_deploy(self):
        config = workflow("pages.yml")
        self.assertEqual(config["on"], {
            "schedule": [{"cron": "0 9 28 * *", "timezone": "America/Sao_Paulo"}],
            "workflow_dispatch": {},
        })
        self.assertEqual(config["permissions"], {"contents": "read"})
        self.assertEqual(config["concurrency"], {"group": "pages-main", "cancel-in-progress": False})
        self.assertEqual(set(config["jobs"]), {"refresh", "deploy"})
        refresh, deploy = (config["jobs"][name] for name in ("refresh", "deploy"))
        guard = ("${{ github.repository == 'tiagoguerreirodev/monitorar-vacancias-perito-pf' "
                 "&& github.ref == 'refs/heads/main' && (github.event_name == 'schedule' "
                 "|| github.event_name == 'workflow_dispatch') }}")
        for job in (refresh, deploy):
            self.assertEqual(job["if"], guard)
            self.assertEqual(job["runs-on"], "ubuntu-latest")
            self.assertLessEqual(job["timeout-minutes"], 30)
        self.assertEqual(refresh["permissions"], {"contents": "write"})
        self.assertEqual(deploy["permissions"], {
            "contents": "read", "pages": "write", "id-token": "write",
        })
        self.assertEqual(deploy["needs"], "refresh")
        self.assertEqual(deploy["environment"], {
            "name": "github-pages", "url": "${{ steps.deployment.outputs.page_url }}",
        })
        steps = refresh["steps"]
        self.assertEqual(steps[0]["uses"], "actions/checkout@v7")
        self.assertEqual(steps[0]["with"], {"ref": "${{ github.sha }}", "persist-credentials": False})
        self.assertEqual(steps[1]["uses"], "actions/setup-python@v7")
        self.assertEqual(steps[1]["with"]["python-version"], "3.13")
        commands = [step["run"] for step in steps if "run" in step]
        self.assertEqual(commands[:2], ["python3 -m unittest discover -v",
                                        "python3 -m perito_dashboard --data-dir data --site-dir site"])
        upload = steps[-1]
        self.assertEqual(upload["uses"], "actions/upload-pages-artifact@v5")
        self.assertEqual(upload["with"]["path"], "site")
        self.assertEqual(upload["with"]["name"], "pages-${{ github.run_id }}-${{ github.run_attempt }}")
        publish = deploy["steps"][-1]
        self.assertEqual(publish["uses"], "actions/deploy-pages@v5")
        self.assertEqual(publish["id"], "deployment")
        self.assertEqual(refresh["outputs"]["artifact_name"], upload["with"]["name"])
        self.assertEqual(publish["with"]["artifact_name"], "${{ needs.refresh.outputs.artifact_name }}")
        # Every downstream step must retain Actions' default success-only gate.
        for job in (refresh, deploy):
            for step in job["steps"]:
                self.assertNotIn("if", step)
                self.assertNotIn("continue-on-error", step)

    def test_failed_deploy_retry_reuses_the_successful_refresh_artifact(self):
        config = workflow("pages.yml")
        refresh, deploy = (config["jobs"][name] for name in ("refresh", "deploy"))
        self.assertEqual(refresh["outputs"]["artifact_name"], refresh["steps"][-1]["with"]["name"])
        self.assertEqual(deploy["steps"][-1]["with"]["artifact_name"],
                         "${{ needs.refresh.outputs.artifact_name }}")

    def test_uploaded_site_identifies_its_accepted_revision_and_workflow_attempt(self):
        steps = workflow("pages.yml")["jobs"]["refresh"]["steps"]
        step = next(step for step in steps if step.get("id") == "provenance")
        self.assertEqual(step["env"], {
            "CODE_REVISION": "${{ github.sha }}", "DATA_REVISION": "${{ steps.persist.outputs.revision }}",
        })
        self.assertLess(next(i for i, item in enumerate(steps) if item.get("id") == "persist"),
                        steps.index(step))
        self.assertLess(steps.index(step), len(steps) - 1)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "site").mkdir()
            env = {**os.environ, "CODE_REVISION": "a" * 40, "DATA_REVISION": "b" * 40,
                   "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2"}
            result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", step["run"]],
                                    cwd=directory, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((Path(directory) / "site/build.json").read_text()), {
                "code_revision": "a" * 40, "data_revision": "b" * 40,
                "run_id": "123", "run_attempt": "2",
            })

    def test_deployment_refuses_a_superseded_revision_or_failed_github_lookup(self):
        step = workflow("pages.yml")["jobs"]["deploy"]["steps"][0]
        self.assertEqual(step["env"], {
            "EXPECTED_REVISION": "${{ needs.refresh.outputs.revision }}",
            "REPOSITORY": "${{ github.repository }}", "GH_TOKEN": "${{ secrets.GITHUB_TOKEN }}",
        })
        with tempfile.TemporaryDirectory() as directory:
            gh = Path(directory) / "gh"
            gh.write_text('#!/bin/sh\n[ "$LOOKUP" != error ] || exit 7\nprintf "%s\\n" "$LOOKUP"\n')
            gh.chmod(0o755)
            for lookup, success in (("accepted-revision", True), ("newer-revision", False), ("error", False)):
                with self.subTest(github_response=lookup):
                    env = {**os.environ, "PATH": directory + os.pathsep + os.environ["PATH"],
                           "EXPECTED_REVISION": "accepted-revision", "LOOKUP": lookup,
                           "REPOSITORY": "owner/repo", "GH_TOKEN": "local-test-token"}
                    result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", step["run"]],
                                            env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode == 0, success, result.stderr)
                    if lookup == "newer-revision":
                        self.assertIn("main changed", result.stderr)


class GitPersistenceTests(unittest.TestCase):
    """Run the shipped workflow command against a real local Git remote."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.repo = self.root / "runner"
        self.git(self.root, "init", "--bare", str(self.remote))
        self.git(self.root, "clone", str(self.remote), str(self.repo))
        self.git(self.repo, "checkout", "-b", "main")
        self.git(self.repo, "config", "user.name", "Test Maintainer")
        self.git(self.repo, "config", "user.email", "test@example.invalid")
        (self.repo / "data").mkdir()
        for name in ("history", "status"):
            (self.repo / "data" / (name + ".json")).write_text('{"accepted": 1}\n')
        (self.repo / ".gitignore").write_text("site/\n")
        (self.repo / "README.md").write_text("unrelated source\n")
        scripts = ROOT / ".github" / "scripts"
        if scripts.exists():
            shutil.copytree(scripts, self.repo / ".github" / "scripts")
        self.git(self.repo, "add", ".")
        self.git(self.repo, "commit", "-m", "baseline")
        self.git(self.repo, "push", "origin", "HEAD:refs/heads/main")
        self.base = self.git(self.repo, "rev-parse", "HEAD").stdout.strip()
        self.git(self.repo, "checkout", "--detach", self.base)
        self.output = self.root / "output"

    def git(self, directory, *args):
        return subprocess.run(["git", "-C", str(directory), *args],
                              capture_output=True, text=True, check=True)

    def persist(self):
        step = next(step for step in workflow("pages.yml")["jobs"]["refresh"]["steps"]
                    if step.get("id") == "persist")
        self.assertEqual(step["env"], {
            "EXPECTED_REVISION": "${{ github.sha }}", "GH_TOKEN": "${{ secrets.GITHUB_TOKEN }}",
        })
        env = {**os.environ, "EXPECTED_REVISION": self.base, "GH_TOKEN": "local-test-token",
               "GITHUB_OUTPUT": str(self.output), "GIT_TERMINAL_PROMPT": "0"}
        return subprocess.run(["bash", "-e", "-o", "pipefail", "-c", step["run"]],
                              cwd=self.repo, env=env, capture_output=True, text=True)

    def test_rejected_push_fails_without_releasing_an_artifact_revision(self):
        hook = self.remote / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\necho 'simulated branch protection rejection' >&2\nexit 1\n")
        hook.chmod(0o755)
        (self.repo / "data/status.json").write_text('{"checked": 2}\n')
        result = self.persist()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("simulated branch protection rejection", result.stderr)
        self.assertIn("run a fresh workflow on main", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.git(self.remote, "rev-parse", "refs/heads/main").stdout.strip(), self.base)
        credentials = subprocess.run(["git", "-C", str(self.repo), "config", "--local",
                                      "--get-regexp", "http.*extraheader"], capture_output=True)
        self.assertEqual(credentials.returncode, 1)

    def test_unvalidated_local_commit_cannot_be_pushed(self):
        self.git(self.repo, "commit", "--allow-empty", "-m", "unvalidated local revision")
        (self.repo / "data/status.json").write_text('{"checked": 2}\n')
        result = self.persist()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checkout changed", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.git(self.remote, "rev-parse", "refs/heads/main").stdout.strip(), self.base)

    def test_unrelated_staged_files_cannot_enter_the_accepted_data_commit(self):
        (self.repo / "README.md").write_text("unvalidated staged source\n")
        self.git(self.repo, "add", "README.md")
        (self.repo / "data/status.json").write_text('{"checked": 2}\n')
        result = self.persist()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("index is not empty", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.git(self.remote, "rev-parse", "refs/heads/main").stdout.strip(), self.base)

    def test_stale_remote_is_rejected_even_when_the_refresh_changes_nothing(self):
        peer = self.root / "maintainer"
        self.git(self.root, "clone", "--branch", "main", str(self.remote), str(peer))
        self.git(peer, "config", "user.name", "Concurrent Maintainer")
        self.git(peer, "config", "user.email", "peer@example.invalid")
        (peer / "README.md").write_text("newer main\n")
        self.git(peer, "commit", "-am", "advance main")
        self.git(peer, "push", "origin", "HEAD:refs/heads/main")
        tip = self.git(peer, "rev-parse", "HEAD").stdout.strip()
        for changed in (False, True):
            with self.subTest(changed_data=changed):
                if changed:
                    (self.repo / "data/history.json").write_text('{"accepted": 2}\n')
                result = self.persist()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("main changed", result.stderr)
                self.assertFalse(self.output.exists())
                self.assertEqual(self.git(self.repo, "rev-parse", "HEAD").stdout.strip(), self.base)
                self.assertEqual(self.git(self.remote, "rev-parse", "refs/heads/main").stdout.strip(), tip)

    def test_commit_contains_only_accepted_data_and_no_change_is_a_safe_noop(self):
        result = self.persist()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD").stdout.strip(), self.base)
        self.assertEqual(self.output.read_text(), "revision=" + self.base + "\n")
        self.output.unlink()
        (self.repo / "data/history.json").write_text('{"accepted": 2}\n')
        (self.repo / "data/status.json").write_text('{"checked": 2}\n')
        (self.repo / "README.md").write_text("must not be committed\n")
        (self.repo / "data/unrelated.json").write_text("must not be committed\n")
        (self.repo / "site").mkdir()
        (self.repo / "site/index.html").write_text("must not be committed\n")
        result = self.persist()
        self.assertEqual(result.returncode, 0, result.stderr)
        changed = self.git(self.repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
        self.assertEqual(changed.stdout.splitlines(), ["data/history.json", "data/status.json"])
        revision = self.git(self.repo, "rev-parse", "HEAD").stdout.strip()
        self.assertNotEqual(revision, self.base)
        self.assertEqual(self.git(self.remote, "rev-parse", "refs/heads/main").stdout.strip(), revision)
        self.assertEqual(self.output.read_text(), "revision=" + revision + "\n")
        config = workflow("pages.yml")
        refresh = config["jobs"]["refresh"]
        self.assertEqual(refresh["outputs"]["revision"], "${{ steps.persist.outputs.revision }}")
        ids = [step.get("id", step.get("uses", step.get("name"))) for step in refresh["steps"]]
        self.assertLess(ids.index("persist"), ids.index("actions/upload-pages-artifact@v5"))
        self.assertEqual(self.git(self.repo, "config", "--local", "--get-regexp",
                                  "user\\.").stdout.strip(),
                         "user.name Test Maintainer\nuser.email test@example.invalid")


if __name__ == "__main__":
    unittest.main()
