from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from novel_generator import (
    NovelGenerator,
    NovelState,
    StartChapterError,
    parse_start_chapter,
)


SCRIPT_PATH = Path(__file__).with_name("novel_generator.py")


class RecordingClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, temperature=0.8) -> str:
        self.calls += 1
        if self.calls % 2:
            return f"第 {self.calls // 2 + 1} 章正文"
        return json.dumps(
            {
                "summary": "测试摘要",
                "timeline_events": [],
                "character_updates": {},
            },
            ensure_ascii=False,
        )


class RecordingGenerator(NovelGenerator):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.save_calls = 0

    def save_state(self, state: NovelState) -> None:
        self.save_calls += 1
        super().save_state(state)


def make_generator(root: Path, total_chapters: int = 3):
    state_path = root / "novel_state.json"
    output_dir = root / "novel_output"
    state = NovelState(
        title="测试小说",
        genre="科幻",
        premise="测试前提",
        total_chapters=total_chapters,
        words_per_chapter=100,
        style_guide="简洁",
        world_bible="测试世界观",
    )
    state_path.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    client = RecordingClient()
    generator = RecordingGenerator(
        client=client,
        state_path=state_path,
        output_dir=output_dir,
    )
    return generator, client, state_path, output_dir


class ParseStartChapterTests(unittest.TestCase):
    def test_accepts_positive_integer_strings(self) -> None:
        self.assertEqual(parse_start_chapter("1"), 1)
        self.assertEqual(parse_start_chapter("42"), 42)

    def test_rejects_non_positive_and_non_integer_strings(self) -> None:
        for value in ("0", "-1", "1.5", "abc", ""):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    argparse.ArgumentTypeError,
                    "--start 必须是正整数",
                ):
                    parse_start_chapter(value)


class CliStartArgumentTests(unittest.TestCase):
    def test_argparse_rejects_invalid_start_before_loading_state(self) -> None:
        for value in ("0", "-2", "not-an-integer"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                state_path = root / "missing-state.json"
                output_dir = root / "output"

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
                        "run",
                        "--start",
                        value,
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )

                self.assertEqual(result.returncode, 2)
                self.assertIn("--start 必须是正整数", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(state_path.exists())
                self.assertFalse(output_dir.exists())

    def test_cli_rejects_start_above_total_without_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "novel_state.json"
            output_dir = root / "output"
            state = NovelState(
                title="测试小说",
                genre="科幻",
                premise="测试前提",
                total_chapters=3,
                words_per_chapter=100,
                style_guide="简洁",
                world_bible="测试世界观",
            )
            state_path.write_text(
                json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            original_state = state_path.read_bytes()

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
                    "run",
                    "--start",
                    "4",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("total_chapters（3）", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(state_path.read_bytes(), original_state)
            self.assertTrue(output_dir.is_dir())
            self.assertEqual(list(output_dir.iterdir()), [])


class RunStartValidationTests(unittest.TestCase):
    def test_invalid_direct_start_has_no_generation_side_effects(self) -> None:
        invalid_values = (0, -1, True, 1.0, "1", 4)
        with tempfile.TemporaryDirectory() as temp_dir:
            generator, client, state_path, output_dir = make_generator(
                Path(temp_dir),
                total_chapters=3,
            )
            original_state = state_path.read_bytes()

            for value in invalid_values:
                with self.subTest(value=value):
                    with self.assertRaises(StartChapterError):
                        generator.run(resume=True, start_chapter=value)

                    self.assertEqual(client.calls, 0)
                    self.assertEqual(generator.save_calls, 0)
                    self.assertEqual(state_path.read_bytes(), original_state)
                    self.assertEqual(list(output_dir.iterdir()), [])

    def test_start_at_first_chapter_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            generator, client, _, output_dir = make_generator(
                Path(temp_dir),
                total_chapters=3,
            )

            with mock.patch("novel_generator.time.sleep"):
                generator.run(resume=True, start_chapter=1)

            self.assertEqual(client.calls, 6)
            self.assertEqual(generator.save_calls, 3)
            self.assertEqual(
                sorted(path.name for path in output_dir.iterdir()),
                ["chapter_0001.md", "chapter_0002.md", "chapter_0003.md"],
            )

    def test_start_at_total_chapters_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            generator, client, _, output_dir = make_generator(
                Path(temp_dir),
                total_chapters=3,
            )

            with mock.patch("novel_generator.time.sleep"):
                generator.run(resume=True, start_chapter=3)

            self.assertEqual(client.calls, 2)
            self.assertEqual(generator.save_calls, 1)
            self.assertEqual(
                [path.name for path in output_dir.iterdir()],
                ["chapter_0003.md"],
            )


if __name__ == "__main__":
    unittest.main()
