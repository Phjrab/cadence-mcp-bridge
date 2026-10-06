"""Test the tracked export rules using synthetic repositories, never Cadence data.

These tests verify local Git behavior only. Exact-candidate GitHub ZIP/tarball
inspection, existing repository gates and rights review remain separate.
"""

import hashlib
import importlib.util
import io
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

RULES_FILE = Path(__file__).resolve().parents[2] / "docs" / ".gitattributes"
AUDIT_FILE = RULES_FILE.parents[1] / "scripts" / "verify-git-archive.py"
SPEC = importlib.util.spec_from_file_location("git_archive_audit", AUDIT_FILE)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


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


class ExactArchiveAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="exact-archive-test-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "snapshot.zip"
        self.files = {
            "LICENSE": b"synthetic license\n",
            "NOTICE": b"synthetic notice\n",
            "THIRD_PARTY_NOTICES.md": b"synthetic scope\n",
            "README.md": b"synthetic guide\n",
            "pyproject.toml": b"synthetic metadata\n",
            "src/bridge.py": b"# synthetic original\n",
        }
        self.blobs = {}
        for name, data in {**self.files, "docs/agent_plan/import.md": b"synthetic import"}.items():
            self.blobs[name] = hashlib.sha1(
                b"blob " + str(len(data)).encode() + b"\0" + data
            ).hexdigest()

    def write_zip(self, prefix: str = "", extras: dict[str, bytes] | None = None) -> None:
        with zipfile.ZipFile(self.path, "w") as archive:
            for name, data in {**self.files, **(extras or {})}.items():
                archive.writestr(prefix + name, data)

    def test_local_and_hosted_prefix_exact_content(self) -> None:
        for prefix in ("", "repository-candidate/"):
            self.write_zip(prefix)
            result = AUDIT.inspect(self.path, self.blobs)
            self.assertEqual(result["status"], "IMPORT_EXCLUDED_VERIFIED")
            self.assertEqual(result["rights_status"], "LEGAL_REVIEW_REQUIRED")
            self.assertEqual(result["publication_status"], "PUBLICATION_NOT_AUTHORIZED")
            self.assertEqual(result["imported_files_excluded"], 1)

    def test_import_file_or_empty_directory_rejected(self) -> None:
        for name in ("docs/agent_plan/import.md", "docs/agent_plan/"):
            self.write_zip("repository-candidate/", {name: b""})
            with self.assertRaises(ValueError):
                AUDIT.inspect(self.path, self.blobs)

    def test_missing_modified_extra_and_unsafe_content_rejected(self) -> None:
        for extra in ({"NOTICE": b"altered"}, {"extra.txt": b"x"}, {"../escape": b"x"}):
            self.write_zip(extras=extra)
            with self.assertRaises(ValueError):
                AUDIT.inspect(self.path, self.blobs)
        del self.files["NOTICE"]
        self.write_zip()
        with self.assertRaises(ValueError):
            AUDIT.inspect(self.path, self.blobs)

    def test_duplicate_link_and_mixed_root_rejected(self) -> None:
        self.write_zip()
        with zipfile.ZipFile(self.path, "a") as archive:
            archive.writestr("other/LICENSE", b"duplicate license")
        with self.assertRaises(ValueError):
            AUDIT.inspect(self.path, self.blobs)
        self.write_zip()
        with zipfile.ZipFile(self.path, "a") as archive:
            entry = zipfile.ZipInfo("symlink")
            entry.create_system = 3
            entry.external_attr = 0o120777 << 16
            archive.writestr(entry, "target")
        with self.assertRaises(ValueError):
            AUDIT.inspect(self.path, self.blobs)
        self.write_zip("repository-candidate/")
        with zipfile.ZipFile(self.path, "a") as archive:
            archive.writestr("unprefixed", b"x")
        with self.assertRaises(ValueError):
            AUDIT.inspect(self.path, self.blobs)

    def test_tar_link_rejected(self) -> None:
        path = self.path.with_suffix(".tar")
        with tarfile.open(path, "w") as archive:
            member = tarfile.TarInfo("link")
            member.type = tarfile.SYMTYPE
            member.linkname = "../escape"
            archive.addfile(member)
        with self.assertRaises(ValueError):
            AUDIT.read_members(path)

    def test_expansion_limit_rejected(self) -> None:
        self.write_zip()
        old_limit = AUDIT.MAX_EXPANDED_BYTES
        try:
            AUDIT.MAX_EXPANDED_BYTES = 1
            with self.assertRaises(ValueError):
                AUDIT.inspect(self.path, self.blobs)
        finally:
            AUDIT.MAX_EXPANDED_BYTES = old_limit


if __name__ == "__main__":
    unittest.main()
