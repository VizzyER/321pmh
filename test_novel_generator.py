import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from novel_generator import NovelGenerator, ProjectInitializationError


SCRIPT_PATH = Path(__file__).with_name("novel_generator.py")


class InitializationSafetyTests(unittest.TestCase):
    def make_generator(self, state_path: Path, output_dir: Path) -> NovelGenerator:
        return NovelGenerator(client=object(), state_path=state_path, output_dir=output_dir)

    def initialize(self, generator: NovelGenerator):
        return generator.create_initial_state(
            title="测试小说",
            genre="科幻",
            premise="测试前提",
            total_chapters=3,
            words_per_chapter=1000,
            style_guide="简洁",
            world_bible="测试世界观",
            characters=[],
        )

    def test_fresh_state_and_empty_output_initialize_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "novel_state.json"
            output_dir = root / "novel_output"
            output_dir.mkdir()

            state = self.initialize(self.make_generator(state_path, output_dir))

            self.assertEqual(state.title, "测试小说")
            self.assertTrue(state_path.is_file())
            self.assertEqual(list(output_dir.iterdir()), [])

    def test_existing_state_file_is_rejected_without_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "novel_state.json"
            output_dir = root / "novel_output"
            original = b'{"title": "existing"}\n'
            state_path.write_bytes(original)

            with self.assertRaises(ProjectInitializationError):
                self.initialize(self.make_generator(state_path, output_dir))

            self.assertEqual(state_path.read_bytes(), original)
            self.assertFalse(output_dir.exists())

    def test_existing_state_directory_is_rejected_without_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "novel_state.json"
            output_dir = root / "novel_output"
            state_path.mkdir()
            marker = state_path / "keep.txt"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaises(ProjectInitializationError):
                self.initialize(self.make_generator(state_path, output_dir))

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertFalse(output_dir.exists())

    def test_nonempty_output_is_rejected_without_creating_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "novel_state.json"
            output_dir = root / "novel_output"
            output_dir.mkdir()
            chapter = output_dir / "chapter_0001.md"
            original = b"old chapter\n"
            chapter.write_bytes(original)

            with self.assertRaises(ProjectInitializationError):
                self.initialize(self.make_generator(state_path, output_dir))

            self.assertFalse(os.path.lexists(state_path))
            self.assertEqual(chapter.read_bytes(), original)
            self.assertEqual(list(output_dir.iterdir()), [chapter])

    def test_dangling_state_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "novel_state.json"
            output_dir = root / "novel_output"
            try:
                state_path.symlink_to(root / "missing-state.json")
            except (NotImplementedError, OSError) as e:
                self.skipTest(f"symlinks are unavailable: {e}")

            with self.assertRaises(ProjectInitializationError):
                self.initialize(self.make_generator(state_path, output_dir))

            self.assertTrue(state_path.is_symlink())
            self.assertFalse(state_path.exists())
            self.assertFalse(output_dir.exists())

    def test_cli_rejection_is_actionable_and_has_no_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "novel_state.json"
            output_dir = root / "novel_output"
            original = "existing state\n"
            state_path.write_text(original, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--api-key",
                    "unused",
                    "--state",
                    str(state_path),
                    "--output",
                    str(output_dir),
                    "init",
                    "--title",
                    "测试小说",
                    "--genre",
                    "科幻",
                    "--premise",
                    "测试前提",
                    "--world-bible",
                    "测试世界观",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)
            self.assertIn("--state/--output", result.stderr)
            self.assertIn("备份", result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)
            self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()
