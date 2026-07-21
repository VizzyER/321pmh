import json
import tempfile
import unittest
from pathlib import Path

from novel_generator import (
    Character,
    LLMClient,
    NovelGenerator,
    NovelState,
    has_persisted_continuity_for_chapter,
)


class FakeLLMClient(LLMClient):
    def __init__(self) -> None:
        self.chat_calls: list = []

    def chat(self, messages, temperature: float = 0.8) -> str:
        self.chat_calls.append({"messages": messages, "temperature": temperature})
        if len(self.chat_calls) == 1:
            return "这是生成的章节正文。"
        return json.dumps(
            {
                "summary": "测试摘要",
                "timeline_events": ["事件一"],
                "character_updates": {},
            },
            ensure_ascii=False,
        )


def _minimal_state(**overrides) -> NovelState:
    state = NovelState(
        title="测试",
        genre="测试",
        premise="测试",
        total_chapters=3,
        words_per_chapter=100,
        style_guide="测试",
        world_bible="测试",
        characters=[Character(name="主角", profile="简介")],
    )
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


class HasPersistedContinuityForChapterTests(unittest.TestCase):
    def test_chapter_prefix_is_exact(self) -> None:
        state = _minimal_state(
            chapter_summaries=["第10章：第十章摘要"],
            timeline_events=[],
        )
        self.assertFalse(has_persisted_continuity_for_chapter(state, 1))
        self.assertTrue(has_persisted_continuity_for_chapter(state, 10))

    def test_ignores_non_string_entries(self) -> None:
        state = _minimal_state(
            chapter_summaries=[None, 42, {"bad": "entry"}, "第2章：有效摘要"],
            timeline_events=[None, "第2章：有效事件"],
        )
        self.assertTrue(has_persisted_continuity_for_chapter(state, 2))


class MissingChapterContinuityGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.state_path = self.root / "novel_state.json"
        self.output_dir = self.root / "novel_output"
        self.output_dir.mkdir()
        self.client = FakeLLMClient()
        self.generator = NovelGenerator(
            client=self.client,
            state_path=self.state_path,
            output_dir=self.output_dir,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_state(self, state: NovelState) -> bytes:
        payload = json.dumps(state.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
        self.state_path.write_bytes(payload)
        return payload

    def test_aborts_when_summary_exists_without_chapter_file(self) -> None:
        state = _minimal_state(chapter_summaries=["第1章：已有摘要"])
        original_state_bytes = self._write_state(state)
        chapter_file = self.output_dir / "chapter_0001.md"

        with self.assertRaises(RuntimeError) as ctx:
            self.generator.run(resume=True, start_chapter=1)

        self.assertIn("章节文件缺失但连续性状态已存在", str(ctx.exception))
        self.assertEqual(self.client.chat_calls, [])
        self.assertFalse(chapter_file.exists())
        self.assertEqual(self.state_path.read_bytes(), original_state_bytes)

    def test_aborts_when_only_timeline_exists_without_chapter_file(self) -> None:
        state = _minimal_state(timeline_events=["第1章：已有事件"])
        original_state_bytes = self._write_state(state)
        chapter_file = self.output_dir / "chapter_0001.md"

        with self.assertRaises(RuntimeError) as ctx:
            self.generator.run(resume=True, start_chapter=1)

        self.assertIn("章节文件缺失但连续性状态已存在", str(ctx.exception))
        self.assertEqual(self.client.chat_calls, [])
        self.assertFalse(chapter_file.exists())
        self.assertEqual(self.state_path.read_bytes(), original_state_bytes)

    def test_generates_fresh_chapter_when_no_continuity_record(self) -> None:
        state = _minimal_state(total_chapters=1)
        self._write_state(state)
        chapter_file = self.output_dir / "chapter_0001.md"

        self.generator.run(resume=True, start_chapter=1)

        self.assertEqual(len(self.client.chat_calls), 2)
        self.assertTrue(chapter_file.exists())
        loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertIn("第1章：测试摘要", loaded["chapter_summaries"])
        self.assertIn("第1章：事件一", loaded["timeline_events"])


if __name__ == "__main__":
    unittest.main()
