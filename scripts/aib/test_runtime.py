"""Reject incomplete or corrupt release downloads before using the binaries."""

import io
from contextlib import ExitStack
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import runtime


class ReleaseVerificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="rtk-artifacts-test-")
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name)
        contexts = ExitStack()
        self.addCleanup(contexts.close)
        contexts.enter_context(patch.object(runtime, "OUTPUT", self.output))
        contexts.enter_context(patch.dict(os.environ, {
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123",
        }))
        for target in runtime.TARGETS:
            path = self.output / runtime.archive_name(target)
            content = f"fixture binary: {target}".encode()
            if path.suffix == ".zip":
                with zipfile.ZipFile(path, "w") as bundle:
                    bundle.writestr("rtk.exe", content)
            else:
                with tarfile.open(path, "w:gz") as bundle:
                    info = tarfile.TarInfo("rtk")
                    info.size = len(content)
                    info.mode = 0o755
                    bundle.addfile(info, io.BytesIO(content))

    def test_complete_release(self):
        runtime.manifest("v0.42.3-aib.1")
        runtime.verify(self.output)

    def test_corrupt_archive(self):
        runtime.manifest("v0.42.3-aib.1")
        (self.output / runtime.archive_name(runtime.TARGETS[0])).write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
            runtime.verify(self.output)

    def test_missing_target(self):
        (self.output / runtime.archive_name(runtime.TARGETS[0])).unlink()
        with self.assertRaises(FileNotFoundError):
            runtime.manifest("v0.42.3-aib.1")

    def test_duplicate_checksum(self):
        runtime.manifest("v0.42.3-aib.1")
        path = self.output / "checksums.txt"
        text = path.read_text(encoding="utf-8")
        path.write_text(text + text.splitlines()[0] + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "repeated checksum"):
            runtime.verify(self.output)

    def test_reject_upstream_release_tag(self):
        with self.assertRaisesRegex(ValueError, "prerelease tag"):
            runtime.manifest("v0.42.3")


if __name__ == "__main__":
    unittest.main()
