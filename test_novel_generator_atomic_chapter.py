import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from novel_generator import _atomic_write_text


class _FailingWriter:
    def __init__(self, raw_file):
        self.raw_file = raw_file

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.raw_file.close()

    def write(self, data):
        self.raw_file.write(data[:1])
        raise OSError("simulated write failure")


class AtomicWriteTextTests(unittest.TestCase):
    def assert_no_temporary_file(self, target: Path) -> None:
        pattern = f".{target.name}.*.tmp"
        self.assertEqual([], list(target.parent.glob(pattern)))

    def test_success_writes_exact_utf8_content_without_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "chapter_0001.md"
            content = "## 第一章\n\n正文。\n"

            _atomic_write_text(target, content)

            self.assertEqual(content.encode("utf-8"), target.read_bytes())
            self.assert_no_temporary_file(target)

    def test_replace_failure_preserves_old_target_and_cleans_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "chapter_0001.md"
            old_content = b"existing chapter\n"
            target.write_bytes(old_content)

            with mock.patch("novel_generator.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    _atomic_write_text(target, "replacement\n")

            self.assertEqual(old_content, target.read_bytes())
            self.assert_no_temporary_file(target)

    def test_base_exception_during_replace_also_cleans_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "chapter_0001.md"

            with mock.patch("novel_generator.os.replace", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    _atomic_write_text(target, "chapter\n")

            self.assertFalse(target.exists())
            self.assert_no_temporary_file(target)

    def test_fsync_failure_leaves_no_target_or_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "chapter_0001.md"

            with mock.patch("novel_generator.os.fsync", side_effect=OSError("fsync failed")):
                with self.assertRaises(OSError):
                    _atomic_write_text(target, "chapter\n")

            self.assertFalse(target.exists())
            self.assert_no_temporary_file(target)

    def test_write_failure_leaves_no_target_or_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "chapter_0001.md"
            real_fdopen = os.fdopen

            def failing_fdopen(fd, mode):
                return _FailingWriter(real_fdopen(fd, mode))

            with mock.patch("novel_generator.os.fdopen", side_effect=failing_fdopen):
                with self.assertRaises(OSError):
                    _atomic_write_text(target, "chapter\n")

            self.assertFalse(target.exists())
            self.assert_no_temporary_file(target)


if __name__ == "__main__":
    unittest.main()
