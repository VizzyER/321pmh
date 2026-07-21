import tempfile
import unittest
from pathlib import Path
from unittest import mock

from novel_generator import Character, NovelGenerator, NovelState


class AtomicStateSaveTests(unittest.TestCase):
    def make_state(self) -> NovelState:
        return NovelState(
            title="群星黯淡时",
            genre="科幻",
            premise="守住最后的恒星火种",
            total_chapters=3,
            words_per_chapter=3500,
            style_guide="第三人称",
            world_bible="九大环带",
            chapter_summaries=["第1章：启程"],
            timeline_events=["第1章：舰队出发"],
            characters=[Character(name="林策", profile="航道测绘师")],
        )

    def assert_no_temporary_state_files(self, root: Path) -> None:
        self.assertEqual(
            sorted(path.name for path in root.iterdir()),
            ["novel_output", "novel_state.json"],
        )

    def test_successful_save_can_be_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            generator = NovelGenerator(
                client=object(),
                state_path=root / "novel_state.json",
                output_dir=root / "novel_output",
            )
            state = self.make_state()

            generator.save_state(state)

            self.assertEqual(generator.load_state(), state)
            self.assert_no_temporary_state_files(root)

    def test_replace_failure_preserves_old_state_and_cleans_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "novel_state.json"
            old_bytes = b'{"existing":"state"}'
            state_path.write_bytes(old_bytes)
            generator = NovelGenerator(
                client=object(),
                state_path=state_path,
                output_dir=root / "novel_output",
            )

            with mock.patch("novel_generator.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    generator.save_state(self.make_state())

            self.assertEqual(state_path.read_bytes(), old_bytes)
            self.assert_no_temporary_state_files(root)

    def test_fsync_failure_preserves_old_state_and_cleans_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "novel_state.json"
            old_bytes = b'{"existing":"state"}'
            state_path.write_bytes(old_bytes)
            generator = NovelGenerator(
                client=object(),
                state_path=state_path,
                output_dir=root / "novel_output",
            )

            with mock.patch("novel_generator.os.fsync", side_effect=OSError("fsync failed")):
                with self.assertRaisesRegex(OSError, "fsync failed"):
                    generator.save_state(self.make_state())

            self.assertEqual(state_path.read_bytes(), old_bytes)
            self.assert_no_temporary_state_files(root)

    def test_save_does_not_create_missing_state_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            missing_parent = root / "missing"
            generator = NovelGenerator(
                client=object(),
                state_path=missing_parent / "novel_state.json",
                output_dir=root / "novel_output",
            )

            with self.assertRaises(FileNotFoundError):
                generator.save_state(self.make_state())

            self.assertFalse(missing_parent.exists())


if __name__ == "__main__":
    unittest.main()
