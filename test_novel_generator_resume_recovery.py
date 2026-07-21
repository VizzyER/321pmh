import tempfile
import unittest
from pathlib import Path

from novel_generator import Character, NovelGenerator, NovelState


class NoCallClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, temperature=0.8):
        self.calls += 1
        raise AssertionError("resume recovery must not call the model")


class ResumeRecoveryTests(unittest.TestCase):
    def make_generator(self, root: Path, total_chapters: int = 1):
        state_path = root / "novel_state.json"
        output_dir = root / "novel_output"
        client = NoCallClient()
        generator = NovelGenerator(client, state_path, output_dir)
        state = NovelState(
            title="测试小说",
            genre="悬疑",
            premise="测试断点恢复",
            total_chapters=total_chapters,
            words_per_chapter=1000,
            style_guide="简洁",
            world_bible="测试世界",
            characters=[
                Character(name="林策", profile="谨慎"),
                Character(name="苏岚", profile="冷静"),
            ],
        )
        generator.save_state(state)
        return generator, client, state_path, output_dir

    def test_recovers_orphan_outlines_and_persists_without_model_calls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generator, client, state_path, output_dir = self.make_generator(
                Path(temp_dir), total_chapters=2
            )
            chapter_one_outline = generator.build_chapter_outline(
                1,
                {
                    "summary": "林策发现失踪档案，决定连夜追查。",
                    "timeline_events": ["林策取得密钥", "档案指向旧港"],
                    "character_updates": {
                        "林策": "开始怀疑议会",
                        "不在角色表": "留下无法匹配的线索",
                    },
                },
            )
            chapter_one_body = "正文中的以下标记不得参与恢复：\n**关键事件**"
            (output_dir / "chapter_0001.md").write_text(
                f"{chapter_one_outline}\n\n---\n\n{chapter_one_body.strip()}\n",
                encoding="utf-8",
            )

            chapter_two_outline = generator.build_chapter_outline(
                2,
                {
                    "summary": "苏岚封锁旧港入口。",
                    "timeline_events": [],
                    "character_updates": {},
                },
            )
            chapter_two_body = "第二章正文。"
            (output_dir / "chapter_0002.md").write_text(
                f"{chapter_two_outline}\n\n---\n\n{chapter_two_body.strip()}\n",
                encoding="utf-8",
            )

            generator.run(resume=True)

            repaired = generator.load_state()
            self.assertEqual(client.calls, 0)
            self.assertEqual(
                repaired.chapter_summaries,
                [
                    "第1章：林策发现失踪档案，决定连夜追查。",
                    "第2章：苏岚封锁旧港入口。",
                ],
            )
            self.assertEqual(
                repaired.timeline_events,
                ["第1章：林策取得密钥", "第1章：档案指向旧港"],
            )
            self.assertEqual(
                repaired.characters[0].profile,
                "谨慎 | 最近变化：开始怀疑议会",
            )
            self.assertEqual(repaired.characters[1].profile, "冷静")
            self.assertIn(
                '"第2章：苏岚封锁旧港入口。"',
                state_path.read_text(encoding="utf-8"),
            )

    def test_already_recorded_chapter_is_idempotently_skipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generator, client, state_path, output_dir = self.make_generator(Path(temp_dir))
            state = generator.load_state()
            state.chapter_summaries = ["第1章：已记录"]
            state.timeline_events = ["第1章：已有事件"]
            generator.save_state(state)
            original_state = state_path.read_bytes()
            (output_dir / "chapter_0001.md").write_text(
                "这个文件不需要再次解析。",
                encoding="utf-8",
            )

            generator.run(resume=True)

            self.assertEqual(client.calls, 0)
            self.assertEqual(state_path.read_bytes(), original_state)

    def test_invalid_or_mismatched_outline_fails_without_side_effects(self):
        invalid_outlines = {
            "malformed": (
                "## 第1章细纲摘要\n\n"
                "**剧情摘要**\n摘要\n\n"
                "**人物变化**\n- （无）\n\n"
                "---\n\n正文\n"
            ),
            "mismatched": (
                "## 第2章细纲摘要\n\n"
                "**剧情摘要**\n摘要\n\n"
                "**关键事件**\n- （无）\n\n"
                "**人物变化**\n- （无）\n\n"
                "---\n\n正文\n"
            ),
        }
        for label, outline in invalid_outlines.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                generator, client, state_path, output_dir = self.make_generator(Path(temp_dir))
                original_state = state_path.read_bytes()
                (output_dir / "chapter_0001.md").write_text(outline, encoding="utf-8")

                with self.assertRaisesRegex(RuntimeError, "无法恢复第1章连续性状态"):
                    generator.run(resume=True)

                self.assertEqual(client.calls, 0)
                self.assertEqual(state_path.read_bytes(), original_state)


if __name__ == "__main__":
    unittest.main()
