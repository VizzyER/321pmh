import tempfile
import unittest
from pathlib import Path
from unittest import mock

from novel_generator import (
    Character,
    NovelGenerator,
    _normalize_character_updates,
    _normalize_summary,
)


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)

    def chat(self, messages, temperature=0.8):
        if not self._responses:
            raise AssertionError("No fake response left for chat()")
        return self._responses.pop(0)


class NovelGeneratorSummaryCharacterUpdatesTests(unittest.TestCase):
    def test_normalize_summary_rejects_non_strings(self):
        self.assertEqual(_normalize_summary({"bad": "type"}), "（无摘要）")
        self.assertEqual(_normalize_summary(["bad"]), "（无摘要）")
        self.assertEqual(_normalize_summary(123), "（无摘要）")
        self.assertEqual(_normalize_summary(True), "（无摘要）")
        self.assertEqual(_normalize_summary(None), "（无摘要）")
        self.assertEqual(_normalize_summary("   "), "（无摘要）")
        self.assertEqual(_normalize_summary("  合法摘要  "), "合法摘要")

    def test_normalize_character_updates_filters_mixed_mapping(self):
        raw = {
            " Alice ": "  觉醒  ",
            "Bob": "",
            "Carol": ["not", "string"],
            "": "valid",
            "   ": "valid",
            "Dave": "   ",
            1: "ignored",
            "Eve": {"nested": "ignored"},
            " Frank ": "  新线索  ",
        }

        self.assertEqual(
            _normalize_character_updates(raw),
            {
                "Alice": "觉醒",
                "Frank": "新线索",
            },
        )
        self.assertEqual(_normalize_character_updates(["not", "a", "dict"]), {})

    def test_run_uses_placeholder_for_non_string_summary_and_ignores_non_mapping_updates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            state_path = base / "novel_state.json"
            output_dir = base / "novel_output"
            client = FakeClient([
                "第一章正文",
                (
                    '{"summary": {"bad": "type"}, '
                    '"timeline_events": [], '
                    '"character_updates": ["Alice changed"]}'
                ),
            ])
            generator = NovelGenerator(client=client, state_path=state_path, output_dir=output_dir)
            generator.create_initial_state(
                title="测试小说",
                genre="奇幻",
                premise="测试前提",
                total_chapters=1,
                words_per_chapter=1000,
                style_guide="简洁",
                world_bible="测试世界",
                characters=[Character(name="Alice", profile="初始设定")],
            )

            with mock.patch("novel_generator.time.sleep", return_value=None):
                generator.run(resume=True, start_chapter=1)

            chapter_text = (output_dir / "chapter_0001.md").read_text(encoding="utf-8")
            state = generator.load_state()

            self.assertIn("（无摘要）", chapter_text)
            self.assertIn("**人物变化**\n- （无）", chapter_text)
            self.assertEqual(state.chapter_summaries, ["第1章：（无摘要）"])
            self.assertEqual(state.characters[0].profile, "初始设定")
            self.assertNotIn("{'bad': 'type'}", chapter_text)
            self.assertNotIn("['Alice changed']", chapter_text)

    def test_run_reuses_stripped_summary_and_updates_in_outline_and_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            state_path = base / "novel_state.json"
            output_dir = base / "novel_output"
            client = FakeClient([
                "第二章正文",
                (
                    '{"summary": "  合法摘要  ", '
                    '"timeline_events": ["事件一"], '
                    '"character_updates": {" Alice ": "  觉醒  ", "Mallory": "  "} }'
                ),
            ])
            generator = NovelGenerator(client=client, state_path=state_path, output_dir=output_dir)
            generator.create_initial_state(
                title="测试小说",
                genre="奇幻",
                premise="测试前提",
                total_chapters=1,
                words_per_chapter=1000,
                style_guide="简洁",
                world_bible="测试世界",
                characters=[Character(name="Alice", profile="初始设定")],
            )

            with mock.patch("novel_generator.time.sleep", return_value=None):
                generator.run(resume=True, start_chapter=1)

            chapter_text = (output_dir / "chapter_0001.md").read_text(encoding="utf-8")
            state = generator.load_state()

            self.assertIn("**剧情摘要**\n合法摘要", chapter_text)
            self.assertIn("**人物变化**\n- Alice: 觉醒", chapter_text)
            self.assertEqual(state.chapter_summaries, ["第1章：合法摘要"])
            self.assertEqual(state.timeline_events, ["第1章：事件一"])
            self.assertEqual(state.characters[0].profile, "初始设定 | 最近变化：觉醒")


if __name__ == "__main__":
    unittest.main()
