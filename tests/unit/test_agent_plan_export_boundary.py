"""Test the tracked export rules using synthetic repositories, never Cadence data.

These tests verify local Git behavior only. Exact-candidate GitHub ZIP/tarball
inspection, existing repository gates and rights review remain separate.
"""

import io
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

RULES_FILE = Path(__file__).resolve().parents[2] / "docs" / ".gitattributes"


@unittest.skipUnless(shutil.which("git"), "git is required for archive-boundary tests")
class AgentPlanExportBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="agent-plan-export-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "--quiet")
        self.payloads = {
            "docs/.gitattributes": RULES_FILE.read_bytes(),
            "docs/agent_plan/README.md": b"synthetic imported plan\n",
            "docs/agent_plan/archive/nested/old.md": b"synthetic old plan\n",
            "docs/agent_plan/tools/verify_package.py": b"# synthetic helper only\n",
            "docs/agent_plan_extra/README.md": b"unrelated directory\n",
            "docs/guide.md": b"original guide\n",
            "src/bridge.py": b"# original source fixture\n",
            "LICENSE": b"synthetic license fixture, not a real license grant\n",
        }
        for name, data in self.payloads.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.git("add", "--", *self.payloads)
        self.git("commit", "--quiet", "-m", "synthetic archive fixture")

    def git(self, *arguments: str) -> bytes:
        result = subprocess.run(
            [
                "git", "-C", str(self.root),
                "-c", "user.name=Archive boundary test",
                "-c", "user.email=archive-test@example.invalid",
                "-c", "core.autocrlf=false",
                "-c", "core.attributesFile=",
                *arguments,
            ],
            check=True, capture_output=True, timeout=30,
        )
        return result.stdout

    def tar_files(self) -> dict[str, bytes]:
        archive = self.git("archive", "--format=tar", "HEAD")
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as stream:
            contents = {}
            for member in stream.getmembers():
                if member.isfile():
                    payload = stream.extractfile(member)
                    assert payload is not None
                    contents[member.name] = payload.read()
            return contents

    def expected(self) -> dict[str, bytes]:
        return {
            name: value for name, value in self.payloads.items()
            if not name.startswith("docs/agent_plan/")
        }

    def test_tar_excludes_only_imported_tree(self) -> None:
        self.assertEqual(self.tar_files(), self.expected())

    def test_zip_excludes_only_imported_tree(self) -> None:
        import zipfile

        archive = self.git("archive", "--format=zip", "HEAD")
        with zipfile.ZipFile(io.BytesIO(archive)) as stream:
            contents = {
                item.filename: stream.read(item) for item in stream.infolist()
                if not item.is_dir()
            }
        self.assertEqual(contents, self.expected())

    def test_imported_files_remain_tracked_and_byte_identical(self) -> None:
        tracked = set(self.git("ls-files", "-z").decode().split("\0"))
        for name, data in self.payloads.items():
            self.assertIn(name, tracked)
            self.assertEqual((self.root / name).read_bytes(), data)
            self.assertEqual(self.git("show", "HEAD:" + name), data)

    def test_worktree_rules_do_not_rewrite_committed_archive(self) -> None:
        (self.root / "docs/.gitattributes").write_text("# uncommitted change\n")
        self.assertEqual(self.tar_files(), self.expected())

    def test_missing_rules_are_a_real_negative_control(self) -> None:
        (self.root / "docs/.gitattributes").write_text("# no exclusion\n")
        self.git("add", "--", "docs/.gitattributes")
        self.git("commit", "--quiet", "-m", "remove synthetic export rules")
        self.assertIn("docs/agent_plan/README.md", self.tar_files())
        self.assertIn("docs/agent_plan/archive/nested/old.md", self.tar_files())


if __name__ == "__main__":
    unittest.main()
